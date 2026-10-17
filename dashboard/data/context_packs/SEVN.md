# Agent context pack: SEVN (Seven Hills Realty Trust)

## Identity (stable)
- Ticker: SEVN
- Company: Seven Hills Realty Trust
- Book: holdings
- Stance: watch
- Archetype: turnaround

## What this business is (stable)
Seven Hills Realty Trust is a commercial mortgage real estate investment trust that originates and holds first mortgage loans on middle-market transitional commercial properties across the United States. **[Fact]** As of March 31, 2026 it held 26 floating-rate loans with total commitments of $776.0 million, an average loan size of $30.0 million, financed with secured repurchase facilities from four banks. **[Fact]** The trust is externally managed by Tremont Realty Capital, a wholly owned subsidiary of The RMR Group, which also owns roughly 20% of SEVN's shares. **[Fact]** SEVN pays Tremont a base management fee of 1.5% of equity per year plus an incentive fee equal to 20% of core earnings above a 7% annual hurdle. **[Fact]**

## Why the market might be wrong (stable)
SEVN trades at $7.83 per share (2026-07-23 close), or about 0.54 times its $14.47 book value per share, a discount typical of commercial mortgage REITs during a period of broad worry about office and other transitional commercial real estate credit. **[Fact]** SEVN's own loan book does not show that stress: no realized losses through the first quarter of 2026, a weighted average loan-to-value ratio of 66%, a weighted average risk rating of 2.8 out of 5, and no loans secured by office property in central business districts. **[Fact]** In December 2025 the trust raised $65.2 million of gross proceeds in a rights offering, and as of March 31, 2026 it still held $56.6 million of cash and $44.0 million of unfunded loan commitments waiting to be invested at a current weighted average yield near 7.8%. **[Fact]** Distributable earnings per share fell to $0.24 in the first quarter of 2026, from $0.28 in the fourth quarter of 2025, purely because that new capital has not finished earning a full quarter of income yet. **[Inference]** The market appears to be pricing the temporary earnings dip and sector-wide office fear together, rather than SEVN's own underwriting.

## Returns (stable, percent per year)
- Base return: 17.65% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 5.0, base 16.2, bull 23.2

## Key assumptions (stable)
- Price today: **$7.83** (source: Yahoo SEVN close 2026-07-23)
- Starting free cash flow per share: **$0.96** (source: Q1 2026 Distributable Earnings per share $0.24 (SEVN-Q1-2026-Earnings-Presentation.pdf, p.5) annualized x4)
- Growth in years 1 through 5: **3.0%** per year (source: Rights-offering capital (cash + unfunded commitments) redeploys over roughly two years back to the $0.28/quarter run rate, then grows slowly with the floating-rate book; no realized credit losses; discount to book narrows modestly as the sector re-rates toward ~0.75-0.85x book (about 9x distributable earnings).)
- Growth in years 6 through 7: **1.0%** per year (source: Scenario base)
- Selling multiple in year 10: **9 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Confirm the base case redeployment timeline (roughly two years to the $0.28 per share run rate) against the next one to two quarters of actual results
- Approve or reject promoting the sector price-to-book discount theme in `context_overlay` beyond context-only status
- Review whether total synthesis 17.65% should remain the headline return versus Lawrence scenario base 16.2% after contract backfill
- No third-party research is indexed yet; revisit after `scan_third_party_sources.py SEVN` picks up sell-side or Substack coverage

