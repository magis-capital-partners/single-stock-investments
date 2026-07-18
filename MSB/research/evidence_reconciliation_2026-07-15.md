# MSB valuation evidence reconciliation — 2026-07-15

## Scope and sources

This reconciliation tests the royalty stream, legal option and trust net assets against Mesabi Trust's primary filings. Sources: [2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131.htm), [2026 Annual Report, Exhibit 13](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131xex13.htm), the June 12, 2026 Form 10-Q, the July 14, 2026 distribution 8-K, local exhibits under `MSB/investor-documents/sec-edgar/`, and text extracts under `MSB/research/evidence/_text/`.

### July 18, 2026 primary-evidence refresh

- The April 30, 2026 Form 10-Q reports quarterly royalty income of **$2.078 million**, net income of **$1.087 million / $0.0829 per unit**, royalties received of **$1.625 million**, and a **$0.24** declared distribution. The comparable 2025 quarter reported $4.349 million of royalty income and $0.2768 of net income per unit.
- April 30, 2026 cash was **$20.285 million** and the unallocated reserve was **$18.342 million**, or about **$1.398 per unit**, down from $20.403 million / $1.555 per unit at January 31. The existing $1/$2/$3 cash-claim range still brackets both disclosed observations.
- The July 14, 2026 8-K declares only **$0.05 per unit**, versus $0.12 in the comparable prior-year period. The trustees cite the lower April royalty payment and the absence of any bonus royalty; they also state that they have received no specific update on 2026 Northshore production, sales, or shipments.
- The same 8-K says the second-calendar-quarter royalty report and payment are due **July 30, 2026**. That filing is now the next deterministic refresh trigger.
- The April 30 Form 10-Q still describes the September 2025 AAA arbitration as being in its early stages and supplies no claim amount, schedule, probability, or collectibility. No legal-option value is admitted to the base case.

## Facts reconciled

- The Trust has **13,120,010** units (10-K cover / April 21, 2026 unit count) and is legally limited to collecting income, paying expenses and liabilities, distributing net income, and protecting the trust estate.
- Fiscal 2026 royalties under amended lease agreements were **$15.820 million**, net income was **$13.869 million** or **$1.057 per unit**, and declared distributions were **$16.794 million** or **$1.28 per unit**. The prior year's distribution was **$6.93 per unit**, illustrating extreme variability.
- **Q1 2025 royalty report:** 457,728 tons shipped; base royalty $1,067,762; bonus royalty $1,281,315; Mesabi Land Trust payment $73,252; total payment $2,422,329 (`8-K_20250502` exhibit).
- **Q1 2026 royalty report:** 938,572 tons shipped; base royalty $1,201,501; bonus royalty $0; prior-period adjustments $243,986; Mesabi Land Trust payment $179,813; total payment $1,625,300 (`8-K_20260504` exhibit). Implied base royalty about **$1.28/ton** in Q1 2026 vs about **$2.33/ton** base and **$5.13/ton** total Mesabi royalty (ex land-trust) in Q1 2025.
- Northshore is controlled by Cleveland-Cliffs and is operated as a swing facility. Trustees report no control over production, shipments, capex, or third-party sales. The 2026 bonus threshold cited in the Q1 2026 royalty report is **$71.70 per ton**; all deemed Q1 2026 shipments were below that threshold.
- At January 31, 2026, the unallocated reserve was **$20.403 million**, including **$19.751 million** unallocated cash, or about **$1.555 per unit**.
- **Prior arbitration (resolved):** AAA award of $59,799,977 damages plus $11,288,269 pre-award interest (`8-K_20240910`); Cliffs/Northshore paid **$71,185,029** on October 4, 2024 (`8-K_20241017`), about **$5.43 per unit**, disclosed as satisfying that award (non-recurring).
- **Current arbitration (pending):** commenced September 2025 for damages and declaratory relief over the May 2022–April 2023 idle and alleged underpayment on intercompany shipments from 2023 onward (`8-K_20250926`; repeated in 2026 10-K Item 3). No claimed amount, schedule, probability, or collectible recovery is disclosed.

## Acceptance-test results

