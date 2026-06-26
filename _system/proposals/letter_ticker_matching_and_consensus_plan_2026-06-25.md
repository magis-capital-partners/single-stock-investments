# Letter → Ticker Matching, Robust Grouping, and Consensus Plan

Date: 2026-06-25
Owner: Marvin
Scope: `_system/reference/superinvestor-letters/`, `build_superinvestor_insights.py`, `build_insights.py`, `dashboard/insights-viz.js`, Drive document catalog.

This plan addresses three requests:

1. Audit the letter→ticker matcher and **lower the false-positive rate**.
2. Replace ad-hoc per-letter matching with a **robust, consistent grouping method** (a security master + canonical fund registry), so tickers and funds reconcile across quarters and beyond our own book.
3. Recommend a **filter architecture** (beyond just `2026 Q1` / `2026 Q2`) and a **dataroma-style consensus view** to read letters and extract themes/consensus.

---

## 0. Audit — what is wrong today (measured, not assumed)

Running the current matcher (`build_superinvestor_insights.extract_tickers`) over the 201 local letter extracts:

| Metric | Value |
|---|---|
| Letters indexed | 201 |
| Known tickers (our book = holdings + watchlist + ticker folders) | 103 |
| Letters with ≥1 matched ticker | 127 (63%) |
| Total (letter, ticker) pairs | 366 |
| Pairs backed by **explicit ticker syntax** (`$X`, `(NASDAQ: X)`, `EXCH:X`) | **41 (11%)** |
| Pairs from **bare-word / single-alias only** (no explicit syntax) | **325 (89%)** |

Demonstrable false positives produced today:

- `LAND` — matched **38** letters via the bare symbol matching the English word "land" (case-insensitive). Almost all are noise.
- `META` — **28** letters; "meta" matches as a prefix/word ("meta-analysis", "metadata") in addition to Meta Platforms.
- `ICE` — **16**; "ice" the word. `SNOW` — "snow". `LB` — "lb" (pounds). `SMR` — overlaps "small modular reactor".
- `GOOGL` — **39**; matched whenever the word "Google" appears, including passing mentions ("we ran a Google search"), not positions.
- `0388.HK` — **40**; matched on the numeric base `0388` and a long company alias; plausibly real for HK-centric letters but unverified.

### Root causes

1. **Case-insensitive bare-symbol matching.** `extract_tickers` lowercases and matches `\bTICKER\b` for any ticker ≥3 chars. Three- and four-letter tickers that are also English words (`LAND`, `ICE`, `SNOW`, `META`, `CME`, `OR`, `HE`) match constantly.
2. **Single-word company aliases.** `_company_aliases` emits 1–2 word aliases of length ≥4 and matches them anywhere in the document. A passing mention of "Google" or "Berkshire" counts as a position.
3. **No centrality / threshold.** A single substring hit anywhere in a 30-page PDF includes the ticker. There is no notion of how central the company is to the letter (frequency, holdings-table membership, proximity to position verbs).
4. **Universe is capped at our 103 tickers.** The matcher only keeps tickers that are `in known`. It is structurally incapable of a true cross-fund consensus, because it cannot see the thousands of tickers that funds actually discuss outside our book.
5. **Fund identity is derived from filenames.** `infer_fund_name` turns `100 SQUATS PDF.txt` into fund "100 Squats Pdf" and `ACK Letter 2026 Q1` into manager "ACK". The same fund across quarters does not reconcile, so per-fund aggregation is unreliable.
6. **`letter_date` = file mtime.** Every letter shows the ingest date (e.g. `2026-06-09`), so time filtering and freshness scoring are wrong.

---

## Part A — Lower the false-positive rate (matching engine)

Goal: move from "any substring hit" to **evidence-tiered, scored matching** with an explicit precision target.

### A1. Confidence tiers for every (letter, ticker) candidate

Each candidate match gets a tier; only Tier A/B are emitted by default, Tier C is retained but flagged `low_confidence` and excluded from consensus counts.

- **Tier A — explicit ticker syntax (high).** `$TICKER`, `(NASDAQ: TICKER)`, `(TICKER)` immediately following a capitalized company name, `EXCHANGE: TICKER`, or a numeric ticker with explicit exchange context (`HKEX: 388`, `TSE: 3905`). Numeric bases (`0388`, `3905`) are **only** valid in Tier A.
- **Tier B — verified company name (medium).** Full multi-word company name (≥2 significant tokens, e.g. "Intercontinental Exchange", "Brookfield Corporation") matched case-sensitively at a capitalized position, AND appearing ≥2 times OR within a holdings/position context. A single 1-word generic alias is **not** sufficient.
- **Tier C — weak (excluded from consensus).** Bare symbol word match, single-word alias, or single mention. Retained for recall/debugging only.

### A2. English-word ticker blocklist → require Tier A

