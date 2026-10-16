# Unified Data Architecture Plan: Multi-Agent Coordination Across SSI, Google Drive, and Research Vault

**Date:** 2026-10-16  
**Status:** implemented (Phases 1–4 scripts, L0/L1 shards, cross-store catalog, SQLite FTS5 index, and dated-file compaction deployed)  
**Scope:** `magis-capital-partners/single-stock-investments` (SSI), Google Drive (`Single Stock Research PDF Store`, Shared Drive `0AFpaOm4iTLqjUk9PVA`), `magis-capital-partners/research-vault`, and Cloudflare D1  
**Agents covered:** Grok Bot (7 research desks + VIC intake), Cursor (Marvin, Milly, Committee, Vicki, CI Autofix), and Claude (Claude Code / Opus deep synthesis, quant lanes, memory curation)  
**Template:** `_system/prompts/architecture_review_template.md`

---

## 1. Executive Summary & Empirical Baseline

An empirical audit of `single-stock-investments` (SSI), Google Drive, and `research-vault` on 2026-10-16 shows that the analytical machinery (31 monitored CI lanes, 846+ contract-routed securities, deterministic valuation compilers, and multi-agent PR guardrails) is being throttled by **storage conflation**. Today, raw binary PDFs, 33.7 GB of unparsed SEC EDGAR HTML, 152,467 daily-dated duplicate markdown files, and 457 MB of monolithic dashboard JSONs all live inside a single Git repository.

### Verified Footprint (2026-10-16 Audit)

| Metric | Current Measured State | Root Cause | Target State | Improvement |
|---|---:|---|---:|---:|
| **Git-tracked files in SSI** | **303,687 files** | Daily dated file creation (`*_YYYY-MM-DD.md`) + raw EDGAR HTML | **~28,500 files** | **-90.6%** |
| **SSI working tree size** | **51.71 GB** | `33.67 GB` `.htm` + `14.12 GB` `.pdf` + `2.28 GB` `.json` | **~1.45 GB** | **-97.2%** |
| **SSI `.git` packfile size** | **15.22 GB** | Binary PDFs, `.bin` scraper caches, and daily churn in history | **< 0.60 GB** | **-96.1%** |
| **Dated snapshot files in `{TICKER}/`** | **152,467 files** | `thematic_context_*` (62,959), `insider_signal_*` (51,981), `source_inventory_*` (37,527) | **2,538 files** (3 canonical files/ticker) | **-98.3%** |
| **Semantic duplication in dated files** | **70.4% to 85.8%** | Files rewritten daily when only the header date string changes | **0%** (content-hash gated writes) | **Eliminated** |
| **Binary PDFs committed in SSI Git** | **9,672 PDFs (14.12 GB)** | Local copies kept after 100% upload (`8,815` in `document_registry.json`) to Drive | **0 PDFs in Git** (`sha256` pointer only) | **-14.12 GB** |
| **Activist report storage in SSI Git** | **58,974 files (4.62 GB)** | Duplicated in `_system/reference/activist-reports` (2.20 GB) and `{TICKER}/` (2.42 GB) | **1 canonical index + Vault text** | **-4.50 GB** |
| **Public repo leakage of vault corpora** | **1,089 files (387.6 MB)** | `investment-wisdom` (214.4 MB), `vic` (147.1 MB), `dropbox_ingestion` (26.1 MB) still in SSI | **0 files in public SSI** | **100% private** |
| **Memory daily logs** | **2 split trees (116 files)** | `_system/memory/daily/` (90) vs `_system/memory-hub/research-equity/daily/` (26) | **1 unified ledger + triage loop** | **Unified** |
| **Dashboard JSON freshness keys** | **5 incompatible schemas** | `generated_at`, `build_time`, `generated`, `as_of`, or missing (`shorts_net_edge_v3.json`) | **1 standard `_envelope` header** | **100% uniform** |

---

## 2. Deep Research: Optimal Interaction Between Grok Bot, Cursor, Claude, and Data Stores

Modern multi-agent research architectures (synthesizing 2026 findings from *Codified Context* `arXiv:2602.20478`, *Progressive Disclosure for Coding Agents*, *Agent Memory Vault*, and *Palinode*) converge on four engineering laws for coordinating heterogeneous agents (**Grok Bot**, **Cursor**, and **Claude**) over shared data.

### 2.1 Cognitive Specialization & I/O Constraints by Agent Family

Each agent family has a distinct execution environment, token economics profile, and failure mode. Data must be structured around **how each agent reads and writes**:

