# Tape and index desk eval set

Point-in-time record for the Technical Analyst (tape_index) desk. Research only. Nothing here is a position, a price target, or an input to a base return.

`grok/tape_index/index-backfill` was not on origin when this folder was added. File names below are the contract if that branch lands later.

## Files

- `run_log.jsonl` is one JSON object per posted flag.
- `test_set.json` holds forward index cases, known-answer backtests, and held names.
- `tape_snapshots/YYYY-MM-DD.json` is the technical print stored for that run date. `2026-10-29.json` is the first snapshot.

## Run log

Each row has `run_date`, `ticker`, `kind`, `flag`, `source`, `verdict`, `verdict_by`, `graded_on`, and `grade`.

`kind` is `tape` or `index`. `verdict`, `verdict_by`, `graded_on`, and `grade` stay null until the flag is graded.

New rows also carry the source file's `generated_at`, `owner_desk`, and the lens rule ids used for that flag. Rows already in this file predate those fields and do not have them.

## Test set

`forward_index_cases` are names logged before the provider announces. `known_answer` stays null until the grade window closes.

`backtest_known_answers` are cases whose answer is already known.

`held_names` are names the desk refused to rank, with the reason, and a verdict that stays null until graded.

## Grading

Grade each flag point-in-time against the feeds as committed on `run_date`. A later refresh of a feed is not evidence the desk had that day.

The primary metric is index catch rate: index events on book names flagged before the provider announcement, divided by all such events announced. False flags count against the desk.

Secondary metrics are tape-flag persistence (the share of tape flags still over the stored threshold in the next `technical_summary`) and held-name verdict accuracy. Scoring is weekly, on Fridays. A correction becomes a memory note, a threshold or hold-rule change in the digest routine, or a new case in `test_set.json`.
