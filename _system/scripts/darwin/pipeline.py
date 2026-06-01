"""Run Darwin phases 0–3 and emit dashboard JSON."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .attribution import factor_attribution
from .backtest import simulate
from .config import DATA_DIR, FEATURES_PATH, PORTFOLIO_PATH, load_mandate
from .constraints import apply_constraints, weights_to_list
from .encoder import train_encoder
from .features import build_features
from .genetic import run_ga
from .policies import apply_policy, policy_equal_weight, policy_irr_ranked
from .ppo import ppo_weights, train_ppo
from .prices import build_return_panel


def _regime_label(rows: list[dict], mandate: dict) -> str:
    thresh = (mandate.get("regime") or {}).get("falsifier_stress_threshold", 3)
    total_f = sum(r.get("falsifier_count", 0) for r in rows)
    if total_f >= thresh:
        return "stressed"
    stale = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > 120)
    if stale >= len(rows) // 2:
        return "adapting"
    return "calm"


def run_pipeline(write_features: bool = True, fast: bool = False) -> dict:
    mandate_doc = load_mandate()
    training = mandate_doc.get("training") or {}
    if fast:
        training = {
            **training,
            "encoder_epochs": 20,
            "ga_population": 12,
            "ga_generations": 4,
            "ppo_steps": 15,
            "ppo_seeds": 1,
            "price_history_months": 24,
        }

    features = build_features()
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
        months=training.get("price_history_months", 36),
    )

    tickers = [r["ticker"] for r in rows]
    falsifier_map = {r["ticker"]: r.get("falsifier_count", 0) for r in rows}
    features_by_ticker = {r["ticker"]: r for r in rows}

    # Phase 1 baselines
    eq = policy_equal_weight(rows)
    eq_w, eq_notes = apply_constraints(tickers, eq, None, mandate_doc, falsifier_map)
    irr = policy_irr_ranked(rows, {"top_k": training.get("max_names", 12)})
    irr_w, _ = apply_constraints(tickers, irr, None, mandate_doc, falsifier_map)

    def eq_fn(ts, _i):
        return policy_equal_weight(rows)

    def irr_fn(ts, _i):
        return policy_irr_ranked(rows, {"top_k": 12})

    bt_eq = simulate(tickers, panel["dates"], panel["returns_by_ticker"], eq_fn, mandate_doc, falsifier_map)
    bt_irr = simulate(tickers, panel["dates"], panel["returns_by_ticker"], irr_fn, mandate_doc, falsifier_map)

    # Phase 2 encoder
    n_factors = training.get("latent_factors", 5)
    _, latent, enc_meta = train_encoder(
        rows,
        n_factors=n_factors,
        epochs=training.get("encoder_epochs", 80),
        lr=training.get("encoder_lr", 0.02),
    )

    # Phase 3 GA + PPO
    best_genome, ga_hist = run_ga(rows, panel, mandate_doc, latent, training)
    ppo_policy, ppo_metrics = train_ppo(rows, panel, latent, mandate_doc, training)

    genome_w = apply_policy(
        best_genome.get("policy", "irr_ranked"),
        rows,
        {**best_genome, "use_latent": True},
        latent,
    )
    genome_w, _ = apply_constraints(tickers, genome_w, None, mandate_doc, falsifier_map)

    def ga_fn(ts, _i):
        return apply_policy(
            best_genome.get("policy", "irr_ranked"),
            rows,
            {**best_genome, "use_latent": True},
            latent,
        )

    bt_ga = simulate(tickers, panel["dates"], panel["returns_by_ticker"], ga_fn, mandate_doc, falsifier_map)

    prev_equal = {t: 1.0 / min(len(tickers), 15) for t in tickers[:15]}
    if len(prev_equal) < len(tickers):
        s = sum(prev_equal.values()) or 1.0
        prev_equal = {t: prev_equal.get(t, 0.0) / s for t in prev_equal}
    ppo_w = ppo_weights(ppo_policy, rows, latent, mandate_doc, prev_equal)

    def ppo_fn(ts, _i):
        return ppo_weights(ppo_policy, rows, latent, mandate_doc, prev_equal)

    bt_ppo = simulate(tickers, panel["dates"], panel["returns_by_ticker"], ppo_fn, mandate_doc, falsifier_map)

    # Select champion by Sharpe - kappa*turnover
    kappa = (mandate_doc.get("mandate") or {}).get("turnover_penalty_kappa", 0.35)

    def score_bt(bt: dict) -> float:
        if bt.get("error"):
            return -1e9
        return bt.get("sharpe_annualized", 0) - kappa * bt.get("avg_turnover_one_way", 0)

    candidates = [
        ("ppo", ppo_w, bt_ppo),
        ("genetic", genome_w, bt_ga),
        ("irr_ranked", irr_w, bt_irr),
        ("equal_weight", eq_w, bt_eq),
    ]
    champion = max(candidates, key=lambda x: score_bt(x[2]))
    policy_id, target_w, champion_bt = champion

    prev_w = irr_w if irr_w else prev_equal
    target_w, c_notes = apply_constraints(tickers, target_w, prev_w, mandate_doc, falsifier_map)
    turnover_used = c_notes.get("turnover_one_way", 0.0)

    attribution = factor_attribution(
        rows,
        latent,
        target_w,
        enc_meta.get("factor_labels") or [f"factor_{i+1}" for i in range(n_factors)],
    )

    conflicts = []
    for r in rows:
        t = r["ticker"]
        w = target_w.get(t, 0.0)
        stance = (r.get("classification") or {}).get("stance", "watch")
        if w >= 0.08 and stance in ("watch", "trim", "exit"):
            conflicts.append(
                {"ticker": t, "weight_pct": round(w * 100, 2), "stance": stance, "reason": "high_weight_low_stance"}
            )
        if r.get("human_review_pending") and w >= 0.1:
            conflicts.append(
                {"ticker": t, "weight_pct": round(w * 100, 2), "reason": "human_review_pending"}
            )

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": "0-3",
        "mandate": mandate_doc.get("mandate"),
        "regime": _regime_label(rows, mandate_doc),
        "rebalance_frequency": mandate_doc.get("mandate", {}).get("rebalance_frequency", "quarterly"),
        "turnover_budget_pct": mandate_doc.get("mandate", {}).get(
            "max_one_way_turnover_pct_per_rebalance", 15
        ),
        "turnover_used_pct": round(turnover_used * 100, 2),
        "policy_id": policy_id,
        "policy_detail": {
            "champion": policy_id,
            "genome": best_genome if policy_id == "genetic" else None,
            "ga_generations": ga_hist,
            "ppo_metrics": ppo_metrics,
        },
        "weights": weights_to_list(target_w, features_by_ticker, prev_w),
        "benchmarks": {
            "equal_weight": bt_eq,
            "irr_ranked": bt_irr,
            "genetic": bt_ga,
            "ppo": bt_ppo,
            "champion": champion_bt,
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
        "evolution_log": [
            {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "event": "rebalance",
                "policy": policy_id,
                "turnover_pct": round(turnover_used * 100, 2),
                "note": f"Champion {policy_id} Sharpe {champion_bt.get('sharpe_annualized')}",
            }
        ],
        "disclaimer": mandate_doc.get("disclaimer"),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out