Maintain `ticker_word_collisions` (tickers that are also common English words / units): `LAND, ICE, SNOW, META, CME, OR, HE, LB, ALL, ON, SO, BIG, NOW, KEY, PSE, EVR, ...`. For these, **only Tier A explicit syntax counts**. Build this list programmatically by intersecting tickers with an English word list, then hand-curate.

### A3. Matching hygiene fixes

- Make bare-symbol matching **case-sensitive** (`META` matches, `meta` does not).
- Drop ambiguous aliases that map to >1 ticker (already done — keep).
- Require numeric ticker bases to have exchange context (kills `0388`/`3905` bare-number FPs).
- Add a **holdings-table / position-line detector**: lines that look like `Name … (TICKER) … weight%` or appear under a "Top Holdings"/"Portfolio" heading get a confidence boost; prose-only mentions do not.
- Centrality score per ticker = f(distinct mentions, holdings-table membership, proximity to add/trim/initiate/exit verbs). Threshold gates Tier B inclusion.

### A4. Calibration harness (so we can prove it improved)

- New script `_system/scripts/calibrate_letter_matching.py`:
  - Emits, per (letter, ticker), the tier, the matched evidence span, and the rule that fired.
  - Reports precision proxy: % of emitted pairs that are Tier A/B, and the distribution.
- A small **gold fixture set**: hand-label ~15 letters (every ticker truly discussed). CI check asserts precision ≥ target (e.g. ≥ 0.9) and recall does not regress below baseline on the fixtures.
- Store labels in `_system/reference/superinvestor-letters/_eval/gold.jsonl`.

**Acceptance:** Tier A/B share of emitted pairs rises from ~11% to ≥85%; `LAND/ICE/SNOW/META/LB` collapse to only their genuine explicit-syntax occurrences; fixture precision ≥ 0.9.

---

## Part B — Robust, consistent grouping method

The current pipeline groups "tickers mentioned in random letters". Replace it with two canonical reference layers so grouping is deterministic and reconciles across quarters and funds.

### B1. Security master (decouple from our 103-ticker book)

Create `_system/reference/securities/security_master.json` (ticker is the key):

```json
{
  "ICE":   {"name": "Intercontinental Exchange", "exchange": "NYSE", "aliases": ["Intercontinental Exchange"], "is_word_collision": true, "in_book": true},
  "0388.HK": {"name": "Hong Kong Exchanges and Clearing", "exchange": "HKEX", "numeric_base": "388", "aliases": ["HKEX"], "in_book": true},
  "BAM":   {"name": "Brookfield Asset Management", "exchange": "NYSE", "in_book": false}
}
```

Seeding strategy (no paid data feed required):
1. Seed all 103 book tickers + their registry company names.
2. **Harvest Tier-A explicit syntax across the entire corpus**: every `(NASDAQ: XYZ)` / `$XYZ` found in any letter becomes a candidate security. This bootstraps the broad universe directly from the letters themselves.
3. Optionally enrich from a free reference (SEC company_tickers.json for US names/CIKs) to validate harvested symbols and resolve names.
4. Hand-curate the `is_word_collision` flag and any aliases.

This is what makes a **real consensus** possible: letters can now be grouped by every security they discuss, not just the ones we happen to own.

### B2. Canonical fund registry (decouple from filenames)

Create human-editable `_system/reference/superinvestor-letters/funds.yaml`:

```yaml
- fund_id: admiral-capital
  fund: Admiral Capital
  manager: ""
  strategy: long-short-equity
  persona_map: [adversary, growth]
  filename_patterns: ["admiral", "admiralcap"]
  aliases: ["Admiral Cap", "Admiral Capital Group"]
```

Pipeline changes:
- Resolve each letter file to a `fund_id` via `filename_patterns` / fuzzy match; unmatched files go to a `funds_unresolved.json` queue for one-time curation (not silently mangled).
- Parse the **real letter date** from filename tokens (`Q1 2026`, `3.31.26`, `May 2026`) and document content; fall back to mtime only as last resort and mark `date_source`.
- A stable `fund_id` means a fund's letters reconcile across `2026Q1`, `2026Q2`, and future quarters → per-fund position history (added/trimmed over time) becomes possible.

### B3. Structured per-letter "mentions" record

Replace the flat `tickers: [...]` array with a structured list that the consensus layer consumes:

```json
{
  "ticker": "ICE",
  "tier": "A",
  "evidence": "($ICE) we added to Intercontinental Exchange",
  "action": "add",          // new | add | trim | exit | hold | short | discuss
  "conviction": "high",     // from position-table weight or language
  "in_book": true
}
```

`build_superinvestor_insights.py` becomes a thin orchestrator over: security master + fund registry + tiered matcher + action/conviction classifier. Output is deterministic given the same inputs (record provenance + rule versions).

**Acceptance:** Re-running the pipeline twice is byte-stable; ≥90% of letters resolve to a curated `fund_id`; same fund across two quarters shares one `fund_id`; tickers outside our book are now captured (universe ≫ 103).

---

