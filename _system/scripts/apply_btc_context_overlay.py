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
SNOWBALL = ROOT / "dashboard" / "data" / "hk_snowball_model.json"
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


def _theme_spot(manifest: dict) -> tuple[float | None, str | None]:
    theme = (manifest.get("themes") or {}).get("btc_network_economics") or {}
    series = (theme.get("series") or {}).get("btc_spot_usd") or {}
    latest = series.get("latest")
    try:
        return (float(latest), series.get("as_of")) if latest is not None else (None, series.get("as_of"))
    except (TypeError, ValueError):
        return None, series.get("as_of")


def hauck_context(manifest: dict, snowball: dict) -> dict:
    cost_meta = manifest.get("btc_cost_of_production") or {}
    supply = (snowball.get("supply") or {}) if snowball else {}
    bands = supply.get("bands") or {}
    mixed = (supply.get("scenarios") or {}).get("mixed_base") or {}
    mixed_2028 = mixed.get("2028") or {}
    mixed_2032 = mixed.get("2032") or {}
    naive_2028 = ((supply.get("scenarios") or {}).get("naive_hk") or {}).get("2028") or {}
    spot, spot_as_of = _theme_spot(manifest)
    all_in = bands.get("all_in_usd") or cost_meta.get("latest_all_in")
    sota_roic = bands.get("sota_roic_usd") or cost_meta.get("latest_sota_roic")
    stance = supply.get("miner_stance") or {}
    if not stance and (spot or all_in):
        sys.path.insert(0, str(SCRIPTS))
        import btc_cost_of_production as cop  # noqa: WPS433

        stance = cop.miner_stance(spot, all_in, sota_roic)
    return {
        "spot_usd": spot,
        "spot_as_of": spot_as_of,
        "hauck_all_in_usd": all_in,
        "hauck_all_in_as_of": cost_meta.get("latest_date") or snowball.get("as_of"),
        "fleet_jth": (supply.get("assumptions") or {}).get("efficiency_j_th") or cost_meta.get("latest_fleet_jth"),
        "electricity_only_usd": bands.get("electricity_only_usd") or cost_meta.get("latest_electricity_only"),
        "sota_cash_usd": bands.get("sota_cash_usd") or cost_meta.get("latest_sota_cash"),
        "sota_roic_usd": sota_roic,
        "premium_usd": bands.get("premium_usd"),
        "mixed_2028_all_in_usd": mixed_2028.get("all_in_usd"),
        "mixed_2032_all_in_usd": mixed_2032.get("all_in_usd"),
        "naive_2028_all_in_usd": naive_2028.get("all_in_usd"),
        "miner_stance": stance.get("label"),
        "miner_stance_plain_english": stance.get("plain_english"),
        "in_base_irr": False,
        "source": "asic vintage mix + $0.05/kWh HK-comparable case",
    }


def build_btc_overlay(ticker: str, meta: dict, manifest: dict, snowball: dict) -> dict:
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
            elif sid == "btc_spot_usd":
                mining_ctx["spot_usd"] = s.get("latest")
        if indicators:
            themes_out.append({
                "theme_id": theme_id,
                "label": tdata.get("label"),
                "indicators": indicators,
            })
    exposure = meta.get("crypto_exposure", "treasury")
    if exposure != "stablecoin":
        mining_ctx.update(hauck_context(manifest, snowball))
    overlay = {
        "as_of": manifest.get("as_of", TODAY),
        "crypto_exposure": exposure,
        "status": "partial" if themes_out else "pending",
        "disclaimer": DISCLAIMER,
        "in_base_irr": False,
        "themes": themes_out,
        "mining_economics_context": {
            **mining_ctx,
        },
        "in_model": {},
        "not_in_model_requires_refresh": [
            "live_btc_spot_in_price_input",
            "hashprice_vs_fleet_breakeven",
            "post_halving_subsidy_schedule",
            "hauck_cost_floor_not_in_lawrence_base",
        ],
    }
    return overlay


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


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
    ctx = overlay.get("mining_economics_context") or {}
    if ctx.get("hauck_all_in_usd") is not None:
        lines += [
            "",
            "## Hauck reconstructed cost floor",
            "",
            "ASIC vintage mix at $0.05/kWh and 60% power share. Not US residential power. Not in Lawrence base IRR.",
            "",
            "| Band | USD |",
            "|------|-----|",
            f"| Spot | {_fmt_usd(ctx.get('spot_usd'))} |",
            f"| Electricity only | {_fmt_usd(ctx.get('electricity_only_usd'))} |",
            f"| Average-fleet all-in | {_fmt_usd(ctx.get('hauck_all_in_usd'))} |",
            f"| SOTA cash | {_fmt_usd(ctx.get('sota_cash_usd'))} |",
            f"| SOTA + 25% ROIC | {_fmt_usd(ctx.get('sota_roic_usd'))} |",
            f"| Mixed 2028 floor | {_fmt_usd(ctx.get('mixed_2028_all_in_usd'))} |",
            f"| Mixed 2032 floor | {_fmt_usd(ctx.get('mixed_2032_all_in_usd'))} |",
            f"| Naive 2× 2028 (labeled scenario) | {_fmt_usd(ctx.get('naive_2028_all_in_usd'))} |",
            "",
            f"**Miner stance:** {ctx.get('miner_stance') or 'n/a'}. {ctx.get('miner_stance_plain_english') or ''}",
            "",
        ]
    lines += ["", "Source: `_system/reference/market-data/crypto/manifest.json` and `dashboard/data/hk_snowball_model.json`.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def apply_ticker(ticker: str, manifest: dict, holdings: dict[str, dict], snowball: dict) -> str:
    tk = ticker.upper()
    meta = holdings.get(tk)
    if not meta:
        return f"skip {tk} (not in holdings_crypto.json)"
    overlay = build_btc_overlay(tk, meta, manifest, snowball)
    vp = ROOT / tk / "research" / "valuation.json"
    wrote_val = False
    if vp.exists():
        val = json.loads(vp.read_text(encoding="utf-8"))
        val["btc_overlay"] = overlay
        vp.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
        wrote_val = True
    snippet = write_snippet(tk, overlay)
    n = sum(len(t.get("indicators") or []) for t in overlay.get("themes") or [])
    val_note = "valuation.json" if wrote_val else "snippet only (no valuation.json)"
    return f"OK {tk}: {n} crypto indicator(s) -> {snippet.relative_to(ROOT)} ({val_note})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (default: all crypto-tagged)")
    args = ap.parse_args()
    if not CRYPTO_MANIFEST.exists():
        print("Run fetch_crypto_panel.py first.", file=sys.stderr)
        return 1
    manifest = load_json(CRYPTO_MANIFEST)
    snowball = load_json(SNOWBALL)
    holdings = crypto_holdings()
    targets = [t.upper() for t in args.tickers] if args.tickers else sorted(holdings.keys())
    for tk in targets:
        print(apply_ticker(tk, manifest, holdings, snowball))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
