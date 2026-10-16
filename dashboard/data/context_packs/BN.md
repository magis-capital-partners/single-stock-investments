# Agent context pack: BN (Brookfield Corporation)

## Identity (stable)
- Ticker: BN
- Company: Brookfield Corporation
- Book: holdings
- Stance: hold
- Archetype: platform

## What this business is (stable)
Brookfield Corporation is a global alternative-asset manager and owner of real-asset platforms. **[Fact]** Clients pay management and performance fees on capital deployed into infrastructure, real estate, credit, and private equity. **[Fact]** Owner economics are measured as distributable earnings, not GAAP net income. **[Fact]** Fee-bearing capital was **$672 billion** at June 30, 2026; insurance assets were **$191 billion**. **[Fact]** Trailing twelve month distributable earnings were **$6.2 billion**, or **$2.61 per share**. **[Inference]** Realizations are lumpy, so the base case grows owner cash without assuming a heroic carry year.

## Why the market might be wrong (stable)
There is **no dated Horizon Kinetics predictive attribute**. **[Inference]** The listed price (**$37.31** on 2026-09-17) sits far below Brookfield's own blended capital of **$66.64 per share** at June 30, 2026. GAAP marks on more than **$525 billion** of consolidated assets add noise. The combination with Brookfield Wealth Solutions is approved and expected to close this year, but that is a simplification path, not a known payoff date.

## Returns (stable, percent per year)
- Base return: 17.32% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 11.8, base 16.5, bull 19.9

## Key assumptions (stable)
- Price today: **$37.31** (source: Yahoo BN 2026-09-17)
- Starting free cash flow per share: **$2.61** (source: LTM distributable earnings $2.61/sh per Q2 2026 supplemental (2026-Q2-BN-Supplemental.pdf))
- Growth in years 1 through 5: **8.0%** per year (source: Fee-related earnings grew 20% in Q2; trailing twelve month distributable earnings before realizations grew 7% per share. Base keeps 8% as a conservative path versus management 15%+ distributable earnings target.)
- Growth in years 6 through 7: **6.0%** per year (source: Scenario base)
- Selling multiple in year 10: **16 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Live price moved from **$42.39** (July dive) to **$37.31**. Confirm the quote is a regular-session close, not a bad print.
- Holdings already **hold**. Math now clears the 15% band. No agent capital decision.
- Management targets 15%+ distributable-earnings growth. Base uses 8%. Raising base growth to 10% would be a human override.

