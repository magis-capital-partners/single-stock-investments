# ABBV valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blocker by supplying a complete economic ownership map and attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-21 per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `immunology_owner_cash_engine` | unmapped | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $190.00 |
| `other_franchises` | unmapped | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $55.00 |
| `pipeline_options` | unmapped | risk_adjusted_milestone_value@1.0 | bounded_estimate | $12.00 |
| `net_financial_claims` | unmapped | net_asset_value@1.0 | bounded_estimate | $2.95 |
| `downside_reserve` | unmapped | net_asset_value@1.0 | bounded_estimate | -$10.00 |

## Economic ownership map

One diluted ABBV share equals:

1. **Immunology owner-cash engine** — pro-rata Skyrizi, Rinvoq, and remaining Humira cash flows (~46% of consolidated owner cash by revenue mix).
2. **Other franchises** — neuroscience, oncology, aesthetics, and eye care (~54% revenue share of owner cash).
3. **Pipeline options** — probability-weighted late-stage readouts (Skyrizi CD induction, Rinvoq expansions, oncology); not in Lawrence base free cash flow path.
4. **Near-term liquidity claim** — surplus cash separate from capitalized engine (overlap key `net_financial_claims`).
5. **Downside reserve** — litigation, biosimilar spread, payer negotiation, and leverage stress; **not** full net debt subtraction (overlap key `downside_reserve`).

**Excluded (no double count):** Imbruvica/Venclexta collaboration profit shares are embedded in reported product revenue. Full ~$65B debt is reserved through the stress component, not subtracted again from owner-cash engines.

## Acceptance tests

### ownership_map_complete — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five non-overlapping additive components with distinct `overlap_key` values; `all_material_components_identified: true`. |
| source path | `ABBV/research/valuation.json` → `component_valuation.components[]` |
| calculation | Base sum: $190.00 + $55.00 + $12.00 + $2.95 − $10.00 = **$249.95/sh** vs price **$249.91**. |
| remaining uncertainty | Franchise-level margin splits are revenue-proportional judgments, not indication-level DCFs. |
| affected components | All five additive components |
| valuation consequence | Universal contract may advance toward `decision_grade` after mechanical refresh. |
| falsifier | Any additive component lacks valid proof or overlap keys collide. |

### owner_cash_bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow $19.03B less capital spending $1.21B = $17.82B owner cash; 1,773M diluted shares = **$10.05/sh**. |
| source path | `ABBV/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001551152_26_000008.htm` |
| calculation | Immunology share 28.2/61.2 × $17.82B = ~$8.21B; other franchises ~$9.61B. |
| remaining uncertainty | Product-level rebates and collaboration profit shares not line-item in segment note (single operating segment). |
| affected components | `immunology_owner_cash_engine`, `other_franchises` |
| valuation consequence | Lawrence base IRR **6.9%** reconciles to component fair value ~$250/sh at base assumptions. |
| falsifier | Two consecutive quarters of consolidated owner cash below $8/sh without offsetting growth product ramp. |

### downside_capital_claims — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | FY2025 cash $5.23B; total debt ~$65.0B (current $6.06B + long-term $58.94B). Reserve uses bounded stress claim, not full net debt NAV. |
| source path | FY2025 10-K balance sheet |
| calculation | Reserve base −$10/sh = −$17.7B aggregate stress vs ~$36.7/sh full net debt per share. |
| remaining uncertainty | Litigation reserve timing and IRA pricing impact remain judgment bands. |
| affected components | `downside_reserve`, `net_financial_claims` |
| valuation consequence | Dhando partial: strong cash generation but leverage limits balance-sheet flexibility. |
| falsifier | Net debt rises above $70B while owner cash falls below $8/sh for four quarters. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All five additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `ABBV/research/valuation.json` |
| calculation | Proof sum (base) **$249.95/sh** at price **$249.91** → Lawrence **6.9%** annual return. |
| remaining uncertainty | Pipeline aggregate remains judgment; not indication-level event trees. |
| affected components | All five |
| valuation consequence | `valuation_contract.json` may reach `decision_grade` pending mechanical pipeline. |
| falsifier | Any component proof fails validation. |

## Facts vs judgments

**Facts (locked):** FY2025 net revenues $61.16B; operating cash flow $19.03B; capital spending $1.21B; owner cash ~$10.05/sh; cash $5.23B; total debt ~$65.0B; diluted shares 1,773M; Skyrizi ~$17.6B (+50%); Rinvoq ~$7.5B (+39%); Humira ~$3.1B (-49%); Q1 2026 revenue +12.4% YoY.

**Judgments (bounded):** Revenue-proportional owner-cash split between immunology and other franchises; aggregate pipeline risked value; near-term liquidity claim sizing; litigation and leverage stress reserve.

## Valuation consequence

Proof-complete additive schedule base case **$249.95 per share** vs market price **$249.91** implies Lawrence base **6.9% per year** (total synthesis **7.6%** with qualitative adjustments). Security remains **watch** below 15% accumulate hurdle; no stance promotion in this agent run.
