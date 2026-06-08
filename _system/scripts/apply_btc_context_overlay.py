#!/usr/bin/env python3
"""Inject btc_overlay / stablecoin context into crypto-tagged holdings."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CRYPTO_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "crypto" / "manifest.json"
HOLDINGS_CRYPTO = ROOT / "_system" / "portfolio" / "holdings_crypto.json"
TODAY = date.today().isoformat()

DISCLAIMER = (
    "Context only. Crypto and mining metrics inform stance and overlays; they do not "
    "auto-inflate Lawrence base IRR. Promotion to base case requires [HUMAN REVIEW]."
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def crypto_holdings() -> dict[str, dict]:
    return (load_json(HOLDINGS_CRYPTO).get("holdings") or {})


def build_btc_overlay(ticker: str, meta: dict, manifest: dict) -> dict:
    themes_out: list[dict] = []
    mining_ctx: dict = {}
    for theme_id in meta.get("themes") or []:
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
                "source": s.get("source"),
                "stale": s.get("stale"),
                "in_base_irr": False,
            })
            if sid == "btc_hash_rate_eh":
                mining_ctx["hash_rate_eh"] = s.get("latest")
            elif sid == "btc_difficulty":
                mining_ctx["difficulty"] = s.get("latest")
            elif sid == "btc_hashprice_usd_ph_day":
                mining_ctx["hashprice_usd_ph_day"] = s.get("latest")
            elif sid == "btc_breakeven_power_30jth":
                mining_ctx["breakeven_power_usd_kwh_30jth"] = s.get("latest")
            elif sid == "btc_avg_fee_per_block_usd":
                mining_ctx["avg_fee_per_block_usd"] = s.get("latest")
        if indicators:
            themes_out.append({
                "theme_id": theme_id,
                "label": tdata.get("label"),
                "indicators": indicators,
            })
    exposure = meta.get("crypto_exposure", "treasury")
    overlay = {
        "as_of": manifest.get("as_of", TODAY),
        "crypto_exposure": exposure,
        "status": "partial" if themes_out else "pending",
        "disclaimer": DISCLAIMER,
        "in_base_irr": False,
        "themes": themes_out,
        "mining_economics_context": {
            **mining_ctx,
            "source": "mempool.space + computed",
        },
        "in_model": {},
        "not_in_model_requires_refresh": [
            "live_btc_spot_in_price_input",
            "hashprice_vs_fleet_breakeven",
            "post_halving_subsidy_schedule",
        ],
    }
    return overlay


def write_snippet(ticker: str, overlay: dict) -> Path:
    research = ROOT / ticker / "research" / "evidence"
    research.mkdir(parents=True, exist_ok=True)
    path = research / f"crypto_context_{TODAY}.md"
    lines = [
        f"# {ticker} - Crypto economics context ({overlay['as_of']})",
        "",
        f"> {overlay['disclaimer']}",
        "",
        f"**Exposure type:** {overlay.get('crypto_exposure')}",
        "",
        "| Indicator | Latest | As of | YoY | Direction | In base IRR? |",
        "|-----------|--------|-------|-----|-----------|--------------|",
    ]
    for theme in overlay.get("themes") or []:
        for ind in theme.get("indicators") or []:
            yoy = f"{ind['yoy_pct']:+.1f}%" if isinstance(ind.get("yoy_pct"), (int, float)) else "n/a"
            latest = ind["latest"] if ind.get("latest") is not None else "fetch failed"
            if ind.get("stale") and ind.get("latest") is None:
                latest = "fetch failed (stale)"
            base = "no (context)"
            lines.append(
                f"| {ind['label']} | {latest} | {ind.get('as_of') or 'n/a'} | {yoy} | {ind.get('direction') or 'flat'} | {base} |"
            )
    lines += ["", f"Source: `_system/reference/market-data/crypto/manifest.json`.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def apply_ticker(ticker: str, manifest: dict, holdings: dict[str, dict]) -> str:
    tk = ticker.upper()
    meta = holdings.get(tk)
    if not meta:
        return f"skip {tk} (not in holdings_crypto.json)"
    vp = ROOT / tk / "research" / "valuation.json"
    if not vp.exists():
        return f"skip {tk} (no valuation.json)"
    val = json.loads(vp.read_text(encoding="utf-8"))
    overlay = build_btc_overlay(tk, meta, manifest)
    val["btc_overlay"] = overlay
    vp.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    snippet = write_snippet(tk, overlay)
    n = sum(len(t.get("indicators") or []) for t in overlay.get("themes") or [])
    return f"OK {tk}: {n} crypto indicator(s) -> {snippet.relative_to(ROOT)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (default: all crypto-tagged)")
    args = ap.parse_args()
    if not CRYPTO_MANIFEST.exists():
        print("Run fetch_crypto_panel.py first.", file=sys.stderr)
        return 1
    manifest = load_json(CRYPTO_MANIFEST)
    holdings = crypto_holdings()
    targets = [t.upper() for t in args.tickers] if args.tickers else sorted(holdings.keys())
    for tk in targets:
        print(apply_ticker(tk, manifest, holdings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
