#!/usr/bin/env python3
"""Onboard / refresh closed-end fund and listed investment-company NAV-discount names.

Scaffolds ticker folders, registry entries, fund_nav_overlay valuations, thesis,
and deep-dive stubs. Safe to re-run with --force for content refresh.

Example:
  python _system/scripts/onboard_fund_nav_sleeve.py
  python _system/scripts/onboard_fund_nav_sleeve.py --tickers CEE PSH
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import (  # noqa: E402
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    load_registry,
    save_registry,
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
PY = sys.executable

# Seed economics — update via refresh_fund_nav_overlay.py / human review.
FUND_SPECS: dict[str, dict] = {
    "CEE": {
        "company": "The Central and Eastern Europe Fund, Inc.",
        "market": "US",
        "exchange": "NYSE",
        "instrument_type": "closed_end_fund",
        "edge": "shadow",
        "ir_roots": [
            "https://www.dws.com/en-us/products/closed-end-funds/CEE-the-central-and-eastern-europe-fund-inc/"
        ],
        "download_type": "us_shared",
        "cik": "0000860489",
        "currency": "USD",
        "market_price": 20.48,
        "reported_nav": 21.32,
        "liquid_nav_per_share": 21.32,
        "complete_nav_per_share_base": 21.32,
        "shares_outstanding": 6520194,
        "expense_ratio_net": 0.0126,
        "price_note": "Yahoo CEE regularMarketPrice ~2026-07-20.",
        "nav_note": "DWS reported NAV as of 2026-07-17 (~$21.32). Liquid NAV ≈ reported while Russia remains at zero.",
        "zero_marked_sleeves": [
            {
                "id": "russia_equity_sleeve",
                "label": "Russian securities marked at zero since 2022-03-14",
                "option_treatment": "zero",
                "cost_basis_total": 30722586,
                "cost_basis_as_of": "2025-07-31",
                "reported_value": 0,
                "proxy_gross_value_base": None,
                "realization_probability_base": 0.0,
                "years_to_realization_base": None,
                "friction_haircut_pct": None,
                "evidence": "CEE-PH3.pdf Schedule of Investments; N-CSR Russia footnotes",
                "human_review": True,
            }
        ],
        "thesis_line": (
            "CEE is a DWS closed-end fund: liquid Polish/Hungarian equities plus a Russian sleeve "
            "carried at zero since March 2022. Reported net asset value describes only the liquid book."
        ),
        "one_liner": (
            "Shadow-NAV CEF: price tracks reported NAV (Russia = $0), but Moscow marks imply a "
            "mid-20s percent discount to economic value — base still prices Russia at zero."
        ),
    },
    "URB.A.TO": {
        "company": "Urbana Corporation (Class A)",
        "market": "CA",
        "exchange": "TSX",
        "instrument_type": "listed_investment_co",
        "edge": "holdco",
        "ir_roots": [
            "https://www.urbanacorp.com/",
            "https://www.urbanacorp.com/net-asset-reports/",
        ],
        "download_type": "uk_ir",
        "currency": "CAD",
        "market_price": 8.45,
        "reported_nav": 14.49,
        "liquid_nav_per_share": None,
        "complete_nav_per_share_base": 14.49,
        "shares_outstanding": None,
        "expense_ratio_net": None,
        "price_note": "Yahoo URB-A.TO ~CAD 8.45 (2026-07-20).",
        "nav_note": "Urbana weekly net assets per share CAD 14.49 as of 2026-07-10 (company site).",
        "zero_marked_sleeves": [],
        "private_note": "Private + public financials/exchanges portfolio; private marks need look-through schedule.",
        "thesis_line": "Urbana is a TSX-listed investment corporation (permanent capital) mixing public financials with private stakes, habitually trading at a wide discount to published NAV.",
        "one_liner": "Canadian investment corp trading ~40% below weekly NAV — holdco look-through plus buyback alignment.",
    },
    "PSH": {
        "company": "Pershing Square Holdings, Ltd.",
        "market": "UK",
        "exchange": "LSE",
        "instrument_type": "closed_end_fund",
        "edge": "classic",
        "ir_roots": [
            "https://pershingsquareholdings.com/",
            "https://pershingsquareholdings.com/wp-content/uploads/",
        ],
        "download_type": "uk_ir",
        "currency": "USD",
        "market_price": 50.50,
        "reported_nav": 77.06,
        "liquid_nav_per_share": 77.06,
        "complete_nav_per_share_base": 77.06,
        "shares_outstanding": 175030590,
        "expense_ratio_net": 0.015,
        "price_note": "Yahoo PSHD.L (USD line) ~$50.50 (2026-07-20); GBP line PSH.L ~3768p.",
        "nav_note": "Company weekly NAV $77.06 per share as of 2026-07-14 (PSH site).",
        "zero_marked_sleeves": [],
        "thesis_line": "PSH is Ackman's LSE-listed closed-ended vehicle: concentrated large-cap longs, weekly NAV, persistent double-digit discount, active share repurchases.",
        "one_liner": "Pershing Square closed-end holdco at a large discount to weekly NAV with ongoing buybacks.",
    },
}


def log(msg: str) -> None:
    print(msg, flush=True)


def scaffold(ticker: str, spec: dict) -> Path:
    td = ROOT / ticker
    market = spec["market"]
    if market == "US":
        inv = td / "investor-documents"
        for sub in ("sec-edgar", f"ir-{ticker.lower()}", "research-notes"):
            (inv / sub).mkdir(parents=True, exist_ok=True)
        script = inv / f"download_{ticker.lower().replace('.', '_')}_investor_docs.py"
        if not script.exists():
            script.write_text(
                f'''#!/usr/bin/env python3
"""Download {ticker} investor documents via shared Marvin script."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_us_investor_docs.py"),
    "--ticker",
    "{ticker}",
])
''',
                encoding="utf-8",
            )
    else:
        for sub in (
            "official-reports",
            "corporate-documents",
            "presentations-and-media",
            "third-party-analyses",
            "investor-documents",
            "research",
        ):
            (td / sub).mkdir(parents=True, exist_ok=True)
        idx = td / "document-index.csv"
        if not idx.exists():
            idx.write_text("path,title,date,type\n", encoding="utf-8")
        inv = td / "investor-documents"
        inv.mkdir(parents=True, exist_ok=True)
        script = inv / f"download_{ticker.lower().replace('.', '_')}_investor_docs.py"
        if not script.exists():
            roots = spec.get("ir_roots") or []
            script.write_text(
                f'''#!/usr/bin/env python3
