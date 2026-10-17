# Darwin Covered Call: lookup table

`lookup_v1.json` holds the historical evidence behind the Darwin Covered Call page
(`#/strategies/darwin`, built by `_system/scripts/build_darwin_covered_call.py`).

Each cell is the average net result to a stock holder of selling one covered call,
for a tenor bucket (7/14/21/35/42 days), a call delta (10–50) and the stock's
condition score (0–4). Net means the premium received (mid minus a quarter of the
quoted spread, less $0.65 a contract) minus intrinsic owed at expiry, in basis points
of the stock price. Calls whose window contained an earnings report are excluded:
earnings is a veto on the page, not a cell.

## Where it comes from

- 698,668 calls on point-in-time S&P 500 members, 128 monthly entry dates,
  January 2016 to August 2026.
- Quotes: ThetaData end-of-day option chains pulled through NY4's terminal after
  hours for research. Only these aggregates are stored here; raw quotes are not
  published (`_system/trading/portfolio_hub/MARKET_DATA_SOURCES.md`).
- Conditions were kept only if their sign held in both 2016–20 and 2021–26. A
  walk-forward check (cell averages from earlier years applied to each year,
  2019–2026) ranked calls correctly out of sample; the deciles are in the file's
  `validation` block. Expect about half the in-sample edge.

## Refreshing it

The cells change slowly and are rebuilt by hand from the research pipeline
(`_external/darwin_vol_research/work/cc_build.py`, `cc_analysis.py`, `cc_lookup.py`
on the research workstation, outside the repository). Re-derive it once a year, or
if the live page's ranked calls stop resembling the validation deciles.
