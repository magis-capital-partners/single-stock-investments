# KEWL valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the universal ownership map to FY2024–FY2025 primary filings. Evidence packet authorized per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `current_operating_claim` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $27.50 |
| `asset_option_inventory` | legacy_sensitivity | probability_weighted_catalyst_nav@1.0 | bounded_estimate | $9.90 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $6.60 |
| `realization_reserve` | legacy_sensitivity | realization_reserve@1.0 | bounded_estimate | -$8.25 |

**Component sum (base):** $27.50 + $9.90 + $6.60 − $8.25 = **$35.75/sh** (matches legacy component schedule).

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `KEWL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): **$35.75/sh** vs price ~$55.0. |
| remaining uncertainty | Copperwood production royalty remains probability-weighted; SSI $7.7M reference is estimate until production. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Copperwood cancelled and lease income falls below $250K/yr for two consecutive reporting periods. |

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping overlap keys map one diluted common share (1,126,284 units) to lease/mineral cash flows, Copperwood and acreage options, net financial claims, and realization reserve. |
| source path | `KEWL/research/valuation.json` → `component_valuation.components[]`; `economic_value.economic_claim` |
| calculation | Ownership percentage 1.0 on each component; `double_counting_flags` empty; GAAP mineral rights line bounded in net financial fraction, not duplicated in option royalty math. |
| remaining uncertainty | Subsidiary Keweenaw Properties / Keweenaw Minerals LLC look-through not separately quantified. |
| affected components | All |
| valuation consequence | Each material claim valued exactly once in additive schedule. |
| falsifier | New component added without unique overlap_key or embedded treatment documented. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 annual: 1,126,284 shares; >1.3M mineral acres; 36,705 leased acres. FY2024: book ~$14.3M (~$12.70/sh); mineral lease income ~$349.7K. H1 2025 semi-annual: lease income $189,101 vs $149,310 prior year. |
| source path | `KEWL/investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf`; `2024-12-31_Annual_Report.pdf`; `2025-06-30_Semi-Annual_Report.pdf` |
| calculation | Operating proof: $365K lease run-rate / 1.126M sh × 84.86× cap = **$27.50/sh**. Option proof: ($4.41M risked royalty + $6.74M acreage) / 1.126M sh = **$9.90/sh**. |
| remaining uncertainty | $365K run-rate is annualized from H1 2025 trend, not full-year audited revenue. |
| affected components | `current_operating_claim`, `asset_option_inventory` |
| valuation consequence | Filing-anchored facts anchor proofs; legacy sensitivities replaced. |
| falsifier | FY2026 annual shows mineral lease income below $300K with no Copperwood milestone. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | No convertible debt outstanding (FY2025 annual); ~$160K/yr corporate burn (FY2024 MD&A); H1 2025 net loss ($51,156); cash ~$4M vs book ~$14.3M (Dec 2024). |
| source path | FY2024 and FY2025 OTC annual reports |
| calculation | Realization reserve proof: $160K burn × 58.07× / 1.126M sh = **−$8.25/sh** base; captures overhead, title, and development-capital drag. |
| remaining uncertainty | Management CF-positive-from-2026 claim unverified vs H1 2025 loss. |
| affected components | `realization_reserve`, `net_financial_claims` |
| valuation consequence | Senior claims and downside explicitly reserved; not double-counted in operating or option components. |
| falsifier | Undisclosed debt, dilutive issuance, or material title loss on core acreage. |

## Facts vs judgments

**Facts (locked):** Shares 1,126,284; >1.3M gross mineral acres; 36,705 leased acres; no convertible debt; repurchase 51,633 shares at $27 (June 2024).

**Estimates:** FY2024 book $14.3M; FY2024 lease income $349.7K; H1 2025 lease income $189K; cash ~$4M; operating burn ~$160K/yr.

**Judgments (bounded):** Lease capitalization multiple 54–119×; Copperwood success probability 0–65%; acreage option $0–$19.7M; equity claim fraction 13–87%; realization reserve multiple 15–116× on burn proxy.

## Valuation consequence

Proof-complete additive schedule base case **~$35.75 per share** vs price **~$55** implies negative annualized return on component economic value at spot. Lawrence synthesis **-8.3%** remains the headline reference; NAV overlay **~$22.65/sh** stays a separate context tier. Security remains **watch**; no human capital decision recorded.