"""Placeholder IR harvest for {ticker}. Prefer Vicki/browser or manual PDF drop."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "{ticker}" / "_download_log.txt"
IR = {roots!r}
LOG.write_text(
    f"{{__import__('datetime').datetime.utcnow().isoformat()}}Z placeholder; IR roots={{IR}}\\n",
    encoding="utf-8",
)
print("IR harvest placeholder — drop PDFs under {ticker}/ and re-run indexes")
''',
                encoding="utf-8",
            )

    (td / "research" / "reports").mkdir(parents=True, exist_ok=True)
    (td / "research" / "evidence").mkdir(parents=True, exist_ok=True)
    readme = td / "README.md"
    readme.write_text(
        f"# {spec['company']} ({ticker})\n\n"
        f"**Ticker:** {ticker} | **Market:** {spec['market']} | **Exchange:** {spec['exchange']}\n"
        f"**Instrument:** {spec['instrument_type']} | **Fund edge:** {spec['edge']}\n"
        f"**Sleeve:** fund_nav_discounts (NAV discounts)\n"
        f"**Last updated:** {TODAY}\n\n"
        f"## IR\n\n"
        + "\n".join(f"- {u}" for u in spec.get("ir_roots") or [])
        + "\n\n## Download\n\n"
        f"```powershell\npython {ticker}/investor-documents/download_{ticker.lower().replace('.', '_')}_investor_docs.py\n```\n",
        encoding="utf-8",
    )
    return td


def write_valuation(ticker: str, spec: dict) -> Path:
    price = float(spec["market_price"])
    reported = float(spec["reported_nav"])
    disc = round((price / reported - 1.0) * 100.0, 2) if reported else None
    liquid = spec.get("liquid_nav_per_share")
    liquid_f = float(liquid) if liquid is not None else reported
    complete = spec.get("complete_nav_per_share_base") or reported
    complete_f = float(complete) if complete is not None else reported
    # Scenario payoffs (5y):
    # - thin discount (|disc|<8%): look-through NAV growth; discount roughly sticky
    # - deep discount: partial close toward liquid NAV plus modest NAV growth
    if disc is not None and disc > -8:
        bear_payoff = round(price * (0.98**5), 2)
        base_payoff = round(price * (1.04**5), 2)
        bull_payoff = round(complete_f * (1.06**5) * 0.97, 2)
        base_notes = (
            "Thin reported-NAV discount; base is look-through NAV growth with sticky discount "
            "(shadow sleeve stays zero in base)"
        )
        bull_notes = "NAV compounds faster and/or discount tightens; no automatic Russia recovery"
    else:
        bear_payoff = round(max(price * 1.02, liquid_f * 0.70), 2)
        # Halfway from today's price toward 95% of liquid NAV, then grow 4%/yr
        mid = 0.5 * price + 0.5 * liquid_f * 0.95
        base_payoff = round(mid * (1.04**5), 2)
        bull_payoff = round(complete_f * 0.97 * (1.05**5), 2)
        base_notes = (
            "Partial discount close toward liquid/reported NAV over five years; "
            "no heroic private/Russia recovery"
        )
        bull_notes = "Discount nearly closes to complete NAV with modest NAV growth"

    def scen_irr(payoff: float | None, years: float = 5.0) -> float | None:
        if payoff is None or price <= 0:
            return None
        return round(((payoff / price) ** (1.0 / years) - 1.0) * 100.0, 1)

    base_irr = scen_irr(base_payoff) or 0.0
    data = {
        "ticker": ticker,
        "as_of": TODAY,
        "valuation_mode": "optionality",
        "method": "scenario",
        "instrument_type": spec["instrument_type"],
        "lawrence_bucket": "other",
        "classification_inputs": {
            "archetype": "holding_co",
            "moat": "n/a",
            "dhando": "partial",
            "stance": "watch",
            "cycle": "-",
            "payoff_lens": "asset",
            "investment_sleeve": "fund_nav_discounts",
        },
        "inputs": {
            "price": price,
            "price_source": spec.get("price_note"),
            "currency": spec["currency"],
            "shares_outstanding": spec.get("shares_outstanding"),
            "normalization_note": spec.get("nav_note"),
        },
        "optionality_gate": {
            "framework": "fund_lookthrough_nav",
            "floor_pass": True,
            "floor_metric": "liquid_nav_per_share" if liquid is not None else "reported_nav",
            "floor_value": liquid if liquid is not None else reported,
            "primary_metric": "discount_to_reported_nav",
            "primary_label": "discount to reported NAV",
            "primary_return_pct": base_irr,
            "notes": (
                "Stance uses liquid/reported NAV floor + discount-close scenarios. "
                "Zero-marked sleeves stay at zero in base until human sets realization probability."
            ),
        },
        "fund_nav_overlay": {
            "edge": spec["edge"],
            "as_of": TODAY,
            "currency": spec["currency"],
            "market_price": price,
            "reported_nav": reported,
            "liquid_nav_per_share": liquid,
            "complete_nav_per_share_base": complete,
            "discount_to_reported_nav_pct": disc,
            "discount_to_liquid_nav_pct": (
                round((price / liquid - 1.0) * 100.0, 2) if liquid else disc
            ),
            "discount_to_complete_nav_pct": (
                round((price / complete - 1.0) * 100.0, 2) if complete else disc
            ),
            "shares_outstanding": spec.get("shares_outstanding"),
            "expense_ratio_net": spec.get("expense_ratio_net"),
            "leverage_pct": None,
            "zero_marked_sleeves": spec.get("zero_marked_sleeves") or [],
            "private_note": spec.get("private_note"),
            "evidence_refresh": {"type": "fund_nav", "sources": ["sponsor_nav", "market_price"]},
        },
        "scenarios": {
            "bear": {
                "price": price,
                "payoff": bear_payoff,
                "years": 5,
                "implied_irr_pct": scen_irr(bear_payoff),
                "notes": "Discount persists; NAV flat to slightly up",
            },
            "base": {
                "price": price,
                "payoff": base_payoff,
                "years": 5,
                "implied_irr_pct": base_irr,
                "notes": base_notes,
            },
            "bull": {
                "price": price,
                "payoff": bull_payoff,
                "years": 5,
                "implied_irr_pct": scen_irr(bull_payoff),
                "notes": bull_notes,
            },
        },
        "estimates": {
            "implied_irr_base_pct": base_irr,
            "irr_method": "scenario",
        },
        "human_review": [
            "Confirm live market price and latest sponsor NAV before sizing.",
            "Zero-marked or private sleeves: set realization_probability_base only after evidence review.",
        ],
    }
    path = ROOT / ticker / "research" / "valuation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_thesis(ticker: str, spec: dict, irr: float) -> Path:
    path = ROOT / ticker / "research" / "thesis.md"
    path.write_text(
        f"# {ticker} — Investment Thesis\n\n"
        f"**Last updated:** {TODAY}\n\n"
        f"## Classification\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| **Archetype** (Stahl) | holding_co |\n"
        f"| **Moat** (Munger) | n/a |\n"
        f"| **Dhando** (Pabrai) | partial |\n"
        f"| **Stance** | watch |\n"
        f"| **Cycle** | - |\n"
        f"| **Implied 7yr IRR** (Lawrence) | {irr}% (scenario) |\n"
        f"| **IRR method** | scenario |\n"
        f"| **Lawrence bucket** | other |\n"
        f"| **Valuation overlay** | fund_nav_overlay |\n"
        f"| **Payoff lens** | asset |\n"
        f"| **Investment sleeve** | fund_nav_discounts |\n"
        f"| **Instrument** | {spec['instrument_type']} |\n"
        f"| **Fund edge** | {spec['edge']} |\n\n"
        f"## One-line thesis\n\n"
        f"{spec['one_liner']}\n\n"
        f"## Key questions\n\n"
        f"- [ ] Latest reported NAV and share count confirmed\n"
        f"- [ ] Liquid vs complete NAV bridge documented\n"
        f"- [ ] Discount-close catalyst (buyback / tender / activism) named\n"
        f"- [ ] Zero-marked or private sleeves option-scanned\n\n"
        f"## [HUMAN REVIEW]\n\n"
        f"- Onboarded to NAV discounts sleeve {TODAY}.\n",
        encoding="utf-8",
    )
    return path


def write_deep_dive(ticker: str, spec: dict, irr: float) -> Path:
    path = ROOT / ticker / "research" / f"deep_dive_{TODAY}.md"
    # Never clobber a hand-edited dive (e.g. CEE shadow-NAV rewrite).
    if path.exists() and "Shadow" in path.read_text(encoding="utf-8", errors="replace"):
        log(f"Skip deep dive overwrite (hand-edited): {path.relative_to(ROOT)}")
        return path
    disc = None
    if spec.get("market_price") and spec.get("reported_nav"):
        disc = round((spec["market_price"] / spec["reported_nav"] - 1.0) * 100.0, 1)
    disc_txt = f"{disc}% vs reported NAV" if disc is not None else "discount pending"
    russia = ""
    if ticker == "CEE":
        russia = (
            " The edge is not that thin reported discount. Russian holdings have been valued at "
            "zero since 14 March 2022 while share counts remain; economic NAV can be mid-20s percent "
            "higher on a Moscow mark-to-market illustration. Base case still keeps Russia at zero "
            "until a human sets a realization probability."
        )
    edge = spec.get("edge") or "classic"
    if edge == "shadow":
        why = (
            f"The interesting mispricing is not {disc_txt}. "
            f"Reported net asset value understates economic ownership by carrying a material sleeve at zero."
            f"{russia} "
            f"Lead with the accounting mark; treat reported-NAV discount as secondary context only."
        )
        exec_sum = (
            f"This is a shadow-net-asset-value fund idea. Base case about **{irr}% per year** keeps the "
            f"zero-marked sleeve at $0 until a human sets recovery probability; the asymmetric payoff is "
            f"that sleeve on top of the liquid book. Do not size on the thin reported-NAV discount alone."
        )
    else:
        why = (
            f"The shares trade at {disc_txt}.{russia} "
            f"The inefficiency is closed-end market structure and/or look-through marks, not a hidden factory."
        )
        exec_sum = (
            f"Base case about **{irr}% per year** from discount-close scenarios over five years, "
            f"with liquid or reported NAV as the floor. Not a filing free-cash-flow IRR."
        )
    path.write_text(
        f"# {ticker} — Deep dive ({TODAY})\n\n"
        f"**Adversarial review:** pending (`adversarial_{TODAY}.md`)\n\n"
        f"## What this business is\n\n"
        f"{spec['thesis_line']} It is tagged as a fund NAV-discount idea, not an operating compounder.\n\n"
        f"## Why the market might be wrong\n\n"
        f"{why}\n\n"
        f"## Executive summary\n\n"
        f"{exec_sum}\n\n"
        f"## Primary sources\n\n"
        + "\n".join(f"- {u}" for u in spec.get("ir_roots") or [])
        + "\n"
        + ("- `CEE/investor-documents/CEE-PH3.pdf` (schedule of investments)\n" if ticker == "CEE" else "")
        + "\n"
        f"## Business & moat\n\n"
        f"Wrapper economics matter: fees, leverage, distribution policy, and board capital-return tools. "
        f"Competitive advantage sits in the underlying book and in permanent capital, not in a product moat.\n\n"
        f"#### Option scan\n\n"
        f"| # | Question | Treatment |\n|---|----------|----------|\n"
        f"| 1 | GAAP/NAV mark misstates sleeves? | "
        + ("Yes — Russia Level 3 at zero; overlay only" if ticker == "CEE" else "Private marks (Urbana) or none material")
        + " |\n"
        f"| 2 | Buyback / tender catalyst? | Document from board notices |\n"
        f"| 3 | Leverage or fee drag? | Burden in liquid NAV |\n\n"
        f"## Payoff & return\n\n"
        f"| Gate | Result |\n|------|--------|\n"
        f"| Understand? | Fund look-through |\n"
        f"| Bounded bear? | Liquid/reported NAV less friction |\n"
        f"| Why mispriced? | {spec['edge']} NAV edge |\n"
        f"| Stance proposal | watch pending human size |\n\n"
        f"See **Valuation & IRR** below.\n\n"
        f"## Risks & inversion\n\n"
        f"- Discount never closes; expense ratio compounds against you.\n"
        f"- NAV marks are wrong the other way (private overstatement; Russia permanent zero).\n"
        f"- Liquidity: wide spreads on small CEFs / Class A lines.\n\n"
        f"**Lens failure mode:** value trap where the wrapper discount is structural and buybacks are too small to matter.\n\n"
        f"## Valuation & IRR (assumption ledger)\n\n"
        f"### Assumption ledger (base case)\n\n"
        f"| Input | Value | Source |\n|-------|-------|--------|\n"
        f"| Price today | {spec['currency']} {spec['market_price']} | {spec.get('price_note')} |\n"
        f"| Reported NAV | {spec['currency']} {spec['reported_nav']} | {spec.get('nav_note')} |\n"
        f"| Discount to reported NAV | {disc_txt} | price / NAV - 1 |\n"
        f"| Fund edge tag | {spec['edge']} | sleeve taxonomy |\n"
        f"| Horizon | 5 years | [Assumption] |\n"
        f"| Base payoff | ~90% of liquid/reported NAV | [Assumption] |\n"
        + (
            "| Russia sleeve base value | 0 | [Assumption] pending human P |\n"
            if ticker == "CEE"
            else ""
        )
        + "\n"
        f"#### IRR arithmetic (show your work)\n\n"
        f"1. Start from price today.\n"
        f"2. Compare to reported NAV (and liquid NAV when different).\n"
        f"3. Base payoff assumes partial discount close over five years without heroic sleeve recovery.\n"
        f"4. Annualize (payoff / price)^(1/5) - 1.\n\n"
        f"**Returns statement:** About **{irr}% per year** in the base discount-close case.\n\n"
        f"## Classification\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| **Archetype** (Stahl) | holding_co |\n"
        f"| **Moat** (Munger) | n/a |\n"
        f"| **Dhando** (Pabrai) | partial |\n"
        f"| **Stance** | watch |\n"
        f"| **Cycle** | - |\n"
        f"| **Implied 7yr IRR** (Lawrence) | {irr}% (scenario) |\n"
        f"| **IRR method** | scenario |\n"
        f"| **Lawrence bucket** | other |\n"
        f"| **Valuation overlay** | fund_nav_overlay |\n"
        f"| **Payoff lens** | asset |\n"
        f"| **Investment sleeve** | fund_nav_discounts |\n\n"
        f"## [HUMAN REVIEW]\n\n"
        f"- Approve live NAV/price marks and any non-zero recovery probability.\n"
        f"- Confirm mandate fit (liquidity, fees, currency).\n\n"
        f"## [PROPOSED MEMORY]\n\n"
        f"- [PROPOSED COMPANY] {ticker} onboarded to NAV discounts sleeve with edge `{spec['edge']}`.\n",
        encoding="utf-8",
    )
    return path


def write_adversarial(ticker: str, spec: dict) -> Path:
    path = ROOT / ticker / "research" / f"adversarial_{TODAY}.md"
    path.write_text(
        f"# {ticker} — Milly adversarial ({TODAY})\n\n"
        f"**Status:** first-pass scaffold (not a full Milly re-read of all filings)\n\n"
        f"## Factual checks\n\n"
        f"- [ ] Price and reported NAV as-of dates match sources cited in deep dive\n"
        f"- [ ] Edge tag `{spec['edge']}` matches the real thesis (classic vs shadow vs holdco)\n"
        f"- [ ] No Russia/private recovery smuggled into base IRR\n\n"
        f"## Inference gaps → [HUMAN REVIEW]\n\n"
        f"- Scenario payoffs (90% of NAV in five years) are assumptions, not filing facts\n"
        f"- Expense ratio and share count may be stale\n\n"
        f"## Lens failure\n\n"
        f"Discount persists; buybacks too small; marks overstated.\n",
        encoding="utf-8",
    )
    return path


def register(ticker: str, spec: dict) -> None:
    reg = load_registry()
    holdings = reg.setdefault("holdings", {})
    entry = {
        "company": spec["company"],
        "market": spec["market"],
        "exchange": spec.get("exchange") or EXCHANGE_META.get(ticker, "—"),
        "onboarded": TODAY,
        "instrument_type": spec["instrument_type"],
        "download": {
            "type": spec.get("download_type") or "us_shared",
            "ir_roots": list(spec.get("ir_roots") or []),
        },
        "classification": {
            **DEFAULT_CLASSIFICATION,
            "archetype": "holding_co",
            "moat": "n/a",
            "dhando": "partial",
            "stance": "watch",
            "cycle": "-",
            "payoff_lens": "asset",
            "moi_bucket": "asset",
            "investment_sleeve": "fund_nav_discounts",
            "fund_edge": spec["edge"],
            "instrument_type": spec["instrument_type"],
        },
    }
    if spec.get("cik"):
        entry["download"]["cik"] = spec["cik"]
    holdings[ticker] = entry
    save_registry(reg)


def copy_cee_pdf() -> None:
    src = Path(r"c:\Users\drewg\Downloads\CEE-PH3.pdf")
    dest_dir = ROOT / "CEE" / "investor-documents"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "CEE-PH3.pdf"
    if src.exists():
        shutil.copy2(src, dest)
        log(f"Copied {src} -> {dest}")
        (ROOT / "CEE" / "_download_log.txt").write_text(
            f"{datetime.now(timezone.utc).isoformat()} copied CEE-PH3.pdf from Downloads\n",
            encoding="utf-8",
        )
    else:
        log(f"WARN: {src} not found — drop CEE-PH3.pdf manually")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", nargs="*", default=list(FUND_SPECS))
    ap.add_argument("--skip-sync", action="store_true")
    args = ap.parse_args()

    for ticker in args.tickers:
        key = ticker.upper() if not ticker.endswith(".TO") else ticker.upper()
        # preserve URB.A.TO casing pattern
        match = None
        for k in FUND_SPECS:
            if k.upper() == ticker.upper():
                match = k
                break
        if not match:
            log(f"Unknown fund ticker {ticker}; known: {', '.join(FUND_SPECS)}")
            return 1
        spec = FUND_SPECS[match]
        log(f"=== {match} ===")
        scaffold(match, spec)
        if match == "CEE":
            copy_cee_pdf()
        register(match, spec)
        vpath = write_valuation(match, spec)
        val = json.loads(vpath.read_text(encoding="utf-8"))
        irr = float((val.get("estimates") or {}).get("implied_irr_base_pct") or 0)
        write_thesis(match, spec, irr)
        write_deep_dive(match, spec, irr)
        write_adversarial(match, spec)
        log(f"Wrote research artifacts for {match} (base IRR ~{irr}%)")

    if not args.skip_sync:
        for cmd, label in (
            ([PY, str(SCRIPTS / "sync_investment_sleeves.py")], "sync sleeves"),
            ([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], "sync portfolio"),
            ([PY, str(SCRIPTS / "refresh_fund_nav_overlay.py"), "--all"], "fund nav refresh"),
            ([PY, str(SCRIPTS / "build_folder_indexes.py")], "folder indexes"),
            ([PY, str(SCRIPTS / "build_dashboard_data.py")], "dashboard data"),
        ):
            log(f"\n=== {label} ===")
            subprocess.run(cmd, cwd=ROOT, check=False)
    log("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
