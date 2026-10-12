# Magis Capital Partners sources

This repo is the source list for Magis Capital Partners bots, including Michael's Grok bots. The GitHub repository `magis-capital-partners/single-stock-investments` is the source of truth.

Drew's local worktree at `C:\Users\drewg\.codex\worktrees\energy-btc-model\single-stock-investments` can be stale. Read and write from this GitHub repo.

The machine-readable index is `_system/sources.json`. Check it with `python _system/scripts/validate_sources.py`. The Python tests workflow runs `_system/scripts/tests/test_validate_sources.py`.

## Ground rules

1. Before using a dashboard data file, read its build date first. Use `generated_at` when the file has that field, and `build_time` when the file has that field.
2. Read `_system/portfolio/registry.json` fresh. Do not hardcode tickers.
3. Report ranked hits only.
4. Stubs go to the Special Situations desk.
5. Say nothing when nothing is new.
6. Never post Drew's personal trades or private correspondence.
7. Outbound messages to people need Drew's approval.
8. Email is read-only. Use it only to cross-reference universe names. Label each item as a newsletter or a letter with its date, and treat it as a lead until a filing confirms it. Never surface personal brokerage mail, and do not store email content in this repo.
9. Bots write only inside `_system/memory-hub/research-equity/`. Append at most three `[PROPOSED]` lessons per session. Never edit `_system/memory/MEMORY.md`. Never create a new hub without Drew's approval. Never write the `borrow-etf`, `diamond-creek`, or `spx-0dte` hubs.

## Dashboard data

Files live in `dashboard/data/`. Read the build date before the contents.

| File | Build date field | What it holds |
| --- | --- | --- |
| `kpi_trends.json` | `generated_at` | KPI trend series for the covered universe. |
| `portfolio_news.json` | `build_time` | News items. Each item has `published_utc`, `confidence`, `category`, and `tickers`. |
| `document_catalog.json` | `generated_at` | Document index in `documents`. `folder_index_generated_at` is an older folder-index stamp. Use `generated_at` for the catalog build. |
| `warrants.json` | `generated_at` | Warrant alerts and filing events. |
| `activist_feed.json` | `generated_at` | Activist filings and triage counts. Desk: Activism. |
| `index_membership.json` | `generated` | Index membership and scorecards. This file stamps the build in `generated`, and the membership date in `as_of`. |
| `fico_watch.json` | `generated_at` | FICO watch page. The file is not always present. When it is absent, skip it. Desk: Fundamental Analyst. |

These files are generated. A bot reads them. A correction goes out as a pull request from a cloud agent or the GitHub connector.

## Portfolio registry

`_system/portfolio/registry.json` is the book. Read it at the start of a run. The stamp on the file is `meta.updated`. Holdings and classifications come from this file on that run.

## Reference library

`_system/reference/short-selling-library/` is the short-selling reference library. `README.md` catalogues the books. Book scans are not committed. Public papers sit under `public/`. A catalogue change is a pull request. Do not commit a book scan.

## Google Drive

Folder and file ids below were read from Drive on 2026-10-12, except where a row says to search by name.

| What | Drive id | Where it sits |
| --- | --- | --- |
| Books | `1q0B2FkNPF2onYEv9MBh6VJoDR6rqtBxQ` | `Research Sources/Books` |
| Value Investing | `1BDzwtkgAHsKOda2NtxlHEwc37cEjTwD7` | Child of Books. The briefing said to find this folder by name. The id is the folder titled Value Investing. |
| Accounting | `1tL89aD9SDliM3BDCaQDJHU0CJ_YR0kgS` | `Research Sources/Books/Accounting` |
| Trading & Markets | `1hsvaElY-UaFW0fGygv2685Bb9HJqatTS` | `Research Sources/Books/Trading & Markets` |
| Accounting (near-duplicate) | `1m5c1VcKkGzy2rEp3V6GWAORQspMJHkjm` | `Research Sources/Investment Wisdom/Accounting`. Parent folder Investment Wisdom is `1zjhPYsBH9eoV36wm8G_9X5vGt1YY_9Ql`. |
| Short-selling library papers | `1VLD6d4PpNWRagijg0ibsSeU5g3fMoNBz` | Drive title of this folder is `public`, inside `short-selling-library` (`1cHaPQfoJVCJKslWtKxplrYloteokdC4S`), inside `reference`. |
| Special-situations checklist book | `1LwfqcmaUU7X8uCMsoteeF8nRFt9mDNRe` | Drive title is `Joel Greenblatt - You Can Be A Stock Market Genius.pdf`, in `Books/Value Investing/Joel Greenblatt`. |
| Admin / Intake | `1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C` | Drive title is `Intake`, under `Admin` (`1LRc4HnEoXolUgma_cLh4rwHMpTuKJrt-`). VIC drops land at `Admin/Intake/VIC/{TICKER}/`. |

