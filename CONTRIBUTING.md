# Contributing to single-stock-investments

This repository is the one hub for Magis Capital Partners research. Drew, Michael, and both owners' Cursor and Grok desk bots add to it and update it. `SOURCES.md` says where the data lives; this file says how a change gets in. The full table of who may write what is `docs/WRITE_MAP.md`.

## The three rules

1. **Everything lands by pull request.** Humans use any branch name. Cursor research agents use `cursor/`. Grok desk bots use `grok/<desk>/<yyyy-mm-dd>-<slug>`. The CI commit action is the only thing that pushes to `main` directly.
2. **Bots write data, never code.** A `grok/` pull request may touch only the paths in the write map's data allowlist. `check_contributor_paths.py` rejects anything else, and the pull request waits for a human. Code from a bot is reviewed like code from a person.
3. **A headline is never a term.** A number in a register, a brief, or a ledger names its filing or provider and the date it was read. An estimate carries a confidence. What was not read stays null.

## Where a change goes

| Kind of change | Path | Checked by | Merged by |
|---|---|---|---|
| Desk brief (ranked hits from a desk bot) | `_system/data/desk_briefs/<desk>/<date>.json` | `check_desk_briefs.py` | Automerge on a `grok/` branch when checks pass |
| Lesson or proposal | `_system/memory-hub/research-equity/daily/<date>.md`, at most three `[PROPOSED]` bullets per session | Hub README rules | Automerge on a `grok/` branch |
| Separation terms read from a filing | `_system/data/separations/separation_registry.jsonl` (new rows) or `separation_amendments.jsonl` (new versions) | `check_separation_universe.py --strict` | Automerge on a `grok/` branch |
| Short idea | A row in `_system/research/short-alpha/candidates.json` (`origin: desk_note`) plus the narrative note in the private research vault, pointed to by `note_ref` | `build_short_alpha_dashboard.py --check` | Automerge on a `grok/` branch |
| Short scorecard row | `_system/reference/activist-reports/short_scorecard/` | folder README | Automerge on a `grok/` branch |
| VIC text | `{TICKER}/third-party-analyses/vic/*.md` | `third_party_inventory.py` | Automerge on a `grok/` branch |
| PDF | Drive `Admin/Intake/{Kind}/{TICKER}/` via `drive_intake_drop.py` | Drive Intake Sync, 14:41 UTC | Not a git change |
| Ticker research | `{TICKER}/research/` | Provenance manifest gate | Automerge on a `cursor/` branch |
| Code, workflows, frameworks, schemas | Anywhere else | `python-tests.yml`, lints, graph invariants | Human review, then merge |
| Beliefs, capital, approvals | `_system/memory/MEMORY.md`, `human_decision.json`, `_system/reviews/approved/` | None | Drew only |

## Writing an entry (adopted from Michael's short-selling desk)

- One idea per file or row. Two tickers means two entries.
- Never rename a merged file; the name is the link.
- Figures need a source and the date they were read. A borrow reading is a reading on a date, not a standing fact.
- Move `updated_on` on every material edit. Leave `added_on` alone.
- Do not paste copyrighted text. Paper notes are summaries in our words with a citation.
- Do not weaken a schema to make one note pass. Fix the note.
- Fictional examples are examples. They are never migrated into a live ledger.

## Before you open the pull request

```bash
python _system/scripts/check_contributor_paths.py --head-ref <your-branch> --files <changed-paths.txt>
python _system/scripts/check_desk_briefs.py          # if you added a brief
python _system/scripts/check_separation_universe.py --strict   # if you touched the register
python _system/scripts/build_short_alpha_dashboard.py --check  # if you touched the short ledgers
python _system/scripts/validate_sources.py           # if you touched SOURCES.md or sources.json
python -m pytest -q _system/scripts/tests            # if you touched code
```

## What never goes in

- Credentials, account ids, tokens. Secrets live in Cursor Cloud Agents secrets or `_secrets/` (ignored).
- Licensed PDFs or book scans. Catalogue pointers only; text extracts go to the private research vault.
- Personal trades, balances, brokerage mail, private correspondence.
- Anything that contacts the IB Gateway. Rule 0 and Rule 9 in `CLAUDE.md` have no exceptions.
- Files over a few megabytes. Raw caches are reproducible and ignored; the compact ledger is what gets committed.

## Access

| Who | Access |
|---|---|
| Drew | Admin. Approves beliefs, capital, approvals, rulesets, secrets. |
| Michael | Maintain. Reviews code with Drew; owns the Michael sleeve notes and the reverse-split strategy decisions. |
| Each desk bot | A fine-grained token scoped to this repo with contents and pull-request write, created by its owner under their account, named after the bot (`grok-drew-special-situations`, `grok-michael-short-selling`), stored in Cursor Cloud Agents secrets. |

`main` is protected against force pushes and deletion. A "require pull request" rule is not in force: on this GitHub plan the repository's own Actions cannot be given a bypass, and without one every scheduled lane's commit would be rejected. Instead `.github/workflows/main-push-guard.yml` opens an issue whenever anyone other than Drew or the repository's Actions pushes to `main` directly. Detect, not block; the pull-request path above is the contract.
