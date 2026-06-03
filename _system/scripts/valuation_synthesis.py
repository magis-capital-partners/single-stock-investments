#!/usr/bin/env python3
"""Build total synthesis IRR from all valuation paths + third-party + qualitative factors.

Called from marvin_valuation.py --write after overlay_results are computed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import sys

sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from lawrence_horizon import LAWRENCE_HORIZON_YEARS, SYNTHESIS_LABEL  # noqa: E402

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
        "why": f"Answers a different question (NAV convergence) than {LAWRENCE_HORIZON_YEARS}yr cash-flow IRR; capped weight to avoid theory conflation.",
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


# Auto-template path ids (safe to replace when estimates.external / blended_best exist)
TEMPLATE_PATH_IDS = frozenset(
    {
        "filing_falsifier",
        "theory_implied",
        "scenario_bear",
        "scenario_bull",
        "segment_implied",
        "nav_overlay_payoff",
        "third_party_context",
    }
)


def _has_custom_synthesis_paths(paths: list[dict]) -> bool:
    """Human-curated synthesis (e.g. VTRS Rosen weights) must not be replaced."""
    return any(p.get("id") not in TEMPLATE_PATH_IDS for p in paths)


def _third_party_proxies_bull(paths: list[dict], data: dict) -> bool:
    """Detect instrumentalist third_party_context row (bull proxy or stale upside)."""
    legacy = data.get("results_lawrence_legacy") or data.get("results") or {}
    bull = (legacy.get("bull") or {}).get("return_pct")
    for p in paths:
        if p.get("id") != "third_party_context":
            continue
        notes = (p.get("notes") or "").lower()
        if "proxy" in notes and "bull" in notes:
            return True
        if bull is not None and p.get("return_pct") == bull:
            return True
        if bull is not None and p.get("return_pct") is not None:
            if abs(float(p["return_pct"]) - float(bull)) < 0.25:
                return True
    return False


def _should_rebuild_paths_from_estimates(paths: list[dict], data: dict) -> bool:
    est = data.get("estimates") or {}
    if not (est.get("blended_best") or est.get("external") or est.get("marvin_floor")):
        return False
    if not paths:
        return True
    if any(p.get("id") == "third_party_context" for p in paths):
        return True
    return _third_party_proxies_bull(paths, data)


def _external_return_pct(ext: dict) -> float | None:
    for key in (
        "return_pct_7yr",
        "return_pct",
        "return_pct_approx",
        "return_pct_catalyst_capped",
    ):
        if ext.get(key) is not None:
            return _round_pct(float(ext[key]))
    return None


def _catalyst_return_pct(cid: str, cs: dict, price: float | None) -> float | None:
    if cs.get("return_pct") is not None:
        return _round_pct(float(cs["return_pct"]))
    payoff = cs.get("payoff")
    years = cs.get("years")
    if payoff and years and price and price > 0:
        return _round_pct(((float(payoff) / float(price)) ** (1 / float(years)) - 1) * 100)
    return None


def _paths_from_estimates(data: dict) -> list[dict]:
    """Build synthesis paths from estimates.* (triangulated blend, not bull proxy)."""
    est = data.get("estimates") or {}
    paths: list[dict] = []
    mf = est.get("marvin_floor") or {}
    if mf.get("return_pct") is not None:
        paths.append(
            {
                "id": "marvin_floor",
                "label": "Marvin floor (filings stress)",
                "source": "estimates.marvin_floor",
                "return_pct": _round_pct(float(mf["return_pct"])),
                "weight": 0.25,
                "type": "numeric",
                "epistemic_tier": "A (primary filings)",
                "weight_why": "Stress floor from primary docs; anchors pessimistic bound.",
                "hard_to_vary": "yes",
            }
        )
    bb = est.get("blended_best") or {}
    if bb.get("return_pct") is not None:
        ps = bb.get("per_share")
        src = f"estimates.blended_best @ ${ps}/sh" if ps is not None else "estimates.blended_best"
        paths.append(
            {
                "id": "blended_best_primary",
                "label": "Blended best estimate (Marvin + external)",
                "source": src,
                "return_pct": _round_pct(float(bb["return_pct"])),
                "weight": 0.5,
                "type": "numeric",
                "notes": (bb.get("weights") or bb.get("notes") or "")[:120],
                "epistemic_tier": "B (triangulated best judgment)",
                "weight_why": "Primary holding-period path after partial credit for approved external normalization.",
                "hard_to_vary": "yes",
            }
        )
    for ext in est.get("external") or []:
        ret = _external_return_pct(ext)
        if ret is None:
            continue
        sid = ext.get("source_id") or "external"
        approved = (ext.get("status") or "").lower() == "approved"
        paths.append(
            {
                "id": f"external_{sid}",
                "label": (ext.get("source") or sid)[:60],
                "source": ext.get("path") or f"estimates.external[{sid}]",
                "return_pct": ret,
                "weight": 0.12 if approved else 0.08,
                "type": "numeric",
                "notes": (ext.get("notes") or "")[:100],
                "epistemic_tier": "C (approved external)" if approved else "D (external context)",
                "weight_why": "Triangulation lane; capped when already in blended_best to avoid double-count.",
                "hard_to_vary": "partial",
            }
        )
    price = (data.get("inputs") or {}).get("price")
    for cid, cs in (data.get("catalyst_scenarios") or {}).items():
        ret = _catalyst_return_pct(cid, cs, float(price) if price else None)
        if ret is None:
            continue
        paths.append(
            {
                "id": f"catalyst_{cid}",
                "label": f"Catalyst: {cid.replace('_', ' ')}",
                "source": f"catalyst_scenarios.{cid}",
                "return_pct": ret,
                "weight": 0.1,
                "type": "numeric",
                "notes": (cs.get("notes") or "")[:100],
                "epistemic_tier": "D (event path)",
                "weight_why": "Capped catalyst; not Lawrence operating base.",
                "hard_to_vary": "no",
            }
        )
    legacy = data.get("results_lawrence_legacy") or data.get("results") or {}
    for case, w in (("bear", 0.05), ("bull", 0.05)):
        pct = (legacy.get(case) or {}).get("return_pct")
        if pct is not None:
            paths.append(
                {
                    "id": f"scenario_{case}",
                    "label": f"{case.capitalize()} scenario (Lawrence envelope)",
                    "source": f"scenarios.{case}",
                    "return_pct": _round_pct(float(pct)),
                    "weight": w,
                    "type": "numeric",
                    "epistemic_tier": "C (scenario envelope)",
                    "weight_why": "Sensitivity only; not a competing explanation of base mechanics.",
                    "hard_to_vary": "yes",
                }
            )
    if not paths:
        return _default_paths(data)
    return paths


def _sync_path_returns(paths: list[dict], data: dict) -> list[dict]:
    """Refresh numeric returns on preserved paths without changing weights or labels."""
    est = data.get("estimates") or {}
    mf = est.get("marvin_floor") or {}
    bb = est.get("blended_best") or {}
    legacy = data.get("results_lawrence_legacy") or data.get("results") or {}
    base_ret = (legacy.get("base") or {}).get("return_pct")
    ir = data.get("implied_return") or {}
    fa = ir.get("falsifier_adjusted_pct")
    price = (data.get("inputs") or {}).get("price")
    ext_by_id = {e.get("source_id"): e for e in est.get("external") or [] if e.get("source_id")}

    out: list[dict] = []
    for p in paths:
        pid = p.get("id", "")
        updated = dict(p)
        if pid == "marvin_floor" and mf.get("return_pct") is not None:
            updated["return_pct"] = _round_pct(float(mf["return_pct"]))
        elif pid in ("blended_best_primary", "blended_lawrence_primary") and bb.get("return_pct") is not None:
            updated["return_pct"] = _round_pct(float(bb["return_pct"]))
        elif pid == "blended_lawrence_primary" and base_ret is not None:
            updated["return_pct"] = _round_pct(float(base_ret))
        elif pid == "filing_falsifier" and fa is not None:
            updated["return_pct"] = _round_pct(float(fa))
        elif pid.startswith("external_"):
            sid = pid.replace("external_", "", 1)
            ext = ext_by_id.get(sid)
            if ext:
                ret = _external_return_pct(ext)
                if ret is not None:
                    updated["return_pct"] = ret
        elif pid.startswith("catalyst_"):
            cid = pid.replace("catalyst_", "", 1)
            cs = (data.get("catalyst_scenarios") or {}).get(cid) or {}
            ret = _catalyst_return_pct(cid, cs, float(price) if price else None)
            if ret is not None:
                updated["return_pct"] = ret
        elif pid == "rosen_operating_7yr":
            ext = ext_by_id.get("sohn_rosen_vtrs") or (est.get("external") or [{}])[0]
            ret = _external_return_pct(ext) if ext else None
            if ret is not None:
                updated["return_pct"] = ret
        elif pid == "idorsia_catalyst_capped":
            ext = ext_by_id.get("sohn_rosen_vtrs") or {}
            if ext.get("return_pct_catalyst_capped") is not None:
                updated["return_pct"] = _round_pct(float(ext["return_pct_catalyst_capped"]))
        elif pid.startswith("scenario_"):
            case = pid.replace("scenario_", "")
            pct = (legacy.get(case) or {}).get("return_pct")
            if pct is not None:
                updated["return_pct"] = _round_pct(float(pct))
        out.append(updated)
    return out


def resolve_synthesis_paths(data: dict) -> list[dict]:
    """Choose synthesis paths: preserve human blends, else estimates-driven, else template."""
    existing = data.get("synthesis") or {}
    paths = list(existing.get("paths") or [])
    est = data.get("estimates") or {}
    has_estimates = bool(est.get("marvin_floor") or est.get("blended_best") or est.get("external"))

    if existing.get("lock_paths") or _has_custom_synthesis_paths(paths):
        return _sync_path_returns(paths, data) if paths else _paths_from_estimates(data)

    if _should_rebuild_paths_from_estimates(paths, data):
        return _sync_path_returns(_paths_from_estimates(data), data)

    if not paths:
        paths = _default_paths(data)
    elif has_estimates:
        paths = _sync_path_returns(paths, data)
    return paths


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
        years = LAWRENCE_HORIZON_YEARS
        nav_irr = ((overlay_nav / price) ** (1 / years) - 1) * 100
        paths.append(
            {
                "id": "nav_overlay_payoff",
                "label": f"NAV overlay dated payoff ({LAWRENCE_HORIZON_YEARS}yr to overlay base)",
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


def post_optionality_valuation_pass(data: dict) -> None:
    """After refresh_optionality_valuation: sync synthesis paths; keep Lawrence base for yield_curve."""
    from optionality_evidence_common import lawrence_base_return_pct, synthesis_in_dive

    method = data.get("method", "")
    base_lawrence = lawrence_base_return_pct(data)
    if base_lawrence is not None:
        ir = data.setdefault("implied_return", {})
        ir["base_pct"] = base_lawrence
        ir["label"] = "annualized return"
        ir["display"] = f"{base_lawrence:.2f}% (base)"

    if method == "yield_curve" and not synthesis_in_dive(data):
        data["synthesis"] = {
            "status": "n/a",
            "reason": "Lawrence yield_curve is stance gate; set evidence_refresh.synthesis_in_dive true to enable capstone blend",
            "human_approval": "n/a",
        }
        return

    existing = data.get("synthesis") or {}
    paths = resolve_synthesis_paths(data)
    gate = data.get("optionality_gate") or {}
    overlay_nav = gate.get("overlay_nav_per_share")
    price = (data.get("inputs") or {}).get("price")
    for i, p in enumerate(paths):
        if p.get("id") == "nav_overlay_payoff" and overlay_nav and price and overlay_nav > 0:
            years = LAWRENCE_HORIZON_YEARS
            nav_irr = ((float(overlay_nav) / float(price)) ** (1 / years) - 1) * 100
            paths[i] = {
                **p,
                "source": f"nav_overlay ~${overlay_nav}/sh vs price ${price}",
                "return_pct": _round_pct(nav_irr),
            }
            break
    data["synthesis"] = {**existing, "paths": paths}
    compute_synthesis(data)


def compute_synthesis(data: dict) -> dict:
    """Populate data['synthesis'] and update implied_return when complete."""
    from optionality_evidence_common import synthesis_in_dive

    if data.get("method") == "yield_curve" and not synthesis_in_dive(data):
        data["synthesis"] = {
            "status": "n/a",
            "reason": "Lawrence yield_curve stance gate",
            "human_approval": "n/a",
        }
        return data["synthesis"]

    ticker = data.get("ticker", "")
    existing = data.get("synthesis") or {}
    raw_paths = resolve_synthesis_paths(data)
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
    if data.get("method") != "yield_curve":
        ir["base_pct"] = total
        ir["label"] = SYNTHESIS_LABEL
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


def _headline_pct(pct: float | int) -> str:
    if isinstance(pct, float) and pct == int(pct):
        return str(int(pct))
    if isinstance(pct, float):
        return f"{pct:.2f}".rstrip("0").rstrip(".")
    return str(pct)


def has_blended_estimates(val: dict) -> bool:
    est = val.get("estimates") or {}
    return bool(est.get("marvin_floor") or est.get("blended_best") or est.get("external"))


def blended_estimate_markdown(val: dict) -> str:
    """Render ## Blended estimate from valuation.json estimates (repeatable refresh)."""
    est = val.get("estimates") or {}
    if not has_blended_estimates(val):
        return ""
    syn = val.get("synthesis") or {}
    headline = syn.get("total_synthesis_pct") or (val.get("implied_return") or {}).get("base_pct")
    headline_s = _headline_pct(headline) if headline is not None else "n/a"
    stance = (val.get("stance_proposal") or {}).get("suggested", "watch")
    price = (val.get("inputs") or {}).get("price", "?")

    lines = [
        "## Blended estimate (best judgment)",
        "",
        "| Lens | Owner cash (or metric) | Return / horizon | Stance hint |",
        "|------|------------------------|------------------|-------------|",
    ]
    mf = est.get("marvin_floor") or {}
    if mf:
        ret = mf.get("return_pct")
        ret_s = f"**{ret}%** / {LAWRENCE_HORIZON_YEARS}yr" if ret is not None else "n/a"
        ps = mf.get("per_share")
        cash = f"**${ps}/sh**" if ps is not None else "—"
        lines.append(f"| Marvin floor | {cash} | {ret_s} | stress |")
    for ext in est.get("external") or []:
        ret = _external_return_pct(ext)
        ret_s = f"**{ret}%** / {LAWRENCE_HORIZON_YEARS}yr" if ret is not None else "context"
        ps = ext.get("per_share_normalized") or ext.get("per_share")
        cash = f"**${ps}/sh**" if ps is not None else "—"
        src = (ext.get("source") or ext.get("source_id") or "External")[:50]
        lines.append(f"| {src} | {cash} | {ret_s} | external |")
    bb = est.get("blended_best") or {}
    if bb:
        ret = bb.get("return_pct")
        ret_s = f"**{ret}%** / {LAWRENCE_HORIZON_YEARS}yr operating" if ret is not None else "n/a"
        ps = bb.get("per_share")
        cash = f"**${ps}/sh**" if ps is not None else "—"
        lines.append(f"| Blended operating | {cash} | {ret_s} | — |")
    lines.append(
        f"| **Total synthesis (headline)** | blended path | **{headline_s}%** / {LAWRENCE_HORIZON_YEARS}yr | **{stance}** |"
    )
    lines.append("")
    weights = bb.get("weights") or ""
    syn_paths = syn.get("paths") or []
    if syn_paths:
        wparts = [
            f"**{int((p.get('weight') or 0) * 100)}%** {p.get('label', p.get('id', ''))[:40]}"
            for p in syn_paths
            if p.get("return_pct") is not None
        ]
        if wparts:
            lines.append(f"**Weights (synthesis):** " + " · ".join(wparts[:6]) + ".")
    elif weights:
        lines.append(f"**Weights:** {weights}")
    if bb.get("notes"):
        lines.append("")
        lines.append(f"**Bridge:** {bb['notes']}")
    lines += [
        "",
        f"**Returns statement (blend):** We expect about **{headline_s}%** per year at **${price}** "
        f"(total synthesis headline; Marvin floor **{mf.get('return_pct', 'n/a')}%** on "
        f"**${mf.get('per_share', 'n/a')}/sh** for stress).",
        "",
    ]
    for ext in est.get("external") or []:
        sid = ext.get("source_id") or "external"
        lines.append(f"### {ext.get('source', sid)[:60]}")
        lines.append("")
        lines.append("| Claim | Marvin use in blend |")
        lines.append("|-------|---------------------|")
        notes = (ext.get("notes") or "See cross-check and primary path.")[:200]
        lines.append(f"| Summary | {notes} |")
        if ext.get("path"):
            lines.append(f"| Source | `{ext['path']}` (`{sid}`) |")
        lines.append("")
    return "\n".join(lines)


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
        f"| # | Source / lens | Type | Return ({LAWRENCE_HORIZON_YEARS}yr) | Weight | Role in synthesis |",
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
        f"**Returns statement (synthesis):** At today's price, we expect about **{t}%** per year over "
        f"{LAWRENCE_HORIZON_YEARS} years "
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
