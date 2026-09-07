# ASML epistemic review receipt — 2026-09-07

**Work ID:** `f705288ed11a8de6f2813751`  
**Task:** `review_forecast` for `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/2750cd7278c04903d8dacb51.json`  
**Evidence hash:** `495966f4ea769d47479ab6f9f026a8efdf922ca3b345863a0cb38f59a8a202e3` <!-- pragma: allowlist secret -->  
**Input SHA:** `1547c5631614209e1f5e171e99d162dd18869542`

## Epistemic loop status

**COLLECTING** — 0 eligible scored outcomes; calibration **insufficient_outcomes** with `release_hash: null`. Diagnostic and legacy outcomes do not change stance, valuation, or sizing.

## Calibration receipt

| Field | Value |
|-------|-------|
| calibration_release_hash | null |
| route | quality_reinvestment\|owner_earnings_reinvestment_dcf |
| named_challenge | null |
| calibration_response | not_applicable |

## Review challenges

| Challenge | Result | Notes |
|-----------|--------|-------|
| Reviewer differs from author | passed | Author `marvin-cloud-agent` / `composer-2.5` (2026-09-02); reviewer `cursor-cloud-agent` (independent run, 2026-09-07) |
| Materiality | passed | Component is `entire_security`; low-case anchor $382.06/sh vs base $644.26/sh (41% equity impact if fires) |
| Period semantics | passed_with_note | FY2026 annual observation is correct for a 20-F-only filer; metric id retains TTM naming for registry compatibility |
| Look-ahead | passed | Information cutoff 2026-09-02; FY2026 20-F not yet filed; expected ~2027-02-28 per prior cadence |
| Source replay | failed | Registered `sec_companyfacts_ttm` adapter returns `ttm_period_inputs_missing` for FY2025 (ocf_rows=0): `_duration_rows` filters to 10-Q/10-K only and `source_unit=USD` while companyfacts are EUR |
| Forward source recipe | failed | Same adapter cannot resolve FY2026 at filing time; `fact_ledger` with evidenced FX (prior draft pattern) is the working path |

## Disposition

**Rejected** — spec `asml-opbiz-oe-2026fy-v3` (v3, revision 1). Threshold anchor and economic materiality are sound, but the frozen observation plan cannot mechanically resolve ASML annual 20-F filings. Author should re-author with `fact_ledger` adapter (or a 20-F-capable recipe) while preserving the 13,024.8M USD millions FY2025 low-case anchor.

## Facts

- FY2025 normalized owner earnings: **$13,024.8M** (OCF €12,658.5M minus capex €1,573.6M, converted at 2025-12-31 rate) — `ASML/research/valuation_fact_ledger.json`; `ASML/investor-documents/sec-edgar/20-F_20260225_rpt20251231_acc0001628280_26_011378.htm`
- Low-case proof trace locks owner_earnings at **13,024.81611167** USD millions — `ASML/research/valuation_contract.json`
- Independent `resolve_spec('ASML', spec, 2026-09-07)` for FY2025 and FY2026: **blocker `ttm_period_inputs_missing`**

## Inferences

- The 0.22 fire probability is not challenged on merit (semiconductor cycle can compress owner cash YoY), but the forecast is not scorable until the observation adapter matches issuer filing cadence

## Routed memory verification

- Observation 77414d5a ($13.0B FY2025 normalized owner earnings): **confirmed** against fact ledger and FY2025 20-F; context only, not promoted

## [HUMAN REVIEW]

- Stance and sizing remain in `human_decision.json` only
- Re-author with resolvable adapter before scheduled promoter can append
