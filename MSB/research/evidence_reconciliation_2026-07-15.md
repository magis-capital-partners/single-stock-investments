# MSB valuation evidence reconciliation — 2026-07-15

## Scope and sources

This reconciliation tests the royalty stream, legal option and trust net assets against Mesabi Trust's primary filings. Sources: [2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131.htm) and [2026 Annual Report, Exhibit 13](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131xex13.htm). Local filings are preserved under `MSB/investor-documents/sec-edgar/`.

## Facts reconciled

- The Trust has 13,120,010 units and is legally limited to collecting income, paying expenses and liabilities, distributing net income, and protecting the trust estate. It cannot operate or redeploy capital like a normal company.
- Fiscal 2026 royalties under amended lease agreements were $15.820 million, net income was $13.869 million or $1.057 per unit, and declared distributions were $16.794 million or $1.28 per unit. The prior year's distribution was $6.93 per unit, illustrating the stream's extreme variability.
- Northshore is controlled by Cleveland-Cliffs and is operated as a swing facility. The Trust cannot control production, shipments, capital expenditure or third-party sales. In calendar 2025, Cliffs reported only three low-volume third-party shipments to one customer, below the bonus threshold.
- The annual bonus threshold was $69.41 per ton for 2025. Bonus royalties range from 0.5% of gross proceeds just above the threshold to 3% at $10 or more above it. No bonus royalty was recorded in January 2026 because the highest relevant third-party price was below the threshold.
- At January 31, 2026, the unallocated reserve was $20.403 million, including $19.751 million of unallocated cash, $0.782 million accrued income receivable and $0.264 million contract asset, net of $0.395 million accrued expenses. That equals approximately $1.555 per unit, directly reproducing the current component base value of $2 per unit after rounding/conservatism.
- The current arbitration seeks damages and declaratory relief for the May 2022–April 2023 idle and alleged underpayment on intercompany shipments from 2023 onward. The filing does not state a claimed amount, probability, hearing date, ruling date or collectible recovery.

## Acceptance-test results

### `royalty_reserve_reconciliation` — open

Units, current royalty revenue, distributions, bonus tiers and operator concentration are reconciled. The acceptance test is not met because the public filing says geological reserve estimates, future production and pricing inputs remain controlled by Cliffs; no independently reproducible tonnage/depletion schedule supports the $30/$35/$42 per-unit producing-stream range. Required next evidence is the operator's reserve/production schedule mapped to royalty tiers and realized prices. Falsifier: Northshore remains structurally idle or independently supported recoverable tonnage/cadence is below the low case.

### `legal_option_record` — open

The legal issue and non-overlap rule are clear: only incremental damages or pricing rights belong in the $0/$7/$13 legal-option range, not ordinary royalties already in the producing stream. The acceptance test is not met because amount, timing, probability and collectibility are undisclosed. Required next evidence is the primary arbitration record or a final award/settlement. Falsifier: dismissal, adverse award, or a remedy limited to amounts already reflected in ordinary royalty accruals.

### `trust_net_assets` — accepted

The audited reserve bridge independently reproduces current net assets attributable to 13,120,010 units and distinguishes distribution payable from unallocated cash. The model's $1/$2/$3 range brackets the $1.555-per-unit audited reserve. Monitoring source: each Form 10-Q/10-K reserve table. Falsifier: material contingent legal costs or liabilities consume the reserve. This resolves only the net-asset component; it does not make the security decision-ready.

## Valuation consequence

Every material component remains valued exactly once, but the overall case remains evidence-blocked by reserve/depletion and legal-option evidence. Primary value should remain a finite, scenario-weighted royalty-distribution curve. The cash claim is additive; the arbitration claim is separately probability-weighted; ordinary royalties cannot be counted in both.
