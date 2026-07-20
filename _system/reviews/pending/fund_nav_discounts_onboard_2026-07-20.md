# Fund NAV discounts sleeve — onboard summary

**Date:** 2026-07-20  
**Sleeve:** `fund_nav_discounts` (dashboard label: **NAV discounts**)

## Tickers

| Ticker | Company | Edge | Disc. to reported NAV | Base scenario IRR | Notes |
|--------|---------|------|------------------------|-------------------|-------|
| CEE | Central and Eastern Europe Fund | shadow | −3.9% | ~4%/yr | Russia sleeve $0 in base; PH3 ingested |
| URB.A.TO | Urbana Corp Class A | holdco | −41.7% | ~9.8%/yr | Weekly NAV CAD 14.49 (2026-07-10) |
| PSH | Pershing Square Holdings | classic | −34.5% | ~8.3%/yr | USD line PSHD; weekly NAV $77.06 (2026-07-14) |
| NAN | Nuveen NY muni CEF | classic | pending | pending | Stub valuation only |

## How to add the next fund

```powershell
# 1. Extend FUND_SPECS in _system/scripts/onboard_fund_nav_sleeve.py
# 2. Add ticker to investment_sleeves.json → fund_nav_discounts.tickers
# 3. Run:
python _system/scripts/onboard_fund_nav_sleeve.py --tickers NEW.TICKER
python _system/scripts/patch_dashboard_fund_nav_rows.py NEW.TICKER
```

## Dashboard tags

- Sleeve filter **NAV discounts** (amber badge)
- Edge chip: Classic discount / Shadow NAV / Holdco look-through
- Column **NAV disc.** (sortable)

## [HUMAN REVIEW]

- Approve Russia recovery probability for CEE (still zero in base)
- Confirm Urbana private-mark look-through before sizing
- Confirm PSH USD vs GBP share line for trading
- Pull live NAN NAV/price

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] CEE / URB.A.TO / PSH onboarded under NAV discounts sleeve with fund_nav_overlay.
- [PROPOSED MOI] CEF/listed-fund ideas use three NAVs (reported / liquid / complete) and edge tags classic|shadow|holdco.
