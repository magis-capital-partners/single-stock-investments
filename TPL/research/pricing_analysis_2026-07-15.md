# TPL pricing analysis

**As of:** 2026-07-15

**Price:** $414.22

**Decision:** watch_above_base_below_high_economic_value

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Producing oil and gas royalties | capital_free_revenue_driver_dcf | $42.59 | $88.35 | $152.93 |
| Existing surface, easement, and land-use operations | land_use_revenue_driver_dcf | $7.08 | $14.89 | $27.31 |
| Produced-water royalty stream | capital_free_produced_water_driver_dcf | $20.32 | $43.25 | $89.98 |
| Cash and equity-method investment | balance_sheet_mark | $3.60 | $4.32 | $4.32 |
| Operated water sales and services | reinvestment_return_driver_dcf | $6.38 | $16.41 | $39.57 |
| Contracted data-center land-financing receivable | discounted_contract_value | $0.27 | $0.30 | $0.32 |
| Visible undeveloped royalty inventory | comparable_royalty_nav_residual | $17.35 | $18.65 | $40.70 |
| Dormant and long-dated royalty inventory | comparable_royalty_nav_residual | $21.21 | $22.80 | $49.77 |
| Residual uncontracted surface land | portfolio_discounted_unit_nav | $15.34 | $32.59 | $65.77 |
| Future infrastructure corridors and easements | milestone_probability_weighted_option | $0.80 | $4.46 | $13.48 |
| Data-center, power, and water co-location option | milestone_probability_weighted_option | $0.22 | $2.03 | $12.75 |
| Desalination and water-technology platform | stage_gated_milestone_option | $-0.30 | $1.16 | $10.51 |
| Corporate, tax, and realization reserve | conservative_reserve | $-5.00 | $-3.00 | $-1.00 |
| **Total** |  | **$129.86** | **$246.21** | **$506.41** |

Base value versus price: **-40.6%**. Current or contracted operating and financial assets support approximately **$164.52** per share; the market asks investors to pay another **$249.70** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** misleading_historical_cost

**Accounting reference:** TPL's 2025 10-K reports approximately $840M net acquired royalty interests, while the legacy 1/16 and 1/128 perpetual interests remain at zero carrying value.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Producing plus undeveloped royalty estate | 224,000 total NRA at $25k/$40k/$75k per NRA; TPL acquisition marks near $19.8k/$26.0k/$34.1k and developed public royalty transactions provide the ladder. | $129.83 | $129.80 | The producing DCF is subtracted from total royalty NAV before visible and dormant residual values are added. |
| Surface land, existing uses, and future corridors | Existing cash-flow value plus 882,000-acre portfolio marks anchored to TPL, LandBridge, and Intrepid transactions. | n/a | $51.94 | Existing contracted uses, residual land, and uncontracted corridors are separate economic claims. |
| Produced-water royalty, operated water, and technology | Capital-free produced-water royalties are separated from capital-requiring operated water and stage-gated treatment technology. | n/a | $60.82 | Royalty volume, operated margin, and technology licensing are modeled separately; infrastructure replacement cost remains embedded. |
| Cash, investments, and contracted receivable | Balance-sheet and discounted-contract marks. | n/a | $4.62 | The Bolt investment is excluded from the incremental project success value. |
| Data-center, power, and water co-location option | Milestone probability × success value less remaining TPL capital; powered-land scarcity is context, not a contracted rent assumption. | n/a | $2.03 | Only uncontracted incremental project economics are included. |
| Corporate and realization reserve | Tax, transaction, and corporate friction. | n/a | $-3.00 | Applied once at the consolidated level. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Producing plus undeveloped royalty estate | capital_free_revenue_driver_dcf | tpl_royalty_acquisitions_2024_2025, viper_sitio_2025 | $42.59 / $88.35 / $152.93 | n/a | The producing DCF is subtracted from total royalty NAV before visible and dormant residual values are added. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Surface land, existing uses, and future corridors | land_use_revenue_driver_dcf | tpl_surface_sale_2025, lb_reeves_800_2025, lb_lea_3000_2025, intrepid_south_ranch_2026 | $7.08 / $14.89 / $27.31 | n/a | Existing contracted uses, residual land, and uncontracted corridors are separate economic claims. | A directly comparable transaction or asset-specific impairment supports a value below the low-case unit mark after like-for-like adjustments. |
| Produced-water royalty, operated water, and technology | capital_free_produced_water_driver_dcf | not_applicable | $20.32 / $43.25 / $89.98 | n/a | Royalty volume, operated margin, and technology licensing are modeled separately; infrastructure replacement cost remains embedded. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Cash, investments, and contracted receivable | balance_sheet_mark | not_applicable | $3.60 / $4.32 / $4.32 | n/a | The Bolt investment is excluded from the incremental project success value. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Produced-water royalty, operated water, and technology | reinvestment_return_driver_dcf | not_applicable | $6.38 / $16.41 / $39.57 | n/a | Royalty volume, operated margin, and technology licensing are modeled separately; infrastructure replacement cost remains embedded. | Utilization, incremental after-tax return on capital, or contract economics fall below the low-case assumptions. |
| Cash, investments, and contracted receivable | discounted_contract_value | not_applicable | $0.27 / $0.30 / $0.32 | n/a | The Bolt investment is excluded from the incremental project success value. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Producing plus undeveloped royalty estate | comparable_royalty_nav_residual | tpl_royalty_acquisitions_2024_2025, viper_sitio_2025 | $17.35 / $18.65 / $40.70 | risked range; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | The producing DCF is subtracted from total royalty NAV before visible and dormant residual values are added. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Producing plus undeveloped royalty estate | comparable_royalty_nav_residual | tpl_royalty_acquisitions_2024_2025, viper_sitio_2025 | $21.21 / $22.80 / $49.77 | risked range; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | The producing DCF is subtracted from total royalty NAV before visible and dormant residual values are added. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Surface land, existing uses, and future corridors | portfolio_discounted_unit_nav | tpl_surface_sale_2025, lb_reeves_800_2025, lb_lea_3000_2025, intrepid_south_ranch_2026 | $15.34 / $32.59 / $65.77 | p=100.0%; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | Existing contracted uses, residual land, and uncontracted corridors are separate economic claims. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Surface land, existing uses, and future corridors | milestone_probability_weighted_option | tpl_surface_sale_2025, lb_reeves_800_2025, lb_lea_3000_2025, intrepid_south_ranch_2026 | $0.80 / $4.46 / $13.48 | p=45.0%; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | Existing contracted uses, residual land, and uncontracted corridors are separate economic claims. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Data-center, power, and water co-location option | milestone_probability_weighted_option | not_applicable | $0.22 / $2.03 / $12.75 | p=6.0%; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | Only uncontracted incremental project economics are included. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Produced-water royalty, operated water, and technology | stage_gated_milestone_option | not_applicable | $-0.30 / $1.16 / $10.51 | p=10.0%; Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim. | Royalty volume, operated margin, and technology licensing are modeled separately; infrastructure replacement cost remains embedded. | The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress. |
| Corporate and realization reserve | conservative_reserve | not_applicable | $-5.00 / $-3.00 / $-1.00 | n/a | Applied once at the consolidated level. | The obligation, financing claim, tax, or realization friction is materially larger than the low-case reserve. |
| Produced-water royalty, operated water, and technology | depreciated_replacement_cost | not_applicable | $2.00 / $2.40 / $4.00 | n/a | Royalty volume, operated margin, and technology licensing are modeled separately; infrastructure replacement cost remains embedded. | Utilization, incremental after-tax return on capital, or contract economics fall below the low-case assumptions. |