| Agent Family | Primary Role in Magis | Execution & Context Profile | Current Data Bottleneck | Optimal Data Contract |
|---|---|---|---|---|
| **Grok Bot** (7 Desks + VIC Intake) | Wide-funnel daily/weekly scanning (Special Situations, Activism, Fundamentals, NOL, Tape, Stahl, Shorts), X/web synthesis, Drive drop triage | Stateless between sessions; reads via GitHub/Drive APIs; bounded context window; cannot run local compilers or clone 67 GB repos | Forced to inspect `dashboard/data/*.json` monoliths (`4 MB` to `18.6 MB` each) with 5 different timestamp field names; writes lessons to `_system/memory-hub/` which has no triage consumer | **Read:** `L0` compact manifests (`< 100 KB`) with uniform `_envelope` + `L1` per-ticker shards (`dashboard/data/tickers/{T}.json`). **Write:** Schema-validated PR drops (`_system/data/desk_briefs/<desk>/<date>.json`, `candidates.json` seeds, unified `_system/memory/daily/`). |
| **Cursor** (Marvin, Milly, Committee, Vicki, CI Autofix) | Deep-dive compilation, 9-persona committee voting, adversarial fact checking, browser IR harvesting, deterministic Python pipelines | Full Linux VM with Python/bash; governed by `llm_call_gate.py`; spawns parallel subagents | 67 GB checkout requires `jlumbroso/free-disk-space` + 11 sparse profiles; daily compiler churn invalidates frozen committee packets (AAOI superseded 21 times); rebase collisions in `ci_push_main.sh` | **Read:** Content-addressed frozen evidence packets (`sha256` locked) + canonical undated `filing_digest.md` / `insider_signal.md`. **Write:** `{TICKER}/research/` contracts, append-only `.jsonl` ledgers, deterministic shard builders. |
| **Claude** (Claude Code / Opus) | Cross-document synthesis (10-K + letters + accounting forensics), quantitative backtests (`reverse_splits`), architecture & memory curation | High reasoning depth; highest per-token cost if context is polluted by raw HTML or boilerplate rules | Context window flooded by unchunked SEC `.htm` files, duplicate third-party inventories, and 1,014 unpromoted memory items in a flat queue | **Read:** 3-Tier Progressive Disclosure (`Tier 0` thin index -> `Tier 1` digest/trigger map -> `Tier 2` verbatim section extract from `research-vault` by `sha256`). **Write:** Promoted belief diffs, methodology specs, and complex multi-file code refactors. |

### 2.2 Four Architectural Laws for Agentic Data Storage

1. **Law 1: Three-Tier Progressive Disclosure (`L0 Manifest -> L1 Digest -> L2 Verbatim Chunk`)**
   Agents should resolve 80% of screening and routing decisions at **Tier 0/1** (`< 2,000 tokens`) and escalate to **Tier 2** full-text reads only for specific tickers under active underwriting. Replacing upfront monolithic file reads with tiered manifests cuts average session token consumption by **40% to 75%** while improving reasoning accuracy (eliminating middle-context dilution).
2. **Law 2: Content-Addressable Identity (`sha256` as Universal Primary Key)**
   Never use a mutable folder path (`Letters/2026 Q1/...` vs `superinvestor-letters/2026Q1/...`) as the primary key linking stores. Every source document receives `doc_id = "sha256:<64-hex>"` at intake. That single `doc_id` maps to:
   - `drive_file_id` (the binary PDF in Google Drive, stamped with `appProperties.sha256`),
   - `vault_extract_path` (the clean `.md`/`.txt` text extract in `research-vault`), and
   - `ssi_evidence_refs` (structured citations and locked facts in SSI).
   Renaming or reorganizing Google Drive folders never breaks a single link.
3. **Law 3: Strict Four-Store Separation ("One Home Per Byte")**
   Each byte of data belongs in **exactly one** canonical store based on its mutability, format, and privacy class:
   - **Store 1: Google Drive (`Single Stock Research PDF Store`)** = *Human-browsable binary store* (all raw `.pdf` files, slide decks, audio/video). Zero binary PDFs in Git.
   - **Store 4: `research-vault` (Private GitHub)** = *Licensed & sensitive text corpus* (clean `.md`/`.txt` extracts of letters, books, VIC, SumZero, transcripts, private short narratives, and material SEC/IR text extracts).
   - **Store 3: `single-stock-investments` (Public GitHub)** = *Deterministic compiler, schemas, compact ledgers (`.jsonl`), per-ticker research contracts (`valuation.json`, `deep_dive_*.md`), and sharded dashboard payloads*. Zero raw `.htm` filings, zero binary PDFs, zero licensed text.
   - **Store 4: Cloudflare D1 (+ Local SQLite FTS5 Rebuildable Cache)** = *Mutable human state & fast query/search index* (sleeve notes, human decisions, operational task queues, and indexed search over manifests).
