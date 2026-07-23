# ACMR pricing analysis

**As of:** 2026-07-22

**Price:** $82.52

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Wet clean and electroplating equipment operations | owner_cash_or_dividend_discount | $9.68 | $15.49 | $23.23 |
| Advanced packaging and deferred-revenue backlog option | risk_adjusted_milestone_value | $0.00 | $6.00 | $18.00 |
| Net cash and debt claims on common equity | net_asset_value | $6.13 | $8.08 | $8.90 |
| Semicap cycle, customer concentration, and working-capital reserve | net_asset_value | $-15.00 | $-7.00 | $-2.00 |
| **Total** |  | **$0.81** | **$22.57** | **$48.13** |

Base value versus price: **-72.6%**. Current or contracted operating and financial assets support approximately **$16.57** per share; the market asks investors to pay another **$65.95** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q1 2026 10-Q extracts; reconciliation 2026-07-21.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Wet clean and electroplating equipment operations | Mid-cycle operating income capitalization proof. | n/a | $15.49 | Unique overlap key wet_clean_equipment_engine. |
| Advanced packaging and deferred-revenue backlog option | Risk-adjusted milestone on $252M deferred revenue. | n/a | $6.00 | Unique overlap key advanced_packaging_backlog_option. |
| Net cash and debt claims on common equity | Filing-locked cash less total debt. | n/a | $8.08 | Unique overlap key net_financial_claims. |
| Semicap cycle, customer concentration, and working-capital reserve | Negative reserve for OCF trough and geo concentration. | n/a | $-7.00 | Unique overlap key cycle_and_concentration_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Wet clean and electroplating equipment operations | owner_cash_or_dividend_discount | not_applicable | $9.68 / $15.49 / $23.23 | n/a | Unique overlap key wet_clean_equipment_engine. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Advanced packaging and deferred-revenue backlog option | risk_adjusted_milestone_value | not_applicable | $0.00 / $6.00 / $18.00 | risked range; Backlog ships as advanced packaging tools install; [Assumption] 3-year base. | Unique overlap key advanced_packaging_backlog_option. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net cash and debt claims on common equity | net_asset_value | not_applicable | $6.13 / $8.08 / $8.90 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Semicap cycle, customer concentration, and working-capital reserve | net_asset_value | not_applicable | $-15.00 / $-7.00 / $-2.00 | n/a | Unique overlap key cycle_and_concentration_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Contract backfill scaffold; not a committee-approved valuation.
- Backlog milestone band remains widest judgment range pending segment disclosure.



## What the price implies

At the stated terminal multiple, the price requires approximately **19.3%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 8x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $12.60 | $11.60 | $10.31 | $8.58 |
| Base | $22.92 | $20.82 | $18.12 | $14.60 |
| Bull | $35.48 | $31.98 | $27.52 | $21.75 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (Predictable cash-flow security). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** dividend treated as earning power

**Committee routing:** not_initialized — not initialized

**Falsifiers:**

- dividend treated as earning power
- growth capital and dilution omitted
- contract renewal or regulatory reset ignored

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
