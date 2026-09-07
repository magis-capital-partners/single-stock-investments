# Filing panels

Operating metrics that companies disclose in filings but that no XBRL extractor can
reach. Consumed by `fetch_theme_panel.py` via a theme series with
`"source": "filing_panel"`, `"panel": "<file>.csv"`, `"metric": "<column>"`.

## The one constraint that shapes every panel here

`read_filing_panel()` (`_system/scripts/fetch_theme_panel.py`) reads a panel by
`as_of` and `metric` column **and does not filter by ticker**. Put two companies'
values in the same metric column and they are silently interleaved into one
series that looks like a trend and is not.

So a multi-company panel gets **one metric column per company**
(`vmc_cash_gross_profit_per_ton`, `crh_aggregates_tons_mm`, ...), never a shared
`cash_gross_profit_per_ton` column plus a `ticker` column. Blank cells are skipped
by the reader's `float()` guard, so a row may fill in only one company.

## `aggregates_unit_economics.csv`

The metrics an aggregates thesis actually turns on -- tons shipped,
freight-adjusted price per ton, cash gross profit per ton. Not in XBRL, and the
wording differs by company, so this is curated by hand from the filings rather
than extracted:

- **VMC** states all three plainly in the 10-K business section, including a
  two-year comparison, which is why it has the fullest history here.
- **CRH** gives annualized aggregates sales volumes (total, Americas,
  International) but not price or unit profitability in the 10-K.
- **MLM** publishes average selling price **by division** in the 10-K
  (East / Central / Southwest / West) and reports consolidated shipments and
  gross profit per ton in its quarterly earnings release, not the 10-K. Its
  columns are therefore still empty; filling them means parsing the release.

`as_of` is the fiscal period end so the column reads as a time series; `filed` and
`source_path` record where each figure came from. Every value must be traceable to
the cited document -- never carry a number forward from memory or an estimate.
