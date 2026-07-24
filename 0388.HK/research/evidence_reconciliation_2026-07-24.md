# 0388.HK valuation evidence reconciliation — 2026-07-24

**Scope:** Contract backfill close per authorized evidence packet `02af38d6ec6783a55b91dbb913088864c305797e904ed8431474a916a7572b06`. // pragma: allowlist secret

## Proofs attached

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `core_engine` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | HK$243.82 |
| `reinvestment_or_assets` | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | HK$36.57 |
| `net_financial_claims` | net_asset_value@1.0 | bounded_estimate | HK$14.63 |
| `downside_reserve` | midcycle_capacity_value@1.0 | bounded_estimate | −HK$36.57 |

Proof builder: `_system/scripts/build_0388_contract_proofs.py`. Additive base sum **HK$258.45/sh**.

## Acceptance test — economic ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping additive components map croupier fee infrastructure, Connect/data reinvestment, net financial claims after clearing pass-through, and peak-cycle volume reserve. |
| source path | `0388.HK/official-reports/annual-reports/annual_report_fy2024.pdf`; `0388.HK/investor-documents/ir-0388.hk/260316sr_e.pdf`; `0388.HK/investor-documents/ir-0388.hk/202605_HKEX-IR-Pack_v5-_vF_.pdf` |
| calculation | Unique overlap keys: `core_engine`, `reinvestment_or_assets`, `net_financial_claims`, `downside_reserve`. Base sum HK$243.82 + HK$36.57 + HK$14.63 − HK$36.57 = **HK$258.45/sh**. |
| remaining uncertainty | Full-tier OCR text extract pending for segment fee bridge; equity and share count use FY2024 annual with [HUMAN REVIEW] on latest count. |
| affected components | All additive |
| valuation consequence | Contract status **decision_grade**; value_per_share base **HK$258.45/sh** vs price **HK$383**. |
| falsifier | New material fee stream or balance-sheet claim added without unique overlap_key and proof graph. |

## Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Connect/LME economics embedded in `core_engine`; reinvestment sized separately; clearing pass-through excluded from net financial claim. |
| source path | `0388.HK/research/valuation.json` → `economic_value.component_groups` |
| calculation | No double_counting_flags in component coverage audit. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | Duplicate overlap_key on additive component. |

## Facts vs judgments

**Facts (locked):** FY2024 revenue **HK$22.4B** (+9% YoY); profit attributable **HK$13.1B**; basic EPS **HK$10.32**; core revenue **HK$20.6B**; headline ADT **HK$131.8B** (+26% YoY); FY2025 EPS **HK$14.05**; DPS **HK$12.52**; issued shares **~1,264M**.

**Judgments (bounded):** Normalized owner cash **HK$11/sh**; growth years 1–5 **0%–7%**; peak-cycle reserve **−HK$22.88 to −HK$44.99/sh**; net financial claim **HK$0–HK$35.96/sh**.

## Valuation consequence

Proof-complete additive schedule base **~HK$258.45 per share** vs thesis-card price **~HK$383** implies market prices sustained peak-cycle earnings above normalized component value. Lawrence seven-year base **0.0%** per year and total synthesis **−0.15%** remain stance gates. Contract status **decision_grade**. Security remains **watch** pending human decision authority.
