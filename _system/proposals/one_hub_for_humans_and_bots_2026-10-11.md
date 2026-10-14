# One hub for humans and bots: consolidating Michael's repos and the reverse-split study into SSI

**Date:** 2026-10-11
**Status:** implemented 2026-10-12 (phases 0 to 4 in one pass; see § Implementation record at the end). Still open: Drive-folder sharing with Michael's accounts, bot tokens (created by each owner), the Magis-room decision, Decision 1 on visibility, and archiving the reverse-split repo once its local workbench is no longer in use.
**Readers:** Drew, Michael, and every Cursor/Grok desk bot that touches Magis research. This file is the contract until `CONTRIBUTING.md` and `docs/WRITE_MAP.md` exist (Phase 0 creates both from it).
**Template:** `_system/prompts/architecture_review_template.md`

## Decision in one paragraph

`single-stock-investments` (SSI) is already the hub: the universe, the dashboard, 30 monitored lanes, the review gates, and the only place where structured facts and derived JSON are rebuilt by CI. Michael's two GitHub repos and the reverse-split study were started outside it because nobody but Drew can write to SSI and because the one place the desk bots are told to write is a folder on Drew's laptop. Fix the access and the write path, fold the three outside pieces into SSI's existing patterns (append-only ledgers, schema-validated drops, lanes with receipts, one dashboard), and archive the side repos. Nothing new is invented that SSI does not already do for warrants, CVRs and separations.

## What exists outside SSI today (inventory, verified 2026-10-11)

