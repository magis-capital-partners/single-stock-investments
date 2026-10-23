# Short Alpha ledger

Three files, one contract, one compiler.

| File | What it holds | Who writes it |
|---|---|---|
| `candidates.json` | Every name the desk tracks: leads, names under research, the open book's names, closed and rejected rows. One row per ticker, never overwritten by discovery. | Humans by PR; desk bots by PR (`origin: desk_note`); `build_short_alpha_dashboard.py sync_leads` (activist index, filing furnace, Fugazi scorecard); `import_reverse_split_queue.py` (reverse-split engine). |
| `ideas.json` | Open borrowed shorts only: shares, opened price, split factor, dated check-ins. A position ticker must exist as a candidate. | Humans. |
| `frameworks.json` | The lens catalog: groups, source types, judgment lenses, screens and gates. The Shorts tab's framework board. | Humans, with `_system/frameworks/framework_governance.md`. |
| `schema.json` | The JSON Schema for `ideas.json` and, under `$defs`, the candidate contract. | Humans. |

`python _system/scripts/build_short_alpha_dashboard.py --check` validates the three files together and prints the summary without writing. The full build writes `dashboard/data/short_alpha.json`, which the Shorts tab reads. Borrow arrives through `refresh_short_alpha_borrow.py --input <file>` and never through the Gateway. The file is IBKR's public short-stock availability file (`curl --user shortstock: -o usa.txt ftp://ftp2.interactivebrokers.com/usa.txt`; no account, refreshed intraday) or a Client Portal availability CSV. The writer keeps the ledger's names in `dashboard/data/short_alpha_borrow.json`, each stamped with the file's own time. A name missing from the file stays pending, never zero.

## The entry contract (adopted from Michael's Short-Selling desk)

A candidate row is the structured half of an idea entry. The narrative half is a Markdown note written from `_system/templates/short_entry_template.md`. SSI is public, so a note that names a real company as a short target lives in the private research vault at `research-vault/short-research/{TICKER}/{YYYY-MM-DD}-{slug}.md`; the row keeps the pointer in `note_ref`. Only the row and the pointer are committed here.

Optional fields on every row (`schema.json` `$defs.candidate`):

| Field | Rule |
|---|---|
| `source` | Bot id or author name. Stable string, 1 to 80 characters, not an email address. |
| `added_on` | `YYYY-MM-DD`, set once when the row is created. |
| `updated_on` | `YYYY-MM-DD`, moved on every material edit. Must be on or after `added_on`. |
| `tags` | Lowercase kebab-case (`revenue-quality`), unique, no commas. |
| `summary` | One or two sentences for the card, 400 characters or fewer. |
| `note_ref` | A vault pointer (`research-vault/short-research/{TICKER}/{date}-{slug}.md`) or a repository-relative SSI path. The Shorts tab renders vault pointers as text and SSI paths as links. |
| `category` | One of the eight slugs below. |
| `lens_reviews` | The six dated analyst lens reviews from the reverse-split process (`lens_id`, `frameworks`, `status`, `known_at`, `mechanism`, `supporting_evidence`, `contradictory_evidence`, `falsifier`, `reviewed_at`). `status` is `unreviewed`, `unresolved`, `supported` or `contradicted`. A blank review is `unreviewed`, never `supported`. |

A `desk_note` row must carry `source`, `category`, `added_on`, `updated_on`, `summary`, at least one tag and `note_ref`; `--check` refuses it otherwise. The contract is not weakened to let one note through.

Michael's statuses map onto `stage`: `watching` is `lead`, `active` is `researching` (or `live` once borrowed), `closed` is `closed`, `archived` is `rejected`. His `type: playbook` and `type: paper` entries are not rows: a playbook goes to `_system/reference/short-selling-library/playbooks/`, a paper note to `_system/reference/short-selling-library/public/notes/`, both listed in that library's README.

Rules that travel with the contract:

1. One idea per row and per note file. Two unrelated tickers are two entries.
2. Never rename a merged note file; the row's `note_ref` is the link.
3. A market figure (price, fee, availability, short interest, size) appears only with its source and the date it was read. A borrow snapshot is a reading on a date, not a standing fact.
4. No copyrighted text: paper notes are summaries in our words with a citation; filings are quoted by locator.
5. Move `updated_on` on every material edit. Leave `added_on` alone.
6. Bots and humans use the same path: a PR that adds or edits the row and, where a narrative exists, the vault note.
7. Fictional `example` entries (the `FKTN*` placeholders) are never migrated. A real idea never reuses a placeholder ticker.

## Category to lens map

`category` is Michael's taxonomy; the lenses are `frameworks.json` ids. The map lives in code as `CATEGORY_LENSES` in `build_short_alpha_dashboard.py` and is what gives a row with only a `category` its `effective_frameworks`. The test suite keeps this table and the code equal.

