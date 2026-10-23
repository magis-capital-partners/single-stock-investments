# Desk briefs

Ranked output from the Magis desk bots, one JSON file per desk per day, checked by
schema and consumed by the dashboard Inbox. Proposal:
`_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md` ("Desk brief contract",
Phase 1). Desk mandates: `_system/agents/DESKS.md`. Prompts:
`_system/prompts/grok_scan_agents.md`, `_system/prompts/grok_stahl_agent.md`.

A brief is research only. It carries `research_only: true`, `in_base_irr: false`,
`authority: "none"`, and nothing in it is a position, a price target or a stance.

## Who writes

Grok desk bots (Drew's and Michael's), Cursor or Claude desk runs acting for an owner, and
either human. The `author` field is the bot id (`grok-michael-special-situations`,
`claude-drew-special-situations`); `owner` is `drew` or `michael`, whose queue the brief
lands in. The same desk may be filed by both owners' bots on the same day; the file names
differ only by directory and date, so a second owner files on a later date or the two
runs merge into one file before the PR.

## File name

```
_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json
```

`<desk>` is one of `special_situations`, `activism`, `fundamentals`, `nol_tax_assets`,
`tape_index`, `stahl`, `short_selling`. The file stem is the brief's `as_of`. One file
per desk per day; a correction is a new file on a later date, never an edit to a merged
one (the ledgers' first-write-wins rule).

## How it gets in

1. Build the brief from the dashboard files first (read each file's stamp before its
   contents), then the filing each row points at, then the web only to fill a name or an
   exhibit. The schema is `schema.json` in this directory.
2. Run `python _system/scripts/check_desk_briefs.py`. It must print no `ERROR` line.
3. Run `python _system/scripts/build_desk_briefs.py`. Commit
   `dashboard/data/desk_briefs.json` in the same commit as the new brief. The
   checker fails when that file's desk paths are not the latest brief per desk.
   The Inbox reads the payload, not the brief directory.
4. Commit on a branch named `grok/<desk>/<YYYY-MM-DD>-<slug>` and open a pull request
   that touches only the new brief, that rebuilt payload, and, when a lesson was learned,
   `_system/memory-hub/research-equity/daily/<YYYY-MM-DD>.md`. A PR that touches code
   or any human-gated path waits for a human.
5. The check runs in CI on the PR. A data-only `grok/` PR that passes auto-merges.

The chat room gets a one-line pointer (ticker and the one number). The brief is the
record; a chat post is not.

## What the check rejects

`check_desk_briefs.py` validates every file against `schema.json` (JSON Schema
2020-12) and then checks what a schema cannot:

- the file is `<desk>/<YYYY-MM-DD>.json`, the directory matches `desk`, and the stem
  matches `as_of`; stray files anywhere under this directory;
- more than 12 items; a headline over 160 characters; a missing `one_number`;
- a `ticker` that is not in `_system/portfolio/registry.json` holdings or watchlist and
  is not the literal `unresolved`;
- an `inputs_read` path that does not exist in the repo, or is absolute or escapes it;
- `confidence: filing` with no filing in `evidence`, or `confidence: provider` with no
  filing, provider or dashboard entry (a headline is never a term);
- a `handoff` to the desk's own id; an `as_of` more than a day in the future;
- an unknown field anywhere (`additionalProperties: false`).

Exit code 1 on any error; `--warn-only` reports and exits 0 (for the nightly rebuild
lane, which does not own the files). Warnings (an input with no stamp, a filing with no
URL) never fail the check.

## How it reaches the Inbox

`python _system/scripts/build_desk_briefs.py` joins the latest valid file per desk into
`dashboard/data/desk_briefs.json`:

```json
{"schema_version": "desk_briefs.v1", "generated_at": "...", "caption": "...",
 "desks": [{"desk": "special_situations", "owner": "drew", "author": "...", "as_of": "2026-10-12",
            "age_hours": 14.2, "stale": false, "path": "_system/data/desk_briefs/special_situations/2026-10-12.json",
            "items": [...], "inputs_read": [{"path": "...", "generated_at": "...", "age_hours_at_read": 0.0, "exists": true}],
            "screens_empty": [...], "notes": null}],
 "items_flat": [{"...item", "desk": "...", "owner": "...", "as_of": "...", "author": "...", "stale": false}],
 "desks_without_brief": ["activism", "..."],
 "counts": {"briefs": 1, "items": 9, "files": 1, "by_desk": {"special_situations": 9}, "by_owner": {"drew": 9}},
 "health": {"status": "healthy", "structural_errors": [], "problems": [], "checked_at": "..."},
 "research_only": true, "in_base_irr": false, "authority": "none"}
```

A brief older than seven days is still listed, with `stale: true`, and named in
`health.problems` (`status: degraded`). A structurally invalid file is excluded from
`desks`, listed in `health.structural_errors`, and makes `status: unhealthy`.
`age_hours_at_read` is the hours between an input's stamp and the end of the brief's
`as_of` day, an upper bound since the brief carries a date, not a time.

The Inbox (`dashboard/index.html`, Ideas, Inbox) renders the file through
`dashboard/desk-briefs-viz.js` as one card per desk with owner and desk filters, the
items table (ticker, headline, one number, confidence, evidence, next) and the input
ages. A missing or malformed `desk_briefs.json` is an empty state, never an error.

## Wiring (lead)

The channel is complete when `dashboard/data/desk_briefs.json` has a `data_feeds` entry
in `_system/graph/graph_sources.json` (`stamp_field: generated_at`, `assert_fields` on
`health.status not_in [unhealthy]` and `health.structural_errors max_count 0`), the
nightly rebuild profile runs `check_desk_briefs.py --warn-only` and
`build_desk_briefs.py`, `build_feed_status.py` lists it, `build_dashboard_shards.py`
maps `desk_briefs` to `data/desk_briefs.json`, and `python-tests.yml` lists
`_system/scripts/tests/test_desk_briefs.py`. The brief's own pull request commits
the rebuilt payload. The nightly lane runs the same two scripts again so the
stamp stays current after other dashboard files move.

## Lessons still go to the hub

A brief holds ranked hits. A lesson about how to read the files (what fooled the desk,
what to check first next time) is a `[PROPOSED]` bullet in
`_system/memory-hub/research-equity/daily/<YYYY-MM-DD>.md`, at most three per session,
with Evidence, Seen, Harmful, Scope and Review after
(`_system/memory-hub/research-equity/README.md`).

## Privacy and tone

The repo is public. Until Decision 1 in the proposal is taken, a brief names tickers,
filings and the dashboard's own numbers. No fraud language (the `fraud_bad_actors` tag
stays a human conclusion), no position sizes, no personal trades, no email content.
