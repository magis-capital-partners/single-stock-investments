# Proposal: property-level real estate tracking feeding the dashboard

**Date:** 2026-07-16
**Status:** implemented 2026-07-16
**Trigger:** SAFE x Brookfield JV read-through raised the question of tracking real estate properties as dashboard inputs.

## What exists today

- Real estate reaches the dashboard only as ticker-level aggregates: `{TICKER}/research/valuation.json` `nav_overlay` lines and `component_valuation_results`, projected into `dashboard_data.json` `tickers[].component_valuation` by `_system/scripts/build_dashboard_data.py`.
- Best current examples: STHO (SAFE stake, Asbury Park, Magnolia Green as `nav_overlay` buckets), TPL (surface acres / NRA unit NAV), LAND (thin NAV stub).
- There is **no** property register (no address / asset type / sqft / NOI / cap rate rows) and no market-data cache for cap rate comps.

## Design (three pieces)

### 1. Per-ticker property register (source of truth)

New file `{TICKER}/research/properties.json`:

```json
{
  "ticker": "STHO",
  "as_of": "2026-03-31",
  "properties": [
    {
      "id": "asbury-waterfront",
      "name": "Asbury Park Waterfront",
      "type": "land_development",
      "location": "Asbury Park, NJ",
      "units": {"acres": null, "sqft": null},
      "carrying_value_usd": null,
      "estimated_fair_value_usd": {"low": null, "base": null, "high": null},
      "income": {"annualized_cash_noi_usd": null},
      "valuation_basis": "10-Q Q1 2026 segment note",
      "source": "STHO/investor-documents/...",
      "status": "held",
      "nav_overlay_line": "monetizing_portfolio"
    }
  ]
}
```

Key rule: each property row maps to a `nav_overlay` line via `nav_overlay_line`, so the register reconciles to the valuation the dashboard already shows. Filing-cited values only; estimates flagged `[Assumption]`.

### 2. Roll-up script

`_system/scripts/build_property_register.py {TICKER}`:

- Validates `properties.json` (schema + reconciliation: sum of property fair values within tolerance of the mapped `nav_overlay` lines).
- Writes a compact summary onto `valuation.json` (e.g. `property_register: {count, total_fair_value, as_of}`) so `refresh_optionality_valuation.py` and lint can see it.
- Hooked into `marvin_cloud_refresh.py` as an optional step when `properties.json` exists.

### 3. Dashboard projection

In `build_dashboard_data.py` `build_ticker_row()`: if `properties.json` exists, attach `tickers[].properties` (the rows plus the reconciliation status). UI: a "Properties" sub-table inside the existing Valuation drawer (`valuation-viz.js`), no new tab.

## Optional shared cache (phase 2)

`_system/reference/market-data/real-estate/` for cross-ticker comps: deal-implied cap rates (e.g. SAFE/Brookfield 4.0% cash cap, June 2026), REIT implied cap rate series. Context tier only — `in_base_irr: false`, consistent with `optionality_valuation.md` (no auto-inflating NAV marks without filing evidence).

## Candidate tickers to seed

| Ticker | Register contents |
|---|---|
| STHO | Asbury Park, Magnolia Green, operating properties, SAFE stake (mark, not property) |
| TPL | Surface acres / NRA blocks (already partially in nav_overlay) |
| LAND | Farm portfolio (10-K schedule III) |
| PCYO | Sky Ranch land / water assets |
| CDZI | Land + water rights |

## Effort and risks

- Phase 1 (schema + validator + STHO seed + dashboard column): small, one session.
- Risk: stale property marks presented as current — mitigated by mandatory `as_of` and the same 7-day/dated-staleness display convention used for market inputs.
- No new framework file needed; this rides on `option_treatment.md` / `optionality_valuation.md` nav_overlay semantics.

## Implementation notes (2026-07-16)

Shipped:

- Schema: `_system/templates/properties_schema.json`
- Seeds: `STHO`, `TPL`, `LAND`, `PCYO`, `CDZI` → `{TICKER}/research/properties.json`
- Roll-up: `_system/scripts/build_property_register.py` (+ unit tests)
- Hook: `marvin_cloud_refresh.py` runs register when `properties.json` exists
- Dashboard: `build_dashboard_data.py` → `tickers[].properties`; UI panel in `valuation-viz.js` / holdings detail
- Context cache: `_system/reference/market-data/real-estate/` (SAFE×Brookfield 4.0% cash cap)

`in_base_irr` remains false on registers and deal comps.
