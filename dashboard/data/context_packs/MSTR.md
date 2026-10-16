# Agent context pack: MSTR (MicroStrategy Incorporated)

## Identity (stable)
- Ticker: MSTR
- Company: MicroStrategy Incorporated
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Strategy Inc. (NASDAQ: MSTR; formerly MicroStrategy) is a public bitcoin treasury vehicle wrapped around a legacy enterprise analytics software franchise. **[Fact]** FY2025 revenue was **$463.5 million**, mostly subscription and support for Strategy One / cloud analytics. **[Fact]** The balance sheet is dominated by bitcoin: **672,500 BTC** at fair value **$58.9 billion** at December 31, 2025, rising to **762,099 BTC** (**$64.0 billion** fair value) at March 31, 2026 per the Q1 10-Q. **[Fact]** The company funds purchases with convertible notes, preferred stock (STRK, STRF, STRD, STRC), and common equity ATM programs; long-term debt was **~$8.2 billion** and temporary equity (preferred) **~$9.0 billion** at Q1 2026. Operating cash flow from software was **$67.2 million** in FY2025 while GAAP net income swung on **$5.4 billion** of unrealized BTC marks.

## Why the market might be wrong (stable)
The market prices MSTR as a levered call on bitcoin with an embedded software annuity, not as a normalized software compounder. **[Inference]** At roughly **$390** per share (placeholder until market refresh), the stock embeds a large premium to filing look-through net asset value (~**$110** per share of GAAP equity at Q1 2026, or ~**$150** per share on a simplified BTC-minus-debt bridge). Mispricing debates are about **mNAV premium persistence**, dilution from the capital-markets flywheel, and whether spot bitcoin ETFs arbitrage away the equity wrapper. There is no dated equity yield curve; the predictive attribute is **levered digital-asset accumulation** rather than a passive royalty trust.

## Returns (stable, percent per year)
- Base return: 4.2% per year (annualized return)
- Scenarios (percent per year): bear -6.7, base 4.2, bull 11.8

## Key assumptions (stable)
- Price today: **$390.0** (source: Placeholder ~June 2026; confirm via fetch_market_inputs)
- Payoff price (Year 7): **$520** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **7** (source: Model choice in valuation.json (not company guidance))
- BTC price CAGR + net stacking per share uplift: **+$280.0/sh** (source: 6% BTC CAGR × 7yr + modest accumulation net of dilution [Assumption])
- Software terminal (12× normalized cash) uplift: **+$8.0/sh** (source: $0.65/sh × 12×)
- Partial mNAV premium vs look-through at year 7 uplift: **+$121.2/sh** (source: Tie-out to $520/sh base payoff)

## Open questions (stable)
- Confirm live **price today** and BTC spot vs Q1 measurement date after `fetch_market_inputs`.
- Governance: CEO/chair bitcoin alignment vs minority common holders (DEF 14A).
- mNAV premium and base payoff **$520/sh** are **[Assumption]**; stress dilution from outstanding converts (conversion ratios in 10-Q debt note).
- No approved third-party sources in base IRR.