## Verified claims (stable, cited)
- [approved] cash_m = 16242.0 USD millions (source: BN/research/evidence/sec_companyfacts.json)
- [approved] debt_m = 14301.0 USD millions (source: BN/research/evidence/sec_companyfacts.json)
- [approved] fee_bearing_capital_b = 614.0 USD billions (source: BN/investor-documents/ir-bn/2026-Q1-BN-Press-Release-vF.pdf)
- [approved] ltm_de_per_share = 2.54 USD_per_share (source: BN/investor-documents/ir-bn/2026-Q1-BN-Supplemental-vF-2.pdf)
- [approved] normalized_owner_earnings_m = 6014.21 USD millions (source: BN/investor-documents/ir-bn/2026-Q1-BN-Supplemental-vF-2.pdf)
- [approved] shares_outstanding = 2367800000.0 shares (source: BN/research/evidence/sec_companyfacts.json)
- [pending] Brookfield Corporation is a global alternative-asset manager and owner of real-asset platforms. **[Fact]** Clients pay management and performance fees on capital deployed into infrastructure, real estate, credit, and private equity. **[Fact]** Owner economics are measured as distributable earnings, not GAAP net income. **[Fact]** Fee-bearing capital was **$672 billion** at June 30, 2026; insurance assets were **$191 billion**. **[Fact]** Trailing twelve month distributable earnings were **$6.2 billion**, or **$2.61 per share**. **[Inference]** Realizations are lumpy, so the base case grows owner cash without assuming a heroic carry year. (source: BN/research/thesis_card.json)
- [assumption] Growth in years 1 through 5: **8.0%** per year (source: BN/research/thesis_card.json)
- [assumption] Growth in years 6 through 7: **6.0%** per year (source: BN/research/thesis_card.json)
- [assumption] Price today: **$37.31** (source: BN/research/thesis_card.json)
- [assumption] Selling multiple in year 10: **16 times cash flow** (source: BN/research/thesis_card.json)
- [assumption] Starting free cash flow per share: **$2.61** (source: BN/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — BN

**Generated:** 2026-09-17  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `BN/research/evidence/document_inventory.json`  

Documents in folder: **139** (all listed below; Tier 1–3 extracted or keyword-scanned).

**Latest earnings transcript:** `investor-documents/transcripts/undated_other_Q1_cab36868.pdf` (date unknown, tier partial).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | shareholder | — | `investor-documents/ir-bn/Q1-26-Brookfield-Letter-to-Shareholders-vF.pdf` | 31196 |
| partial | shareholder | — | `investor-documents/ir-bn/Q2-26-Brookfield-Letter-to-Shareholders.pdf` | 30644 |
| scan | transcript | — | `investor-documents/ir-bn/BN_20Q2-2026-transcript.pdf` | 8798 |
| partial | transcript | — | `investor-documents/ir-bn/bn-q1-2026-transcript.pdf` | 44034 |
| partial | transcript | — | `investor-documents/transcripts/undated_other_Q1_cab36868.pdf` | 44034 |
| partial | 40-F-cover | 2024-03-19 | `investor-documents/sec-edgar/40-F_20240319_rpt20231231_acc0001001085_24_000007.htm` | 30058 |
| full | 40-F-cover | 2025-03-24 | `investor-documents/sec-edgar/40-F_20250324_rpt20241231_acc0001001085_25_000007.htm` | 194810 |
| full | 40-F-cover | 2026-03-18 | `investor-documents/sec-edgar/40-F_20260318_rpt20251231_acc0001001085_26_000006.htm` | 193810 |
| partial | supplemental | — | `investor-documents/ir-bn/2026-Q1-BN-Supplemental-vF-2.pdf` | 36450 |
| partial | supplemental | — | `investor-documents/ir-bn/2026-Q2-BN-Supplemental.pdf` | 34968 |
| scan | presentation | — | `investor-documents/ir-bn/2022-agm-presentation-final.pdf` | 289 |
| scan | presentation | — | `investor-documents/ir-bn/2023-agm-presentation-vf.pdf` | 509 |
| scan | presentation | — | `investor-documents/ir-bn/2024-bn-agm-presentation.pdf` | 343 |
| scan | presentation | — | `investor-documents/ir-bn/bn-2025-agm-presentation.pdf` | 337 |
| scan | presentation | — | `investor-documents/ir-bn/bn-2026-agm-presentation.pdf` | 477 |
| scan | presentation | — | `investor-documents/ir-bn/bn-ir-day-presentationvf-stock-split.pdf` | 692 |
| inventory | other | — | `investor-documents/ir-bn/2022-ir-day-slides-sep12-22-updated-final-2022.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/2023-bn-investor-day.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/2024-bn-investor-day-v1.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/2026-Q1-BN-Press-Release-vF.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/2026-Q2-BN-Press-Release.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/2026-q2-bn-interim-report.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/bn-2026-q1-interim.pdf` | 0 |
| inventory | other | — | `investor-documents/ir-bn/bn-modern-slavery-statement-2025-v-website-upload.pdf` | 0 |
| inventory | other | 2018-07-31 | `third-party-analyses/activist_reports/long/DFAN14A_20180731_acc0001171843_18_005544.htm` | 0 |
| inventory | other | 2018-02-07 | `third-party-analyses/activist_reports/long/SC-13D/A_20180207_acc0000950157_18_000203.htm` | 0 |
| inventory | other | 2018-02-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20180228_acc0001140361_18_010805.htm` | 0 |
| inventory | other | 2018-03-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20180328_acc0001104659_18_020750.htm` | 0 |
| inventory | other | 2018-03-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20180328_acc0001193125_18_098187.htm` | 0 |
| inventory | other | 2018-05-02 | `third-party-analyses/activist_reports/long/SC-13D/A_20180502_acc0001104659_18_029473.htm` | 0 |
| inventory | other | 2018-05-29 | `third-party-analyses/activist_reports/long/SC-13D/A_20180529_acc0000950157_18_000569.htm` | 0 |
| inventory | other | 2018-06-06 | `third-party-analyses/activist_reports/long/SC-13D/A_20180606_acc0000950157_18_000588.htm` | 0 |
| inventory | other | 2018-06-12 | `third-party-analyses/activist_reports/long/SC-13D/A_20180612_acc0000950157_18_000608.htm` | 0 |
| inventory | other | 2018-06-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20180628_acc0001193125_18_207873.htm` | 0 |
| inventory | other | 2018-06-29 | `third-party-analyses/activist_reports/long/SC-13D/A_20180629_acc0000950157_18_000787.htm` | 0 |
| inventory | other | 2018-07-09 | `third-party-analyses/activist_reports/long/SC-13D/A_20180709_acc0001104659_18_044314.htm` | 0 |
| inventory | other | 2018-07-31 | `third-party-analyses/activist_reports/long/SC-13D/A_20180731_acc0001193125_18_233406.htm` | 0 |
| inventory | other | 2018-08-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20180828_acc0001104659_18_053974.htm` | 0 |
| inventory | other | 2018-08-30 | `third-party-analyses/activist_reports/long/SC-13D/A_20180830_acc0001193125_18_263758.htm` | 0 |
| inventory | other | 2018-09-21 | `third-party-analyses/activist_reports/long/SC-13D/A_20180921_acc0001104659_18_058046.htm` | 0 |
| inventory | other | 2018-10-10 | `third-party-analyses/activist_reports/long/SC-13D/A_20181010_acc0001104659_18_061373.htm` | 0 |
| inventory | other | 2018-11-21 | `third-party-analyses/activist_reports/long/SC-13D/A_20181121_acc0001104659_18_069607.htm` | 0 |
| inventory | other | 2019-01-03 | `third-party-analyses/activist_reports/long/SC-13D/A_20190103_acc0001140361_19_000227.htm` | 0 |
| inventory | other | 2019-01-16 | `third-party-analyses/activist_reports/long/SC-13D/A_20190116_acc0001193125_19_010679.htm` | 0 |
| inventory | other | 2019-02-28 | `third-party-analyses/activist_reports/long/SC-13D/A_20190228_acc0001140361_19_004047.htm` | 0 |
| inventory | other | 2019-05-03 | `third-party-analyses/activist_reports/long/SC-13D/A_20190503_acc0001104659_19_026831.htm` | 0 |
| inventory | other | 2019-05-13 | `third-party-analyses/activist_reports/long/SC-13D/A_20190513_acc0001104659_19_028706.htm` | 0 |
| inventory | other | 2019-05-20 | `third-party-analyses/activist

## Canonical pointers (open only when needed)
- deep_dive: BN/research/deep_dive_2026-09-17.md (sha256 sha256:4c7e3457cdc28ea1...)
- filing_digest: BN/research/evidence/filing_digest.md (sha256 sha256:99970ca95e73194a...)
- adversarial: BN/research/adversarial_2026-09-17.md (sha256 sha256:f7b5b9c24d0dadab...)
- valuation: BN/research/valuation.json (sha256 sha256:07718b0103c6975d...)
- thesis_card: BN/research/thesis_card.json (sha256 sha256:fdd6ea87a9c5717f...)
- cross_check: BN/research/cross_check_third_party_2026-09-17.md (sha256 sha256:0c6929181ed7879c...)

## Excluded from this pack
- BN/research/valuation.json (full; returns block included, open only for assumption audit)
- BN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
