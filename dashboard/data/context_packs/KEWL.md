# Agent context pack: KEWL (Keweenaw Land Association)

## Identity (stable)
- Ticker: KEWL
- Company: Keweenaw Land Association
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Keweenaw Land Association owns mineral rights on more than one million net acres in Michigan's Upper Peninsula. **[Fact]** Revenue today is mineral lease income, primarily from Highland Copper's Copperwood project leases (~$349,700 in FY2024). **[Fact]** The company is not an operator; it collects rent and royalties if lessees develop mines. **[Fact]** Book value was about $14.3 million (~$12.70 per share) at December 2024 with roughly $4 million in cash and treasuries against ~$160,000 per year operating burn. **[Fact]** In June 2024 management repurchased 51,633 shares at $27 and acquired 667,000 additional acres at roughly $1.52 per acre. The stock trades OTC with very thin volume.

## Why the market might be wrong (stable)
The market may either ignore Copperwood production royalties priced at zero in lease-only cash flow, or overpay after a move from management's $27 repurchase to much higher OTC quotes. **[Inference]** At **$59.33** (Yahoo close, 2026-07-23), roughly 4.7× book, the dormant asset (Copperwood royalties) is partially in the price. **[Inference]** OTC illiquidity and CEO-prepared statements keep the acreage option opaque to generalists. SSI framing (May 2024) used **$4/lb copper**; we scale the SSI royalty bridge to spot copper when available. Lawrence base still assumes **no production royalties** in operating cash; overlay uses **35% probability** on spot royalty math.

## Returns (stable, percent per year)
- Base return: -7.46% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -18.64, base -9.28, bull 2.39

## Key assumptions (stable)
- Price today: **$59.33** (source: Yahoo KEWL close 2026-07-23)
- GAAP book per share: **$12.7** (source: Filing equity ÷ shares)
- Payoff price (Year 7): **$30.0** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **7** (source: Model choice in valuation.json (not company guidance))
- Mineral lease run-rate capitalized uplift: **+$3.24/sh** (source: ~$365K/yr x 10.0x / shares)
- Production option (partially in price) uplift: **+$3.79/sh** (source: P=35% x spot royalty $12.2M/yr)
- Acreage + secondary lessee uplift: **+$1.0/sh** (source: Filing + option [Assumption])
- Residual to Lawrence base payoff uplift: **+$9.27/sh** (source: Tie to $30.0 path)

## Open questions (stable)
- Price refreshed: Stooq **$55.00** (2026-05-22) vs mgmt repurchase **$27** (Jun 2024)
- Verify FY2025 machine-readable financials
- Track Highland Copper Copperwood milestones

## Verified claims (stable, cited)
- [approved] shares_outstanding = 1126284 shares (source: KEWL/research/evidence/filing_facts_2026-07-20.json)
- [assumption] Acreage + secondary lessee uplift: **+$1.0/sh** (source: KEWL/research/thesis_card.json)
- [assumption] GAAP book per share: **$12.7** (source: KEWL/research/thesis_card.json)
- [assumption] Horizon (years): **7** (source: KEWL/research/thesis_card.json)
- [pending] Keweenaw Land Association owns mineral rights on more than one million net acres in Michigan's Upper Peninsula. **[Fact]** Revenue today is mineral lease income, primarily from Highland Copper's Copperwood project leases (~$349,700 in FY2024). **[Fact]** The company is not an operator; it collects rent and royalties if lessees develop mines. **[Fact]** Book value was about $14.3 million (~$12.70 per share) at December 2024 with roughly $4 million in cash and treasuries against ~$160,000 per year operating burn. **[Fact]** In June 2024 management repurchased 51,633 shares at $27 and acquired 667,000 additional acres at roughly $1.52 per acre. The stock trades OTC with very thin volume. (source: KEWL/research/thesis_card.json)
- [assumption] Mineral lease run-rate capitalized uplift: **+$3.24/sh** (source: KEWL/research/thesis_card.json)
- [assumption] Payoff price (Year 7): **$30.0** (source: KEWL/research/thesis_card.json)
- [assumption] Price today: **$59.33** (source: KEWL/research/thesis_card.json)
- [assumption] Production option (partially in price) uplift: **+$3.79/sh** (source: KEWL/research/thesis_card.json)
- [assumption] Residual to Lawrence base payoff uplift: **+$9.27/sh** (source: KEWL/research/thesis_card.json)
- [pending] The market may either ignore Copperwood production royalties priced at zero in lease-only cash flow, or overpay after a move from management's $27 repurchase to much higher OTC quotes. **[Inference]** At **$59.33** (Yahoo close, 2026-07-23), roughly 4.7× book, the dormant asset (Copperwood royalties) is partially in the price. **[Inference]** OTC illiquidity and CEO-prepared statements keep the acreage option opaque to generalists. SSI framing (May 2024) used **$4/lb copper**; we scale the SSI royalty bridge to spot copper when available. Lawrence base still assumes **no production royalties** in operating cash; overlay uses **35% probability** on spot royalty math. (source: KEWL/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — KEWL

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `KEWL/research/evidence/document_inventory.json`  