## Verified claims (stable, cited)
- [verified] AccruedIncomeTaxesCurrent moved 9.5 → 1.8 (-81.0%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] CashAndCashEquivalentsAtCarryingValue moved 6.03e+04 → 2.207e+06 (+3560.5%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-Q_20260506_rpt20260331_acc0001050446_26_000031.htm.txt)
- [verified] CashCashEquivalentsAndShortTermInvestments moved 8.8 → — (removed) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect moved 2.236e+04 → 9.41e+04 (+320.8%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-Q_20260506_rpt20260331_acc0001050446_26_000031.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 1.171e+06 → 3.838e+06 (+227.9%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] ComprehensiveIncomeNetOfTax moved 4.214e+06 → 1.255e+07 (+197.7%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-Q_20260506_rpt20260331_acc0001050446_26_000031.htm.txt)
- [verified] CurrentIncomeTaxExpenseBenefit moved 238 → 6,149 (+2483.6%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] DebtInstrumentConvertibleConversionPrice1 moved 39.8 → 143.2 (+259.9%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] DeferredIncomeTaxExpenseBenefit moved 7.679e+05 → 1.684e+06 (+119.3%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] DeferredIncomeTaxesAndTaxCredits moved 7.746e+05 → 1.684e+06 (+117.4%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] DeferredTaxAssetsGross moved 1.555e+06 → 5.299e+05 (-65.9%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)
- [verified] DeferredTaxAssetsNet moved 1.555e+06 → 5.294e+05 (-66.0%) vs comparable prior filing (source: MSTR/research/evidence/_text/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm.txt)

## Filing digest excerpt (semi-stable)
# Filing digest — MSTR

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `MSTR/research/evidence/document_inventory.json`  

Documents in folder: **174** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| scan | 424B | — | `investor-documents/ir-mstr/form-424B2_03-23-2026_strategy-base-prospectus.pdf` | 4308 |
| scan | 424B | — | `investor-documents/ir-mstr/form-424B3_05-06-2026.pdf` | 7103 |
| scan | 424B | — | `investor-documents/ir-mstr/form-424B3_06-23-2026.pdf` | 9974 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_03-23-2026_mstr-annex.pdf` | 30088 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_03-23-2026_strc-annex.pdf` | 54032 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_03-23-2026_strk-annex.pdf` | 46674 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_11-04-2025_mstr-annex.pdf` | 27771 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_11-04-2025_strc-annex.pdf` | 48106 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_11-04-2025_strd-annex.pdf` | 51095 |
| partial | 424B | — | `investor-documents/ir-mstr/form-424B5_11-04-2025_strk-annex.pdf` | 42618 |
| partial | 424B | 2025-11-07 | `investor-documents/sec-edgar/424B5_20251107_rpt_acc0001193125_25_272591.htm` | 30000 |
| partial | 424B | 2026-03-23 | `investor-documents/sec-edgar/424B5_20260323_rpt_acc0001193125_26_118782.htm` | 30000 |
| partial | 424B | 2026-03-23 | `investor-documents/sec-edgar/424B5_20260323_rpt_acc0001193125_26_118796.htm` | 30000 |
| partial | 424B | 2026-03-23 | `investor-documents/sec-edgar/424B5_20260323_rpt_acc0001193125_26_118806.htm` | 29898 |
| full | 424B | 2026-06-23 | `investor-documents/sec-edgar/424B5_20260623_rpt_acc0001193125_26_279602.htm` | 27040 |
| scan | 10-K | 2022-02-16 | `investor-documents/sec-edgar/10-K_20220216_rpt20211231_acc0001564590_22_005287.htm` | 8000 |
| scan | 10-K | 2023-02-16 | `investor-documents/sec-edgar/10-K_20230216_rpt20221231_acc0001564590_23_002012.htm` | 8000 |
| full | 10-K | 2024-02-15 | `investor-documents/sec-edgar/10-K_20240215_rpt20231231_acc0000950170_24_015847.htm` | 300000 |
| full | 10-K | 2025-02-18 | `investor-documents/sec-edgar/10-K_20250218_rpt20241231_acc0000950170_25_021814.htm` | 300000 |
| full | 10-K | 2026-02-19 | `investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0001050446_26_000020.htm` | 300000 |
| scan | 10-Q | 2021-10-28 | `investor-documents/sec-edgar/10-Q_20211028_rpt20210930_acc0001564590_21_052646.htm` | 8000 |
| scan | 10-Q | 2022-05-03 | `investor-documents/sec-edgar/10-Q_20220503_rpt20220331_acc0001564590_22_017437.htm` | 8000 |
| scan | 10-Q | 2022-08-02 | `investor-documents/sec-edgar/10-Q_20220802_rpt20220630_acc0001564590_22_027479.htm` | 8000 |
| scan | 10-Q | 2022-11-01 | `investor-documents/sec-edgar/10-Q_20221101_rpt20220930_acc0001564590_22_036073.htm` | 8000 |
| scan | 10-Q | 2023-05-01 | `investor-documents/sec-edgar/10-Q_20230501_rpt20230331_acc0000950170_23_016229.htm` | 8000 |
| scan | 10-Q | 2023-08-01 | `investor-documents/sec-edgar/10-Q_20230801_rpt20230630_acc0000950170_23_036448.htm` | 8000 |
| scan | 10-Q | 2023-11-01 | `investor-documents/sec-edgar/10-Q_20231101_rpt20230930_acc0000950170_23_057418.htm` | 8000 |
| full | 10-Q | 2024-05-01 | `investor-documents/sec-edgar/10-Q_20240501_rpt20240331_acc0000950170_24_051230.htm` | 300000 |
| scan | 10-Q | 2024-08-06 | `investor-documents/sec-edgar/10-Q_20240806_rpt20240630_acc0000950170_24_091778.htm` | 8000 |
| scan | 10-Q | 2024-10-31 | `investor-documents/sec-edgar/10-Q_20241031_rpt20240930_acc0000950170_24_119263.htm` | 8000 |
| full | 10-Q | 2025-05-05 | `investor-documents/sec-edgar/10-Q_20250505_rpt20250331_acc0000950170_25_063536.htm` | 300000 |
| scan | 10-Q | 2025-08-05 | `investor-documents/sec-edgar/10-Q_20250805_rpt20250630_acc0000950170_25_102209.htm` | 8000 |
| scan | 10-Q | 2025-11-03 | `investor-documents/sec-edgar/10-Q_20251103_rpt20250930_acc0001193125_25_262568.htm` | 8000 |
| full | 10-Q | 2026-05-06 | `investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001050446_26_000031.htm` | 300000 |
| scan | proxy | 2024-04-12 | `investor-documents/sec-edgar/DEF 14A_20240412_rpt20240522_acc0001193125_24_094634.htm` | 8000 |
| scan | proxy | 2025-01-03 | `investor-documents/sec-edgar/DEF 14A_20250103_rpt20250121_acc0001140361_25_000231.htm` | 8000 |
| scan | proxy | 2025-04-28 | `investor-documents/sec-edgar/DEF 14A_20250428_rpt20250612_acc0001193125_25_100720.htm` | 8000 |
| full | proxy | 2026-04-28 | `investor-documents/sec-edgar/DEF 14A_20260428_rpt20260608_acc0001193125_26_186895.htm` | 300000 |
| scan | earnings | — | `investor-documents/ir-mstr/microstrategy-q1-2024-earnings-presentation.pdf` | 1070 |
| scan | earnings | — | `investor-documents/ir-mstr/microstrategy-q2-2024-earnings-presentation.pdf` | 1067 |
| scan | earnings | — | `investor-documents/ir-mstr/microstrategy-q3-2024-earnings-presentation.pdf` | 1069 |
| scan | earnings | — | `investor-documents/ir-mstr/microstrategy-q4-2023-earnings-presentation.pdf` | 1072 |
| scan | earnings | — | `investor-documents/ir-mstr/q1-2025-strategy-earnings-presentation.pdf` | 1180 |
| scan | earnings | — | `investor-documents/ir-mstr/q2-2025-strategy-earnings-presentation.pdf` | 1897 |
| scan | earnings | — | `investor-documents/ir-mstr/q3-2025-strategy-earnings-presentation.pdf` | 1039 |
| scan | 8-K | — | `investor-documents/ir-mstr/form-8-k-filing-2_06-15-2026.pdf` | 5826 |
| scan | 8-K | — | `investor-documents/ir-mstr/form-8-k_06-01-2026.pdf` | 6370 |
| scan | 8-K | — | `investor-documents/ir-mstr/form-8-k_06-08-2026.pdf` | 6066 |
| scan | 8-K | — | `investor-documents/ir-mstr/form-8-k_06-08-2026_filing-2.pdf` | 3402 |
| scan | 8-K | — | `investor-documents/ir-mstr/form-8-k_06-10-2026.pdf` | 5340 |
| scan | 8-K | — | `investor-d

## Canonical pointers (open only when needed)
- deep_dive: MSTR/research/deep_dive_2026-06-07.md (sha256 sha256:40e822ae3d1ecb44...)
- filing_digest: MSTR/research/evidence/filing_digest.md (sha256 sha256:3f2f6bacff1e8f02...)
- adversarial: MSTR/research/adversarial_2026-06-07.md (sha256 sha256:bd73d37107ea3fc5...)
- valuation: MSTR/research/valuation.json (sha256 sha256:f1ae4d496bcb5267...)
- thesis_card: MSTR/research/thesis_card.json (sha256 sha256:c609eb488fc5ef27...)
- cross_check: MSTR/research/cross_check_third_party_2026-06-07.md (sha256 sha256:f9c9546d55e5943d...)

## Excluded from this pack
- MSTR/research/valuation.json (full; returns block included, open only for assumption audit)
- MSTR/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
