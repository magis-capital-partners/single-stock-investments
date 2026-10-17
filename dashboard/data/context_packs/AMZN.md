# Agent context pack: AMZN (Amazon.com)

## Identity (stable)
- Ticker: AMZN
- Company: Amazon.com
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Amazon.com is a global retailer and technology platform. **[Fact]** Customers pay for physical and digital goods (North America and International stores), cloud infrastructure (AWS), advertising, and third-party seller services. **[Fact]** Cash to shareholders comes from operating cash flow after capital spending on logistics and data centers, not from a single product line. **[Fact]** FY2025 net sales were **$716.9 billion** (+12%); Q1 2026 net sales **$181.5 billion** (+17%). **[Fact]** AWS is the profit engine: Q1 2026 AWS sales **$37.6 billion** (+28%) with segment operating income margin **37.7%**. **[Inference]** Reported free cash flow is temporarily depressed by AI-related capital spending while operating cash flow remains large.

## Why the market might be wrong (stable)
There is **no clear dated mispricing signal** (HK predictive attribute: **none**). **[Inference]** The market prices Amazon as a growth compounder with embedded artificial intelligence optionality, not as a distressed asset. **[Inference]** The debate is whether **normalized owner cash flow** after capital spending (not trailing twelve-month free cash flow of **$1.2 billion**) supports the multiple at today's price. Return is **franchise earnings power at price**, contingent on capital spending moderating toward a **~$90 billion** sustainable run rate versus trailing purchases of **$147.3 billion**.

## Returns (stable, percent per year)
- Base return: 3.14% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -5.2, base 1.7, bull 6.9

## Key assumptions (stable)
- Price today: **$250.88** (source: Yahoo AMZN close 2026-10-02)
- Starting free cash flow per share: **$5.35** (source: Q1-26 TTM OCF \.5B less normalized capex ~\ / ~10.95B diluted shares (valuation.json))
- Growth in years 1 through 5: **9.0%** per year (source: AWS/ads/chips growth; capex moderates toward ~60% of OCF by Y5)
- Growth in years 6 through 7: **7.0%** per year (source: Scenario base)
- Selling multiple in year 10: **24 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- AI inflection FCF₀ (sensitivity): **$9.0/sh** (source: [Assumption] capex ~$90B sustainable vs $147B TTM; needs mgmt guide)
- AI inflection implied return: **16.0%** (source: `marvin_valuation.py` overlay)

## Open questions (stable)
- Confirm live price before acting on IRR.
- Hold override?** Quality compounder with sub-15% IRR at spot.
- Track quarterly capital spending versus operating cash flow; strip Anthropic gains from net income.
- Model path from **$147B** TTM capex toward **~$90B** sustainable.
- Reconcile Lawrence normalized owner cash ($5.35/sh) with contract reinvestment DCF ($11.64/sh base value).
- VIC PDF pending approval; do not blend into base IRR.