4. **Law 4: Content-Hash Gated Writes (Kill Calendar-Dated No-Op Files)**
   Git is already a chronological version control system. Writing `insider_signal_2026-07-19.md`, `insider_signal_2026-07-20.md`, ... when the content has not changed creates O(N x Days) file explosion (`152,467` files). Every recurring extractor must write to a **single canonical filename** (`insider_signal.md`, `thematic_context.md`, `source_inventory.json`) and skip updating `as_of` / committing when `payload_sha256` (excluding timestamp) matches the existing file. Historical series belong in a single append-only `.jsonl` file (`insider_history.jsonl`), never thousands of dated markdown files.

---

## 3. Target Architecture: The Four-Store Contract

```text
+---------------------------------------------------------------------------------------------------+
|                                   AGENTIC CONSUMERS & WRITERS                                     |
|  Grok Bots (7 Desks + VIC Drop)    |    Cursor Agents (Marvin/Milly/IC/Vicki)    |    Claude      |
+-----------------+------------------+----------------------+----------------------+--------+-------+
                  |                                         |                               |
                  v (Tier 0/1 JSON & PR Drops)              v (Contracts, JSONL, Shards)    v (Deep Synthesis)
+---------------------------------------------------------------------------------------------------+
|                        UNIFIED CATALOG & ENVELOPE LAYER (_system/sources.json)                    |
|              Primary Key: doc_id = "sha256:<hex>"  |  Entity Key: ticker / cik / figi             |
+-----------------+--------------------------+--------------------------+---------------------------+
                  |                          |                          |
                  v                          v                          v
+------------------------+  +------------------------------+  +------------------------+  +---------+
| STORE 1: GOOGLE DRIVE  |  | STORE 2: RESEARCH-VAULT      |  | STORE 3: SSI REPO      |  | STORE 4 |
| Shared Drive (Binary)  |  | Private GitHub (Text Corpus) |  | Public GitHub (Engine) |  | CF D1   |
+------------------------+  +------------------------------+  +------------------------+  +---------+
| - Raw PDFs ONLY        |  | - Clean .md/.txt extracts    |  | - Code, schemas, CI    |  | Mutable |
| - Stamped on upload:   |  | - superinvestor-letters/     |  | - registry.json        |  | human   |
|   appProperties.sha256 |  | - investment-wisdom/         |  | - .jsonl event ledgers |  | state,  |
| - Single Stocks/{T}/   |  | - vic-research/{T}/          |  | - {T}/research/        |  | sleeve  |
| - Letters/{YYYY-Qn}/   |  | - sumzero-research/{T}/      |  |   (valuation.json,     |  | notes,  |
| - Research Sources/    |  | - short-research/{T}/        |  |    deep_dive.md,       |  | queues, |
| - Admin/Intake/        |  | - podcasts/ & transcripts/   |  |    canonical digests)  |  | & FTS5  |
|                        |  | - filings-extracts/{T}/      |  | - dashboard/data/      |  | query   |
| Cost: $0 (existing)    |  | Cost: $0 (private text Git)  |  | Cost: $0 (public CI)   |  | index   |
+------------------------+  +------------------------------+  +------------------------+  +---------+
```

### 3.1 Store 1: Google Drive (`Single Stock Research PDF Store` — `0AFpaOm4iTLqjUk9PVA`)

**Role:** The sole home for raw binary `.pdf` files. Humans browse and read PDFs here; agents never read binary PDFs directly during research runs (agents read the pre-extracted Markdown/text in `research-vault` or `{TICKER}/research/evidence/filing_digest.md`, and link the Drive URL for human click-through).

**Structural Improvements:**
1. **Hash-First Registration (`appProperties.sha256`):** Every file uploaded or imported via `sync_pdf_store_google_drive.py` or `import_drive_intake.py` must have `appProperties: {"sha256": "<digest>", "source_type": "<kind>", "ticker": "<TICKER>"}` written to its Google Drive file metadata. This eliminates the 19,700 unhashed Drive files reported in the June audit and allows instant O(1) Drive API lookup by SHA-256 regardless of folder moves.
2. **One Canonical Taxonomy (Eliminate Folder Collisions):**
   Standardize folder naming across Drive and Vault so automated scripts never guess between spaces and hyphens:
   - `Admin/Intake/{VIC,Research,Company,Activist-Long,Activist-Short}/` — human & Grok dropzone. Once `import_drive_intake.py` hashes, extracts text to `research-vault`, and registers the PDF, it **moves** the Drive file by `fileId` into its permanent folder (never leaving a duplicate copy in `Admin/Intake/`).
   - `Single Stocks/{TICKER}/{Filings,Company,VIC,SumZero,Activist,Research}/` — all ticker-scoped PDFs.
   - `Letters/{YYYY}Q{n}/` — unify naming with `research-vault/superinvestor-letters/{YYYY}Q{n}/` (provide aliases for legacy `YYYY Qn` folders via folder ID map in `google_drive_config.json`).
   - `Research Sources/{Investment Wisdom,Books,Macro & Academic,SumZero Unmatched}/` — merge the duplicate `Research Sources/Books/Accounting` and `Research Sources/Investment Wisdom/Accounting` into a single canonical folder ID in `_system/sources.json`.
