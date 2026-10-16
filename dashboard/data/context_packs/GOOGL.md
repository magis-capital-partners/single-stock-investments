# Agent context pack: GOOGL (Alphabet Inc.)

## Identity (stable)
- Ticker: GOOGL
- Company: Alphabet Inc.
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Alphabet Inc. owns Google (Search, YouTube, Android, Chrome) and Google Cloud. **[Fact]** Advertisers and enterprises pay for ad auctions, cloud compute, and subscriptions; consumers use free products that drive query volume and data. **[Fact]** FY2025 revenue was **$402.8B** (+15%); Q1 2026 revenue **$109.9B** (+22%). **[Fact]** Reportable segments are **Google Services**, **Google Cloud**, and **Other Bets** (Waymo, etc.), plus **Alphabet-level activities** (centralized AI R&D). **[Fact]** FY2025 consolidated operating cash flow **$125.3B**, capital spending **$52.5B**, owner free cash flow **~$72.8B**; management guides **$180-190B** capital spending in 2026. **[Inference]** Owner economics depend on Cloud return on invested capital versus the capital spending step-up and whether Search monetization holds as interfaces shift to AI.

## Why the market might be wrong (stable)
There is **no clear dated mispricing signal** (predictive attribute: **none**). **[Inference]** At **~$386**, the stock prices Cloud AI optionality and Search resilience together. **[Inference]** A single consolidated free cash flow growth rate hides **divergent segment economics**: Services throws off most cash today while Cloud and Alphabet-level spend absorb the 2026 capital guide. **[Inference]** Proof-first component math sums to **~$348 per share** base economic value versus **~$386** price, implying the market embeds higher Cloud multiples or faster capex normalization than the bounded proof schedule.

## Returns (stable, percent per year)
- Base return: 0.12% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -7.7, base 0.5, bull 4.4

## Key assumptions (stable)
- Price today: **$386.0** (source: NASDAQ ~May 26, 2026 (CNBC quote; confirm live))
- Starting free cash flow per share: **$5.85** (source: FY2025 OCF $125.3B − capex $52.5B ÷ ~12.45B diluted shares (10-K))
- Growth in years 1 through 5: **11.0%** per year (source: Cloud AI mix shift; normalize post-capex ramp)
- Growth in years 6 through 7: **8.0%** per year (source: Scenario base)
- Selling multiple in year 10: **25 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- AI inflection FCF₀ (sensitivity): **$8.0/sh** (source: [Assumption] normalized ~2028 post-capex; needs filing bridge)
- AI inflection implied return: **10.2%** (source: `marvin_valuation.py` overlay)

## Open questions (stable)
- Confirm live price and diluted share count against latest filing.
- Promote AI inflection or third-party views into base case only after human OK.
- Stance and sizing require `human_decision.json`.

