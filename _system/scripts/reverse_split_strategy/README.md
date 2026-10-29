# Selected announcement-first strategy dashboard

User-selected research candidate as of October 29, 2026:

- At least the second documented reverse split for the same SEC issuer.
- Original point-in-time financial distress score at least 60; unknown or stale scores exclude entry.
- First eligible 09:30 Eastern opening after filing-date-plus-one-day availability plus five minutes, strictly before the effective split date. Exact press-release timestamps are unavailable.
- Five exchange sessions including entry; planned cover at the fifth session close.
- No price stop, profit target, rally veto, separate cash-burn/dilution gate or size multiplier.
- $25,000 reference short notional before constraints; strict SSR and one open position per issuer remain enforced.

Five sessions is the selected historical default for this specific candidate, not a validated universal optimum. The UI includes 10 and 20 sessions, split-day and post-split timing, constrained sizing, and three cost sensitivities: 54 complete scenarios.

## What is published

`dashboard/data/reverse_split_strategy/` contains a manifest, summary and 54 individually loaded scenario files. Each has the complete screening trace, trade ledger, modeled executions, cash flows, daily position/account marks, financial source observations, prior split evidence and reconciliation. The summary documents the score formula, fee schedule and metric definitions. SHA-256 bindings prevent mixed-build display.

The selected base case has 21 trades / 20 issuers, $85,174.31 net marked P&L, $18,982.17 maximum closing drawdown and 1.363 conditional daily Sharpe. Its modeled margin peak exceeds $6.26m, and 13 trades assume adjusted fractional covers. Account CAGR and Calmar are withheld. The constrained five-session comparison has four entries and -$133.34 marked net P&L with three remaining obligations. Neither view establishes approved locates, executable fills or an implementable account return.

Raw bar databases, broker records and machine paths are not published. The derived hypothetical trade paths are published at the user's explicit request. No execution policy or trading authority is changed.

## Reproduce and verify

The exporter only reads cached local research. It requires the original ignored price database, event cache, frozen sizing features and completed stop study; it performs no data acquisition. A missing input fails closed. `engine.cjs` is an isolated audit extension of the frozen sizing engine. Its monetary calculations are checked against all 54 corresponding no-stop study scenarios before publication.

```powershell
node _system/scripts/reverse_split_strategy/export.cjs
node --test _system/scripts/tests/test_reverse_split_strategy.cjs _system/scripts/tests/test_short_profit_program.cjs
```

The committed derived snapshots are sufficient to serve and test the dashboard in CI; CI does not need the ignored research caches. The normal static Pages artifact builder includes these files. Routine dashboard refreshes do not replace this explicitly frozen strategy snapshot.

For optional browser integration QA, serve `dashboard/` with a local HTTP server and run:

```powershell
python _system/scripts/reverse_split_strategy/browser_qa.py --base-url http://127.0.0.1:8767
```

This uses installed Chrome and Playwright and writes screenshots/downloads only under the ignored `local/strategy_dashboard_qa/` directory. It verifies both the Strategies → Reverse-split short route and the Shorts → Backtest → Strategy tab, all seven sections, CSV export, scenario switching and a 390px viewport.

The main direct route is `#/strategies/reverse-split/overview`; `trades`, `metrics`, `assumptions`, `comparisons`, `screen` and `provenance` are directly addressable sections. In-page comparisons preserve current selections; a fresh page load starts with the user-selected default.
