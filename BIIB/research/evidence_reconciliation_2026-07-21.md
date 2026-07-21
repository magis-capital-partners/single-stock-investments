# BIIB valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `legacy_products` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $54.81 |
| `growth_products` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $55.00 |
| `pipeline` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $60.00 |
| `apellis_assets` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $45.03 |
| `net_debt_acquisition_and_cvrs` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$54.63 |
| `patent_failure_and_burn_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$15.00 |

## Acceptance tests

### product_cash_flows — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | FY2025 10-K locks MS product revenue $4,039M, biosimilars $729M, rare-disease $2,154M; legacy and growth proofs anchor revenue facts and bounded margin/multiple judgments. |
| source path | `BIIB/investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0000875045_26_000013.htm` |
| calculation | Legacy base: $4,768M revenue × 34% margin × 4.97× / 147M shares = **$54.81/sh**. Growth base: $2,154M × 32% × 11.73× / 147M = **$55.00/sh**. |
| remaining uncertainty | Product-level rebates, collaboration profit shares, and post-exclusivity tails are not line-item disclosed; margins remain bounded judgments. |
| affected components | `legacy_products`, `growth_products` |
| valuation consequence | Proofs reproduce low/base/high; product schedules are not yet indication-level DCFs. |
| falsifier | Two consecutive quarters of product revenue erosion below low-case margin path without offsetting growth. |

### pipeline_event_trees — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | 10-K and earnings materials disclose program phase and several readout dates (e.g., litifilimab Phase 3 SLE H2 2026). Proof uses aggregate risked success value less remaining R&D. |
| source path | `BIIB/investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0000875045_26_000013.htm` |
| calculation | Base net option: $10,620M − $1,800M = $8,820M → **$60.00/sh** at 147M shares. |
| remaining uncertainty | Indication-level probabilities and non-overlapping event trees are not yet built; aggregate judgment remains. |
| affected components | `pipeline` |
| valuation consequence | Milestone method approved; granular trees remain [HUMAN REVIEW]. |
| falsifier | Phase 3 miss on litifilimab or felzartamab reduces aggregate success value below low case. |

### closing_claims — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | May 14 2026 8-K: ~$5.3B consideration, $2.0B term facilities drawn, max CVR ~$582M. Proof reconciles post-close net debt core ($7.4B) plus CVR/integration judgments. |
| source path | `BIIB/investor-documents/sec-edgar/8-K_20260514_rpt20260514_acc0001193125_26_222908.htm` |
| calculation | Base senior claims: ($6.3B + $2.0B − $0.9B remaining cash) + $350M CVR EV + $280M integration = $8.03B → **-$54.63/sh**. |
| remaining uncertainty | Purchase-price allocation and day-one balance sheet await first post-close 10-Q; integration costs are bounded estimates. |
| affected components | `net_debt_acquisition_and_cvrs` |
| valuation consequence | Filing-locked cash, debt, acquisition cash, and new borrowings drive proof; stress reserve in low case. |
| falsifier | Post-close 10-Q shows net debt or CVR liability >15% above base proof inputs. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All six additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `BIIB/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof sum (base): $54.81 + $55.00 + $60.00 + $45.03 − $54.63 − $15.00 = **$145.21/sh** vs price ~$197. |
| remaining uncertainty | Judgment bands on margins, milestone aggregates, and integration remain wide. |
| affected components | All six additive blockers |
| valuation consequence | Universal contract may advance toward `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** FY2025 MS revenue $4,039M; biosimilars $729M; rare-disease $2,154M; cash ~$4.2B; debt ~$6.3B; diluted shares ~147M; Apellis close ~$5.3B; $2.0B new term debt; Apellis 2025 revenue $689M; max CVR ~$582M.

**Judgments (bounded):** Legacy and growth margins and multiples; aggregate pipeline risked value; Apellis success probability and revenue multiple; CVR expected value and integration costs; correlated downside reserve.

## Valuation consequence

Proof-complete additive schedule base case **$145.21 per share** vs market price **~$197** implies negative annualized return on component economic value at a seven-year horizon. Security remains **watch** pending human capital decision; no stance promotion in this agent run.
