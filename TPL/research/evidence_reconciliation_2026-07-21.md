# TPL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_operations` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $88.35 |
| `existing_surface_and_easement_operations` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $14.89 |
| `produced_water_royalties` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $43.25 |
| `cash_and_investments` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $4.32 |
| `operated_water_sales` | legacy_sensitivity | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $16.41 |
| `contracted_data_center_receivable` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.30 |
| `visible_royalty_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $18.65 |
| `dormant_royalty_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $22.80 |
| `residual_surface_land_option` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $32.59 |
| `future_infrastructure_corridors` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $4.46 |
| `data_center_power_water_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $2.03 |
| `desalination_and_water_technology_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $1.16 |
| `realization_and_corporate_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$3.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Thirteen additive components with unique `overlap_key` values; `water_infrastructure_cross_check` embedded in `operated_water_sales`. |
| source path | `TPL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$246.21/sh** = additive components at proof outputs; producing royalty DCF subtracted before undeveloped royalty residual allocation. |
| remaining uncertainty | Tract-level NRA roll-forward and milestone capital waterfalls remain judgment-heavy. |
| affected components | All thirteen additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 company-defined owner cash **$7.02/sh** after fixed-asset spending and share-based compensation; Q1 2026 cash **$247.6M** plus **$50M** equity-method investment. |
| source path | `TPL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001811074_26_000018.htm`, `10-Q_20260506_rpt20260331_acc0001811074_26_000035.htm` |
| calculation | Producing proof: $411.7M royalty revenue × 78% margin × 19.0× capitalization ≈ **$88.35/sh**. Cash proof: ($247.6M + $50M) / 69.027M ≈ **$4.31/sh**. |
| remaining uncertainty | Capitalization multiples and comparable NRA marks are bounded judgments, not filing marks. |
| affected components | Operating streams, cash, royalty inventory |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Trailing four-quarter owner cash per share falls below **$5.50** for two reporting periods without offsetting asset realization. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | No debt disclosed on FY2025 balance sheet; realization reserve **−$3.00/sh** base; desalination low case allows negative milestone value after remaining cost. |
| source path | `10-K_20260218`, `10-Q_20260506` |
| calculation | Reserve proof uses explicit per-share judgment band **−$5.00 / −$3.00 / −$1.00**; no GAAP book used as dhando floor. |
| remaining uncertainty | Tax and transaction friction on latent land and royalty monetization remain widest bands. |
| affected components | `realization_and_corporate_reserve`, milestone options |
| valuation consequence | Downside claims reconciled; 1888 Assigned assets remain off balance sheet at zero. |
| falsifier | Material debt or preferred claim appears without corresponding reserve adjustment. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; producing royalties subtracted before undeveloped inventory residual; Bolt investment and contracted receivable excluded from data-center option. |
| source path | `TPL/research/valuation.json`, `authorized_evidence.json` |
| calculation | `double_counting_flags` empty; embedded water cross-check not additive. |
| remaining uncertainty | Tract-level inventory split between visible and dormant remains provisional (45%/55%). |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Curated follow-up gaps (partially met)

| Gap ID | Status | Progress |
|--------|--------|----------|
| `tract_level_royalty_inventory` | partially_met | FY2025 10-K confirms ~224,000 total NRA; proofs use comparable marks and producing-DCF residual split; tract roll-forward still absent. |
| `water_economic_separation` | partially_met | Produced-water royalty and operated water proofs use separate revenue anchors; infrastructure cross-check embedded only. |
| `option_milestones_and_capital` | partially_met | Milestone proofs encode success probability and remaining cost; contracted cash flows and ownership waterfalls still thin. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated revenue **$798.2M**; oil and gas royalties **$411.7M**; easements **$78.2M**; produced-water royalty **~$124M**; operated water sales **~$170M**; cash **$247.6M** and equity-method investment **$50M** at Q1 2026; **~882,000** surface acres and **~224,000** NRA per Item 1; **69.027M** diluted shares FY2025.

**Judgments (bounded):** Revenue capitalization multiples 9.9–31.3× on producing royalties; comparable NRA marks **$25k/$40k/$75k** with 45%/55% visible/dormant split; surface marks **$1,500–$5,718/acre** with 10–20% friction; milestone success probabilities 2–65% by project.

## Valuation consequence

Proof-complete additive schedule base case **~$246 per share** vs price **~$414** implies component economic value below market; Lawrence seven-year base **−8.2%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
