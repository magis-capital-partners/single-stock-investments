"""Run Darwin phases 0–4: features, evolution, ensemble, regime, gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .attribution import factor_attribution
from .backtest import benchmark_buy_hold, simulate
from .config import (
    BACKTEST_REPORT_PATH,
    DATA_DIR,
    FEATURES_PATH,
    IRA_WEIGHTS_PATH,
    PORTFOLIO_PATH,
    load_mandate,
)
from .constraints import apply_constraints, apply_ira_stance_caps, weights_to_list
from .encoder import train_encoder
from .ensemble import blend_weights, deflated_sharpe
from .features import build_features
from .gates import human_review_flags
from .genetic import run_ga
from .persistence import append_lineage, load_population
from .pit_snapshot import save_snapshot
from .policies import apply_policy, policy_equal_weight, policy_irr_ranked
from .ppo import ppo_weights, train_ppo
from .prices import build_return_panel, load_returns_csv
from .regime import latest_macro_state, merge_regime, regime_constraint_overrides


def _research_regime_label(rows: list[dict], mandate: dict) -> str:
    thresh = (mandate.get("regime") or {}).get("falsifier_stress_threshold", 3)
    total_f = sum(r.get("falsifier_count", 0) for r in rows)
    if total_f >= thresh:
        return "stressed"
    stale = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > 120)
    if stale >= len(rows) // 2:
        return "adapting"
    return "calm"


def load_previous_weights() -> dict[str, float]:
    if not IRA_WEIGHTS_PATH.exists():
        return {}
    try:
        data = json.loads(IRA_WEIGHTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, float] = {}
    for row in data.get("weights") or []:
        t = row.get("ticker")
        pct = row.get("weight_pct")
        if t and pct is not None:
            out[t] = float(pct) / 100.0
    return out


def _spy_panel(dates: list[str]) -> list[float]:
    loaded = load_returns_csv("SPY")
    if not loaded:
        loaded = load_returns_csv("spy")
    if not loaded:
        return [0.0] * len(dates)
    d2r = dict(zip(loaded[0], loaded[1]))
    return [d2r.get(d, 0.0) for d in dates]


def sync_ira_target_weights(
    target_w: dict[str, float],
    features_by_ticker: dict[str, dict],
    policy_id: str,
    regime: dict,
) -> None:
    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "account_profile": "ira",
        "policy": policy_id,
        "status": "proposed",
        "rebalance": "semiannual",
        "regime": regime.get("label"),
        "note": "Auto-synced from Darwin pipeline. Approve before trading.",
        "weights": [
            {
                "ticker": t,
                "weight_pct": round(w * 100, 2),
                "stance": (features_by_ticker.get(t, {}).get("classification") or {}).get("stance"),
            }
            for t, w in sorted(target_w.items(), key=lambda x: -x[1])
        ],
    }
    IRA_WEIGHTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_backtest_report(out: dict) -> None:
    b = out.get("benchmarks") or {}
    lines = [
        "# Darwin backtest report",
        "",
        f"Generated: {out.get('generated_at', '')}",
        f"Policy: **{out.get('policy_id')}** · Regime: **{out.get('regime', {}).get('label', out.get('regime'))}**",
        "",
        "## Champion vs baselines",
        "",
        "| Policy | Sharpe | Cumulative | Turnover |",
        "|--------|--------|------------|----------|",
    ]
    for k in ("ira_marvin", "equal_weight", "irr_ranked", "genetic", "ppo", "ensemble", "champion", "spy"):
        row = b.get(k) or {}
        if row.get("error"):
            continue
        lines.append(
            f"| {k} | {row.get('sharpe_annualized', '—')} | "
            f"{(row.get('cumulative_return') or 0) * 100:.1f}% | "
            f"{(row.get('avg_turnover_one_way') or 0) * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Human review",
            "",
        ]
    )
    for f in out.get("human_review") or []:
        lines.append(f"- **{f.get('ticker')}**: {f.get('reason')} ({f.get('severity')})")
    if not out.get("human_review"):
        lines.append("- None flagged")
    lines.append("")
    lines.append(out.get("disclaimer", ""))
    BACKTEST_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(write_features: bool = True, fast: bool = False) -> dict:
    mandate_doc = load_mandate()
    training = dict(mandate_doc.get("training") or {})
    if fast:
        training.update(
            {
                "encoder_epochs": 20,
                "ga_population": 12,
                "ga_generations": 4,
                "ppo_steps": 15,
                "ppo_seeds": 1,
                "price_history_months": 36,
            }
        )

    features = build_features()
    save_snapshot(features)
    if write_features:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        FEATURES_PATH.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")

    rows = features["tickers"]
    if not rows:
        return {"error": "no_holdings"}

    panel = build_return_panel(
        [
            {
                "ticker": r["ticker"],
                "market": r.get("market"),
                "irr_base_pct": r.get("irr_base_pct"),
            }
            for r in rows
        ],
        months=training.get("price_history_months", 60),
    )

    tickers = [r["ticker"] for r in rows]
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    features_by_ticker = {r["ticker"]: r for r in rows}

    research_regime = _research_regime_label(rows, mandate_doc)
    macro = latest_macro_state()
    regime = merge_regime(research_regime, macro, mandate_doc)
    mandate_effective = {**mandate_doc, "mandate": regime_constraint_overrides(regime, mandate_doc)}

    ira_scoring = mandate_doc.get("ira_scoring") or {}
    ira_genome = {
        **(mandate_doc.get("mandate") or {}),
        "ira_scoring": ira_scoring,
        "top_k": (mandate_doc.get("mandate") or {}).get("max_names", 12),
    }
    ira_raw = apply_policy("ira_marvin", rows, ira_genome)
    ira_w, _ = apply_constraints(tickers, ira_raw, None, mandate_effective, falsifier_map)

    def ira_fn(ts, _i):
        return apply_policy("ira_marvin", rows, ira_genome)

    bt_ira = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], ira_fn, mandate_effective, falsifier_map
    )

    eq_w, _ = apply_constraints(
        tickers, policy_equal_weight(rows), None, mandate_effective, falsifier_map
    )
    irr_w, _ = apply_constraints(
        tickers,
        policy_irr_ranked(rows, {"top_k": (mandate_doc.get("mandate") or {}).get("max_names", 12)}),
        None,
        mandate_effective,
        falsifier_map,
    )

    def eq_fn(ts, _i):
        return policy_equal_weight(rows)

    def irr_fn(ts, _i):
        return policy_irr_ranked(rows, {"top_k": 12})

    bt_eq = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], eq_fn, mandate_effective, falsifier_map
    )
    bt_irr = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], irr_fn, mandate_effective, falsifier_map
    )

    n_factors = training.get("latent_factors", 5)
    _, latent, enc_meta = train_encoder(
        rows,
        n_factors=n_factors,
        epochs=training.get("encoder_epochs", 80),
        lr=training.get("encoder_lr", 0.02),
    )

    best_genome, ga_hist, ga_survivors = run_ga(rows, panel, mandate_effective, latent, training)
    ppo_policy, ppo_metrics = train_ppo(rows, panel, latent, mandate_effective, training)

    genome_w, _ = apply_constraints(
        tickers,
        apply_policy(best_genome.get("policy", "irr_ranked"), rows, {**best_genome, "use_latent": True}, latent),
        None,
        mandate_effective,
        falsifier_map,
    )

    def ga_fn(ts, _i):
        return apply_policy(
            best_genome.get("policy", "irr_ranked"),
            rows,
            {**best_genome, "use_latent": True},
            latent,
        )

    bt_ga = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], ga_fn, mandate_effective, falsifier_map
    )

    prev_equal = {t: 1.0 / min(len(tickers), 15) for t in tickers[:15]}
    s_eq = sum(prev_equal.values()) or 1.0
    prev_equal = {t: prev_equal.get(t, 0.0) / s_eq for t in prev_equal}
    ppo_w = ppo_weights(ppo_policy, rows, latent, mandate_effective, prev_equal)

    def ppo_fn(ts, _i):
        return ppo_weights(ppo_policy, rows, latent, mandate_effective, prev_equal)

    bt_ppo = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], ppo_fn, mandate_effective, falsifier_map
    )

    kappa = (mandate_doc.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)
    n_trials = (mandate_doc.get("evolution") or {}).get("policy_trials", 8)

    def score_bt(bt: dict) -> float:
        if bt.get("error"):
            return -1e9
        raw = bt.get("sharpe_annualized", 0) - kappa * bt.get("avg_turnover_one_way", 0)
        return deflated_sharpe(raw, n_trials)

    policy_candidates = [
        ("ira_marvin", ira_w, bt_ira),
        ("ppo", ppo_w, bt_ppo),
        ("genetic", genome_w, bt_ga),
        ("irr_ranked", irr_w, bt_irr),
        ("equal_weight", eq_w, bt_eq),
    ]
    scored_candidates = [(n, w, score_bt(bt)) for n, w, bt in policy_candidates]

    evo_cfg = mandate_doc.get("evolution") or {}
    use_ensemble = evo_cfg.get("ensemble_champion", True)
    ensemble_k = evo_cfg.get("ensemble_top_k", 3)

    if use_ensemble:
        ens_w, ens_detail = blend_weights(
            [(n, w, s) for n, w, s in scored_candidates if s > -1e8],
            top_k=ensemble_k,
        )
        bt_ens = simulate(
            tickers,
            panel["dates"],
            panel["returns_by_ticker"],
            lambda _ts, _i: ens_w,
            mandate_effective,
            falsifier_map,
        )
        ensemble_policy_id = "ensemble"
    else:
        ens_w, ens_detail, bt_ens = {}, [], {"error": "disabled"}

    ml_best = max(policy_candidates, key=lambda x: score_bt(x[2]))
    ml_bt = ml_best[2]

    m = mandate_doc.get("mandate") or {}
    min_sharpe = m.get("ml_champion_min_sharpe", 0.3)
    min_periods = m.get("ml_champion_min_periods", 12)
    preferred = m.get("preferred_policy", "ira_marvin")

    ml_names = {"ppo", "genetic", "irr_ranked", "equal_weight"}
    use_ml = (
        ml_best[0] in ml_names
        and not ml_bt.get("error")
        and (ml_bt.get("periods") or 0) >= min_periods
        and (ml_bt.get("sharpe_annualized") or -999) >= min_sharpe
    )

    if use_ensemble and not bt_ens.get("error") and score_bt(bt_ens) >= score_bt(ml_bt) - 0.02:
        policy_id, target_w, champion_bt = ensemble_policy_id, ens_w, bt_ens
    elif use_ml:
        policy_id, target_w, champion_bt = ml_best
    else:
        policy_id, target_w, champion_bt = preferred, ira_w, bt_ira

    prev_w = load_previous_weights()
    if not prev_w:
        prev_w = irr_w if irr_w else prev_equal

    target_w, c_notes = apply_constraints(tickers, target_w, prev_w, mandate_effective, falsifier_map)
    max_turn = (mandate_doc.get("mandate") or {}).get("max_one_way_turnover_pct_per_rebalance", 10.0) / 100.0
    turnover_now = 0.5 * sum(
        abs(target_w.get(t, 0) - prev_w.get(t, 0)) for t in set(target_w) | set(prev_w)
    )
    if prev_w and turnover_now > max_turn:
        alpha = max_turn / turnover_now
        blended = {t: prev_w.get(t, 0) * (1 - alpha) + target_w.get(t, 0) * alpha for t in set(target_w) | set(prev_w)}
        s = sum(blended.values()) or 1.0
        target_w = {t: blended[t] / s for t in blended}
        target_w, _ = apply_constraints(tickers, target_w, prev_w, mandate_effective, falsifier_map)
        c_notes["turnover_capped_output"] = True
        c_notes["turnover_one_way"] = round(max_turn, 4)
    if mandate_doc.get("account_profile") == "ira":
        target_w = apply_ira_stance_caps(target_w, features_by_ticker, mandate_doc)
        max_w = m.get("max_weight_pct", 15.0) / 100.0
        for t in list(target_w):
            target_w[t] = min(target_w[t], max_w)
        s = sum(target_w.values()) or 1.0
        target_w = {t: target_w[t] / s for t in target_w}
    turnover_used = (
        c_notes.get("turnover_one_way")
        if c_notes.get("turnover_capped_output")
        else 0.5
        * sum(abs(target_w.get(t, 0) - prev_w.get(t, 0)) for t in set(target_w) | set(prev_w))
    )
    if prev_w:
        turnover_used = round(float(turnover_used), 4)

    attribution = factor_attribution(
        rows,
        latent,
        target_w,
        enc_meta.get("factor_labels") or [f"factor_{i+1}" for i in range(n_factors)],
    )

    review_flags = human_review_flags(rows, target_w, prev_w, mandate_doc)
    conflicts = [f for f in review_flags if f.get("severity") == "review"]

    spy_rets = _spy_panel(panel["dates"])
    bt_spy = benchmark_buy_hold(
        panel["dates"],
        spy_rets,
        (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual"),
    )

    pop = load_population()
    lineage = append_lineage(
        {
            "event": "rebalance",
            "policy": policy_id,
            "regime": regime.get("label"),
            "turnover_pct": round(turnover_used * 100, 2),
            "champion_sharpe": champion_bt.get("sharpe_annualized"),
            "population_size": len(pop),
        }
    )

    sync_ira_target_weights(target_w, features_by_ticker, policy_id, regime)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": "0-4",
        "mandate": mandate_doc.get("mandate"),
        "regime": regime,
        "rebalance_frequency": mandate_doc.get("mandate", {}).get("rebalance_frequency", "semiannual"),
        "turnover_budget_pct": mandate_doc.get("mandate", {}).get(
            "max_one_way_turnover_pct_per_rebalance", 15
        ),
        "turnover_used_pct": round(turnover_used * 100, 2),
        "policy_id": policy_id,
        "policy_detail": {
            "champion": policy_id,
            "genome": best_genome if policy_id == "genetic" else None,
            "ga_generations": ga_hist,
            "ga_survivors": ga_survivors[:5],
            "ppo_metrics": ppo_metrics,
            "ensemble": ens_detail if use_ensemble else None,
            "population_loaded": len(pop),
        },
        "weights": weights_to_list(target_w, features_by_ticker, prev_w),
        "account_profile": mandate_doc.get("account_profile", "taxable"),
        "benchmarks": {
            "ira_marvin": bt_ira,
            "equal_weight": bt_eq,
            "irr_ranked": bt_irr,
            "genetic": bt_ga,
            "ppo": bt_ppo,
            "ensemble": bt_ens,
            "champion": champion_bt,
            "spy": bt_spy,
            "ml_best": ml_best[2],
            "ml_selected": use_ml,
        },
        "attribution": attribution,
        "latent_factors": {
            "labels": enc_meta.get("factor_labels"),
            "by_ticker": latent,
        },
        "price_panel": {
            "months": len(panel.get("dates") or []),
            "sources": panel.get("sources"),
        },
        "conflicts": conflicts,
        "human_review": review_flags,
        "evolution_log": [
            {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "event": "rebalance",
                "policy": policy_id,
                "turnover_pct": round(turnover_used * 100, 2),
                "note": (
                    f"Champion {policy_id} Sharpe {champion_bt.get('sharpe_annualized')} "
                    f"regime {regime.get('label')}"
                ),
            }
        ],
        "lineage": lineage[-5:],
        "source_alignment_version": (mandate_doc.get("source_overrides") or {}).get("version"),
        "disclaimer": mandate_doc.get("disclaimer"),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    write_backtest_report(out)
    return out
