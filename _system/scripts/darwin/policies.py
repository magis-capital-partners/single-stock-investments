"""Allocation policies: naive baselines + genome-driven (Phase 1 & 3)."""
from __future__ import annotations

import math
from typing import Any


def _score_row(row: dict, genome: dict | None = None) -> float:
    g = genome or {}
    irr = row.get("irr_falsifier_pct") or row.get("irr_base_pct") or 0.0
    power = g.get("irr_power", 1.0)
    score = max(float(irr), -5.0) ** power
    moat = (row.get("classification") or {}).get("moat", "unproven")
    moat_bonus = g.get("moat_bonus", 0.15)
    if moat == "widening":
        score *= 1.0 + moat_bonus
    elif moat == "stable":
        score *= 1.0 + moat_bonus * 0.5
    elif moat == "eroding":
        score *= 1.0 - moat_bonus
    dhando = (row.get("classification") or {}).get("dhando", "none")
    if dhando == "full":
        score *= 1.0 + g.get("dhando_bonus", 0.1)
    elif dhando == "partial":
        score *= 1.0 + g.get("dhando_bonus", 0.1) * 0.5
    staleness = row.get("days_since_deep_dive") or 0
    score -= g.get("staleness_penalty", 0.02) * (staleness / 365.0)
    score -= g.get("falsifier_penalty", 0.5) * (row.get("falsifier_count") or 0)
    if row.get("human_review_pending"):
        score *= 1.0 - g.get("human_review_discount", 0.2)
    archetype = (row.get("classification") or {}).get("archetype", "unknown")
    arch_w = (g.get("archetype_weights") or {}).get(archetype, 1.0)
    score *= arch_w
    return max(score, 1e-6)


def policy_equal_weight(rows: list[dict], genome: dict | None = None) -> dict[str, float]:
    tickers = [r["ticker"] for r in rows]
    n = len(tickers) or 1
    return {t: 1.0 / n for t in tickers}


def policy_irr_ranked(rows: list[dict], genome: dict | None = None) -> dict[str, float]:
    g = genome or {"top_k": 12, "irr_power": 1.2}
    top_k = int(g.get("top_k", 12))
    scored = [(r["ticker"], _score_row(r, g)) for r in rows]
    scored.sort(key=lambda x: -x[1])
    keep = scored[:top_k]
    total = sum(s for _, s in keep) or 1.0
    return {t: s / total for t, s in keep}


def policy_archetype_risk_parity(rows: list[dict], genome: dict | None = None) -> dict[str, float]:
    g = genome or {}
    risk = {
        "compounder": 1.0,
        "croupier": 1.1,
        "platform": 1.05,
        "serial_acquirer": 1.15,
        "holding_co": 1.2,
        "optionality": 1.35,
        "turnaround": 1.4,
        "infrastructure": 1.05,
        "unknown": 1.25,
    }
    inv: dict[str, float] = {}
    for r in rows:
        arch = (r.get("classification") or {}).get("archetype", "unknown")
        inv[r["ticker"]] = 1.0 / (risk.get(arch, 1.2) * g.get("risk_scale", 1.0))
    s = sum(inv.values()) or 1.0
    return {t: v / s for t, v in inv.items()}


def policy_softmax_latent(
    rows: list[dict],
    latent: dict[str, list[float]],
    genome: dict | None = None,
) -> dict[str, float]:
    g = genome or {"temperature": 0.5}
    temp = max(g.get("temperature", 0.5), 0.05)
    tickers = [r["ticker"] for r in rows]
    logits = []
    for r in rows:
        z = latent.get(r["ticker"], [0.0])
        logits.append(sum(z) / max(len(z), 1))
    m = max(logits)
    exps = [math.exp((x - m) / temp) for x in logits]
    s = sum(exps) or 1.0
    return {tickers[i]: exps[i] / s for i in range(len(tickers))}


