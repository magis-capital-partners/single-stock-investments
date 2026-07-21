# CRML valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json` (hash `0b6b4313…dc2391`).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `corporate_cash` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.07 |
| `tanbreez_risked_nav` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.00 |
| `wolfsberg_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.50 |
| `dilution_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$0.50 |

Ownership map unchanged: four additive components, unique overlap keys, no embedded double-count.

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` → `component_valuation.components[]` carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `CRML/research/valuation.json` |
| calculation | Proof sum (base): $0.07 + $3.00 + $0.50 - $0.50 = **$3.07/sh** vs legacy component schedule. Lawrence scenario payoff **$4.00/sh** remains the stance gate (seven-year asset path). |
| remaining uncertainty | Tanbreez success probability and gross success value are judgment-heavy; PEA is pre-tax project-level, not equity NAV. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Two consecutive quarters of cash below $5M without matching asset uplift; DFS fails economic viability test. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 20-F: cash $7.3M; shares 104,912,853; Tanbreez 42%; BMW advance $15M restricted; Stage 2 up to 14.5M shares. |
| source path | `CRML/investor-documents/sec-edgar/20-F_20251006_rpt20250630_acc0001213900_25_096254.htm` |
| calculation | Cash proof: $7.3M × 1.006 / 104.913M = **$0.07/sh**. Tanbreez: $2,098M × 15% / 104.913M = **$3.00/sh**. Wolfsberg: $52.5M / 104.913M = **$0.50/sh**. Dilution: -$6.40 × 7.8% = **-$0.50/sh**. |
| remaining uncertainty | Going-concern burn may erode cash floor; GEM arbitration magnitude undisclosed in filing. |
| affected components | `corporate_cash`, `tanbreez_risked_nav`, `wolfsberg_option`, `dilution_reserve` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | March 2026 cash balance revised downward >15% without matching liability release. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `corporate_cash`, `tanbreez_risked_nav`, `wolfsberg_option`, `dilution_reserve`. |
| source path | `CRML/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Cash $7.3M at June 30, 2025; 104,912,853 shares; Tanbreez 42% (path to 92.5%); 44.87 Mt @ 0.38% TREO; BMW $15M advance; Stage 2 up to 14.5M shares; GEM facility dispute.

**Judgments (bounded):** Tanbreez success probability 7.6–23.8%; gross success value $655M–$3,357M; Wolfsberg milestone value $0–$210M; dilution/GEM reserve 3.1–23.4% of price.

## Valuation consequence

Proof-complete additive schedule base case **$3.07 per share** vs price **$6.40** implies negative annualized return on component economic value. Lawrence synthesis **-6.53%** remains the stance reference on seven-year risked asset payoff **$4.00/sh**. Security remains **watch**; no human capital decision recorded.
