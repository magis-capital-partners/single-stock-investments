#!/usr/bin/env python3
"""Apply phases 1-3 KEWL valuation refresh: market inputs, economic NAV, option overlay."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()
VAL_PATH = ROOT / "KEWL" / "research" / "valuation.json"


def irr(p0: float, payoff: float, years: float) -> float:
    if p0 <= 0 or years <= 0:
        return 0.0
    return round(100.0 * ((payoff / p0) ** (1.0 / years) - 1.0), 2)


def main() -> None:
    val = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    inp = val.setdefault("inputs", {})
    price = float(inp.get("price", 55.0))
    book = float(inp.get("book_per_share", 12.7))
    shares = float(inp.get("shares_outstanding", 1_126_284))
    lease_annual = 365_000  # FY2024 ~$349.7K; H1 2025 run-rate higher [Filing]
    lease_cap_multiple = 10.0  # [Assumption]
    lease_uplift = round(lease_annual * lease_cap_multiple / shares, 2)

    mi_path = ROOT / "KEWL" / "research" / "market_inputs.json"
    spot_cu = 4.0
    if mi_path.exists():
        mi = json.loads(mi_path.read_text(encoding="utf-8")).get("market_inputs") or {}
        spot_cu = float((mi.get("copper") or {}).get("spot") or spot_cu)

    ssi_royalty = 7_700_000.0
    royalty_spot = round(ssi_royalty * (spot_cu / 4.0), 0)
    royalty_per_sh = royalty_spot / shares
    p_base = 0.35
    copperwood_uplift = round(royalty_per_sh * p_base, 2)
    acreage_uplift = 1.0  # 667K @ ~$1.52/acre ≈ $1M / shares [Filing]
    cash_floor = 3.6  # ~$4M cash/treasuries / shares [Filing FY2024]

    economic_floor = round(book + lease_uplift + copperwood_uplift + acreage_uplift, 2)
    overlay_nav = round(economic_floor + cash_floor * 0.5, 2)

    # Overlay base payoff (7yr): economic components + partial copperwood — not Lawrence lease-only
    overlay_payoff = round(book + lease_uplift + copperwood_uplift + acreage_uplift + 4.0, 2)
    overlay_irr = irr(price, overlay_payoff, 7)

    bull_payoff = round(price * 1.18, 2)  # production + spot copper scenario
    bear_payoff = 14.0
    base_payoff = 30.0  # Lawrence lease-only path unchanged

    val["as_of"] = TODAY
    inp["lease_income_annual_usd"] = lease_annual
    inp["lease_income_source"] = "FY2024 annual; H1 2025 semi-annual trend"
    inp["copperwood_royalty_est_usd_at_spot"] = royalty_spot
    inp["copper_spot_usd_per_lb"] = spot_cu

    og = val.setdefault("optionality_gate", {})
    og["floor_metric"] = "nav_per_share"
    og["floor_value"] = economic_floor
    og["floor_pass"] = price < economic_floor * 1.15
    og["overlay_nav_per_share"] = overlay_nav
    og["copperwood_option_yield_pct"] = round(100.0 * royalty_spot / (price * shares), 2)
    og["overlay_implied_return_pct"] = overlay_irr
    og["notes"] = (
        f"Economic floor ~${economic_floor}/sh (not GAAP book); spot Cu ${spot_cu}/lb; "
        f"Copperwood option yield ~{og['copperwood_option_yield_pct']}% at spot royalty"
    )

    val["nav_overlay"] = {
        "status": "complete",
        "as_of": TODAY,
        "gaap_vs_fair_value": {
            "mineral_rights_balance_sheet_m": 7.98,
            "mineral_rights_source": "H1 2025 semi-annual",
            "acres_disclosed": ">1.3M gross",
            "acres_source": "FY2025 OTC annual disclosure",
            "policy": "Minerals at historical cost; Copperwood royalties off balance sheet until production",
        },
        "gaap_book_per_share": book,
        "economic_floor_per_share": economic_floor,
        "overlay_nav_per_share": overlay_nav,
        "method": "probability_weighted",
        "lines": [
            {"id": "gaap_book", "label": "GAAP equity per share", "per_share": book, "source": "FY2024"},
            {"id": "lease_cap", "label": "Lease run-rate capitalized", "per_share": lease_uplift, "source": f"[Assumption] {lease_cap_multiple}x on ~${lease_annual/1000:.0f}K/yr"},
            {"id": "copperwood_pw", "label": f"Copperwood royalty P={int(p_base*100)}% @ spot Cu", "per_share": copperwood_uplift, "source": f"SSI bridge scaled to ${spot_cu}/lb"},
            {"id": "acreage", "label": "667K-acre package (transaction cost)", "per_share": acreage_uplift, "source": "FY2024 acquisition"},
        ],
        "components": [
            {
                "id": "copperwood_royalty",
                "label": "Copperwood production royalty",
                "option_treatment": "probability_weighted",
                "probability_pct": int(p_base * 100),
                "payoff_per_share_full": round(royalty_per_sh, 2),
                "payoff_per_share_overlay": copperwood_uplift,
                "source": f"SSI @ $4/lb scaled to spot ${spot_cu}/lb; Highland feasibility [Assumption]",
            },
            {
                "id": "secondary_lessee",
                "label": "Secondary lessee / diversification",
                "option_treatment": "probability_weighted",
                "probability_pct": 20,
                "payoff_per_share_overlay": 1.5,
                "source": "FY2024 MD&A diversification; solar/recycling leases [Assumption]",
            },
        ],
        "premium_to_economic_floor_pct": round(100.0 * (price / economic_floor - 1.0), 1),
        "notes": "Do not use GAAP book as dhando floor",
    }

    val["overlay_options"] = {
        "lawrence_base": "lease_income_only_zero_production_royalty",
        "overlay_base_payoff_7yr": overlay_payoff,
        "overlay_implied_return_pct": overlay_irr,
    }

    # Rebuild base sotp without large tie-out
    lines = [
        {"id": "book", "label": "GAAP book / price anchor", "gaap_per_share": book, "uplift_per_share": 0.0, "math": f"Anchor ${book}/sh"},
        {"id": "lease_cap", "label": "Mineral lease run-rate capitalized", "gaap_per_share": 0.0, "uplift_per_share": lease_uplift, "math": f"~${lease_annual/1000:.0f}K/yr x {lease_cap_multiple}x / shares"},
        {"id": "copperwood_partial", "label": "Copperwood option (priced in @ entry)", "gaap_per_share": 0.0, "uplift_per_share": copperwood_uplift, "math": f"P={int(p_base*100)}% x spot royalty ${royalty_spot/1e6:.1f}M/yr"},
        {"id": "acreage", "label": "667K-acre + secondary lessee", "gaap_per_share": 0.0, "uplift_per_share": acreage_uplift, "math": "Filing transaction + option [Assumption]"},
    ]
    running = book + sum(l["uplift_per_share"] for l in lines[1:])
    slack = round(base_payoff - running, 2)
    if abs(slack) > 0.05:
        lines.append({"id": "residual", "label": "Residual to Lawrence base payoff", "gaap_per_share": 0.0, "uplift_per_share": slack, "math": f"Tie to ${base_payoff} lease-heavy path"})

    base = val.setdefault("scenarios", {}).setdefault("base", {})
    base["sotp_build"] = {
        "shares": int(shares),
        "book_per_share": book,
        "lines": lines,
        "year5_economic_nav_per_share": base_payoff,
        "sum_check": f"lines sum to {base_payoff}",
        "years": 7,
        "notes": "Lawrence base: lease path; copper partial via P x spot royalty",
    }
    bull = val.setdefault("scenarios", {}).setdefault("bull", {})
    bull["payoff"] = bull_payoff
    bull["notes"] = f"Copperwood at spot ${spot_cu}/lb + diversification; royalty ~${royalty_spot/1e6:.1f}M/yr"

    val.setdefault("results", {})["base"] = {"return_pct": irr(price, base_payoff, 7)}
    val["results"]["bear"] = {"return_pct": irr(price, bear_payoff, 7)}
    val["results"]["bull"] = {"return_pct": irr(price, bull_payoff, 7)}
    base_ret = val["results"]["base"]["return_pct"]
    val["implied_return"] = {
        "base_pct": base_ret,
        "label": "annualized return",
        "display": f"{base_ret:.2f}% (base)",
    }

    val["management_outlook"] = {
        "cf_positive_from_2026": {
            "claim": "Revenues exceed costs from 2026; self-sustaining operations",
            "source": "investor-documents/transcripts/2025-12-31_Annual_Shareholder_Meeting_Transcript.md",
            "tier": "management_statement",
            "status": "unverified",
            "filing_reconcile": "H1 2025 net loss ($51,156); not in Lawrence base until confirmed",
        }
    }

    val["catalyst_paths"] = [
        {"event": "Operating cash positive (management)", "timing": "2026+", "impact": "Lower burn vs ~$160K/yr historical", "source": "shareholder meeting transcript"},
        {"event": "Highland Copper Copperwood production start", "timing": "3-7 years", "impact": f"Royalty ~${royalty_spot/1e6:.1f}M/yr at spot Cu"},
        {"event": "Michigan mining infrastructure grant", "timing": "uncertain", "impact": "Project acceleration"},
        {"event": "Secondary lessee on 667K-acre package", "timing": "medium term", "impact": "Lease diversification"},
        {"event": "Critical minerals / AI-datacenter copper demand", "timing": "secular", "impact": "Qualitative tailwind for Copperwood [Assumption]", "tier": "narrative"},
        {"event": "Failure mode", "timing": "-", "impact": f"Reversion toward economic floor ~${economic_floor}"},
    ]

    ci = val.setdefault("classification_inputs", {})
    ci["payoff_lens"] = "asset"

    facts_path = ROOT / "KEWL" / "research" / "evidence" / f"filing_facts_{TODAY}.json"
    facts = {
        "ticker": "KEWL",
        "source_text": "evidence/_text/2025-12-31_Annual_Report.pdf.txt",
        "as_of": TODAY,
        "metrics": {
            "book_value_per_share": {"current": book, "source": "FY2024 balance sheet"},
            "shares_outstanding": {"current": int(shares), "source": "FY2025 annual disclosure"},
            "mineral_acres_gross": {"current": ">1.3M", "source": "2025-12-31_Annual_Report.pdf"},
            "leased_acres": {"current": 36705, "source": "2025-12-31_Annual_Report.pdf"},
            "mineral_lease_income": {"current": 349700, "prior": 189101, "source": "FY2024 annual; H1 2025 semi-annual"},
            "net_income": {"current": 262499, "prior": 168602, "source": "FY2024 annual"},
            "h1_net_income": {"current": -51156, "source": "2025-06-30_Semi-Annual_Report.pdf"},
        },
    }
    facts_path.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")

    VAL_PATH.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    print(f"OK KEWL valuation refreshed as_of={TODAY} spot_cu={spot_cu} econ_floor={economic_floor} overlay_irr={overlay_irr}%")


if __name__ == "__main__":
    main()
