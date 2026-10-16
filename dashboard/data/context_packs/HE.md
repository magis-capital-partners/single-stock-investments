# Agent context pack: HE (Hawaiian Electric Industries)

## Identity (stable)
- Ticker: HE
- Company: Hawaiian Electric Industries
- Book: holdings
- Stance: watch
- Archetype: infrastructure

## What this business is (stable)
Hawaiian Electric Industries is the parent of Hawaii's regulated electric utility and related businesses serving most of the state. **[Fact]** Consolidated revenues were about **$3.09 billion** in fiscal 2025 (`investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm`). **[Fact]** The company reports an **Electric Utility** segment plus **All Other** activities. **[Fact]** Earnings and cash flow are set largely by the Hawaii Public Utilities Commission through allowed returns on rate-base capital, not by open-market pricing alone. **[Fact]** The common dividend has been suspended since the August 2023 Maui wildfires while the company funds legal and restoration obligations. **[Fact]** HE completed the sale of its **90.1%** stake in American Savings Bank at the end of calendar 2024 and is now essentially a pure-play utility (**[Inference]** from Horizon Kinetics Q1 2025 commentary, context tier).

## Why the market might be wrong (stable)
The stock still trades like a distressed credit event at roughly **$13** per share (Stooq, 2026-06-03), down sharply from pre-fire levels. **[Inference]** Index and income funds that sort on dividend yield never see the name, which creates a **predictive attribute** (Horizon Kinetics equity yield curve): the payoff is known in direction (regulated recovery, dividend reinstatement, credit repair) but mis-timed for twelve-month holders. **[Inference]** The market may be anchoring on trough GAAP earnings (**$0.71** diluted EPS in FY2025 per 10-K XBRL) instead of mid-cycle owner cash once wildfire payments normalize. **[Opinion]** Patience is the edge; precision on timing and residual liability is not.

## Returns (stable, percent per year)
- Base return: 12.05% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 5.2, base 13.0, bull 16.5

## Key assumptions (stable)
- Price today: **$13.37** (source: Stooq HE.US close 2026-06-03)
- Starting free cash flow per share: **$0.95** (source: Marvin floor $0.55 (FY2025 OCF $391M less est. capex $320M, 172.6M shares) blended 50% with normalized recovery $1.35 [Assumption] as wildfire cash burden eases)
- Growth in years 1 through 5: **6.0%** per year (source: Normalized owner cash recovery; regulated earnings path)
- Growth in years 6 through 7: **4.0%** per year (source: Scenario base)
- Selling multiple in year 10: **14 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- Blended owner cash: **$0.95** (source: 50% marvin_floor / 50% normalized recovery [Assumption])

## Open questions (stable)
- CIK mismatch:** `us_ticker_config.json` lists CIK **354707** (HEICO) but folder filings are **Hawaiian Electric** (entity CIK **0000046207**). Fix before next download refresh.
- Normalized cash $1.35/sh** is Marvin assumption; confirm against management guidance post-settlement.
- HK extracts** are context tier only; promote via `third_party_sources.md` before blending into base IRR.
- Governance** post-Maui: review DEF 14A compensation and board changes.