3. **Stop Copying Drive PDFs Back Into SSI Git:**
   When `import_drive_intake.py` imports a PDF from `Admin/Intake/`, it must:
   - Compute `sha256`,
   - Extract clean `.md`/`.txt` into `research-vault` (for VIC, SumZero, Books, Letters, Activist) or `{TICKER}/research/evidence/filing_digest.md` (for Company docs),
   - Append/upsert the metadata row (`doc_id`, `drive_file_id`, `drive_web_view_link`, `vault_extract_path`, `ticker`, `source_type`) into `_system/data/catalog/documents.jsonl`, and
   - **Never commit the binary `.pdf` into `single-stock-investments`.**

### 3.2 Store 2: Research Vault (`magis-capital-partners/research-vault` — Private GitHub)

**Role:** The private, Git-versioned text corpus for all copyrighted, licensed, or proprietary research narratives. Because it stores **compressed/clean `.md`, `.txt`, and `.json` metadata only** (no raw multi-MB PDFs or audio binaries), `research-vault` stays fast (`< 1.5 GB`), clones in seconds in CI via `.github/actions/checkout-vault`, and costs **$0/month**.

**Structural Improvements:**
1. **Complete the Incomplete Vault Cutover (`-387.6 MB` from Public SSI):**
   Execute the pending removal of:
   - `_system/reference/investment-wisdom/` (`467 files, 214.40 MB`) -> already mapped in `vault_paths.py` to `research-vault/investment-wisdom/`.
   - `_system/dropbox_ingestion/` (`55 files, 26.11 MB`) -> `research-vault/dropbox-ingestion/`.
   - `{TICKER}/third-party-analyses/vic/*.{pdf,md,txt}` (`567 files, 147.10 MB`) -> `research-vault/vic-research/{TICKER}/` (keep only non-sensitive metadata citations in `{TICKER}/third-party-analyses/source_inventory.json`).
   - `_system/reference/activist-reports/` (`1,632 files, 2.20 GB`) and `{TICKER}/third-party-analyses/activist_reports/` (`57,342 files, 2.42 GB`) -> move binary PDFs to Google Drive `Single Stocks/{TICKER}/Activist/`, move extracted text to `research-vault/activist-research/{TICKER}/`, and keep only the compact metadata index (`_system/reference/activist-reports/activist_index.jsonl`) in SSI.
2. **Standardize Vault Directory Layout & Chunking for Agents:**
   Every document in `research-vault` follows a predictable two-file pattern so Claude and Cursor agents can read summaries first and sections second:
   ```text
   research-vault/
     catalog_manifest.jsonl                  # Compact index of every vault text extract (sha256, ticker, tokens, path)
     superinvestor-letters/{YYYY}Q{n}/{fund_slug}.txt
     investment-wisdom/{author}/{work_slug}.txt
     manager-meetings/{YYYY-MM-DD}-{slug}.md
     vic-research/{TICKER}/{YYYY-MM-DD}-{slug}.md
     sumzero-research/{TICKER}/{YYYY-MM-DD}-{slug}.md
     short-research/{TICKER}/{YYYY-MM-DD}-{slug}.md
     activist-research/{TICKER}/{YYYY-MM-DD}-{campaign_slug}.md
     podcasts/episodes/{episode_id}.txt
   ```
3. **Eliminate Multi-Writer Git Lock Contention on `research-vault`:**
   `vault_git.py` solved local process collisions on a single machine, but remote push races between NY4 Whisper daemons and GitHub Actions (`letter-backfill`, `drive-intake`) still occur when jobs commit every 15 minutes.
   - **Rule:** Local Whisper/LLM daemons write extracted `.txt`/`.json` to a local staging spool and flush to `research-vault` `main` in **batched commits (at most once per hour)** using `ci_push_vault.sh` / `vault_git.py` with `git pull --rebase -X theirs` on append-only catalogs.

### 3.3 Store 3: SSI Operational Repository (`magis-capital-partners/single-stock-investments` — Public GitHub)

**Role:** The deterministic valuation engine, agent orchestration control plane, append-only fact ledgers, and dashboard build pipeline.

