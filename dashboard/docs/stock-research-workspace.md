# Stock research workspace

Every covered listing uses the same six-tab one-pager. Company profiles select
appropriate starting metrics. Missing data remains a named gap; a listing never
inherits another issuer’s financials simply because a ticker matches.

## Reading a stock

- **Summary:** thesis, countercase, monitoring conditions, total shareholder
  performance and a concise financial/model snapshot.
- **Financials:** metric search, chart presets, annual/quarterly/TTM, 5/10/20/all
  history, growth, percentage-point changes, indexed views, exact statement
  tables, dated sources and CSV/SVG/PNG exports. Save chart templates or copy a
  link. Compare companies, run compound screens and maintain watchlists here.
- **Business & KPIs:** sector drivers, operating observations, capital
  allocation, a reconciled earnings flow, business/geographic segment charts,
  share-count history and peer comparisons.
- **Valuation:** existing dated issuer forecasts, editable research worksheets,
  bear/base/bull cash flows and IRRs, historical multiples, reverse valuation,
  implied margins, price/multiple sensitivity and named saved scenarios.
- **Research:** calculated answers with source citations, retrieved passages,
  fund letters, podcasts, filings, results/transcripts, institutional holders and
  verified insider transactions. The complete company source library remains.
- **Risks & updates:** falsifiers, developments, custom valuation/KPI thresholds,
  latest-data checks and the private persistent alert inbox.

## Financial definitions and dates

The extended company dataset drives charts, financial tables, peer comparisons,
screens and alerts. Recorded underwriting keeps its original source/date and
authority. A source refresh does not silently approve a new investment case.

- TTM flows require a full fiscal year or four consecutive compatible quarters.
  Average shares are duration weighted; balance-sheet stocks are never summed.
  Margins divide aggregate amounts. YTD and discrete-quarter observations are
  separate operands, including when both appear for the same period end.
- Latest comparative/restated and first-filed histories are separate views.
  First-filed per-share TTM is withheld without a compatible split basis.
- Monthly historical valuations use filings available **before** that price
  session. An unknown publication time never makes a same-day filing usable.
  EPS/share counts are aligned to the captured split basis. Market caps use
  then-available reported shares, explicitly an estimate of daily shares.
  P/E uses that market cap divided by then-available TTM common net earnings;
  it is not a mix of trailing EPS conventions. Quarterly EPS derived by
  subtracting rounded YTD EPS is withheld. Comparable per-share charts retain
  original reported values and the split factors in their source tables.
- Multiple share classes, unverified ADR conversions and missing historical FX
  withhold affected historical ratios. Price multiples with nonpositive
  denominators are N/M; cash-flow/earnings yields can be negative.
- Enterprise value requires compatible debt/cash and evidence for other claims.
  A missing noncontrolling-interest tag is not assumed to mean zero. An exact
  same-date balance-sheet identity may establish a zero residual claim.
- Bank/insurer/holding-company cash flows are not classified as industrial
  distributable FCF. Funds and contingent claims retain their own model gates.
- Peer values retain original currencies and fiscal dates. Indexed histories
  compare trajectories; they do not imply FX conversion or aligned fiscal years.
- A historical ratio older than 45 days does not become a current screen/alert
  value. Source gaps never pass numerical filters as zeroes.

## Expectations, segments and operating supplements

Use **Financials → Import / export research data** for sourced JSON supplements
or estimate CSV. Research assumptions, management guidance and street consensus
are distinct kinds. A subscription to a terminal does not grant a data API
license. No unavailable consensus, segment or transcript is fabricated.

Estimate CSV columns:

```
ticker,kind,metric,frequency,period,as_of,value,unit,source_url
```

`kind` is `research`, `management` or `street`; `frequency` is `annual` or
`quarterly`. Period and publication/capture dates use `YYYY-MM-DD`. Amounts use
original reporting units, not millions unless the unit says so. Every row needs
its original source URL. Import an additional snapshot to retain revisions.
Beats/misses compare pre-result consensus with first-reported actuals of the
same metric, period, frequency and unit. When an exact results-release date is
unverified, only snapshots captured before the fiscal period ended qualify.
Later restatements cannot move the original results date forward.

JSON supplements contain `expectations`, `segments`, `series` and/or `events`.
Segments need `kind` (`business` / `geography`), name, metric, unit and sourced
points. Operating series need an identifier, label, unit, statement,
annual/quarterly points, period and source for every value. Segment totals are
not presumed additive because intersegment eliminations and definitions vary.
Workspace exports separately preserve personal templates, screens, watchlists,
scenarios, imports and alert rules.

## Storage and operation

Raw captures and full snapshots stay outside Git. The initial fallback uses
private artifact receipts, parts no larger than 8 MiB, startup core below
6,000,000 bytes, and hosted JSON assets no larger than 20 MiB. Citations are
deduplicated losslessly. Publication loads one private part at a time.

`Stock financial charts refresh` runs after the US close using public/licensed
HTTPS inputs. It preserves per-company source caches, publishes immutable R2
shards, verifies stored/raw hashes and sizes, and switches the release pointer
only after all shards verify. A single-ticker manual refresh is supported.
Financial updates do not rebuild the full letters/podcast library or commit
source catalogs. The authenticated API falls back to the checked publication
snapshot if a live release cannot be verified.

Saved work is cached in the browser and synced to the verified owner’s D1 row,
with revision conflicts protected. Scheduled monitoring reads the same financial
index, deduplicates events by rule/observation and retains an immutable release
receipt. The inbox is owner scoped. There are no external messages, market-data
terminal sessions, Gateway connections or trades in this workflow.

## Verification

Run the stock Python/display suites, Cloudflare research/auth tests and the
full-universe audit before release. The audit checks listing identities, source
availability dates, finite values, ordering, N/M rules, profile gates, coverage
and file sizes. Validate browser interactions at desktop/mobile breakpoints,
including downloads, saved views, models, comparisons and alerts. Deployment
keeps the existing authentication, privacy boundary and size guards enabled.
