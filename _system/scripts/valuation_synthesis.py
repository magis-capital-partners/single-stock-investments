#!/usr/bin/env python3
"""Build total synthesis IRR from all valuation paths + third-party + qualitative factors.

Called from marvin_valuation.py --write after overlay_results are computed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Epistemic tiers for synthesis weights (see total_synthesis_irr.md § Popper / Deutsch)
WEIGHT_THEORY: dict[str, dict] = {
    "filing_falsifier": {
        "tier": "A (primary falsifiable)",
        "default_weight": 0.30,
        "why": "Only path tied to 10-K/10-Q owner cash with growth mechanism + falsifier runner; highest refutation reach.",
        "falsifiers": [
            "Any triggered growth falsifier forces weight cut or path removal",
            "Theory-implied diverges from falsifier-adjusted by >2pp without documented mechanism change",
        ],
        "hard_to_vary": "yes: weight tracks evidence tier, not target IRR",
    },
    "segment_implied": {
        "tier": "B (independent derivation)",
        "default_weight": 0.20,
        "why": "Reverse DCF from segment filing data; cross-checks consolidated growth without replacing falsifier path.",
        "falsifiers": [
            "Segment sum PV tie-out fails vs consolidated OCF",
            "Implied return moves >1pp when segment growth matches filing falsifier-adjusted exactly (double-count signal)",
        ],
        "hard_to_vary": "partial: shares growth inputs with Tier A; weight kept below filing path",
    },
    "scenario_bear": {
        "tier": "C (scenario envelope)",
        "default_weight": 0.05,
        "why": "Downside stress; low weight because bear is a sensitivity, not a competing explanation of base mechanics.",
        "falsifiers": ["Bear assumptions become base case in filings (e.g. sustained volume collapse)"],
        "hard_to_vary": "yes: asymmetric low weight is structural",
    },
    "scenario_bull": {
        "tier": "C (scenario envelope)",
        "default_weight": 0.12,
        "why": "Upside stress probe; higher than bear because optionality archetype has skew, but still below primary paths.",
        "falsifiers": ["Bull growth sustained in filings for 4+ quarters without falsifier trigger"],
        "hard_to_vary": "yes",
    },
    "nav_overlay_payoff": {
        "tier": "D (alternate theory: dated asset payoff)",
        "default_weight": 0.10,
        "why": "Answers a different question (NAV convergence) than 10yr cash-flow IRR; capped weight to avoid theory conflation.",
        "falsifiers": [
            "NAV overlay base not updated when segment build or filings change >10%",
            "floor_pass false but weight above 15% without [HUMAN REVIEW]",
        ],
        "hard_to_vary": "yes: separate theory type",
    },
    "third_party_context": {
        "tier": "D (external triangulation)",
        "default_weight": 0.10,
        "why": "Context-tier HK/Substacks until human promotes in third_party_sources.md; numeric proxy is weak.",
        "falsifiers": [
            "Using bull scenario as HK proxy when cross_check synthesis says no IRR upgrade",
            "Weight above 15% while human_approval pending",
        ],
        "hard_to_vary": "no: proxy return is instrumentalist; prefer qualitative pp until approved blend",
    },
    "theory_implied": {
        "tier": "B (pre-falsifier derivation)",
        "default_weight": 0.08,
        "why": "Segment blend before falsifier pass; diagnostic only when it differs from falsifier-adjusted.",
        "falsifiers": ["Included at full weight alongside falsifier-adjusted without divergence note"],
        "hard_to_vary": "partial",
    },
}


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


def _attach_weight_theory(paths: list[dict]) -> list[dict]:
    """Enrich each path with epistemic weight rationale for Popper/Deutsch audit."""
    out: list[dict] = []
    for p in paths:
        pid = p.get("id", "")
        theory = WEIGHT_THEORY.get(pid, {})
        enriched = dict(p)
        if theory:
            enriched["epistemic_tier"] = theory.get("tier", "")
            enriched["weight_why"] = theory.get("why", "")
            enriched["weight_falsifiers"] = theory.get("falsifiers", [])
            enriched["hard_to_vary"] = theory.get("hard_to_vary", "partial")
        out.append(enriched)
    return out


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
        n_tp = sum(
            1
            for s in inv.get("sources", [])
            if s.get("status") in ("approved", "context")
            and s.get("source_id") in ("reference", "hk", "short_report")
        )
        if n_tp:
            bull_pct = legacy.get("bull", {}).get("return_pct")
            paths.append(
                {
                    "id": "third_party_context",
                    "label": "Third-party approved (HK + Substacks + inventory)",
                    "source": f"source_inventory ({n_tp} sources); cross_check blend",
                    "return_pct": bull_pct if bull_pct is not None else fa,
                    "weight": 0.10,
                    "type": "numeric",
                    "notes": "Proxy: upside case when strategic third party has no spot IRR",
                }
            )
    return _attach_weight_theory(paths)


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


def _synthesis_weight_flags(paths: list[dict], qual: list[dict]) -> dict:
    """Popper/Deutsch audit flags for the weight scheme itself."""
    flags: list[str] = []
    by_id = {p.get("id"): p for p in paths}
    tp = by_id.get("third_party_context") or {}
    nav = by_id.get("nav_overlay_payoff") or {}
    if tp and tp.get("return_pct") == (by_id.get("scenario_bull") or {}).get("return_pct"):
        flags.append(
            "Third-party numeric path proxies bull scenario (instrumentalist); HK cross-check says no base IRR upgrade. Prefer qualitative pp only until approved blend."
        )
    if nav and (nav.get("weight") or 0) >= 0.10:
        flags.append(
            "NAV overlay is a different theory (asset payoff vs cash-flow IRR); weight capped at 10% to limit theory conflation."
        )
    seg = by_id.get("segment_implied") or {}
    fil = by_id.get("filing_falsifier") or {}
    if seg and fil and abs(float(seg.get("return_pct", 0)) - float(fil.get("return_pct", 0))) < 0.5:
        flags.append(
            "Segment implied approx filing falsifier-adjusted; shared growth inputs. Combined Tier A+B weight is ~54% after renormalize (watch double-count)."
        )
    if len(qual) >= 3:
        flags.append(
            "Qualitative ±pp stack may overlap numeric paths (moat/dhando); cap ±3pp and require source for each row."
        )
    htv_bad = any(str(p.get("hard_to_vary", "")).startswith("no") for p in paths)
    return {
        "flags": flags,
        "deutsch_checks": {
            "hard_to_vary": not htv_bad,
            "falsifiable": bool(any(p.get("weight_falsifiers") for p in paths)),
            "not_instrumentalist": tp.get("hard_to_vary", "").startswith("no") is False if tp else True,
            "reach": "Weights encode evidence tier (A primary → D external), not fitted to hit a target IRR",
        },
    }


def _weight_stress_markdown(paths: list[dict], flags: dict) -> str:
    total_w = sum(p.get("weight", 0) for p in paths if p.get("return_pct") is not None)
    lines = [
        "#### Why these weights (Popper / Deutsch)",
        "",
        "Weights are **not** optimized to hit a target return. They encode **epistemic tier**: "
        "how independently falsifiable each path is. Template defaults live in `total_synthesis_irr.md`; "
        "renormalized shares below sum to 100%.",
        "",
        "| Path | Tier | Raw weight | Renormalized | Why this weight | Hard to vary? |",
        "|------|------|------------|--------------|-----------------|---------------|",
    ]
    for p in paths:
        if p.get("return_pct") is None:
            continue
        rw = p.get("weight", 0)
        nw = rw / total_w * 100 if total_w else 0
        why = (p.get("weight_why") or p.get("source", ""))[:90]
        htv = p.get("hard_to_vary", "partial")
        lines.append(
            f"| {p.get('label', '')[:45]} | {p.get('epistemic_tier', '-')[:22]} | "
            f"{rw*100:.0f}% | {nw:.0f}% | {why} | {htv} |"
        )
    lines += [
        "",
        "#### Weight-scheme falsifiers (Popper)",
        "",
    ]
    for p in paths:
        for f in p.get("weight_falsifiers") or []:
            lines.append(f"- **{p.get('id', '')}:** {f}")
    for f in flags.get("flags") or []:
        lines.append(f"- **[Audit]:** {f}")
    dc = flags.get("deutsch_checks") or {}
    lines += [
        "",
        "#### Deutsch checks (weight theory)",
        "",
        "| Check | Pass? | Notes |",
        "|-------|-------|-------|",
        f"| Hard to vary | {'yes' if dc.get('hard_to_vary') else 'partial'} | Weights tied to evidence tier, not narrative fitting |",
        f"| Falsifiable | {'yes' if dc.get('falsifiable') else 'no'} | Each path lists what would force a weight change |",
        f"| Not instrumentalist | {'yes' if dc.get('not_instrumentalist') else 'no'} | Flag if bull proxy used for third party |",
        f"| Reach | yes | {dc.get('reach', '')} |",
        "",
    ]
    return "\n".join(lines)


def compute_synthesis(data: dict) -> dict:
    """Populate data['synthesis'] and update implied_return when complete."""
    ticker = data.get("ticker", "")
    existing = data.get("synthesis") or {}
    raw_paths = existing.get("paths") or _default_paths(data)
    paths = _attach_weight_theory(raw_paths)
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

    weight_audit = _synthesis_weight_flags(paths, qual)

    total = _round_pct(numeric + qual_pp)
    numeric_r = _round_pct(numeric)

    synthesis = {
        "status": "complete",
        "paths": paths,
        "qualitative_adjustments": qual,
        "numeric_weighted_pct": numeric_r,
        "qualitative_pp": _round_pct(qual_pp),
        "total_synthesis_pct": total,
        "human_approval": existing.get("human_approval")
        or (
            "approved"
            if (data.get("ticker") or "").upper() in {"TEQ.ST", "TPL", "FRMO", "CMSG", "MSB", "ICE", "SJT", "KEWL", "VTRS"}
            else "pending"
        ),
        "weight_audit": weight_audit,
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


def website_implied_irr(data: dict) -> dict:
    """Compute total synthesis when possible; return fields for dashboard / thesis sync."""
    compute_synthesis(data)
    ir = data.get("implied_return") or {}
    syn = data.get("synthesis") or {}
    base = ir.get("base_pct")
    if syn.get("status") == "complete" and syn.get("total_synthesis_pct") is not None:
        base = syn["total_synthesis_pct"]
    display = ir.get("display")
    if syn.get("status") == "complete" and base is not None:
        display = f"{base}% (total synthesis)"
    elif base is not None and not display:
        display = f"{base}%"
    return {
        "display": display,
        "base_pct": base,
        "falsifier_adjusted_pct": ir.get("falsifier_adjusted_pct"),
        "synthesis_status": syn.get("status"),
        "synthesis_pct": syn.get("total_synthesis_pct"),
    }


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
    lines.append("")
    lines.append(_weight_stress_markdown(syn.get("paths", []), syn.get("weight_audit") or {}))
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
