# Reverse-split research data

Reverse splits over about five years, US listed and OTC: completed events with
an ex date, the 8-K/6-K phrase hits that never printed, FINRA positioning
context, the persisted shared-capital book runs and the append-only RSI-1.0
decision journal. Proposal:
`_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md` (Phase 3).
Process: `_system/frameworks/reverse_split_short_process.md`.
Code: `_system/scripts/reverse_splits/` (CLI
`python -m _system.scripts.reverse_splits.cli`).

This directory separates the **committed ledger** (JSONL beside this file) from
**local build artifacts** (`local/`, ignored by git: the 260 MB SQLite, raw
EDGAR and companyfacts caches, price history, reports). The ledger is what a
clean clone has; `import_ledger` rebuilds SQLite from it and `export_ledger`
writes it back. Nothing over 10 MB enters git; a file that would is capped to
the last three years and the cap is recorded in `ledger_manifest.json`.

| File | Content | Rows (2026-10-11) | Mutability |
|---|---|---:|---|
| `events.jsonl` | Completed or candidate reverse splits with an ex date (`status` seeded / edgar_candidate; `outcome` effective). One row per `(ticker, ex_date, split_from, split_to)`. | 632 | Rewritten by `export-ledger`; rows are upserted, never deleted, by the collectors |
| `announcements.jsonl` | 8-K/6-K reverse-split phrase hits that did not become a Yahoo split, with the parsed outcome where the filing text was read. Written sparse: an absent key is null. | 22,879 | Rewritten by `export-ledger`; the weekly `seed --since-days` rebuilds only its window |
| `finra_short_interest.jsonl` | FINRA consolidated short interest when files were present, else synthetic rows carrying average daily volume only (`source_file: synthetic_adv_only`). Sparse. | 17,223 | Rewritten by `export-ledger` |
| `book_runs.jsonl` | One row per persisted book run: label, assumptions (`config`), diagnostics (`analysis`), funnel, and the sha256 of its source manifest. | 118 | Append-only through the local `book` command |
| `book_source_manifests.jsonl` | Deduplicated source manifests (code hashes, SEC cache hashes, SSI source hashes) referenced from book runs. | 8 | Append-only |
| `decisions.jsonl` | RSI-1.0 decisions: review / pass / paper_ready with the frozen evidence, policy and evaluation. Hash-chained. **Michael owns these rows.** | 2 | Append-only, immutable; revisions append with `supersedes` |
| `ledger_manifest.json` | `exported_at`, per-file rows / bytes / sha256, caps applied, chain validity, the tables deliberately not exported. | | Rewritten by `export-ledger` |
| `config.toml` | Package configuration; paths resolve relative to this directory. | | Edited by hand |
| `local/` | SQLite (`reverse_splits.db`, `strategy_decisions.sqlite`), `raw/` caches, `reports/`. | | Ignored |

Not exported (reproducible from public sources or too large): `prices_daily`
(1.78 M Yahoo rows), `edgar_hits` (39.8 k phrase hits), `control_prices`,
`book_trades`, `book_equity`, `issuers` (names travel on the rows), `filings`,
`borrow_snapshots`, `backtest_*`.

## Schemas

### Event row

```json
{"ticker": "BRTX", "cik": "0001505497", "company": "BioRestorative Therapies, Inc.",
 "exchange": "Nasdaq", "exchange_class": "listed",
 "split_from": 4000.0, "split_to": 1.0, "ratio": 0.00025,
 "first_proxy_date": "2022-08-05", "announce_date": "2021-10-26", "vote_date": null,
 "ratio_set_date": null, "effective_date": "2021-10-27", "ex_date": "2021-10-27",
 "prior_rs_count": 0, "cohort": "first", "status": "seeded", "confidence": 0.5,
 "needs_review": 0, "source": "yfinance", "outcome": "effective", "vote_path": "board",
 "accept_time": "2021-10-26T21:09:51.000Z", "announced_ex_date": null, "announced_ratio": 0.25,
 "jump_status": null, "jump_observed": null, "date_quality": "filing_text",
 "accession": null, "form": null, "created_at": "2026-10-09 03:14:38", "updated_at": "2026-10-09 04:04:43"}
```

