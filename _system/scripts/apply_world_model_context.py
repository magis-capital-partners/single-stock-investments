#!/usr/bin/env python3
"""Apply World Model context to valuation.json (context only).

Reads dashboard/data/world_model.json (or rebuilds strip digests from artifacts),
writes `world_model_context` on each ticker's valuation.json + evidence snippet.

  python _system/scripts/apply_world_model_context.py ICE
  python _system/scripts/apply_world_model_context.py --all

Guardrails:
- world_model_context.in_base_irr stays false unless human already set true.
- Never edits inputs, scenarios, implied_return, or promotion without preserving.
- Fail / Superorg gaps → optional review queue via --queue-reviews.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import predictability as pred  # noqa: E402
import world_model_common as wm  # noqa: E402

TODAY = date.today().isoformat()
REVIEWS = wm.ROOT / "_system" / "reviews" / "pending"


def load_strip() -> dict:
    hot = wm.load_json(wm.DASHBOARD_WORLD_MODEL) or {}
    strip = hot.get("strip") if isinstance(hot, dict) else None
    if isinstance(strip, dict) and strip.get("industry_nodes") is not None:
        return strip
    # Fallback: assemble from artifacts without full KPI collect
    from build_world_model_snapshot import (  # noqa: WPS433
        load_expert_horizons,
        load_industry_nodes,
        load_prediction_cards,
        load_superorg_digests,
    )

    return {
        "as_of": TODAY,
        "label": "unknown",
        "broken": [],
        "stale": [],
        "prediction_cards": load_prediction_cards(),
        "superorgs": load_superorg_digests(),
        "expert_horizons": load_expert_horizons(),
        "industry_nodes": load_industry_nodes(),
        "disclaimer": "Context only. Does not auto-rewrite Lawrence base IRR.",
    }


def tickers_from_strip(strip: dict) -> set[str]:
    out: set[str] = set()
    for n in strip.get("industry_nodes") or []:
        for t in n.get("linked_tickers") or []:
            out.add(str(t).upper())
    for row in (strip.get("broken") or []) + (strip.get("stale") or []):
        if row.get("ticker"):
            out.add(str(row["ticker"]).upper())
    for path in wm.ROOT.glob("*/research/kpi_ledger.json"):
        out.add(path.parent.parent.name.upper())
    return out


def build_context(ticker: str, strip: dict, existing: dict | None) -> dict:
    t = ticker.upper()
    industries = []
    theme_ids: list[str] = []

    # Industries attach only when the ticker is explicitly linked on the node.
    for n in strip.get("industry_nodes") or []:
        linked = {str(x).upper() for x in (n.get("linked_tickers") or [])}
        if t not in linked:
            continue
        industries.append({
            "node_id": n.get("node_id"),
            "label": n.get("label"),
            "kind": n.get("kind") or "thesis",
            "checklist": n.get("checklist"),
        })
        for tid in n.get("linked_theme_ids") or []:
            if tid not in theme_ids:
                theme_ids.append(tid)

    # Theme ids from holdings_themes (for prediction cards) — do not invent industries.
    ht = wm.load_json(wm.ROOT / "_system" / "portfolio" / "holdings_themes.json") or {}
    for tid, meta in (ht.get("themes") or {}).items():
        ticks = meta.get("tickers") or []
        if "*" in ticks or t in {str(x).upper() for x in ticks}:
            if tid not in theme_ids:
                theme_ids.append(tid)

    cards = []
    for c in strip.get("prediction_cards") or []:
        if c.get("theme_id") in theme_ids:
            cards.append({
                "theme_id": c.get("theme_id"),
                "phase_transition": c.get("phase_transition"),
                "regulatory": c.get("regulatory"),
                "recursive": c.get("recursive"),
                "tam_magnetism": c.get("tam_magnetism"),
            })

    kpi_fails = [
        {
            "kpi_id": r.get("kpi_id"),
            "status": r.get("status") or "fail",
            "binds_to": r.get("binds_to"),
            "label": r.get("label"),
        }
        for r in (strip.get("broken") or [])
        if str(r.get("ticker") or "").upper() == t
    ]
    kpi_stale = [
        {"kpi_id": r.get("kpi_id"), "binds_to": r.get("binds_to")}
        for r in (strip.get("stale") or [])
        if str(r.get("ticker") or "").upper() == t
    ]

    superorg_gaps = []
    for s in strip.get("superorgs") or []:
        st = str(s.get("ticker") or "").upper()
        role = s.get("role") or ""
        linked = False
        if st == t:
            linked = True
        elif role in ("demand_proxy", "demand_side") and any(
            i.get("node_id") in ("hyperscaler_cloud", "ai_power", "agi")
            for i in industries
        ):
            linked = True
        if not linked:
            continue
        pillars = s.get("pillars") or {}
        if isinstance(pillars, dict):
            for name, status in pillars.items():
                st_val = status if isinstance(status, str) else (status or {}).get("status")
                if st_val in ("gap", "fail", "weak", "missing", "partial"):
                    superorg_gaps.append({
                        "org_id": s.get("org_id"),
                        "pillar": name,
                        "status": st_val,
                    })
        elif isinstance(pillars, list):
            for p in pillars:
                if isinstance(p, dict) and p.get("status") in (
                    "gap", "fail", "weak", "missing", "partial"
                ):
                    superorg_gaps.append({
                        "org_id": s.get("org_id"),
                        "pillar": p.get("pillar") or p.get("name"),
                        "status": p.get("status"),
                    })

    horizon_convergence = {}
    for h in strip.get("expert_horizons") or []:
        domain = h.get("domain")
        for n in industries:
            # match via industry files
            pass
        # attach if any industry for ticker lists the domain
        for path in wm.INDUSTRY_DIR.glob("*.json"):
            node = wm.load_json(path) or {}
            if t not in {str(x).upper() for x in (node.get("linked_tickers") or [])}:
                continue
            if domain in (node.get("linked_horizon_domains") or []):
                horizon_convergence[domain] = {
                    "convergence": h.get("convergence"),
                    "years_ahead_delta": h.get("years_ahead_delta"),
                    "latest": h.get("latest"),
                }

    existing = existing or {}
    promotion = existing.get("promotion")
    in_base = bool(existing.get("in_base_irr"))

    # Magis context never reaches P4 (house valuation). Horizons demote date claims to P0.
    pred_class = "P3_oriented"
    if horizon_convergence and not industries and not cards:
        pred_class = "P0_ill_defined"
    elif any(
        (h or {}).get("predictability_class") == "P0_ill_defined"
        for h in (horizon_convergence or {}).values()
        if isinstance(h, dict)
    ):
        # Keep ticker context at P3 for thesis hygiene; horizon dates stay P0 in strip.
        pred_class = "P3_oriented"
    strip_ceiling = strip.get("claim_ceiling")
    if strip_ceiling:
        pred_class = pred.min_class(pred_class, strip_ceiling)

    return {
        "as_of": strip.get("as_of") or TODAY,
        "strip_label": strip.get("label"),
        "predictability_class": pred_class,
        "claim_ceiling": strip.get("claim_ceiling"),
        "industry_node_ids": [i.get("node_id") for i in industries],
        "industries": industries,
        "theme_ids": theme_ids,
        "prediction_cards": cards,
        "kpi_fails": kpi_fails,
        "kpi_stale": kpi_stale,
        "superorg_gaps": superorg_gaps,
        "horizon_convergence": horizon_convergence,
        "in_base_irr": in_base,
        "promotion": promotion,
        "disclaimer": (
            "Context only. World Model fails and Superorg gaps open diligence; "
            "they do not rewrite universal contracts, IC packets, or human_decision.json. "
            f"Magis claim class: {pred_class}. Promotion template: "
            "_system/reviews/pending/world_model_promote_{TICKER}_{date}.md."
        ),
        "human_review_required": bool(kpi_fails or superorg_gaps),
    }


def write_snippet(ticker: str, ctx: dict) -> Path:
    research = wm.ROOT / ticker / "research" / "evidence"
    research.mkdir(parents=True, exist_ok=True)
    path = research / f"world_model_context_{TODAY}.md"
    lines = [
        f"# {ticker} — World Model context ({ctx.get('as_of', TODAY)})",
        "",
        f"> {ctx.get('disclaimer', '')}",
        "",
        f"**Strip label:** {ctx.get('strip_label')} · **Magis class:** "
        f"`{ctx.get('predictability_class') or 'P3_oriented'}` · **In base IRR:** "
        f"{'yes [HUMAN REVIEW]' if ctx.get('in_base_irr') else 'no (context)'}",
        "",
        "**Industries:** " + (", ".join(ctx.get("industry_node_ids") or []) or "none"),
        "",
        "**Themes:** " + (", ".join(ctx.get("theme_ids") or []) or "none"),
        "",
    ]
    if ctx.get("kpi_fails"):
        lines += ["**KPI fails (address in Risks / inversion):**", ""]
        for r in ctx["kpi_fails"]:
            binds = r.get("binds_to") or {}
            lines.append(
                f"- `{r.get('kpi_id')}` → `{binds.get('valuation_path') or 'stance-only'}` "
                f"[HUMAN REVIEW]"
            )
        lines.append("")
    if ctx.get("horizon_convergence"):
        lines += ["**Horizon convergence:**", ""]
        for dom, h in ctx["horizon_convergence"].items():
            lines.append(f"- {dom}: {h.get('convergence')} (delta {h.get('years_ahead_delta')})")
        lines.append("")
    if ctx.get("human_review_required"):
        lines.append(
            f"**Review queue:** see `_system/reviews/pending/world_model_review_{ticker}_{TODAY}.md` if queued."
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def queue_review(ticker: str, ctx: dict) -> Path | None:
    if not ctx.get("human_review_required"):
        return None
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path = REVIEWS / f"world_model_review_{ticker}_{TODAY}.md"
    lines = [
        f"# World Model review — {ticker} ({TODAY})",
        "",
        "Auto-opened because KPI fail and/or Superorg pillar gap.",
        "Context only — do **not** edit `implied_return` here.",
        "",
        "## KPI fails",
        "",
    ]
    for r in ctx.get("kpi_fails") or []:
        binds = r.get("binds_to") or {}
        lines.append(
            f"- [ ] `{r.get('kpi_id')}` binds `{binds.get('valuation_path') or 'n/a'}` — annotate assumption"
        )
    if not ctx.get("kpi_fails"):
        lines.append("- (none)")
    lines += ["", "## Superorg gaps", ""]
    for g in ctx.get("superorg_gaps") or []:
        lines.append(f"- [ ] {g}")
    if not ctx.get("superorg_gaps"):
        lines.append("- (none)")
    lines += [
        "",
        "## Promotion (optional)",
        "",
        f"If promoting into ledger/falsifiers only: copy `_system/reviews/templates/world_model_promote.md` → "
        f"`world_model_promote_{ticker}_{TODAY}.md` and get human OK before editing valuation paths.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def apply_one(ticker: str, strip: dict, *, write: bool, queue: bool) -> bool:
    val_path = wm.ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        print(f"{ticker}: skip (no valuation.json)")
        return False
    val = wm.load_json(val_path) or {}
    existing = val.get("world_model_context") if isinstance(val.get("world_model_context"), dict) else {}
    ctx = build_context(ticker, strip, existing)
    if not ctx.get("industry_node_ids") and not ctx.get("kpi_fails") and not ctx.get("theme_ids"):
        print(f"{ticker}: skip (no World Model binds)")
        return False
    if write:
        # Preserve IRR keys — only replace world_model_context
        val["world_model_context"] = ctx
        wm.write_json(val_path, val)
        snip = write_snippet(ticker, ctx)
        print(
            f"{ticker}: wrote world_model_context "
            f"({len(ctx.get('industry_node_ids') or [])} industries) -> {snip.name}"
        )
        if queue:
            q = queue_review(ticker, ctx)
            if q:
                print(f"{ticker}: queued {q.relative_to(wm.ROOT)}")
    else:
        print(
            f"{ticker}: dry-run industries={ctx.get('industry_node_ids')} "
            f"fails={len(ctx.get('kpi_fails') or [])} themes={ctx.get('theme_ids')}"
        )
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", help="Tickers to update")
    ap.add_argument("--all", action="store_true", help="All tickers linked from strip/industries/ledgers")
    ap.add_argument("--write", action="store_true", help="Write valuation.json")
    ap.add_argument(
        "--queue-reviews",
        action="store_true",
        help="Open pending review files when fails/gaps present",
    )
    args = ap.parse_args()
    strip = load_strip()
    if args.all:
        tickers = sorted(tickers_from_strip(strip))
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        ap.error("pass tickers or --all")
        return 2

    n = 0
    for t in tickers:
        if apply_one(t, strip, write=args.write, queue=args.queue_reviews):
            n += 1
    print(f"apply_world_model_context: {'wrote' if args.write else 'dry-run'} {n} ticker(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
