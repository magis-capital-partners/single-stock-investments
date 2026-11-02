# Technical Analyst desk — self-grading

Pre-registered tests live in `grading_spec.json` (spec_version 1.0, registered 2026-10-30). `grade.py` (Python 3 stdlib only)
applies them to `run_log.jsonl` using only stored `tape_snapshots/<date>.json` rows and `index_announcements.json`.
It never computes a new indicator and never makes a buy/sell call: every number it writes is a stored close, a stored
field, or a difference of stored closes. Self-tests: `python3 test_grade.py` (synthetic fixture in a temp dir).

## Modes
```
python3 grade.py --register candidates.json [--retro] [--today YYYY-MM-DD]   # after each desk run
python3 grade.py --daily  [--today YYYY-MM-DD]                                 # every weekday after the snapshot lands
python3 grade.py --report [--out report_<date>.json]                           # weekly (Fridays)
python3 grade.py --backfill-retro                                              # one-off: tag pre-spec rows
```
`--eval-dir DIR` points at another store (default: the folder holding grade.py).

## candidates.json (one file per desk run)
```json
{
  "run_date": "2026-11-02",
  "source": "dashboard/data/technical_summary.json",
  "source_generated_at": "2026-11-01T22:10:00Z",
  "flags": [
    {"ticker": "AMZN", "kind": "tape",  "flag": "panic RSI 34.1", "lens_rules": ["TAPE-01"]},
    {"ticker": "PBT",  "kind": "index", "flag": "S&P 600 inclusion_candidate -5.25%", "index": "sp600", "action": "add"}
  ],
  "held": [
    {"ticker": "GOOGL", "reason": "TAPE-06 gap -11.7%", "counterfactual_flag": "capitulation_candidate rvol 5.41"}
  ],
  "baseline": {"n": 20, "exclude": []}
}
```
* `flags[].flag` is the posted text; the flag kind (capitulation, rsi_oversold, rsi_overbought, breakout, breakout_lost,
  z_stretch, z_trend, cmf, index_add/delete/migration, index_watch_removed, index_report) is parsed from it.
  `index`/`action` are optional overrides. `lens_rules` (FLOW-0x / TAPE-0x, or F#/M# aliases) feed the per-rule report.
* `held[]` rows get cohort `held` and are graded on the same test as a counterfactual (what the flag would have done).
  Without `counterfactual_flag` the kind is derived from the stored snapshot row; with no row they stay `unknown_no_snapshot_row`.
* `baseline` draws n names from that day's snapshot (excluding flagged/held names), seeded by
  `sha256("ta-baseline|" + run_date)`, and grades each under every tape test (`baseline_grades`).
* Idempotent per `run_date + ticker + flag`: re-running adds nothing and never changes an existing value.
  Prints the number of flag rows registered on its last line.

## Fields added to run_log rows (existing values are never rewritten)
| field | meaning |
|---|---|
| `cohort` | flag / held / baseline (absent on legacy rows = flag; legacy flag text containing "held TAPE-06" = held) |
| `flag_kind`, `flag_details`, `test_id`, `test_spec_version`, `test_window_sessions`, `test_deadline` | the pre-registered test |
| `base_as_of`, `window_end_as_of`, `persistence_as_of` | sessions (NYSE calendar for US names, weekdays for non-US) |
| `registered_retro` | true for rows tagged after the fact (pre-2026-10-30 rows, back-filled held/baseline rows) |
| `test_grade` / `test_graded_on` / `test_numbers` | pass / fail / no_data, date graded, the stored numbers used |
| `persistence_grade` / `persistence_graded_on` / `persistence_numbers` | secondary: still over threshold next session (held / faded / no_data) |
| `baseline_grades` | baseline rows only: grade under each tape test |

Legacy `grade` / `graded_on` keep their meaning (next-snapshot persistence, as the weekly scorecard used them); `--daily`
fills them from `persistence_grade` only when null. `verdict`, `verdict_by`, `drew_verdict` are never touched.
A row is never regraded once `test_grade` is set; a closed window whose stored row is missing grades `no_data`.

## Benchmark
SPY close from a stored SPY row when the snapshot has one. Snapshots before 2026-10-30 carry no SPY row, so the fallback
is the median of stored `context.market_move_5d_pct / context.beta_252d` across SPY-benchmarked rows with |beta| >= 0.5
at the window-end as_of (`bench_method` records which was used). Non-US names (benchmark 1321.T, IEUR, XIC.TO) use their own stored `market_move_5d_pct / beta_252d` (5-session windows only).

## Index tests
`index_announcements.json` lists provider announcements with `checked_through`. Index flags stay pending until
`checked_through` and today reach the deadline (Russell Dec 11 2026, S&P DJI / Nasdaq Dec 19 2026). Update the file
after each provider notice; never back-date `checked_through`.

## Report
Per rule id and per flag kind, split live / retro / all: registered, graded n, pass rate, date-matched baseline pass rate
(each run_date's baseline counted once), held counterfactual pass rate, persistence held/faded.
`under_review_candidate` = graded n >= 20 and pass rate <= baseline. It is a flag for Drew, not an automatic change.

## Known limits
* Snapshots store only names the desk already flagged, so the baseline pool is biased toward stressed names.
  Before same-day snapshots existed, retro baselines use earlier-flagged names with a stored window-end row.
* Breakout and 3-session tests need three consecutive daily snapshots; there were only two on 2026-10-30.
