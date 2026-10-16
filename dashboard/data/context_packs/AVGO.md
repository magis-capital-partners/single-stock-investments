# Agent context pack: AVGO (Broadcom)

## Identity (stable)
- Ticker: AVGO
- Company: Broadcom
- Book: holdings
- Stance: watch
- Archetype: compounder

## What this business is (stable)
Broadcom Inc. (NASDAQ: AVGO) designs and supplies semiconductor devices and infrastructure software for enterprises, cloud operators, and equipment makers. **[Fact]** The company reports two segments: semiconductor solutions (networking, broadband, storage, custom AI accelerators, and wireless) and infrastructure software (VMware private cloud, mainframe, cybersecurity, and fibre-channel storage networking). **[Fact]** Fiscal year 2025 revenue was **$63.9 billion**, up **24%** from **$51.6 billion** in fiscal 2024, with semiconductor solutions at **$36.9 billion** and infrastructure software at **$27.0 billion**. **[Fact]** The VMware acquisition closed **November 22, 2023** for roughly **$30.8 billion** in cash plus **544 million** Broadcom shares. **[Inference]** Broadcom is a serial acquirer turned dual-engine compounder: high-margin silicon tied to data-center and AI build-outs, plus recurring subscription software, funded in part by **~$62 billion** of long-term debt.

## Why the market might be wrong (stable)
The market may be capitalizing AI custom-silicon backlog and VMware subscription momentum at a price that already embeds years of owner-cash growth. **[Fact]** Remaining performance obligations were **~$164.6 billion** as of **May 3, 2026**, including a long-term custom AI accelerator contract signed in Q2 fiscal 2026. **[Inference]** If incremental returns on reinvestment fall short of what the stock price implies, or if debt amortization and stock-based compensation absorb more cash than the headline operating cash flow suggests, the equity could remain rich despite strong reported growth. **[Inference]** Conversely, the market could be underweighting how much of fiscal 2025 software revenue came from upfront license recognition (**$7.8 billion** in products revenue) rather than recurring subscription cash.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$357.9** (source: Yahoo AVGO close 2026-09-04)
- Normalized owner earnings: **$26,914M** (source: us-gaap:NetCashProvidedByUsedInOperatingActivities; accession 0001730168-25-000121; form 10-K)
- Cash: **$19,628M** (source: us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents; accession 0001730168-26-000054; form 10-Q)
- Debt: **$62,655M** (source: us-gaap:LongTermDebtNoncurrent; accession 0001730168-26-000054; form 10-Q)
- Diluted shares: **4757.6M** (source: dei:EntityCommonStockSharesOutstanding; accession 0001730168-26-000054; form 10-Q)
- Reinvestment rate: **35.0%** (source: Versioned initial bounds; refresh from the issuer reinvestment ledger.)
- Incremental after-tax ROIC: **18.0%** (source: Conservative bounded starting cases pending a longer primary-source capital bridge.)
- Discount rate: **10.0%** (source: Approved risk bounds for the automated first pass.)

## Open questions (stable)
- Review typed falsifier draft **`AVGO/research/falsifier_drafts/bf20bf9240a0e5b288ab0357.json`**: Q3 FY2026 normalized owner earnings TTM below **$26,914M** triggers low-case bridge compression (observable after **2026-09-10**)
- Confirm reinvestment rate and incremental return assumptions against capital allocation disclosures before stance promotion
- Milly adversarial pass pending: **`AVGO/research/adversarial_2026-08-18.md`**
- No approved third party in base IRR; re-scan when Substacks or fund letters are indexed

