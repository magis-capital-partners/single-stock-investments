"""Run Darwin phases 0–4: features, evolution, ensemble, regime, gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .attribution import factor_attribution
from .backtest import benchmark_buy_hold, benchmark_covered_call, simulate
from .accounts import AccountCtx, account_ctx, build_serving, load_mandate_for, tier0_production
from .config import DATA_DIR, FEATURES_PATH, load_mandate
from .paper_portfolio import update_paper_portfolio
from .constraints import apply_constraints, apply_ira_stance_caps, weights_to_list
from .encoder import train_encoder
from .ensemble import blend_weights, deflated_sharpe
from .features import build_features
from .gates import human_review_flags
from .genetic import run_ga
from .persistence import append_lineage, load_population
from .pit_audit import run_pit_audit
from .pit_backtest import run_pit_backtest
from .pit_snapshot import append_pit_status, save_registry_snapshot, save_snapshot
from .research_events import rebuild_events_log
from .bias_scan import run_bias_scan
from .import_external_data import sync_external_market_data
from .observatory import build_observatory, save_observatory, write_regime_brief
from .policies import apply_policy, ira_marvin_ineligible, policy_equal_weight, policy_irr_ranked, policy_risk_parity_vol
from .questions import scaffold_all_questions
from .scorecard import append_scorecard
from .simulation import run_stress_simulation
from .ppo import ppo_weights, train_ppo
from .prices import build_return_panel, load_returns_csv
from .explanation import build_portfolio_explanation
from .regime import latest_macro_state, merge_regime, regime_constraint_overrides
from .visualization import build_method_visualizations
from .covered_call import resolve_cc_cfg
from .options_cache import cache_coverage_report, iv_by_ticker
from .proxy_returns import ensure_proxy_returns
from .cc_lab import run_cc_knob_lab
from .universe import load_liquidity_map

def _research_regime_label(rows: list[dict], mandate: dict) -> str:
    thresh = (mandate.get("regime") or {}).get("falsifier_stress_threshold", 3)
    total_f = sum(r.get("falsifier_count", 0) for r in rows)
    if total_f >= thresh:
        return "stressed"
    stale = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > 120)
    if stale >= len(rows) // 2:
        return "adapting"
    return "calm"


def load_previous_weights(ctx: AccountCtx) -> dict[str, float]:
    if not ctx.target_weights_path.exists():
        return {}
    try:
        data = json.loads(ctx.target_weights_path.read_text(encoding="utf-8"))
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


def sync_target_weights(
    ctx: AccountCtx,
    mandate_doc: dict,
    target_w: dict[str, float],
    features_by_ticker: dict[str, dict],
    policy_id: str,
    regime: dict,
) -> None:
    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "account_id": ctx.account_id,
        "account_profile": mandate_doc.get("account_profile"),
        "policy": policy_id,
        "status": "proposed",
        "rebalance": (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual"),
        "regime": regime.get("label"),
        "tier": mandate_doc.get("tier", 0),
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
    ctx.target_weights_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.target_weights_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_backtest_report(out: dict, ctx: AccountCtx) -> None:
    b = out.get("benchmarks") or {}
    lines = [
        f"# Darwin backtest report — {ctx.account_id}",
        "",
        f"Generated: {out.get('generated_at', '')}",
        f"Policy: **{out.get('policy_id')}** · Regime: **{out.get('regime', {}).get('label', out.get('regime'))}**",
        "",
        "## Champion vs baselines",
        "",
        "| Policy | Sharpe | Cumulative | Turnover |",
        "|--------|--------|------------|----------|",
    ]
    for k in (
        "ira_marvin",
        "equal_weight",
        "irr_ranked",
        "genetic",
        "ppo",
        "risk_parity_vol",
        "ensemble",
        "champion",
        "spy",
        "covered_call",
        "xyld",
    ):
        row = b.get(k) or {}
        if row.get("error"):
            continue
        lines.append(
            f"| {k} | {row.get('sharpe_annualized', '—')} | "
            f"{(row.get('cumulative_return') or 0) * 100:.1f}% | "
            f"{(row.get('avg_turnover_one_way') or 0) * 100:.1f}% |"
        )
    pit = out.get("pit") or {}
    if pit:
        lines.extend(
            [
                "",
                "## PIT discipline",
                "",
                f"- Audit pass: **{pit.get('audit_pass')}** (leakage {pit.get('leakage_count', 0)})",
                f"- OOS genetic Sharpe: **{pit.get('oos_sharpe_genetic', '—')}** ({pit.get('oos_periods', 0)} periods)",
                f"- ML OOS eligible: **{pit.get('ml_oos_eligible')}**",
                "",
            ]
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
    ctx.backtest_report_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.backtest_report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(
    account_id: str = "roth",
    write_features: bool = True,
    fast: bool = False,
    pit_audit_only: bool = False,
    pit_backtest_only: bool = False,
    sync_events: bool = False,
    sync_external_only: bool = False,
    run_pit: bool = True,
    shared_features: dict | None = None,
) -> dict:
    ctx = account_ctx(account_id)
    mandate_doc = load_mandate_for(account_id)
    tier0 = tier0_production(mandate_doc)
    if sync_events:
        n = rebuild_events_log()
        return {"sync_events": n}

    if sync_external_only:
        return {"external_sync": sync_external_market_data()}

    if pit_audit_only:
        audit = run_pit_audit(fast=fast)
        status = {
            "generated_at": audit.get("generated_at"),
            "audit_pass": audit.get("pass"),
            "leakage_count": audit.get("leakage_count", 0),
            "synthetic_tickers": audit.get("synthetic_tickers", []),
            "mode": "audit_only",
        }
        append_pit_status(status)
        return {"pit_audit": audit, "pit_status": status}

    if pit_backtest_only:
        pit_bt = run_pit_backtest(fast=fast)
        audit = run_pit_audit(fast=fast)
        status = _pit_status_from_runs(audit, pit_bt)
        append_pit_status(status)
        return {"pit_backtest": pit_bt, "pit_audit": audit, "pit_status": status}

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

    if shared_features is not None:
        features = shared_features
    else:
        features = build_features(mandate_doc)
        save_snapshot(features)
        save_registry_snapshot()
    from .features import holdings_universe
    from .pit import bootstrap_valuation_history

    external_sync: dict = {}
    if shared_features is None:
        try:
            external_sync = sync_external_market_data()
        except Exception as exc:
            external_sync = {"error": str(exc)}
        rebuild_events_log()
    bootstrap_valuation_history(holdings_universe(mandate_doc))
    if write_features:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        FEATURES_PATH.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")

    rows = features["tickers"]
    if not rows:
        return {
            "error": "no_holdings",
            "universe_spec": features.get("universe_spec"),
            "universe_count": 0,
        }

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
        allow_synthetic=not (mandate_doc.get("pit") or {}).get("allow_synthetic_returns") is False,
    )

    tickers = [r["ticker"] for r in rows]
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    features_by_ticker = {r["ticker"]: r for r in rows}

    research_regime = _research_regime_label(rows, mandate_doc)
    macro = latest_macro_state()
    regime = merge_regime(research_regime, macro, mandate_doc)
    mandate_effective = {**mandate_doc, "mandate": regime_constraint_overrides(regime, mandate_doc)}

    ira_scoring = mandate_doc.get("ira_scoring") or {}
    cc_sel = mandate_doc.get("covered_call") or {}
    prefer_cc_policy = bool(cc_sel.get("dual_score_selection")) and (
        (mandate_doc.get("mandate") or {}).get("preferred_policy") in ("ira_marvin_cc", "ira_marvin")
    )
    liq_map_raw = load_liquidity_map()
    liquidity_by_ticker = {
        t: str((liq_map_raw.get(t) or {}).get("liquidity_bucket") or "B")
        for t in tickers
    }
    iv_map = iv_by_ticker(tickers)
    ira_genome = {
        **(mandate_doc.get("mandate") or {}),
        "ira_scoring": ira_scoring,
        "top_k": (mandate_doc.get("mandate") or {}).get("max_names", 12),
        "max_names_cc": (mandate_doc.get("mandate") or {}).get("max_names_cc"),
        "min_names_cc": (mandate_doc.get("mandate") or {}).get("min_names_cc"),
        "cc_dual_score": prefer_cc_policy or (mandate_doc.get("mandate") or {}).get("preferred_policy") == "ira_marvin_cc",
        "iv_by_ticker": iv_map,
        "liquidity_by_ticker": liquidity_by_ticker,
    }
    irr_stance_miss = ira_marvin_ineligible(rows, ira_genome)
    univ_excl = dict(features.get("universe_exclusions") or {})
    if univ_excl:
        by_reason = dict(univ_excl.get("by_reason") or {})
        by_reason["irr_stance_miss"] = len(irr_stance_miss)
        samples = dict(univ_excl.get("samples") or {})
        samples["irr_stance_miss"] = irr_stance_miss[:12]
        univ_excl["by_reason"] = by_reason
        univ_excl["samples"] = samples
        univ_excl["excluded_total"] = sum(int(v or 0) for v in by_reason.values())
    features = {**features, "universe_exclusions": univ_excl}

    ira_policy_name = "ira_marvin_cc" if ira_genome.get("cc_dual_score") else "ira_marvin"
    ira_raw = apply_policy(ira_policy_name, rows, ira_genome)
    ira_w, _ = apply_constraints(tickers, ira_raw, None, mandate_effective, falsifier_map)

    # Scenario: long-only 12-name vs CC-concentrated book (Phase C)
    scenario_genome = {**ira_genome, "cc_dual_score": True, "max_names_cc": (mandate_doc.get("mandate") or {}).get("max_names_cc") or 8}
    scenario_raw = apply_policy("ira_marvin_cc", rows, scenario_genome)
    scenario_w, _ = apply_constraints(tickers, scenario_raw, None, mandate_effective, falsifier_map)

    def ira_fn(ts, _i):
        return apply_policy(ira_policy_name, rows, ira_genome)

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

    rp_raw = apply_policy("risk_parity_vol", rows, {"top_k": 12, "irr_power": 0.8})
    rp_w, _ = apply_constraints(tickers, rp_raw, None, mandate_effective, falsifier_map)

    def rp_fn(ts, _i):
        return apply_policy("risk_parity_vol", rows, {"irr_power": 0.8})

    bt_rp = simulate(
        tickers, panel["dates"], panel["returns_by_ticker"], rp_fn, mandate_effective, falsifier_map
    )

    evo_cfg = mandate_doc.get("evolution") or {}
    use_ml_stack = not tier0 and (
        evo_cfg.get("enable_encoder", True)
        or evo_cfg.get("enable_ga", True)
        or evo_cfg.get("enable_ppo", True)
    )
    n_factors = training.get("latent_factors", 5)
    latent: dict = {}
    enc_meta: dict = {"factor_labels": []}
    best_genome: dict = {}
    ga_hist: list = []
    ga_survivors: list = []
    ppo_metrics: dict = {}
    bt_ga: dict = {"error": "tier0_disabled"}
    bt_ppo: dict = {"error": "tier0_disabled"}
    genome_w: dict = {}
    ppo_w: dict = {}

    def ga_policy_fn(_ts, _i):
        return dict(genome_w) if genome_w else dict(irr_w)

    def ppo_policy_fn(_ts, _i):
        return dict(ppo_w) if ppo_w else dict(irr_w)

    if use_ml_stack:
        _, latent, enc_meta = train_encoder(
            rows,
            n_factors=n_factors,
            epochs=training.get("encoder_epochs", 80),
            lr=training.get("encoder_lr", 0.02),
        )
        if evo_cfg.get("enable_ga", True):
            best_genome, ga_hist, ga_survivors = run_ga(rows, panel, mandate_effective, latent, training)
            genome_w, _ = apply_constraints(
                tickers,
                apply_policy(
                    best_genome.get("policy", "irr_ranked"),
                    rows,
                    {**best_genome, "use_latent": True},
                    latent,
                ),
                None,
                mandate_effective,
                falsifier_map,
            )

            def ga_policy_fn(ts, _i):
                return apply_policy(
                    best_genome.get("policy", "irr_ranked"),
                    rows,
                    {**best_genome, "use_latent": True},
                    latent,
                )

            bt_ga = simulate(
                tickers,
                panel["dates"],
                panel["returns_by_ticker"],
                ga_policy_fn,
                mandate_effective,
                falsifier_map,
            )
        if evo_cfg.get("enable_ppo", True):
            ppo_policy, ppo_metrics = train_ppo(rows, panel, latent, mandate_effective, training)
            prev_equal = {t: 1.0 / min(len(tickers), 15) for t in tickers[:15]}
            s_eq = sum(prev_equal.values()) or 1.0
            prev_equal = {t: prev_equal.get(t, 0.0) / s_eq for t in prev_equal}
            ppo_w = ppo_weights(ppo_policy, rows, latent, mandate_effective, prev_equal)

            def ppo_policy_fn(ts, _i):
                return ppo_weights(ppo_policy, rows, latent, mandate_effective, prev_equal)

            bt_ppo = simulate(
                tickers,
                panel["dates"],
                panel["returns_by_ticker"],
                ppo_policy_fn,
                mandate_effective,
                falsifier_map,
            )

    prev_equal = {t: 1.0 / min(len(tickers), 15) for t in tickers[:15]}
    s_eq = sum(prev_equal.values()) or 1.0
    prev_equal = {t: prev_equal.get(t, 0.0) / s_eq for t in prev_equal}

    kappa = (mandate_doc.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)
    n_trials = (mandate_doc.get("evolution") or {}).get("policy_trials", 8)

    def score_bt(bt: dict) -> float:
        if bt.get("error"):
            return -1e9
        raw = bt.get("sharpe_annualized", 0) - kappa * bt.get("avg_turnover_one_way", 0)
        return deflated_sharpe(raw, n_trials)

    policy_candidates = [
        ("ira_marvin", ira_w, bt_ira),
        ("irr_ranked", irr_w, bt_irr),
        ("equal_weight", eq_w, bt_eq),
    ]
    if not tier0:
        policy_candidates.extend(
            [
                ("ppo", ppo_w, bt_ppo),
                ("genetic", genome_w, bt_ga),
                ("risk_parity_vol", rp_w, bt_rp),
            ]
        )
    bt_by_policy = {n: bt for n, _, bt in policy_candidates}
    scored_candidates = [(n, w, score_bt(bt)) for n, w, bt in policy_candidates]

    evo_cfg = mandate_doc.get("evolution") or {}
    use_ensemble = evo_cfg.get("ensemble_champion", True) and not tier0
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

    explore = mandate_doc.get("exploration") or {}
    exploration_on = bool(explore.get("enabled", False)) and not tier0

    ml_names = {"ppo", "genetic", "irr_ranked", "equal_weight", "risk_parity_vol"}
    use_ml = (
        not tier0
        and ml_best[0] in ml_names
        and not ml_bt.get("error")
        and (ml_bt.get("periods") or 0) >= min_periods
        and (ml_bt.get("sharpe_annualized") or -999) >= min_sharpe
    )
    pit_bt: dict = {}
    pit_audit: dict = {}
    if run_pit:
        try:
            pit_audit = run_pit_audit(fast=fast)
            pit_bt = run_pit_backtest(fast=fast)
            if mandate_doc.get("pit", {}).get("require_oos_for_ml", True) and not explore.get("allow_ml_without_oos"):
                use_ml = use_ml and pit_bt.get("ml_oos_eligible", False)
        except Exception as exc:
            pit_audit = {"error": str(exc)}
            pit_bt = {"error": str(exc)}

    if exploration_on and explore.get("champion_mode") == "best_insample":
        all_scored = list(scored_candidates)
        if use_ensemble and not bt_ens.get("error"):
            bt_by_policy[ensemble_policy_id] = bt_ens
            all_scored.append((ensemble_policy_id, ens_w, score_bt(bt_ens)))
        best = max(all_scored, key=lambda x: x[2])
        policy_id = best[0]
        target_w = best[1]
        champion_bt = bt_by_policy.get(policy_id, bt_ira)
    elif use_ensemble and not bt_ens.get("error") and score_bt(bt_ens) >= score_bt(ml_bt) - 0.02:
        policy_id, target_w, champion_bt = ensemble_policy_id, ens_w, bt_ens
    elif use_ml:
        policy_id, target_w, champion_bt = ml_best
    else:
        pid = (
            ira_policy_name
            if preferred in ("ira_marvin", "ira_marvin_cc")
            else preferred
        )
        policy_id, target_w, champion_bt = pid, ira_w, bt_ira

    prev_w = load_previous_weights(ctx)
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
    target_w = apply_ira_stance_caps(target_w, features_by_ticker, mandate_doc)
    max_w = m.get("max_weight_pct", 15.0) / 100.0
    if max_w:
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
    rebalance_freq = (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual")
    bt_spy = benchmark_buy_hold(panel["dates"], spy_rets, rebalance_freq)

    cc_cfg = resolve_cc_cfg(mandate_doc, regime)
    bt_cc: dict = {"error": "disabled", "periods": 0}
    bt_cc_proxy: dict = {"error": "disabled", "periods": 0}
    bt_qyld: dict = {"error": "disabled", "periods": 0}
    proxy_status = ensure_proxy_returns(list(cc_cfg.get("proxy_tickers") or ["XYLD", "QYLD"]))
    features_by_ticker = {r["ticker"]: r for r in rows}
    if cc_cfg.get("enabled", False):
        bt_cc = benchmark_covered_call(
            panel["dates"],
            panel["returns_by_ticker"],
            dict(target_w),
            cc_cfg,
            rebalance_freq,
            track_series=True,
            features_by_ticker=features_by_ticker,
            iv_by_ticker=iv_map,
            liquidity_by_ticker=liquidity_by_ticker,
            regime=regime,
        )
        for proxy_ticker, bt_slot in (
            ((cc_cfg.get("etf_proxy_ticker") or "XYLD").strip().upper(), "xyld"),
            ("QYLD", "qyld"),
        ):
            loaded_proxy = load_returns_csv(proxy_ticker)
            if loaded_proxy:
                d2r = dict(zip(loaded_proxy[0], loaded_proxy[1]))
                proxy_rets = [d2r.get(d, 0.0) for d in panel["dates"]]
                bt = benchmark_buy_hold(
                    panel["dates"],
                    proxy_rets,
                    rebalance_freq,
                    track_series=True,
                    label=f"{proxy_ticker.lower()}_buy_hold",
                )
                if bt_slot == "xyld" or proxy_ticker == (cc_cfg.get("etf_proxy_ticker") or "XYLD").upper():
                    bt_cc_proxy = bt
                if proxy_ticker == "QYLD":
                    bt_qyld = bt
            elif bt_slot == "xyld":
                bt_cc_proxy = {"error": "missing_returns", "periods": 0, "label": proxy_ticker}

    # Phase C: PIT OOS gate before promoting CC dual-score to production champion
    cc_oos_gate = {
        "enabled": bool(cc_cfg.get("require_oos_for_dual_score", True)),
        "passed": False,
        "reason": "not_evaluated",
        "promote_dual_score": False,
    }
    oos_cc = (pit_bt.get("benchmarks") or {}).get("oos", {}).get("ira_marvin") or {}
    oos_sharpe = oos_cc.get("sharpe_annualized")
    spy_sharpe = (bt_spy or {}).get("sharpe_annualized")
    min_oos = float(cc_cfg.get("oos_min_sharpe", 0.0))
    if not cc_cfg.get("dual_score_selection"):
        cc_oos_gate["reason"] = "dual_score_selection_disabled"
    elif oos_sharpe is None:
        cc_oos_gate["reason"] = "missing_oos_ira_marvin"
    elif spy_sharpe is not None and oos_sharpe < spy_sharpe and cc_cfg.get("oos_require_beat_spy", True):
        cc_oos_gate["reason"] = f"oos_sharpe_{oos_sharpe}_below_spy_{spy_sharpe}"
    elif oos_sharpe < min_oos:
        cc_oos_gate["reason"] = f"oos_sharpe_{oos_sharpe}_below_min_{min_oos}"
    else:
        cc_oos_gate["passed"] = True
        cc_oos_gate["promote_dual_score"] = True
        cc_oos_gate["reason"] = "oos_ok"

    # If dual score requested but OOS gate fails, keep long-only ira_marvin weights for paper
    if ira_genome.get("cc_dual_score") and cc_cfg.get("require_oos_for_dual_score", True) and not cc_oos_gate["passed"]:
        if preferred in ("ira_marvin", "ira_marvin_cc") and policy_id in ("ira_marvin", "ira_marvin_cc"):
            # Rebuild without CC multiplier for production paper book
            plain_genome = {**ira_genome, "cc_dual_score": False, "max_names_cc": None}
            plain_raw = apply_policy("ira_marvin", rows, plain_genome)
            plain_w, _ = apply_constraints(tickers, plain_raw, prev_w, mandate_effective, falsifier_map)
            target_w = apply_ira_stance_caps(plain_w, features_by_ticker, mandate_doc)
            policy_id = "ira_marvin"
            cc_oos_gate["production_policy"] = "ira_marvin_gated"
            # refresh CC bench on gated weights
            if cc_cfg.get("enabled", False):
                bt_cc = benchmark_covered_call(
                    panel["dates"],
                    panel["returns_by_ticker"],
                    dict(target_w),
                    cc_cfg,
                    rebalance_freq,
                    track_series=True,
                    features_by_ticker=features_by_ticker,
                    iv_by_ticker=iv_map,
                    liquidity_by_ticker=liquidity_by_ticker,
                    regime=regime,
                )

    cc_lab = run_cc_knob_lab(
        panel["dates"],
        panel["returns_by_ticker"],
        dict(target_w),
        mandate_doc,
        features_by_ticker=features_by_ticker,
        iv_by_ticker=iv_map,
        liquidity_by_ticker=liquidity_by_ticker,
        regime=regime,
        n_trials=int((mandate_doc.get("evolution") or {}).get("cc_ga_trials", 12)),
    )

    scenarios = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "long_only_max_names": (mandate_doc.get("mandate") or {}).get("max_names", 12),
        "cc_concentrated_max_names": (mandate_doc.get("mandate") or {}).get("max_names_cc") or 8,
        "production_policy": policy_id,
        "cc_oos_gate": cc_oos_gate,
        "scenario_cc_weights": [
            {"ticker": t, "weight_pct": round(w * 100, 2)}
            for t, w in sorted(scenario_w.items(), key=lambda x: -x[1])
        ],
        "scenario_vs_production": {
            "scenario_names": len(scenario_w),
            "production_names": len(target_w),
            "overlap": sorted(set(scenario_w) & set(target_w)),
        },
        "human_approve_note": "Approve scenario_cc_weights before changing live paper book.",
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "darwin_cc_scenarios.json").write_text(json.dumps(scenarios, indent=2) + "\n", encoding="utf-8")

    options_report = cache_coverage_report(list(target_w.keys()) or tickers[:12])

    champion_selection = "ira_default"
    if exploration_on and explore.get("champion_mode") == "best_insample":
        champion_selection = "exploration"
    elif use_ensemble and policy_id == "ensemble":
        champion_selection = "ensemble"
    elif use_ml:
        champion_selection = "ml_oos" if pit_bt.get("ml_oos_eligible") else "ml_insample_pending_oos"
    elif policy_id == preferred:
        champion_selection = "ira_default"
    else:
        champion_selection = "champion_other"

    policy_fns: dict = {
        "ira_marvin": ira_fn,
        "equal_weight": eq_fn,
        "irr_ranked": irr_fn,
        "risk_parity_vol": rp_fn,
    }
    if not tier0:
        policy_fns["genetic"] = ga_policy_fn
        policy_fns["ppo"] = ppo_policy_fn
    if use_ensemble and ens_w:
        policy_fns["ensemble"] = lambda _ts, _i: ens_w
    policy_fns["champion"] = lambda _ts, _i: dict(target_w)

    viz = build_method_visualizations(
        tickers=tickers,
        dates=panel["dates"],
        returns_by_ticker=panel["returns_by_ticker"],
        spy_returns=spy_rets,
        mandate_effective=mandate_effective,
        falsifier_map=falsifier_map,
        policy_fns=policy_fns,
        rebalance_frequency=rebalance_freq,
        covered_call_bt=bt_cc if not bt_cc.get("error") else None,
        covered_call_proxy_bt=bt_cc_proxy if not bt_cc_proxy.get("error") else None,
        covered_call_proxy_key=(cc_cfg.get("etf_proxy_ticker") or "xyld").strip().lower() or "xyld",
    )

    portfolio_explanation = build_portfolio_explanation(
        policy_id=policy_id,
        target_w=target_w,
        rows=rows,
        regime=regime,
        mandate=m,
        constraints_notes=c_notes,
        ensemble_detail=ens_detail if use_ensemble else None,
        champion_selection=champion_selection,
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

    sync_target_weights(ctx, mandate_doc, target_w, features_by_ticker, policy_id, regime)

    # Strip series from benchmark stats blobs (charts use visualization.methods)
    def _bench_stats(bt: dict) -> dict:
        if not bt:
            return {"error": "missing", "periods": 0}
        if bt.get("error"):
            return {k: bt[k] for k in bt if k != "series"}
        out_b = {k: v for k, v in bt.items() if k != "series"}
        return out_b

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "account_id": ctx.account_id,
        "tier": mandate_doc.get("tier", 0),
        "phase": "0-tier0" if tier0 else "0-4",
        "mandate": mandate_doc.get("mandate"),
        "universe_spec": features.get("universe_spec")
        or (mandate_doc.get("mandate") or {}).get("universe"),
        "universe_spec_effective": features.get("universe_spec_effective")
        or features.get("universe_spec"),
        "universe_count": features.get("universe_count", len(rows)),
        "universe_excluded_sample": features.get("universe_excluded_sample") or [],
        "universe_exclusions": features.get("universe_exclusions") or {},
        "sp500": features.get("sp500"),
        "liquidity": features.get("liquidity"),
        "covered_call": {
            **cc_cfg,
            "disclaimer": (
                "Synthetic covered-call overlay on champion weights, "
                "not Darwin AI Ventures proprietary model"
            ),
            "stress_cases": (bt_cc.get("stress_cases") if isinstance(bt_cc, dict) else None),
            "name_level_sample": (bt_cc.get("name_level_sample") if isinstance(bt_cc, dict) else None),
            "proxy_returns_status": proxy_status,
            "options_cache": options_report,
            "oos_gate": cc_oos_gate,
        },
        "cc_scenarios": scenarios,
        "cc_lab": {k: v for k, v in (cc_lab or {}).items() if k != "trials"} if cc_lab else {"enabled": False},
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
        "account_profile": mandate_doc.get("account_profile", "roth"),
        "benchmarks": {
            "ira_marvin": bt_ira,
            "equal_weight": bt_eq,
            "irr_ranked": bt_irr,
            "genetic": bt_ga,
            "ppo": bt_ppo,
            "risk_parity_vol": bt_rp,
            "ensemble": bt_ens,
            "champion": champion_bt,
            "spy": bt_spy,
            "covered_call": _bench_stats(bt_cc),
            "ml_best": ml_best[2],
            "ml_selected": use_ml and not exploration_on,
        },
    }
    proxy_key = (cc_cfg.get("etf_proxy_ticker") or "").strip().lower()
    if proxy_key and not bt_cc_proxy.get("error"):
        out["benchmarks"][proxy_key] = _bench_stats(bt_cc_proxy)
    if not bt_qyld.get("error"):
        out["benchmarks"]["qyld"] = _bench_stats(bt_qyld)

    # Phase C: flag high CC suitability + watch stance for human review
    for t in list(ira_genome.get("_cc_high_suitability_watch") or []):
        review_flags.append(
            {
                "ticker": t,
                "severity": "warn",
                "reason": "high_cc_suitability_with_watch_stance",
            }
        )
    conflicts = [f for f in review_flags if f.get("severity") == "review"]
    out["conflicts"] = conflicts
    out["human_review"] = review_flags

    out.update(
        {
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
            "visualization": viz,
            "portfolio_explanation": portfolio_explanation,
            "pit": {
                "audit_pass": pit_audit.get("pass"),
                "leakage_count": pit_audit.get("leakage_count"),
                "oos_sharpe_genetic": pit_bt.get("oos_sharpe_genetic"),
                "oos_periods": pit_bt.get("oos_periods"),
                "ml_oos_eligible": pit_bt.get("ml_oos_eligible"),
                "synthetic_count": (pit_bt.get("price_panel") or {}).get("synthetic_count"),
            },
        }
    )

    if run_pit:
        pit_status = _pit_status_from_runs(pit_audit, pit_bt, production=out)
        append_pit_status(pit_status)
        out["pit_status"] = pit_status
        append_scorecard(pit_status, pit_audit, pit_bt, bias := run_bias_scan(rows, target_w), policy_id, exploration_on, ctx.account_id)
    else:
        out["pit_status"] = {}
        bias = run_bias_scan(rows, target_w)
        append_scorecard({}, {}, {}, bias, policy_id, exploration_on, ctx.account_id)

    out["bias_scan"] = bias

    if run_pit and account_id == "roth":
        observatory = build_observatory(rows, regime)
        save_observatory(observatory)
        brief_path = write_regime_brief(observatory, rows)
        out["observatory"] = observatory
        out["regime_brief"] = str(brief_path.relative_to(Path(__file__).resolve().parents[3]))

    if not tier0:
        out["open_questions"] = scaffold_all_questions(tickers)

        def _w_fn(active, qi):
            return target_w

        out["stress_simulation"] = run_stress_simulation(
            panel, _w_fn, mandate_effective, n_paths=120 if fast else 250
        )
        write_backtest_report(out, ctx)

    out["exploration"] = {"enabled": exploration_on, "champion_mode": explore.get("champion_mode")}
    out["external_sync"] = external_sync if account_id == "roth" else {}

    paper = update_paper_portfolio(ctx, mandate_doc, target_w, policy_id, regime, out)
    out["paper_portfolio"] = paper

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ctx.portfolio_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    return out


def run_all_accounts(fast: bool = False, write_features: bool = True) -> dict:
    """Build Roth IRA Tier 0 book, paper tracker, and L4 serving bundle (IRA-only)."""
    from .accounts import ACCOUNT_IDS
    from .features import build_features as _build

    features = _build(load_mandate_for("roth"))
    results: dict = {}
    for i, aid in enumerate(ACCOUNT_IDS):
        results[aid] = run_pipeline(
            account_id=aid,
            fast=fast,
            write_features=write_features and i == 0,
            shared_features=features,
            run_pit=(aid == "roth"),
        )
    serving = build_serving(results)
    return {"serving": serving, "portfolios": results}


def _pit_status_from_runs(audit: dict, pit_bt: dict, production: dict | None = None) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audit_pass": audit.get("pass"),
        "leakage_count": audit.get("leakage_count", 0),
        "synthetic_tickers": audit.get("synthetic_tickers", []),
        "oos_sharpe_genetic": pit_bt.get("oos_sharpe_genetic"),
        "oos_sharpe_ira_marvin": (pit_bt.get("benchmarks") or {}).get("oos", {}).get("ira_marvin", {}).get(
            "sharpe_annualized"
        ),
        "oos_periods": pit_bt.get("oos_periods"),
        "ml_oos_eligible": pit_bt.get("ml_oos_eligible"),
        "production_policy": (production or {}).get("policy_id"),
        "production_sharpe_insample": (production or {}).get("benchmarks", {}).get("genetic", {}).get(
            "sharpe_annualized"
        ),
        "pit_error": pit_bt.get("error") or audit.get("error"),
    }