def policy_ira_marvin(rows: list[dict], genome: dict | None = None) -> dict[str, float]:
    """IRA: Marvin IRR × stance × dhando; drop negative IRR watch names."""
    g = genome or {}
    mandate_scoring = g.get("ira_scoring") or {}
    stance_m = mandate_scoring.get("stance_multipliers") or {
        "core": 1.25,
        "accumulate": 1.15,
        "hold": 1.0,
        "watch": 0.45,
        "trim": 0.2,
        "exit": 0.0,
    }
    dhando_m = mandate_scoring.get("dhando_multipliers") or {
        "full": 1.12,
        "partial": 1.05,
        "none": 0.85,
        "pending": 0.9,
    }
    market_m = mandate_scoring.get("market_multipliers") or {}
    min_irr = g.get("min_irr_pct_for_weight", 6.0)
    allow_stances = set(g.get("exclude_negative_irr_unless_stance") or ["core", "accumulate"])
    top_k = int(g.get("top_k", 12))

    scored: list[tuple[str, float]] = []
    for r in rows:
        irr = r.get("irr_falsifier_pct") or r.get("irr_base_pct")
        if irr is None:
            continue
        cl = r.get("classification") or {}
        stance = (cl.get("stance") or "watch").lower()
        if irr < 0 and stance not in allow_stances:
            continue
        if irr < min_irr and stance not in allow_stances:
            continue
        if stance in ("watch", "trim", "exit") and stance not in allow_stances:
            continue
        score = max(float(irr), 0.1)
        score *= stance_m.get(stance, 0.5)
        score *= dhando_m.get((cl.get("dhando") or "pending").lower(), 0.9)
        score *= market_m.get(r.get("market", "US"), 1.0)
        moat = (cl.get("moat") or "").lower()
        if moat in ("widening", "stable"):
            score *= 1.0 + mandate_scoring.get("moat_bonus", 0.12)
        score -= mandate_scoring.get("staleness_penalty_per_year", 0.04) * (
            (r.get("days_since_deep_dive") or 0) / 365.0
        )
        score -= mandate_scoring.get("falsifier_penalty", 0.6) * (r.get("falsifier_count") or 0)
        if r.get("human_review_pending"):
            score *= 1.0 - mandate_scoring.get("human_review_discount", 0.25)
        scored.append((r["ticker"], max(score, 1e-6)))

    scored.sort(key=lambda x: -x[1])
    keep = scored[:top_k]
    min_names = int(g.get("min_names", 8))
    if len(keep) < min_names and len(scored) >= min_names:
        keep = scored[:min_names]
    elif len(keep) < min_names:
        keep = scored
    total = sum(s for _, s in keep) or 1.0
    return {t: s / total for t, s in keep}


POLICY_FNS = {
    "equal_weight": policy_equal_weight,
    "irr_ranked": policy_irr_ranked,
    "archetype_risk_parity": policy_archetype_risk_parity,
    "ira_marvin": policy_ira_marvin,
}


def random_genome(rng) -> dict[str, Any]:
    return {
        "policy": rng.choice(["irr_ranked", "irr_ranked", "archetype_risk_parity"]),
        "top_k": int(rng.integers(8, 16)),
        "irr_power": float(rng.uniform(0.6, 2.0)),
        "moat_bonus": float(rng.uniform(0.05, 0.25)),
        "dhando_bonus": float(rng.uniform(0.0, 0.15)),
        "staleness_penalty": float(rng.uniform(0.01, 0.06)),
        "falsifier_penalty": float(rng.uniform(0.2, 0.8)),
        "human_review_discount": float(rng.uniform(0.1, 0.35)),
        "temperature": float(rng.uniform(0.2, 1.2)),
        "archetype_weights": {
            "optionality": float(rng.uniform(0.7, 1.1)),
            "turnaround": float(rng.uniform(0.6, 1.0)),
            "compounder": float(rng.uniform(0.9, 1.2)),
        },
    }


def mutate_genome(genome: dict, rng, rate: float) -> dict:
    g = dict(genome)
    if rng.random() < rate:
        g["top_k"] = int(rng.integers(8, 16))
    if rng.random() < rate:
        g["irr_power"] = float(rng.uniform(0.6, 2.0))
    if rng.random() < rate:
        g["policy"] = rng.choice(list(POLICY_FNS.keys()))
    return g


def apply_policy(
    name: str,
    rows: list[dict],
    genome: dict | None = None,
    latent: dict[str, list[float]] | None = None,
) -> dict[str, float]:
    if latent and genome and genome.get("use_latent"):
        return policy_softmax_latent(rows, latent, genome)
    fn = POLICY_FNS.get(name or "irr_ranked", policy_irr_ranked)
    return fn(rows, genome)
