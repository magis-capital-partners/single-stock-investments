"""Deutsch-style plain-English explanation for Darwin portfolio construction."""
from __future__ import annotations


def _top_holdings(target_w: dict[str, float], features_by_ticker: dict, n: int = 5) -> list[dict]:
    ranked = sorted(target_w.items(), key=lambda x: -x[1])[:n]
    out = []
    for ticker, w in ranked:
        row = features_by_ticker.get(ticker) or {}
        clf = row.get("classification") or {}
        out.append(
            {
                "ticker": ticker,
                "weight_pct": round(w * 100, 2),
                "stance": clf.get("stance"),
                "irr_base_pct": row.get("irr_base_pct"),
                "archetype": clf.get("archetype"),
                "moat": clf.get("moat"),
                "dhando": clf.get("dhando"),
            }
        )
    return out


def _policy_mechanism(policy_id: str, ensemble_detail: list | None) -> str:
    mechanisms = {
        "ira_marvin": (
            "IRA Marvin admits only completed, current deep dives with a published "
            "falsifier-adjusted IRR above the mandate threshold, ranks them by that IRR, "
            "and applies research-freshness, diversification, and cash caps."
        ),
        "irr_ranked": "IRR-ranked policy overweight names with higher falsifier-adjusted IRR scores.",
        "equal_weight": "Equal-weight spreads risk across the full registry with no IRR tilt.",
        "risk_parity_vol": "Risk-parity tilts toward lower archetype risk buckets with a mild IRR tilt.",
        "genetic": "Genetic search picked a genome that blends policy type and scoring knobs on in-sample history.",
        "ppo": "PPO reinforcement policy learned weights from latent factors and past returns.",
        "ensemble": "Ensemble blends the top-scoring policies by deflated Sharpe minus turnover penalty.",
    }
    base = mechanisms.get(policy_id, f"Champion policy `{policy_id}` from the Darwin evolution stack.")
    if policy_id == "ensemble" and ensemble_detail:
        parts = [
            f"{e.get('policy')} ({round((e.get('weight_in_ensemble') or 0) * 100)}%)"
            for e in ensemble_detail[:4]
        ]
        if parts:
            base += " Blend: " + ", ".join(parts) + "."
    return base


def build_portfolio_explanation(
    *,
    policy_id: str,
    target_w: dict[str, float],
    rows: list[dict],
    regime: dict,
    mandate: dict,
    constraints_notes: dict | None,
    ensemble_detail: list | None,
    champion_selection: str,
) -> dict:
    """Popper/Deutsch audit block for why the live portfolio looks the way it does."""
    features_by_ticker = {r["ticker"]: r for r in rows}
    m = mandate or {}
    top = _top_holdings(target_w, features_by_ticker)
    excluded = [
        r["ticker"]
        for r in rows
        if r["ticker"] not in target_w or target_w.get(r["ticker"], 0) < 0.001
    ]
    low_irr = [
        r["ticker"]
        for r in rows
        if (r.get("irr_base_pct") or 0) < m.get("min_irr_pct_for_weight", 6)
        and r["ticker"] in target_w
    ]

    falsifier_total = sum(r.get("falsifier_count", 0) for r in rows)
    stale = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > m.get("stale_dive_days_for_review", 120))

    flags: list[str] = []
    if champion_selection == "exploration":
        flags.append("Exploration mode: champion may not be production-safe ML.")
    if constraints_notes and constraints_notes.get("turnover_capped_output"):
        flags.append(
            f"Turnover cap applied: one-way trade limited to about "
            f"{round((constraints_notes.get('turnover_one_way') or 0) * 100, 1)}%."
        )
    if low_irr:
        flags.append(
            f"Names below min IRR gate ({m.get('min_irr_pct_for_weight', 6)}%) still held at small weights: "
            + ", ".join(low_irr[:5])
            + ("…" if len(low_irr) > 5 else "")
        )
    if falsifier_total >= (m.get("regime") or {}).get("falsifier_stress_threshold", 3):
        flags.append("Research regime stressed: falsifier count elevated across the book.")

    mechanism = _policy_mechanism(policy_id, ensemble_detail)
    summary = (
        f"We hold {len(target_w)} names under **{policy_id}** in a **{regime.get('label', 'unknown')}** regime. "
        f"{mechanism} Largest positions: "
        + ", ".join(f"{h['ticker']} {h['weight_pct']}%" for h in top[:3])
        + "."
    )

    falsifiers = [
        f"If {h['ticker']} falsifiers fire, weight should drop or exit per mandate."
        for h in top[:3]
        if (features_by_ticker.get(h["ticker"]) or {}).get("falsifier_count", 0) > 0
    ]
    falsifiers.extend(
        [
            "If OOS Sharpe for ML policies falls below gate, champion reverts to IRA Marvin.",
            "If turnover budget is breached, next rebalance scales trades toward prior weights.",
            "If regime shifts to stressed, turnover multiplier and caps tighten automatically.",
        ]
    )

    deutsch_checks = {
        "hard_to_vary": policy_id in ("ira_marvin", "ensemble", "irr_ranked", "risk_parity_vol"),
        "falsifiable": True,
        "not_instrumentalist": champion_selection != "forced_ml_without_oos",
        "reach": (
            "Weights follow published mandate rules and Marvin research inputs, "
            "not a fitted price target."
        ),
    }
    if policy_id in ("ppo", "genetic") and champion_selection == "ml_insample":
        deutsch_checks["hard_to_vary"] = False
        flags.append("ML champion selected in-sample; treat weights as hypothesis until OOS gate passes.")

    return {
        "summary": summary,
        "mechanism": mechanism,
        "champion_selection": champion_selection,
        "regime": regime.get("label"),
        "top_holdings": top,
        "excluded_count": len(excluded),
        "excluded_sample": excluded[:8],
        "drivers": [
            {"factor": "Falsifier-adjusted IRR", "role": "Sole selection rank input for the IRA policy"},
            {"factor": "Deep-dive validity", "role": "Completed valuation required; no proxy returns for unresearched names"},
            {"factor": "Research freshness", "role": f"{stale} names beyond review threshold; aging research has a lower cap"},
            {"factor": "Falsifiers", "role": f"Book total {falsifier_total}; critical evidence prevents allocation"},
            {"factor": "Mandate caps", "role": "Position, diversification, turnover, and cash limits; stance is context only"},
            {"factor": "Macro regime", "role": f"Label {regime.get('label')} adjusts constraint overrides"},
        ],
        "popper_falsifiers": falsifiers,
        "flags": flags,
        "deutsch_checks": deutsch_checks,
    }