**Structural Improvements:**
1. **Evict Raw SEC EDGAR `.htm`/`.xml` Files from Git (`-31.74 GB`, `-26,620 files`):**
   - Currently `{TICKER}/investor-documents/sec-edgar/` commits raw 10-K/10-Q `.htm` files (up to 40 MB each) directly into Git.
   - **New Contract:**
     - Commit `{TICKER}/investor-documents/DOWNLOAD_MANIFEST.json` (accession number, form, filing date, primary document URL, `sha256`),
     - Commit `{TICKER}/research/evidence/sec_companyfacts.json` (compact structured XBRL numbers) and `{TICKER}/research/evidence/filing_digest.md` + `filing_facts.json` (the extracted narrative sections and tables Marvin/Milly actually read),
     - Add `*/investor-documents/sec-edgar/*.htm`, `*.html`, `*.xml`, `*.jpg`, `*.gif`, and `**/*.pdf` to `.gitignore` (while keeping local disk caching in `/tmp/sec-edgar-cache/` or NY4 local disk for rebuilds).
2. **Collapse 152,467 Dated Snapshot Files into Canonical-Latest + Compact JSONL (`-150,000 files`):**
   - Replace `{TICKER}/research/evidence/insider_signal_YYYY-MM-DD.md` (51,981 files) with `{TICKER}/research/evidence/insider_signal.md`.
   - Replace `{TICKER}/research/evidence/thematic_context_YYYY-MM-DD.md` (62,959 files) with `{TICKER}/research/evidence/thematic_context.md`.
   - Replace `{TICKER}/third-party-analyses/source_inventory_YYYY-MM-DD.{json,md}` (37,527 files) with `{TICKER}/third-party-analyses/source_inventory.json`.
   - Replace dated `filing_digest_YYYY-MM-DD.md` / `filing_facts_YYYY-MM-DD.json` with canonical `filing_digest.md` and `filing_facts.json` (plus `ssi_evidence_pack.json` pinned by `evidence_sha256` inside `committee_work/` when a committee is frozen).
   - **Content-Hash Gate (`write_if_changed()`):** Every evidence builder computes `semantic_sha256 = sha256(canonical_json_without_timestamps)`. If `semantic_sha256 == existing.semantic_sha256`, the script **does not touch the file on disk**. Zero no-op Git commits.
3. **Clean Ticker Directory Contract (Max ~15 Tracked Files per Ticker Instead of ~270):**
   ```text
   {TICKER}/
     README.md                                      # Human & agent entry card
     investor-documents/
       DOWNLOAD_MANIFEST.json                       # SEC accessions, IR URLs, Drive file IDs, sha256
       TRANSCRIPT_MANIFEST.json                     # Transcript pointers into research-vault
     third-party-analyses/
       source_inventory.json                        # Single undated inventory (Drive + Vault pointers)
       references.md                                # Approved Substack / context links
     research/
       valuation_route.json                         # Power Zone route
       valuation_contract.json                      # Contract v3 proof & locked facts
       valuation.json                               # Scenario inputs & overlays
       deep_dive.md                                 # Canonical latest deep dive (git history holds prior versions)
       adversarial.md                               # Canonical latest Milly review
       evidence/
         document_inventory.json                    # Content-addressed source map
         filing_facts.json                          # Structured financial facts
         filing_digest.md                           # Extracted MD&A, segments, footnotes
         insider_signal.md                          # Canonical insider conviction digest
         thematic_context.md                        # Canonical thematic & peer digest
   ```
4. **Unify the Dual Memory Systems (`_system/memory/` + `_system/memory-hub/`):**
   - Today, Cursor/Marvin writes to `_system/memory/daily/YYYY-MM-DD.md` (triaged by `build_memory_triage.py`), while Grok desk bots write to `_system/memory-hub/research-equity/daily/YYYY-MM-DD.md` (not read by `build_memory_triage.py`).
   - **Fix:** Make `_system/memory/` the **single equity memory store in SSI**:
     - Keep `GRAPH.md`, `CONTEXT.md`, and `bridges.md` inside `_system/memory/` (migrating them from `_system/memory-hub/research-equity/` and leaving a thin symlink/pointer for backward compatibility during transition).
     - Both Grok desk bots and Cursor/Marvin agents append `[PROPOSED <LENS>]` bullets to `_system/memory/daily/YYYY-MM-DD.md` using the structured 5-field contract (`Evidence`, `Seen`, `Harmful`, `Scope`, `Review after`).
     - `build_memory_triage.py` ingests both Marvin and Grok proposals into `_system/reviews/pending/memory_triage.md`, and a weekly **Claude memory-curation job** groups duplicates and stages a human-approval PR for Drew.

### 3.4 Store 4: Cloudflare D1 & Disposable Local SQLite Cache

**Role:** Fast operational state, human mutable inputs (sleeve notes, committee decisions, triage verdicts), and sub-50ms multi-agent query endpoints.

