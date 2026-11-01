# Activism desk eval cases

Known-answer cases for the activism lane. Each line of `cases.jsonl` is one situation the desk should have called the same way. `runs.jsonl` starts empty.

## Point in time

Each case has an `as_of_date`, the morning the desk first had the document. A replay may only use filings and feed data dated on or before `as_of_date`, with the expected answer kept hidden until the replay is scored.

A filing accepted during the day is dated the next morning. The Edison International short report is dated the morning it was published.

## Scoring

Score each item on its own, right or wrong: subject issuer, filer, activist yes or no, label, and post or drop.

Activist yes means an outside campaign or an activist short. A control filing, a governance agreement, a passive holding, and a name outside the universe are activist no.

Labels are `campaign`, `control filing`, `governance agreement`, `passive`, `short report`, and `not_in_universe`.

A short report is also scored on timeliness. Posted the morning of `as_of_date`, or the next morning, is on time.

## Run log

`runs.jsonl` is one JSON object per line, with the fields `date`, `case_id` or `accession`, `desk_verdict`, `drew_verdict` (blank until Drew marks it), `correction_type` (`memory`, `skill`, or `new_case`), and `notes`.
