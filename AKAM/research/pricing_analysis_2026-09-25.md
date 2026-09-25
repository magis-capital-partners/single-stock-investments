# AKAM pricing analysis

**As of:** 2026-09-25

**Price:** $124.22

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Edge platform owner-cash engine (Compute, Security, Delivery) | owner_cash_or_dividend_discount | $98.00 | $145.00 | $215.00 |
| Compute and GPU/cloud platform upside option | risk_adjusted_milestone_value | $0.00 | $10.00 | $28.00 |
| Net cash and convertible debt claims on common equity | net_asset_value | $-28.00 | $-21.84 | $-8.00 |
| Cloud price competition and Security share-loss stress reserve | net_asset_value | $-20.00 | $-8.00 | $-2.00 |
| **Total** |  | **$50.00** | **$125.16** | **$233.00** |

Base value versus price: **0.8%**. Current or contracted operating and financial assets support approximately **$115.16** per share; the market asks investors to pay another **$9.06** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K: stockholders' equity ~$4.98B; economic value in normalized owner cash ($6.8789/sh), not GAAP book alone.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Edge platform owner-cash engine | Owner-cash discount on FY2025 FCF per diluted share. | n/a | $145.00 | Unique overlap key edge_platform_owner_cash_engine. |
| Compute and GPU/cloud platform upside option | Risk-adjusted milestone value on Compute mix shift and RPO. | n/a | $10.00 | Unique overlap key compute_gpu_platform_option. |
| Net cash and convertible debt claims on common equity | Net asset value on filing-locked cash less convertible debt. | n/a | $-21.84 | Unique overlap key net_financial_claims. |
| Cloud price competition and Security share-loss stress reserve | Bounded negative reserve; not full enterprise value haircut. | n/a | $-8.00 | Unique overlap key cloud_competition_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Compute, Security, and Delivery normalized free cash flow | owner_cash_or_dividend_discount | not_applicable | $98.00 / $145.00 / $215.00 | n/a | Unique overlap key edge_platform_owner_cash_engine. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Incremental GPU/cloud monetization beyond normalized FCF | risk_adjusted_milestone_value | not_applicable | $0.00 / $10.00 / $28.00 | risked range; RPO ~$5.2B converts over multi-year contracts per FY2025 10-K. | Unique overlap key compute_gpu_platform_option. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net corporate liquidity after convertible notes and operating minimum | net_asset_value | not_applicable | $-28.00 / $-21.84 / $-8.00 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Hyperscaler/Cloudflare pricing and Security erosion stress | net_asset_value | not_applicable | $-20.00 / $-8.00 / $-2.00 | n/a | Unique overlap key cloud_competition_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Segment-level FCF not separately disclosed; consolidated engine with Compute option overlay.
- Convertible note equity conversion and competition reserve bands are judgment.



## What the price implies

At the stated terminal multiple, the price requires approximately **-7.4%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 22x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $113.84 | $102.37 | $87.79 | $68.98 |
| Base | $153.74 | $137.69 | $117.34 | $91.19 |
| Bull | $216.78 | $193.42 | $163.87 | $126.02 |

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