**Structural Improvements:**
1. **Fix `build_document_registry.py` Cross-Store Blindness:**
   Update `build_document_registry.py` so it reads `_system/data/catalog/documents.jsonl` (which merges SSI manifests, `research-vault/catalog_manifest.jsonl`, and Google Drive's `appProperties.sha256` index) rather than only running `ROOT.rglob("*.pdf")` with `_external` skipped. This immediately restores all `superinvestor-letters`, `vic-research`, and `sumzero-research` PDFs to `dashboard/data/document_registry.json` without requiring those PDFs to sit on local disk in SSI.
2. **Disposable Local SQLite + FTS5 Index (`_system/cache/magis_index.sqlite`, gitignored):**
   Following the 2026 *Agent Memory Vault* / *Palinode* pattern, provide a lightweight single-script builder (`python _system/scripts/build_agent_index.py`) that compiles all JSONL ledgers, `registry.json`, `documents.jsonl`, and `MEMORY.md` into a local SQLite FTS5 database in `< 3 seconds`. Cursor and Claude agents can query exact facts, filing locators, and memory beliefs via SQL/BM25 in milliseconds instead of grepping 300,000 files.

---

## 4. Standardized Data Envelope & Progressive Disclosure for `dashboard/data/`

Today, `dashboard/data/` holds **6,406 files (457.38 MB)**, and top-level files use five incompatible timestamp conventions (`generated_at`, `build_time`, `generated`, `as_of`, or none). Grok Bots and Cursor agents waste context tokens loading 10–18 MB JSON files just to check freshness or filter for 5 tickers.

### 4.1 Mandatory `_envelope` Header on Every JSON Artifact

Every generated JSON file in `dashboard/data/` and `_system/data/` must carry a standardized top-level `_envelope` block (while keeping top-level `generated_at` as an alias for backward compatibility):

```json
{
  "_envelope": {
    "schema_version": "magis.feed.v2",
    "feed_id": "reverse_splits",
    "generated_at": "2026-10-16T14:00:00Z",
    "as_of": "2026-10-16",
    "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "row_count": 632,
    "upstream_inputs": [
      {"path": "_system/data/reverse_splits/events.jsonl", "sha256": "..."}
    ],
    "health": {
      "status": "healthy",
      "structural_errors": 0,
      "stale_sources": []
    }
  },
  "generated_at": "2026-10-16T14:00:00Z"
}
```

### 4.2 Splitting the 10–18 MB Monoliths into `L0 Summary (< 100 KB)` + `L1 Shards`

| Current Monolith | Current Size | Problem for Agents & UI | New Tiered Structure |
|---|---:|---|---|
| `dashboard/data/insights/tickers.json` | **18.59 MB** | Too large for Grok Bot / Cursor context window | `insights/tickers_index.json` (`< 80 KB` top signals) + per-ticker block inside `dashboard/data/tickers/{T}.json` |
| `dashboard/data/kpi_trends.json` | **18.12 MB** | Full historical series for all tickers in one file | `kpi_summary.json` (`< 120 KB` z-scores & inflections) + per-ticker KPIs in `dashboard/data/tickers/{T}.json` |
| `dashboard/data/insights/profiles.json` | **15.84 MB** | Full fund holdings history in one blob | `insights/funds_index.json` (`< 60 KB`) + `insights/funds/{fund_slug}.json` |
| `dashboard/data/research_memory_evidence.json` | **14.93 MB** | Loaded wholesale by UI and memory scripts | `research_memory_index.json` (`< 90 KB`) + on-demand per-lens/per-ticker shards |
| `dashboard/data/document_registry.json` | **10.40 MB** | 8,815 full document records in one JSON | `_system/data/catalog/documents.jsonl` (source of truth) -> `document_catalog_summary.json` (`< 50 KB`) + per-ticker `documents` array in `tickers/{T}.json` |

---

## 5. End-to-End Repeatable Workflows (How Data Flows Every Day)

### Workflow A: New Document Intake (PDF / Letter / VIC / Filing)
1. **Drop:** Human or Grok VIC Bot drops a PDF into Google Drive `Admin/Intake/{VIC,Research,Company,Activist}/` (or SEC downloader fetches a new filing).
2. **Hash & Dedupe (`import_drive_intake.py`):**
   - Computes `sha256` of bytes.
   - Checks `_system/data/catalog/documents.jsonl`. If `sha256` already exists, links existing `doc_id` and trashes the duplicate intake file.
3. **Store Binary in Drive (`Store 1`):**
   - Stamps `appProperties: {sha256, ticker, source_type}` on the Drive file and moves it by `fileId` to `Single Stocks/{TICKER}/{Category}/` or `Letters/{YYYY}Q{n}/`.
4. **Extract Text to Vault (`Store 2`):**
   - Extracts clean Markdown/text and writes it to `research-vault/{collection}/{TICKER}/{YYYY-MM-DD}-{slug}.md`.
5. **Register Pointer in SSI (`Store 3`):**
   - Appends 1 line to `_system/data/catalog/documents.jsonl` and updates `{TICKER}/third-party-analyses/source_inventory.json` (only if `semantic_sha256` changed). Zero PDF bytes enter SSI Git.

### Workflow B: Multi-Agent Research Loop (Grok -> Cursor -> Claude -> Human)
1. **Grok Bot (Daily/Weekly Scan):**
   - Reads `_system/sources.json`, `_system/portfolio/registry.json`, and `L0` summary feeds (`< 100 KB` each, verifying `_envelope.generated_at` and `_envelope.health.status == "healthy"`).
   - Opens a PR on `grok/<desk>/<date>-<slug>` containing `_system/data/desk_briefs/<desk>/<date>.json` and up to 3 `[PROPOSED <LENS>]` bullets in `_system/memory/daily/<date>.md`.
   - `marvin-pr-automerge.yml` runs `check_contributor_paths.py` and `check_desk_briefs.py`, auto-merging valid data drops.
2. **Cursor Agent (Marvin / Milly / Committee Underwriting):**
   - Triggered when a desk brief, filing sentinel, or Power Zone route flags a Tier 1/2 security.
   - Checks out SSI in `< 10 seconds` (post-cleanup `< 600 MB` repo).
   - Reads `{TICKER}/research/valuation_contract.json`, canonical `evidence/filing_digest.md`, and targeted `research-vault` extracts via `vault_paths.py`.
   - Runs `marvin_cloud_refresh.py {TICKER}` -> updates `valuation.json`, `deep_dive.md`, `adversarial.md`, and freezes a content-addressed `committee_work/` packet keyed by `evidence_sha256`.
3. **Claude (Deep Synthesis & Weekly Memory Curation):**
   - Runs weekly over `_system/reviews/pending/memory_triage.md` and cross-ticker themes, clustering the 1,014 pending `[PROPOSED]` bullets into deduplicated candidate additions for `_system/memory/MEMORY.md` with supporting citations from `research-vault`.
4. **Human Quality Filter (Drew & Michael):**
   - Reviews the Inbox Desk Briefs panel, Committee packets, and staged Memory Promotion PRs. Only Drew merges changes to `_system/memory/MEMORY.md`, `human_decision.json`, and `_system/reviews/approved/`.

---

## 6. Phased Implementation Roadmap

| Phase | Scope | Key Actions | Measurable Exit Gate |
|---|---|---|---|
| **Phase 1: Stop the Bleeding (Content-Gated Writes & Envelope Standard)** | Scripts & schemas in SSI (`2-3 PRs`, zero breaking changes) | 1. Add `write_if_semantic_changed()` helper and switch `insider_signal`, `thematic_context`, `filing_digest`, and `source_inventory` builders to write canonical undated filenames (`insider_signal.md`, etc.) while keeping a symlink/reader fallback for latest dated file.<br>2. Add standard `_envelope` block to all `dashboard/data/*.json` builders.<br>3. Unify Grok and Marvin memory daily writes into `_system/memory/daily/YYYY-MM-DD.md` and update `validate_sources.py`. | Zero new `*_YYYY-MM-DD.{md,json}` files created on daily runs when content is unchanged; all 20 top `dashboard/data/*.json` feeds pass `_envelope` schema check; `build_memory_triage.py` indexes Grok desk lessons. |
| **Phase 2: Complete Vault Cutover & Unified Document Catalog** | SSI + `research-vault` + Google Drive metadata | 1. Introduce `_system/data/catalog/documents.jsonl` keyed by `sha256`.<br>2. Update `build_document_registry.py` to read both SSI and `_external/research-vault` manifests.<br>3. Move remaining public SSI copies of `investment-wisdom` (214 MB), `dropbox_ingestion` (26 MB), `vic` (147 MB), and duplicate `activist_reports` (4.62 GB) to `research-vault` + Google Drive.<br>4. Stamp `appProperties.sha256` on Drive files and merge duplicate Drive `Accounting` folders. | `git ls-files` in public SSI has `0` files under `investment-wisdom/`, `dropbox_ingestion/`, or `*/vic/*.pdf`; `document_registry.json` reports full letter and vault counts (`> 1,500` text extracts linked). |
| **Phase 3: Prune Historical Dated Files & Raw Binaries from SSI Working Tree** | SSI working tree cleanup (`-49 GB` working tree) | 1. Delete superseded historical `insider_signal_YYYY-MM-DD.md` (51,981), `thematic_context_YYYY-MM-DD.md` (62,959), and `source_inventory_YYYY-MM-DD.*` (37,527) after verifying each ticker has its canonical undated file.<br>2. Verify 100% of `9,672` local `.pdf` files have verified `drive_file_id` + `sha256` in `documents.jsonl` and text extracts in Vault/evidence, then `git rm` binary `.pdf` and raw `.htm` (`sec-edgar/*.htm`) from SSI working tree. | SSI tracked file count drops from `303,687` to `< 30,000`; working tree drops from `51.71 GB` to `< 1.5 GB`; `make research-check` and all 1,200+ unit tests pass. |
| **Phase 4: Progressive Disclosure Sharding & Git History Packfile Compaction** | `dashboard/data/` shards + scheduled maintenance window | 1. Split the পাঁচ `10-18 MB` dashboard JSON monoliths into `< 100 KB` `L0` index files + per-ticker/per-fund shards.<br>2. Add `build_agent_index.py` (disposable local SQLite FTS5 index).<br>3. During a 30-minute off-hours maintenance window, run `git filter-repo` (or BFG) to strip historical `.htm` and `.pdf` blobs from `.git` packfiles, shrinking `.git` from `15.22 GB` to `< 600 MB` and retiring `jlumbroso/free-disk-space`. | `.git` clone size `< 600 MB`; CI checkout time `< 15s` without `free-disk-space`; Grok Bot & Cursor session token usage per scan reduced by `> 60%`. |

---

## 7. Risks of Simplification & Redundancy Kept on Purpose

### Risks & Mitigations
- **Risk: Evicting binary PDFs and raw SEC `.htm` files from SSI Git could break scripts that expect local files on disk.**
  - *Mitigation:* Phase 2/3 keeps `filing_digest.md`, `filing_facts.json`, `sec_companyfacts.json`, and `research-vault` text extracts on disk, which are the exact files `marvin_cloud_refresh.py` and compilers read. Any script needing a raw PDF or raw `.htm` fetches it on demand into gitignored `/tmp/magis-cache/{sha256}` via `DOWNLOAD_MANIFEST.json` (EDGAR URL or `drive_file_id`).
- **Risk: Removing dated `insider_signal_YYYY-MM-DD.md` files could break glob readers expecting `insider_signal_*.md`.**
  - *Mitigation:* Audit all readers via `rg "insider_signal_|thematic_context_|source_inventory_"` in Phase 1; update readers to prefer canonical `insider_signal.md` with fallback to `sorted(glob("insider_signal_*.md"))[-1]` before deleting historical files in Phase 3.

### Redundancy Kept on Purpose
- **Human Quality Filter (`human-quality-filter.mdc`):** `MEMORY.md`, `human_decision.json`, and `_system/reviews/approved/` remain 100% human-gated. Automated memory curation only stages a reviewable diff.
- **IB Gateway Safety (`CLAUDE.md` Rules 0 & 9):** Zero Gateway contact from SSI or any data pipeline; broker truth arrives exclusively via IBKR Flex HTTPS and Client Portal CSVs.
- **Milly Adversarial Gate & Provenance Manifests:** Every deep dive and valuation update still requires Milly adversarial verification and locked fact provenance (`sha256` + locator).
- **Dual-Store Backup for Proprietary Research:** Every proprietary PDF (VIC, SumZero, Superinvestor Letter, Manager Meeting) has its binary backed up on Google Drive (`Store 1`) AND its full text extract versioned in private `research-vault` (`Store 2`), linked by `sha256` in SSI (`Store 3`).

## 8. Implementation Scope Checklist

- [x] Deep architectural audit across SSI, Google Drive, `research-vault`, and D1 (2026-10-16)
- [x] Phase 1: `_system/scripts/atomic_io.py` (`write_text_if_changed`, `write_json_if_changed`, `attach_envelope`), canonical undated evidence filenames (`insider_signal.md`, `thematic_context.md`, `filing_digest.md`, `source_inventory.json`), `_envelope` schema, unified memory triage (`build_memory_triage.py` indexing both `_system/memory/daily` and `_system/memory-hub/research-equity/daily`)
- [x] Phase 2: `_system/data/catalog/documents.jsonl` (8,815 cross-store documents), Drive-resilient `build_document_registry.py`, Drive `appProperties.sha256` stamping in `import_drive_intake.py`
- [x] Phase 3: `_system/scripts/compact_dated_artifacts.py` + core-book compaction (74 canonical undated files materialized, 3,367 redundant dated files pruned)
- [x] Phase 4: `_system/scripts/build_progressive_shards.py` (`L0` summary feeds `< 100 KB` + 348 `L1` `dashboard/data/agent_shards/{TICKER}.json`), `_system/scripts/build_local_search_index.py`, and `_system/scripts/query_magis_index.py` (SQLite FTS5 cache)
