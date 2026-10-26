# Autonomous compounder research IRRs

The canonical 37-company list has a separate unattended research-estimate lane.
It collects dated quotes and annual fundamentals, reconciles reporting and
listing currencies, constructs three dated shareholder cash-flow scenarios,
validates them with the existing canonical schedule/IRR mathematics, and
publishes the results directly. No proposal, committee vote, or human approval
is required to collect, calculate, refresh, publish, or retry this product.
Existing issuer valuation contracts and capital decisions retain their meaning.

## Run and replay

```
python _system/scripts/autonomous_compounders.py --collect
python _system/scripts/autonomous_compounders.py --check
```

`--tickers` supports bounded repairs. `--as-of YYYY-MM-DD` supports replay of
already collected observations; it is not a point-in-time historical backtest
of provider data whose original publication dates are unavailable. SEC facts
filed after the supplied date are excluded. Provider retrieval dates and
economic periods are disclosed separately.

The scheduled GitHub workflow runs at 08:23 and 18:23 New York time on weekdays.
It can also receive `refresh-autonomous-compounders` repository dispatches.
It runs regression tests, collects all names, verifies source-bound replay and
the served core/detail payloads, then commits through the existing main publisher.
Collection failures preserve the previous source cache; expired prices or
invalid economics withdraw the return and retry on the next run. A dashboard
rebuild also withdraws an expired cached return. No `[HUMAN REVIEW]` parking lot.

## Inputs and source acceptance

Compact input observations live in
`_system/reference/market-data/compounders/{TICKER}.json`. Each retains provider,
source URL, concept/locator, economic period, currency, retrieval date and, when
available, filing date. Annual cash-flow and earnings facts require a 300–390-day
duration. Quarter and YTD values cannot substitute for annual values. SEC
primary concepts override provider observations only for the same field,
period and currency. Provider fundamentals are identified as secondary sources,
not relabelled primary facts. Raw SEC/PDF responses are not committed.

Quotes must be positive, dated within seven days, and match the requested
listing symbol. GBP pence are converted to pounds explicitly. Reporting/listing
currency differences require a fresh dated FX pair. Annual economic inputs
older than 550 days or future-dated observations cannot publish.

Lifco maps to `LIFCO-B.ST`; registry identity remains `LIFCO.ST`. FRMO uses its
issuer's dynamically discovered annual report. Its parser checks year columns,
parent-attributable equity/income, diluted shares, and the explicit thousands
scale. A layout change becomes a collection failure, never an inferred number.

## Versioned scenario assumptions

These are mechanical estimates, not issuer guidance or forecasts approved by an
analyst. The complete assumptions, sources, date-by-date cash flows, terminal
proceeds, currency conversion and hurdle entry prices are visible in the stock
workspace. Negative returns are valid outputs and remain visible.

* **Retained owner cash:** annual operating cash less reported capex and observed
  stock compensation. Thirty-five percent is retained for acquisitions and
  other reinvestment; 65% is hypothetically distributed. Historical aggregate
  cash growth informs the scenarios, bounded at retention × 25% incremental
  return in the base case and retention × 35% in the high case. Growth is not
  augmented by future buybacks. Exit equity/cash multiples are 12/18/24. If SBC
  is unavailable, a disclosed 1% annual dilution assumption is applied instead
  of silently treating SBC as zero.
* **Parent book value:** holding companies, material minority structures, and
  companies with nonpositive current owner cash use parent equity and earnings
  with period-matched share counts. Parent ROE is bounded at 0–12% in the base
  case, with downside/upside variations; 80% of earnings are retained and 20%
  hypothetically distributed. Exit price/book multiples are 0.75/1/1.25, with
  a disclosed 1% annual dilution scenario. This is a conservative book-based
  sensitivity; it is not a substitute for a complete holding-company SOTP.
* **Deterra royalty distributions:** reported dividends divided by matched
  ordinary shares; distribution growth of -5%/0%/3% and terminal distribution
  multiples of 12/18/24. Optional development royalties are not added.

All routes use seven explicit annual dates and include terminal proceeds in the
last cash flow. There is no extra net cash/debt addition or present-value
annualization. Entry prices discount the same schedules at each displayed
hurdle. Scenario assumptions are versioned in code and retained in the output.

The existing Copart/ICE/SPGI owner-earnings proof bridge separately reads its
undiscounted post-reinvestment cash nodes. Changing a present value alone cannot
change that diagnostic. It adds no cash/debt to an equity terminal multiple.

## KPI and quality coverage

Annual financial observations are also published to the existing operating-KPI
store for every company, with fiscal period end retained. Existing monthly and
quarterly issuer observations and their revision history survive. Coverage can
fall back to a dated observation already in the legacy KPI ledger. Company
requirements remove irrelevant metrics such as membership fees for Ferrari or
Hermès, rated issuance for MSCI, and insurance float for Brookfield.

Issuer-specific traffic, volume, retention and similar metrics remain separate
monitoring evidence when they are not disclosed in machine-readable financials;
their absence does not block a mechanical research IRR. Capex ratios are
computed from comparable facts. Moat, governance, pricing power and incremental
ROIC are not fabricated from generic ratios and are not manual publication
gates for this product.

## Artifacts and tests

`_system/data/autonomous_compounders.json` is the source-bound estimate report.
`dashboard/data/core.json` carries compact labels and scenario returns; ticker
shards carry the full calculation. The normal dashboard builder preserves this
lane. `--check` verifies complete universe coverage, deterministic input replay,
and equality with the served payloads.

The regression suite covers stale/future prices and facts, failed providers,
quarter/annual confusion, FX, funded scenarios, holding-company routing,
partial refresh preservation, expiry, the specialist proof bridge, and UI
labels/negative returns. Investment execution remains a separate activity.
