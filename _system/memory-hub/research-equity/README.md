# research-equity memory hub

This is the only shared memory hub bots may write. It is the in-repo copy of Drew's research-equity hub.

Drew's local copy at `C:\Users\drewg\Projects\.agent-memory\hubs\research-equity\` is not reachable from the cloud. Its content was copied in on 2026-10-12 (`CONTEXT.md`, `MEMORY.md`, `bridges.md`, `daily/` through 2026-10-08, and the mesh-root `GRAPH.md`; `decisions/` was empty). From that date this directory is the copy bots read and write; the laptop copy is Drew's cross-repo mesh. Do not invent graph nodes, context, or lessons that are not here.

| File | Role | Who edits |
| --- | --- | --- |
| `GRAPH.md` | Copy of the mesh root graph: nodes, edges, hard laws. Only `research-equity` lives in this repo. | Drew |
| `CONTEXT.md` | Domain language, current truths, desk lines under `## Desk`. | Bots: one desk line per session. Drew: everything else. |
| `MEMORY.md` | Approved cross-repo invariants. | Drew promotes. Bots never edit it (same rule as `_system/memory/MEMORY.md`). |
| `bridges.md` | Shared data artifacts and path contracts between SSI and the research vault. | Drew; bots propose changes in `daily/`. |
| `daily/YYYY-MM-DD.md` | `[PROPOSED]` lessons from sessions. | Bots append, at most three per session. |
| `decisions/YYYY-MM-DD-slug.md` | ADR-style decisions, when asked. | Drew, or a bot Drew asked. |

Ranked desk output does not go here. Since 2026-10-12 it goes to `_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json` (`_system/data/desk_briefs/README.md`). This hub keeps the lessons.

## Who may write

Bots write only inside this directory (`_system/memory-hub/research-equity/`).

A session may:

- Append at most three `[PROPOSED]` lessons to `daily/YYYY-MM-DD.md`.
- Add one desk line to `CONTEXT.md`.

A session may not:

- Edit `_system/memory/MEMORY.md`.
- Create a new hub. A new hub needs Drew's approval.
- Write the `borrow-etf`, `diamond-creek`, or `spx-0dte` hubs.
- Store credentials, personal trades, balances, brokerage mail, or private correspondence.

## Lesson form

Create or append `daily/YYYY-MM-DD.md` for the session date. Use the blank form in `daily/README.md`. Each lesson has Evidence, Seen, Harmful, Scope, and Review after, in that order, under a `[PROPOSED]` heading.

Lessons stay proposed until a person reviews them. This hub does not promote text into `_system/memory/MEMORY.md`.

## Desk line

`CONTEXT.md` has a `## Desk` heading at the end with one line per desk. A bot may append one desk line under that heading per session. The desk mandates in full are `_system/agents/DESKS.md`.
