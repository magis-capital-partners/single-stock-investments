# ABNB pricing analysis

**As of:** 2026-07-22

**Price:** $144.94

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Core marketplace owner-cash engine (nights and GBV) | owner_cash_or_dividend_discount | $109.37 | $140.00 | $175.00 |
| Experiences and services attach option | risk_adjusted_milestone_value | $0.00 | $4.00 | $12.00 |
| Net cash and debt claims on common equity | net_asset_value | $6.55 | $7.82 | $8.53 |
| Regulatory, tax, and execution reserve | net_asset_value | $-14.00 | $-6.00 | $-1.50 |
| **Total** |  | **$101.92** | **$145.82** | **$194.03** |

Base value versus price: **0.6%**. Current or contracted operating and financial assets support approximately **$141.82** per share; the market asks investors to pay another **$3.12** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K: revenue $12241.0M, FCF $4600.0M, cash $6864.0M, long-term debt $1995.0M, SBC $1.59B.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Core marketplace owner-cash engine (nights and GBV) | Proof outputs {'low': 109.37, 'base': 140.0, 'high': 175.0}; see calculation_proof graph. | n/a | $140.00 | Unique overlap key core_marketplace_platform; no other component capitalizes the same claim. |
| Experiences and services attach option | Proof outputs {'low': 0.0, 'base': 4.0, 'high': 12.0}; see calculation_proof graph. | n/a | $4.00 | Unique overlap key experiences_services_option; seats in KPI embedded in core engine. |
| Net cash and debt claims on common equity | Proof outputs {'low': 6.5536, 'base': 7.8154, 'high': 8.5265}; see calculation_proof graph. | n/a | $7.82 | Unique overlap key net_financial_claims; no other component capitalizes the same claim. |
| Regulatory, tax, and execution reserve | Proof outputs {'low': -14.0, 'base': -6.0, 'high': -1.5}; see calculation_proof graph. | n/a | $-6.00 | Unique overlap key regulatory_and_execution_reserve; no other component capitalizes the same claim. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Core marketplace owner-cash engine (nights and GBV) | owner_cash_or_dividend_discount | not_applicable | $109.37 / $140.00 / $175.00 | n/a | Unique overlap key core_marketplace_platform; no other component capitalizes the same claim. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Experiences and services attach option | risk_adjusted_milestone_value | not_applicable | $0.00 / $4.00 / $12.00 | risked range; Milestone value over 3–7 years as experiences/services mix expands. | Unique overlap key experiences_services_option; seats in KPI embedded in core engine. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net cash and debt claims on common equity | net_asset_value | not_applicable | $6.55 / $7.82 / $8.53 | n/a | Unique overlap key net_financial_claims; no other component capitalizes the same claim. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Regulatory, tax, and execution reserve | net_asset_value | not_applicable | $-14.00 / $-6.00 / $-1.50 | n/a | Unique overlap key regulatory_and_execution_reserve; no other component capitalizes the same claim. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Component ranges are filing-anchored bounded estimates, not committee-approved price targets.
- Experiences/services option remains judgment-heavy pending standalone segment disclosure.



## What the price implies

At the stated terminal multiple, the price requires approximately **-6.1%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 22x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $127.53 | $114.63 | $98.25 | $77.12 |
| Base | $172.20 | $154.17 | $131.33 | $101.97 |
| Bull | $229.04 | $204.46 | $173.36 | $133.49 |

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
