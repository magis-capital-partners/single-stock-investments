"""Bottom-up growth derivation, falsifier adjustments, Deutsch gate (Popper/Deutsch IRR path)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def blend_segment_growth(segments: list[dict]) -> dict[str, Any] | None:
    """Weight segment growth rates by owner cash Y0 per share."""
    rows = []
    for seg in segments:
        f0 = seg.get("owner_cash_y0_per_share")
        if f0 is None or float(f0) <= 0:
            continue
        rows.append(
            {
                "id": seg.get("id", ""),
                "weight": float(f0),
                "growth_y1_5": float(seg.get("growth_y1_5", 0)),
                "growth_y6_10": float(seg.get("growth_y6_10", 0)),
                "exit_pfcf_y10": float(seg.get("exit_pfcf_y10", 22)),
            }
        )
    if not rows:
        return None
    total = sum(r["weight"] for r in rows)
    g1 = sum(r["weight"] * r["growth_y1_5"] for r in rows) / total
    g2 = sum(r["weight"] * r["growth_y6_10"] for r in rows) / total
    exit_w = sum(r["weight"] * r["exit_pfcf_y10"] for r in rows) / total
    return {
        "y1_5": round(g1, 4),
        "y6_10": round(g2, 4),
        "exit_pfcf_y10_segment_blend": round(exit_w, 1),
        "derivation": "segment_build owner-cash weighted blend (growth only; exit from scenarios.base)",
        "segment_weights": [
            {"id": r["id"], "weight_pct": round(100 * r["weight"] / total, 1)} for r in rows
        ],
    }


def derive_theory_implied(data: dict) -> dict[str, Any] | None:
    """Step A: bottom-up growth from segment_build (or segment_theories fallback)."""
    build = data.get("segment_build") or {}
    segments = build.get("segments") or []
    implied = blend_segment_growth(segments)
    if implied:
        return implied

    ge = data.get("growth_explanation") or {}
    theories = ge.get("segment_theories") or []
    if not theories:
        consolidated = ge.get("consolidated_growth") or {}
        if consolidated.get("y1_5") is not None:
            base = data.get("scenarios", {}).get("base", {})
            return {
                "y1_5": float(consolidated["y1_5"]),
                "y6_10": float(consolidated.get("y6_10", consolidated["y1_5"] * 0.75)),
                "exit_pfcf_y10": float(base.get("exit_pfcf_y10", 22)),
                "derivation": "growth_explanation.consolidated_growth (no segment_build)",
            }
        return None

    pseudo_segments = []
    for t in theories:
        pseudo_segments.append(
            {
                "id": t.get("segment_id", ""),
                "owner_cash_y0_per_share": 1.0,
                "growth_y1_5": t.get("growth_y1_5", 0.05),
                "growth_y6_10": t.get("growth_y6_10", 0.03),
                "exit_pfcf_y10": 22,
            }
        )
    out = blend_segment_growth(pseudo_segments)
    if out:
        out["derivation"] = "segment_theories equal-weight blend"
    return out


def deutsch_gate_status(growth_explanation: dict) -> str:
    """Step C: block 'complete' unless Deutsch checks pass."""
    if not growth_explanation:
        return "incomplete"
    checks = growth_explanation.get("deutsch_checks") or {}
    if checks.get("hard_to_vary") is not True:
        return "partial"
    if checks.get("falsifiable") is not True:
        return "partial"
    if checks.get("not_instrumentalist") is not True:
        return "partial"
    for mech in growth_explanation.get("mechanisms") or []:
        hv = mech.get("hard_to_vary")
        if hv in (False, "no"):
            return "partial"
    return "complete"


def _parse_pct_from_text(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100 if m else None


def _revenue_yoy(filing_facts: dict) -> float | None:
    rev = (filing_facts.get("metrics") or {}).get("revenues") or {}
    cur, prior = rev.get("current"), rev.get("prior")
    if cur is None or prior in (None, 0):
        return None
    return (float(cur) - float(prior)) / float(prior)


def evaluate_falsifiers(data: dict, filing_facts: dict | None = None) -> dict[str, Any]:
    """Step D: check falsifiers against filings; return adjusted growth + audit trail."""
    ge = data.get("growth_explanation") or {}
    theory = ge.get("theory_implied") or derive_theory_implied(data)
    if not theory:
        base_sc = data.get("scenarios", {}).get("base", {})
        theory = {
            "y1_5": float(base_sc.get("growth_y1_5", 0.05)),
            "y6_10": float(base_sc.get("growth_y6_10", 0.03)),
            "exit_pfcf_y10": float(base_sc.get("exit_pfcf_y10", 22)),
            "derivation": "scenarios.base fallback",
        }

    g1 = float(theory["y1_5"])
    g2 = float(theory["y6_10"])
    base_sc = data.get("scenarios", {}).get("base", {})
    exit_mult = float(base_sc.get("exit_pfcf_y10", base_sc.get("exit_multiple", 22)))
    adjustments: list[dict] = []
    triggered: list[dict] = []

    rev_yoy = _revenue_yoy(filing_facts) if filing_facts else None

    for falsifier in ge.get("falsifiers") or []:
        fid = falsifier.get("id") or falsifier.get("observation", "")[:40]
        obs = falsifier.get("observation", "")
        adj_spec = falsifier.get("adjustment") or {}
        auto = falsifier.get("auto_check") or {}
        fired = False
        reason = ""

        if auto.get("type") == "revenue_yoy_below" and rev_yoy is not None:
            threshold = float(auto.get("threshold_pct", 0.10))
            if rev_yoy < threshold:
                fired = True
                reason = f"Consolidated revenue YoY {rev_yoy*100:.1f}% < {threshold*100:.0f}%"
        elif auto.get("type") == "revenue_yoy_above" and rev_yoy is not None:
            threshold = float(auto.get("threshold_pct", 0.15))
            if rev_yoy >= threshold:
                fired = True
                reason = f"Consolidated revenue YoY {rev_yoy*100:.1f}% >= {threshold*100:.0f}%"

        if not fired and adj_spec.get("manual_only"):
            continue

        if fired or adj_spec.get("apply_on_refresh"):
            delta1 = adj_spec.get("growth_y1_5_delta")
            delta2 = adj_spec.get("growth_y6_10_delta")
            override1 = adj_spec.get("growth_y1_5")
            override2 = adj_spec.get("growth_y6_10")
            if override1 is not None:
                g1 = float(override1)
            elif delta1 is not None:
                g1 += float(delta1)
            if override2 is not None:
                g2 = float(override2)
            elif delta2 is not None:
                g2 += float(delta2)
            if fired or adj_spec.get("apply_on_refresh"):
                entry = {
                    "falsifier_id": fid,
                    "observation": obs,
                    "triggered": fired,
                    "reason": reason or falsifier.get("action", ""),
                    "growth_y1_5_after": round(g1, 4),
                    "growth_y6_10_after": round(g2, 4),
                }
                adjustments.append(entry)
                if fired:
                    triggered.append(entry)

    # Parse action text for cut hints when no structured adjustment (legacy falsifiers)
    if not adjustments:
        for falsifier in ge.get("falsifiers") or []:
            action = falsifier.get("action", "")
            if "cut" in action.lower() and "8%" in action:
                pass  # legacy — no auto trigger without filing segment data

    return {
        "y1_5": round(max(g1, -0.5), 4),
        "y6_10": round(max(g2, -0.5), 4),
        "exit_pfcf_y10": exit_mult,
        "adjustments": adjustments,
        "triggered": triggered,
        "filing_revenue_yoy": round(rev_yoy, 4) if rev_yoy is not None else None,
        "as_of_filing_facts": (filing_facts or {}).get("source_text"),
    }


def load_filing_facts(ticker: str) -> dict | None:
    research = ROOT / ticker / "research" / "evidence"
    if not research.exists():
        return None
    candidates = sorted(research.glob("filing_facts_*.json"), reverse=True)
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def enrich_growth_explanation(data: dict, filing_facts: dict | None = None) -> dict:
    """Compute theory_implied, falsifier_adjusted, status; mutate data in place."""
    ge = data.setdefault("growth_explanation", {})
    if filing_facts is None and data.get("ticker"):
        filing_facts = load_filing_facts(data["ticker"])

    theory = derive_theory_implied(data)
    if theory:
        ge["theory_implied"] = theory

    lawrence = data.get("scenarios", {}).get("base", {})
    ge["lawrence_legacy"] = {
        "y1_5": lawrence.get("growth_y1_5"),
        "y6_10": lawrence.get("growth_y6_10"),
        "return_pct": (data.get("results_lawrence_legacy") or data.get("results", {}).get("base", {})).get(
            "return_pct"
        ),
    }

    falsifier_adj = evaluate_falsifiers(data, filing_facts)
    ge["falsifier_adjusted"] = falsifier_adj
    ge["status"] = deutsch_gate_status(ge)

    if theory and falsifier_adj:
        ge["divergence"] = {
            "theory_vs_lawrence_y1_5_pp": round((theory["y1_5"] - float(lawrence.get("growth_y1_5", 0))) * 100, 1),
            "falsifier_vs_theory_y1_5_pp": round((falsifier_adj["y1_5"] - theory["y1_5"]) * 100, 1),
        }

    return ge


def theory_scenario(data: dict, path: str = "falsifier_adjusted") -> dict:
    """Build a Lawrence-style scenario dict from theory paths."""
    ge = data.get("growth_explanation") or {}
    base = data.get("scenarios", {}).get("base", {})
    if path == "theory_implied":
        src = ge.get("theory_implied") or {}
    else:
        src = ge.get("falsifier_adjusted") or ge.get("theory_implied") or {}
    exit_mult = float(base.get("exit_pfcf_y10", base.get("exit_multiple", 22)))
    return {
        "growth_y1_5": float(src.get("y1_5", base.get("growth_y1_5", 0.05))),
        "growth_y6_10": float(src.get("y6_10", base.get("growth_y6_10", 0.03))),
        "exit_pfcf_y10": exit_mult,
        "notes": f"Popper/Deutsch {path}",
    }
