# Agent context pack: FRMO (FRMO Corporation)

## Identity (stable)
- Ticker: FRMO
- Company: FRMO Corporation
- Book: holdings
- Stance: hold
- Archetype: holding_co

## What this business is (stable)
FRMO Corporation is a Delaware holding company affiliated with Horizon Kinetics. It does not run an operating business. **[Fact]** It owns concentrated stakes in investment partnerships, exchange infrastructure (Miami International Holdings), Horizon Kinetics Holding Corp., and smaller fund and digital-asset positions. Revenue to shareholders comes from fair-value marks on those investments, advisory royalty interests, and fund economics, not from product sales. **[Fact]** As of February 28, 2026, total assets were $919.5 million and FRMO-attributable stockholders' equity was $376.7 million, about $8.55 per share. **[Fact]** Roughly 82% of FRMO's equity sits in a single consolidated investment position ("Investment A"). The stock trades OTC with thin liquidity.

## Why the market might be wrong (stable)
The market prices FRMO like a volatile mark-to-market fund, not like a sum of parts. **[Inference]** OTC trading, fair-value earnings swings (Q3 FY2026 diluted EPS $1.89 vs a $0.54 loss a year earlier), and concentration in one line item push generalist investors away. **[Inference]** Private stakes (MIH post-IPO, HKHC, Winland, catalyst names) are likely carried below economic value in GAAP marks. Horizon Kinetics calls this a **dormant asset** case: value sits in subsidiaries and listing events, not in trailing GAAP earnings. There is no clean equity yield curve with one dated payoff; return depends on a catalyst stack over several years.

## Returns (stable, percent per year)
- Base return: 21.9% per year (annualized return)
- Scenarios (percent per year): bear 7.2, base 21.9, bull 30.1

## Key assumptions (stable)
- Price today: **$7.0** (source: Yahoo FRMO close 2026-07-20)
- GAAP book per share: **$8.55** (source: Filing equity ÷ shares)
- Payoff price (Year 5): **$18.0** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **5** (source: Model choice in valuation.json (not company guidance))
- Investment A look-through (82% of equity) uplift: **+$4.5/sh** (source: Bottom-up ~$2.00/sh from weighted holdings (holdco_uplift_explanation.md) + ~$2.50/sh slack until look-through filed. GAAP 309M/44.02M=7.02 inside book.)
- HKHC 4.42% + royalty + subsidiary marks uplift: **+$2.0/sh** (source: Incremental: +2.00/sh (~88M). GAAP 37.4M/44.02M=0.85 inside book. SSI HK gap illustrative; HUMAN REVIEW.)
- MIH/MIAX direct stake uplift: **+$0.5/sh** (source: Incremental +0.50/sh. GAAP 13.9M/44.02M=0.32; ~271k MIAX sh at ~$51; price + fund look-through)
- Winland + CMSG + small options uplift: **+$0.4/sh** (source: Incremental +0.40/sh option value; Winland 5.5M + CMSG 0.7M in/near book)

## Open questions (stable)
- Confirm live OTC price (Stooq **$6.70**, 2026-05-22)
- Extend sum-of-parts lines (MIH, HKHC, funds) with economic fair values vs GAAP
- Approve **accumulate** at discount to book; size for thin liquidity
- Resolve Nov 2025 late filing notification in INDEX