## Verified claims (stable, cited)
- [verified] AssetRetirementObligationLiabilitiesSettled moved 1 → 3 (+200.0%) vs comparable prior filing (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] Bank-style revenue definition: operating revenue 2.974e+05 (NII 2.52e+05 + non-interest 4.541e+04) — consensus 'revenue' comparisons must reconcile definitions first (source: HE/research/evidence/_text/10-K_20240229_rpt20231231_acc0000354707_24_000012.htm.txt)
- [verified] Bank-style revenue definition: operating revenue 3.204e+05 (NII 2.508e+05 + non-interest 6.953e+04) — consensus 'revenue' comparisons must reconcile definitions first (source: HE/research/evidence/_text/10-K_20250224_rpt20241231_acc0000354707_25_000013.htm.txt)
- [verified] Bank-style revenue definition: operating revenue 3.204e+05 (NII 2.508e+05 + non-interest 6.953e+04) — consensus 'revenue' comparisons must reconcile definitions first (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] Bank-style revenue definition: operating revenue 7.956e+04 (NII 6.235e+04 + non-interest 1.721e+04) — consensus 'revenue' comparisons must reconcile definitions first (source: HE/research/evidence/_text/10-Q_20240510_rpt20240331_acc0000354707_24_000020.htm.txt)
- [verified] Bank-style revenue definition: operating revenue 8.172e+04 (NII 6.451e+04 + non-interest 1.721e+04) — consensus 'revenue' comparisons must reconcile definitions first (source: HE/research/evidence/_text/10-Q_20250509_rpt20250331_acc0000354707_25_000026.htm.txt)
- [verified] CashAndDueFromBanks moved 1.844e+05 → — (removed) vs comparable prior filing (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents moved 6.946e+05 → 1.243e+06 (+78.9%) vs comparable prior filing (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 1.31e+05 → 4.894e+04 (-62.6%) vs comparable prior filing (source: HE/research/evidence/_text/10-Q_20260508_rpt20260331_acc0000354707_26_000037.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 9.005e+05 → 2.621e+05 (-70.9%) vs comparable prior filing (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 1.423e+06 → 1.23e+05 (-91.4%) vs comparable prior filing (source: HE/research/evidence/_text/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm.txt)
- [verified] DebtInstrumentCarryingAmount moved 6.1e+05 → 2.077e+05 (-65.9%) vs comparable prior filing (source: HE/research/evidence/_text/10-Q_20260508_rpt20260331_acc0000354707_26_000037.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — HE

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `HE/research/evidence/document_inventory.json`  

Documents in folder: **68** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 424B | 2024-09-19 | `investor-documents/sec-edgar/424B5_20240919_rpt_acc0001104659_24_101172.htm` | 30000 |
| partial | 424B | 2024-09-23 | `investor-documents/sec-edgar/424B5_20240923_rpt_acc0001104659_24_102082.htm` | 30000 |
| full | 424B | 2024-09-24 | `investor-documents/sec-edgar/424B5_20240924_rpt_acc0001104659_24_102433.htm` | 243262 |
| partial | 10-K | 2022-02-25 | `investor-documents/sec-edgar/10-K_20220225_rpt20211231_acc0000354707_22_000049.htm` | 30000 |
| partial | 10-K | 2023-02-27 | `investor-documents/sec-edgar/10-K_20230227_rpt20221231_acc0000354707_23_000032.htm` | 30000 |
| full | 10-K | 2024-02-29 | `investor-documents/sec-edgar/10-K_20240229_rpt20231231_acc0000354707_24_000012.htm` | 300000 |
| full | 10-K | 2025-02-24 | `investor-documents/sec-edgar/10-K_20250224_rpt20241231_acc0000354707_25_000013.htm` | 300000 |
| full | 10-K | 2026-02-27 | `investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0000354707_26_000008.htm` | 300000 |
| full | annual | — | `investor-documents/ir-he/Hawaiian-Electric-Industries-Annual-Report.pdf` | 505964 |
| scan | 10-Q | 2021-11-05 | `investor-documents/sec-edgar/10-Q_20211105_rpt20210930_acc0000354707_21_000112.htm` | 8000 |
| scan | 10-Q | 2022-05-09 | `investor-documents/sec-edgar/10-Q_20220509_rpt20220331_acc0000354707_22_000066.htm` | 8000 |
| scan | 10-Q | 2022-08-08 | `investor-documents/sec-edgar/10-Q_20220808_rpt20220630_acc0000354707_22_000100.htm` | 8000 |
| scan | 10-Q | 2022-11-07 | `investor-documents/sec-edgar/10-Q_20221107_rpt20220930_acc0000354707_22_000114.htm` | 8000 |
| scan | 10-Q | 2023-05-09 | `investor-documents/sec-edgar/10-Q_20230509_rpt20230331_acc0000354707_23_000047.htm` | 8000 |
| scan | 10-Q | 2023-08-07 | `investor-documents/sec-edgar/10-Q_20230807_rpt20230630_acc0000354707_23_000064.htm` | 8000 |
| scan | 10-Q | 2023-11-13 | `investor-documents/sec-edgar/10-Q_20231113_rpt20230930_acc0000354707_23_000095.htm` | 8000 |
| full | 10-Q | 2024-05-10 | `investor-documents/sec-edgar/10-Q_20240510_rpt20240331_acc0000354707_24_000020.htm` | 300000 |
| scan | 10-Q | 2024-08-09 | `investor-documents/sec-edgar/10-Q_20240809_rpt20240630_acc0000354707_24_000053.htm` | 8000 |
| scan | 10-Q | 2024-11-08 | `investor-documents/sec-edgar/10-Q_20241108_rpt20240930_acc0000354707_24_000071.htm` | 8000 |
| full | 10-Q | 2025-05-09 | `investor-documents/sec-edgar/10-Q_20250509_rpt20250331_acc0000354707_25_000026.htm` | 300000 |
| partial | 10-Q | 2025-08-07 | `investor-documents/sec-edgar/10-Q_20250807_rpt20250630_acc0000354707_25_000039.htm` | 30000 |
| partial | 10-Q | 2025-11-07 | `investor-documents/sec-edgar/10-Q_20251107_rpt20250930_acc0000354707_25_000063.htm` | 30000 |
| full | 10-Q | 2026-05-08 | `investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0000354707_26_000037.htm` | 300000 |
| scan | proxy | — | `investor-documents/ir-he/Hawaiian-Electric-Industries-Inc-Proxy.pdf` | 6219 |
| scan | proxy | 2023-03-24 | `investor-documents/sec-edgar/DEF 14A_20230324_rpt_acc0001104659_23_036502.htm` | 8000 |
| scan | proxy | 2024-03-29 | `investor-documents/sec-edgar/DEF 14A_20240329_rpt20240513_acc0001104659_24_041136.htm` | 8000 |
| scan | proxy | 2025-03-28 | `investor-documents/sec-edgar/DEF 14A_20250328_rpt20250512_acc0001104659_25_029347.htm` | 8000 |
| full | proxy | 2026-04-29 | `investor-documents/sec-edgar/DEF 14A_20260429_rpt20260611_acc0001104659_26_051288.htm` | 292055 |
| scan | 8-K | 2024-08-09 | `investor-documents/sec-edgar/8-K_20240809_rpt20240809_acc0000354707_24_000052.htm` | 4123 |
| scan | 8-K | 2024-08-19 | `investor-documents/sec-edgar/8-K_20240819_rpt20240814_acc0000354707_24_000056.htm` | 6471 |
| scan | 8-K | 2024-09-19 | `investor-documents/sec-edgar/8-K_20240919_rpt20240919_acc0001104659_24_101130.htm` | 6812 |
| scan | 8-K | 2024-09-19 | `investor-documents/sec-edgar/8-K_20240919_rpt20240919_acc0001104659_24_101175.htm` | 8000 |
| scan | 8-K | 2024-09-23 | `investor-documents/sec-edgar/8-K_20240923_rpt20240923_acc0001104659_24_102097.htm` | 4698 |
| scan | 8-K | 2024-09-24 | `investor-documents/sec-edgar/8-K_20240924_rpt20240923_acc0001104659_24_102437.htm` | 6419 |
| scan | 8-K | 2024-10-30 | `investor-documents/sec-edgar/8-K_20241030_rpt20241030_acc0000354707_24_000060.htm` | 3351 |
| scan | 8-K | 2024-11-05 | `investor-documents/sec-edgar/8-K_20241105_rpt20241101_acc0000354707_24_000064.htm` | 8000 |
| scan | 8-K | 2024-11-08 | `investor-documents/sec-edgar/8-K_20241108_rpt20241108_acc0000354707_24_000070.htm` | 4131 |
| scan | 8-K | 2024-12-31 | `investor-documents/sec-edgar/8-K_20241231_rpt20241230_acc0001104659_24_132904.htm` | 8000 |
| scan | 8-K | 2025-01-03 | `investor-documents/sec-edgar/8-K_20250103_rpt20250102_acc0000354707_25_000003.htm` | 3527 |
| scan | 8-K | 2025-02-11 | `investor-documents/sec-edgar/8-K_20250211_rpt20250211_acc0000354707_25_000005.htm` | 4312 |
| scan | 8-K | 2025-02-21 | `investor-documents/sec-edgar/8-K_20250221_rpt20250221_acc0000354707_25_000008.htm` | 4166 |
| scan | 8-K | 2025-03-05 | `investor-documents/sec-edgar/8-K_20250305_rpt20250305_acc0000950142_25_000634.htm` | 8000 |
| scan | 8-K | 2025-03-26 | `investor-documents/sec-edgar/8-K_20250326_rpt20250326_acc0000354707_25_000017.htm` | 5320 |
| scan | 8-K | 2025-05-09 | `investor-documents/sec-edgar/8-K_20250509_rpt20250509_acc0000354707_25_000024.htm` | 4095 |
| scan | 8-K | 2025-05-14 | `investor-documents/sec-edgar/8-K_20250514_rpt20250512_acc0000354707_25_000029.htm` | 5939 |
| scan | 8-K | 2025-08-07 | `investor-documents/sec-edgar/8-K_20250807_rpt20250807_acc0000354707_25_000038.htm` | 4112 |
| scan | 8-K | 2025-09-08 | `

## Canonical pointers (open only when needed)
- deep_dive: HE/research/deep_dive_2026-06-03.md (sha256 sha256:9a19a90c0af9226f...)
- filing_digest: HE/research/evidence/filing_digest.md (sha256 sha256:4aeebf5f1da56bc1...)
- adversarial: HE/research/adversarial_2026-06-03.md (sha256 sha256:eb47a370db93f56e...)
- valuation: HE/research/valuation.json (sha256 sha256:ca4c09528c698bd2...)
- thesis_card: HE/research/thesis_card.json (sha256 sha256:b312d9d19ee27a64...)
- cross_check: HE/research/cross_check_third_party_2026-06-03.md (sha256 sha256:740cb1c67df008bc...)

## Excluded from this pack
- HE/research/valuation.json (full; returns block included, open only for assumption audit)
- HE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
