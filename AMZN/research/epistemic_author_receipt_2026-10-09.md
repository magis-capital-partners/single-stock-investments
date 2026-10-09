# AMZN epistemic author receipt — 2026-10-09

**Work ID:** `019de6b6bba30e2236e36604`  
**Task:** `author_forecast` for `cycle_reserve`  
**Draft:** `AMZN/research/falsifier_drafts/019de6b6bba30e2236e36604.json`  
**Evidence hash:** `2b355985cfe9bcbae053fa16abeeb0eadbda9eed5330a4cec52f99313b609132` <!-- pragma: allowlist secret -->  
**Input SHA:** `400490464c74935044ba4aeb2198b1bfc4759bfb` <!-- pragma: allowlist secret -->

## Epistemic loop status

**COLLECTING** — 1 eligible scored outcome globally; calibration **insufficient_outcomes** with `release_hash: null`. Diagnostic outcomes do not change stance, valuation, or sizing.

## Calibration receipt

| Field | Value |
|-------|-------|
| calibration_release_hash | null |
| route | capital_cycle\|midcycle_capacity_value |
| named_challenge | null |
| calibration_response | not_applicable |

## Author deliverable

v3 spec `amzn-cycle-reserve-owner-earnings-2026q3-v2` (revision 2), status **awaiting_review**. Fires if Q3 FY2026 TTM normalized owner earnings resolve below **-10,000 USD millions** via `normalized_owner_earnings_ttm_m_v2` / `sec_companyfacts_ttm`. Historical replay Q3 FY2025 TTM **10,560 USD millions**; Q1 FY2026 TTM **-2,472 USD millions** verified at authoring time.

## Routed memory verification

- TTM OCF **$148.5B** vs capex **$151.0B**: **confirmed** against Q1 2026 10-Q and adapter (not promoted).
- Normalized owner cash **$5.35/sh** and hold stance: **context only** (Lawrence normalization uses sustainable capex assumption).
- Legacy runway draft `0679c1f233147debec1dbf64`: **superseded** by published zero-threshold runway spec; not reused here.

## Disposition

Author success — independent review required before promoter appends to `falsifier_specs.json`.
