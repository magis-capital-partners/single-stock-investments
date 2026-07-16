# MSB valuation evidence reconciliation — 2026-07-15

## Scope and sources

This reconciliation tests the royalty stream, legal option and trust net assets against Mesabi Trust's primary filings. Sources: [2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131.htm), [2026 Annual Report, Exhibit 13](https://www.sec.gov/Archives/edgar/data/65172/000110465926046864/msb-20260131xex13.htm), local exhibits under `MSB/investor-documents/sec-edgar/`, and text extracts under `MSB/research/evidence/_text/`.

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
| source path or URL | `MSB/investor-documents/sec-edgar/8-K_20260504_exhibit_msb-20260430xex99d1.htm_acc0001104659_26_054941.htm`; `8-K_20250502` royalty exhibit; `MSB/research/evidence/_text/10-K_20260422_...htm.txt` |
| calculation | Q1 2025: $1,067,762 / 457,728 = $2.33 base $/ton; ($1,067,762+$1,281,315)/457,728 = $5.13 Mesabi royalty $/ton ex land-trust. Q1 2026: $1,201,501 / 938,572 = $1.28 base $/ton; payment / 13,120,010 = $0.124 per unit for the quarter. These are historical observations only and do **not** reproduce $30/$35/$42. |
| remaining uncertainty | Full contractual base-royalty percentage table; independently usable realized pellet prices; Cliffs/Northshore recoverable reserve and production life schedule; discount-rate and duration assumptions for the PV bridge. |
| affected valuation components | `producing_royalty_stream`, `depletion_and_concentration_reserve` |
| valuation consequence | Keep provisional $30/$35/$42 and -$5/-$3/-$1. Do not mark the producing stream audited. Security remains evidence-blocked. |
| falsifier | Northshore idles again, royalty-per-ton economics stay below the low case, or a primary reserve/production disclosure shows recoverable tonnage/cadence insufficient for the low case. |
| monitoring source | Quarterly royalty-report 8-K exhibits; annual 10-K / Exhibit 13. |

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
| valuation consequence | Keep provisional $0/$7/$13. Only incremental damages or a demonstrated contractual change excluded from the producing-stream model may sit here. Ordinary base/bonus/internal-use royalties stay in `producing_royalty_stream`. |
| falsifier | Dismissal, adverse award, settlement below the separately modeled incremental amount, or a remedy limited to royalties already accrued in the producing stream. |
| monitoring source | 8-K litigation updates; 10-Q/10-K Item 3; any AAA award or settlement exhibit. |

**Overlap control:** producing component owns ordinary royalty and contractual bonus economics; legal option owns only incremental recovery beyond that stream.

### `trust_net_assets` — met / **accepted**

| Field | Content |
|---|---|
| status | met |
| evidence | Audited January 31, 2026 unallocated reserve $20.403m including $19.751m unallocated cash. |
| source path or URL | 2026 Form 10-K / Annual Report Exhibit 13 |
| calculation | $20.403m / 13,120,010 ≈ $1.555 per unit, bracketed by model $1/$2/$3. |
| remaining uncertainty | Contingent legal costs or other senior liabilities could consume the reserve. |
| affected valuation components | `trust_cash_and_other_claims` |
| valuation consequence | Cash claim remains additive; does not make the security decision-ready. |
| falsifier | Material contingent legal costs or liabilities consume the unallocated reserve. |
| monitoring source | Each Form 10-Q/10-K reserve table. |

## Valuation consequence

Every material component remains valued exactly once, but the overall case remains **evidence-blocked** by reserve/depletion and legal-option evidence. Primary value should remain a finite, scenario-weighted royalty-distribution curve. The cash claim is additive; the arbitration claim is separately probability-weighted; ordinary royalties cannot be counted in both.
