# Agent context pack: NUE (Nucor)

## Identity (stable)
- Ticker: NUE
- Company: Nucor
- Book: holdings
- Stance: watch
- Archetype: capital_cycle

## What this business is (stable)
Nucor Corporation is the largest steel producer in the United States by tonnage, built almost entirely on electric-arc-furnace (EAF) mini-mills fed by scrap and direct-reduced iron. **[Fact]** The company reports three operating segments: steel mills (sheet, plate, bar, and structural products), steel products (joist, deck, rebar fabrication, towers, and other downstream businesses), and raw materials (scrap yards, DRI, and brokerage). **[Fact]** FY2025 pretax segment earnings were **$2.383 billion** for mills, **$1.229 billion** for products, and **$153 million** for raw materials, with corporate eliminations of **$1.197 billion**. **[Fact]** Steel-mill shipments were **25.271 million tons** at **83%** capacity utilization. **[Fact]** Nucor is also in the late stages of a multi-year capital program, including a West Virginia sheet mill targeted at roughly **3 million tons** of annual capacity for about **$3.65 billion** net of state incentives. **[Fact]**

## Why the market might be wrong (stable)
We do not see a durable mispricing signal at today's price. **[Inference]** Nucor's cost position, balance-sheet strength, and project pipeline may justify a premium to our through-cycle component base of about **$179 per share** versus a price near **$231**. **[Inference]** The market may be capitalizing mid-cycle spreads and successful project completion, while our base case normalizes 2025 peak mill utilization and keeps an explicit supply-response reserve. **[Inference]** If projects earn above their cost of capital and industry supply discipline holds, the bull component schedule (**~$334 per share**) could prove conservative; if imports and new domestic capacity depress spreads, the low case (**~$68 per share**) is the relevant stress path.

## Returns (stable, percent per year)
- Base return: -3.56% per year (component base)
- Scenarios (percent per year): bear -0.8, base -23.8, bull -0.8

## Key assumptions (stable)
- Price today: **$230.74** (source: Yahoo NUE close 2026-07-20)
- Starting free cash flow per share: **$7.52** (source: FY2025 diluted EPS anchor from NUE/research/evidence_reconciliation_2026-07-15.json)
- Growth in years 1 through 5: **0.0%** per year (source: Base component sum $179/sh versus price; terminal value equals normalized component equity)
- Growth in years 6 through 7: **0.0%** per year (source: Scenario base)
- Selling multiple in year 10: **1.0 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- Blended owner cash: **$179.0** (source: component base sum from proof-complete schedule)

## Open questions (stable)
- Confirm post-refresh 10-K extract matches locked FY2025 facts in `evidence_reconciliation_2026-07-15.json`.
- Product-level capacity/import map remains a bounded stress reserve, not a full industry database.

## Verified claims (stable, cited)
- [assumption] Blended owner cash: **$179.0** (source: NUE/research/thesis_card.json)
- [assumption] Growth in years 1 through 5: **0.0%** per year (source: NUE/research/thesis_card.json)
- [assumption] Growth in years 6 through 7: **0.0%** per year (source: NUE/research/thesis_card.json)
- [pending] Nucor Corporation is the largest steel producer in the United States by tonnage, built almost entirely on electric-arc-furnace (EAF) mini-mills fed by scrap and direct-reduced iron. **[Fact]** The company reports three operating segments: steel mills (sheet, plate, bar, and structural products), steel products (joist, deck, rebar fabrication, towers, and other downstream businesses), and raw materials (scrap yards, DRI, and brokerage). **[Fact]** FY2025 pretax segment earnings were **$2.383 billion** for mills, **$1.229 billion** for products, and **$153 million** for raw materials, with corporate eliminations of **$1.197 billion**. **[Fact]** Steel-mill shipments were **25.271 million tons** at **83%** capacity utilization. **[Fact]** Nucor is also in the late stages of a multi-year capital program, including a West Virginia sheet mill targeted at roughly **3 million tons** of annual capacity for about **$3.65 billion** net of state incentives. **[Fact]** (source: NUE/research/thesis_card.json)
- [assumption] Price today: **$230.74** (source: NUE/research/thesis_card.json)
- [assumption] Selling multiple in year 10: **1.0 times cash flow** (source: NUE/research/thesis_card.json)
- [assumption] Starting free cash flow per share: **$7.52** (source: NUE/research/thesis_card.json)
- [assumption] Time horizon: **7 years** (source: NUE/research/thesis_card.json)
- [pending] We do not see a durable mispricing signal at today's price. **[Inference]** Nucor's cost position, balance-sheet strength, and project pipeline may justify a premium to our through-cycle component base of about **$179 per share** versus a price near **$231**. **[Inference]** The market may be capitalizing mid-cycle spreads and successful project completion, while our base case normalizes 2025 peak mill utilization and keeps an explicit supply-response reserve. **[Inference]** If projects earn above their cost of capital and industry supply discipline holds, the bull component schedule (**~$334 per share**) could prove conservative; if imports and new domestic capacity depress spreads, the low case (**~$68 per share**) is the relevant stress path. (source: NUE/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — NUE

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `NUE/research/evidence/document_inventory.json`  

Documents in folder: **0** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|

## Canonical pointers (open only when needed)
- deep_dive: NUE/research/deep_dive_2026-07-21.md (sha256 sha256:72175a0116163e2a...)
- filing_digest: NUE/research/evidence/filing_digest.md (sha256 sha256:f5380204ba2726e0...)
- adversarial: NUE/research/adversarial_2026-07-21.md (sha256 sha256:2e0c2faa47194067...)
- valuation: NUE/research/valuation.json (sha256 sha256:d810e5a0ce976b32...)
- thesis_card: NUE/research/thesis_card.json (sha256 sha256:013dd6b0f5ba02fd...)
- cross_check: NUE/research/cross_check_third_party_2026-07-21.md (sha256 sha256:3f328535dad078e3...)

## Excluded from this pack
- NUE/research/valuation.json (full; returns block included, open only for assumption audit)
- NUE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