Documents in folder: **33** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | annual | 2016-12-31 | `investor-documents/ir-kewl/2016-12-31_Annual_Report.pdf` | 43640 |
| partial | annual | 2018-12-31 | `investor-documents/ir-kewl/2018-12-31_Annual_Report.pdf` | 0 |
| partial | annual | 2019-12-31 | `investor-documents/ir-kewl/2019-12-31_Annual_Report.pdf` | 25549 |
| partial | annual | 2020-12-31 | `investor-documents/ir-kewl/2020-12-31_Annual_Report.pdf` | 26779 |
| partial | annual | 2021-12-31 | `investor-documents/ir-kewl/2021-12-31_Annual_Report.pdf` | 23538 |
| partial | annual | 2022-06-30 | `investor-documents/ir-kewl/2022-06-30_Semi-Annual_Report.pdf` | 23843 |
| partial | annual | 2022-12-31 | `investor-documents/ir-kewl/2022-12-31_Annual_Report.pdf` | 48308 |
| full | annual | 2023-12-31 | `investor-documents/ir-kewl/2023-12-31_Annual_Report.pdf` | 101391 |
| partial | annual | 2024-06-30 | `investor-documents/ir-kewl/2024-06-30_Semi-Annual_Report.pdf` | 36779 |
| full | annual | 2024-12-31 | `investor-documents/ir-kewl/2024-12-31_Annual_Report.pdf` | 76186 |
| partial | annual | 2025-06-30 | `investor-documents/ir-kewl/2025-06-30_Semi-Annual_Report.pdf` | 38514 |
| full | annual | 2025-12-31 | `investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf` | 33396 |
| scan | quarterly | 2019-03-31 | `investor-documents/ir-kewl/2019-03-31_Quarterly_Report.pdf` | 0 |
| scan | quarterly | 2019-06-30 | `investor-documents/ir-kewl/2019-06-30_Quarterly_Report.pdf` | 3949 |
| full | quarterly | 2019-09-30 | `investor-documents/ir-kewl/2019-09-30_Quarterly_Report.pdf` | 24981 |
| scan | quarterly | 2020-03-31 | `investor-documents/ir-kewl/2020-03-31_Quarterly_Report.pdf` | 4721 |
| scan | quarterly | 2020-06-30 | `investor-documents/ir-kewl/2020-06-30_Quarterly_Report.pdf` | 7534 |
| full | quarterly | 2020-09-30 | `investor-documents/ir-kewl/2020-09-30_Quarterly_Report.pdf` | 25960 |
| scan | quarterly | 2021-03-31 | `investor-documents/ir-kewl/2021-03-31_Quarterly_Report.pdf` | 4588 |
| scan | quarterly | 2021-06-30 | `investor-documents/ir-kewl/2021-06-30_Quarterly_Report.pdf` | 7388 |
| full | quarterly | 2021-09-30 | `investor-documents/ir-kewl/2021-09-30_Quarterly_Report.pdf` | 25225 |
| full | proxy | 2021-11-22 | `investor-documents/ir-kewl/2021-11-22_Proxy_Statement.pdf` | 125756 |
| scan | 8-K | 2026-06-18 | `third-party-analyses/vic/vic_pdf_2026-06-18_kewl-vic-pdf_35c3c4c41a.pdf` | 9735 |
| scan | supplemental | 2021-03-31 | `investor-documents/ir-kewl/2021-03-31_Supplemental_Information.pdf` | 2460 |
| scan | supplemental | 2022-07-14 | `investor-documents/ir-kewl/2022-07-14_Supplemental_Information.pdf` | 2887 |
| scan | supplemental | 2022-07-15 | `investor-documents/ir-kewl/2022-07-15_Supplemental_Information.pdf` | 3319 |
| scan | supplemental | 2022-11-18 | `investor-documents/ir-kewl/2022-11-18_Supplemental_Information.pdf` | 9531 |
| scan | supplemental | 2024-12-31 | `investor-documents/ir-kewl/2024-12-31_Supplemental_Information.pdf` | 7226 |
| scan | supplemental | 2025-06-30 | `investor-documents/ir-kewl/2025-06-30_Supplemental_Information.pdf` | 10180 |
| inventory | other | 2019-12-31 | `investor-documents/ir-kewl/2019-12-31_Notification_of_Late_Filing.pdf` | 0 |
| inventory | other | 2022-01-28 | `investor-documents/ir-kewl/2022-01-28_Officer_Director_Affiliate_Stock_Transactions.pdf` | 0 |
| inventory | other | 2023-06-30 | `investor-documents/ir-kewl/2023-06-30_Interim_Financial_Report.pdf` | 0 |
| inventory | other | 2025-12-31 | `investor-documents/ir-kewl/2025-12-31_Management_Certification.pdf` | 0 |