## Part C — Filters + dataroma-style consensus

### C1. Filter / facet model

Today the dashboard exposes only quarter tabs (and only `2026Q1`/`2026Q2` exist locally, with Q2 thin at 13 vs 187). Generalize to a facet model so the same UI scales to the many Drive folders/quarters:

- **Time:** year, quarter, "latest", custom range (driven by real `letter_date`).
- **Fund / Manager / Strategy / Persona** (from `funds.yaml`).
- **Ticker / Sector / Theme.**
- **Action:** new buy, add, trim, exit, hold, short.
- **Conviction** and **confidence tier** (let the user choose "Tier A only" vs "include B").
- **Book overlap** ("our holdings only" toggle — already present, keep).

Quarters/years are derived from data, not hard-coded, and low-N quarters render a visible coverage warning (e.g. "Q2 2026: 13 letters — partial").

### C2. Consensus view (the dataroma analog)

New `consensus` section in `dashboard/data/insights.json`, computed from Tier A/B mentions only:

- **Most discussed / most held** — tickers ranked by # of distinct funds, with bull/bear/neutral split. (dataroma "Most held".)
- **Activity feed** — new buys, adds, trims, exits this period, grouped by ticker. (dataroma "Activity".)
- **Biggest changes** — net add vs trim count quarter-over-quarter per ticker (uses cross-quarter fund reconciliation from B2).
- **Sector / theme rollup** — aggregate stance per sector and per theme.
- **Per-ticker consensus card** — "N funds discuss ICE this quarter: 4 add, 1 trim", each with fund name, action badge, representative quote, and a link to the source PDF. This generalizes the existing `ticker_discussants` to the full universe and gates it on tier.

UI: add a **Consensus** tab in `insights-viz.js` alongside the existing Letters/Funds/Themes tabs, plus a "consensus" filter axis. Reuse existing table/card components.

### C3. Read the letters + extract themes

- Keep the per-letter **PDF link** (Drive `web_view_link`) and the extracted-text fallback already wired through `source_document` / `evidence_url`.
- Per-letter detail shows: lead summary, themes (with stance), structured positions (ticker/action/quote), risks, catalysts — already partly built; just feed it the new structured mentions.
- **Drive coverage without bloat:** the dashboard should not live-query Drive. Surface the many Drive folders via the lazy-loaded `document_catalog.json` (per the existing drive-reorg plan) with quarter/source/ticker facets, so "way more folders than Q1/Q2" become browsable filters rather than hard-coded tabs.

**Acceptance:** Consensus tab shows most-discussed tickers and an activity feed for a selected quarter; filters compose (e.g. "Tier A · adds · 2026 Q1 · Exchanges sector"); every consensus row links to the underlying letter PDF; coverage warnings appear on thin quarters.

---

## Phasing & execution order

1. **Phase 1 — Matcher precision (Part A).** Confidence tiers, case-sensitivity, word-collision blocklist, numeric-base gating, calibration harness + gold fixtures. *Self-contained; biggest immediate win.*
2. **Phase 2 — Security master (B1).** Harvest Tier-A symbols corpus-wide + seed from book; curate word-collision flags. Unlocks beyond-book universe.
3. **Phase 3 — Fund registry + real dates (B2) + structured mentions (B3).** Deterministic grouping.
4. **Phase 4 — Consensus data layer (C2).** New `consensus` block in `insights.json`.
5. **Phase 5 — Dashboard filters + Consensus tab (C1, C3).** UI on top of the new data.
6. **Phase 6 — Drive catalog facets.** Tie into the existing `drive_reorg_and_insights_plan_2026-06-25.md` document-catalog work so all quarters/folders are filterable.

## Risks & mitigations

- **Recall drop from stricter matching.** Mitigate with the gold fixture set and a recall floor in CI; keep Tier C retained (flagged) so nothing is lost, only down-weighted.
- **Security-master curation effort.** Bootstrap automatically from Tier-A syntax; manual curation only for word-collision flags and a few aliases.
- **Thin/late quarters mislead consensus.** Always render coverage counts and warnings; default filters to the most-populated recent quarter, not blindly "latest".
- **Fund reconciliation gaps.** Unresolved funds go to an explicit queue, never silently into a filename-derived bucket.

## Deliverables checklist

- [ ] `calibrate_letter_matching.py` + `_eval/gold.jsonl` + CI precision/recall check.
- [ ] Tiered matcher in `build_superinvestor_insights.py` (case-sensitive, blocklist, numeric gating, centrality score).
- [ ] `security_master.json` + harvester.
- [ ] `funds.yaml` + resolver + `funds_unresolved.json` queue + real-date parser.
- [ ] Structured `mentions` records flowing into `insights.json`.
- [ ] `consensus` block in `insights.json` (most-discussed, activity, changes, sector/theme).
- [ ] Consensus tab + generalized facet filters in `insights-viz.js`.
- [ ] Coverage warnings on thin quarters.
