# Reverse-split research data

US listed and OTC reverse-split research: completed events and candidates with
an ex date, filing disclosures, FINRA positioning
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
writes it back. Files over 10 MB are divided into immutable year shards with
a checksum index (`name.parts.json`). Readers use `load_jsonl` to verify and
combine the shards. No old years are removed to meet the size limit.

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

## Expanded universe experiment (v3)

The Shorts → Reverse splits panel has a separate expanded study. It covers
2018-05-01 onward for prices and supports SEC discovery from 2005 onward.
The saved 118 book runs and Michael's decisions remain the frozen comparison.
`full_universe_complete` stays false while source or identity gaps remain.

### Published snapshot: 2026-10-13

Run `20261013T202808739318Z` covers events from 2018-05-01 through
2026-10-13, with complete daily price history available through 2026-10-12.

| Measure | Count |
|---|---:|
| Discovered filing accessions, 2005 onward | 128,077 |
| Parsed filing disclosures | 60,618 |
| Catalogue events and candidates | 7,069 |
| Distinct issuer keys in the catalogue | 4,978 |
| Verified actions: structured notices or matched primary schedules | 3,619 |
| Verified next-session / five-session entry and exit benchmarks | 665 |
| Distinct issuer keys with those benchmarks | 541 |
| Fixed account scenarios | 34 |

The 665 count establishes two benchmark prices, not an uninterrupted,
executable trading path. Unresolved issuer keys use the historical symbol;
identity review can join aliases later. The catalogue is approximately three
times the existing 2,330-row event ledger, with its provisional rows labeled.

All filing accessions inside the priced collection window were attempted;
two remain unavailable. Another 67,457 earlier accessions remain discovery
metadata awaiting text processing and licensed prices. The full-market price
scan retains unmatched candidates; its reconciled window is 2018-05-15 through
2026-10-05 because the detector requires surrounding sessions.

Nominal prices cover 2,736 symbols and 1,057,110 daily rows. Official auction
benchmarks come from 105 venue files, with 1,993,744 valid observations. SEC
fundamental sources were requested for 3,239 issuer IDs; 32 source files were
unavailable. Historical OTC prices, terminal obligations and dated security
identity remain incomplete. The optional Massive cross-check has no local
key and contributes no actions.

For example, the next-session fundamental-score-60 case with a five-session
hold and assumed 100% annual borrow fees has 91 modeled entries across 89
issuer keys, including two unresolved positions. The strict evidence case
has zero trades because its required dated execution evidence is unavailable.
These are conditional research results, not demonstrated tradable profits.

The latest public borrow archive contains 4,599 inventory indications as of
2026-10-13 20:28:29 UTC. It supplies no approved locates. The daily archive
workflow builds future evidence; it cannot reconstruct historical approvals.

### How to read the expanded backtest

1. **Find the names.** Search filings and official OTC action notices, and scan
   historical exchange prices for split-like jumps. This includes names that
   later stopped trading. Unmatched price detections remain searchable candidates.
2. **Identify what happened.** Distinguish permission to split, a board decision,
   a scheduled split, a historical mention and a cancellation. Repeated filings
   are grouped provisionally; they do not automatically become extra trades.
3. **Confirm the action.** A filing's schedule alone does not prove completion.
   Confirmed actions, provisional schedules and unresolved candidates have
   separate counts. Security class and ticker history still need review.
4. **Measure the price move.** Compare official auction prices at the split-day
   open or close, the next session, or five sessions later, with closes after
   5, 10 or 20 sessions. This answers how prices moved before trading costs.
5. **Apply the trading rules.** The separate account replay considers score,
   available history, share quantity, liquidity, margin, spread and capital.
   Sub-$1 stocks are included when the modeled economics allow them.
6. **Charge costs and handle restrictions.** Conditional cases assume 100% or
   300% annual borrow fees, plus spread and commissions. Observed short-sale
   restrictions can delay entry. Unknown evidence remains labeled unknown.
7. **Keep unfinished trades visible.** Missing prices or incomplete covers do
   not create a winning exit. Residual positions and their liabilities remain
   in the account. A strict case requires actual dated execution evidence.
8. **Report the denominator.** Read discovered events, confirmed actions,
   benchmarked events, modeled trades and distinct issuers separately. Running
   several settings on the same company does not increase independent evidence.

The fee rates are assumptions used for sensitivity analysis. Today's public
borrow file cannot tell us whether a stock was borrowable years ago. The
expanded results are exploratory research, not demonstrated executable returns.

The committed files are:

| File | Purpose |
|---|---|
| `expansion_summary.json` | Coverage funnel, source gaps, aggregate event returns and every declared account scenario |
| `expansion_events.jsonl` or `.parts.json` | Event identities, exact action dates/ratios, sources, verification tiers and missing price-path reasons |
| `expansion_disclosures.jsonl` or `.parts.json` | Filing accessions, availability clock, lifecycle stage, ratio and schedule |
| `expansion_discovery.jsonl` or `.parts.json` | All discovered filing-hit identities, including the earlier unpriced inventory; restored on a clean checkout |
| `expansion_episodes.jsonl` or `.parts.json` | Provisional links among repeated disclosures; different schedules or known ratios remain separate |
| `expansion_manifest.json` | Checksums linking one published snapshot to its immutable local input manifest |
| `borrow_history/` | Timestamped public IBKR inventory/fee indications; never approved locates |

Discovery uses three sources independent of today's live ticker list:
all-symbol venue histories (including securities that stopped trading), SEC
full-text windows and quarterly filing inventories, and FINRA's public OTC
Daily List. Every search page is exhausted or recorded as incomplete; large
result windows subdivide. Unknown OTC ratios, unresolved CIKs and security
classes remain candidates. A filing schedule alone is not proof that the
action happened. A price jump alone is not a verified corporate action.

Filings are classified as proposal/authorization, board action, scheduled
action, historical reference, cancellation or unresolved. The parser examines
bounded clauses around split language, including exhibits. Unless a sourced
public release timestamp is supplied, the filing becomes usable at midnight
after its filing day. This prevents a later disclosure from moving a trade
back in time.
Cached complete submission files are retained. For uncached proxies and
information statements, collection resolves the official primary document
and relevant linked exhibits; this is labeled separately from a complete
submission archive, and unlinked exhibits remain an evidence gap.