## Verified claims (stable, cited)
- [verified] CashAndCashEquivalentsAtCarryingValue moved 7.075e+04 → 1.235e+05 (+74.5%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents moved 7.075e+04 → 1.235e+05 (+74.5%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 1.71e+04 → 5.272e+04 (+208.2%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 2.911e+04 → 6.686e+04 (+129.7%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt)
- [verified] IncomeTaxExpenseBenefit moved 33 → 14 (-57.6%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] IncomeTaxesPaidNet moved 35 → 14 (-60.0%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] IncomeTaxesPaidNet moved 64 → 11 (-82.8%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt)
- [verified] IncreaseDecreaseInAccountsPayableAndAccruedLiabilities moved 420 → 104 (-75.2%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt)
- [verified] IncreaseDecreaseInAccountsPayableAndAccruedLiabilities moved 57 → 220 (+286.0%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] NetCashProvidedByUsedInFinancingActivities moved 1.71e+04 → 2.825e+04 (+65.2%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt)
- [verified] NetCashProvidedByUsedInFinancingActivities moved 5.848e+04 → 1.106e+05 (+89.2%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)
- [verified] NetCashProvidedByUsedInInvestingActivities moved 2.126e+04 → 7.296e+04 (+243.2%) vs comparable prior filing (source: SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — SEVN

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `SEVN/research/evidence/document_inventory.json`  

Documents in folder: **157** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| full | 424B | 2025-10-30 | `investor-documents/sec-edgar/424B5_20251030_rpt_acc0001104659_25_104056.htm` | 269437 |
| partial | 10-K | 2022-02-17 | `investor-documents/sec-edgar/10-K_20220217_rpt20211231_acc0001452477_22_000013.htm` | 30000 |
| partial | 10-K | 2023-02-13 | `investor-documents/sec-edgar/10-K_20230213_rpt20221231_acc0001452477_23_000011.htm` | 30000 |
| full | 10-K | 2024-02-20 | `investor-documents/sec-edgar/10-K_20240220_rpt20231231_acc0001452477_24_000011.htm` | 300000 |
| full | 10-K | 2025-02-18 | `investor-documents/sec-edgar/10-K_20250218_rpt20241231_acc0001452477_25_000014.htm` | 300000 |
| full | 10-K | 2026-02-18 | `investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm` | 300000 |
| partial | annual | — | `investor-documents/ir-sevn/2025-SEVN-Annual-Report.pdf` | 51714 |
| partial | annual | — | `investor-documents/ir-sevn/RMRM_2020-Annual-Report_Final.PDF` | 34663 |
| full | annual | 2023-03-20 | `investor-documents/ir-sevn/SEVN-Annual-Report_2023-03-20.pdf` | 443461 |
| partial | annual | — | `investor-documents/ir-sevn/SEVN_2024_Annual-Report_FINAL.pdf` | 51772 |
| partial | annual | — | `investor-documents/ir-sevn/Seven-Hills-Realty-Trust_2023-Annual-Report.pdf` | 51432 |
| scan | 10-Q | — | `investor-documents/ir-sevn/SEVN-Q3-2024-10-Q.pdf` | 5264 |
| scan | 10-Q | 2021-11-02 | `investor-documents/sec-edgar/10-Q_20211102_rpt20210930_acc0001452477_21_000059.htm` | 8000 |
| scan | 10-Q | 2022-04-27 | `investor-documents/sec-edgar/10-Q_20220427_rpt20220331_acc0001452477_22_000022.htm` | 8000 |
| scan | 10-Q | 2022-07-27 | `investor-documents/sec-edgar/10-Q_20220727_rpt20220630_acc0001452477_22_000032.htm` | 8000 |
| scan | 10-Q | 2022-10-26 | `investor-documents/sec-edgar/10-Q_20221026_rpt20220930_acc0001452477_22_000042.htm` | 8000 |
| scan | 10-Q | 2023-04-25 | `investor-documents/sec-edgar/10-Q_20230425_rpt20230331_acc0001452477_23_000018.htm` | 8000 |
| scan | 10-Q | 2023-07-31 | `investor-documents/sec-edgar/10-Q_20230731_rpt20230630_acc0001452477_23_000027.htm` | 8000 |
| scan | 10-Q | 2023-10-31 | `investor-documents/sec-edgar/10-Q_20231031_rpt20230930_acc0001452477_23_000036.htm` | 8000 |
| full | 10-Q | 2024-04-29 | `investor-documents/sec-edgar/10-Q_20240429_rpt20240331_acc0001452477_24_000020.htm` | 109972 |
| scan | 10-Q | 2024-07-29 | `investor-documents/sec-edgar/10-Q_20240729_rpt20240630_acc0001452477_24_000029.htm` | 8000 |
| scan | 10-Q | 2024-10-28 | `investor-documents/sec-edgar/10-Q_20241028_rpt20240930_acc0001452477_24_000042.htm` | 8000 |
| full | 10-Q | 2025-04-28 | `investor-documents/sec-edgar/10-Q_20250428_rpt20250331_acc0001452477_25_000025.htm` | 113583 |
| scan | 10-Q | 2025-07-28 | `investor-documents/sec-edgar/10-Q_20250728_rpt20250630_acc0001452477_25_000044.htm` | 8000 |
| scan | 10-Q | 2025-10-27 | `investor-documents/sec-edgar/10-Q_20251027_rpt20250930_acc0001452477_25_000052.htm` | 8000 |
| full | 10-Q | 2026-04-28 | `investor-documents/sec-edgar/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm` | 115046 |
| scan | proxy | — | `investor-documents/ir-sevn/RIF_Proxy-Special-Shareholders-Meeting_022120.PDF` | 3359 |
| scan | proxy | 2023-03-21 | `investor-documents/sec-edgar/DEF 14A_20230321_rpt_acc0001104659_23_034591.htm` | 8000 |
| scan | proxy | 2024-03-20 | `investor-documents/sec-edgar/DEF 14A_20240320_rpt20240530_acc0001104659_24_036684.htm` | 8000 |
| scan | proxy | 2025-03-19 | `investor-documents/sec-edgar/DEF 14A_20250319_rpt20250528_acc0001104659_25_025566.htm` | 8000 |
| full | proxy | 2026-03-18 | `investor-documents/sec-edgar/DEF 14A_20260318_rpt20260609_acc0001104659_26_030948.htm` | 139880 |
| scan | earnings | — | `investor-documents/ir-sevn/RMRM_3.31.21_Earnings-Release-FINAL.pdf` | 7810 |
| scan | earnings | — | `investor-documents/ir-sevn/RMRM_6.30.21_Earnings-Release-FINAL.pdf` | 7704 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q1-2025-Earnings-Presentation.pdf` | 3992 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q1-2026-Earnings-Presentation.pdf` | 4215 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q3-2023-Earnings-Presentation.pdf` | 4021 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q3-2024-Earnings-Presentation.pdf` | 3881 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q3-2025-Earnings-Presentation.pdf` | 4234 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q4-2024-Earnings-Presentation.pdf` | 4069 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN-Q4-2025-Earnings-Presentation.pdf` | 4175 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_03-31-24_Earnings_Presentation.pdf` | 4022 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_03.31.22_Earnings-Release_FINAL.pdf` | 6148 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_06-30-23_Earnings_Presentation.pdf` | 3947 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_06-30-24_Earnings_Presentation.pdf` | 3923 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_06-30-25_Earnings_Presentation.pdf` | 3938 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_06.30.22_Earnings-Release-FINAL.pdf` | 7115 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_09.30.22_Earnings-Release-FINAL.pdf` | 6570 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_12-31-23_Earnings_Presentation.pdf` | 4087 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_12.31.21_Earnings-Release-FINAL-2.17.2022.pdf` | 6610 |
| scan | earnings | — | `investor-documents/ir-sevn/SEVN_12.31.22_Earnings-Release.pdf` | 8603 |
| scan | earnings | — |

## Canonical pointers (open only when needed)
- deep_dive: SEVN/research/deep_dive_2026-07-24.md (sha256 sha256:a990ba55dc835dbc...)
- filing_digest: SEVN/research/evidence/filing_digest.md (sha256 sha256:b2728eaca3e965d4...)
- adversarial: SEVN/research/adversarial_2026-07-24.md (sha256 sha256:3d1c78820c592fb0...)
- valuation: SEVN/research/valuation.json (sha256 sha256:7c40d362b1f40f27...)
- thesis_card: SEVN/research/thesis_card.json (sha256 sha256:b7e6cc86ec904469...)
- cross_check: SEVN/research/cross_check_third_party_2026-07-24.md (sha256 sha256:75ab761858fd54b2...)

## Excluded from this pack
- SEVN/research/valuation.json (full; returns block included, open only for assumption audit)
- SEVN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
