# Agent context pack: DNN (DNN)

## Identity (stable)
- Ticker: DNN
- Company: DNN
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Denison Mines Corp. (NYSE American/TSX: **DNN**) is a Canadian uranium developer and explorer incorporated in Ontario. **[Fact]** The company files annual reports on Form 40-F as a foreign private issuer; consolidated financial statements follow IFRS. **[Fact]** At December 31, 2025 the company had **901,610,950** common shares outstanding and **CAD 465.9 million** of cash and cash equivalents per XBRL (`DNN/research/evidence/sec_companyfacts.json`). **[Fact]** Reported revenue was only **CAD 4.9 million** in FY2025 while operating activities consumed **CAD 68.1 million** of cash, consistent with a pre-production developer rather than an operating miner. **[Inference]** Economic value sits in undeveloped Athabasca Basin projects (Wheeler River is referenced in reclamation disclosures) and joint-venture interests including McClean Lake and Midwest, but the Annual Information Form and MD&A that describe resources and feasibility are **incorporated by reference** in the 40-F and are **not yet downloaded** into this ticker folder.

## Why the market might be wrong (stable)
The market may treat DNN as a levered bet on spot uranium when the binding variables are **permitting, project finance, and dilution**, not today's reactor demand headline. **[Fact]** FY2025 net loss was **CAD 217.3 million** while operating loss was **CAD 61.4 million**; the gap is dominated by fair-value losses on derivatives and financial instruments (CAD **111.4 million** derivative loss per XBRL), so trailing earnings are not informative. **[Inference]** Mispricing can come from **narrative_retail_flow**: uranium ETFs and AI-power thematics lift the group even when a single developer's FID timeline is unchanged. Predictive attribute: **development_milestone_gap** (equity prices embed production optionality faster than Canadian federal/provincial licensing and construction funding close).

## Returns (stable, percent per year)
- Base return: -3.65% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -19.9, base -8.1, bull 6.5

## Key assumptions (stable)
- Price today: **$3.5** (source: Yahoo DNN close 2026-08-21)
- Starting free cash flow per share: **$0.05** (source: [Assumption] Normalized placeholder owner-cash metric for Lawrence scenario engine; pre-FID developer reports negative operating cash flow (CAD 68M FY2025). Narrative terminal-price scenarios in deep dive remain authoritative for optionality framing.)
- Growth in years 1 through 5: **0.0%** per year (source: Wheeler River FID slips beyond 2030; equity funds burn at ~CAD 60-70M/year operating cash use; terminal price embeds modest uranium sentiment but no full project NPV)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **30 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Open questions (stable)
- Download and index AIF/MD&A exhibits (99.1-99.3) referenced in 40-F; rebuild Wheeler River NPV component.
- Confirm live price and FX at measurement date (stub is 2026-07-20).
- Review Power Zone route mismatch (registry `compounder` vs narrative `optionality`).
- Epistemic loop **BOOTSTRAP_BLOCKED**; calibration **insufficient_outcomes** (no automatic weight changes).

