# BWEL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the universal ownership map to FY2025 primary filings. Evidence packet authorized per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `current_operating_claim` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $274.33 |
| `asset_option_inventory` | legacy_sensitivity | probability_weighted_catalyst_nav@1.0 | bounded_estimate | $98.72 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $65.82 |
| `realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$82.27 |

**Component sum (base):** $274.33 + $98.72 + $65.82 − $82.27 = **$356.60/sh** (vs legacy scaffold $356.53; proof outputs rounded).

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `BWEL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): **$356.60/sh** vs price ~$548.50. |
| remaining uncertainty | Water acre-feet quantity unverified in filings; net financial claim uses bounded judgment pending full sources-and-uses bridge. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Two consecutive loss years with dividends cut below $15/sh; revolver drawn above $180M without crop recovery. |

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping overlap keys map one diluted common share (964,210 units) to operating cash, land/water/mineral optionality, net financial claims, and realization reserve. |
| source path | `BWEL/research/valuation.json` → `component_valuation.components[]`; `economic_value.economic_claim` |
| calculation | Ownership percentage 1.0 on each component; `double_counting_flags` empty; land GAAP line excluded from operating DCF and bounded in option component. |
| remaining uncertainty | Subsurface mineral fractional interests not quantified separately in filings. |
| affected components | All |
| valuation consequence | Each material claim valued exactly once in additive schedule. |
| falsifier | New component added without unique overlap_key or embedded treatment documented. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 annual (`2025-06-30_Annual_Report.pdf`): equity $755.073M, land $106.048M, notes payable $150.285M, cash $0.261M, NRV charge $42.834M, dividends $17.50/sh, shares 964,210. |
| source path | `BWEL/research/evidence/_text/2025-06-30_Annual_Report.pdf.txt` |
| calculation | Operating proof: $22/sh mid-cycle distribution × growth factor / (required return − growth) = **$274.33/sh**. Option proof: $95.19M incremental NAV / 0.96421M sh = **$98.72/sh**. |
| remaining uncertainty | Mid-cycle $22/sh is normalized judgment, not FY2025 GAAP earnings. |
| affected components | `current_operating_claim`, `asset_option_inventory` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities replaced. |
| falsifier | FY2026 annual shows sustained owner cash below $16/sh with no recovery path. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Notes payable $150.285M (up from $35.7M YoY); NRV $42.834M; lease and employee benefit liabilities per balance sheet; no preferred or dilutive overhang disclosed. |
| source path | FY2025 annual Note 4 and Note 2 |
| calculation | Realization reserve proof: −$79.33M base reserve / 0.96421M sh = **−$82.27/sh**; captures cyclical, credit, and monetization-delay downside. |
| remaining uncertainty | Remaining revolver capacity (~$130M undrawn on $280M facilities) is available liquidity not modeled as equity uplift. |
| affected components | `realization_reserve`, `net_financial_claims` |
| valuation consequence | Senior claims and downside explicitly reserved; not double-counted in operating or option components. |
| falsifier | Undisclosed lien, preferred, or off-balance-sheet water obligation appears in subsequent annual. |

## Facts vs judgments

**Facts (locked):** Shares 964,210; equity $755.073M; land $106.048M; notes payable $150.285M; cash $0.261M; NRV charge $42.834M; FY2024 dividend $20/sh; FY2025 dividend $17.50/sh.

**Judgments (bounded):** Mid-cycle distribution $16–$28/sh; incremental NAV $0–$254M; net financial claim $16–$106M; realization reserve $0 to −$159M.

## Valuation consequence

Proof-complete additive schedule base case **~$357 per share** vs price **~$549** implies negative annualized return on component economic value at spot. Lawrence synthesis **2.57%** remains the headline reference; NAV overlay **~$1,480/sh** stays a separate context tier. Security remains **watch**; no human capital decision recorded.
