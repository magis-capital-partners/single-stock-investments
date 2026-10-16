# Agent context pack: TFPM (Triple Flag Precious Metals Corp.)

## Identity (stable)
- Ticker: TFPM
- Company: Triple Flag Precious Metals Corp.
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Triple Flag Precious Metals is a Toronto- and New York-listed precious metals streaming and royalty company. **[Fact]** It provides upfront capital to mine operators in exchange for a percentage of future metal production, earning cash without operating mines or funding mine-level capital spending. **[Fact]** FY2025 revenue was **$388.7 million** (+44% versus prior year); operating cash flow **$312.8 million** (+46%); the portfolio delivered **113,237** gold equivalent ounces (GEOs) against guidance of 105,000 to 115,000 (`investor-documents/sec-edgar/2025-Annual-Report.pdf` MD&A). **[Fact]** At December 31, 2025 the company had **206,531,806** common shares outstanding, an undrawn **$700 million** credit facility (accordion to **$1 billion**), and paid a **$0.23** annual dividend in U.S. dollars.

## Why the market might be wrong (stable)
The market may treat Triple Flag as a smaller Franco-Nevada proxy priced for peak commodity cash flows, underweighting the embedded portfolio growth engine. **[Inference]** FY2025 results embed elevated gold and silver prices; if metals normalize, near-term GEO guidance of **95,000 to 105,000** for 2026 sits below the **113,237** GEOs delivered in 2025, so headline growth may stall even as the asset count rises. **[Inference]** Two hundred five development and exploration royalties are not in the 2026 cash-flow path but support management's 2030 outlook of **140,000 to 150,000** GEOs. **[Inference]** The July 2025 Orogen acquisition and February 2026 Northparkes expansion funding commitment add deal-optionality that a pure commodity-beta multiple may not capture.

## Returns (stable, percent per year)
- Base return: 10.85% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 2.5, base 9.7, bull 15.1

## Key assumptions (stable)
- Price today: **$27.8** (source: Yahoo TFPM close 2026-06-11)
- Starting free cash flow per share: **$1.54** (source: FY2025 operating cash flow $312,832k / 203,618,559 weighted average shares (2025 Annual Report MD&A))
- Growth in years 1 through 5: **3.0%** per year (source: Mid-single-digit cash flow growth [Assumption] off FY2025 record; 2030 management outlook 140-150k GEOs not in base Lawrence path)
- Growth in years 6 through 7: **2.0%** per year (source: Scenario base)
- Selling multiple in year 10: **20 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Controlled-company governance and alignment (majority shareholder Triple Flag Mining Aggregator).
- CIK added to `us_ticker_config.json`; re-run download for full EDGAR 6-K set.
- No third-party sources indexed; HK 13F position noted in Royalty King screen but not in vault.
- Price and implied return pending `marvin_cloud_refresh.py` mechanical sync.

