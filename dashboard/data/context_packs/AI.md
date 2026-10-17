# Agent context pack: AI (AI)

## Identity (stable)
- Ticker: AI
- Company: AI
- Book: holdings
- Stance: watch
- Archetype: compounder

## What this business is (stable)
C3.ai, Inc. (NYSE: AI) sells enterprise application software for artificial intelligence: a model-driven platform used to build, deploy, and operate predictive and generative AI applications for large organizations. **[Fact]** The company reports as a single operating segment. **[Fact]** FY2026 revenue (year ended April 30, 2026) was **$227.1 million**, down from **$327.6 million** in FY2025 per XBRL-tagged filing extracts in `filing_facts_2026-08-06.json`. **[Fact]** Cash and cash equivalents were **$66.2 million** with **no reported long-term debt** at the April 30, 2026 balance sheet date on the FY2026 10-K. **[Inference]** C3.ai is an application-layer enterprise AI vendor competing with hyperscaler platforms and specialized software peers; owner economics today depend on converting large-deal pipeline into durable subscription revenue without further dilution.

## Why the market might be wrong (stable)
The market may overweight **CEO Thomas Siebel's return**, **Federal and Shell partnership headlines**, and **episodic insider purchases** while underweighting a **31% revenue decline**, an **unproven switching-cost moat** against hyperscalers, and **stock-based compensation dilution**. **[Inference]** At about **$10.82** (Yahoo close 2026-08-31 in `valuation.json`), the stock still embeds recovery in normalized owner cash that filings have not confirmed: our base case uses **$0.80 per share** starting owner cash **[Assumption]**, not spot GAAP earnings (mechanical net income tags in the filing extract conflict with loss-making history and are not used as the cash anchor). **[Inference]** The universal contract sums four non-overlapping components to roughly **$21 per share** base intrinsic value at the prior price stub; at a higher spot price, implied contract returns compress even if pipeline optionality is real. Moat durability remains the binding gate.

## Returns (stable, percent per year)
- Base return: 30.1% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 9.9, base 24.5, bull 38.8

## Key assumptions (stable)
- Price today: **$11.34** (source: Yahoo AI close 2026-10-08)
- Starting free cash flow per share: **$0.8** (source: FY2026 (ended 2026-04-30) OCF .2M less ~ growth/SBC-adjusted reinvestment [Assumption] ÷ ~137.5M shares ≈ .80/sh; XBRL tags in thousands)
- Growth in years 1 through 5: **15.0%** per year (source: [Assumption])
- Growth in years 6 through 7: **8.0%** per year (source: Scenario base)
- Selling multiple in year 10: **18 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Confirm live price vs **$10.82** stub (`human_review.live_price_confirmed: false`).
- Reconcile normalized owner cash **$0.80/sh** to FY2027 filing OCF and SBC schedule; mechanical net income tags flagged inconsistent.
- Siebel insider activity is mixed; do not promote insider tilt to base IRR without discussion.
- Clear `cycle_reserve` prospective falsifier gate (author forecast + independent review, or approved untestable disposition).
- No approved third-party sources in base IRR; SC-13G filings are context only.

