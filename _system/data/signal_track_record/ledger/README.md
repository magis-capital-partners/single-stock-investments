# Signal track record ledger

One CSV per month of every technical signal the dashboard published, written by
`_system/scripts/build_signal_track_record.py` in the nightly `technicals` job
(`.github/workflows/data-pipeline.yml`).

- Rows are keyed by `(as_of, kind, ticker)`. The first write wins, so a re-run
  never rewrites what was published.
- `kind` is `stock` (per-stock fear snapshot), `market` (the SPY market-fear
  read) or `ladder` (the daily capitulation ladder rows).
- `r5/r21/r63` are returns from the next session's close and `b*` are SPY's over
  the same window. `mae63` is the further drawdown within 63 sessions; `vol21`
  is realized next-month volatility. All are filled when the horizon matures.
- `fresh=0` marks a preserved (stale) snapshot. It is logged, never graded.

Do not edit by hand. The dashboard summary is
`dashboard/data/signal_track_record.json`.
