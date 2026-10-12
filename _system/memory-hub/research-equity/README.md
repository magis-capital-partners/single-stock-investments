# research-equity memory hub

This is the only shared memory hub bots may write. It is the in-repo copy of Drew's research-equity hub.

Drew's local copy at `C:\Users\drewg\Projects\.agent-memory\hubs\research-equity\` is not reachable from the cloud. This directory is seeded with structure only. Drew copies his existing local `GRAPH.md`, `CONTEXT.md`, and `daily/` notes in. Do not invent graph nodes, context, or lessons to fill the gap.

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

`CONTEXT.md` has a Desk heading. After Drew's local context is copied in, a bot may append one desk line under that heading per session.
