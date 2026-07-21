# WBI valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract-backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (hash `bdfdb6cb…`).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_water_network` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $36.05 |
| `net_debt` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$11.54 |
| `contracted_growth_projects` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.00 |
| `capex_execution_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$1.00 |

Proof builder: `_system/scripts/build_wbi_contract_proofs.py`.

## Acceptance tests (curated gaps — status unchanged)

### `project_cohort_roic` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | 2025 Form 10-K reconciles **$254.0M** adjusted EBITDA, **$159.7M** operating cash flow, **$218.6M** investing outflow, **1.622M** bbl/d volume, and **2,651-mile / 201-facility** asset base. |
| source path | `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm` |
| calculation | No project-level invested capital, in-service date, utilization, or cohort EBITDA disclosed; incremental ROIC cannot be reproduced. |
| remaining uncertainty | Speedway and Devon cohort returns remain judgment in `contracted_growth_projects` range until register published. |
| affected components | `core_water_network`, `contracted_growth_projects`, `capex_execution_reserve` |
| valuation consequence | Proofs bound ranges; cohort ROIC gap does not block proof attachment. |
| falsifier | Mature cohorts fail to earn after-tax returns above cost of capital after maintenance capital. |

### `contract_quality` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | **~10.4-year** weighted-average remaining contract life; **~2.4M** dedicated acres; **71%** of long-term contracts ≥15-year initial term; fixed fees, dedications, MVCs, inflation escalators; top five customers **~51%** of 2025 water revenue. |
| source path | 2025 Form 10-K contract disclosure |
| calculation | Contracted vs merchant cash flows not separable by customer from public filings; renewal/termination rights not quantified. |
| remaining uncertainty | Low-case network multiple assumes partial merchant exposure. |
| affected components | `core_water_network`, `contracted_growth_projects` |
| valuation consequence | Duration supports infrastructure method; full contract-quality acceptance test not met. |
| falsifier | Protected revenue or margin materially below low-case share. |

### `refinancing_and_funding` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | March 2026 debt **~$1.475B** principal (**$825M** 2030 notes, **$600M** 2033 notes); cash **$50.7M**; covenants: interest coverage **≥2.50×**, net leverage **≤5.00×** (5.25× post-acquisition), senior secured leverage **≤3.50×**. |
| source path | Q1 2026 Form 10-Q debt footnote |
| calculation | Net-debt proof reconciles principal less cash across **123.456M** economic units; actual covenant ratios and stressed sources-and-uses bridge not published. |
| remaining uncertainty | 2026 **$430M–$490M** capex program funding under stress case not fully modeled. |
| affected components | `net_debt`, `contracted_growth_projects` |
| valuation consequence | Debt claim deducted once; refinancing stress remains monitoring item. |
| falsifier | Stressed interest coverage approaches **2.50×** or net leverage approaches **5.00×** without equity cure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `wbi_core_network`, `wbi_net_debt`, `wbi_contracted_growth`, `wbi_capex_reserve`; replacement-cost cross-check embedded in core network only. |
| source path | `WBI/research/valuation.json` |
| calculation | Additive base sum **$26.51/sh** = $36.05 − $11.54 + $3.00 − $1.00. |
| remaining uncertainty | None on overlap map. |
| affected components | All additive |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Q1 2026 adjusted EBITDA **$102.9M**; 2026 EBITDA guidance **$425M–$465M**; 2026 capex guidance **$430M–$490M**; debt principal **~$1.475B**; cash **$50.7M**; economic units **123.456M** (47.016M Class A + 76.440M OpCo); price **$34.46** (2026-07-15).

**Judgments (bounded):** Normalized EBITDA **$380M–$500M**; EV/EBITDA **8×–12×**; incremental contracted option **$0–$8/sh**; execution reserve **0–80%** of capex midpoint.

## Valuation consequence

Proof-complete additive schedule base **~$26.51 per share** vs price **$34.46** implies market prices execution above base component value. Lawrence seven-year base **3.2%** per year remains the stance gate; synthesis **6.59%** includes scenario and context weights. Security remains **watch**; no human capital decision recorded.