Library folders are read-only for bots. New documents go to Admin/Intake, not into Books.

Drop a VIC PDF with:

```bash
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TICKER path/to/writeup.pdf
```

The ticker folder must already exist. The procedure is in `_system/agents/GROK.md`. The Data Pipeline job `drive` is the Drive Intake Sync. It runs daily at 14:00 UTC from `.github/workflows/data-pipeline.yml` (`0 14 * * *`). GitHub Actions can start later than that clock time.

Manager letters, short-thesis pitch folders, and conference decks live on Drive. Search by name. Fund letters in the repo's Drive map sit under `Letters/{year and quarter}` (`_system/reference/document-store/google_drive_config.json`). Do not invent a folder id for those searches.

## Email

Email is read-only. Do not store email content in this repo. Use a message only to cross-reference universe names. Label it as a newsletter or a letter with its date. Treat it as a lead until a filing confirms it.

| Connector | Mailbox | What to read | Never surface |
| --- | --- | --- | --- |
| default | `drewgoldman01@gmail.com` | Newsletters: MOI Global, KEDM Lite, Base Hit. Also GitHub pipeline alerts. | Personal brokerage mail. |
| magis | `drew@magiscapitalpartners.com` | Prime-broker cap intro, manager letters, Friday Furnace. |  |

Personal brokerage mail is never surfaced. Do not copy a message, a balance, or a trade blotter into the repo, the memory hub, or a room.

## Memory hub

Shared notes live in `_system/memory-hub/research-equity/`.

| File | Role |
| --- | --- |
| `README.md` | Writing rules for the hub. |
| `GRAPH.md` | Shell until Drew copies his local graph. |
| `CONTEXT.md` | Shell until Drew copies his local context. One desk line may be added per session after that copy. |
| `daily/YYYY-MM-DD.md` | Up to three `[PROPOSED]` lessons per session. Each lesson uses Evidence, Seen, Harmful, Scope, and Review after. |

Drew's local copy at `C:\Users\drewg\Projects\.agent-memory\hubs\research-equity\` is not reachable from the cloud. Copy that content in. Do not invent it.

Bots write only inside `research-equity`. Never edit `_system/memory/MEMORY.md`. Never create a new hub without Drew's approval. Never write the `borrow-etf`, `diamond-creek`, or `spx-0dte` hubs.

## Room and desks

Grok Bot group room: Magis Capital Partners. Room id `7ad6d9cb-85bd-4f2c-b887-1bf4bf59b107`.

Desks: Fundamental Analyst, Special Situations, Activism, NOL and Tax Assets, Technical Analyst, Murray Stahl.

Weekday digests go out around 8:10-8:14 AM ET. Say nothing when nothing is new. Ranked hits only. Stubs go to Special Situations.

## How to push

| Kind of change | Where it goes |
| --- | --- |
| Code and repo data | A pull request from a cloud agent or the GitHub connector. |
| Documents | Shared Drive `Admin/Intake/...`, using `drive_intake_drop.py` for VIC. The 14:00 UTC Drive Intake Sync imports them. |
| Notes and lessons | The `research-equity` hub only, within the writing rules above. |
| Anything outbound to a person | Needs Drew's approval before it is sent. |

## Pending access decisions

- [ ] Grant Michael's accounts access to the repo and Drive folders.
- [ ] Decide read vs write on the memory hub for Michael's bots.
- [ ] Confirm whether Michael's bots join the Magis room.

## Left out on purpose

This page does not hold credentials, personal trades, balances, brokerage mail, or private correspondence.