## Verified claims (stable, cited)
- [verified] AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedGainBeforeTax moved 13 → 4 (-69.2%) vs comparable prior filing (source: AI/research/evidence/_text/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm.txt)
- [verified] AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedLossBeforeTax moved 9 → 80 (+788.9%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] AvailableForSaleDebtSecuritiesAmortizedCostBasis moved 1.438e+04 → 6,756 (-53.0%) vs comparable prior filing (source: AI/research/evidence/_text/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtSecurities moved 1.44e+04 → 6,760 (-53.0%) vs comparable prior filing (source: AI/research/evidence/_text/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm.txt)
- [verified] CashAndCashEquivalentsAtCarryingValue moved 1.644e+05 → 6.62e+04 (-59.7%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] CashCashEquivalentsAndAvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedGainBeforeTax moved 663 → 244 (-63.2%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] CashCashEquivalentsAndAvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedLossBeforeTax moved 140 → 292 (+108.6%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 2,788 → 9.816e+04 (+3420.8%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 4.205e+04 → 7.551e+04 (+79.6%) vs comparable prior filing (source: AI/research/evidence/_text/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 2.876e+05 → 4.709e+05 (+63.7%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 8.043e+04 → 1.333e+05 (+65.7%) vs comparable prior filing (source: AI/research/evidence/_text/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm.txt)
- [verified] DebtSecuritiesAvailableForSaleContinuousUnrealizedLossPosition12MonthsOrLongerAccumulatedLoss moved 2 → 14 (+600.0%) vs comparable prior filing (source: AI/research/evidence/_text/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — AI

**Generated:** 2026-10-09  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `AI/research/evidence/document_inventory.json`  

Documents in folder: **67** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 10-K | 2022-06-23 | `investor-documents/sec-edgar/10-K_20220623_rpt20220430_acc0001628280_22_017829.htm` | 30057 |
| partial | 10-K | 2023-06-22 | `investor-documents/sec-edgar/10-K_20230622_rpt20230430_acc0001628280_23_022983.htm` | 30057 |
| full | 10-K | 2024-06-18 | `investor-documents/sec-edgar/10-K_20240618_rpt20240430_acc0001628280_24_028786.htm` | 581737 |
| full | 10-K | 2025-06-23 | `investor-documents/sec-edgar/10-K_20250623_rpt20250430_acc0001628280_25_032604.htm` | 585211 |
| full | 10-K | 2026-06-24 | `investor-documents/sec-edgar/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm` | 585321 |
| scan | 10-Q | 2021-12-02 | `investor-documents/sec-edgar/10-Q_20211202_rpt20211031_acc0001628280_21_024342.htm` | 8056 |
| scan | 10-Q | 2022-03-03 | `investor-documents/sec-edgar/10-Q_20220303_rpt20220131_acc0001628280_22_004786.htm` | 8056 |
| scan | 10-Q | 2022-09-01 | `investor-documents/sec-edgar/10-Q_20220901_rpt20220731_acc0001628280_22_024099.htm` | 8056 |
| scan | 10-Q | 2022-12-08 | `investor-documents/sec-edgar/10-Q_20221208_rpt20221031_acc0001628280_22_031554.htm` | 8056 |
| scan | 10-Q | 2023-03-03 | `investor-documents/sec-edgar/10-Q_20230303_rpt20230131_acc0001628280_23_006164.htm` | 8056 |
| scan | 10-Q | 2023-09-07 | `investor-documents/sec-edgar/10-Q_20230907_rpt20230731_acc0001628280_23_031636.htm` | 8056 |
| scan | 10-Q | 2023-12-07 | `investor-documents/sec-edgar/10-Q_20231207_rpt20231031_acc0001628280_23_040969.htm` | 8056 |
| full | 10-Q | 2024-02-29 | `investor-documents/sec-edgar/10-Q_20240229_rpt20240131_acc0001628280_24_007744.htm` | 416105 |
| partial | 10-Q | 2024-09-05 | `investor-documents/sec-edgar/10-Q_20240905_rpt20240731_acc0001628280_24_039467.htm` | 30057 |
| partial | 10-Q | 2024-12-10 | `investor-documents/sec-edgar/10-Q_20241210_rpt20241031_acc0001628280_24_050538.htm` | 30057 |
| full | 10-Q | 2025-03-07 | `investor-documents/sec-edgar/10-Q_20250307_rpt20250131_acc0001628280_25_011069.htm` | 410278 |
| partial | 10-Q | 2025-09-09 | `investor-documents/sec-edgar/10-Q_20250909_rpt20250731_acc0001577526_25_000033.htm` | 30057 |
| partial | 10-Q | 2025-12-09 | `investor-documents/sec-edgar/10-Q_20251209_rpt20251031_acc0001577526_25_000055.htm` | 30057 |
| full | 10-Q | 2026-03-11 | `investor-documents/sec-edgar/10-Q_20260311_rpt20260131_acc0001577526_26_000024.htm` | 401182 |
| scan | proxy | 2022-08-24 | `investor-documents/sec-edgar/DEF 14A_20220824_rpt20221005_acc0001628280_22_023631.htm` | 8055 |
| scan | proxy | 2023-08-24 | `investor-documents/sec-edgar/DEF 14A_20230824_rpt20231004_acc0001628280_23_030459.htm` | 8055 |
| scan | proxy | 2024-08-22 | `investor-documents/sec-edgar/DEF 14A_20240822_rpt20241002_acc0001628280_24_038092.htm` | 8056 |
| full | proxy | 2025-08-21 | `investor-documents/sec-edgar/DEF 14A_20250821_rpt20251003_acc0001577526_25_000012.htm` | 203323 |
| scan | 8-K | 2024-04-11 | `investor-documents/sec-edgar/8-K_20240411_rpt20240409_acc0001628280_24_015673.htm` | 4204 |
| scan | 8-K | 2024-05-29 | `investor-documents/sec-edgar/8-K_20240529_rpt20240529_acc0001628280_24_025609.htm` | 4751 |
| scan | 8-K | 2024-06-25 | `investor-documents/sec-edgar/8-K_20240625_rpt20240619_acc0001628280_24_029881.htm` | 3652 |
| scan | 8-K | 2024-08-06 | `investor-documents/sec-edgar/8-K_20240806_rpt20240731_acc0001193125_24_194989.htm` | 4933 |
| scan | 8-K | 2024-09-04 | `investor-documents/sec-edgar/8-K_20240904_rpt20240904_acc0001628280_24_039310.htm` | 3636 |
| scan | 8-K | 2024-10-08 | `investor-documents/sec-edgar/8-K_20241008_rpt20241002_acc0001628280_24_042519.htm` | 4273 |
| scan | 8-K | 2024-10-09 | `investor-documents/sec-edgar/8-K_20241009_rpt20241005_acc0001628280_24_042601.htm` | 4230 |
| scan | 8-K | 2024-12-09 | `investor-documents/sec-edgar/8-K_20241209_rpt20241209_acc0001628280_24_050446.htm` | 3638 |
| scan | 8-K | 2025-02-26 | `investor-documents/sec-edgar/8-K_20250226_rpt20250226_acc0001628280_25_008139.htm` | 3638 |
| scan | 8-K | 2025-05-27 | `investor-documents/sec-edgar/8-K_20250527_rpt20250520_acc0001628280_25_027907.htm` | 4280 |
| scan | 8-K | 2025-05-28 | `investor-documents/sec-edgar/8-K_20250528_rpt20250528_acc0001628280_25_028158.htm` | 3648 |
| scan | 8-K | 2025-07-24 | `investor-documents/sec-edgar/8-K_20250724_rpt20250721_acc0001628280_25_035846.htm` | 4411 |
| scan | 8-K | 2025-08-11 | `investor-documents/sec-edgar/8-K_20250811_rpt20250808_acc0001628280_25_039359.htm` | 4055 |
| scan | 8-K | 2025-09-03 | `investor-documents/sec-edgar/8-K_20250903_rpt20250903_acc0001577526_25_000021.htm` | 3591 |
| scan | 8-K | 2025-09-05 | `investor-documents/sec-edgar/8-K_20250905_rpt20250901_acc0001577526_25_000026.htm` | 8055 |
| scan | 8-K | 2025-09-18 | `investor-documents/sec-edgar/8-K_20250918_rpt20250914_acc0001577526_25_000042.htm` | 4546 |
| scan | 8-K | 2025-10-09 | `investor-documents/sec-edgar/8-K_20251009_rpt20251003_acc0001577526_25_000045.htm` | 4217 |
| scan | 8-K | 2025-11-13 | `investor-documents/sec-edgar/8-K_20251113_rpt20251109_acc0001577526_25_000048.htm` | 5526 |
| scan | 8-K | 2025-12-03 | `investor-documents/sec-edgar/8-K_20251203_rpt20251203_acc0001577526_25_000052.htm` | 3594 |
| scan | 8-K | 2026-02-25 | `investor-documents/sec-edgar/8-K_20260225_rpt20260224_acc0001577526_26_000013.htm` | 7599 |
| scan | 8-K | 2026-03-25 | `investor-documents/sec-edgar/8-K_20260325_rpt20260324_acc0001577526_26_000034.htm` | 6432 |
| scan | 8-K | 2026-05-12 | `investor-documents/sec-edgar/8-K_20260512_rpt20260508_acc0001193125_26_218253.htm` | 7388 |
| scan | 8-K | 2026-06-03 | `investor-documents/sec-edgar/8-K_20260603_rpt20260603_acc00015775

## Canonical pointers (open only when needed)
- deep_dive: AI/research/deep_dive_2026-10-09.md (sha256 sha256:2cab048fc123b57a...)
- filing_digest: AI/research/evidence/filing_digest.md (sha256 sha256:3419c5441291d721...)
- adversarial: AI/research/adversarial_2026-10-09.md (sha256 sha256:76c3aa92912bd412...)
- valuation: AI/research/valuation.json (sha256 sha256:13ac968c048acfb7...)
- thesis_card: AI/research/thesis_card.json (sha256 sha256:ffe1956a29be8217...)
- cross_check: AI/research/cross_check_third_party_2026-10-09.md (sha256 sha256:b56909562863af06...)

## Excluded from this pack
- AI/research/valuation.json (full; returns block included, open only for assumption audit)
- AI/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
