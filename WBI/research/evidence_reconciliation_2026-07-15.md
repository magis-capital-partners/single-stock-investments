# WBI valuation evidence reconciliation — 2026-07-15

## Scope and source

This reconciliation tests the three decision-critical follow-ups against WaterBridge Infrastructure LLC's 2025 Form 10-K, filed March 16, 2026. Primary source: [SEC filing](https://www.sec.gov/Archives/edgar/data/2064947/000119312526106541/wbi-20251231.htm). The locally preserved filing is `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm`.

## Facts reconciled

- Contract duration and footprint: long-term fixed-fee contracts had a weighted-average remaining life of about 10.4 years and approximately 2.4 million dedicated acres at December 31, 2025. Seventy-one percent had an initial term of at least 15 years. The disclosed contract features include fixed per-barrel fees, acreage dedications/AMIs, MVCs for certain contracts, inflation escalators for substantially all long-term contracts, and diverted-volume fees intended to approximate or exceed the lost handling margin.
- Concentration: the top five water customers represented approximately 51% of 2025 water-related revenue. This is a real renewal and counterparty-concentration risk; the aggregate contract disclosure does not provide customer-by-customer duration, MVC, price or termination schedules.
- Asset footprint: the filing reports 2,651 operating pipeline miles, 201 operating water-handling facilities, 5.076 million bbl/day of operating handling capacity, 2.435 million dedicated acres and 6.612 million AMI acres. Delaware represented 89% of handling volumes.
- 2025 economics: adjusted EBITDA was $254.0 million, adjusted EBITDA margin was 48%, and produced-water handling volume was 1.622 million bbl/day. Operating cash flow was $159.7 million and investing cash outflow was $218.6 million. The filing does not split maintenance from growth capital by project cohort.
- Funding: year-end debt was $1.465 billion, cash was $51.5 million and working capital was positive $72.2 million. The senior unsecured notes comprise $825 million due 2030 and $600 million due 2033. The revolving facility tests interest coverage of at least 2.50x, net leverage of no more than 5.00x (5.25x temporarily after a material acquisition), and senior secured leverage of no more than 3.50x. The filing discloses $30.2 million of minimum purchase, power and royalty obligations but says actual cost can be higher with volume and price.

## Acceptance-test results

### `project_cohort_roic` — open

The filing establishes consolidated growth and capital intensity but does not disclose installed capital, utilization, EBITDA, maintenance capital and taxes by mature versus ramping project cohort. The current $3.04/$4.45/$6.00 billion core-network enterprise range and the separate $0/$3/$8 per-share growth option therefore remain analyst estimates rather than a reproducible cohort-ROIC bridge. Required next evidence is a project register with in-service dates, total capital and realized cash contribution. Falsifier: mature cohorts fail to produce after-tax cash returns above WBI's cost of capital after maintenance capital.

### `contract_quality` — open, materially narrowed

The aggregate duration, fee structure, acreage protection, MVC concept and concentration are primary-source facts. The acceptance test is not met because contracted and merchant cash flows cannot be separated by customer or asset from public disclosure, and renewal/termination rights are not quantified. Required next evidence is a contract-level schedule or management reconciliation of revenue and EBITDA covered by MVCs versus acreage dedications and merchant activity. Falsifier: protected revenue or margin is materially below the share assumed in the low case.

### `refinancing_and_funding` — open, materially narrowed

Debt amount, contractual maturities and covenant thresholds are reconciled. The acceptance test is not met because the filing does not publish actual covenant ratios/headroom or a downside schedule that funds committed growth and maintenance capital. Required next evidence is actual covenant compliance data and a 2026–2033 sources-and-uses stress bridge. Falsifier: stressed interest coverage approaches 2.50x, net leverage approaches 5.00x, or committed capital requires equity issuance.

## Valuation consequence

No component is unvalued, but the decision remains evidence-blocked. The aggregate contract facts support a duration-based infrastructure method; they do not support treating the entire EBITDA base or backlog as fully contracted. The primary method remains normalized infrastructure cash flow/enterprise value, with the growth option separately risked and the funding reserve retained.
