# AAPL pricing analysis

**As of:** 2026-07-22

**Price:** $326.59

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Core products and services owner-cash engine | owner_earnings_reinvestment_dcf | $131.56 | $171.03 | $210.50 |
| Services installed-base and platform monetization option | risk_adjusted_milestone_value | $0.00 | $35.00 | $85.00 |
| Net cash, securities, and debt claims on common equity | net_asset_value | $-6.00 | $3.00 | $10.00 |
| China, antitrust, and hardware cycle stress reserve | net_asset_value | $-45.00 | $-22.00 | $-8.00 |
| **Total** |  | **$80.56** | **$187.03** | **$297.50** |

Base value versus price: **-42.7%**. Current or contracted operating and financial assets support approximately **$152.03** per share; the market asks investors to pay another **$174.56** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q2 FY2026 10-Q filing extracts; GAAP net income is cross-check only for platform compounder.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Core products and services owner-cash engine | Proof outputs {'low': 131.56, 'base': 171.03, 'high': 210.4999}; see calculation_proof graph. | n/a | $171.03 | Unique overlap key core_products_services_engine. |
| Services installed-base and platform monetization option | Proof outputs {'low': 0.0, 'base': 35.0, 'high': 85.0}; see calculation_proof graph. | n/a | $35.00 | Unique overlap key services_installed_base_option. |
| Net cash, securities, and debt claims on common equity | Proof outputs {'low': -6.0, 'base': 3.0, 'high': 10.0}; see calculation_proof graph. | n/a | $3.00 | Unique overlap key net_financial_claims. |
| China, antitrust, and hardware cycle stress reserve | Proof outputs {'low': -45.0, 'base': -22.0, 'high': -8.0}; see calculation_proof graph. | n/a | $-22.00 | Unique overlap key regulatory_and_cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Core products and services owner-cash engine | owner_earnings_reinvestment_dcf | not_applicable | $131.56 / $171.03 / $210.50 | n/a | Unique overlap key core_products_services_engine. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Services installed-base and platform monetization option | risk_adjusted_milestone_value | not_applicable | $0.00 / $35.00 / $85.00 | risked range; Installed-base monetization through App Store, iCloud, and Apple Intelligence over 3 to 7 years. | Unique overlap key services_installed_base_option. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net cash, securities, and debt claims on common equity | net_asset_value | not_applicable | $-6.00 / $3.00 / $10.00 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| China, antitrust, and hardware cycle stress reserve | net_asset_value | not_applicable | $-45.00 / $-22.00 / $-8.00 | n/a | Unique overlap key regulatory_and_cycle_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Services milestone value is judgment-based; deferred Services revenue partially embedded in consolidated free cash flow.
- Regulatory and China reserve bands remain widest judgment components.



## What the price implies

At the stated terminal multiple, the price requires approximately **5.6%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 28x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $125.15 | $112.25 | $95.88 | $74.82 |
| Base | $176.33 | $157.50 | $133.69 | $103.14 |
| Bull | $226.96 | $202.29 | $171.11 | $131.20 |

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
