# MSB valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per unit |
|-----------|--------------|--------|--------------|---------------|
| `producing_royalty_stream` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $35.00 |
| `arbitration_and_bonus_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.00 |
| `trust_cash_and_other_claims` | calculated (partial) | net_asset_value@1.0 | bounded_estimate | $1.40 |

Embedded `depletion_and_concentration_reserve` remains inside the producing capitalization multiple; it is not additive.

## Acceptance tests

### `royalty_reserve_reconciliation` — partially_met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Units (**13,120,010**), FY2026 declared distributions (**$1.28/unit**), Q1 2025/Q1 2026 royalty reports (tons, base, bonus, **$71.70/ton** 2026 bonus threshold), and operator concentration are primary-sourced. |
| source path | `MSB/investor-documents/sec-edgar/10-K_20260422_rpt20260131_acc0001104659_26_046864.htm`; `8-K_20260504` royalty exhibit; `MSB/research/evidence_reconciliation_2026-07-15.md` |
| calculation | FY2026 distributions **$1.28/unit** × capitalization multiple **27.34×** (base judgment) ≈ **$35.00/unit** producing proof. Q1 2026 base royalty ≈ **$1.28/ton** on 938,572 tons; this is a historical observation, not a full reserve-life PV bridge. |
| remaining uncertainty | Full contractual base-tier table; Cliffs/Northshore recoverable reserve and production cadence; independently usable realized pellet prices for every quarter. |
| affected components | `producing_royalty_stream`, embedded depletion reserve |
| valuation consequence | Producing stream now has a reproducible proof anchored to filing distributions; reserve-life PV bridge remains open. |
| falsifier | Northshore idles again, royalty-per-ton economics stay below the low case, or July 2026 distributions remain near the **$0.05** level. |
| monitoring source | July 30, 2026 quarterly royalty report; subsequent royalty-report 8-K exhibits. |

### `legal_option_record` — met (base case)

| Field | Content |
|---|---|
| status | met |
| evidence | Prior AAA award paid in full (**$71.185M** / ~**$5.43/unit**, `8-K_20241017`). September 2025 arbitration disclosed without amount, schedule, probability, or collectibility (`8-K_20250926`; 2026 10-K Item 3). |
| source path | `MSB/investor-documents/sec-edgar/8-K_20241017_rpt20241017_acc0001558370_24_013375.htm`; `8-K_20250926_rpt20250926_acc0001104659_25_093889.htm` |
| calculation | Base incremental recovery **$0**; high sensitivity **$13/unit** = **$170.56M** risked at 100% probability (unapproved upside only). Prior award is closed context, not current payoff. |
| remaining uncertainty | Statement of claim, hearing schedule, award or settlement amount; whether remedy is incremental to ordinary royalties. |
| affected components | `arbitration_and_bonus_option` |
| valuation consequence | Ordinary royalties stay in producing stream; legal option is separately proofed with explicit zero base. |
| falsifier | Dismissal, adverse award, or remedy limited to royalties already in the producing stream. |
| monitoring source | 8-K litigation updates; 10-Q/10-K Item 3. |

### `trust_net_assets` — met

| Field | Content |
|---|---|
| status | met |
| evidence | April 30, 2026 unallocated reserve **$18.341533M**; January 31, 2026 reserve **$20.403M**; **13,120,010** units. |
| source path | `MSB/investor-documents/sec-edgar/10-Q_20260612_rpt20260430_acc0001104659_26_073470.htm`; 2026 Form 10-K / Exhibit 13 |
| calculation | **$18.341533M** ÷ **13.12001M** units = **$1.398/unit** base proof; low/high bracket contingent costs and prior reserve mark. |
| remaining uncertainty | Contingent legal costs could consume reserve. |
| affected components | `trust_cash_and_other_claims` |
| valuation consequence | Filing-locked reserve per unit reproduced exactly in base proof. |
| falsifier | Material contingent liabilities consume the unallocated reserve. |

## Overlap control — met

Unique overlap keys unchanged. Ordinary base and bonus royalties are in `producing_royalty_stream`; arbitration owns only incremental recovery beyond that stream. `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** **13,120,010** units; FY2026 distributions **$1.28/unit**; April 30, 2026 unallocated reserve **$18.341533M**; prior award collected **$71.185M**; Q1 2026 bonus **$0** with **$71.70/ton** threshold.

**Judgments (bounded):** Distribution capitalization multiple **23.44–32.81×**; arbitration high sensitivity **$13/unit** incremental only; reserve adjustment **−$5M to +$2.06M** for legal/timing band.

## Valuation consequence

Proof-complete additive schedule base case **~$36.40 per unit** ($35.00 + $0 + $1.40) vs price **~$24.40** implies component economic value above market before mechanical Lawrence refresh. Reserve-life and full royalty-tier acceptance tests remain **partially_met**; security may reach **decision_grade** on proofs while royalty PV bridge stays an open follow-up. No human capital decision recorded.
