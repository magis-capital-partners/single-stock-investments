"""Point-in-time walk-forward backtest (production research gate)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .backtest import rebalance_points, simulate
from .config import load_mandate
from .constraints import apply_constraints
from .encoder import train_encoder
from .ensemble import deflated_sharpe
from .features import build_features, rows_at_rebalance
from .genetic import run_ga
from .pit import pit_mandate_cfg
from .pit_snapshot import PIT_BACKTEST_PATH
from .policies import apply_policy, policy_equal_weight, policy_irr_ranked
from .prices import build_return_panel
from .regime import macro_state_as_of, merge_regime, regime_constraint_overrides
from .research_events import load_events, purge_tickers_at_rebalance


def _research_regime_label(rows: list[dict], mandate: dict) -> str:
    thresh = (mandate.get("regime") or {}).get("falsifier_stress_threshold", 3)
    total_f = sum(r.get("falsifier_count", 0) for r in rows)
    if total_f >= thresh:
        return "stressed"
    stale = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > 120)
    if stale >= len(rows) // 2:
        return "adapting"
    return "calm"


def slice_panel(panel: dict, end_index: int, start_index: int = 0) -> dict:
    end_index = min(end_index, len(panel["dates"]) - 1)
    start_index = max(0, min(start_index, end_index))
    dates = panel["dates"][start_index : end_index + 1]
    returns = {
        t: panel["returns_by_ticker"][t][start_index : end_index + 1]
        for t in panel["returns_by_ticker"]
    }
    return {"dates": dates, "returns_by_ticker": returns, "sources": panel.get("sources")}


def make_rows_provider(lag_days: int, purge_days: int, events: list[dict]):
    def provider(as_of: str, _qi: int) -> list[dict]:
        rows = rows_at_rebalance(as_of, lag_days=lag_days)
        tickers = purge_tickers_at_rebalance(as_of, [r["ticker"] for r in rows], events, purge_days)
        return [r for r in rows if r["ticker"] in tickers]

    return provider


def run_pit_backtest(fast: bool = False) -> dict:
    mandate_doc = load_mandate()
    pit_cfg = pit_mandate_cfg(mandate_doc)
    training = dict(mandate_doc.get("training") or {})
    if fast:
        training.update({"ga_population": 8, "ga_generations": 4, "encoder_epochs": 15, "price_history_months": 30})

    lag = int(pit_cfg.get("research_publication_lag_days", 0))
    purge_days = int(pit_cfg.get("purge_days", 120))
    min_train = int(pit_cfg.get("min_train_rebalances", 2))
    min_oos_periods = int(pit_cfg.get("oos_min_periods", 12))
    allow_latent_pit = bool(pit_cfg.get("encoder_in_pit", False))
    events = load_events()

    latest = build_features()
    rows_seed = latest["tickers"]
    if not rows_seed:
        return {"error": "no_holdings"}

    panel = build_return_panel(
        [
            {"ticker": r["ticker"], "market": r.get("market"), "irr_base_pct": r.get("irr_base_pct")}
            for r in rows_seed
        ],
        months=training.get("price_history_months", 60),
        allow_synthetic=bool(pit_cfg.get("allow_synthetic_returns", False)),
    )
    dates = panel["dates"]
    freq = (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual")
    rebals = rebalance_points(dates, freq)
    if len(rebals) < 2:
        return {
            "error": "insufficient_rebalances",
            "rebalance_points": max(0, len(rebals) - 1),
            "min_train_rebalances": min_train,
            "months": len(dates),
        }

    rows_provider = make_rows_provider(lag, purge_days, events)
    kappa = (mandate_doc.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)
    n_trials = (mandate_doc.get("evolution") or {}).get("policy_trials", 8)

    def mandate_at(as_of: str) -> dict:
        rows = rows_provider(as_of, 0)
        research = _research_regime_label(rows, mandate_doc)
        macro = macro_state_as_of(as_of[:7])
        regime = merge_regime(research, macro, mandate_doc)
        return {**mandate_doc, "mandate": regime_constraint_overrides(regime, mandate_doc)}

    ira_genome = {
        **(mandate_doc.get("mandate") or {}),
        "ira_scoring": mandate_doc.get("ira_scoring") or {},
        "top_k": (mandate_doc.get("mandate") or {}).get("max_names", 12),
    }

    def pit_policy_sim(policy_name: str, genome: dict | None, start_idx: int, end_idx: int) -> dict:
        sub = slice_panel(panel, end_idx, start_idx)
        tickers = list(panel["returns_by_ticker"].keys())

        def pfn(active, qi):
            as_of = sub["dates"][qi]
            rrows = rows_provider(as_of, qi)
            g = genome or {}
            return apply_policy(policy_name, rrows, g, None)

        m = mandate_at(sub["dates"][0])
        return simulate(
            tickers,
            sub["dates"],
            sub["returns_by_ticker"],
            pfn,
            m,
            None,
            rows_provider=rows_provider,
        )

    train_end_rebal = rebals[min_train] if len(rebals) > min_train else rebals[-2]
    train_end_idx = train_end_rebal
    train_panel = slice_panel(panel, train_end_idx)

    train_rows = rows_provider(dates[train_end_idx], 0)
    latent = None
    enc_meta: dict = {}
    if allow_latent_pit and train_rows:
        _, latent, enc_meta = train_encoder(
            train_rows,
            n_factors=training.get("latent_factors", 5),
            epochs=training.get("encoder_epochs", 40),
            lr=training.get("encoder_lr", 0.02),
        )

    best_genome, ga_hist, _ = run_ga(
        train_rows,
        train_panel,
        mandate_at(dates[train_end_idx]),
        latent if allow_latent_pit else None,
        training,
        pit_mode=True,
        rows_provider=rows_provider,
    )

    bt_train_ira = pit_policy_sim("ira_marvin", ira_genome, 0, train_end_idx)
    bt_train_eq = pit_policy_sim("equal_weight", {}, 0, train_end_idx)
    bt_train_irr = pit_policy_sim("irr_ranked", {"top_k": 12}, 0, train_end_idx)

    def ga_policy_sim(start_idx: int, end_idx: int) -> dict:
        sub = slice_panel(panel, end_idx, start_idx)
        tickers = list(panel["returns_by_ticker"].keys())

        def pfn(active, qi):
            as_of = sub["dates"][qi]
            rrows = rows_provider(as_of, qi)
            return apply_policy(
                best_genome.get("policy", "irr_ranked"),
                rrows,
                {**best_genome, "use_latent": False},
                None,
            )

        return simulate(
            tickers,
            sub["dates"],
            sub["returns_by_ticker"],
            pfn,
            mandate_at(sub["dates"][0]),
            None,
            rows_provider=rows_provider,
        )

    bt_train_ga = ga_policy_sim(0, train_end_idx)
    bt_oos_ga = ga_policy_sim(train_end_idx, len(dates) - 1)
    bt_oos_ira = pit_policy_sim("ira_marvin", ira_genome, train_end_idx, len(dates) - 1)
    bt_oos_eq = pit_policy_sim("equal_weight", {}, train_end_idx, len(dates) - 1)

    def score(bt: dict) -> float:
        if bt.get("error"):
            return -1e9
        return deflated_sharpe(bt.get("sharpe_annualized", 0) - kappa * bt.get("avg_turnover_one_way", 0), n_trials)

    oos_sharpe = bt_oos_ga.get("sharpe_annualized")
    oos_periods = bt_oos_ga.get("periods") or 0
    min_sharpe = (mandate_doc.get("mandate") or {}).get("ml_champion_min_sharpe", 0.25)
    ml_oos_ok = (
        not bt_oos_ga.get("error")
        and oos_periods >= min_oos_periods
        and (oos_sharpe or -999) >= min_sharpe
        and score(bt_oos_ga) > score(bt_oos_ira)
    )

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "pit_backtest",
        "train_end_date": dates[train_end_idx],
        "train_rebalances": min_train,
        "benchmarks": {
            "train": {
                "ira_marvin": bt_train_ira,
                "equal_weight": bt_train_eq,
                "irr_ranked": bt_train_irr,
                "genetic": bt_train_ga,
            },
            "oos": {
                "ira_marvin": bt_oos_ira,
                "equal_weight": bt_oos_eq,
                "genetic": bt_oos_ga,
            },
        },
        "genetic_genome": best_genome,
        "ga_generations": ga_hist,
        "encoder_meta": enc_meta,
        "pit_config": pit_cfg,
        "ml_oos_eligible": ml_oos_ok,
        "oos_sharpe_genetic": oos_sharpe,
        "oos_periods": oos_periods,
        "price_panel": {
            "months": len(dates),
            "sources": panel.get("sources"),
            "synthetic_count": sum(1 for s in (panel.get("sources") or {}).values() if s == "synthetic_irr_prior"),
        },
        "lag_days": lag,
    }

    PIT_BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIT_BACKTEST_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out