### Investor-wisdom rules applied

- Horizon Kinetics: value the capital-free royalty structure and dormant assets, not their GAAP carrying amount.
- Horizon Kinetics/PrairieSky: third parties fund drilling, so acreage content and cash flow can expand without owner capital.
- Groundbreaker: the same non-depleting surface can host sequential tolls, but each toll is separated to prevent double counting.
- Klarman: current cash flows, comparable asset NAV, and uncontracted catalysts remain distinct layers.

### Limitations

- TPL does not disclose a tract-level split between producing, visible undeveloped, and dormant NRA; the residual reconciliation is portfolio-level.
- Royalty transaction values vary dramatically with production, operator, location, and inventory depth; the $75k high mark remains below developed Viper/Sitio marks but above TPL's recent acquisition marks.
- Data-center and desalination success values are not comparable NAV and remain probability weighted.



## What the price implies

At the stated terminal multiple, the price requires approximately **13.1%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 20x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $95.90 | $86.49 | $74.52 | $59.03 |
| Base | $132.37 | $118.79 | $101.56 | $79.37 |
| Bull | $177.43 | $158.66 | $134.91 | $104.41 |

## Decision explanation

TPL is an exceptional asset system. After marking its complete royalty acreage to actual royalty transactions and raising the surface-land cross-check, the quote is above the risked base value but below the high economic case. The market still requires strong royalty, produced-water, operated-water, and strategic-project execution, so the security remains a watch rather than a rejection of the asset quality.

**Strongest counter-explanation:** The component model may still understate repeated monetization of the same acreage, increasing water intensity, and data-center or power demand that converts faster than the milestone probabilities assume.

**Committee routing:** round_one_open — klarman_asset_value, hk, hohn

**Falsifiers:**

- Contracted data-center and power economics support materially more than the current option marks without TPL-funded capital.
- Produced-water royalties sustain growth above the base case while realized revenue per barrel remains stable.
- Operated-water investment cohorts demonstrate incremental after-tax ROIC materially above 30%.

## Economic claim

One post-December-2025-split common share has the same economic claim as every other common share. Q1 2026 diluted shares were approximately 69.0 million; TPL had net cash and an undrawn credit facility.