`ratio` is new/old shares (0.1 is a 1-for-10). `cohort` in `first | second |
third_plus` counts prior splits by CIK, else by ticker. `exchange_class` in
`listed | otc | unknown`. `date_quality` in `search_hit | acceptance_time |
filing_text`; only `filing_text` means the announcement clause was read.
`accession` and `form` identify the EDGAR filing for `edgar_candidate` rows;
Yahoo-seeded rows carry none.

### Announcement row (sparse)

```json
{"accept_time": "2026-10-08T20:30:17.000Z", "accession": "000121390026107822",
 "announce_date": "2026-10-08", "announced_ex_date": "2026-10-09", "announced_ratio": 0.02,
 "cik": "0001966750", "company": "Zhibao Technology Inc.", "date_quality": "filing_text",
 "exchange": "Nasdaq", "exchange_class": "listed", "form": "6-K", "outcome": "announced_only",
 "ticker": "ZBAO"}
```

`outcome` in `announced_only | mention | cancelled`: `mention` is
reverse-split language with no action, `cancelled` an abandonment, both known
only where the text was parsed. Keys that are always the collector constants
(`source: edgar_search`, `confidence: 0.4`, `needs_review: 1`, `ex_date` =
`announce_date`) are not written; the importer restores them. Absent
`first_proxy_date`, `announced_ex_date`, `announced_ratio`, `vote_path`,
`company` or `exchange` mean null.

### FINRA row (sparse)

```json
{"ticker": "AACG", "settlement_date": "2023-12-15", "avg_daily_volume": 6540.9, "source_file": "synthetic_adv_only"}
```

`short_interest` and `days_to_cover` are present only when a real FINRA file
was ingested. Short interest is positioning, never a locate, and never sets a
share count.

### Book run row

```json
{"id": 118, "created_at": "2026-10-11 23:18:48", "label": "fundamental_60",
 "config": {"signal": "announce", "horizon_days": 5, "fee_annual": 1.0, "borrow_policy": "assumed_fee", "...": "..."},
 "analysis": {"waterfall": {"raw_price_pnl": 617.9, "spread_and_slippage": 331.5, "gross_after_fills": 286.4, "borrow": 124.7, "commission": 21.1, "net": 140.7}, "profit_factor": 1.34, "...": "..."},
 "funnel": [{"stage": "evidence_pool", "n": 48}, {"stage": "raw_asof_score_at_least_60", "n": 4}, {"stage": "taken", "n": 4}],
 "source_manifest_sha256": "..."}
```

`analysis` is `diagnostics()` from `reverse_splits/analysis.py`; `funnel`
counts the admission stages. Trades and equity curves stay local.

### Decision row

```json
{"id": "b99be6f0-...", "recorded_at": "2026-10-09T15:29:12.833239+00:00", "ticker": "DFLI",
 "previous_hash": "", "record_hash": "<sha256>",
 "record": {"id": "...", "recorded_at": "...", "ticker": "DFLI", "decision": "pass", "reason": "...",
            "supersedes": null, "prospective": true, "policy": {"version": "RSI-1.0", "...": "..."},
            "fundamental_snapshot": {}, "announcement_snapshot": {}, "inputs": {}, "evaluation": {},
            "research_plan": {}, "furnace_drafts": [], "previous_hash": "", "record_hash": "<sha256>",
            "source_system": "reverse_split_research", "usage": "research decision; not an order or realized return"}}
```

`record_hash` is the sha256 of the canonical JSON (`sort_keys`, compact
separators) of `record` without `record_hash`; `previous_hash` is the prior
row's `record_hash` (empty for the first). `check_reverse_splits.py` fails on
any break. A `paper_ready` row is a plan, not an order or a fill.

## Rebuilding SQLite from the ledger

