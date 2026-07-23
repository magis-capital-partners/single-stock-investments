# WBI valuation evidence reconciliation — 2026-07-23

**Scope:** Contract backfill refresh per authorized evidence packet (DOWNLOAD_MANIFEST + authorized_evidence).

## Proofs attached (unchanged evidence packet)

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `core_water_network` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $36.05 |
| `net_debt` | net_asset_value@1.0 | bounded_estimate | −$11.54 |
| `contracted_growth_projects` | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.00 |
| `capex_execution_reserve` | net_asset_value@1.0 | bounded_estimate | −$1.00 |

Proof builder: `_system/scripts/build_wbi_contract_proofs.py`. Additive base sum **$26.51/sh**.

## Acceptance tests (curated gaps)

### `project_cohort_roic` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | FY2025 Form 10-K: **$254.0M** adjusted EBITDA, **$159.7M** operating cash flow, **$218.6M** investing outflow, **1.622M** bbl/d volume, **2,651-mile / 201-facility** base. Q1 2026 10-Q: **$102.9M** adjusted EBITDA on **~2.5M** bbl/d; Kraken completion cited as organic growth driver. |
| source path | `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm`; `WBI/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209490.htm` |
| calculation | **Consolidated proxy only:** FY2025 OCF **$159.7M** on **$218.6M** gross investing outflow implies ~73% cash recovery in-year (not ROIC). No project-level invested capital, in-service date, utilization, or cohort EBITDA disclosed; incremental ROIC cannot be reproduced by cohort. |
| remaining uncertainty | Speedway and Devon cohort returns remain judgment in `contracted_growth_projects` range until a register is published. |
| affected components | `core_water_network`, `contracted_growth_projects`, `capex_execution_reserve` |
| valuation consequence | Proofs bound ranges; cohort ROIC gap does not block proof attachment. |
| falsifier | Mature cohorts fail to earn after-tax returns above cost of capital after maintenance capital. |

### `contract_quality` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | **~10.4-year** weighted-average remaining contract life; **~2.4M** dedicated acres; **71%** of long-term contracts with initial primary term **≥15 years**; fixed per-barrel fees, acreage dedications, MVCs, CPI-linked escalators; top five customers **~51%** of 2025 water revenue (Devon, Permian Resources, bpx, Mewbourne, EOG). |
| source path | `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm` (Business — Sources of Revenue; customer concentration) |
| calculation | **Bounded split [Assumption]:** low **75%** contracted / **25%** merchant volume exposure in normalized EBITDA multiple; base **85% / 15%**; high **90% / 10%**. Filings do not separate contracted vs merchant cash flows by customer; renewal and termination rights not quantified. |
| remaining uncertainty | Low-case network multiple assumes partial merchant exposure; full acceptance test (separate contracted and merchant valuation paths) not met. |
| affected components | `core_water_network`, `contracted_growth_projects` |
| valuation consequence | Duration supports infrastructure method; contract-quality acceptance test partially met via explicit split assumptions in proofs. |
| falsifier | Protected revenue or margin materially below low-case contracted share. |

### `refinancing_and_funding` — open (partially_met)

| Field | Content |
|---|---|
| status | open |
| evidence | March 2026 debt principal **~$1.475B** (**$825M** 6.875% notes due **2030**, **$600M** 6.50% notes due **2033** per debt footnote); cash **$50.7M**; **$500M** revolving credit facility maximum; covenants: consolidated interest coverage **≥2.50×**, net leverage **≤5.00×** (5.25× post-acquisition window), senior secured leverage **≤3.50×**. |
| source path | `WBI/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209490.htm` (debt footnote; Revolving Credit Facility covenants) |
| calculation | **Stress sources-and-uses bridge [Assumption]:** |

**2026 stress bridge (base filing anchors, judgment on rates and capex timing)**

| Line | Low / stress | Base | Source |
|------|--------------|------|--------|
| Adjusted EBITDA (2026 guide mid) | $425M | $445M | Company guidance, Q1 2026 10-Q |
| Q1 2026 operating cash flow (annualized check) | $380M | $380M | $95.1M × 4, 10-Q cash flow statement |
| Growth capex program | $490M | $460M | $430M–$490M guidance |
| Maintenance / other investing | **[Assumption]** $50M | **[Assumption]** $40M | Not separately disclosed |
| Gross funding need (capex − OCF) | ~$160M | ~$120M | Arithmetic |
| Liquidity: cash + revolver headroom | ~$551M | ~$551M | $50.7M cash + $500M revolver capacity |
| Fixed notes maturity before 2030 | $0 | $0 | 2030/2033 bullet maturities |
| Implied net leverage (net debt / EBITDA) | ~3.8× | ~3.2× | $1.424B net debt ÷ EBITDA |
| Implied interest coverage (EBITDA / interest) | ~3.0× | ~3.8× | **[Assumption]** ~$140M interest at stress rates vs ~$115M base |

| remaining uncertainty | Revolver drawn amount at quarter-end not fully parsed from HTML extract; stressed bridge uses capacity not utilization. Equity dilution path not modeled. |
| affected components | `net_debt`, `contracted_growth_projects` |
| valuation consequence | Debt claim deducted once in `net_debt` proof; bridge shows covenant headroom under filing-backed EBITDA and disclosed limits, but full acceptance test (explicit equity-dilution path) not met. |
| falsifier | Stressed interest coverage approaches **2.50×** or net leverage approaches **5.00×** without equity cure; revolver fully drawn with capex overruns. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `wbi_core_network`, `wbi_net_debt`, `wbi_contracted_growth`, `wbi_capex_reserve`. |
| source path | `WBI/research/valuation.json` |
| calculation | Additive base sum **$26.51/sh** = $36.05 − $11.54 + $3.00 − $1.00. |
| remaining uncertainty | None on overlap map. |
| affected components | All additive |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Q1 2026 adjusted EBITDA **$102.9M**; 2026 EBITDA guidance **$425M–$465M**; 2026 capex guidance **$430M–$490M**; debt principal **~$1.475B**; cash **$50.7M**; economic units **123.456M** (47.016M Class A + 76.440M OpCo); covenant floors **2.50×** interest coverage and **5.00×** net leverage.

**Judgments (bounded):** Normalized EBITDA **$380M–$500M**; EV/EBITDA **8×–12×**; contracted share **75%–90%**; incremental contracted option **$0–$8/sh**; execution reserve **0–80%** of capex midpoint; stress interest **~$115M–$140M**.

## Valuation consequence

Proof-complete additive schedule base **~$26.51 per share** vs prior thesis-card price **$34.75** implies market prices execution above base component value. Lawrence seven-year base **3.0%** per year remains the stance gate; synthesis **6.49%** includes scenario and context weights. Security remains **watch**; three curated evidence gaps stay open with filing-grounded partial progress. No human capital decision recorded.
