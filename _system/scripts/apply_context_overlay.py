#!/usr/bin/env python3
"""Inject thematic context indicators into tagged holdings' valuation.json.

Reads themes/manifest.json (fetch_theme_panel.py) + holdings_themes.json, then
writes a `context_overlay` block into each tagged ticker's valuation.json and a
human-readable snippet under research/evidence/ for deep-dive citation.

  python3 _system/scripts/apply_context_overlay.py            # all tagged tickers
  python3 _system/scripts/apply_context_overlay.py TPL LB     # subset

Guardrails:
- context_overlay is CONTEXT ONLY. Each indicator carries in_base_irr=false.
- A human may set an indicator's in_base_irr=true; that flag is preserved across
  refreshes. The script never sets it true and never edits `inputs`/IRR fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"
HOLDINGS_THEMES = ROOT / "_system" / "portfolio" / "holdings_themes.json"
TODAY = date.today().isoformat()

DISCLAIMER = (
    "Context only. Tailwinds inform stance and overlay sizing; they do not "
    "auto-inflate Lawrence base IRR. Promotion to base case requires [HUMAN REVIEW]."
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def theme_map() -> dict[str, list[str]]:
    """ticker -> [theme_id, ...]"""
    cfg = load_json(HOLDINGS_THEMES).get("themes") or {}
    out: dict[str, list[str]] = {}
    for theme_id, blk in cfg.items():
        for tk in blk.get("tickers") or []:
            out.setdefault(tk.upper(), []).append(theme_id)
    return out


def preserved_base_flags(existing: dict) -> dict[str, bool]:
    """Capture any human-set in_base_irr=true flags keyed by indicator id."""
    flags: dict[str, bool] = {}
    for theme in (existing.get("themes") or []):
        for ind in theme.get("indicators") or []:
            if ind.get("in_base_irr"):
                flags[ind.get("id")] = True
    return flags


def build_overlay(ticker: str, theme_ids: list[str], manifest: dict, existing: dict) -> dict | None:
    keep_flags = preserved_base_flags(existing)
    themes_out: list[dict] = []
    for theme_id in theme_ids:
        tdata = (manifest.get("themes") or {}).get(theme_id)
        if not tdata:
            continue
        indicators: list[dict] = []
        for sid, s in (tdata.get("series") or {}).items():
            indicators.append({
                "id": sid,
                "label": s.get("label"),
                "latest": s.get("latest"),
                "as_of": s.get("as_of"),
                "yoy_pct": s.get("yoy_pct"),
                "direction": s.get("direction"),
                "good_for": s.get("good_for"),
                "source": s.get("source"),
                "stale": s.get("stale"),
                "in_base_irr": bool(keep_flags.get(sid, False)),
            })
        if indicators:
            themes_out.append({"theme_id": theme_id, "label": tdata.get("label"), "indicators": indicators})
    if not themes_out:
        return None
    return {
        "as_of": manifest.get("as_of", TODAY),
        "disclaimer": DISCLAIMER,
        "themes": themes_out,
    }


def arrow(direction: str | None) -> str:
    return {"up": "up", "down": "down", "flat": "flat"}.get(direction or "flat", "flat")


def write_snippet(ticker: str, overlay: dict) -> Path:
    research = ROOT / ticker / "research" / "evidence"
    research.mkdir(parents=True, exist_ok=True)
    path = research / f"thematic_context_{TODAY}.md"
    lines = [
        f"# {ticker} - Thematic context ({overlay['as_of']})",
        "",
        f"> {overlay['disclaimer']}",
        "",
        "| Indicator | Latest | As of | YoY | Direction | In base IRR? |",
        "|-----------|--------|-------|-----|-----------|--------------|",
    ]
    for theme in overlay["themes"]:
        for ind in theme["indicators"]:
            yoy = f"{ind['yoy_pct']:+.1f}%" if isinstance(ind.get("yoy_pct"), (int, float)) else "n/a"
            latest = ind["latest"] if ind["latest"] is not None else "n/a"
            base = "yes [HUMAN REVIEW]" if ind.get("in_base_irr") else "no (context)"
            stale = " (stale)" if ind.get("stale") else ""
            lines.append(
                f"| {ind['label']} | {latest}{stale} | {ind.get('as_of') or 'n/a'} | {yoy} | {arrow(ind.get('direction'))} | {base} |"
            )
    lines += ["", f"Source panels: `_system/reference/market-data/themes/manifest.json`.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def apply_ticker(ticker: str, theme_ids: list[str], manifest: dict) -> str:
    vp = ROOT / ticker / "research" / "valuation.json"
    if not vp.exists():
        return f"skip {ticker} (no valuation.json)"
    val = json.loads(vp.read_text(encoding="utf-8"))
    existing = val.get("context_overlay") or {}
    overlay = build_overlay(ticker, theme_ids, manifest, existing)
    if overlay is None:
        return f"skip {ticker} (no theme data in manifest)"
    val["context_overlay"] = overlay
    vp.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    snippet = write_snippet(ticker, overlay)
    n = sum(len(t["indicators"]) for t in overlay["themes"])
    return f"OK {ticker}: {n} indicator(s) across {len(overlay['themes'])} theme(s) -> {snippet.relative_to(ROOT)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset of tickers (default: all tagged)")
    args = ap.parse_args()
    if not THEMES_MANIFEST.exists():
        print(f"No theme manifest at {THEMES_MANIFEST}; run fetch_theme_panel.py first.", file=sys.stderr)
        return 1
    manifest = load_json(THEMES_MANIFEST)
    tmap = theme_map()
    targets = [t.upper() for t in args.tickers] if args.tickers else sorted(tmap.keys())
    for tk in targets:
        themes = tmap.get(tk)
        if not themes:
            print(f"skip {tk} (not tagged in holdings_themes.json)")
            continue
        print(apply_ticker(tk, themes, manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
