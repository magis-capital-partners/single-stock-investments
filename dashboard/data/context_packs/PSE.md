# Agent context pack: PSE (Philippine Stock Exchange Inc.)

## Identity (stable)
- Ticker: PSE
- Company: Philippine Stock Exchange Inc.
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
The Philippine Stock Exchange, Inc. operates the national equity market and related market infrastructure in the Philippines. **[Fact]** It earns fees on stock listings, trading (transaction fees billed at 0.005% of peso trade value), market data, depository services, and clearing through subsidiaries including Philippine Dealing System Holdings Corp. (PDSHC), Philippine Depository & Trust Corp. (PDTC), and Philippine Dealing & Exchange Corp. (PDEx) (`quarterly_report_3q_2025.pdf`). **[Fact]** FY2025 consolidated gross revenue was **PHP 2.84 billion** and net income after tax **PHP 1.22 billion**; parent-attributable earnings per share were **PHP 14.11** (`annual_report_2025.pdf`). **[Fact]** At **PHP 211.00** per share (PSE edge, 2026-06-09), the stock trades near **15 times** our **PHP 14.00** normalized owner-cash starting point.

## Why the market might be wrong (stable)
There is no dated structural discount. **[Inference]** Investors may treat the 2025 revenue step-up (gross revenue doubled year on year after PDSHC consolidation) as pure organic growth rather than a partly inorganic stack change, and may underweight the recurring **PHP 10** annual dividend (roughly **4.7%** yield at spot). **[Inference]** Conversely, the market may be right that post-consolidation scale and Philippines capital-market depth justify a mid-teens earnings multiple without a further rerating catalyst. Return is franchise earnings power at price, not a timed mispricing with a known payoff date.

## Returns (stable, percent per year)
- Base return: 14.09% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 6.1, base 12.7, bull 17.7

## Key assumptions (stable)
- Price today: **$211.0** (source: PSE edge stock data (cmpy_id=478) last traded PHP 211.00; Stooq/Yahoo unavailable for PH listing)
- Starting free cash flow per share: **$14.0** (source: FY2025 consolidated OCF PHP 1,429.6M minus capital spending PHP 204.2M, divided by 82.27M outstanding shares; ~6% haircut for PDSHC integration and FVTPL volatility (audited_financials_dec_2025.pdf, annual_report_2025.pdf))
- Cycle adjustment (starting cash): **mid** (source: FY2025 post-PDSHC consolidation treated as mid-cycle run rate; not peak 2024 pre-consolidation revenue)
- Growth in years 1 through 5: **6.0%** per year (source: Mid-cycle owner cash after PDSHC stack; listing fee amortization, PDTC/PDEx trading toll, regular PHP 10 dividend)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **15 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Confirm **PHP 211.00** spot via local broker; Stooq/Yahoo do not list PSE.PH.
- PDSHC consolidation makes YoY revenue comparisons non-obvious; verify synergy targets with management.
- Treasury **FVTPL** book (PHP 1.26B) adds earnings volatility not in owner-cash starting point haircut.
- Synthesis weights and qualitative adjustments pending human approval (`valuation.json` → `synthesis.human_approval`).

