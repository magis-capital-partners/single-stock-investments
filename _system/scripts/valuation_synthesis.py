#!/usr/bin/env python3
"""Build total synthesis IRR from all valuation paths + third-party + qualitative factors.

Called from marvin_valuation.py --write after overlay_results are computed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _round_pct(x: float) -> float:
    return round(x, 2)


def _load_inventory(ticker: str) -> dict | None:
    tp = ROOT / ticker / "third-party-analyses"
    if not tp.is_dir():
        return None
    files = sorted(tp.glob("source_inventory_*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _default_paths(data: dict) -> list[dict]:
    """Auto-build synthesis paths from valuation.json results."""
    paths: list[dict] = []
    ir = data.get("implied_return") or {}
    fa = ir.get("falsifier_adjusted_pct")
    if fa is not None:
        paths.append(
            {
                "id": "filing_falsifier",
                "label": "Filings + growth theory (falsifier-adjusted)",
                "source": "10-K/10-Q OCF; growth_explanation",
                "return_pct": fa,
                "weight": 0.30,
                "type": "numeric",
            }
        )
    gt = data.get("results_growth_theory") or {}
    ti = gt.get("theory_implied", {}).get("return_pct")
    if ti is not None and ti != fa:
        paths.append(
            {
                "id": "theory_implied",
                "label": "Segment-derived growth (pre-falsifier)",
                "source": "segment_build weighted blend",
                "return_pct": ti,
                "weight": 0.08,
                "type": "numeric",
            }
        )
    legacy = data.get("results_lawrence_legacy") or data.get("results") or {}
    for case, w in (("bear", 0.05), ("bull", 0.12)):
        pct = legacy.get(case, {}).get("return_pct")
        if pct is not None:
            paths.append(
                {
                    "id": f"scenario_{case}",
                    "label": f"{case.capitalize()} scenario (Lawrence)",
                    "source": f"scenarios.{case}",
                    "return_pct": pct,
                    "weight": w,
                    "type": "numeric",
                }
            )
    recon = (data.get("segment_build") or {}).get("reconciliation") or {}
    seg_irr = recon.get("implied_business_return_pct")
    if seg_irr is not None:
        paths.append(
            {
                "id": "segment_implied",
                "label": "Segment cash-flow build (reverse DCF)",
                "source": "segment_build @ explicit discount",
                "return_pct": seg_irr,
                "weight": 0.20,
                "type": "numeric",
            }
        )
    gate = data.get("optionality_gate") or {}
    overlay_nav = gate.get("overlay_nav_per_share")
    price = (data.get("inputs") or {}).get("price")
    if overlay_nav and price and overlay_nav > 0:
        years = 10
        nav_irr = ((overlay_nav / price) ** (1 / years) - 1) * 100
        paths.append(
            {
                "id": "nav_overlay_payoff",
                "label": "NAV overlay dated payoff (10yr to overlay base)",
                "source": f"nav_overlay ~${overlay_nav}/sh vs price ${price}",
                "return_pct": _round_pct(nav_irr),
                "weight": 0.10,
                "type": "numeric",
            }
        )
    inv = _load_inventory(data.get("ticker", ""))
    if inv:
        n_ctx = sum(1 for s in inv.get("sources", []) if s.get("status") == "context")
        if n_ctx:
            bull_pct = legacy.get("bull", {}).get("return_pct")
            paths.append(
                {
                    "id": "third_party_context",
                    "label": "Third-party context (HK + Substacks inventory)",
                    "source": f"source_inventory ({n_ctx} sources); cross_check blend",
                    "return_pct": bull_pct if bull_pct is not None else fa,
                    "weight": 0.10,
                    "type": "numeric",
                    "notes": "Proxy: upside case when strategic third party has no spot IRR",
                }
            )
    return paths


def _default_qualitative(data: dict, ticker: str) -> list[dict]:
    """Qualitative ±pp from moat, dhando, cross-check themes."""
    adj: list[dict] = []
    ci = data.get("classification_inputs") or {}
    moat = ci.get("moat", "")
    dhando = ci.get("dhando", "")
    if moat == "durable":
        adj.append(
            {
                "factor": "Competition / moat (scarce Permian acreage, no scale peer)",
                "pp": 0.3,
                "rationale": "Irreplaceable surface + royalty footprint limits competitive entry",
                "sources": "10-K Item 1; Business & moat",
            }
        )
    if dhando == "partial":
        adj.append(
            {
                "factor": "Partial dhando (HK hard-asset / hidden NAV)",
                "pp": 0.5,
                "rationale": "Third-party confirms asset quality not in GAAP book; not full floor at spot price",
                "sources": "cross_check_HK; hk_scan; HK Q1 2025/2026",
            }
        )
    inv = _load_inventory(ticker)
    if inv:
        for s in inv.get("sources", []):
            title = (s.get("title") or "").lower()
            if "governance" in title or "end of an era" in title:
                adj.append(
                    {
                        "factor": "Governance transition (post-Stahl)",
                        "pp": -0.4,
                        "rationale": "Capital allocation uncertainty until proven",
                        "sources": s.get("path", "LCI Substack"),
                    }
                )
                break
        for s in inv.get("sources", []):
            if "water" in (s.get("use") or "").lower() or "water" in title:
                adj.append(
                    {
                        "factor": "Water scarcity tailwind (SSI / HK index-weight)",
                        "pp": 0.25,
                        "rationale": "TPWR segment + index cannot replicate subsurface water exposure",
                        "sources": s.get("path", "SSI/HK"),
                    }
                )
                break
    pred = ci.get("predictive_attribute", "none")
    if pred in (None, "", "none"):
        adj.append(
            {
                "factor": "No dated predictive attribute at spot",
                "pp": -0.2,
                "rationale": "Scarcity is descriptive; no timed mispricing catalyst in base",
                "sources": "HK predictive attributes framework",
            }
        )
    return adj


def compute_synthesis(data: dict) -> dict:
    """Populate data['synthesis'] and update implied_return when complete."""
    ticker = data.get("ticker", "")
    existing = data.get("synthesis") or {}
    paths = existing.get("paths") or _default_paths(data)
    if not paths:
        data["synthesis"] = {"status": "incomplete", "reason": "no numeric paths"}
        return data["synthesis"]

    total_w = sum(p.get("weight", 0) for p in paths if p.get("return_pct") is not None)
    if total_w <= 0:
        data["synthesis"] = {"status": "incomplete", "reason": "zero weights"}
        return data["synthesis"]

    numeric = 0.0
    for p in paths:
        if p.get("return_pct") is None:
            continue
        w = p.get("weight", 0) / total_w
        numeric += w * float(p["return_pct"])

    qual = existing.get("qualitative_adjustments") or _default_qualitative(data, ticker)
    qual_pp = sum(float(q.get("pp", 0)) for q in qual)
    qual_pp = max(-3.0, min(3.0, qual_pp))

    total = _round_pct(numeric + qual_pp)
    numeric_r = _round_pct(numeric)

    synthesis = {
        "status": "complete",
        "paths": paths,
        "qualitative_adjustments": qual,
        "numeric_weighted_pct": numeric_r,
        "qualitative_pp": _round_pct(qual_pp),
        "total_synthesis_pct": total,
        "human_approval": existing.get("human_approval", "pending"),
        "notes": "Capstone IRR combining filings, segments, overlays, third-party, qualitative",
    }
    data["synthesis"] = synthesis

    ir = data.setdefault("implied_return", {})
    fa_ref = ir.get("falsifier_adjusted_pct")
    if fa_ref is None:
        fa_ref = ir.get("base_pct")
    ir["falsifier_adjusted_pct"] = fa_ref
    ir["synthesis_pct"] = total
    ir["base_pct"] = total
    ir["label"] = "10yr IRR (total synthesis)"
    ir["display"] = f"{total}% (total synthesis)"
    return synthesis


def synthesis_markdown(data: dict) -> str:
    syn = data.get("synthesis") or {}
    if syn.get("status") != "complete":
        return ""
    lines = [
        "### Total synthesis IRR (all sources)",
        "",
        "Capstone return combining **filings**, **segment/NAV overlays**, **growth theory**, "
        "**third-party cross-checks**, and **qualitative** moat/competition/governance judgments.",
        "",
        "| # | Source / lens | Type | Return (10yr) | Weight | Role in synthesis |",
        "|---|---------------|------|---------------|--------|-------------------|",
    ]
    for i, p in enumerate(syn.get("paths", []), 1):
        ret = p.get("return_pct")
        ret_cell = f"**{ret}%**" if ret is not None else "qualitative"
        w = p.get("weight", 0) * 100
        role = (p.get("notes") or p.get("source", ""))[:70]
        lines.append(
            f"| {i} | {p.get('label', '')} | {p.get('type', 'numeric')} | {ret_cell} | {w:.0f}% | {role} |"
        )
    lines += [
        "",
        "#### Qualitative adjustments (competition, moat, governance)",
        "",
        "| Factor | ±pp | Rationale | Sources |",
        "|--------|-----|-----------|---------|",
    ]
    for q in syn.get("qualitative_adjustments", []):
        pp = q.get("pp", 0)
        sign = "+" if pp >= 0 else ""
        lines.append(
            f"| {q.get('factor', '')} | {sign}{pp} | {q.get('rationale', '')[:80]} | {q.get('sources', '')[:60]} |"
        )
    n = syn.get("numeric_weighted_pct")
    qpp = syn.get("qualitative_pp")
    t = syn.get("total_synthesis_pct")
    lines += [
        "",
        "#### Synthesis arithmetic (show your work)",
        "",
        f"1. **Numeric weighted return:** {_fmt_paths_sum(syn.get('paths', []))} = **{n}%** per year",
        f"2. **Qualitative adjustments:** {' + '.join(_qual_terms(syn.get('qualitative_adjustments', [])))} = **{qpp}** pp",
        f"3. **Total synthesis IRR:** {n}% + {qpp}pp = **{t}%** per year",
        "",
        f"**Returns statement (synthesis):** At today's price, we expect about **{t}%** per year over ten years "
        f"after weighting filings, segment build, scenarios, NAV overlay, third-party context, and qualitative moat/governance factors.",
        "",
        f"**[HUMAN REVIEW]:** Synthesis weights and qualitative pp default to auto-build; "
        f"approval status: **{syn.get('human_approval', 'pending')}**. "
        f"Filing-only falsifier-adjusted reference: **{data.get('implied_return', {}).get('falsifier_adjusted_pct', 'n/a')}%**.",
        "",
    ]
    return "\n".join(lines)


def _fmt_paths_sum(paths: list[dict]) -> str:
    parts = []
    total_w = sum(p.get("weight", 0) for p in paths if p.get("return_pct") is not None)
    if total_w <= 0:
        return "n/a"
    for p in paths:
        if p.get("return_pct") is None:
            continue
        w = p.get("weight", 0) / total_w
        parts.append(f"{w:.0%}×({p['return_pct']}%)")
    return " + ".join(parts[:6]) + (" + …" if len(parts) > 6 else "")


def _qual_terms(quals: list[dict]) -> list[str]:
    out = []
    for q in quals:
        pp = q.get("pp", 0)
        sign = "+" if pp >= 0 else ""
        out.append(f"{sign}{pp}")
    return out or ["0"]


if __name__ == "__main__":
    import sys

    t = sys.argv[1] if len(sys.argv) > 1 else "TPL"
    path = ROOT / t / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    compute_synthesis(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(synthesis_markdown(data))