### `royalty_reserve_reconciliation` — partially_met (followups status remains **open**)

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Units, recent royalty reports (tons, base, bonus, thresholds), operator concentration, and entity-level grantor-trust tax treatment are primary-sourced. |
| source path or URL | `MSB/investor-documents/sec-edgar/8-K_20260504_exhibit_msb-20260430xex99d1.htm_acc0001104659_26_054941.htm`; `MSB/investor-documents/sec-edgar/10-Q_20260612_rpt20260430_acc0001104659_26_073470.htm`; `MSB/investor-documents/sec-edgar/8-K_20260714_exhibit_msb-20260714xex99d1.htm_acc0001104659_26_083538.htm`; `8-K_20250502` royalty exhibit; `MSB/research/evidence/_text/10-K_20260422_...htm.txt` |
| calculation | Q1 2025: $1,067,762 / 457,728 = $2.33 base $/ton; ($1,067,762+$1,281,315)/457,728 = $5.13 Mesabi royalty $/ton ex land-trust. Q1 2026: $1,201,501 / 938,572 = $1.28 base $/ton; payment / 13,120,010 = $0.124 per unit for the quarter. These are historical observations only and do **not** reproduce $30/$35/$42. |
| remaining uncertainty | Full contractual base-royalty percentage table; independently usable realized pellet prices; Cliffs/Northshore recoverable reserve and production life schedule; discount-rate and duration assumptions for the PV bridge. |
| affected valuation components | `producing_royalty_stream`, `depletion_and_concentration_reserve` |
| valuation consequence | Keep provisional $30/$35/$42 and -$5/-$3/-$1. Do not mark the producing stream audited. Security remains evidence-blocked. |
| falsifier | Northshore idles again, royalty-per-ton economics stay below the low case, distributions remain near the July 2026 $0.05 level, or a primary reserve/production disclosure shows recoverable tonnage/cadence insufficient for the low case. |
| monitoring source | July 30, 2026 quarterly royalty report; subsequent royalty-report 8-K exhibits; quarterly 10-Q; annual 10-K / Exhibit 13. |

**Why not `accepted`:** the written acceptance test requires reproducing the low/base/high bridge from primary evidence. Public filings still withhold the operator reserve/production schedule needed for that arithmetic.

### `legal_option_record` — not_met (followups status remains **open**)

| Field | Content |
|---|---|
| status | not_met |
| evidence | Prior award was paid in full ($71.185m / ~$5.43 per unit). Current September 2025 arbitration is disclosed without amount, timing, probability, or collectibility. |
| source path or URL | `MSB/investor-documents/sec-edgar/8-K_20240910_rpt20240906_acc0001558370_24_012705.htm`; `8-K_20241017` payment exhibit; `8-K_20250926`; 2026 10-K Item 3 |
| calculation | $7/unit × 13,120,010 ≈ $91.84m; $13/unit × 13,120,010 ≈ $170.56m. Neither figure appears as a disclosed claim. Prior collected award ($5.43/unit) is a different dispute and cannot be copied as the current option value. |
| remaining uncertainty | Statement of claim / damages methodology; hearing schedule; award or settlement; whether any remedy is incremental to ordinary royalty accruals. |
| affected valuation components | `arbitration_and_bonus_option` |
| valuation consequence | Base value is $0 because the new claim has no disclosed amount, timing, probability, or collectibility. Keep $13 per unit only as an unapproved high sensitivity for a separately evidenced incremental recovery. Ordinary base/bonus/internal-use royalties stay in `producing_royalty_stream`. |
| falsifier | Dismissal, adverse award, settlement below the separately modeled incremental amount, or a remedy limited to royalties already accrued in the producing stream. |
| monitoring source | 8-K litigation updates; 10-Q/10-K Item 3; any AAA award or settlement exhibit. |

**Overlap control:** producing component owns ordinary royalty and contractual bonus economics; legal option owns only incremental recovery beyond that stream.

### `trust_net_assets` — met / **accepted**

| Field | Content |
|---|---|
| status | met |
| evidence | Audited January 31, 2026 unallocated reserve $20.403m including $19.751m unallocated cash; unaudited April 30, 2026 reserve $18.342m and cash $20.285m. |
| source path or URL | 2026 Form 10-K / Annual Report Exhibit 13; `MSB/investor-documents/sec-edgar/10-Q_20260612_rpt20260430_acc0001104659_26_073470.htm` |
| updated calculation | $18.342m / 13,120,010 is approximately $1.398 per unit; the existing model range still brackets the latest disclosed reserve. |
| calculation | $20.403m / 13,120,010 ≈ $1.555 per unit, bracketed by model $1/$2/$3. |
| remaining uncertainty | Contingent legal costs or other senior liabilities could consume the reserve. |
| affected valuation components | `trust_cash_and_other_claims` |
| valuation consequence | Cash claim remains additive; does not make the security decision-ready. |
| falsifier | Material contingent legal costs or liabilities consume the unallocated reserve. |
| monitoring source | Each Form 10-Q/10-K reserve table. |

## Valuation consequence

Every material component remains valued exactly once, but the overall case remains **evidence-blocked** by reserve/depletion and legal-option evidence. The corrected provisional component sum is **$26 low / $34 base / $57 high**; the prior $41 contract base was stale because it still assigned $7 per unit to the undisclosed arbitration after the underlying valuation had reduced that base contribution to zero. At the July 17 close of **$24.40**, those provisional values imply roughly **0.9% / 4.8% / 12.9%** annualized returns over seven years, before distributions, but they are not committee-ready price targets. Primary value should remain a finite, scenario-weighted royalty-distribution curve. The cash claim is additive; the arbitration claim is separately probability-weighted; ordinary royalties cannot be counted in both. The July $0.05 distribution strengthens the downside warning and makes the July 30 royalty report mandatory before any evidence-gate upgrade.