| Category | Label | Lenses applied | Note |
|---|---|---|---|
| `accounting` | Accounting | `accounting`, `revenue_recognition`, `earnings_vs_cash`, `working_capital` | Score a child screen when the filing shows which game it is. |
| `shitco-concept` | Shitco / concept | `promotion_insider_selling`, `fad_single_product` | `fraud_bad_actors` belongs to this category but is a conclusion tag only: a human sets it after a regulator, a court, an admitted restatement or an evidence-backed determination. The map never applies it. |
| `supply-side` | Supply-side / competition | `supply_side`, `margin_contraction`, `cycle_mean_reversion` | |
| `share-supply` | Share supply | `dilution_financing`, `share_supply` | `share_supply` is a gate: lockups, ATMs, converts, insider selling, index deletions, separations. The separations and index lanes feed it. |
| `reverse-split` | Reverse split | `reverse_split_impairment` | Judgment lens; process in `_system/frameworks/reverse_split_short_process.md` (RSI-1.0). |
| `activist-short` | Activist short | none | An origin, not a lens: the row carries `origin: activist_index` and the report as a source. |
| `borrow-squeeze` | Borrow / squeeze risk | `borrow_and_carry`, `crowding_squeeze` | Both are gates. A missing fee is pending, never zero. |
| `playbook` | General strategy / playbook | none | Not a row. Process notes live in the library. |

## Origins

| `origin` | Who creates the row | Stage on arrival |
|---|---|---|
| `position` | The one-time split of the August 2026 position file | `live` |
| `activist_index` | `sync_leads`, from feed short reports in the activist index | `lead` |
| `filing_furnace` | `sync_leads`, from an always-review filing event | `lead` |
| `fugazi_scorecard` | `sync_leads`, from the Fugazi Research scorecard | `lead` |
| `browser_draft` | The Shorts tab's "Track a name" form, exported by a human | `lead` or `researching` |
| `desk_note` | A desk bot or an author, by PR, with the vault note | from the note's status |
| `reverse_split_research` | `import_reverse_split_queue.py`, from the rsdb review queue export | `lead`, `research.status: requires_analyst_review` |

A lead is not a thesis. `sync_leads` and the importer never overwrite an existing row, whatever its stage. The reverse-split import writes the hypothesis "Reverse-split discovery lead; impairment not yet reviewed." and carries the six lens reviews so the analyst's work starts from the engine's record, not from a blank.

## Short strategy lab: data operations

The October 22 research update adds source reviews, dated financial backfill, a separate price overlay, obligation auditing and two immutable prospective policies. These are exploratory research operations, not approval to trade. Historical account exports remain excluded at the user's request. Actual fills, approved borrow, recalls and loan-termination evidence remain missing.

Public IBKR collection starts with `python -m _system.scripts.reverse_splits.profit_borrow collect --legacy-archive`. It uses the public FTP file, verifies its published checksum and row count, and stores every US row in ignored `local/borrow_monitor/borrow.sqlite`. SSI watchlist observations are published in `borrow_monitor/daily/` and `dashboard/data/short_borrow/`. The existing scheduled borrow workflow captures five times each weekday and synchronizes matching observations to D1, subject to the shared free-tier budget guard. Source markers are written after observations so incomplete database imports do not advertise a complete vintage. A dated static snapshot remains available if database synchronization fails; stale captures are labeled. Public indications never approve a loan or rewrite historical costs.

`profit_borrow import-etf --input <borrow_history.json>` imports matching ETF-history symbols into a separate proxy source. Reconstructed daily timestamps and ticker reuse prevent treating those records as issuer-verified intraday loan observations. ETF code/data are read only.

For the versioned research work folder, use these bounded, resumable collectors:

- `python -m _system.scripts.reverse_splits.profit_refresh facts --work <versioned-work-folder> --max-requests 100` collects missing SEC companyfacts. The replay filters as-filed observations again at each public event clock; missing/custom-tag foreign financials remain unknown.
- `python -m _system.scripts.reverse_splits.profit_discovery --work <versioned-work-folder> --max-requests 250` screens full-market SEC indexes independently of split membership. Hash-ordered, incomplete queues are not a complete financing universe or verified trades.
- `python -m _system.scripts.reverse_splits.profit_market_data --work <versioned-work-folder> --max-symbols 600 --through YYYY-MM-DD` prices each exact Databento request first and refuses every nonzero or invalid quote. CSV daily bars and the price overlay stay ignored and private. No raw licensed bars are published; current symbol histories still require dated security-continuity checks.
- `python -m _system.scripts.reverse_splits.profit_operations audit-liabilities --work <versioned-work-folder> --max-requests 150` binds unresolved replay events to SEC sources without assuming a delisting closes a short loan.

`profit_forward/forward_policies.json` pins two paper policies selected after historical exploration. The weekday `profit_refresh monitor` checks screen newly published financing contexts and public split leads and records explicit pre-entry abstentions while inputs are unverified. Already-passed entries stay missed. This is a monitoring/evidence queue, not a completed forward profitability test. New rules require a new policy version; actual execution and independent future outcomes are prerequisites to production.