```bash
python -m _system.scripts.reverse_splits.cli import-ledger          # JSONL -> local/reverse_splits.db (+ decisions sqlite)
python -m _system.scripts.reverse_splits.cli seed --since-days 21   # EDGAR + yfinance for the recent window
python -m _system.scripts.reverse_splits.cli classify-exchanges
python -m _system.scripts.reverse_splits.cli clocks --since-days 21 # accept clocks + announcement text for new hits
python -m _system.scripts.reverse_splits.cli prices                 # Yahoo OHLCV (local only; ~1.8 M rows)
python -m _system.scripts.reverse_splits.cli finra                  # FINRA files in local/raw/finra, else ADV rows
python -m _system.scripts.reverse_splits.cli book                   # books, reports, local/reports/public/backtest.json
python -m _system.scripts.reverse_splits.cli export-ledger          # SQLite -> JSONL
python _system/scripts/build_reverse_splits_dashboard.py            # ledger -> dashboard/data/reverse_splits.json
python _system/scripts/check_reverse_splits.py --strict
```

`seed` and `clocks` without `--since-days` scan the full `years_back` window
(hours of SEC requests). With it, `seed` rebuilds only announcements filed in
the window and leaves older ledger rows alone; `clocks` leaves effective events
whose announcement predates the window alone (the earliest-filing rule means no
newer hit can replace them). The book, prices, controls and the frozen rerun
are local research steps; CI runs import, seed, clocks, export, build and
check only.

Borrow evidence: `borrow-csv path/to/export.csv` imports a Client Portal
Short-Securities Availability export (keeps the export's own timestamp,
divides percent quotes by 100). The same command reads IBKR's public
`usa.txt` (`ftp2.interactivebrokers.com`, user `shortstock`), one snapshot row
per symbol at the file's `#BOF` time, through SSI's
`refresh_short_alpha_borrow.parse_public_ftp`. One file is one point in time;
it is not a historical locate. There is no broker connection anywhere in the
package; the original tool's live snapshot path was deleted (it used the SPX
executor's client id). See `CLAUDE.md`, IB Gateway rules.

## Dashboard payload (`dashboard/data/reverse_splits.json`)

Built from the JSONL alone (CI has no SQLite). Schema `reverse_splits.v1`:
`counts` (events, announcements, by_cohort, by_exchange_class, by_year,
announcements_by_outcome), `recent_announcements` (last 90 days, newest first,
at most 100), `upcoming_effective` (known or announced ex dates on or after
today, `basis` event / announcement, at most 50), `repeat_splitters` (cohort
second / third_plus, at most 50), `book` (latest run, latest batch, honest
limits), `process` (RSI-1.0 rules, gates, policy text), `decisions_summary`,
`health` (`status`, `structural_errors`, `problems`) and the research-only
authority fields. `health.status` is `unhealthy` when the ledger manifest is
older than ten days or the feed is older than 100 hours; the P6 feed registry
asserts `health.status not_in [unhealthy]` and `health.structural_errors`
empty.

## Honest limits

- Historical locates are not in this database. The strict book is empty until
  timestamped pre-order availability and fee are imported.
- Assumed fees are flat annual rates, not the fee the street quoted that day.
- A phrase hit in an 8-K is not an announcement until the filing text is
  parsed (`date_quality: filing_text`). Most announcement rows are accept-clock
  phrase hits.
- The original $50k completed-split comparator lost about $14,286 on 124
  trades. The 2026-10-11 filing and corporate-action audit superseded the
  preliminary four-trade rerun gains (ASTI was a historical reference; PALI and
  IBO fell under the $1 floor once split factors were repaired); the corrected
  rerun leaves one candidate, EDBL, losing about $150 over five sessions. The
  persisted `fundamental_60` book run predates that audit. Nothing here
  establishes an edge.
- Current SEC exchange maps and Yahoo history are not a contemporaneous
  security master; delisted names and failed exit paths are censored.
- Issuer names come from the SEC ticker map at collection time; about 13% of
  announcement rows have none.

Do not edit the JSONL files by hand. Run
`python _system/scripts/check_reverse_splits.py` after any change.
