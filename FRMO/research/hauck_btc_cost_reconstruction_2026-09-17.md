# Hauck BTC cost reconstruction (17 Sep 2026)

**Status:** Context only. Does not enter Lawrence base IRR.
**Method:** `_system/scripts/btc_cost_of_production.py` (ASIC vintage mix, $0.05/kWh, 60% power share).
**Linked plan:** `FRMO/research/hauck_btc_cost_model_plan_2026-09-17.md`.

## Update — 11 November 2026

The September reconstruction below is retained as a dated research record. The
current World Model BTC panel uses schema 2.0 and extends independent demand and
supply scenarios through 31 December 2033. This is research context with no
valuation authority; it does not change base IRR, a security valuation contract,
or an order decision.

### Published references and fit disagreement

- [HK Q3 2026, pp. 5–6](https://horizonkinetics.com/app/uploads/Horizon-Kinetics-Q3-2026-Commentary-Final.pdf#page=5)
  gives approximately $130,000 in April 2028 ($117,000–$149,000) and approximately
  $1 million by 2033, switching from supply-based to demand-based reasoning.
  The 2033 observation retains year precision; no exact target day is invented.
- [HK Q2 2026, pp. 32–36](https://horizonkinetics.com/app/uploads/Horizon-Kinetics-Q2-2026-Commentary-Final.pdf#page=32)
  retains separate $150,000–$250,000 supply and $270,438.05 demand references for
  April 2028. It describes $117,000–$149,000 as **current** SOTA economics with a
  25% annual return. Q3's reuse of those endpoints at a different horizon is an
  unresolved basis/timing change, not a replacement of the Q2 observations.
- The refreshed constrained fit remains at its lower bound, k=4. Its April 2033
  value is approximately $391,746; the free-fit diagnostic (k≈3.77) is $310,304.
  End-2033 values are approximately $444,246 and $349,346. Neither is tuned to HK.
  Different fit windows, time origins and four one-year historical holdouts are
  exposed in the panel. Anchor-implied exponents combine different letter
  vintages and are labeled illustrations, not HK's unpublished full equation.

### Cost inputs and remaining uncertainty

- Average-fleet production cost is approximately $61,314 at $0.05/kWh; the legacy
  SOTA-plus-return result is $95,281. Updating efficiency did not force this
  legacy method into HK's range.
- Manufacturer-linked specifications replace the assumed S23 row with 580 TH/s,
  5,510 W and 9.5 J/TH. The catalog adds current MicroBT M70/M70S and Bitmain S23
  XP Hyd specifications, separates nameplate efficiency from assumed facility
  PUE, dates price observations, and states release/deployment uncertainties.
  Current equipment quotes never overwrite assumed historical prices.
- A separate per-model capital schedule uses 95% utilization, 15% ancillary
  cash opex relative to power, three-year straight-line depreciation, zero
  salvage, and a 25% annual return on installed capital. Infrastructure costs
  of $2/TH air and $5/TH hydro remain assumptions. This avoids including
  depreciation in both a 60% power gross-up and a separate capital schedule.
  The S21 XP+ Hyd example is approximately $124,859; other verified-specification
  examples span approximately $99,679–$178,764, with unverified equipment prices
  explicitly marked assumptions. Power, utilization, depreciation and equipment
  price sensitivities explain the spread rather than calibrating it away.
- Fleet weights still use a hashrate-at-release survival proxy, not measured
  global shipments. Three/five/seven-year survival sensitivities and same-date
  Cambridge comparisons expose this uncertainty.

### Historical electricity and fees

The new power alternative covers monthly observations from January 2015 to
July 2026. It scales the [EIA US industrial electricity series ESICUUS](https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T09.08)
to the [Cambridge June-2024 miner survey median of $45/MWh](https://www.jbs.cam.ac.uk/wp-content/uploads/2025/04/2025-04-cambridge-digital-mining-industry-report.pdf).
This is a retrospective US-indexed **proxy**, not observed global miner tariffs
or HK's proprietary ten-year series. It uses an assumed two-month release lag;
revisions are not vintage controlled and the later survey anchor was not known
at earlier dates. The latest proxy is approximately $0.05228/kWh. The flat
$0.05 case remains separately selectable for HK comparison.

Fees now come from mined-block averages in mempool.space's mining-history API,
with source timestamps and dated USD prices, instead of projected mempool
blocks. Older committed fee history can contain legacy projections; no observed
fee backtest is claimed. Historical dollar fees offset total dollar cost; future
BTC/block fee scenarios solve breakeven against subsidy plus fees. Fees transfer
existing BTC and do not increase issuance. Security-revenue figures disclose the
conditional BTC price and include zero-fee, latest-rate-constant and assumed
0.25-BTC/block scenarios.

### Refresh and validation

Cambridge comparison data now reaches 10 November 2026 using download v1.8.0.
The parser selects annual TWh columns explicitly: newer CSVs also contain GW,
and confusing them understates efficiency by 8.76 times. Core market and cost
inputs were refreshed on 11 November. Each source keeps its own observation
date, including on download failure; freshness is checked again in the browser.

The weekly World Model lane runs `validate_btc_model.py --require-fresh` after
fetching and building. Validation fails on stale core inputs, missing 2033
horizons, lost letter vintages, snapshot disagreement or valuation-boundary
violations. Unit tests cover units, halving jumps, fee revenue, historical
cutoffs, failed-refresh cache preservation and dated equipment quotes. The
production renderer and event binding are exercised on desktop and mobile by
`_system/scripts/tests/check_btc_model_browser.py`; it needs Playwright/Chromium
and writes screenshots outside the repository.

The near/long horizon controls change emphasis, not a valuation formula or a
claimed date of an economic regime change. Both raw model paths remain visible;
cost is dynamic support subject to shutdowns and difficulty adjustment, and
demand is never clipped to it. ETF and treasury-company flow models remain
outside this update.

## Live prints versus HK commentary

| Band | Reconstruction | HK Q2 2026 commentary |
|------|----------------|------------------------|
| Average-fleet all-in | **$57,101** (17 Sep 2026) | $65,000 |
| Fleet efficiency | 14.7 J/TH | Implied ~16 J/TH at ~915 EH/s |
| Network hashrate | 874 EH/s | ~915 EH/s at the print |
| 2024-04-20 all-in | $66,497 | Near their $65k identity |
| 2023-08 all-in | $19,855 | Not the old constant-16 print (~$11k) |
| Electricity only | $34,261 | ~60% of all-in |
| SOTA cash | $42,728 | n/a |
| SOTA + 25% ROIC | $89,288 | ~$117k / ~$149k on two current models |
| Mixed 2028 floor | **$138,184** | $130,000 naive 2× |
| Naive 2× 2028 | $114,202 | $130,000 |
| Mixed 2032 floor | $342,606 | Not published |
| Demand path 2028 | unchanged (k = 4.0) | $270,438 (k a touch under 6) |

The $57k versus $65k gap is hashrate (874 vs ~915 EH/s) plus a slightly more efficient mixed fleet (14.7 vs 16 J/TH). The identity is the same. We did not hard-code 16 J/TH.

Spot on 17 Sep 2026 is $76,210. That sits above the average-fleet floor and below SOTA-plus-25%-ROIC. Average miners are cash-profitable. New machines with a 25% ROIC hurdle are not earning that return at this spot.

## What this is not

- Not a 24-month or 6-year price target attributed to Hauck.
- Not a change to demand \(k\).
- Not a Power Zone contract.
- CBECI TWh ends 12 Nov 2025 and is stored as a comparison series. Primary fleet J/TH is the ASIC vintage mix.

## Overlays

FRMO, MSTR, CMSG, MARA, CLSK, GLXY get `btc_overlay.mining_economics_context` with these bands. Deep-dive refresh will render them under Bitcoin economics. Still context only.
