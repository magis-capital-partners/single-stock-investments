# Write map

Who may write what in `single-stock-investments`, in which format, checked by what, consumed by whom. The machine copy of the bot allowlist is `GROK_DATA_ALLOWLIST` in `_system/scripts/check_contributor_paths.py`; `_system/scripts/tests/test_contributor_paths.py` keeps this table and that list in step.

Branch prefixes: humans use any branch; Cursor research agents keep `cursor/`; Grok desk bots use `grok/<desk>/<yyyy-mm-dd>-<slug>`; CI commits through the `commit-main` action.

| Actor | May write | Format and checker | Gate | Consumer |
|---|---|---|---|---|
| **Drew** | Everything, by pull request. Sole approver of `_system/memory/MEMORY.md`, `human_decision.json`, `_system/reviews/approved/`, framework files, rulesets, secrets. | Existing lints and `python-tests.yml`. | Self-review on code; none on data drops. | Whole repo. |
| **Michael** | Same research paths as Drew: ticker `research/`, Short Alpha ledgers, separations register seeds, desk briefs, `_system/reviews/pending/`, hub daily notes. Owns the Michael sleeve notes (D1) and `_system/data/reverse_splits/decisions.jsonl`. Code by pull request with Drew's review. | Same. | `reviews/approved/`, `MEMORY.md`, `human_decision.json` stay Drew's. | Same. |
| **Grok desk bots (either owner)** | The data allowlist below. | `check_contributor_paths.py`, then the checker for each path. | Automerge when every check passes and only allowlisted paths changed. Anything else waits for a human. | Dashboard Inbox and desk panels; review queue; the separations and short-alpha lanes. |
| **Cursor research agents** | `{TICKER}/research/` via `cursor/*` pull requests with a provenance manifest. | Existing automerge gate. | Existing. | Existing. |
| **CI** | `dashboard/data/`, derived `_system/data/` files, vault extracts. | Validators in each job. | None. | Dashboard. |
| **Nobody but a human in chat** | IB Gateway, live orders, `reviews/approved/`, `MEMORY.md`, `human_decision.json`, new Drive roots, licensed PDFs. | `CLAUDE.md` Rule 0 and Rule 9; `human-quality-filter.mdc`. | Human. | n/a |

## Bot data allowlist

| Path | Format | Checker | Consumer |
|---|---|---|---|
| `_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json` | `_system/data/desk_briefs/schema.json` | `check_desk_briefs.py` | `build_desk_briefs.py` → Inbox "Desk briefs" |
| `dashboard/data/desk_briefs.json` | Rebuilt by `build_desk_briefs.py` in the same commit as a new brief | `check_desk_briefs.py` (desk paths must match the rebuild) | Inbox "Desk briefs" |
| `_system/memory-hub/research-equity/daily/<YYYY-MM-DD>.md` | `[PROPOSED]` bullets, at most three per session | Hub README | Human promotion |
| `_system/memory-hub/research-equity/CONTEXT.md` | One desk line under `## Desk` per session | Hub README | Humans and bots at session start |
| `_system/data/separations/separation_registry.jsonl`, `_system/data/separations/separation_amendments.jsonl` | Append-only rows with filing accessions | `check_separation_universe.py --strict` | Separations lane, Special Situations desk |
| `_system/research/short-alpha/candidates.json` | Rows with `origin: desk_note` or `reverse_split_research` | `build_short_alpha_dashboard.py --check` | Shorts tab |
| `_system/reference/activist-reports/short_scorecard/` | Folder README | Folder README | Short Alpha leads |
| `{TICKER}/third-party-analyses/vic/*.md` | GROK.md text-only VIC | `third_party_inventory.py` | Ticker folder, Insights |
| `_system/reviews/pending/*.md` | Review note | Human gate | `reviews/approved/` by Drew |
| `_system/memory/daily/<YYYY-MM-DD>.md` | `[PROPOSED]` bullets | `build_memory_triage.py` | Routed observations |

Everything not listed is code or a human-gated file. A `grok/` pull request that touches it is held for review.

## Outside git

| Surface | Who | How |
|---|---|---|
| Drive `Admin/Intake/{Kind}/{TICKER}/` | Any bot with the service account | `drive_intake_drop.py`; imported daily at 14:41 UTC |
| Drive `Letters/`, `Investment Wisdom/` | Michael's intake bot | `_system/agents/MICHAEL.md`; needs vault write |
| D1 sleeve notes and ideas | Drew, Michael | Dashboard sign-in; `POST /api/v1/sleeves/notes` |
| Private research vault `short-research/{TICKER}/` | Short desk bots and humans with vault write | Narrative for a short idea; SSI holds the pointer |