## Verified claims (stable, cited)
- [verified] CashAndCashEquivalentsAtCarryingValue moved 9,348 → 1.618e+04 (+73.1%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm.txt)
- [verified] CashAndCashEquivalentsAtCarryingValue moved 9,472 → 1.963e+04 (+107.2%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents moved 9,348 → 1.618e+04 (+73.1%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 124 → 3,450 (+2682.3%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest moved 4,964 → 9,306 (+87.5%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest moved 5,895 → 2.314e+04 (+292.5%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm.txt)
- [verified] ContractWithCustomerLiabilityRevenueRecognized moved 2,440 → 9,205 (+277.2%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm.txt)
- [verified] DebtCurrent moved 5,531 → 2,252 (-59.3%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] DeferredIncomeTaxesandOtherNoncashTaxExpense moved 1,965 → 4,008 (+104.0%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm.txt)
- [verified] DeferredTaxAndOtherLiabilitiesNoncurrent moved 3,365 → 1,615 (-52.0%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)
- [verified] DeferredTaxAssetsTaxDeferredExpenseCompensationAndBenefitsShareBasedCompensationCost moved 291 → 474 (+62.9%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm.txt)
- [verified] EarningsPerShareBasic moved 1.05 → 1.96 (+86.7%) vs comparable prior filing (source: AVGO/research/evidence/_text/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — AVGO

**Generated:** 2026-09-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `AVGO/research/evidence/document_inventory.json`  

Documents in folder: **74** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 424B | 2025-01-06 | `investor-documents/sec-edgar/424B5_20250106_rpt_acc0001193125_25_001877.htm` | 30058 |
| partial | 424B | 2025-07-07 | `investor-documents/sec-edgar/424B5_20250707_rpt_acc0001193125_25_155891.htm` | 30058 |
| partial | 424B | 2025-09-22 | `investor-documents/sec-edgar/424B5_20250922_rpt_acc0001193125_25_210136.htm` | 30058 |
| full | 424B | 2026-01-06 | `investor-documents/sec-edgar/424B5_20260106_rpt_acc0001193125_26_003525.htm` | 232886 |
| partial | 10-K | 2021-12-17 | `investor-documents/sec-edgar/10-K_20211217_rpt20211031_acc0001730168_21_000153.htm` | 30057 |
| partial | 10-K | 2022-12-16 | `investor-documents/sec-edgar/10-K_20221216_rpt20221030_acc0001730168_22_000118.htm` | 30057 |
| full | 10-K | 2023-12-14 | `investor-documents/sec-edgar/10-K_20231214_rpt20231029_acc0001730168_23_000096.htm` | 459128 |
| full | 10-K | 2024-12-20 | `investor-documents/sec-edgar/10-K_20241220_rpt20241103_acc0001730168_24_000139.htm` | 469417 |
| full | 10-K | 2025-12-18 | `investor-documents/sec-edgar/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm` | 453327 |
| scan | 10-Q | 2022-03-10 | `investor-documents/sec-edgar/10-Q_20220310_rpt20220130_acc0001730168_22_000029.htm` | 8056 |
| scan | 10-Q | 2022-06-09 | `investor-documents/sec-edgar/10-Q_20220609_rpt20220501_acc0001730168_22_000081.htm` | 8056 |
| scan | 10-Q | 2022-09-08 | `investor-documents/sec-edgar/10-Q_20220908_rpt20220731_acc0001730168_22_000094.htm` | 8056 |
| scan | 10-Q | 2023-03-08 | `investor-documents/sec-edgar/10-Q_20230308_rpt20230129_acc0001730168_23_000008.htm` | 8056 |
| scan | 10-Q | 2023-06-07 | `investor-documents/sec-edgar/10-Q_20230607_rpt20230430_acc0001730168_23_000064.htm` | 8056 |
| scan | 10-Q | 2023-09-06 | `investor-documents/sec-edgar/10-Q_20230906_rpt20230730_acc0001730168_23_000077.htm` | 8056 |
| scan | 10-Q | 2024-03-14 | `investor-documents/sec-edgar/10-Q_20240314_rpt20240204_acc0001730168_24_000023.htm` | 8056 |
| full | 10-Q | 2024-06-13 | `investor-documents/sec-edgar/10-Q_20240613_rpt20240505_acc0001730168_24_000080.htm` | 286816 |
| scan | 10-Q | 2024-09-11 | `investor-documents/sec-edgar/10-Q_20240911_rpt20240804_acc0001730168_24_000099.htm` | 8056 |
| scan | 10-Q | 2025-03-12 | `investor-documents/sec-edgar/10-Q_20250312_rpt20250202_acc0001730168_25_000021.htm` | 8056 |
| full | 10-Q | 2025-06-11 | `investor-documents/sec-edgar/10-Q_20250611_rpt20250504_acc0001730168_25_000064.htm` | 245210 |
| partial | 10-Q | 2025-09-10 | `investor-documents/sec-edgar/10-Q_20250910_rpt20250803_acc0001730168_25_000098.htm` | 30058 |
| partial | 10-Q | 2026-03-11 | `investor-documents/sec-edgar/10-Q_20260311_rpt20260201_acc0001730168_26_000016.htm` | 30058 |
| full | 10-Q | 2026-06-09 | `investor-documents/sec-edgar/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm` | 238035 |
| scan | proxy | 2023-02-17 | `investor-documents/sec-edgar/DEF 14A_20230217_rpt20230403_acc0001140361_23_007640.htm` | 8056 |
| scan | proxy | 2024-02-26 | `investor-documents/sec-edgar/DEF 14A_20240226_rpt20240422_acc0001140361_24_009541.htm` | 8056 |
| scan | proxy | 2025-03-03 | `investor-documents/sec-edgar/DEF 14A_20250303_rpt20250421_acc0001193125_25_044112.htm` | 8056 |
| full | proxy | 2026-03-02 | `investor-documents/sec-edgar/DEF 14A_20260302_rpt20260420_acc0001193125_26_085691.htm` | 240251 |
| scan | 8-K | 2024-07-12 | `investor-documents/sec-edgar/8-K_20240712_rpt20240712_acc0001140361_24_033072.htm` | 7385 |
| scan | 8-K | 2024-09-05 | `investor-documents/sec-edgar/8-K_20240905_rpt20240905_acc0001730168_24_000095.htm` | 3443 |
| scan | 8-K | 2024-10-02 | `investor-documents/sec-edgar/8-K_20241002_rpt20241002_acc0001193125_24_231159.htm` | 7207 |
| scan | 8-K | 2024-12-12 | `investor-documents/sec-edgar/8-K_20241212_rpt20241212_acc0001730168_24_000125.htm` | 3460 |
| scan | 8-K | 2025-01-10 | `investor-documents/sec-edgar/8-K_20250110_rpt20250110_acc0001193125_25_004476.htm` | 6974 |
| scan | 8-K | 2025-01-13 | `investor-documents/sec-edgar/8-K_20250113_rpt20250113_acc0001193125_25_005318.htm` | 5280 |
| scan | 8-K | 2025-03-06 | `investor-documents/sec-edgar/8-K_20250306_rpt20250306_acc0001730168_25_000009.htm` | 3417 |
| scan | 8-K | 2025-04-22 | `investor-documents/sec-edgar/8-K_20250422_rpt20250421_acc0001730168_25_000037.htm` | 3860 |
| scan | 8-K | 2025-06-05 | `investor-documents/sec-edgar/8-K_20250605_rpt20250605_acc0001730168_25_000061.htm` | 3407 |
| scan | 8-K | 2025-07-11 | `investor-documents/sec-edgar/8-K_20250711_rpt20250711_acc0001193125_25_158202.htm` | 8055 |
| scan | 8-K | 2025-09-04 | `investor-documents/sec-edgar/8-K_20250904_rpt20250904_acc0001730168_25_000094.htm` | 3443 |
| scan | 8-K | 2025-09-09 | `investor-documents/sec-edgar/8-K_20250909_rpt20250903_acc0001193125_25_199281.htm` | 8056 |
| scan | 8-K | 2025-09-10 | `investor-documents/sec-edgar/8-K_20250910_rpt20250910_acc0001193125_25_200108.htm` | 3341 |
| scan | 8-K | 2025-09-29 | `investor-documents/sec-edgar/8-K_20250929_rpt20250929_acc0001193125_25_223202.htm` | 8055 |
| scan | 8-K | 2025-12-11 | `investor-documents/sec-edgar/8-K_20251211_rpt20251211_acc0001730168_25_000116.htm` | 3460 |
| scan | 8-K | 2026-01-13 | `investor-documents/sec-edgar/8-K_20260113_rpt20260113_acc0001193125_26_011731.htm` | 8056 |
| scan | 8-K | 2026-03-02 | `investor-documents/sec-edgar/8-K_20260302_rpt20260224_acc0001193125_26_085656.htm` | 3168 |
| scan | 8-K | 2026-03-04 | `investor-documents/sec-edgar/8-K_20260304_rpt20260304_acc0001730168_26_000011.htm` | 3404 |
| scan | 8-K | 2026-04-02 | `investor-documents/sec-edgar/8-K_20260402_rpt20260330_acc0001193125_26_1405

## Canonical pointers (open only when needed)
- deep_dive: AVGO/research/deep_dive_2026-08-18.md (sha256 sha256:fbfe27a046141515...)
- filing_digest: AVGO/research/evidence/filing_digest.md (sha256 sha256:fc334a8808c675ae...)
- adversarial: AVGO/research/adversarial_2026-08-18.md (sha256 sha256:fe9c64eeab056fbf...)
- valuation: AVGO/research/valuation.json (sha256 sha256:10022d42257406c8...)
- thesis_card: AVGO/research/thesis_card.json (sha256 sha256:251f75557a991ff8...)
- cross_check: AVGO/research/cross_check_third_party_2026-08-18.md (sha256 sha256:74a437fa5223a6ca...)

## Excluded from this pack
- AVGO/research/valuation.json (full; returns block included, open only for assumption audit)
- AVGO/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