## Verified claims (stable, cited)
- [approved] net_income_m = 217837163.0 USD millions (source: FRMO/research/evidence/filing_facts_2026-07-20.json)
- [approved] shares_outstanding = 44 shares (source: FRMO/research/evidence/filing_facts_2026-07-20.json)
- [approved] stockholders_equity_m = 5.0 USD millions (source: FRMO/research/evidence/filing_facts_2026-07-20.json)
- [pending] FRMO Corporation is a Delaware holding company affiliated with Horizon Kinetics. It does not run an operating business. **[Fact]** It owns concentrated stakes in investment partnerships, exchange infrastructure (Miami International Holdings), Horizon Kinetics Holding Corp., and smaller fund and digital-asset positions. Revenue to shareholders comes from fair-value marks on those investments, advisory royalty interests, and fund economics, not from product sales. **[Fact]** As of February 28, 2026, total assets were $919.5 million and FRMO-attributable stockholders' equity was $376.7 million, about $8.55 per share. **[Fact]** Roughly 82% of FRMO's equity sits in a single consolidated investment position ("Investment A"). The stock trades OTC with thin liquidity. (source: FRMO/research/thesis_card.json)
- [assumption] GAAP book per share: **$8.55** (source: FRMO/research/thesis_card.json)
- [assumption] HKHC 4.42% + royalty + subsidiary marks uplift: **+$2.0/sh** (source: FRMO/research/thesis_card.json)
- [assumption] Horizon (years): **5** (source: FRMO/research/thesis_card.json)
- [assumption] Investment A look-through (82% of equity) uplift: **+$4.5/sh** (source: FRMO/research/thesis_card.json)
- [assumption] MIH/MIAX direct stake uplift: **+$0.5/sh** (source: FRMO/research/thesis_card.json)
- [assumption] Payoff price (Year 5): **$18.0** (source: FRMO/research/thesis_card.json)
- [assumption] Price today: **$7.0** (source: FRMO/research/thesis_card.json)
- [pending] The market prices FRMO like a volatile mark-to-market fund, not like a sum of parts. **[Inference]** OTC trading, fair-value earnings swings (Q3 FY2026 diluted EPS $1.89 vs a $0.54 loss a year earlier), and concentration in one line item push generalist investors away. **[Inference]** Private stakes (MIH post-IPO, HKHC, Winland, catalyst names) are likely carried below economic value in GAAP marks. Horizon Kinetics calls this a **dormant asset** case: value sits in subsidiaries and listing events, not in trailing GAAP earnings. There is no clean equity yield curve with one dated payoff; return depends on a catalyst stack over several years. (source: FRMO/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — FRMO

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `FRMO/research/evidence/document_inventory.json`  

Documents in folder: **42** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | annual | 2019-05-31 | `investor-documents/ir-frmo/2019-05-31_Annual_Report.pdf` | 29409 |
| partial | annual | 2020-05-31 | `investor-documents/ir-frmo/2020-05-31_Annual_Report.pdf` | 28475 |
| partial | annual | 2021-05-31 | `investor-documents/ir-frmo/2021-05-31_Annual_Report.pdf` | 30434 |
| partial | annual | 2022-05-31 | `investor-documents/ir-frmo/2022-05-31_Annual_Report.pdf` | 31444 |
| full | annual | 2023-05-31 | `investor-documents/ir-frmo/2023-05-31_Annual_Report.pdf` | 86027 |
| full | annual | 2024-05-31 | `investor-documents/ir-frmo/2024-05-31_Annual_Report.pdf` | 98312 |
| full | annual | 2025-05-31 | `investor-documents/ir-frmo/2025-05-31_Annual_Report.pdf` | 130942 |
| scan | quarterly | 2018-08-31 | `investor-documents/ir-frmo/2018-08-31_Quarterly_Report.pdf` | 4657 |
| scan | quarterly | 2018-11-30 | `investor-documents/ir-frmo/2018-11-30_Quarterly_Report.pdf` | 4703 |
| scan | quarterly | 2019-02-28 | `investor-documents/ir-frmo/2019-02-28_Quarterly_Report.pdf` | 5669 |
| scan | quarterly | 2019-08-31 | `investor-documents/ir-frmo/2019-08-31_Quarterly_Report.pdf` | 5912 |
| scan | quarterly | 2019-11-30 | `investor-documents/ir-frmo/2019-11-30_Quarterly_Report.pdf` | 5930 |
| scan | quarterly | 2020-02-29 | `investor-documents/ir-frmo/2020-02-29_Quarterly_Report.pdf` | 5985 |
| scan | quarterly | 2020-08-31 | `investor-documents/ir-frmo/2020-08-31_Quarterly_Report.pdf` | 6250 |
| scan | quarterly | 2020-11-30 | `investor-documents/ir-frmo/2020-11-30_Quarterly_Report.pdf` | 6127 |
| scan | quarterly | 2021-02-28 | `investor-documents/ir-frmo/2021-02-28_Quarterly_Report.pdf` | 6536 |
| scan | quarterly | 2021-08-31 | `investor-documents/ir-frmo/2021-08-31_Quarterly_Report.pdf` | 6459 |
| scan | quarterly | 2021-11-30 | `investor-documents/ir-frmo/2021-11-30_Quarterly_Report.pdf` | 6561 |
| scan | quarterly | 2022-02-28 | `investor-documents/ir-frmo/2022-02-28_Quarterly_Report.pdf` | 6787 |
| scan | quarterly | 2022-08-31 | `investor-documents/ir-frmo/2022-08-31_Quarterly_Report.pdf` | 6618 |
| scan | quarterly | 2022-11-30 | `investor-documents/ir-frmo/2022-11-30_Quarterly_Report.pdf` | 7360 |
| scan | quarterly | 2023-02-28 | `investor-documents/ir-frmo/2023-02-28_Quarterly_Report.pdf` | 7396 |
| scan | quarterly | 2023-08-31 | `investor-documents/ir-frmo/2023-08-31_Quarterly_Report.pdf` | 7390 |
| scan | quarterly | 2023-11-30 | `investor-documents/ir-frmo/2023-11-30_Quarterly_Report.pdf` | 7414 |
| full | quarterly | 2024-02-29 | `investor-documents/ir-frmo/2024-02-29_Quarterly_Report.pdf` | 70499 |
| scan | quarterly | 2024-08-31 | `investor-documents/ir-frmo/2024-08-31_Quarterly_Report.pdf` | 7362 |
| partial | quarterly | 2024-11-30 | `investor-documents/ir-frmo/2024-11-30_Quarterly_Report.pdf` | 29624 |
| full | quarterly | 2025-02-28 | `investor-documents/ir-frmo/2025-02-28_Quarterly_Report.pdf` | 69461 |
| partial | quarterly | 2025-08-31 | `investor-documents/ir-frmo/2025-08-31_Quarterly_Report.pdf` | 29452 |
| partial | quarterly | 2025-11-30 | `investor-documents/ir-frmo/2025-11-30_Quarterly_Report.pdf` | 29649 |
| full | quarterly | 2026-02-28 | `investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf` | 71289 |
| scan | supplemental | 2019-05-31 | `investor-documents/ir-frmo/2019-05-31_Supplemental_Information.pdf` | 9858 |
| scan | supplemental | 2020-05-31 | `investor-documents/ir-frmo/2020-05-31_Supplemental_Information.pdf` | 10088 |
| scan | supplemental | 2022-05-31 | `investor-documents/ir-frmo/2022-05-31_Supplemental_Information.pdf` | 10476 |
| scan | supplemental | 2023-05-31 | `investor-documents/ir-frmo/2023-05-31_Supplemental_Information.pdf` | 9945 |
| scan | supplemental | 2024-05-31 | `investor-documents/ir-frmo/2024-05-31_Supplemental_Information.pdf` | 6864 |
| inventory | other | 2024-05-31 | `investor-documents/ir-frmo/2024-05-31_Management_Certification.pdf` | 0 |
| inventory | other | 2025-05-31 | `investor-documents/ir-frmo/2025-05-31_Management_Certification.pdf` | 0 |
| inventory | other | 2025-11-30 | `investor-documents/ir-frmo/2025-11-30_Notification_of_Late_Filing.pdf` | 0 |
| inventory | other | 2012-01-18 | `investor-documents/sec-edgar/15-12G_20120118_rpt_acc0001144204_12_002780.htm` | 0 |
| inventory | other | 2026-06-18 | `third-party-analyses/vic/vic_pdf_2026-06-18_frmo-vic-pdf_d5e74c745b.pdf` | 0 |
| inventory | skip | 2014-11-26 | `investor-documents/sec-edgar/SC 13G_20141126_rpt_acc0001042017_14_000001.htm` | 0 |

## Tier: full — extracts

### `investor-documents/ir-frmo/2025-05-31_Annual_Report.pdf`
**Keyword snippets (related party, financials, segments):**
- Principal Executive Offices and Principal Place of Business:
- (iii) A change in the composition of the Board occurring within a two (2)-year period, as a result of which fewer than a majority of the directors are directors immediately prior to
- The address(es) of the issuer’s principal executive office:
- ☒ Check if principal executive office and principal place of business are the same address:
- such securities, issued for services. Using the tabular format below, please describe these events.
- Compensation
- (Please ensure that these descriptions are updated on the Company’s Profile on www.otcmarkest.com).
- The corporation is an intellectual capital firm identifying and managing investment strategies and business opportunities.
- LLC (“HKHA”), a company formed by Horizon and certain officers, principal stockholders and directors of the Company.  Due to the common
- control and ownership between HKHA and the Company’s principal stockholders and directors, HKHA has been consolidated

## Canonical pointers (open only when needed)
- deep_dive: FRMO/research/deep_dive_2026-07-21.md (sha256 sha256:8b2b91f41f82e8fb...)
- filing_digest: FRMO/research/evidence/filing_digest.md (sha256 sha256:3acaea5cf38372c9...)
- adversarial: FRMO/research/adversarial_2026-07-21.md (sha256 sha256:5ffbca6826612890...)
- valuation: FRMO/research/valuation.json (sha256 sha256:93b429b2d4bd5161...)
- thesis_card: FRMO/research/thesis_card.json (sha256 sha256:d8af4dc511a6603c...)
- cross_check: FRMO/research/cross_check_third_party_2026-07-21.md (sha256 sha256:0536ad650d6ac7e3...)

## Excluded from this pack
- FRMO/research/valuation.json (full; returns block included, open only for assumption audit)
- FRMO/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
