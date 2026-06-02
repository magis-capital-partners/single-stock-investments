#!/usr/bin/env python3
"""Config-driven optionality / commodity NAV refresh (post marvin_valuation --write).

Reads valuation.json → evidence_refresh (type commodity_nav). Used by marvin_cloud_refresh.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from marvin_pipeline_common import has_evidence_refresh_config  # noqa: E402

TODAY = date.today().isoformat()


def irr(p0: float, payoff: float, years: float) -> float:
    if p0 <= 0 or years <= 0:
        return 0.0
    return round(100.0 * ((payoff / p0) ** (1.0 / years) - 1.0), 2)


def _spot_from_market_inputs(ticker: str, commodity: str, default: float) -> float:
    mi_path = ROOT / ticker / "research" / "market_inputs.json"
    if not mi_path.exists():
        return default
    mi = json.loads(mi_path.read_text(encoding="utf-8")).get("market_inputs") or {}
    return float((mi.get(commodity) or {}).get("spot") or default)


def refresh_commodity_nav(ticker: str, val: dict, cfg: dict) -> dict:
    inp = val.setdefault("inputs", {})
    price = float(inp.get("price", 0))
    book = float(inp.get("book_per_share", 0))
    shares = float(inp.get("shares_outstanding", 1))
    commodity = cfg.get("commodity", "copper")
    spot = _spot_from_market_inputs(ticker, commodity, float(inp.get(f"{commodity}_spot_usd_per_lb", 4.0)))

    royalty_cfg = cfg.get("royalty_usd_at_ref_lb") or {}
    ssi_royalty = float(royalty_cfg.get("amount", inp.get("copperwood_royalty_est_usd", 0)))
    ref_lb = float(royalty_cfg.get("ref_lb", 4.0))
    royalty_spot = round(ssi_royalty * (spot / ref_lb), 0) if ref_lb > 0 else ssi_royalty
    royalty_per_sh = royalty_spot / shares if shares else 0
    p_base = float(cfg.get("probability_pct", 35)) / 100.0

    lease_annual = float(cfg.get("lease_annual_usd", inp.get("lease_income_annual_usd", 0)))
    lease_cap_multiple = float(cfg.get("lease_cap_multiple", 10))
    lease_uplift = round(lease_annual * lease_cap_multiple / shares, 2) if shares else 0

    acreage_uplift = float(cfg.get("acreage_uplift_per_share", 0))
    cash_floor = float(cfg.get("cash_floor_per_share", 0))
    horizon = float(cfg.get("horizon_years", 7))
    mode = cfg.get("base_payoff_mode", "fixed_stance_gate")
    base_payoff = float(cfg.get("base_payoff", (val.get("scenarios") or {}).get("base", {}).get("payoff", 30)))
    bear_payoff = float(cfg.get("bear_payoff", (val.get("scenarios") or {}).get("bear", {}).get("payoff", 14)))
    overlay_slack = float(cfg.get("overlay_slack_per_share", 4.0))

    copperwood_uplift = round(royalty_per_sh * p_base, 2)
    economic_floor = round(book + lease_uplift + copperwood_uplift + acreage_uplift, 2)
    overlay_nav = round(economic_floor + cash_floor * 0.5, 2)
    overlay_payoff = round(book + lease_uplift + copperwood_uplift + acreage_uplift + overlay_slack, 2)
    overlay_irr = irr(price, overlay_payoff, horizon)

    val["as_of"] = TODAY
    inp[f"{commodity}_spot_usd_per_lb"] = spot
    inp["lease_income_annual_usd"] = lease_annual
    inp["copperwood_royalty_est_usd_at_spot"] = royalty_spot

    og = val.setdefault("optionality_gate", {})
    og["floor_metric"] = cfg.get("floor_metric", "nav_per_share")
    og["floor_value"] = economic_floor
    og["floor_pass"] = price < economic_floor * float(cfg.get("floor_premium_cap", 1.15))
    og["overlay_nav_per_share"] = overlay_nav
    if shares and price > 0:
        og["copperwood_option_yield_pct"] = round(100.0 * royalty_spot / (price * shares), 2)
    og["overlay_implied_return_pct"] = overlay_irr
    og["notes"] = (
        f"Economic floor ~${economic_floor}/sh (not GAAP book); spot {commodity} ${spot}/unit; "
        f"option yield ~{og.get('copperwood_option_yield_pct', 'n/a')}%"
    )

    nav_existing = val.get("nav_overlay") or {}
    gaap_block = nav_existing.get("gaap_vs_fair_value") or cfg.get("gaap_vs_fair_value") or {}
    val["nav_overlay"] = {
        "status": "complete",
        "as_of": TODAY,
        "gaap_vs_fair_value": gaap_block,
        "gaap_book_per_share": book,
        "economic_floor_per_share": economic_floor,
        "overlay_nav_per_share": overlay_nav,
        "method": cfg.get("nav_method", "probability_weighted"),
        "lines": [
            {"id": "gaap_book", "label": "GAAP equity per share", "per_share": book, "source": "filing"},
            {
                "id": "lease_cap",
                "label": "Lease run-rate capitalized",
                "per_share": lease_uplift,
                "source": f"[Assumption] {lease_cap_multiple}x on ~${lease_annual/1000:.0f}K/yr",
            },
            {
                "id": "production_pw",
                "label": f"Production royalty P={int(p_base*100)}% @ spot",
                "per_share": copperwood_uplift,
                "source": f"Scaled to spot ${spot}",
            },
            {"id": "acreage", "label": "Acreage / secondary option", "per_share": acreage_uplift, "source": "filing"},
        ],
        "premium_to_economic_floor_pct": round(100.0 * (price / economic_floor - 1.0), 1) if economic_floor else None,
        "notes": cfg.get("nav_notes", "Do not use GAAP book as dhando floor"),
    }

    val["overlay_options"] = {
        "lawrence_base": cfg.get("lawrence_base_note", "lease_income_only_zero_production_royalty"),
        "overlay_base_payoff_7yr": overlay_payoff,
        "overlay_implied_return_pct": overlay_irr,
    }

    lines = [
        {"id": "book", "label": "GAAP book / price anchor", "gaap_per_share": book, "uplift_per_share": 0.0, "math": f"Anchor ${book}/sh"},
        {
            "id": "lease_cap",
            "label": "Mineral lease run-rate capitalized",
            "gaap_per_share": 0.0,
            "uplift_per_share": lease_uplift,
            "math": f"~${lease_annual/1000:.0f}K/yr x {lease_cap_multiple}x / shares",
        },
        {
            "id": "production_partial",
            "label": "Production option (partially in price)",
            "gaap_per_share": 0.0,
            "uplift_per_share": copperwood_uplift,
            "math": f"P={int(p_base*100)}% x spot royalty ${royalty_spot/1e6:.1f}M/yr",
        },
        {
            "id": "acreage",
            "label": "Acreage + secondary lessee",
            "gaap_per_share": 0.0,
            "uplift_per_share": acreage_uplift,
            "math": "Filing + option [Assumption]",
        },
    ]
    running = book + sum(l["uplift_per_share"] for l in lines[1:])

    if mode == "sum_lines":
        base_payoff = round(running, 2)
    else:
        slack = round(base_payoff - running, 2)
        if abs(slack) > 0.05:
            lines.append(
                {
                    "id": "residual",
                    "label": "Residual to Lawrence base payoff",
                    "gaap_per_share": 0.0,
                    "uplift_per_share": slack,
                    "math": f"Tie to ${base_payoff} path",
                }
            )

    base = val.setdefault("scenarios", {}).setdefault("base", {})
    base["payoff"] = base_payoff
    base["years"] = int(horizon)
    base["sotp_build"] = {
        "shares": int(shares),
        "book_per_share": book,
        "lines": lines,
        "year5_economic_nav_per_share": base_payoff,
        "sum_check": f"lines sum to {base_payoff}",
        "years": int(horizon),
        "notes": cfg.get("sotp_notes", "Lawrence base with partial production option"),
    }
    bull = val.setdefault("scenarios", {}).setdefault("bull", {})
    bull["payoff"] = float(cfg.get("bull_payoff", price * 1.18))
    bull["notes"] = cfg.get("bull_notes", f"Production at spot ${spot}")

    base_ret = irr(price, base_payoff, horizon)
    val.setdefault("results", {})["base"] = {"return_pct": base_ret}
    val["results"]["bear"] = {"return_pct": irr(price, bear_payoff, horizon)}
    val["results"]["bull"] = {"return_pct": irr(price, bull["payoff"], horizon)}
    val["implied_return"] = {
        "base_pct": base_ret,
        "label": "annualized return",
        "display": f"{base_ret:.2f}% (base)",
    }

    ci = val.setdefault("classification_inputs", {})
    if cfg.get("payoff_lens"):
        ci["payoff_lens"] = cfg["payoff_lens"]

    return val


def seed_filing_facts_from_inputs(ticker: str, val: dict, as_of: str) -> None:
    """Write filing_facts metrics from valuation inputs when OTC parse is thin."""
    inp = val.get("inputs") or {}
    book = inp.get("book_per_share")
    if book is None:
        return
    evidence = ROOT / ticker / "research" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    out = evidence / f"filing_facts_{as_of}.json"
    metrics: dict = {}
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            metrics.update(old.get("metrics") or {})
        except json.JSONDecodeError:
            pass
    metrics["book_value_per_share"] = {"current": book, "source": "valuation.json inputs"}
    if inp.get("shares_outstanding"):
        metrics["shares_outstanding"] = {"current": int(inp["shares_outstanding"]), "source": "valuation.json"}
    if inp.get("lease_income_annual_usd"):
        metrics["mineral_lease_income"] = {
            "current": inp["lease_income_annual_usd"],
            "source": inp.get("lease_income_source", "filing"),
        }
    payload = {
        "ticker": ticker,
        "source_text": metrics.get("shares_outstanding", {}).get("source", "valuation.json evidence_refresh seed"),
        "as_of": as_of,
        "metrics": metrics,
        "parser": "evidence_refresh_seed",
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def refresh_ticker(ticker: str) -> bool:
    from valuation_synthesis import post_optionality_valuation_pass

    ticker = ticker.upper()
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        print(f"SKIP {ticker}: no valuation.json")
        return False
    val = json.loads(val_path.read_text(encoding="utf-8"))
    cfg = val.get("evidence_refresh") or {}
    rtype = cfg.get("type")
    if not rtype:
        print(f"SKIP {ticker}: no evidence_refresh in valuation.json")
        return False
    if rtype == "commodity_nav":
        val = refresh_commodity_nav(ticker, val, cfg)
    else:
        print(f"SKIP {ticker}: unknown evidence_refresh type {rtype}")
        return False
    if cfg.get("seed_filing_facts", True):
        seed_filing_facts_from_inputs(ticker, val, TODAY)
    post_optionality_valuation_pass(val)
    val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    og = val.get("optionality_gate") or {}
    print(
        f"OK {ticker} optionality refresh as_of={TODAY} "
        f"floor={og.get('floor_value')} overlay_nav={og.get('overlay_nav_per_share')}"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", help="Ticker (default: all with evidence_refresh)")
    args = parser.parse_args()
    if args.ticker:
        return 0 if refresh_ticker(args.ticker.upper()) else 1
    rc = 0
    for td in sorted(ROOT.iterdir()):
        if not td.is_dir() or td.name.startswith(("_", ".")):
            continue
        vp = td / "research" / "valuation.json"
        if not vp.exists():
            continue
        val = json.loads(vp.read_text(encoding="utf-8"))
        if has_evidence_refresh_config(val):
            if not refresh_ticker(td.name):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