## Verified claims (stable, cited)
- [verified] AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedGainBeforeTax moved 5 → 2 (-60.0%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedLossBeforeTax moved 40 → 18 (-55.0%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] AvailableForSaleDebtSecuritiesAmortizedCostBasis moved 180 → 4,601 (+2456.1%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] AvailableForSaleDebtSecuritiesAmortizedCostBasis moved 505 → 3,452 (+583.6%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtMaturitiesAfterOneThroughFiveYearsAmortizedCost moved 5,023 → 8,217 (+63.6%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtMaturitiesSingleMaturityDateAmortizedCostBasis moved 7.952e+04 → 1.285e+05 (+61.6%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtSecurities moved 177 → 5,222 (+2850.3%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 558 → 1.242e+04 (+2125.6%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 5,833 → 3.187e+04 (+446.4%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm.txt)
- [verified] DebtInstrumentFaceAmount moved 6 → 14.5 (+141.7%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm.txt)
- [verified] DebtSecuritiesAvailableForSaleRealizedGain moved 43 → 2 (-95.3%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm.txt)
- [verified] DebtSecuritiesAvailableForSaleRealizedLoss moved 341 → 67 (-80.3%) vs comparable prior filing (source: AMZN/research/evidence/_text/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — AMZN

**Generated:** 2026-10-09  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `AMZN/research/evidence/document_inventory.json`  

Documents in folder: **390** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 424B | 2026-03-10 | `investor-documents/sec-edgar/424B5_20260310_rpt_acc0001104659_26_025560.htm` | 30057 |
| partial | 424B | 2026-03-11 | `investor-documents/sec-edgar/424B5_20260311_rpt_acc0001104659_26_026082.htm` | 30058 |
| partial | 424B | 2026-03-12 | `investor-documents/sec-edgar/424B5_20260312_rpt_acc0001104659_26_027125.htm` | 30058 |
| partial | 424B | 2026-03-13 | `investor-documents/sec-edgar/424B5_20260313_rpt_acc0001104659_26_027669.htm` | 30058 |
| partial | 424B | 2026-06-08 | `investor-documents/sec-edgar/424B5_20260608_rpt_acc0001104659_26_071190.htm` | 30057 |
| partial | 424B | 2026-06-10 | `investor-documents/sec-edgar/424B5_20260610_rpt_acc0001104659_26_072332.htm` | 30058 |
| partial | 424B | 2026-07-07 | `investor-documents/sec-edgar/424B5_20260707_rpt_acc0001104659_26_080950.htm` | 30058 |
| full | 424B | 2026-07-08 | `investor-documents/sec-edgar/424B5_20260708_rpt_acc0001104659_26_081786.htm` | 212491 |
| full | S-1 | — | `investor-documents/ir-amzn/64aef25f-17ea-4c46-985a-814cb89f6182.pdf` | 0 |
| scan | 20-F | — | `investor-documents/ir-amzn/Webslides_Q120_4.28.20_Final.pdf` | 0 |
| scan | 20-F | — | `investor-documents/ir-amzn/Webslides_Q220_Final.pdf` | 0 |
| scan | 20-F | — | `investor-documents/ir-amzn/Webslides_Q320_Final.pdf` | 0 |
| scan | 20-F | — | `investor-documents/ir-amzn/Webslides_Q419_1.30.2020_Final.pdf` | 0 |
| full | 20-F | — | `investor-documents/ir-amzn/Webslides_Q420_Final.pdf` | 0 |
| scan | 10-K | 2022-02-04 | `investor-documents/sec-edgar/10-K_20220204_rpt20211231_acc0001018724_22_000005.htm` | 8056 |
| partial | 10-K | 2023-02-03 | `investor-documents/sec-edgar/10-K_20230203_rpt20221231_acc0001018724_23_000004.htm` | 30057 |
| full | 10-K | 2024-02-02 | `investor-documents/sec-edgar/10-K_20240202_rpt20231231_acc0001018724_24_000008.htm` | 351821 |
| full | 10-K | 2025-02-07 | `investor-documents/sec-edgar/10-K_20250207_rpt20241231_acc0001018724_25_000004.htm` | 348352 |
| full | 10-K | 2026-02-06 | `investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm` | 358775 |
| scan | annual | — | `investor-documents/ir-amzn/2001annualreport.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2002_Annual_Report_FINAL.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2004_Annual_report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2006AnnualReport.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2012-Annual-Report.PDF` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2013-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2015-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2016-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2018-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/2019-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/AMAZON-2014-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/AMZN2005AnnualReport.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/AMZN_Annual-Report-2009-_final_.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-2020-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-2021-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-2022-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-2024-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-2025-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon-com-Inc-2023-Annual-Report.pdf` | 0 |
| scan | annual | — | `investor-documents/ir-amzn/Amazon_Annual_Report_2008.pdf` | 0 |
| full | annual | 2003-04-13 | `investor-documents/ir-amzn/Annual_Report_2003041304.pdf` | 0 |
| scan | 10-Q | 2021-10-29 | `investor-documents/sec-edgar/10-Q_20211029_rpt20210930_acc0001018724_21_000028.htm` | 8056 |
| scan | 10-Q | 2022-04-29 | `investor-documents/sec-edgar/10-Q_20220429_rpt20220331_acc0001018724_22_000013.htm` | 8056 |
| scan | 10-Q | 2022-07-29 | `investor-documents/sec-edgar/10-Q_20220729_rpt20220630_acc0001018724_22_000019.htm` | 8056 |
| scan | 10-Q | 2022-10-28 | `investor-documents/sec-edgar/10-Q_20221028_rpt20220930_acc0001018724_22_000023.htm` | 8056 |
| scan | 10-Q | 2023-04-28 | `investor-documents/sec-edgar/10-Q_20230428_rpt20230331_acc0001018724_23_000008.htm` | 8056 |
| scan | 10-Q | 2023-08-04 | `investor-documents/sec-edgar/10-Q_20230804_rpt20230630_acc0001018724_23_000012.htm` | 8056 |
| scan | 10-Q | 2023-10-27 | `investor-documents/sec-edgar/10-Q_20231027_rpt20230930_acc0001018724_23_000018.htm` | 8056 |
| scan | 10-Q | 2024-05-01 | `investor-documents/sec-edgar/10-Q_20240501_rpt20240331_acc0001018724_24_000083.htm` | 8055 |
| full | 10-Q | 2024-08-02 | `investor-documents/sec-edgar/10-Q_20240802_rpt20240630_acc0001018724_24_000130.htm` | 222154 |
| scan | 10-Q | 2024-11-01 | `investor-documents/sec-edgar/10-Q_20241101_rpt20240930_acc0001018724_24_000161.htm` | 8056 |
| scan | 10-Q | 2025-05-02 | `investor-documents/sec-edgar/10-Q_20250502_rpt20250331_acc0001018724_25_000036.htm` | 8056 |
| full | 10-Q | 2025-08-01 | `investor-documents/sec-edgar/10-Q_20250801_rpt20250630_acc0001018724_25_000086.htm` | 225529 |
| scan | 10-Q | 2025-10-31 | `investor-documents/sec-edgar/10-Q_20251031_rpt20250930_acc0001018724_25_000123.htm` | 8056 |
| scan | 10-Q | 2026-04-30 | `investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm` | 8056 |
| full | 10-Q | 2026-07-31 | `invest

## Canonical pointers (open only when needed)
- deep_dive: AMZN/research/deep_dive_2026-10-03.md (sha256 sha256:be5a5b3ffdb1235c...)
- filing_digest: AMZN/research/evidence/filing_digest.md (sha256 sha256:9928f1d64c17bf3a...)
- adversarial: AMZN/research/adversarial_2026-10-03.md (sha256 sha256:e6cf4461d36733cc...)
- valuation: AMZN/research/valuation.json (sha256 sha256:9cf0647ce211035d...)
- thesis_card: AMZN/research/thesis_card.json (sha256 sha256:195202dd5a770a1a...)
- cross_check: AMZN/research/cross_check_third_party_2026-10-03.md (sha256 sha256:51ec20502eb2f34f...)

## Excluded from this pack
- AMZN/research/valuation.json (full; returns block included, open only for assumption audit)
- AMZN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