## Verified claims (stable, cited)
- [approved] shares_outstanding = 901610950.0 shares (source: DNN/research/evidence/sec_companyfacts.json)
- [pending] Denison Mines Corp. (NYSE American/TSX: **DNN**) is a Canadian uranium developer and explorer incorporated in Ontario. **[Fact]** The company files annual reports on Form 40-F as a foreign private issuer; consolidated financial statements follow IFRS. **[Fact]** At December 31, 2025 the company had **901,610,950** common shares outstanding and **CAD 465.9 million** of cash and cash equivalents per XBRL (`DNN/research/evidence/sec_companyfacts.json`). **[Fact]** Reported revenue was only **CAD 4.9 million** in FY2025 while operating activities consumed **CAD 68.1 million** of cash, consistent with a pre-production developer rather than an operating miner. **[Inference]** Economic value sits in undeveloped Athabasca Basin projects (Wheeler River is referenced in reclamation disclosures) and joint-venture interests including McClean Lake and Midwest, but the Annual Information Form and MD&A that describe resources and feasibility are **incorporated by reference** in the 40-F and are **not yet downloaded** into this ticker folder. (source: DNN/research/thesis_card.json)
- [assumption] Growth in years 1 through 5: **0.0%** per year (source: DNN/research/thesis_card.json)
- [assumption] Growth in years 6 through 7: **5.0%** per year (source: DNN/research/thesis_card.json)
- [assumption] Price today: **$3.5** (source: DNN/research/thesis_card.json)
- [assumption] Selling multiple in year 10: **30 times cash flow** (source: DNN/research/thesis_card.json)
- [assumption] Starting free cash flow per share: **$0.05** (source: DNN/research/thesis_card.json)
- [pending] The market may treat DNN as a levered bet on spot uranium when the binding variables are **permitting, project finance, and dilution**, not today's reactor demand headline. **[Fact]** FY2025 net loss was **CAD 217.3 million** while operating loss was **CAD 61.4 million**; the gap is dominated by fair-value losses on derivatives and financial instruments (CAD **111.4 million** derivative loss per XBRL), so trailing earnings are not informative. **[Inference]** Mispricing can come from **narrative_retail_flow**: uranium ETFs and AI-power thematics lift the group even when a single developer's FID timeline is unchanged. Predictive attribute: **development_milestone_gap** (equity prices embed production optionality faster than Canadian federal/provincial licensing and construction funding close). (source: DNN/research/thesis_card.json)
- [assumption] Time horizon: **7 years** (source: DNN/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — DNN

**Generated:** 2026-10-02  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `DNN/research/evidence/document_inventory.json`  

Documents in folder: **3** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | 40-F-cover | 2024-03-28 | `investor-documents/sec-edgar/40-F_20240328_rpt20231231_acc0001104659_24_040470.htm` | 30057 |
| full | 40-F-cover | 2025-03-28 | `investor-documents/sec-edgar/40-F_20250328_rpt20241231_acc0001104659_25_029414.htm` | 59999 |
| full | 40-F-cover | 2026-03-30 | `investor-documents/sec-edgar/40-F_20260330_rpt20251231_acc0001104659_26_036912.htm` | 60790 |

## Tier: full — extracts

### `investor-documents/sec-edgar/40-F_20260330_rpt20251231_acc0001104659_26_036912.htm`
**Keyword snippets (related party, financials, segments):**
- (Address and telephone number of registrant's principal executive offices)
- President and Chief Executive Officer
- Policy Relating to Recovery of Erroneously Awarded Compensation (incorporated by reference to Exhibit 97.1 of the Registrant's Annual Report on Form 40-F furnished to the Commission on March 28, 2024)
- Certificate of Chief Executive Officer as required by Rule 13a-14(a) or Rule 15d-14(a), pursuant to Section 302 of the Sarbanes-Oxley Act of 2002
- Certificate of Chief Executive Officer pursuant to 18 U.S.C. Section 1350, as enacted pursuant to Section 906 of the Sarbanes-Oxley Act of 2002

### `investor-documents/sec-edgar/40-F_20250328_rpt20241231_acc0001104659_25_029414.htm`
**Keyword snippets (related party, financials, segments):**
- (Address and telephone number of registrant's principal executive offices)
- Held senior positions with financial oversight, including President and Chief Executive Officer of Ontario Power Group (2019 to 2024)
- RECOVERY OF ERRONEOUSLY AWARDED COMPENSATION
- President and Chief Executive Officer
- Policy Relating to Recovery of Erroneously Awarded Compensation (incorporated by reference to Exhibit 97.1 of the Registrant's Annual Report on Form 40F furnished to the Commission on March 28, 2024)
- Certification of Chief Executive Officer as required by Rule 13a-14(a) or Rule 15d-14(a) of the Securities Exchange Act of 1934

## Tier: partial — extracts

### `investor-documents/sec-edgar/40-F_20240328_rpt20231231_acc0001104659_24_040470.htm`
**Keyword snippets (related party, financials, segments):**
- principal executive offices)
- corrections are restatements that required a recovery analysis of incentive-based compensation received by any of the registrant's
- executive officers during the relevant recovery period pursuant to &#167;240.10D-1(b). &#168;
- control. These risks, uncertainties and assumptions include, but are not limited to, those described under the section "Risk Factors"
- an evaluation, under the supervision and with the participation of its management, including the Chief Executive Officer and Chief Financial
- Report on Form 40-F. Based upon that evaluation, the Chief Executive Officer and Chief Financial Officer concluded that the Company's
- its Chief Executive Officer and Chief Financial Officer, as appropriate to allow timely decisions regarding required disclosure.
- are designed to provide reasonable assurance of achieving their objectives and, as indicated in the preceding paragraph, the Chief Executive
- assurance level, although the Chief Executive Officer and Chief Financial Officer do not expect that the disclosure controls and procedures
- that receipts and expenditures of the company are being made only in accordance with authorizations of management and directors of the
- The Company's Board of Directors has determined
- Held positions in a public company as Chairman since 2011 and President and Chief Executive Officer from 2005 to 2011.
- applies to the Company's directors, officers and employees, including the Chief Executive Officer, the Chief Financial Officer,
- the principal accounting officer or controller, persons performing similar functions and other officers, directors and employees of the
- 2023, the Company has not made any amendment to a provision of its code of ethics that applies to any of its Chief Executive Officer,
- 2023, the Company has not granted a waiver (including an implicit waiver) from a provision of its code of ethics to any of its Chief Executive
- The Company's Board of Directors (the " Board ")
- sale of common shares (or securities convertible into common shares) at a discount to officers or directors. The TSX rules require

## Canonical pointers (open only when needed)
- deep_dive: DNN/research/deep_dive_2026-08-23.md (sha256 sha256:05503c33e2e342da...)
- filing_digest: DNN/research/evidence/filing_digest.md (sha256 sha256:a48e03ca90534d88...)
- adversarial: DNN/research/adversarial_2026-08-23.md (sha256 sha256:3b7e035455088247...)
- valuation: DNN/research/valuation.json (sha256 sha256:31977a0138bfe74d...)
- thesis_card: DNN/research/thesis_card.json (sha256 sha256:e1dddcd69c009ec4...)
- cross_check: DNN/research/cross_check_third_party_2026-08-23.md (sha256 sha256:75d10097473cce19...)

## Excluded from this pack
- DNN/research/valuation.json (full; returns block included, open only for assumption audit)
- DNN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