## Verified claims (stable, cited)
- [verified] AccruedIncomeTaxesCurrent moved 2,905 → 523 (-82.0%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtMaturitiesWithinOneYearFairValue moved 5,151 → 1.432e+04 (+178.1%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] AvailableForSaleSecuritiesDebtMaturitiesWithinOneYearFairValue moved 6,341 → 2.674e+04 (+321.6%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)
- [verified] CashCashEquivalentsAndAvailableForSaleDebtSecuritiesAmortizedCost moved 2,217 → — (removed) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] CashCashEquivalentsAndAvailableForSaleDebtSecuritiesAmortizedCost moved 2,628 → — (removed) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)
- [verified] CashCashEquivalentsAndMarketableSecurities moved 2,217 → — (removed) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] CashCashEquivalentsAndMarketableSecurities moved 2,628 → — (removed) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 934 → 2,169 (+132.2%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)
- [verified] DebtAndEquitySecuritiesGainLoss moved 1,781 → 9,960 (+459.2%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] DebtInstrumentCarryingAmount moved 1,000 → 2,000 (+100.0%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)
- [verified] DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet moved 118 → 542 (+359.3%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm.txt)
- [verified] DebtSecuritiesAvailableForSaleAllowanceForCreditLossPeriodIncreaseDecrease moved 22 → 50 (+127.3%) vs comparable prior filing (source: GOOGL/research/evidence/_text/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — GOOGL

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `GOOGL/research/evidence/document_inventory.json`  

Documents in folder: **67** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 424B | 2026-05-05 | `investor-documents/sec-edgar/424B5_20260505_rpt_acc0001193125_26_204938.htm` | 30000 |
| partial | 424B | 2026-05-05 | `investor-documents/sec-edgar/424B5_20260505_rpt_acc0001193125_26_205120.htm` | 30000 |
| partial | 424B | 2026-05-11 | `investor-documents/sec-edgar/424B5_20260511_rpt_acc0001193125_26_215570.htm` | 30000 |
| partial | 424B | 2026-05-18 | `investor-documents/sec-edgar/424B5_20260518_rpt_acc0001193125_26_228923.htm` | 30000 |
| partial | 424B | 2026-06-02 | `investor-documents/sec-edgar/424B5_20260602_rpt_acc0001193125_26_252362.htm` | 30000 |
| partial | 424B | 2026-06-02 | `investor-documents/sec-edgar/424B5_20260602_rpt_acc0001193125_26_252374.htm` | 30000 |
| partial | 424B | 2026-06-02 | `investor-documents/sec-edgar/424B5_20260602_rpt_acc0001193125_26_252392.htm` | 30000 |
| partial | 424B | 2026-06-02 | `investor-documents/sec-edgar/424B5_20260602_rpt_acc0001193125_26_252439.htm` | 30000 |
| partial | 424B | 2026-06-04 | `investor-documents/sec-edgar/424B5_20260604_rpt_acc0001193125_26_256375.htm` | 30000 |
| partial | 424B | 2026-06-04 | `investor-documents/sec-edgar/424B5_20260604_rpt_acc0001193125_26_257690.htm` | 30000 |
| full | 424B | 2026-06-04 | `investor-documents/sec-edgar/424B5_20260604_rpt_acc0001193125_26_257702.htm` | 300000 |
| scan | 10-K | 2023-02-03 | `investor-documents/sec-edgar/10-K_20230203_rpt20221231_acc0001652044_23_000016.htm` | 8000 |
| full | 10-K | 2024-01-31 | `investor-documents/sec-edgar/10-K_20240131_rpt20231231_acc0001652044_24_000022.htm` | 300000 |
| full | 10-K | 2025-02-05 | `investor-documents/sec-edgar/10-K_20250205_rpt20241231_acc0001652044_25_000014.htm` | 300000 |
| full | 10-K | 2026-02-05 | `investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm` | 300000 |
| scan | 10-Q | 2023-04-26 | `investor-documents/sec-edgar/10-Q_20230426_rpt20230331_acc0001652044_23_000045.htm` | 8000 |
| scan | 10-Q | 2023-07-26 | `investor-documents/sec-edgar/10-Q_20230726_rpt20230630_acc0001652044_23_000070.htm` | 8000 |
| scan | 10-Q | 2023-10-25 | `investor-documents/sec-edgar/10-Q_20231025_rpt20230930_acc0001652044_23_000094.htm` | 8000 |
| full | 10-Q | 2024-04-26 | `investor-documents/sec-edgar/10-Q_20240426_rpt20240331_acc0001652044_24_000053.htm` | 188742 |
| scan | 10-Q | 2024-07-24 | `investor-documents/sec-edgar/10-Q_20240724_rpt20240630_acc0001652044_24_000079.htm` | 8000 |
| scan | 10-Q | 2024-10-30 | `investor-documents/sec-edgar/10-Q_20241030_rpt20240930_acc0001652044_24_000118.htm` | 8000 |
| full | 10-Q | 2025-04-25 | `investor-documents/sec-edgar/10-Q_20250425_rpt20250331_acc0001652044_25_000043.htm` | 195970 |
| scan | 10-Q | 2025-07-24 | `investor-documents/sec-edgar/10-Q_20250724_rpt20250630_acc0001652044_25_000062.htm` | 8000 |
| scan | 10-Q | 2025-10-30 | `investor-documents/sec-edgar/10-Q_20251030_rpt20250930_acc0001652044_25_000091.htm` | 8000 |
| full | 10-Q | 2026-04-30 | `investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm` | 225249 |
| scan | proxy | 2023-04-21 | `investor-documents/sec-edgar/DEF 14A_20230421_rpt_acc0001308179_23_000736.htm` | 8000 |
| scan | proxy | 2024-04-26 | `investor-documents/sec-edgar/DEF 14A_20240426_rpt20240607_acc0001308179_24_000612.htm` | 8000 |
| scan | proxy | 2025-04-25 | `investor-documents/sec-edgar/DEF 14A_20250425_rpt20250606_acc0001308179_25_000511.htm` | 8000 |
| full | proxy | 2026-04-24 | `investor-documents/sec-edgar/DEF 14A_20260424_rpt20260605_acc0001308179_26_000342.htm` | 300000 |
| scan | 8-K | 2024-07-23 | `investor-documents/sec-edgar/8-K_20240723_rpt20240723_acc0001652044_24_000076.htm` | 4387 |
| scan | 8-K | 2024-08-06 | `investor-documents/sec-edgar/8-K_20240806_rpt20240805_acc0001652044_24_000085.htm` | 3332 |
| scan | 8-K | 2024-09-24 | `investor-documents/sec-edgar/8-K_20240924_rpt20240924_acc0001652044_24_000097.htm` | 4405 |
| scan | 8-K | 2024-10-17 | `investor-documents/sec-edgar/8-K_20241017_rpt20241017_acc0001193125_24_238769.htm` | 3058 |
| scan | 8-K | 2024-10-29 | `investor-documents/sec-edgar/8-K_20241029_rpt20241029_acc0001652044_24_000115.htm` | 4390 |
| scan | 8-K | 2025-02-04 | `investor-documents/sec-edgar/8-K_20250204_rpt20250204_acc0001652044_25_000010.htm` | 4402 |
| scan | 8-K | 2025-03-18 | `investor-documents/sec-edgar/8-K_20250318_rpt20250318_acc0001652044_25_000027.htm` | 7154 |
| scan | 8-K | 2025-04-18 | `investor-documents/sec-edgar/8-K_20250418_rpt20250417_acc0001652044_25_000033.htm` | 3495 |
| scan | 8-K | 2025-04-24 | `investor-documents/sec-edgar/8-K_20250424_rpt20250423_acc0001652044_25_000040.htm` | 4530 |
| scan | 8-K | 2025-05-01 | `investor-documents/sec-edgar/8-K_20250501_rpt20250501_acc0001193125_25_110020.htm` | 4897 |
| scan | 8-K | 2025-05-06 | `investor-documents/sec-edgar/8-K_20250506_rpt20250506_acc0001193125_25_113864.htm` | 5190 |
| scan | 8-K | 2025-06-12 | `investor-documents/sec-edgar/8-K_20250612_rpt20250606_acc0001193125_25_139948.htm` | 8000 |
| scan | 8-K | 2025-07-18 | `investor-documents/sec-edgar/8-K_20250718_rpt20250708_acc0001193125_25_161225.htm` | 4613 |
| scan | 8-K | 2025-07-23 | `investor-documents/sec-edgar/8-K_20250723_rpt20250723_acc0001652044_25_000056.htm` | 4960 |
| scan | 8-K | 2025-09-03 | `investor-documents/sec-edgar/8-K_20250903_rpt20250902_acc0001652044_25_000067.htm` | 4132 |
| scan | 8-K | 2025-09-05 | `investor-documents/sec-edgar/8-K_20250905_rpt20250905_acc0001652044_25_000074.htm` | 4151 |
| scan | 8-K | 2025-10-29 | `investor-documents/sec-edgar/8-K_20251029_rpt20251029_acc0001652044_25_000087.htm` | 4736 |
| scan | 8-K | 2025-11

## Canonical pointers (open only when needed)
- deep_dive: GOOGL/research/deep_dive_2026-07-23.md (sha256 sha256:d4ad306f93629389...)
- filing_digest: GOOGL/research/evidence/filing_digest.md (sha256 sha256:e01cacb91458bfb0...)
- adversarial: GOOGL/research/adversarial_2026-07-23.md (sha256 sha256:c29cd93fc420ef9a...)
- valuation: GOOGL/research/valuation.json (sha256 sha256:d12c59af8fc9ac18...)
- thesis_card: GOOGL/research/thesis_card.json (sha256 sha256:50106c4abd366000...)
- cross_check: GOOGL/research/cross_check_third_party_2026-07-23.md (sha256 sha256:82d42734c89dfd08...)

## Excluded from this pack
- GOOGL/research/valuation.json (full; returns block included, open only for assumption audit)
- GOOGL/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
