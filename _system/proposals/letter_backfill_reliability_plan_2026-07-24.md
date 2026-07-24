# Letter backfill reliability plan (2026-07-24)

## Problem (confirmed)

Drive folder [`Letters/2026 Q2`](https://drive.google.com/drive/folders/1CtFKEdK0eTXZlY-t6bddds5rLSX5V7sO) had ~68 PDFs; vault/dashboard only showed ~19.

Root causes:

1. **PDFs are gitignored in research-vault** (`superinvestor-letters/**/*.pdf`). Only `.txt` extracts are committed.
2. **Download and extract were split across CI jobs**, so extract runners never saw the PDFs downloaded on prior runners.
3. **Skip logic only looked at local PDFs**, so every shard re-downloaded historical letters from scratch (`skipped ≈ 0`) and often never reached new quarter folders inside the 120-minute budget.
4. **`publish-dashboard` called `make letter-date-check`** after a `minimal` sparse checkout that did not include root `Makefile`, so dashboard rebuild never ran even when ingest partially succeeded.
5. **Sunday schedule used `--all` with no year window**, maximizing history work and starving current-quarter intake.

## Fix shipped (this PR)

| Change | Why |
|--------|-----|
| Skip download when nontrivial `.txt` already exists | Matches vault commit model; makes weekly runs incremental |
| Download + extract in the same `ingest-letters` job | Extract can see ephemeral PDFs before they are discarded |
| Recent-year default window on schedule (`year-1`) + Wed catch-up cron | New quarter drops finish every week |
| `quarter` / `since_year` / `full_history` workflow inputs | Manual focused intake (e.g. `2026Q2`) |
| Sparse checkout includes `Makefile`; publish calls Python directly | Publish gate cannot miss make targets |
| Publish job uses `pages` checkout (includes `dashboard/`) + `git add --sparse` | Staging rebuilt payloads cannot fail under sparse-checkout |
| `check_letter_drive_coverage.py` gate after rebuild | Fail the workflow when Drive≫vault for recent quarters |

## Keep it automatic (operating model)

### Cadence

- **Wed 15:00 UTC** — recent-year ingest (catch new drops mid-week).
- **Sun 16:00 UTC** — recent-year ingest + full publish/coverage gate.
- **Manual** — `quarter=2026Q2` (or `since_year=2026`) when a bulk Dropbox/Drive dump lands.
- **Quarterly** — optional `full_history=true` cold pass only when repairing deep history.

### Definition of done for a quarter folder

For `Letters/{YYYY Qn}`:

1. Vault `superinvestor-letters/{YYYY}Qn/*.txt` count ≥ 85% of Drive PDF count (coverage gate).
2. Absolute missing ≤ 25 (or justified non-letters / bad PDFs).
3. `dashboard/data/insights/letters.json` rebuilt and committed by `publish-dashboard`.
4. Coverage gate green in the same workflow run.

### Alerts / failure handling

- Coverage gate failure is a **hard fail** on `publish-dashboard` (visible in Actions).
- On fail: re-run `Letter Backfill` with `quarter=YYYYQn` (or `since_year=YYYY`), do not expand to full history first.
- If Drive index is stale, publish refreshes `build_drive_filename_index.py` before the gate.

### Follow-ups (not blocking this intake)

1. **Artifact/cache for PDFs (optional)** — only if OCR cost forces multi-job extract again; prefer keep single-job ingest.
2. **Classify non-letter PDFs** in quarter folders (white papers, decks) so coverage denominator excludes them.
3. **Dashboard UI badge** — show latest `2026Qn` letter count vs prior quarter on the letters page.
4. **Hub daily note** — when coverage fails twice in a row, append `[PROPOSED]` to research-equity `daily/`.

## Manual verification for this incident

```bash
# After green CI for quarter 2026Q2:
python _system/scripts/check_letter_drive_coverage.py --quarter 2026Q2
# Expect vault≈drive and OK.
```

Dashboard should then list the new 2026Q2 manager letters (Engine, FourSixThree, 1 Main, etc.).