## Verified claims (stable, cited)
- [assumption] Cycle adjustment (starting cash): **mid** (source: PSE/research/thesis_card.json)
- [assumption] Growth in years 1 through 5: **6.0%** per year (source: PSE/research/thesis_card.json)
- [assumption] Growth in years 6 through 7: **5.0%** per year (source: PSE/research/thesis_card.json)
- [assumption] Price today: **$211.0** (source: PSE/research/thesis_card.json)
- [assumption] Selling multiple in year 10: **15 times cash flow** (source: PSE/research/thesis_card.json)
- [assumption] Starting free cash flow per share: **$14.0** (source: PSE/research/thesis_card.json)
- [pending] The Philippine Stock Exchange, Inc. operates the national equity market and related market infrastructure in the Philippines. **[Fact]** It earns fees on stock listings, trading (transaction fees billed at 0.005% of peso trade value), market data, depository services, and clearing through subsidiaries including Philippine Dealing System Holdings Corp. (PDSHC), Philippine Depository & Trust Corp. (PDTC), and Philippine Dealing & Exchange Corp. (PDEx) (`quarterly_report_3q_2025.pdf`). **[Fact]** FY2025 consolidated gross revenue was **PHP 2.84 billion** and net income after tax **PHP 1.22 billion**; parent-attributable earnings per share were **PHP 14.11** (`annual_report_2025.pdf`). **[Fact]** At **PHP 211.00** per share (PSE edge, 2026-06-09), the stock trades near **15 times** our **PHP 14.00** normalized owner-cash starting point. (source: PSE/research/thesis_card.json)
- [pending] There is no dated structural discount. **[Inference]** Investors may treat the 2025 revenue step-up (gross revenue doubled year on year after PDSHC consolidation) as pure organic growth rather than a partly inorganic stack change, and may underweight the recurring **PHP 10** annual dividend (roughly **4.7%** yield at spot). **[Inference]** Conversely, the market may be right that post-consolidation scale and Philippines capital-market depth justify a mid-teens earnings multiple without a further rerating catalyst. Return is franchise earnings power at price, not a timed mispricing with a known payoff date. (source: PSE/research/thesis_card.json)
- [assumption] Time horizon: **7 years** (source: PSE/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — PSE

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `PSE/research/evidence/document_inventory.json`  

Documents in folder: **5** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | annual | — | `official-reports/annual-reports/annual_report_2024.pdf` | 24030 |
| full | annual | — | `official-reports/annual-reports/annual_report_2025.pdf` | 189106 |
| partial | quarterly | — | `official-reports/quarterly-reports/audited_financials_dec_2025.pdf` | 39826 |
| full | quarterly | — | `official-reports/quarterly-reports/quarterly_report_3q_2025.pdf` | 318346 |
| inventory | other | 2026-06-18 | `third-party-analyses/vic/vic_pdf_2026-06-18_pse-vic-pdf_31c2412024.pdf` | 0 |

## Tier: full — extracts

### `official-reports/annual-reports/annual_report_2025.pdf`
**Keyword snippets (related party, financials, segments):**
- the Code subsequent to the distribution of securities under a plan confirmed by a court or the
- Total Assets 8,750,900,634 8,537,562,864
- Book Value Per Share 67.35 80.81
- Gross Revenue 2,842,603,240 1,398,089,806
- Non-Operating Income 3,008,803,631 2,234,410,218
- Net Income/(Loss) After Tax 1,223,987,746 1,207,217,494
- Net Income/(Loss) Attributable to ParentEquity Holder 1,155,790,887 1,207,217,494
- Solvency Ratio Total Assets / Total Liabilities 2.71 4.44
- Debt Ratio Total Debt/Total Assets 0.37 0.23
- Debt-to-Equity Ratio Total Debt/Total Stockholders'Equity 0.59 0.29
- Asset to Equity Ratio Total Assets / TotalStockholders' Equity 1.59 1.29
- Return on Assets Net Income / Total Assets 14% 14%
- Return on Equity Net Income / TotalStockholders' Equity 22% 18%

### `official-reports/quarterly-reports/quarterly_report_3q_2025.pdf`
**Keyword snippets (related party, financials, segments):**
- previously classified as an investment in an associate.
- notable increases in total assets, liabilities, revenues, and expenses compared to the same period in the
- Operating Revenues P2,005,478,775 P1,043,346,372 92.22
- Net Income  738,814,180 640,249,256 15.39
- For the period ended September 30, 2025, the Group reported a consolidated net income after
- in the same period last year. Operating revenues grew significantly by 92.22% or P962.13 million.
- to the decline in the fair value of  financial assets and higher interest expenses. The details are
- The increase in operating revenues of P962.13 million was primarily driven by a 10 3.42% or
- revenues. The growth in l isting-related revenues was attributable to 55 .65% or P105.19 million
- from PDTC contributed P428.41 million to the overall revenue growth.
- operations such as compensation and other related staff costs, repairs and maintenance,
-  compensation and other related staff costs - 31.77% or P337.16 million
- fair value of financial assets by 131.85% or P172.08 million, from a P130.51 million mark -to-
- recognized a P39.40 million share in the net income of PDSHC, corresponding to its 20.98%
- accounted for as an associate, and the Group no longer recognizes equity share in its net income.
- Net income* (a)
- Net income (a)
- that Philippine corporates need guidance when it comes to sustainability disclosures. A
- strategic initiative of the Exchange was to publish a guidance document on  sustainability
- reporting and disclosures. For this guidance material, which is published in PSE website, the
- Support for the Women’s Empowerment Principles (WEPs), which provides guidance to
- Launch of the Model Guidance on Sustainability for SMEs
- development of a model guidance document on SMEs’ adoption of sustainable business
- practices. On June 17, 2025, the UN SSE formally lau nched the guidance document. At the
- guidance follows the UN SSE’s four -step process for SMEs to integrate sustainability into
- sustainability reporting regulations in the Philippines, including t he 2020 Philippine Mineral
- distribution of trade-related assets of IACI in July 2016.
- been able to release the cash and securities entitlements of its Clearing Members at an average
- time of 12:05 PM, an improvement over the previous year’s average release time of 12:17 PM.
- Series, Investment Banking, Income Tax Computation and Return Preparation, Fundamentals
- For the period ended September 30, 2025, operating revenues of P2.01 billion went up by 92.22% or
- PDSHC’s revenues amounting to P876.51 million, which made up 43.70% of total operating revenues.
- In compliance with PFRS 15, l isting fees are recognized as revenue using the proportionate
- over the listed life of the companies.   Please refer to the Notes to Financial Stateme nts for
- listing revenue for the current period . Of the listing fees received during the current period

## Tier: partial — extracts

### `official-reports/annual-reports/annual_report_2024.pdf`
- *(no keyword hits; see cached full text in `research/evidence/_text/` if tier=full)*

### `official-reports/quarterly-reports/audited_financials_dec_2025.pdf`
**Keyword snippets (related party, financials, segments):**
- Please see the attached Consolidated Financial Statements with the Independent Auditor's Report as of 31 December
- The Stockholders and the Board of Directors
- Information Technology Environment Supporting the Trading-related Revenue Process
- infrastructure and IT processes.  The IT environment is key to the Group’s revenue generation and is
- relied upon for many aspects of its revenue reporting process.  We therefore considered the testing of the
- testing of the operation of the IT controls of the applications supporting the trading-related revenue
- process.  We also tested the trading-related revenue process transaction level controls.  We evaluated and
- PFRS 15, Revenue Contracts with Customers on Revenue from Listing Fees
- The Group applies PFRS 15, Revenue from Contracts with Customers, in recogni

## Canonical pointers (open only when needed)
- deep_dive: PSE/research/deep_dive_2026-06-11.md (sha256 sha256:b561f2af3538a869...)
- filing_digest: PSE/research/evidence/filing_digest.md (sha256 sha256:bf98da2c737b4316...)
- adversarial: PSE/research/adversarial_2026-06-11.md (sha256 sha256:6a35b9155bde7377...)
- valuation: PSE/research/valuation.json (sha256 sha256:cb5d69b159985702...)
- thesis_card: PSE/research/thesis_card.json (sha256 sha256:ca15b53247cd36e7...)
- cross_check: PSE/research/cross_check_third_party_2026-06-11.md (sha256 sha256:2c0f1e74ff15ac52...)

## Excluded from this pack
- PSE/research/valuation.json (full; returns block included, open only for assumption audit)
- PSE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
