# ADI pricing analysis

**As of:** 2026-07-22

**Price:** $372.46

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Analog semiconductor owner-cash engine | owner_earnings_reinvestment_dcf | $172.28 | $223.96 | $275.64 |
| AI and data-center power and connectivity option | risk_adjusted_milestone_value | $0.00 | $18.00 | $45.00 |
| Net cash and debt claims on common equity | net_asset_value | $-16.00 | $-12.00 | $-8.00 |
| Semiconductor cycle and integration stress reserve | net_asset_value | $-35.00 | $-20.00 | $-10.00 |
| **Total** |  | **$121.28** | **$209.96** | **$302.64** |

Base value versus price: **-43.6%**. Current or contracted operating and financial assets support approximately **$191.96** per share; the market asks investors to pay another **$180.50** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q2 FY2026 10-Q filing extracts; GAAP net income is cross-check only for analog compounder.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Analog semiconductor owner-cash engine | Proof outputs {'low': 172.2797, 'base': 223.9597, 'high': 275.6396}; see calculation_proof graph. | n/a | $223.96 | Unique overlap key analog_semiconductor_engine. |
| AI and data-center power and connectivity option | Proof outputs {'low': 0.0, 'base': 18.0001, 'high': 45.0}; see calculation_proof graph. | n/a | $18.00 | Unique overlap key ai_data_center_edge_option. |
| Net cash and debt claims on common equity | Proof outputs {'low': -15.9999, 'base': -12.0, 'high': -8.0001}; see calculation_proof graph. | n/a | $-12.00 | Unique overlap key net_financial_claims. |
| Semiconductor cycle and integration stress reserve | Proof outputs {'low': -35.0, 'base': -20.0, 'high': -10.0}; see calculation_proof graph. | n/a | $-20.00 | Unique overlap key cycle_integration_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Analog semiconductor owner-cash engine | owner_earnings_reinvestment_dcf | not_applicable | $172.28 / $223.96 / $275.64 | n/a | Unique overlap key analog_semiconductor_engine. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| AI and data-center power and connectivity option | risk_adjusted_milestone_value | not_applicable | $0.00 / $18.00 / $45.00 | risked range; Data-center power delivery and high-speed connectivity design wins over 3 to 7 years. | Unique overlap key ai_data_center_edge_option. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net cash and debt claims on common equity | net_asset_value | not_applicable | $-16.00 / $-12.00 / $-8.00 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Semiconductor cycle and integration stress reserve | net_asset_value | not_applicable | $-35.00 / $-20.00 / $-10.00 | n/a | Unique overlap key cycle_integration_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- AI/data-center milestone value is judgment-based; industrial revenue partially embedded in consolidated free cash flow.
- Cycle and integration reserve bands remain widest judgment components.



## What the price implies

At the stated terminal multiple, the price requires approximately **4.3%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 26x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $144.51 | $129.84 | $111.23 | $87.23 |
| Base | $205.53 | $183.82 | $156.34 | $121.05 |
| Bull | $280.03 | $249.69 | $211.34 | $162.23 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (High-return compounder). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** growth projected without its capital cost

**Committee routing:** not_initialized — not initialized

**Falsifiers:**

- growth projected without its capital cost
- stock compensation or acquisitions omitted
- terminal value unsupported by a durable mechanism

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