## Verified claims (stable, cited)
- [assumption] Growth in years 1 through 5: **3.0%** per year (source: TFPM/research/thesis_card.json)
- [assumption] Growth in years 6 through 7: **2.0%** per year (source: TFPM/research/thesis_card.json)
- [assumption] Price today: **$27.8** (source: TFPM/research/thesis_card.json)
- [assumption] Selling multiple in year 10: **20 times cash flow** (source: TFPM/research/thesis_card.json)
- [assumption] Starting free cash flow per share: **$1.54** (source: TFPM/research/thesis_card.json)
- [pending] The market may treat Triple Flag as a smaller Franco-Nevada proxy priced for peak commodity cash flows, underweighting the embedded portfolio growth engine. **[Inference]** FY2025 results embed elevated gold and silver prices; if metals normalize, near-term GEO guidance of **95,000 to 105,000** for 2026 sits below the **113,237** GEOs delivered in 2025, so headline growth may stall even as the asset count rises. **[Inference]** Two hundred five development and exploration royalties are not in the 2026 cash-flow path but support management's 2030 outlook of **140,000 to 150,000** GEOs. **[Inference]** The July 2025 Orogen acquisition and February 2026 Northparkes expansion funding commitment add deal-optionality that a pure commodity-beta multiple may not capture. (source: TFPM/research/thesis_card.json)
- [assumption] Time horizon: **7 years** (source: TFPM/research/thesis_card.json)
- [pending] Triple Flag Precious Metals is a Toronto- and New York-listed precious metals streaming and royalty company. **[Fact]** It provides upfront capital to mine operators in exchange for a percentage of future metal production, earning cash without operating mines or funding mine-level capital spending. **[Fact]** FY2025 revenue was **$388.7 million** (+44% versus prior year); operating cash flow **$312.8 million** (+46%); the portfolio delivered **113,237** gold equivalent ounces (GEOs) against guidance of 105,000 to 115,000 (`investor-documents/sec-edgar/2025-Annual-Report.pdf` MD&A). **[Fact]** At December 31, 2025 the company had **206,531,806** common shares outstanding, an undrawn **$700 million** credit facility (accordion to **$1 billion**), and paid a **$0.23** annual dividend in U.S. dollars. (source: TFPM/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — TFPM

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `TFPM/research/evidence/document_inventory.json`  

Documents in folder: **7** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| full | 40-F | — | `investor-documents/sec-edgar/2025-Form-40-F.pdf` | 441820 |
| full | annual | — | `investor-documents/sec-edgar/2025-Annual-Report.pdf` | 281021 |
| partial | 40-F-cover | 2024-03-28 | `investor-documents/sec-edgar/40-F_20240328_rpt20231231_acc0001104659_24_039990.htm` | 30000 |
| partial | 40-F-cover | 2025-03-28 | `investor-documents/sec-edgar/40-F_20250328_rpt20241231_acc0001558370_25_003977.htm` | 30000 |
| partial | 40-F-cover | 2026-03-27 | `investor-documents/sec-edgar/40-F_20260327_rpt20251231_acc0001104659_26_036188.htm` | 30000 |
| inventory | other | — | `investor-documents/ir-tfpm/2025-Triple-Flag-Asset-Handbook.pdf` | 0 |
| inventory | other | 2026-06-20 | `third-party-analyses/vic/vic_pdf_2026-06-20_tfpm-vic-pdf_681cce8e51.pdf` | 0 |

## Tier: full — extracts

### `investor-documents/sec-edgar/2025-Form-40-F.pdf`
**Keyword snippets (related party, financials, segments):**
- (Address and telephone number of Registrant’s principal executive offices)
- Triple Flag USA Royalties Ltd.c/o Torys LLP1114 Avenue of the Americas, 23rd FloorNew York, New York 10036(212) 880-6000
- CAUTIONARY NOTE REGARDING MINERAL RESERVE AND RESOURCE ESTIMATES
- RECOVERY OF ERRONEOUSLY AWARDED COMPENSATION
- CAUTIONARY NOTE REGARDING MINERAL RESERVE AND RESOURCE ESTIMATES 4
- RISK FACTORS 14
- SUMMARY OF MINERAL RESOURCES AND MINERAL RESERVES 40
- DIRECTORS AND OFFICERS 73
- James Lill, Director, Mining for Triple Flag and a “qualified person” under NI 43-101 has reviewed and approved the written scientific and technicaldisclosures contained in this AIF.
- We have systematically developed a long-life, low-cost, high-quality, diversified portfolio of streams and royalties providing exposure primarily to gold andsilver in the Americas and Australia.
- Streaming and Royalty Business
- Acquisition of Minera Florida Royalties (1.5% and 0.8% net smelter returns (“NSR”) royalties)
- Acquisition of Orogen Royalties Inc. (“Orogen”)
- Acquisition of 1.5% gross revenue royalty (“GRR”) on the Johnson Camp Mine
- Executive Leadership Transition
- Acquisition of Additional Tamarack Royalty
- On March 28, 2024, Triple Flag and Coeur Mining (“Coeur”) entered into a settlement agreement to resolve litigation regarding the terms of a royalty heldby Triple Flag on Coeur’s Kensington gold mine.
- Acquisition of Johnson Camp Mine Royalty
- Acquisition of Additional royalty interest in Stawell Gold Mines Pty Ltd
- Beaufor Royalty
- Acquisition of Agbaou Royalty
- RISK FACTORS
- Changes in commodity prices will affect the revenues generated from our portfolio and our profitability
- We have limited or no control over the operation of the properties in which we hold an interest and the operators’ failure to perform or decision to cease orsuspend operations will affect our revenues
- Sales of assets in respect of which we hold an interest may result in a new operator and any failure of such operator to perform could affect our revenues
- We may acquire streams, royalties or other similar interests in respect of properties that are speculative and there can be no guarantee that mineabledeposits will be discovered, developed or mined successfully
- We are exposed to counterparty and liquidity risk, and any delay or failure of counterparties to make payments will affect our revenues
- Some of the agreements governing Triple Flag’s stream and royalty interests contain terms that reduce the revenue generated from those interests upon theachievement of certain milestones
- Streams, royalties and other similar interests may be subject to buyback or buydown rights in favor of counterparties that could adversely affect therevenues generated from such assets
- Streams, royalties and other similar interests may not be honored by operators of a project
- Not all our streams, royalties and other similar interests are secured, including some of our principal streams and royalties
- Operators of mines may not be able to replace depleted Mineral Resources and Mineral Reserves, which would reduce our revenue from streams, royaltiesand other similar interests
- Increased competition for streams, royalties and other similar interests could adversely affect our ability to acquire additional streams, royalties and othersimilar interests in mineral properties
- If we expand our business beyond the acquisition of streams, royalties or other similar interests, we may face new challenges and risks which could affectour profitability, results of operations and financial condition
- Certain of our directors and officers serve or may serve as directors or officers of or in similar positions with other public companies, which could put themin a conflict of interest from time to time

### `investor-documents/sec-edgar/2025-Annual-Report.pdf`
**Keyword snippets (related party, financials, segments):**
- 9 Board of Directors
- to date, as well as share some thoughts on our outlook going forward.
- reward profile that had been demonstrated by mining royalties and
- As I look back on the past years, I am very pleased with the progress that
- ating cash flows, we also own royalties and streams on a large number
- redeploy our capital into further streams and royalties on attractive
- required to successfully undertake royalty and streaming investment
- Turning to 2025, I was very pleased with both the performance of the
- new record and in the upper half of our guidance range, and we bene-
- future years. Our long-term outlook is that the current portfolio will pro-
- forecast 2026 production at the midpoint. Beyond our 2030 outlook,
- $350 million to acquire streams and royalties

## Canonical pointers (open only when needed)
- deep_dive: TFPM/research/deep_dive_2026-06-11.md (sha256 sha256:814788010986b523...)
- filing_digest: TFPM/research/evidence/filing_digest.md (sha256 sha256:a0c12549447fd269...)
- adversarial: TFPM/research/adversarial_2026-06-11.md (sha256 sha256:8f7763afbd2633a2...)
- valuation: TFPM/research/valuation.json (sha256 sha256:1d6024e896baeb4f...)
- thesis_card: TFPM/research/thesis_card.json (sha256 sha256:744b90992349e7db...)
- cross_check: TFPM/research/cross_check_third_party_2026-06-11.md (sha256 sha256:f2d46b7b82afb9f9...)

## Excluded from this pack
- TFPM/research/valuation.json (full; returns block included, open only for assumption audit)
- TFPM/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
