# AXTI valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `cash_and_liquidity` | legacy_sensitivity | net_asset_value@1.0 | calculated | $0.89 |
| `midcycle_substrate_operations` | legacy_sensitivity | midcycle_capacity_value@1.0 | bounded_estimate | $1.40 |
| `tongmei_hk_listing_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.50 |
| `pe_redemption_liability` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$0.75 |
| `dilution_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$0.30 |

Embedded `raw_materials_gallium` remains zero and embedded in substrate operations (no double count).

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` now carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all five graphs. |
| source path | `AXTI/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $1.40 + $0.89 + $0.50 - $0.75 - $0.30 = **$1.74/sh** vs legacy component schedule. |
| remaining uncertainty | Tongmei success value and PE redemption timing remain judgment-heavy; substrate mid-cycle anchor is normalized, not spot GAAP. |
| affected components | All five additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Two consecutive quarters of owner cash below low-case normalized path; full PE redemption funded from parent cash without HK listing offset. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K and Q1 2026 10-Q via `sec_companyfacts.json`; Tongmei redemption $49M (Note 1); cash $57.9M; shares 65,423,184. |
| source path | `AXTI/investor-documents/sec-edgar/10-Q_20260514_rpt20260331_acc0001437749_26_017054.htm` |
| calculation | Cash proof: $57.9M × 1.005 / 65.423M = **$0.889/sh**. PE liability: $49M / 65.423M = **$0.749/sh** at base redemption_pct 1.0. |
| remaining uncertainty | Restricted cash usability; RMB/USD on redemption. |
| affected components | `cash_and_liquidity`, `pe_redemption_liability` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | March 2026 cash balance revised downward >15% in next 10-Q without matching liability release. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; gallium vertical integration embedded in `midcycle_substrate_operations`. |
| source path | `AXTI/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Cash $57.9M; shares 65.423M; PE redemption aggregate ~$49M; FY2021-FY2022 operating profit band ~$13M; Q1 2026 revenue $26.9M.

**Judgments (bounded):** Mid-cycle owner cash $4.5M–$12.0M; Tongmei HK success probability 0–55%; PE redemption pct 0–133%; future dilution haircut 0–1.1% of price.

## Valuation consequence

Proof-complete additive schedule base case **$1.74 per share** vs price **$45.86** implies deeply negative annualized return on component economic value. Lawrence synthesis **-9.92%** remains the stance reference on normalized owner-cash path; component schedule cross-check **-32.8%** weights corporate-structure risks. Security remains **watch**; no human capital decision recorded.
