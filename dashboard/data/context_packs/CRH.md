# Agent context pack: CRH (CRH plc)

## Identity (stable)
- Ticker: CRH
- Company: CRH plc
- Book: holdings
- Stance: watch
- Archetype: compounder

## What this business is (stable)
CRH plc is a global building materials company (aggregates, cement, asphalt, and building products) listed on the NYSE with an Irish parent and primary U.S. operating footprint. **[Fact]** FY2025 consolidated revenue was **$37.45 billion** per `investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm`. **[Fact]** FY2025 net income attributable to shareholders was **$3.75 billion** (diluted EPS **$5.51**) on the same filing. **[Fact]** The group reports through an Americas division (materials and building solutions) and an International division (international solutions), per segment disclosures in the FY2025 10-K and the October 2025 prospectus supplement (`424B5_20251007_rpt_acc0001193125_25_233453.htm`).

## Why the market might be wrong (stable)
The stock may trade as a passive infrastructure beneficiary while owner cash is already capital-intensive and levered. **[Inference]** FY2025 operating cash flow was **$5.62 billion** against capital spending of **$2.71 billion**, yet long-term debt on the March 2026 balance sheet was **$16.07 billion** per `10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm`, so equity holders may underweight refinancing and integration risk from serial acquisitions. **[Inference]** Proof-first owner-earnings math at **$99.95** per share (July 2026 price in `valuation.json`) implies mid-single-digit negative annual returns on the automated base bridge even as reported earnings grow, suggesting the market prices reinvestment quality above what the conservative template captures. **[Inference]** Q1 2026 trailing normalized owner earnings (**$2.99 billion**) sit only modestly above the low-case anchor (**$2.91 billion**), while Q3 2025 trailing owner earnings (**$2.61 billion**) were below that anchor, so cyclical seasonality may be misread as steady compounder growth.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$78.905** (source: Yahoo CRH close 2026-10-14)
- Normalized owner earnings: **$2,912M** (source: us-gaap:NetCashProvidedByUsedInOperatingActivities; accession 0001628280-26-009043; form 10-K)
- Cash: **$3,240M** (source: us-gaap:CashAndCashEquivalentsAtCarryingValue; accession 0001628280-26-028556; form 10-Q)
- Debt: **$16,071M** (source: us-gaap:LongTermDebtNoncurrent; accession 0001628280-26-028556; form 10-Q)
- Diluted shares: **668.2M** (source: dei:EntityCommonStockSharesOutstanding; accession 0001628280-26-028556; form 10-Q)
- Reinvestment rate: **35.0%** (source: Versioned initial bounds; refresh from the issuer reinvestment ledger.)
- Incremental after-tax ROIC: **18.0%** (source: Conservative bounded starting cases pending a longer primary-source capital bridge.)
- Discount rate: **10.0%** (source: Approved risk bounds for the automated first pass.)

## Open questions (stable)
- Stock-specific reinvestment and incremental ROIC not yet bridged from 10-K capex tables.
- Independent review of falsifier draft `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json`.
- Approve or reject third-party sources before blending external views.

