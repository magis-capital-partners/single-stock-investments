# Agent context pack: SBR (Sabine Royalty Trust)

## Identity (stable)
- Ticker: SBR
- Company: Sabine Royalty Trust
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Sabine Royalty Trust is a Texas express trust that holds non-operating royalty and mineral interests across producing and proved undeveloped oil and gas properties in Florida, Louisiana, Mississippi, New Mexico, Oklahoma, and Texas. **[Fact]** The Trust has no employees; Argent Trust Company serves as trustee and distributes essentially all distributable income monthly. **[Fact]** As of February 27, 2026, there were **14,579,345** units outstanding (`SBR/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001193125_26_081251.htm`). **[Fact]** Calendar Q1 2026 royalty income was **$14.19 million** and distributable income was **$13.04 million** ($0.89 per unit for the quarter) with cash and short-term investments of **$8.26 million** at March 31, 2026 (`SBR/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001193125_26_213810.htm`). **[Fact]** The May 2026 monthly distribution was **$0.497900** per unit (`SBR/investor-documents/sec-edgar/8-K_20260505_exhibit_sbr-ex99_1.htm_acc0001193125_26_205699.htm`).

## Why the market might be wrong (stable)
Yield-oriented screens often skip royalty trusts, K-1 complexity, and depletion narrative, so a long record of cash distributions can trade below a simple sum of expected payouts. **[Inference]** Horizon Kinetics frames Sabine as a localized inflation beneficiary: monthly pass-through of oil and gas prices with minimal overhead (~0.7% of revenues in their commentary). **[Inference]** Engineering has added proved reserves over decades despite production, which the market may under-weight when pricing the trust on near-term distribution noise alone.

## Returns (stable, percent per year)
- Base return: 7.3% per year (annualized return)
- Scenarios (percent per year): bear 1.9, base 7.3, bull 11.3

## Key assumptions (stable)
- Price today: **$77.23** (source: Stooq SBR.US close 2026-06-03)
- Payoff price (Year 5): **$110.0** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **5** (source: Model choice in valuation.json (not company guidance))
- Five-year cumulative distributions at ~$4.75/unit per year uplift: **+$23.75/sh** (source: 5 x $4.75 [Assumption] from trailing monthly 8-K cadence)
- Terminal unit price after five years uplift: **+$9.02/sh** (source: Terminal ~$86 vs $77.23 today [Assumption])

## Open questions (stable)
- First Marvin deep dive; CIK corrected to **710752** for SEC downloads (was **84128** in onboard batch).
- HK Q3-2025 SBR case study cited as context only; not in base IRR.
- Trustee administrative bonus (~$30k/month Feb 2026–Jan 2027 per 10-Q) noted; monitor vs distribution trend.