| Source | What is actually there | Unique and worth keeping | Verdict |
|---|---|---|---|
| `magis-capital-partners/Special-Situations` | One commit, one file: `README.md` containing the title. Author "Cursor Agent", 2026-10-07. | Nothing. The desk's real work already landed in SSI: the Special Situations desk (PR #1137), the separations register (PR #1146), and the Grok prompt `_system/prompts/grok_scan_agents.md`. | Archive. Point the README at SSI `#/ideas/situations`. |
| `magis-capital-partners/Short-Selling` | An Astro static site (38 files). Nine entries, all fictional placeholders (`FKTN*` tickers, `example: true`). A content schema, a `CONTRIBUTING.md`, and a Cloudflare Pages + Access deploy guide. | The **entry contract**: `type` (idea / playbook / paper), eight categories, four statuses, `source` = bot id, `dateAdded` / `lastUpdated`, tags, summary; one idea per file; never rename a merged file; figures need a source and a date; no copyrighted text. The **contribution rules** for bots and people. The Access recipe is already how the SSI dashboard is served. | Adopt the contract into SSI's Short Alpha ledger and templates. Do not run a second website; the Shorts tab is the site. Archive the repo. |
| `reverse-split-short-research` (local clone, origin in the org, 7 commits, 795 uncommitted lines) | A real system: `rsdb` Python package, SQLite with about 1,000 reverse-split events over five years, EDGAR date enrichment, Yahoo prices, FINRA short-interest proxy, borrow snapshots, backtest and "realism" scenario suites, the RSI-1.0 strategy process with six analyst lenses and an append-only decision journal, a read-only bridge that imports SSI's own fundamentals extractor and short-alpha thresholds, a local dashboard, 69 passing tests, a 22-page research contract. | Nearly all of it. It is the reverse-split short engine Short Alpha lacks (SSI has the tag and the caveat but no detector). The bridge already consumes SSI code by file path; inside SSI it becomes an import. | Migrate as a lane. Archive the repo with a pointer after the move. |
| `C:\Users\drewg\Projects\.agent-memory\hubs\research-equity\` | The memory mesh hub. `CONTEXT.md` defines six Magis Grok desks (Special Situations, Activism, Fundamentals, NOL, Tape, Stahl) and tells each to "write proposals only to this hub `daily/`". Daily files hold real desk output (the MDT/MMED split-off was read there on Oct 6). | The desk mandates and the proposal discipline (`[PROPOSED]` with Evidence / Seen / Harmful / Scope / Review after). | Keep the mesh for cross-repo context. Move the **desk output** into SSI, because the hub has no git remote: Michael's bots cannot read or write it, and nothing is backed up. |

Three facts that shape the design:

1. **SSI is public; the research vault is private.** Chosen for unlimited Actions minutes (`_system/reference/research-vault-split.md` § 6). Everything committed to SSI is readable by anyone, including `_system/research/short-alpha/ideas.json` (real short share counts) and `dashboard/data/sleeves_michael.json` (63 positions with quantities and cost).
2. **Only Drew can write.** `GoldmanDrew` admin, `mcricenti` read-only on SSI; `main` has no ruleset beyond "no force-push". Automerge recognises only `cursor/`, `codex/` and `claude/` branches, and research PRs need a provenance manifest.
3. **The reverse-split tool defaults to IB Gateway client id 17.** That is the SPX 0DTE live executor's id in `_system/trading/ib_gateway_client_registry.v1.json`. It must never run against the shared Gateway from any Magis machine. Borrow comes from the IBKR Client Portal availability CSV, which both `rsdb` and SSI already support.

## Goal

One repo that both humans and both sets of bots add to and update, with:

- one write map (who may write what, where, in which format, checked by what, consumed by whom);
- every dataset as a contract (schema, validator, test, lane, freshness entry) rather than a folder of files;
- bots writing through pull requests on a known branch prefix, auto-merged only for schema-validated data drops, never for code;
- the dashboard as the single reading surface;
- the side repos archived with pointers.

## Constraints

- **Must keep:** framework governance (extend existing docs and `valuation.json` keys before adding files); the lane-and-receipt supervisor model (an undeclared lane is invisible); `commit-main` and sparse checkouts; append-only ledgers with first-write-wins; human gates on `MEMORY.md`, `human_decision.json`, `reviews/approved/`, live capital; the research-vault split for licensed and sensitive text; IB Gateway rules (no contact from this repo; Rule 9 has no exceptions).
- **Must not break:** the 30 lanes, `python-tests.yml` path filters, the Cloudflare Pages deploy, the D1 row budget (desk output goes to git, not D1).
- **Non-goals:** a second website; a shared SQLite in git; a chat integration; changing how Marvin, Milly or Vicki work.

## Design principles (the "professional" part, stated once)

| Principle | Concretely in SSI |
|---|---|
| Git holds facts and code; D1 holds mutable human state; Drive holds PDFs; the vault holds licensed or sensitive text | Desk briefs, registers, ledgers and derived JSON in git. Sleeve notes and decisions in D1. Books and letters on Drive and in the vault. |
| One contract per dataset | `schema.json` next to the data, a `check_*.py` validator, a test, a lane, a `data_feeds` entry with `assert_fields`. The warrants and separations directories are the template. |
| Append-only, first write wins | JSONL ledgers; corrections are new versions, never edits (`separation_amendments.jsonl` pattern). |
| Derived files are rebuilt, never hand-edited | `dashboard/data/*.json` regenerated by CI; conflicts resolved by regeneration (`ci_push_main.sh`). |
| Bots write through PRs with a declared prefix and an allowlist of paths | A path guard rejects any bot PR that touches code or a human-gated path. |
| A headline is never a term; an estimate always carries a confidence | Same rule the separations register enforces, applied to short entries and desk briefs. |
| Nothing larger than a few MB in git; raw caches are reproducible and ignored | SQLite and price caches stay local; the compact event ledger is committed. |
| Every feed has health, and health is asserted on contents, not just a timestamp | `health.status` and `structural_errors` blocks, P6 `assert_fields`. |

## The write map (the thing everyone reads)

Branch prefixes: humans use any branch; Cursor research agents keep `cursor/`; Grok desk bots use `grok/<desk>/<yyyy-mm-dd>-<slug>`. CI commits through `commit-main` as today.

| Actor | May write | Format and checker | Gate | Consumer |
|---|---|---|---|---|
| **Drew** | Everything, by PR. Sole approver of `_system/memory/MEMORY.md`, `human_decision.json`, `reviews/approved/`, framework files, rulesets, secrets. | Existing lints and `python-tests.yml`. | Self-review on code; none on data drops. | Whole repo. |
| **Michael** | Same research paths as Drew: ticker `research/`, Short Alpha ledgers, separations register seeds, desk briefs, `reviews/pending/`, `_system/memory/daily/`. Owns the Michael sleeve notes (D1) and the reverse-split strategy decisions. Code by PR with Drew's review. | Same. | `reviews/approved/`, `MEMORY.md` and `human_decision.json` stay Drew's. | Same. |
| **Grok desk bots (Drew's and Michael's)** | 1. `_system/data/desk_briefs/<desk>/<date>.json` (new; schema below). 2. Drive `Admin/Intake/{Kind}/{TICKER}/` PDFs (existing). 3. `_system/data/separations/separation_registry.jsonl` seed rows with accessions (existing rule). 4. `_system/research/short-alpha/candidates.json` rows with `origin: desk_note` and the matching entry file (Phase 2). 5. `_system/memory/daily/<date>.md` `[PROPOSED]` bullets (existing triage consumer). 6. `{T}/third-party-analyses/vic/*.md` (existing). | `check_desk_briefs.py`, `check_separation_universe.py --strict`, `build_short_alpha_dashboard.py --check`, `check_contributor_paths.py` (new path guard). | Auto-merge when every check passes **and** the PR touches only allowlisted data paths. Anything else waits for a human. | Dashboard Inbox and desk panels; review queue; the separations and short-alpha lanes. |
| **Cursor research agents (Marvin lane)** | `{T}/research/` via `cursor/*` PRs with a provenance manifest. Unchanged. | Existing automerge gate. | Existing. | Existing. |
| **CI** | `dashboard/data/`, `_system/data/` derived files, vault extracts. Unchanged. | Validators in each job. | None. | Dashboard. |
| **Nobody but a human in chat** | IB Gateway, live orders, `reviews/approved/`, `MEMORY.md`, `human_decision.json`, new Drive roots, licensed PDFs into SSI. | Rule 0 and Rule 9 in `CLAUDE.md`; `human-quality-filter.mdc`. | Human. | n/a |

Two things the map changes for the bots: they stop writing to the laptop-only mesh hub and write the same `[PROPOSED]` bullets to SSI `_system/memory/daily/`, which already has a triage consumer; and they get a durable, schema-checked home for ranked output (desk briefs) instead of chat.

### Desk brief contract (new, Phase 1)

`_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json`, one file per desk per day, validated by `_system/data/desk_briefs/schema.json`:

```json
{
  "schema_version": "desk_briefs.v1",
  "desk": "special_situations",
  "as_of": "2026-10-11",
  "author": "grok-michael-special-situations",
  "owner": "michael",
  "inputs_read": [{"path": "dashboard/data/special_situations.json", "generated_at": "..."}],
  "items": [
    {"ticker": "MDT", "headline": "MiniMed exchange offer: upper limit bound at 4.5939; final results pending",
     "one_number": "realized discount 2.3%", "lane": "split_offs",
     "evidence": [{"kind": "filing", "ref": "SC TO-I/A 0001628280-26-065406", "url": "https://..."}],
     "next": "Read the final-results 8-K; append a version-2 amendment.",
     "confidence": "filing", "handoff": null}
  ],
  "screens_empty": ["odd_lot_tender", "topping_bid_lost"],
  "research_only": true, "in_base_irr": false, "authority": "none"
}
```

Rules: at most 12 items (the prompts already cap at 12); every item names a ticker in `registry.json` or says `unresolved`; `confidence` in `filing | provider | news | web`; `one_number` is required (the Magis room convention); `inputs_read` records the `generated_at` of every dashboard file read, so a brief built on stale data says so. `build_desk_briefs.py` joins the latest file per desk into `dashboard/data/desk_briefs.json`; the Inbox grows a "Desk briefs" panel with owner and desk filters; a `desk-briefs` entry joins `data_feeds` with a 100 h window per desk that has filed at least once.

## Where each outside asset lands

### Michael's Short-Selling contract (Phase 2)

| Short-Selling repo concept | SSI landing |
|---|---|
| `type: idea` entry | A `candidates.json` row (`origin: desk_note`, `source` = bot id or author, `stage` from status) **plus** the narrative file. Narrative goes to the private vault at `research-vault/short-research/{TICKER}/{YYYY-MM-DD}-{slug}.md` while SSI is public (see Decision 1); SSI stores the pointer and the structured row. The Shorts tab renders the row and links the note. |
| `type: playbook` | `_system/frameworks/short_alpha_filing_furnace.md` § Playbooks, or `_system/reference/short-selling-library/playbooks/*.md` when it is process rather than framework. |
| `type: paper` | `_system/reference/short-selling-library/public/notes/{slug}.md` (summary in our words, citation, no copied text). The README's reading-to-workflow map links them. |
| Eight categories | Mapped to `frameworks.json` lenses: accounting → `accounting`, `revenue_recognition`, `earnings_vs_cash`, `working_capital`; shitco-concept → `promotion_insider_selling`, `fad_single_product`, `fraud_bad_actors` (conclusion tag only); supply-side → `supply_side`, `margin_contraction`, `cycle_mean_reversion`; share-supply → `dilution_financing` plus a new gate `share_supply` (lockups, ATMs, converts, index deletions; the separations and index lanes feed it); reverse-split → new lens `reverse_split_impairment` (Phase 3); activist-short → `origin: activist_index`; borrow-squeeze → `borrow_and_carry`, `crowding_squeeze`; playbook → not a lens. |
| Statuses `watching / active / closed / archived` | `stage` `lead / researching or live / closed / rejected`. |
| `source` (bot id), `dateAdded`, `lastUpdated`, `tags`, `summary`, `example` | Added to the candidate schema as `source`, `added_on`, `updated_on`, `tags`, `summary`; `example` entries are not migrated (they are fictional). `TEMPLATE.md` becomes `_system/templates/short_entry_template.md`. |
| CONTRIBUTING rules | Folded into SSI `CONTRIBUTING.md`: one idea per file, never rename a merged file, figures need source and date, no copyrighted text, move `updated_on` on every material edit, bots and humans use the same path. |
| Astro site, Cloudflare Access recipe | Not migrated. The SSI dashboard is already behind Access. |

### The reverse-split study (Phase 3)

| `rsdb` piece | SSI landing | Note |
|---|---|---|
| `src/rsdb/*` | `_system/scripts/reverse_splits/` package (the repo already has `_system/scripts/criticality/`). CLI exposed as `python -m _system.scripts.reverse_splits.cli`. | `fundamentals.py` stops loading SSI files by path and imports `build_fundamental_series` and `build_short_quant_screen` directly. |
| SQLite `data/reverse_splits.db` (260 MB), raw EDGAR and price caches (184 MB) | Local build artifacts, ignored. The committed truth is a compact ledger under `_system/data/reverse_splits/`: `events.jsonl` (about 1,000 rows), `filings.jsonl`, `borrow_snapshots.jsonl`, `finra_short_interest.jsonl` (when files are present), `backtest_runs.jsonl`. `export_ledger.py` and `import_ledger.py` round-trip SQLite and the ledger. | Prices are refetched; FINRA files stay ignored as now. Nothing over a few MB enters git. |
| `strategy_decisions.sqlite` (append-only, hash-chained) | `_system/data/reverse_splits/decisions.jsonl`, same hash chain, same immutability. Written by the dashboard form through a D1-backed endpoint later if Michael wants it hosted; git first. | Michael owns these decisions. |
| `docs/index.html`, `strategy.jsx`, `framework-plan.jsx`, `serve.py` | A "Reverse splits" sub-tab of the Shorts tab (`dashboard/reverse-splits-viz.js`) reading `dashboard/data/reverse_splits.json`. `serve.py`'s resimulation endpoints become `build_reverse_splits_dashboard.py` options; live resimulation is out of scope for the hosted site. | Same look as the Shorts tab. |
| `docs/data/short_alpha_review_queue.json` (119 candidates) | Imported into `candidates.json` as `origin: reverse_split_research`, stage `lead`, with the six lens reviews carried as `lens_reviews`. The 85 existing rows are not touched. | The export was built to be compatible with SSI candidate fields. |
| `docs/RESEARCH_METHOD.md`, `KNOWLEDGE_TRANSFER_PROMPT.md` | `_system/frameworks/reverse_split_short_process.md` (RSI-1.0 rules, gates, sizing, stress, honest limits). Governance: this proposal is the required proposal; the file is an operative process doc, not a persona lens. `KNOWLEDGE_TRANSFER_PROMPT.md` is retired; the README and this doc replace it. | Adds the `reverse_split_impairment` lens and the `share_supply` gate to `frameworks.json`. |
| `research_lens.py` (20 books with Drive ids) | Book rows join `_system/reference/short-selling-library/README.md` as catalogue pointers with Drive ids; text extracts, where authorized, go to the vault `investment-wisdom/{author}/`. | Same rule as `MICHAEL.md`: catalogue in SSI, text in the vault, PDF on Drive. |
| `ibkr_borrow.py` (ib_insync, client id 17) | Deleted. Borrow comes from the Client Portal availability CSV through the existing `refresh_short_alpha_borrow.py --input` and the `rsdb` CSV importer, merged into one importer. | Rule 9. The client id collision alone is reason enough. |
| Tests (69) | `_system/scripts/tests/reverse_splits/`, added to the `python-tests.yml` explicit list. | |
| The 795 uncommitted lines (EDGAR paging past the hit cap, 6-K and 14C forms, symbol parsing) | Committed and pushed to the `rsdb` repo first, so the migration starts from a clean, pushed state. | Phase 3, step 1. |
| Lane | `reverse-splits` job in `data-pipeline.yml` (weekly, Monday with the other discovery jobs): seed and enrich from EDGAR, refresh prices, export ledger, build dashboard, `check_reverse_splits.py --strict`. Lane entry, receipt, `data_feeds` entry. | The separations job is the template. |

### Desk mandates from the mesh hub (Phase 1)

The six desk definitions in the hub `CONTEXT.md` move verbatim into `_system/agents/DESKS.md` (one section per desk: owner, reads, screens, output, never). The Grok prompts gain two lines each: the write path (desk brief file and `_system/memory/daily/`) and the reads they currently skip (`special_situations.json`, `separations.json`, `cvr_universe.json`, `nol_382_facts.json` for the special-situations desk). The mesh hub keeps cross-repo context and the bridges; its `daily/` stops being the desks' output.

## Access and governance (Phase 0)

1. **Michael:** `maintain` on SSI and `write` on `research-vault`. He reviews code PRs with Drew; he approves nothing in the three human-gated files.
2. **Bots:** one fine-grained GitHub token per bot identity (`grok-drew-*`, `grok-michael-*`), scoped to SSI (and the vault for short notes) with `contents: write` and `pull_requests: write`, stored in the Cursor Cloud Agents secrets the way `GOOGLE_APPLICATION_CREDENTIALS_JSON` already is. No bot token holds admin or secrets scopes.
3. **Ruleset on `main`:** require a pull request and the `python-tests` check for every actor except the `github-actions` app (the `commit-main` action keeps pushing). Bots cannot push to `main` directly even with a token.
4. **Automerge classifier:** `classify_agent_pr_lane.py` gains a `grok/` lane whose allowlist is the data paths in the write map; `check_contributor_paths.py` runs in `marvin-pr-automerge.yml` and fails the PR when a `grok/` branch touches anything else. Code from a bot always waits for a human.
5. **`CONTRIBUTING.md`** (new, root) and **`docs/WRITE_MAP.md`** (the table above, kept in sync by a test that reads `classify_agent_pr_lane.py`'s allowlist).
6. **Archive** `Special-Situations` and `Short-Selling` on GitHub with a README pointer each; archive `reverse-split-short-research` at the end of Phase 3.
7. **README:** remove the three workflows that do not exist (`darwin-refresh.yml`, `vicki-ir-harvest.yml`, `ci-autofix.yml`); add the write map link.

## Phases

| Phase | Scope | Exit check |
|---|---|---|
| **0. Access and guardrails** (1 day) | Items 1 to 7 above. `_system/agents/DESKS.md`. Prompts point at SSI daily notes. | Michael can open and merge a data PR; a `grok/` PR touching `_system/scripts/` is blocked; the two empty-or-placeholder repos are archived with pointers. |
| **1. Desk briefs** (2 days) | Schema, `check_desk_briefs.py`, `build_desk_briefs.py`, Inbox panel, `data_feeds` entry, lane note (briefs arrive by PR, so the lane is the nightly intake that rebuilds the panel), prompt updates, first briefs from both owners' bots. | A brief from each of the six desks renders on the Inbox with owner and `inputs_read` ages; a brief with 13 items or an unknown ticker fails the check. |
| **2. Short research consolidation** (3 days) | Candidate schema fields, `desk_note` origin, lens mapping, `share_supply` gate, entry template, paper notes, vault `short-research/` collection and SSI index, Shorts tab entries list, `short_alpha.json` and `special_situations.json` in `data_feeds`, borrow CSV importer, tests into CI. Archive `Short-Selling`. | A real idea entry travels bot → PR → `candidates.json` + vault note → Shorts tab, with the ledger validator green; the Fugazi and activist leads are untouched. |
| **3. Reverse splits lane** (5 days) | Commit and push the uncommitted `rsdb` work; package move; ledger export/import; delete the Gateway path; CSV borrow merge; `reverse_split_impairment` lens; process doc; dashboard sub-tab; weekly job, lane, receipt, feed; tests in CI; import the 119-candidate queue; archive the repo. | `python -m _system.scripts.reverse_splits.cli pipeline --skip-edgar` rebuilds the ledger from a clean clone plus the ignored caches; the dashboard shows the book; P3 and P6 green; `check_ib_gateway_registry.py --scan-ssi` finds no `ib_insync` connect. |
| **4. Hygiene the survey turned up** (2 days) | Add the orphan tests (`test_special_situations.py`, `test_separation_*`, `test_split_off_terms.py`, `test_separations_ui.py`, `test_cvr_discovery.py`) to the explicit list; decide the dead queues (`cvr_agent_queue.json` 209 waiting, `short_alpha_research_queue.json`, `vicki_dispatch_queue.json`): wire a consumer or delete; commit the refreshed float/short-interest file from the technicals job; set `CVR_ALPHARANK_DROP_PATH` or remove the step; Greenblatt text extract into the vault under `investment-wisdom/greenblatt/` with a catalogue pointer in SSI. | Every test file in the repo is invoked by a workflow or deleted; every queue has a consumer or is gone. |
| **5. Privacy decisions** (Drew's call, see below) | Depends on Decision 1. | Recorded in this file's implementation record. |

## Decisions for Drew and Michael

1. **Public SSI, or private SSI.** Today the public repo carries short share counts and Michael's full book. Three options: (a) keep SSI public and keep anything that names a real company as a short target, plus live quantities, out of it: short narratives in the vault (this plan assumes (a)), `ideas.json` and `sleeves_*.json` quantities moved to D1 with the committed files reduced to tickers and dates; (b) make SSI private and run the heavy lanes on a self-hosted runner in a private repo (safe only because fork PRs no longer run); (c) leave as is. Recommendation: (a) now, revisit (b) when the Actions bill or the runner question is settled.
2. **Who owns reverse-split strategy decisions.** The process doc says the record is Michael's; the plan makes him owner of `decisions.jsonl` and the sleeve. Confirm.
3. **Bot identities.** One token per bot per owner (recommended, so a brief's `author` is attributable), or one shared bot. 
4. **Chat.** The desks' one-line "Magis room" posts stay wherever they are; the brief is the durable record. If the room should be fed from the repo instead, that is a later webhook from `build_desk_briefs.py`, not a design input now.

## Risks of simplification

- Moving desk output from the laptop hub into a public repo exposes bot reasoning about real companies. Decision 1 governs; until it is taken, briefs name tickers and filings only, no fraud language (the `fraud_bad_actors` tag stays a human conclusion).
- Auto-merging bot data PRs is only safe because validators run on every PR and the path guard exists. If either is weakened "to let one brief through", the lane is no longer safe. Do not weaken the schema to make one note pass (Michael's rule, kept).
- Folding `rsdb` into SSI puts a 5-year event database under the ThetaData and Gateway rules. It needs neither; the rules apply anyway.

## Redundancy kept on purpose

Human gates on beliefs, capital and approvals; the provenance manifest on research PRs; strict checks in discovery jobs and warn-only checks in the rebuild chain; the vault split; one receipt per lane.

## Success criteria

- One `CONTRIBUTING.md` and one write map; a new bot can be onboarded by reading two files.
- Zero Magis research in repos other than SSI and the vault; the three side repos archived.
- Every bot output path has a schema, a validator, a test, a feed entry and a consumer on the dashboard.
- Both owners' bots have filed briefs that render with owner attribution and input ages.
- The reverse-split ledger rebuilds from a clean clone; no `ib_insync` import remains anywhere in SSI.
- No test file in the repo is orphaned from CI.

## Implementation scope

- [ ] Access, rulesets, archives (GitHub settings; Drew)
- [ ] Docs: `CONTRIBUTING.md`, `docs/WRITE_MAP.md`, `_system/agents/DESKS.md`, prompt lines, process doc, README fixes
- [ ] Scripts: `check_desk_briefs.py`, `build_desk_briefs.py`, `check_contributor_paths.py`, `reverse_splits/` package, ledger export/import, borrow CSV merge
- [ ] Data: `_system/data/desk_briefs/`, `_system/data/reverse_splits/`, schema fields on `candidates.json`
- [ ] Dashboard: Inbox desk-briefs panel, Shorts entries list, Reverse splits sub-tab
- [ ] CI: `reverse-splits` job, lanes, `data_feeds`, explicit test list, automerge lane and path guard

## Implementation record (2026-10-12)

| Phase | Landed | Notes |
|---|---|---|
| 0. Access and guardrails | `mcricenti` promoted to `maintain`; `Special-Situations` and `Short-Selling` archived with pointer READMEs; `CONTRIBUTING.md`, `docs/WRITE_MAP.md`, `_system/agents/DESKS.md`; `grok/` lane in `classify_agent_pr_lane.py`; `check_contributor_paths.py` and the automerge `data-guard` job; `main-push-guard.yml`; README stale rows removed. | A "require pull request" rule could not be enabled: on this GitHub plan the Actions app cannot be a bypass actor (repo ruleset 422, org ruleset needs Team, classic protection silently dropped the app allowance), and without the bypass every lane's commit would be rejected. Protection stays force-push and deletion only; the push guard detects instead. |
| 1. Desk briefs | `_system/data/desk_briefs/` (schema, README, first real special-situations brief), `check_desk_briefs.py`, `build_desk_briefs.py`, `dashboard/desk-briefs-viz.js`, Inbox panel, `desk_briefs` feed in P6, intake rebuild steps; the local memory hub (CONTEXT, GRAPH, MEMORY, bridges, 24 daily files) copied into `_system/memory-hub/research-equity/`; Grok prompts gained their write path and the reads they skipped, plus a Short Selling desk. | Lessons go to the in-repo hub daily, which SOURCES.md already names, rather than `_system/memory/daily/`. |
| 2. Short research | Candidate contract fields and the `desk_note` / `reverse_split_research` origins; `share_supply` gate and `reverse_split_impairment` lens; entry template; Michael's playbook and the Dechow et al. paper note; Client Portal borrow CSV importer; Shorts tab entry fields and lens strip; 114 reverse-split leads imported (5 already present); `short_alpha` and `special_situations` feeds in P6; `research-vault/short-research/README.md` created. | The nine fictional entries were not migrated. A latent Shorts-tab crash on names outside the quant screen was fixed on the way. |
| 3. Reverse splits | `_system/scripts/reverse_splits/` (35 modules, Gateway path deleted), JSONL ledger under `_system/data/reverse_splits/` (632 events, 22,879 announcements, FINRA, book runs, 2 hash-chained decisions), `build_reverse_splits_dashboard.py`, `check_reverse_splits.py`, `dashboard/reverse-splits-viz.js` mounted under the Shorts tab, `reverse_split_short_process.md`, 124 tests, Monday `reverse-splits` lane and `reverse_splits` feed. | The source repo was still being written to during the move (a rerun regenerated its reports); its new commits are pushed and its README points here. It is not archived yet because the local full pipeline (prices, book, rerun) still runs there. |
| 4. Hygiene | Orphan test suites added to `python-tests.yml` with the files they read; `index_float_adv.json` committed by the technicals job. | Dead queues (`cvr_agent_queue.json`, `short_alpha_research_queue.json`, `vicki_dispatch_queue.json`) and the Greenblatt text extract were left as they are; each is a one-line decision for Drew. |
| 5. Privacy | Not changed. | Decision 1 stands open; nothing was made private and no quantities moved to D1. |

Verification at merge time: 1,076 tests across `_system/trading`, `_system/scripts/tests` and the explicit list, plus 124 reverse-split tests; graph invariants P3 (31 lanes) and P6 (13 feeds) green; `validate_sources.py` valid.

## Decisions taken (2026-10-12)

Drew asked for the open decisions to be taken rather than parked.

1. **Visibility.** SSI stays public (Actions minutes). Short-idea narratives go to the private vault (`research-vault/short-research/`); SSI holds the structured row and the pointer. The short position ledger stays where it is: its history is already public, and a history scrub is a separate, deliberate step.
2. **Reverse-split strategy decisions** belong to Michael (`_system/data/reverse_splits/decisions.jsonl`).
3. **Bot identities.** One fine-grained token per bot per owner, named after the bot; each owner creates their own.
4. **Magis room.** Michael's bots join. Same posting rules as Drew's desks; the desk brief is the record.
5. **Drive sharing.** Drew is sharing the folders with Michael's accounts himself.
6. **Side repos.** All three archived: `Special-Situations`, `Short-Selling`, and `reverse-split-short-research` (its last rerun outputs were pushed first and its README points at the hub package).
7. **Dead queues.** `short_alpha_research_queue.json` and `vicki_dispatch_queue.json` retired (no consumer, no workflow). `cvr_agent_queue.json` kept: `cvr_common.py` maintains it and the Special Situations desk now reads it.
8. **Greenblatt.** Text extracted from the Magis library copy on Drive into the private vault under `investment-wisdom/greenblatt/`; SSI carries only the catalogue pointer.
