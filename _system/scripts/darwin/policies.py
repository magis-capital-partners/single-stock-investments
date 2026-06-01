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


POLICY_FNS = {
    "equal_weight": policy_equal_weight,
    "irr_ranked": policy_irr_ranked,
    "archetype_risk_parity": policy_archetype_risk_parity,
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
