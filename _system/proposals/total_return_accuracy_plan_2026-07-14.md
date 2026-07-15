# Dividend-accurate total-return plots

## Current audit

The existing plot is not decision-grade. It uses raw Yahoo closing prices, places annual distribution totals on the last trading day of each year, can overwrite multiple distributions in one year, and calculates the chart and annualized return with different formulas. It neither distinguishes special dividends nor proves distribution-history completeness. TPL is therefore shown with zero cumulative distributions over a long history, which is plainly not an acceptable result.

## Return contract

One canonical wealth series must drive the chart, cumulative return, and annualized return. Default convention:

- begin with one share at the first valid close;
- use split-adjusted prices that exclude dividends, and normalize historical cash events to the same share basis;
- reinvest each cash distribution at the ex-date close (next valid close if the ex-date is not a trading day);
- grow shares by `cash distribution per share / reinvestment price`;
- calculate annualized return from the same ending wealth index using actual calendar days;
- display nominal pre-tax return in the security's listing currency unless the user selects an FX-adjusted view.

## Canonical event ledger

Store every event separately: ticker, ex-date, record date, pay date, amount per share, currency, type, split factor where applicable, source URL/path, source tier, retrieval date, and reconciliation status.

The implemented contract is `_system/templates/distribution_event_schema.json`; ticker ledgers live at `{TICKER}/research/distribution_events.json`.

Types must include regular dividend, special dividend, trust distribution, return of capital, liquidating distribution, stock distribution, spin-off, and split. Multiple events in one year are additive; none may overwrite another.

Source priority is company and regulatory filings, then exchange records, then a market-data vendor. Vendor dividend and split events are useful discovery inputs, not sufficient proof for unusual or large distributions.

## Implementation phases

### Phase TR0 — freeze definitions and fixtures

Document the return contract above. Create fixtures for TPL special dividends, a non-dividend stock, a split, a monthly distribution trust, a return-of-capital event, a spin-off, and a foreign-currency security.

### Phase TR1 — build and reconcile the event ledger

Ingest vendor dividend/split events, then reconcile them against company and filing evidence. Give each ticker coverage start/end dates and a completeness status. A series cannot be called complete when price history begins before verified distribution history.

### Phase TR2 — replace the calculation engine

Build a daily wealth index from split-normalized raw prices and the event ledger. Use that same series for cumulative and annualized total return. Keep price-only return as a separate comparison. Add a benchmark through the identical convention.

### Phase TR3 — special situations

Treat ordinary and special cash dividends identically in wealth math but disclose their contribution separately. Include return of capital in economic return while labeling it for tax interpretation. Value spin-offs as a linked distributed security rather than silently dropping them. Add FX conversion only as an explicit investor-currency view.

### Phase TR4 — validation gates

Require tests for split invariance, multiple same-year distributions, exact ex-date timing, no adjusted-close double counting, chart/summary identity, missing-event blocking, and special-dividend contribution. Reconcile ending wealth against a reputable adjusted-price series within a documented tolerance; investigate rather than force a match.

### Phase TR5 — dashboard redesign

Show total-return wealth, price-only wealth, and benchmark on one indexed chart. Add a contribution strip for regular dividends, special dividends, and other distributions. Display data coverage, reinvestment convention, currency/FX basis, event count, last reconciled date, and source status beside the plot. Use `partial` or `evidence blocked` visibly when the ledger is incomplete.

### Phase TR6 — rollout

Start with TPL because its specials expose the present error, then validate the other fixtures, holdings, and watchlist. Only after fixture and reconciliation gates pass should the old plots be replaced in bulk.

## Acceptance criteria

- TPL no longer reports zero distributions when verified dividends exist.
- A special dividend changes wealth on its actual ex-date and is separately disclosed.
- The displayed annualized return exactly derives from the plotted wealth endpoints.
- Splits do not change economic return.
- Missing distribution history prevents a `complete` badge.
- Every plotted cash event is traceable to a dated source record.