## Tier: full — extracts

### `investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf`
**Keyword snippets (related party, financials, segments):**
- not limited to, a complete list of officers, directors, and service providers; outstanding shares; a business
- promptly release to the public any news or information regarding corporate events that may be material to the issuer and
- publication of such disclosure documents, the issuer shall publicly disclose such events by disseminating a news release
- within four (4) business days following their occurrence and posting such news release through an Integrated Newswire
-  Changes to the company’s shell status. Please refer to our FAQ on Shell Companies
-  Departure of directors or principal officers; election of directors; appointment of principal officers
-  Officer, director, or insider transactions in the issuer’s securities
- company’s revenues
-  Earnings releases
- (iii) A change in the composition of the Board occurring within a two (2)-year period, as a result of which fewer than a majority of the directors are directors immediately prior to
- Address of the issuer’s principal executive office:
- x Check if principal executive office and principal place of business are the same address:
- Please provide the above-referenced information for all other publicly quoted or traded securities of the issuer.
- Please provide the above-referenced information for all other classes of authorized or outstanding equity securities.
- the company. Please provide the below information for each class of the company’s equity securities, as applicable:
- such securities, issued for services. Using the tabular format below, please describe these events.
- / investment control
- Mineral leasing and mineral asset management company
- Keweenaw Properties, LLC and Keweenaw Minerals, LLC
- Mineral lessor, mineral exploration, mineral royalties, commercial property lessor
- of outstanding shares that can be owned by the Noteholder at a particular time. For purposes of this calculation, please use the current market pricing (e.g. mos

## Canonical pointers (open only when needed)
- deep_dive: KEWL/research/deep_dive_2026-07-23.md (sha256 sha256:ad8610ae88dbc758...)
- filing_digest: KEWL/research/evidence/filing_digest.md (sha256 sha256:d96d8fc87ec6b74b...)
- adversarial: KEWL/research/adversarial_2026-07-23.md (sha256 sha256:594b59b54ba66239...)
- valuation: KEWL/research/valuation.json (sha256 sha256:14e9f769f4e9418e...)
- thesis_card: KEWL/research/thesis_card.json (sha256 sha256:8719dd8bca9f47e2...)
- cross_check: KEWL/research/cross_check_third_party_2026-07-23.md (sha256 sha256:16a4ddfd56ddaa34...)

## Excluded from this pack
- KEWL/research/valuation.json (full; returns block included, open only for assumption audit)
- KEWL/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