## Verified claims (stable, cited)
- [verified] AccruedIncomeTaxesCurrent moved 58 → 99 (+70.7%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] AdjustedEarningsBeforeInterestTaxDepreciationAndAmortization moved 59 → 103 (+74.6%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] AssetsOfDisposalGroupIncludingDiscontinuedOperationCurrent moved 236 → 1,811 (+667.4%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedCashAndEquivalents moved 1 → 9 (+800.0%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedCashAndEquivalents moved 15 → 23 (+53.3%) vs comparable prior filing (source: CRH/research/evidence/_text/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedEquityMethodInvestments moved 366 → 49 (-86.6%) vs comparable prior filing (source: CRH/research/evidence/_text/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedIntangibleAssetsOtherThanGoodwill moved 21 → 2 (-90.5%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNoncurrentLiabilitiesLongTermDebt moved 519 → 159 (-69.4%) vs comparable prior filing (source: CRH/research/evidence/_text/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedOperatingLeaseLiability moved 12 → 62 (+416.7%) vs comparable prior filing (source: CRH/research/evidence/_text/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedOperatingLeaseLiability moved 13 → 1 (-92.3%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] BusinessCombinationRecognizedIdentifiableAssetsAcquiredGoodwillAndLiabilitiesAssumedLessNoncontrollingInterest moved 586 → 136 (-76.8%) vs comparable prior filing (source: CRH/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 2,631 → 388 (-85.2%) vs comparable prior filing (source: CRH/research/evidence/_text/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — CRH

**Generated:** 2026-10-14  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `CRH/research/evidence/document_inventory.json`  

Documents in folder: **51** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 424B | 2025-01-07 | `investor-documents/sec-edgar/424B5_20250107_rpt_acc0001193125_25_002926.htm` | 30058 |
| partial | 424B | 2025-01-07 | `investor-documents/sec-edgar/424B5_20250107_rpt_acc0001193125_25_002930.htm` | 30057 |
| partial | 424B | 2025-10-06 | `investor-documents/sec-edgar/424B5_20251006_rpt_acc0001193125_25_230993.htm` | 30057 |
| full | 424B | 2025-10-07 | `investor-documents/sec-edgar/424B5_20251007_rpt_acc0001193125_25_233453.htm` | 298181 |
| partial | 10-K | 2024-03-15 | `investor-documents/sec-edgar/10-K-A_20240315_rpt20231231_acc0001628280_24_011326.htm` | 30057 |
| full | 10-K | 2024-02-29 | `investor-documents/sec-edgar/10-K_20240229_rpt20231231_acc0001628280_24_007773.htm` | 597850 |
| full | 10-K | 2025-02-26 | `investor-documents/sec-edgar/10-K_20250226_rpt20241231_acc0001628280_25_008179.htm` | 602811 |
| full | 10-K | 2026-02-18 | `investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001628280_26_009043.htm` | 593782 |
| partial | 20-F | 2021-03-12 | `investor-documents/sec-edgar/20-F_20210312_rpt20201231_acc0001193125_21_078969.htm` | 30057 |
| partial | 20-F | 2022-03-11 | `investor-documents/sec-edgar/20-F_20220311_rpt20211231_acc0001193125_22_072901.htm` | 30059 |
| full | 20-F | 2023-03-10 | `investor-documents/sec-edgar/20-F_20230310_rpt20221231_acc0001628280_23_007435.htm` | 1185514 |
| full | 10-Q | 2024-05-10 | `investor-documents/sec-edgar/10-Q_20240510_rpt20240331_acc0001628280_24_022452.htm` | 189681 |
| scan | 10-Q | 2024-08-08 | `investor-documents/sec-edgar/10-Q_20240808_rpt20240630_acc0001628280_24_035823.htm` | 8056 |
| scan | 10-Q | 2024-11-07 | `investor-documents/sec-edgar/10-Q_20241107_rpt20240930_acc0001628280_24_045944.htm` | 8056 |
| full | 10-Q | 2025-05-05 | `investor-documents/sec-edgar/10-Q_20250505_rpt20250331_acc0001628280_25_022195.htm` | 185744 |
| scan | 10-Q | 2025-08-06 | `investor-documents/sec-edgar/10-Q_20250806_rpt20250630_acc0001628280_25_038362.htm` | 8056 |
| scan | 10-Q | 2025-11-05 | `investor-documents/sec-edgar/10-Q_20251105_rpt20250930_acc0001628280_25_049574.htm` | 8055 |
| full | 10-Q | 2026-04-30 | `investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001628280_26_028556.htm` | 189342 |
| scan | proxy | 2025-03-28 | `investor-documents/sec-edgar/DEF 14A_20250328_rpt20241231_acc0001628280_25_015342.htm` | 8056 |
| full | proxy | 2026-03-27 | `investor-documents/sec-edgar/DEF 14A_20260327_rpt20260327_acc0001628280_26_021560.htm` | 529500 |
| scan | 8-K | 2024-12-26 | `investor-documents/sec-edgar/8-K_20241226_rpt20241226_acc0001628280_24_052436.htm` | 3447 |
| scan | 8-K | 2024-12-30 | `investor-documents/sec-edgar/8-K_20241230_rpt20241230_acc0001628280_24_052576.htm` | 3313 |
| scan | 8-K | 2025-01-10 | `investor-documents/sec-edgar/8-K_20250110_rpt20250109_acc0001193125_25_004088.htm` | 8055 |
| scan | 8-K | 2025-02-26 | `investor-documents/sec-edgar/8-K_20250226_rpt20250226_acc0001628280_25_008174.htm` | 4774 |
| scan | 8-K | 2025-02-28 | `investor-documents/sec-edgar/8-K_20250228_rpt20250228_acc0001628280_25_009105.htm` | 7286 |
| scan | 8-K | 2025-04-17 | `investor-documents/sec-edgar/8-K_20250417_rpt20250417_acc0001628280_25_018116.htm` | 8056 |
| scan | 8-K | 2025-05-05 | `investor-documents/sec-edgar/8-K_20250505_rpt20250505_acc0001628280_25_022191.htm` | 4767 |
| scan | 8-K | 2025-05-09 | `investor-documents/sec-edgar/8-K_20250509_rpt20250509_acc0001628280_25_024227.htm` | 8056 |
| scan | 8-K | 2025-07-29 | `investor-documents/sec-edgar/8-K_20250729_rpt20250729_acc0001628280_25_036321.htm` | 3996 |
| scan | 8-K | 2025-08-06 | `investor-documents/sec-edgar/8-K_20250806_rpt20250806_acc0001628280_25_038359.htm` | 4749 |
| scan | 8-K | 2025-09-09 | `investor-documents/sec-edgar/8-K_20250909_rpt20250909_acc0000849395_25_000005.htm` | 5772 |
| scan | 8-K | 2025-09-30 | `investor-documents/sec-edgar/8-K_20250930_rpt20250930_acc0001193125_25_224165.htm` | 5284 |
| scan | 8-K | 2025-10-09 | `investor-documents/sec-edgar/8-K_20251009_rpt20251009_acc0001193125_25_235823.htm` | 7591 |
| scan | 8-K | 2025-11-05 | `investor-documents/sec-edgar/8-K_20251105_rpt20251105_acc0001628280_25_049547.htm` | 5676 |
| scan | 8-K | 2025-12-05 | `investor-documents/sec-edgar/8-K_20251205_rpt20251201_acc0001193125_25_309854.htm` | 4522 |
| scan | 8-K | 2026-02-18 | `investor-documents/sec-edgar/8-K_20260218_rpt20260218_acc0001628280_26_009032.htm` | 5677 |
| scan | 8-K | 2026-03-04 | `investor-documents/sec-edgar/8-K_20260304_rpt20260304_acc0001628280_26_014635.htm` | 4512 |
| scan | 8-K | 2026-04-30 | `investor-documents/sec-edgar/8-K_20260430_rpt20260430_acc0001628280_26_028554.htm` | 5306 |
| scan | 8-K | 2026-05-01 | `investor-documents/sec-edgar/8-K_20260501_rpt20260428_acc0001628280_26_029318.htm` | 4556 |
| scan | 8-K | 2026-05-07 | `investor-documents/sec-edgar/8-K_20260507_rpt20260507_acc0001628280_26_032325.htm` | 8055 |
| scan | 8-K | 2026-05-15 | `investor-documents/sec-edgar/8-K_20260515_rpt20260515_acc0001628280_26_035552.htm` | 8055 |
| scan | 8-K | 2026-05-21 | `investor-documents/sec-edgar/8-K_20260521_rpt20260521_acc0001628280_26_037252.htm` | 5034 |
| scan | 8-K | 2026-06-16 | `investor-documents/sec-edgar/8-K_20260616_rpt20260616_acc0001628280_26_043417.htm` | 6347 |
| scan | 8-K | 2026-06-22 | `investor-documents/sec-edgar/8-K_20260622_rpt20260621_acc0001193125_26_276686.htm` | 8056 |
| scan | 8-K | 2026-07-17 | `investor-documents/sec-edgar/8-K_20260717_rpt20260717_acc0001628280_26_048660.htm` | 8056 |
| inventory | other | 2025-03-14 | `investor-documents/sec-edgar/PRE 14A_20250314_rpt20241231_acc0001628280_25_012727.htm` | 0

## Canonical pointers (open only when needed)
- deep_dive: CRH/research/deep_dive_2026-10-06.md (sha256 sha256:420fedf1f2168de1...)
- filing_digest: CRH/research/evidence/filing_digest.md (sha256 sha256:667db70b737f409f...)
- adversarial: CRH/research/adversarial_2026-10-06.md (sha256 sha256:a149ce58e5fa7693...)
- valuation: CRH/research/valuation.json (sha256 sha256:f0112830e096f727...)
- thesis_card: CRH/research/thesis_card.json (sha256 sha256:af37d60c77fdb7f0...)
- cross_check: CRH/research/cross_check_third_party_2026-10-06.md (sha256 sha256:6b7079f81c49d5ec...)

## Excluded from this pack
- CRH/research/valuation.json (full; returns block included, open only for assumption audit)
- CRH/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