## Verified claims (stable, cited)
- [assumption] Five-year cumulative distributions at ~$4.75/unit per year uplift: **+$23.75/sh** (source: SBR/research/thesis_card.json)
- [assumption] Horizon (years): **5** (source: SBR/research/thesis_card.json)
- [assumption] Payoff price (Year 5): **$110.0** (source: SBR/research/thesis_card.json)
- [assumption] Price today: **$77.23** (source: SBR/research/thesis_card.json)
- [pending] Sabine Royalty Trust is a Texas express trust that holds non-operating royalty and mineral interests across producing and proved undeveloped oil and gas properties in Florida, Louisiana, Mississippi, New Mexico, Oklahoma, and Texas. **[Fact]** The Trust has no employees; Argent Trust Company serves as trustee and distributes essentially all distributable income monthly. **[Fact]** As of February 27, 2026, there were **14,579,345** units outstanding (`SBR/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001193125_26_081251.htm`). **[Fact]** Calendar Q1 2026 royalty income was **$14.19 million** and distributable income was **$13.04 million** ($0.89 per unit for the quarter) with cash and short-term investments of **$8.26 million** at March 31, 2026 (`SBR/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001193125_26_213810.htm`). **[Fact]** The May 2026 monthly distribution was **$0.497900** per unit (`SBR/investor-documents/sec-edgar/8-K_20260505_exhibit_sbr-ex99_1.htm_acc0001193125_26_205699.htm`). (source: SBR/research/thesis_card.json)
- [assumption] Terminal unit price after five years uplift: **+$9.02/sh** (source: SBR/research/thesis_card.json)
- [pending] Yield-oriented screens often skip royalty trusts, K-1 complexity, and depletion narrative, so a long record of cash distributions can trade below a simple sum of expected payouts. **[Inference]** Horizon Kinetics frames Sabine as a localized inflation beneficiary: monthly pass-through of oil and gas prices with minimal overhead (~0.7% of revenues in their commentary). **[Inference]** Engineering has added proved reserves over decades despite production, which the market may under-weight when pricing the trust on near-term distribution noise alone. (source: SBR/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — SBR

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `SBR/research/evidence/document_inventory.json`  

Documents in folder: **80** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 10-K | 2022-03-25 | `investor-documents/sec-edgar/10-K_20220325_rpt20211231_acc0001193125_22_085045.htm` | 30000 |
| partial | 10-K | 2023-02-28 | `investor-documents/sec-edgar/10-K_20230228_rpt20221231_acc0001193125_23_054030.htm` | 30000 |
| full | 10-K | 2024-02-29 | `investor-documents/sec-edgar/10-K_20240229_rpt20231231_acc0001193125_24_052967.htm` | 209582 |
| full | 10-K | 2025-02-27 | `investor-documents/sec-edgar/10-K_20250227_rpt20241231_acc0000950170_25_029052.htm` | 216038 |
| full | 10-K | 2026-02-27 | `investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001193125_26_081251.htm` | 227633 |
| scan | 10-Q | 2021-11-09 | `investor-documents/sec-edgar/10-Q_20211109_rpt20210930_acc0001193125_21_324113.htm` | 8000 |
| scan | 10-Q | 2022-05-12 | `investor-documents/sec-edgar/10-Q_20220512_rpt20220331_acc0001193125_22_148313.htm` | 8000 |
| scan | 10-Q | 2022-08-11 | `investor-documents/sec-edgar/10-Q_20220811_rpt20220630_acc0001193125_22_218379.htm` | 8000 |
| scan | 10-Q | 2022-11-10 | `investor-documents/sec-edgar/10-Q_20221110_rpt20220930_acc0001193125_22_282438.htm` | 8000 |
| scan | 10-Q | 2023-05-08 | `investor-documents/sec-edgar/10-Q_20230508_rpt20230331_acc0001193125_23_138074.htm` | 8000 |
| scan | 10-Q | 2023-08-04 | `investor-documents/sec-edgar/10-Q_20230804_rpt20230630_acc0001193125_23_203813.htm` | 8000 |
| scan | 10-Q | 2023-11-07 | `investor-documents/sec-edgar/10-Q_20231107_rpt20230930_acc0001193125_23_272367.htm` | 8000 |
| full | 10-Q | 2024-05-09 | `investor-documents/sec-edgar/10-Q_20240509_rpt20240331_acc0000950170_24_056580.htm` | 45718 |
| partial | 10-Q | 2024-08-08 | `investor-documents/sec-edgar/10-Q_20240808_rpt20240808_acc0000950170_24_093772.htm` | 30000 |
| partial | 10-Q | 2024-11-12 | `investor-documents/sec-edgar/10-Q_20241112_rpt20241112_acc0000950170_24_124994.htm` | 30000 |
| full | 10-Q | 2025-05-09 | `investor-documents/sec-edgar/10-Q_20250509_rpt20250331_acc0000950170_25_067649.htm` | 46704 |
| partial | 10-Q | 2025-08-08 | `investor-documents/sec-edgar/10-Q_20250808_rpt20250630_acc0000950170_25_105603.htm` | 30000 |
| partial | 10-Q | 2025-11-07 | `investor-documents/sec-edgar/10-Q_20251107_rpt20251107_acc0001193125_25_271873.htm` | 30000 |
| full | 10-Q | 2026-05-08 | `investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001193125_26_213810.htm` | 46655 |
| full | proxy | 2022-02-09 | `investor-documents/sec-edgar/DEF 14A_20220209_rpt20220404_acc0001193125_22_031730.htm` | 48794 |
| scan | 8-K | 2024-05-03 | `investor-documents/sec-edgar/8-K_20240503_exhibit_sbr-ex99_1.htm_acc0000950170_24_052726.htm` | 2878 |
| scan | 8-K | 2024-05-03 | `investor-documents/sec-edgar/8-K_20240503_rpt20240503_acc0000950170_24_052726.htm` | 3210 |
| scan | 8-K | 2024-06-07 | `investor-documents/sec-edgar/8-K_20240607_exhibit_sbr-ex99_1.htm_acc0000950170_24_070381.htm` | 2900 |
| scan | 8-K | 2024-06-07 | `investor-documents/sec-edgar/8-K_20240607_rpt20240607_acc0000950170_24_070381.htm` | 3214 |
| scan | 8-K | 2024-07-05 | `investor-documents/sec-edgar/8-K_20240705_exhibit_sbr-ex99_1.htm_acc0000950170_24_081802.htm` | 2902 |
| scan | 8-K | 2024-07-05 | `investor-documents/sec-edgar/8-K_20240705_rpt20240705_acc0000950170_24_081802.htm` | 3214 |
| scan | 8-K | 2024-08-05 | `investor-documents/sec-edgar/8-K_20240805_exhibit_sbr-ex99_1.htm_acc0000950170_24_090557.htm` | 2902 |
| scan | 8-K | 2024-08-05 | `investor-documents/sec-edgar/8-K_20240805_rpt20240805_acc0000950170_24_090557.htm` | 3226 |
| scan | 8-K | 2024-09-06 | `investor-documents/sec-edgar/8-K_20240906_exhibit_sbr-ex99_1.htm_acc0000950170_24_104364.htm` | 2921 |
| scan | 8-K | 2024-09-06 | `investor-documents/sec-edgar/8-K_20240906_rpt20240906_acc0000950170_24_104364.htm` | 3239 |
| scan | 8-K | 2024-10-04 | `investor-documents/sec-edgar/8-K_20241004_exhibit_sbr-ex99_1.htm_acc0000950170_24_112769.htm` | 2883 |
| scan | 8-K | 2024-10-04 | `investor-documents/sec-edgar/8-K_20241004_rpt20241004_acc0000950170_24_112769.htm` | 3229 |
| scan | 8-K | 2024-11-05 | `investor-documents/sec-edgar/8-K_20241105_exhibit_sbr-ex99_1.htm_acc0000950170_24_121191.htm` | 4956 |
| scan | 8-K | 2024-11-05 | `investor-documents/sec-edgar/8-K_20241105_rpt20241105_acc0000950170_24_121191.htm` | 3233 |
| scan | 8-K | 2024-12-05 | `investor-documents/sec-edgar/8-K_20241205_exhibit_sbr-ex99_1.htm_acc0000950170_24_133578.htm` | 4941 |
| scan | 8-K | 2024-12-05 | `investor-documents/sec-edgar/8-K_20241205_rpt20241205_acc0000950170_24_133578.htm` | 3233 |
| scan | 8-K | 2025-01-03 | `investor-documents/sec-edgar/8-K_20250103_exhibit_sbr-ex99_1.htm_acc0000950170_25_000790.htm` | 4966 |
| scan | 8-K | 2025-01-03 | `investor-documents/sec-edgar/8-K_20250103_rpt20250103_acc0000950170_25_000790.htm` | 3228 |
| scan | 8-K | 2025-02-07 | `investor-documents/sec-edgar/8-K_20250207_exhibit_sbr-ex99_1.htm_acc0000950170_25_015946.htm` | 4647 |
| scan | 8-K | 2025-02-07 | `investor-documents/sec-edgar/8-K_20250207_rpt20250207_acc0000950170_25_015946.htm` | 3233 |
| scan | 8-K | 2025-03-07 | `investor-documents/sec-edgar/8-K_20250307_exhibit_sbr-ex99_1.htm_acc0000950170_25_035166.htm` | 4811 |
| scan | 8-K | 2025-03-07 | `investor-documents/sec-edgar/8-K_20250307_rpt20250307_acc0000950170_25_035166.htm` | 3218 |
| scan | 8-K | 2025-04-04 | `investor-documents/sec-edgar/8-K_20250404_exhibit_sbr-ex99_1.htm_acc0000950170_25_050977.htm` | 4764 |
| scan | 8-K | 2025-04-04 | `investor-documents/sec-edgar/8-K_20250404_rpt20250404_acc0000950170_25_050977.htm` | 3218 |
| scan | 8-K | 2025-05-05 | `investor-documents/sec-edgar/8-K_20250505_exhibit_sbr-ex99_1.htm_acc000095

## Canonical pointers (open only when needed)
- deep_dive: SBR/research/deep_dive_2026-06-03.md (sha256 sha256:c3b456bfa232e27d...)
- filing_digest: SBR/research/evidence/filing_digest.md (sha256 sha256:55d362502d33ff3e...)
- adversarial: SBR/research/adversarial_2026-06-03.md (sha256 sha256:68f99174c9a9d958...)
- valuation: SBR/research/valuation.json (sha256 sha256:1967bc6bac3b8045...)
- thesis_card: SBR/research/thesis_card.json (sha256 sha256:37c03ffb2f119c30...)
- cross_check: SBR/research/cross_check_third_party_2026-06-03.md (sha256 sha256:acc34d6d45c9749a...)

## Excluded from this pack
- SBR/research/valuation.json (full; returns block included, open only for assumption audit)
- SBR/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