An optional `reference` collector cross-checks Massive's structured reverse
split endpoint inside its documented two-year Basic window. It uses an
existing `MASSIVE_API_KEY` or `POLYGON_API_KEY`, records access gaps, and never
buys or upgrades a subscription. Older history needs an entitlement decision.
See [Massive's split coverage](https://massive.com/knowledge-base/article/does-massive-support-normal-and-reverse-splits).

The broad event study compares official listing-venue auction entry prices
with closes after
5, 10 and 20 trading sessions. Entry cohorts are split-day open, split-day
close, the next session and five sessions later. Known subsequent splits
change the share quantity; unverified actions block the path. Missing exits
stay unavailable. Returns are gross price behavior, with no assumption of
borrow or executable fills. Each cohort reports distinct events and issuer
keys, plus uncertainty clustered by issuer and calendar year.

The account study uses one hypothetical $50,000 account, the existing
fundamental score floor of 60 and minimum three observed signals. Scheduled,
authorization and board disclosures and next-session entries have separate
declared cases. Sub-$1 prices remain in scope; margin per share, integer
quantity, participation, spread, fees, commissions, economic cost budgets and
conservative stress sizing determine whether a modeled trade fits. Observed
short-sale restrictions delay entry at most two sessions. Missing status
remains unknown. Repeated settings do not increase the independent sample.
Partial covers and missing terminal prices remain residual liabilities.

Companyfacts are filtered by historical filing availability before the SSI
extractor runs. Missing/custom/foreign financial facts remain unscored.
Strict execution requires dated security identity, thesis, house margin,
known unrestricted status, fresh quotes and an approved locate with a
reference. Public inventory indications satisfy none of the locate-approval
requirement. Conditional fee scenarios use fixed 100% and 300% annual fee
assumptions; annualized performance claims are withheld.

Each local run writes its plan before calculating returns, then freezes both
SQLite inputs, companyfacts, code hashes and source hashes under
`local/expansion/expansion_v2/runs/<run-id>/`. Licensed bars, quotes and
individual price-derived returns remain local. Public feeds contain metadata
and aggregate research. Forward validation starts the day after the frozen
cutoff; the existing history is exploratory.
Older immutable content shards can remain alongside the current version;
the `.parts.json` index selects the active rows and checks their hashes.

### Run or resume the expansion

Install `_system/scripts/requirements-reverse-splits.txt` and import the ledger.
Fetch licensed venue files separately with `databento-pull --max-cost 0`;
every new request is quoted before download. The expansion command never
logs into a broker or ThetaData.

```powershell
python -m _system.scripts.reverse_splits.cli import-ledger
python -m _system.scripts.reverse_splits.cli expand all --discovery-start 2005-01-01 --start 2018-05-01 --end 2026-10-13
```

Collection is resumable. Individual steps are `discover`, `discover-ads`, `filings`,
`reclassify`, `fundamentals`, `otc`, `study` and `publish`. `--offline` uses
archived sources and records missing sources. `--pilot` / `--limit` can bound
a collection run; its incomplete coverage is still reported. A denied SEC
request stops that collector; it never changes identity to bypass a denial.
All SEC collectors share one four-requests-per-second budget.

Existing local research can be migrated once with
`expand bootstrap --legacy-root <archived-research-directory>`. This makes a
consistent SQLite snapshot and retains immutable caches without modifying
the old workbench. CSV evidence templates come from `expand templates`;
`expand import --kind <kind> --input <file.csv>` accepts sourced dated
security, action, nominal price, quote, borrow approval, margin, fact, thesis,
decision, holdings and NAV records. Historical evidence vintages cannot be
silently overwritten. Fact and whole-portfolio imports remain review inputs;
the published experiment is the isolated sleeve, not total SSI performance.

The weekday `Reverse-split borrow indications` workflow archives the public
IBKR file before the open, validates its checksum and record count, and
retains the file's actual timestamp. It never backdates availability and
never contacts TWS or an IB Gateway. Historical borrow, OTC price histories,
cash-in-lieu, dividends and terminal obligations still need sourced evidence.

Official auction prices come from the venue `statistics` files, obtained with
`databento-pull --schemas statistics --max-cost 0`. Daily UTC OHLCV alone does
not establish an official open or close. The benchmark follows the listing
venue in dated definitions; missing auction prices remain missing.
See [Databento's statistics definition](https://databento.com/docs/schemas-and-data-formats/statistics).

## Shorts alpha program: Phase 0 (2026-10-18)

Phase 0 of `_system/proposals/shorts_alpha_program_2026-10-18.md` installs
pre-registration and answers two questions from data already local. Code:
`reverse_splits/phase0_research.py` (from `_system/scripts`:
`python -m reverse_splits.phase0_research --publish`); tests in
`tests/reverse_splits/test_rs_phase0.py`. No broker, ThetaData or vendor
request is involved and no new licensed data was downloaded.

| File | Purpose |
|---|---|
| `hypotheses.jsonl` | The registry: H1-H17 with cohort, horizon, exit, cost model, metric, success and kill criteria, split and `declared_at`. Rows may gain a `status` or `result_ref`; `declared_at` never changes. |
| `phase0_research.json` | Aggregate results for H1, H7 and H8 on the train (2018-05 to 2022-12) and validation (2023 to 2024) splits, with each hypothesis read against its registered criteria. |
| `phase0_manifest.json` | Hashes of the output, the registry, the module, the frozen run inputs and every venue file read. |
| `local/holdout/phase0_holdout.json` | Sealed: results for entry sessions from 2025-01-01, not committed and not read until the program's final review. |
| `local/phase0/phase0_full.local.json` | Per-event rows and control matches; licensed returns stay local. |

`check_reverse_splits.py --strict` now refuses a research JSON beside the
ledger that cites a hypothesis id missing from the registry or declared after
the result's `built_at`, that does not declare `aggregate_only: true`, or that
contains per-event or per-symbol-day keys.

### H1: the SSR cohort

Of the 671 verified ex+1 paths, 388 opened under an observed Rule 201
restriction, 282 did not and 1 is unknown. Gross official-open-to-close short
returns with issuer-clustered 95% intervals:

| Split | Restricted | Unrestricted | Difference |
|---|---|---|---|
| Train (2018-2022) | n 64, +3.4% [+1.3%, +5.6%] | n 56, +0.5% [-2.0%, +2.8%] | +2.9% [-0.2%, +6.0%], t 1.8 |
| Validate (2023-2024) | n 154, +3.7% [+1.9%, +5.4%] | n 88, +4.1% [+2.2%, +5.9%] | -0.4% [-3.0%, +2.2%], t -0.3 |

Both intervals cover zero, which is H1's registered kill branch: restricted
and unrestricted sessions are one population for the gross return, so the 58%
of events the account replays skip under SSR carry no return penalty. Rule 201
belongs in the fill model as a price constraint (workstream A3), not in the
admission rule. The bar-based proxy (prior low at or below 90% of the restated
prior close) agrees with the cached status on 551 of 668 events.

### H7 and H8: the generic weak-microcap fade

Universe: listed common, ordinary and ADS shares on Nasdaq, NYSE and NYSE
American; prior listing-venue close under $5; prior 20-session three-venue
dollar volume $50k-$20M; at least 20 prior printed sessions; no catalogued
reverse split within 30 days; both official auction prints present.
1,595,187 eligible symbol-days over 35 quarters (2.9% of otherwise eligible
days lack an official print). Gross short return from the official open to
the official close, equal weight per symbol-day; symbol-clustered intervals,
month-clustered in brackets.

| Condition | Train | Validate |
|---|---|---|
| All sessions | n 786,332: +0.20% [+0.18%, +0.22%] (month [+0.10%, +0.30%]) | n 409,808: +0.21% [+0.19%, +0.24%] (month [+0.08%, +0.33%]) |
| After a close down 10% or more | n 29,472: +0.36% [+0.24%, +0.49%] | n 16,103: +0.72% [+0.54%, +0.89%] |
| After a close up 20% or more | n 8,835: +1.28% [+0.94%, +1.61%] | n 5,261: +0.81% [+0.27%, +1.33%] |
| Prior close under $1 | +0.44% | +0.47% |
| Prior close $2 to $5 | +0.15% | +0.13% |
| H8 difference (down 10% minus up 20%) | -0.92% [-1.26%, -0.56%], t -5.2 | -0.09% [-0.64%, +0.46%], t -0.3 |

The fade is real, small and steady: +0.10% to +0.51% a year from 2018 to
2024, strongest under $1. H8 as registered (a larger fade after a -10% close)
is reversed on train and flat on validation; it is reported, not promoted.

### The split family in excess of the fade

Each event's return is compared with the same session's eligible universe and
with up to three same-session listed names nearest in log prior close (within
x2) and log dollar volume (within x3), with the subject's prior sessions
restated by the split ratio. The recomputed auction returns matched the frozen
study's for all 363 train and validation events.

| Comparator | Train (n 120) | Validate (n 243) |
|---|---|---|
| Same-session universe mean | subject +2.1% vs +0.1%: excess +1.9% [+0.3%, +3.6%] | subject +3.8% vs +0.3%: excess +3.5% [+2.2%, +4.8%] |
| Matched controls, calipers only | n 105: +1.8% [+0.2%, +3.4%] | n 185: +3.7% [+1.9%, +5.2%] |
| Matched controls, same prior-session bucket | n 97: +1.1% [-0.6%, +2.8%] | n 166: +3.3% [+1.5%, +5.1%] |

The post-split return is not the generic fade: comparable names fade a few
tenths of a percent on the same sessions, and the split-specific excess is
+1.8% on train and +3.5% on validation. All of this is gross price behaviour;
no borrow, fill, spread or commission assumption enters any Phase 0 number.

## Shorts alpha program: workstream A, execution and capacity realism (2026-10-18)

Workstream A of `_system/proposals/shorts_alpha_program_2026-10-18.md` tests
the three fill-model conventions that the proposal says consume the gross
edge: the opening auction as a size lever (H4), passive offers under Rule 201
on restricted sessions (H18, the free-data form of H2) and participation over
time instead of a 0.1%-of-ADV cap (H19, the free-data form of H3), with IBKR
tiered commissions beside the fixed schedule as a declared variant. Code:
`reverse_splits/execution_realism.py` (events, requests, the free-only data
gate) and `reverse_splits/execution_realism_build.py` (analysis and
publication); tests in `tests/reverse_splits/test_rs_execution_realism.py`.
From `_system/scripts`:

```powershell
python -m reverse_splits.execution_realism quote      # price every request; downloads nothing; resumable
python -m reverse_splits.execution_realism download   # fetches only requests quoted at exactly $0.00
python -m reverse_splits.execution_realism build --publish
```

| File | Purpose |
|---|---|
| `execution_realism.json` | Aggregate results for H4, H18 and H19 on the train (2018-05 to 2022-12) and validation (2023 to 2024) splits, each read against its registered criteria, plus the commission variants and the data coverage and cost actually incurred ($0). |
| `execution_realism_manifest.json` | Hashes of the output, the registry, both modules, the frozen run inputs, the cached books, every statistics file and every bar file read; the list of hypotheses the build actually measured; the download receipts. |
| `local/holdout/execution_realism_holdout.json` | Sealed: the same results for entry sessions from 2025-01-01, not committed and not read until the program's final review. |
| `local/workstream_a/` | Per-event rows (`execution_realism_full.local.json`), `quotes.json` (every request with its quote), `downloads.json` and the archived paid-plan quote that was declined. |
| `local/raw/databento/{venue}/ohlcv-1s/sessions/` | The free one-second bar files, one per venue-session with its `.ok.json` receipt. Never committed. |

**Free data only.** The plan as proposed needed `trades` and `mbp-1` for
each event session. Every request was quoted first: $0.3245 for all 671
sessions ($0.2366 for train and validation only; $0.4778 with full-session
mbp-1), recorded in `local/workstream_a/quotes_paid_plan_2026-10-18.json`.
Drew's decision on 2026-10-18 was "nothing for now" and, going forward, free
data only. So H2 and H3 stay `registered` and unmeasured in
`hypotheses.jsonl`, blocked on that budget decision (their rows carry the
note and the quoted amounts so it can be revisited), and H18 and H19 measure
the same two questions on free data with the same success and kill
thresholds and an explicitly declared bar-based cost model, registered before
the bars were pulled. On this plan `ohlcv-1s`, `ohlcv-1m`, `ohlcv-1h`,
`statistics`, `status` and `definition` quote $0.00 on all three venues;
every quote, trade and book schema does not. `quote` prices every request
with `metadata.get_cost` and `download` fetches only those quoted at exactly
$0.00, with no override; the refused count and the receipts are in the
manifest. The book-level queue model and the print-based participation
pricer stay in `execution_realism_build.py` as the tested design for H2 and
H3; they are not run.

### H4: the opening cross is not a size lever at $50k

Official opening cross price and matched shares from the listing venue's
`statistics` file (every one of the 671 events has exactly one cross row and
its price equals the frozen study's official open). The modeled order is 2.5%
of a $50k account ($1,250) in whole shares at the printed price; "replay" is
that order capped at 0.1% of the prior 20-session split-adjusted venue ADV,
the frozen account replay's sizing. Feasible means at most 5% of the cross.

| Split, SSR state | n | $1,250 order feasible (issuer CI) | median cross | median order / cross | replay order feasible | replay orders under $100 |
|---|---:|---|---:|---:|---:|---:|
| Train, all | 120 | 45.0% [35.9%, 53.5%] | $21.4k | 0.06 | 100% | 54 |
| Train, restricted | 64 | 45.3% [33.9%, 57.4%] | $22.7k | 0.05 | 100% | 29 |
| Train, unrestricted | 56 | 44.6% [32.1%, 57.1%] | $16.2k | 0.08 | 100% | 25 |
| Validate, all | 243 | 24.3% [19.1%, 30.0%] | $6.7k | 0.19 | 92.2% | 173 |
| Validate, restricted | 153 | 19.6% [13.4%, 26.5%] | $6.5k | 0.19 | 95.4% | 118 |
| Validate, unrestricted | 88 | 33.0% [23.0%, 42.7%] | $10.3k | 0.12 | 86.4% | 53 |

By year the feasible share runs 38% to 82% in 2018 to 2021 and 20% to 28% in
2022 to 2024 as the median cross falls from $22k-$82k to $6k-$10k; it is 18% to
20% for opens under $5 and 49% at $5 and over; 51% on NYSE against 27% on
Nasdaq and NYSE American. The closing cross supports the $1,250 cover in 15%
of validation events. The replay order is feasible almost everywhere only
because it is tiny: its median is 9 shares on validation and 173 of 243 such
orders fall under the replay's own $100 minimum.

**Assessment.** H4's kill branch (under 50% on validation) is met: 24.3%.
The auction is a legality lever under Rule 201, not a size lever; a $1,250
order is a fifth of the median cross in 2023-2024, so an auction entry of the
modeled size would itself set the print. The SSR state does not change the
reading (restricted 19.6%, unrestricted 33.0%).

### H18: a passive offer under SSR rarely fills in 15 minutes

Inputs: one-second listing-venue bars for each event session (550 files,
$0.00) and the opening and closing books the earlier quote study cached for
every event (bid, ask and displayed sizes one second and thirty seconds after
the open and one second before the close; 555, 647 and 636 valid books). The
offer rests at the cached venue best offer one second after the open (thirty
seconds where that book is missing), behind that level's displayed size. Each
later second's volume is spread evenly over the bar's tick prices; the part
at or above the offer depletes the queue ahead and then fills the order at
the offer. No cancellations are credited and no re-pricing is modeled, so the
fill rate is an upper bound against the book-level model and the fill price a
lower bound. Adverse selection is the last bar close five minutes after
completion minus the fill price, over the arrival midpoint.

| Restricted sessions, $1,250 order | Train | Validate |
|---|---|---|
| Simulated (no arrival book) | 58 (6) | 149 (4) |
| Filled within 15 minutes (issuer CI) | 48.3% [35.7%, 60.7%] | 22.1% [15.9%, 28.7%] |
| of which on bars entirely above the offer (possible re-pricing) | 20 of 28 | 21 of 33 |
| Partial fills; mean filled fraction | 5; 52% | 20; 25% |
| Time to fill, median (p75) | 139 s (324 s) | 176 s (422 s) |
| Displayed queue ahead, median; order, median | 166 sh; 330 sh | 53 sh; 337 sh |
| Fill price over the arrival mid (the half-spread earned) | +1.12% | +1.15% |
| Adverse selection, 5 min, mean (CI); median | +1.89% [+0.1%, +4.1%]; +0.48% | +0.75% [-0.9%, +2.2%]; +0.99% |
| Unfilled: midpoint drift to the 15-minute deadline | -2.05% | -2.44% |
| Filled: gross short return to the official close | +3.43% | +4.19% |

The $1,250 order is six times the displayed size at the offer on validation,
and buyers lift that much within 15 minutes in only a fifth of restricted
sessions (2018-2021: 50% to 86% on small samples; 2022-2024: 18% to 35%).
Unrestricted sessions fill less often still (30.6% train, 15.9% validate).
The order the replay actually sized (median 9 shares) fills 31.3% of the
time; a $6,250 order 13.4%; a $25,000 order 4.0%. While the offer waits, the
midpoint falls about 2.4%: the fade happens without the position. Filled
orders earn the half-spread and then give it back within five minutes
(adverse selection +0.75% mean, +0.99% median on validation, above the 0.5%
threshold).

**Assessment.** H18's kill branch (fill rate under 25% on validation) is
met at 22.1%, and the adverse-selection half of the success criterion fails
as well. Rule 201 is a price constraint, as Phase 0 said, but resting at the
offer is not the way through it at this order size: the displayed book at the
open is too thin and the price moves away while the order waits.

### H19: participation over time gives the edge away before it pays the spread

A fixed share (1%, 2%, 5%) of every bar's volume from the arrival book for
60 minutes, at the bar's range midpoint, with the opening cross removed by
its statistics size (removed on every priced event); the cover is the same
schedule over the last 60 minutes from the first bar at or after 15:00 (the
last close before it when nothing printed within five minutes), any residual
at the official closing print. Cost = entry shortfall + exit shortfall +
crossing fraction x the cached half-spreads (open books for the entry, close
book for the cover), over the entry arrival midpoint. The primary reading is
the registered one: the order is 1% of the window's volume and every fill
pays the half-spread.

| 1% of first-hour volume, 634 priced events | Train (n 106) | Validate (n 233) |
|---|---|---|
| Entry shortfall (arrival mid minus sell VWAP) | +0.49% | +1.79% |
| Exit shortfall (buy VWAP minus 15:00 price) | -0.25% | -0.07% |
| Half-spreads, round trip (cached open and close books) | +1.72% | +2.73% |
| Round-trip cost, crossing fraction 1.0 (issuer CI) | +1.96% [+0.8%, +3.0%] | +4.45% [+3.6%, +5.3%] |
| Round-trip cost, crossing fraction 0.5 | +1.10% | +3.08% |
| Open-to-close benchmark, same events | +2.28% | +3.77% |
| Benchmark minus cost (CI) | +0.32% [-1.4%, +2.0%] | -0.68% [-2.1%, +0.7%] |
| Realized short return, net of the spread term (CI) | +0.11% [-1.3%, +1.5%] | -0.21% [-1.5%, +1.1%] |
| Position at 1%: median (IQR) | $432 ($140 to $1,723) | $190 ($56 to $545) |
| Position at 5%: median | $2,162 | $952 |
| Residual covered at the closing print | 34% | 34% |

The cost per share does not depend on the rate under a print-following model
(1%, 2% and 5% give the same VWAP); the rate sets capacity, and capacity is
small: median first-hour volume is $53k on train and $20k on validation, so
1% is a few hundred dollars per event and 5% is under $1,000. The entry
shortfall is the fade itself: on validation the price falls 1.8% during the
hour the schedule is still selling, before any spread is paid. By year the
cost is 0% to 1% in 2018-2021 and 4.2% to 4.5% in 2022-2024 against
benchmarks of 3.4% to 4.1%; by venue 2.8% on NYSE against a 1.1% benchmark
and 3.9% on Nasdaq against 3.8%. A fixed $1,250 order completes within the
hour in 35% of train and 15% of validation events at 1% (63% and 42% at 5%).
The official open prints 0.2% to 0.4% below the one-second midpoint, so the
auction is not the price lever either.

**Assessment.** H19's kill branch is met on validation: the round-trip cost
(4.45%) exceeds the same events' open-to-close benchmark (3.77%). Train sits
between the thresholds (1.96% against 2.28%). With the crossing fraction at
0.5 the validation cost is still 3.08%, above the 1.5% success line.

### What workstream A says

All three fill conventions the proposal expected to release the edge fail on
validation with free data: the opening cross cannot absorb the order, a
passive offer under SSR seldom fills before the fade happens, and spreading
the order over the first hour converts most of the edge into shortfall before
the spread is paid. The sessions the account replay skips under SSR carry the
same gross return (Phase 0), but no execution modeled here collects it at
$1,250 a name, let alone at $6,250 or $25,000. The proposal's own stop
condition ("the SSR cohort and the participation cost curve both fail")
applies to the execution side: capacity really is this edge's ceiling, and
weight moves to breadth (workstream C). Everything above is an upper bound on
fills and a model without impact, so the real numbers are worse, not better.

### Commissions as declared variants

Round-trip commission, venue fees and clearing over the entry notional for the
auction orders (official open and close prints), regulatory pass-through
reported separately and identical under both schedules:

| Order | Fixed ($0.005/sh, $1 min, 1% cap) | Tiered ($0.0035/sh, $0.35 min, 1% cap, exchange fees, clearing) | Tiered cheaper |
|---|---:|---:|---:|
| $1,250 account order, train (median 268 sh) | 0.3% | 0.4% | 24% |
| $1,250 account order, validate (median 318 sh) | 0.3% | 0.4% | 14% |
| Replay order, train (median 26 sh) | 1.3% | 1.0% | 66% |
| Replay order, validate (median 10 sh) | 1.6% | 1.5% | 44% |

At the account order the fixed schedule is cheaper because the tiered
take-fee ($0.0030/sh removing liquidity) outweighs the lower per-share rate;
tiered only wins on the replay's tiny tickets, where the $1 minimum binds.
Passive fills from H18 earn the tiered add-liquidity rebate only when the
fill model fills: on the 43 train and 49 validation fills the round trip is
0.27% / 0.30% fixed against 0.20% / 0.24% tiered, tiered cheaper on every
one. The 1%-participation position (median 116 shares train, 38 validate)
costs 0.82% / 1.19% fixed against 0.72% / 0.98% tiered: at these ticket sizes
the fixed minimum is a material part of the cost either way.

## Original ledger schemas

### Historical execution evidence

`execution_research.json` contains aggregate costs measured from Databento's
historical quotes for the published 671 one-day price events, plus MBP-10
depth for the original 35 account entries. Licensed books, individual results,
historical symbols, source hashes and request/cost receipts remain in
`local/execution_research/`. The original frozen experiments stay intact.

The dashboard's execution section supersedes the daily-range spread proxy as
an execution estimate. The proxy remains explicitly labeled as an uncalibrated
stress scenario. Quoted spread, displayed depth, price changes relative to
auction benchmarks, commissions, assumed borrowing and additional latency/
impact sensitivities are reported separately.

Measurements use entry at 1 and 30 seconds after the scheduled open and cover
one second before the scheduled close, including early closes. Timestamp and
book-gap flags are rejected; MBP books require completed events. Account
comparisons require affirmative cached Nasdaq trading status at both times
and unrestricted SSR at entry. Quotes alone do not establish an approved
locate or a broker fill. The multi-venue sensitivity combines the listing
venue, NYSE Arca and Cboe EDGX where available, falling back to one valid
venue when necessary. It must not be described as full NBBO.

The original entries and share quantities remain fixed in this comparison.
The previous daily-volume cap delayed six partial covers; the new study
estimates full same-session covers only where displayed depth supports the
quantity. Missing exit books or insufficient depth remain disclosed. This
comparison does not replay whole-account selection or margin after changing
the fills. Additional 0/5/10/25 basis points per side are explicitly unmeasured
latency/impact sensitivities.

The latency diagnostic compares quantity-adjusted quoted execution prices
at the decision time and 10/100/500 milliseconds later on both legs. It
reports signed mean, median and 90th-percentile changes, including price
improvements. This measures background market movement without our orders;
it cannot establish causal market impact or actual broker fill delays.

`capital_risk` adds returns on gross exposure and required margin for the
price cohorts, individual cost components and execution scenarios. The
main house assumption is 100%, with 50% and 200% sensitivities. Initial and
FINRA per-share maintenance floors remain in all sensitivities. Encumbered
short proceeds are not required equity. Summed entry capital is reused over
the historical dates: P&L divided by it is a weighted capital return, not
an annual portfolio result. Simultaneous entry margin and $50k account
drawdown are shown separately. Historical broker margin schedules remain
unknown; these calculations cannot establish a broker-approved margin rate.

Tail statistics show worst losses, empirical 95% loss percentiles and the
average worst 5% of observations. 99% estimates are withheld below 100
observations. Listing-venue `ohlcv-1m` bars restrict the adverse-price
diagnostics to the regular session. Full entry/exit minute highs are bounds;
interior-minute highs omit the ambiguous boundary minutes. These are marks,
not covers. Missing intraday paths remain missing.

Explicit stress cases raise prices by 25%, 50%, 100%, 200% and 500%. The
combined stress also raises house margin to 200%, triples the original
case's annual borrowing assumption, holds seven calendar days and assumes
a 5% adverse cover cost. Borrow accrues on rounded collateral at the
stressed price for the whole delay. Results show loss on gross and original
margin, stressed margin demand and a conservative loss-plus-margin reserve.
The three-largest-position basket is hypothetical; it does not claim the
positions historically overlapped. No stress probability or finite maximum
short loss is asserted. Add `--intraday` to collect missing minute bars;
that collection uses its own `--max-cost` reservation budget.

With a Databento key supplied securely in the process environment:

```powershell
python -m _system.scripts.reverse_splits.execution_research --source-run _system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z --offline --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Omit `--offline` to download missing windows; each request is priced first.
`--max-cost` defaults to zero and caps new quoted-cost reservations per
collection. `--routing` also collects the two additional venues, with its
own collection budget. Metadata requests are limited to six per second.
Completed files are checksum-verified and reused. Raw market data is never
published.

### Full-sample costs, stops and funded portfolios

`portfolio_protocol.json` declares the account, comparison rules and scenario
matrix before calculating results. `portfolio_research.json` and its manifest
publish aggregate model results. The dashboard builder also exports all scalar scenario metrics to `dashboard/data/reverse_splits_portfolios.csv` (returns are fractions, dollars are USD). Licensed books, quote paths, individual
outcomes and daily account records remain in ignored `local/portfolio_research/`.
The original frozen studies and forward-validation protocol are preserved.

The primary account starts with $50,000 on 2018-05-01 and ends 2026-10-13.
It compounds sizes up to 2.5% of opening equity, admits at most three issuers,
requires $100 minimum notional, caps shares at 0.1% of prior split-adjusted
venue ADV and reserves 40% of opening equity beyond its entry-margin budget. The ADV proxy uses the preceding 20 exchange sessions; unknown volume adds no verified capacity, producing a conservative lower bound rather than assuming unknown returns are zero.
Admission ranking uses prior dollar volume. It never screens on the future
exit book, realized return or full-day volume. Margin requirements retain
initial and FINRA per-share floors and exclude encumbered short-sale proceeds.

Full-session one-second BBO observations combine up to 15 distinct exchange
feeds where their dated histories are available. These are not consolidated
NBBO. Fresh mutually consistent venue states are combined; stale conflicting
states are omitted. Midpoint stops at 5%, 10%
and 20% are monitored after entry; covers use a subsequent quote after a
100ms modeled response. Other cases cover after 15 or 60 minutes or before
the scheduled close, including early closes. Event-level depth is requested
at entry and close and for thinner risk exits. One-second top snapshots
remain where adequate or when deeper books are unavailable; subsecond moves
between sampled observations remain unknown. Missing venue books can
contribute their valid sampled top quote without duplicating the same venue.
Unchanged valid BBO states persist within a complete session until updated or invalidated; absent interval records do not expire resting quotes. Bad timestamps, crossed books and provider book-gap flags reset validity and are rejected. The 30-second event-book lookup is separate from full-session BBO state.

Cached national trading/SSR transitions gate entries. A restriction that
activates during the entry delay can prevent a fill. A stop during a halt
queues until a subsequent tradable quote where observed. Missing or
insufficient-depth covers are estimated and counted, never removed from the
results. Quotes during known nontrading states are excluded from cost calibration; intraday marks fall back to completed trade prices. Same-session completion of those estimates remains a conditional
assumption; delayed-exit and correlated squeeze stresses show additional
capital demands without assuming a stop can fill at its threshold.

For missing execution costs, match the entry price, prior dollar ADV, order
size, prior volatility, year and listing venue, together with entry timing and exit rule. Use
one nearest observation from each of up to 40 other issuers. The base is
the arithmetic mean of paired spread/depth costs; paired empirical cost
percentiles provide sensitivities. Donor dates and feature scaling use past
observations where at least 20 other issuers exist. During warmup, retrospective
issuer holdouts are labeled and permitted only for conditional cost accounting;
they cannot admit a trade through the expected-cost screen. Validation reports
entry half-spread errors and separate round-trip cost forecast errors by exit rule, including past-only comparisons and warmup counts. Measured pairs require sufficient observed depth; they do not identify missing liquidity or historical broker fills.

Every original price event gets standardized $125/$500/$1,250 target-exposure
outcomes, with at least one whole share, separately from account admissions.
Those hypothetical outcomes assume borrowing and complete covers and ignore
SSR/capital admission restrictions. The account replays separately compare
known-before-entry events, the unchanged fundamental score >=60 screen,
cost limits, fixed sizing and 2.5%/5%/10% equity caps per name, margin, residual execution cost, borrowing assumptions,
early and recent periods. Current-rate exclusions are retrospective illustrations.

Ordinary matched same-day settlement is modeled with zero billed borrowing
days and no separate pre-borrow charge. One-billed-day rates are sensitivities,
not historical invoices or an overnight price strategy. Commissions retain
the disclosed fixed per-share/minimum/cap assumptions; dated broker invoices,
historical house margins, approved locates and all other broker charges remain
unavailable. Cash interest is zero.

CAGR uses funded account equity and calendar elapsed years. Sharpe and Sortino
use all exchange sessions, including idle sessions; the main risk-free/target
rate is zero. A constant 4% Sharpe alternative is explicitly hypothetical.
Full-period Calmar and trailing 36-month Calmar each use matching CAGR and
drawdown windows. Also report serial-dependence sensitivity, volatility,
profit factor, expectancy, win rate, daily/trade loss tails, intraday marked
drawdowns, margin usage, turnover, exposure and year-by-year results. ROG and
ROM divide P&L by summed entry exposure/equity requirements; they are not
annualized portfolio growth. Year-block uncertainty is conditional on the
modeled account and observed history, not independent future evidence. Intraday marks include the immediate post-fill spread and fully costed closing equity. Margin breaches are reported without assuming a successful forced liquidation; such cases are unconstrained conditional paths.

A recovery pass checks incomplete auctions with a unique dated security
identity. Only observed entry/exit quote pairs enter the separately labeled
expanded comparison; the original 671-event definition remains fixed.
Unresolved identities and unpriced events remain coverage gaps. Authenticated
dataset metadata confirms that the configured venue history starts in May
2018; the user has no older Massive Advanced, TAQ or CRSP entitlement. No
pre-2018 returns are invented, and the sample is not a complete split census.

With the existing Databento key supplied securely in the process environment:

```powershell
python -m _system.scripts.reverse_splits.portfolio_data --stage access
python -m _system.scripts.reverse_splits.portfolio_data --stage sessions --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage supplemental --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage paths
python -m _system.scripts.reverse_splits.portfolio_data --stage depth --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage books
python -m _system.scripts.reverse_splits.portfolio_repair --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_research --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Collections reuse checksum-verified caches and quote each new request.
The cumulative research-download budget is $5 across session/supplement/depth/recovery
collections; metadata is free. No Theta terminal, IB Gateway, order API,
subscription upgrade or paid-data automation is involved.

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

## Databento venue files and the split detector (local)

`databento-pull` fetches Databento's venue datasets (`XNAS.ITCH`, `XNYS.PILLAR`,
`XASE.PILLAR`; they begin 2018-05-01) into `local/raw/databento/`: quarterly
all-symbol daily bars, monthly `definition` snapshots (issue type and listing
venue) and quarterly `status` (Reg SHO 201 state and halts). It needs
`DATABENTO_API_KEY`. Every request is priced first with `metadata.get_cost`
and refused above `--max-cost` (default $0.00, which the current plan quotes
for all of these). Reruns skip complete files. Venue files carry every
instrument that traded, including names that later delisted, at printed
prices. The data is licensed to us and SSI is public, so the files stay under
the gitignored `local/`; only derived event facts may enter the ledger.

`detect-splits` reads those files and finds reverse splits in printed prices:
a session that opens (or closes) at least 1.8x the prior close, within 30% of
a common ratio (15% for 1:2 and 1:3), with the median share volume of the
next five sessions at most 0.8x (0.6x for 1:2 and 1:3) of the five before.
A news move of the same size comes with rising volume and fails the rule.
Detections of one symbol within ten days are one event (a venue with no print
on the split day sees the jump at its next print), dated by the earliest
session. Events are classified with the definitions: only common, ordinary and
ADS shares listed on Nasdaq, NYSE or NYSE American count, and exchange test
symbols (`ZJZZT` and friends) never do. An event is `corroborated` when the
listing exchange saw it or at least two venues did. A lone print on a venue that
is not the listing market is weak evidence: on 2026-10-12, 10 of 20 such events
in a random sample were confirmed by an SEC filing, against 30 of 40
corroborated ones. Count only corroborated events. Calibration: the same
filing search confirmed 14 of 15 events the ledger already had. The result is reconciled against `events.jsonl` (same ticker, ex dates
within five days) and written to `local/reports/split_detections.csv` and
`local/reports/split_detection_reconciliation.json`:

- `matched`: in the ledger and in prices.
- `detector_only`: a discovery gap. Verify it against the filing before it
  enters the ledger.
- `ledger_only`: detector work, such as a ticker renamed since the split (the ledger keeps today's ticker; the venue file has the one in use then), an OTC
  name, or a first session below the jump threshold.

The ratio is inferred from prices and labelled so; the filing's ratio wins.

### Filing checks, the rename join, and adding detections to the ledger

`check-filings` asks EDGAR full-text search, for every corroborated
detector-only event, for a filing between 200 days before and 45 days after
the detected session that says reverse stock split, reverse split, reverse
share split, share consolidation or ADS ratio, together with the ticker.
EDGAR display names carry an issuer's *current* tickers, so there are two
ways to match:

- `display_ticker`: the issuer lists the ticker today.
- `ticker_text`: the issuer's own filings (8-K, 6-K, 10-Q/K, 20-F, proxies;
  never a prospectus) carry the ticker in their text. This is how a renamed or
  delisted company is found. It is weaker, needs two filings from a company
  showing another live ticker, and is skipped for tickers under three letters.

`check-filings` also runs the rename join. Every listed ledger event the
detector missed is matched to a detection within five days, with the same
ratio, whose issuer has the ledger event's CIK. Results are cached in
`reports/filing_checks.json` and `reports/rename_joins.json`.

`import-detections` adds the corroborated detector-only events to the ledger:
it imports the ledger into a scratch SQLite, upserts the rows, recomputes
cohorts per issuer (touching only rows that change) and writes the ledger with
`export_ledger`. Each row is `source = databento_price_jump` with
`needs_review = 1`, and its `status` and `confidence` are:

| `status` | Meaning | `confidence` |
|---|---|---|
| `filing_ratio` | Issuer confirmed, and the filing's own ratio agrees with the printed jump within 35% | 0.5 |
| `filing_confirmed` | Issuer confirmed, ratio inferred from prices | 0.4 |
| `filing_not_found` | No filing found | 0.3 |

A detection the rename join tied to an existing event, or one within ten days
of a ledger event with the same CIK, is that event and is skipped. Price data
never enters the ledger.

### Databento prices and Rule 201 in the book

`databento-prices` loads printed bars into `prices_daily` for every listed
ledger event (ex date -120 to +60 days). OHLC comes from the highest-volume
venue among XNAS, XNYS and XASE; volume is the sum of the three, which is less
than consolidated volume. A renamed ticker is priced under the symbol it
carried at the split. `ssr_flags` holds every (ticker, day) restricted at the
open: the last explicit Y/N in Nasdaq's `status` feed at or before 09:30 New
York time.

`[execution] ssr_policy` sets how the book treats a restricted entry bar:

- `ignore` (the default): existing books are unchanged.
- `exclude`: the entry is dropped (funnel stage `ssr_restricted`).
- `delay`: the entry moves to the next unrestricted session, at most two
  sessions later.

A short may still fill above the national best bid while restricted, so
`exclude` is the conservative reading and `delay` the faithful one for an
order at the open.

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

### One-session research and the October 14 validation cohort

The v4 study adds a primary benchmark: short at the official opening auction
of the session after a verified split and cover at that session's official
closing auction. It holds zero overnights. Gross return is `1 - close/open`,
with equal weight per event. Split-day open/close, closing-to-closing overnight
benchmarks and longer holds are shown separately. Account cases retain capital,
liquidity, spread, commission, collateral fees and unresolved obligations.

The historical financial screen remains score >=60, three numeric signals,
an operating-company profile and latest-period age <=200 days. A one-day entry
is skipped when observed SSR would delay it. Unknown SSR remains conditional.
Missing exit prices do not exclude an otherwise observable opening entry from
the account replay; the obligation remains open. Only complete benchmark pairs
enter the descriptive gross-return denominator.

`action_reviews.json` preserves ACON's rejected April 8, 2025 price-jump
candidate with the archived primary-source hash. It was a lone non-listing-venue
print; the June quarterly report identifies January and March splits. The
rejection corrects share/price reconciliation and never creates an earlier
entry signal. DBGI's issuer filing establishes the December 18, 2024 Nasdaq
suspension and expected OTC quotation; it supplies neither an OTC exit price
nor an end to the borrowing obligation. The exit audit retains every residual
path from the earlier published run and classifies remaining evidence gaps.

Current IBKR public inventory is archived with its timestamp, checksum and
quantity/rate indications. The dashboard reports median, mean and 90th
percentile annual rates for the current archive, priced one-day names and
financially screened names. These determine flat-rate sensitivities before
account replay. A separate illustration applies per-name current rates <=50%
and the 1% expected-cost screen to historical prices. **That illustration uses
current availability and is not a tradable historical selection rule.** Missing
quotes are not zero fees; public inventory is never an approved locate.

No private IBKR statement connection or Flex token is configured in this
research session. The import templates accept `borrow_fee` (dated broker annual
rates), `loan_event` (recall, return or buy-in records), `action_review` and
`forward_observation` in addition to prices, quotes, margin and actual locates.
Broker-statement rates replace scenario rates on their effective dates when a
verified dated security identity joins them. Unsupplied dates stay assumptions.
The minimum intraday borrowing charge is one calendar day. A missing prior
close uses an explicitly recorded entry-price collateral proxy, not NaN or a
zero fee. Actual loan termination requires broker evidence.

`forward_protocol.json` freezes the initial paper version before October 14:
next-session open to same close, unchanged fundamental screen, approved locate,
fresh quote, dated margin/security/thesis, <=50% annual borrowing rate and <=1%
estimated total cost. Sizing uses <=0.1% of prior ADV, <=2.5% of equity, three
names and a 0.5% name-loss budget under a +200% price stress, triple fees and
seven calendar days of exit delay. These are research budgets, not guaranteed
loss limits. One overnight is a comparator rather than the frozen primary rule.

Controls use different weak issuers, same current SIC division, score within
15, prior price within factor 2 and prior dollar volume within factor 3. Choose
up to three by pre-entry distance, never by subsequent return. The current
historical control pool is partial and event-derived. Its +/-30-day action
exclusion is retrospective, so excess return is diagnostic rather than causal.

The registry retains provisional future disclosures and first-recorded times.
They need action, identity and execution verification before becoming eligible
paper trades. The first result review needs at least 100 completed events and
60 issuers with cost/exit evidence; neither threshold guarantees a representative
sample. There are no completed new-cohort outcomes before October 14.

```powershell
python -m _system.scripts.reverse_splits.cli expand templates
python -m _system.scripts.reverse_splits.cli expand import --kind borrow_fee --input path/to/dated_fees.csv
python -m _system.scripts.reverse_splits.cli expand import --kind loan_event --input path/to/loan_returns.csv
python -m _system.scripts.reverse_splits.cli expand forward --end YYYY-MM-DD
python -m _system.scripts.reverse_splits.cli expand study --start 2018-05-01 --end YYYY-MM-DD
python -m _system.scripts.reverse_splits.cli expand publish
python _system/scripts/build_reverse_splits_dashboard.py
```

The forward collector uses SEC public sources and IBKR public FTP. It never
connects to ThetaData or the IB Gateway, places orders or purchases data. A
weekday 17:30 Eastern thread follow-up checks meaningful changes; absent
licensed price updates and broker records, it reports evidence gaps rather
than invented paper fills. Full immutable history snapshots are manual because
disk space is limited. Repeated companyfacts use hash-checked hardlinks only
from a completed immutable snapshot; mutable databases are separately frozen.

- Historical approved locates are not supplied by the public availability
  file. The strict book needs a dated approval reference, quantity and fee,
  plus the other execution evidence.
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

## Portfolio-NAV sleeve illustration (2026-10-19)

The backtest route opens with incremental portfolio contribution, observed
price-cohort distributions, five-year month-block Monte Carlo, and hypothetical
margin/collateral. Existing strategy versions and source audits remain in the
research fold below it.

`_system/scripts/short_sleeve_research.py` reads the frozen local 20261013 run
and cached quote observations, without network or broker access. Rebuild with:

```text
python _system/scripts/short_sleeve_research.py --source-root /path/to/local/repo --out dashboard/data/short_sleeve.json
```

CI uses the committed aggregate feed; licensed prices, per-trade observations,
actual account NAV and account identifiers are not published. The feed contains
90 comparisons: a fixed hypothetical $10m total NAV, three position weights
(25/50/100 bps = $25k/$50k/$100k), five holding periods, two capacity conventions
and exactly three combined cost cases. The default requests the full ticket;
the capacity alternative reduces it to the prior-volume limit.
Sizing is a fixed fraction of starting total NAV in dollars, not an independently
funded $50k sleeve. Core investment returns are held at zero.
Combined Michael-portfolio performance cannot be inferred from these results.

Bear/base/bull combine the 75th/50th/25th cached half-spread percentiles plus
the measured full-population mean displayed-depth cost, respectively, with
the 90th-percentile/mean/median current indicative borrowing rate for quoted
reverse-split names. Fixed commissions are additional. Larger orders and
multi-session execution remain cost sensitivities, not verified fills.
Borrow uses rounded 102% collateral and settled calendar days under T+2/T+1.
IBKR Pro USD short-proceeds interest is credited separately, once per account,
on settled rounded collateral including weekends until cover settlement.
Other USD shorts are assumed to consume the first $100k zero-rate band; a
minimum $100k external balance makes the sleeve's marginal credit conservative
relative to unknown higher account tiers. The current 2026-10-19 tier rates
(2.63%/3.38%/3.63%) are held fixed throughout as a sensitivity, not a reconstruction
of historical paid interest. Same-day settled-flat trades earn no short credit.
Core-account debit interest, collateral top-up funding and ordinary cash interest
are excluded because settled account cash and financing history are unavailable.
Closed-trade descriptive statistics exclude the account-level proceeds credit;
portfolio performance and Monte Carlo include it.
Missing closes retain the last liability mark; covers wait for an observed close.
Open positions at the cutoff remain open rather than being deleted.

An explicit reconciliation reproduces the original 1/5/10/20-session gross
event-study counts and means. It also rebases the original eligible account's
exact daily cash P&L onto $10m without enlarging its 115 historical tickets.
The original account used event-specific quotes, displayed depth, entry-margin
and trading-status checks; its accepted trades had about 1.38% weighted
spread/depth costs. The new Base's 3.11% is a broad-cohort sensitivity: 2.44%
median paired quote half-spreads plus 0.67% depth from a separate $500-reference
study. Neither estimate establishes executable costs at $25k-$100k.

The browser worker resamples whole interior calendar months, omitting partial
endpoint months, with the same draws across all three cases (2,000 paths,
five years, fixed seed). It resamples aggregate daily dollar P&L against starting
NAV, along with margin and collateral; it does not reconstruct broker fills or
position continuity at block boundaries. Insolvent paths keep their lower-tail
rank in CAGR summaries. Unseen squeezes are assessed separately, not assigned
bootstrap probabilities. Calmar is unavailable when drawdown is zero.

Margin is a hypothetical 100% house floor plus FINRA per-share floors. Collateral
includes restricted short proceeds and must not be added to margin as a second
equity charge. The +200% squeeze reserve adds price loss to post-shock margin
under a 200% house requirement. This is neither a worst possible loss nor
Michael's actual available excess liquidity. All published statistics are
conditional research; none changes a strategy threshold or order permission.

### Matched execution-cost audit (2026-10-19)

`_system/scripts/short_execution_audit.py` verifies the frozen books, decision
points, path index and each of 671 cached path files before comparing listing
and observed multi-venue quotes at identical decision times. It separately
sweeps the same original share quantity through entry and cover depth at
$500/$25k/$50k/$100k. Spread, additional depth, commissions and timing relative
to the auction benchmark reconcile to the exact price-P&L shortfall.

`dashboard/data/short_execution_audit.json` publishes aggregates only; the
generated `execution_cost_audit_2026-10-19.md` reports the comparisons. Static
book support is not a broker fill. Unsupported quantities remain coverage gaps;
cost summaries condition on both legs fitting the displayed books, so different
size rows have different surviving samples. A common-support table holds the
same events fixed and explicitly identifies that hindsight selection.

Rebuild using the existing licensed local cache:

```text
python _system/scripts/short_execution_audit.py --source-root /path/to/local/repo --local-out /path/to/local/execution_cost_audit/20261019_v1 --out dashboard/data/short_execution_audit.json --report _system/data/reverse_splits/execution_cost_audit_2026-10-19.md --databento-access-receipt /path/to/local/databento_access_summary.local.json
```

The local acquisition plan defines 4,000 entry/exit windows for the five
holding periods, including 595 windows for 100 events selected deterministically
by year, listing venue and prior liquidity, without return outcomes. Multi-day
historical exit symbols require confirmation before collection. The optional
Massive collector uses an existing licensed environment key, bounded requests,
safe pagination, local-only raw records and SIP timestamps for as-of quote
selection. Provider denials stop collection. No purchases, subscription upgrades,
broker connections, ThetaData calls or trades occur.

Databento access was verified on 2026-10-19 using the existing protected local
credential. The earlier environment-only credential check missed it. Through
the authenticated historical API, EQUS.SIP and EQUS.ALL returned
`dataset_not_found`; this is an observed access result, not a claim that the
provider cannot supply those products. EQUS.MINI is available from 2023-03-28
and provides a derived BBO from a venue subset, not official consolidated NBBO.
Individual historical venue feeds are also available. The local same-day
100-event pilot expands to 2,444 concrete quote/depth requests. Free metadata
checks priced sampled requests above zero; no chargeable downloads were made.
The user explicitly confirmed a **$0 cap on new downloads**. No new data have
replaced the existing cached estimates. Verified NBBO pairs and actual broker
fills remain zero. Raw receipts, request plans and credentials stay local;
the public feed includes only allowlisted access/pricing metadata.

The dashboard shows these findings inside execution evidence. Its 90 sleeve
scenarios retain the legacy costs as sensitivities: neither the conditional
supported-order means nor the available-venue touch spread is substituted for
the missing full-population, size-dependent, multi-session execution costs.

### Adaptive sizing experiment (2026-10-20)

`_system/scripts/short_adaptive_sizing.py` tests fixed $25k/$50k/$100k,
cost-filtered sizing and conditional gross-edge-plus-cost sizing on $10m NAV.
The 56 eligible events before 2023 initialize an expanding fit; all 226 eligible
events from 2023-01-03 to 2026-10-13 remain in the test population. Only earlier
sessions supply training labels. Entry quotes, prior venue dollar volume,
price and split multiple are entry-time features. The protocol is fixed before
the first run and published inside `dashboard/data/short_adaptive_sizing.json`.
This is retrospective walk-forward research designed after previous inspection
of the sample, not an untouched or prospective validation cohort.

Admissions never inspect the future cover book or realized test return.
Candidate orders must fit the decision book within 3% below the midpoint.
The response book 100ms later can give partial or zero IOC fills. Missing cover
depth is retained using declared residual-price sensitivities, with its share
fraction and trade count disclosed. Additional impact is 0/25/50 bps per side
for bull/base/bear; unsupported cover shares are priced 2/5/10% above the worst
available ask. These are assumptions, not calibrated fill or impact estimates.
All policies share three-name, issuer and entry squeeze-reserve constraints.
Same-session modeled closes have zero settled borrow and proceeds-interest
accrual; delayed real completions would change financing.

The first base run takes five adaptive trades, all $25k targets, and earns
$13,348 versus $30,693 on 32 fixed-$25k trades. It does not establish a return
uplift from fitting gross edge. The adaptive sample has zero observed drawdown
and undefined Calmar; five winners cannot establish a squeeze-tail estimate.
One adaptive cover includes modeled residual shares. Results, financing/risk
limits and all three cases are in `adaptive_sizing_2026-10-20.md`.

The shared month-block bootstrap now keeps every boundary-month session. The
prior routine dropped the first and last month, which could remove a real tail
loss and reverse the apparent result in a sparse sleeve. A regression test
ensures those losses remain eligible for resampling. Resampling still cannot
invent losses absent from five profitable trades or refit the policy.

```text
python _system/scripts/short_adaptive_sizing.py --source-root /path/to/licensed/cache/repo --local-out /path/to/local/adaptive_sizing/20261020_v1 --out dashboard/data/short_adaptive_sizing.json --report _system/data/reverse_splits/adaptive_sizing_2026-10-20.md
```

No additional downloads occur. Individual decisions, training counts, forecasts
and fills stay local. Only aggregate performance and the protocol publish.
This first test is same-day; multi-session cover costs remain unmeasured.
