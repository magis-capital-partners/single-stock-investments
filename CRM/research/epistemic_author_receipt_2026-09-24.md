# Epistemic author forecast receipt — CRM — 2026-09-24

**Work ID:** `01d9e3c381ada1ca50dc1fe5`  
**Task:** `author_forecast` (re-publish on stable evidence gate)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `3cd1d6a85dcd33550c22cc8c26ebd998cfc429499cbbb663f6b79ea0e5ee0faa` | <!-- pragma: allowlist secret -->
| input_sha | `9a0b24251e11002a3891821eefc71e4b1945481d` |
| component_fingerprint | `fa4138ee5767973d83a77e9c447898995514163bc8f91f59b4e0e8e6e709e86e` |
| contract_hash | `fd0fdcc2039ee575b427bb54578fe55961aa37b0071bc04167da9fcf88793d1f` |

## Epistemic loop

- **health_state:** COLLECTING
- **calibration_status:** insufficient_outcomes
- **eligible_scored_outcomes:** 0

Diagnostic scored outcomes do not count as learning. Calibration cannot yet change analysis weights or thresholds.

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

## Evidence boundary

Changed artifact: `CRM/investor-documents/DOWNLOAD_MANIFEST.json` (stable download index; Q3 FY2027 10-Q expected ~2026-12-04 per prior-year filing cadence).

## Mechanical checks (2026-09-24)

- `preflight_spec`: passed (`normalized_owner_earnings_ttm_m_v2`, `sec_companyfacts_ttm`)
- Historical replay Q3 FY2026 (period end 2025-10-31): **12,895 USD millions**
- Interim Q1 FY2027 TTM at 2026-04-30: **14,661 USD millions** (above low-case anchor)
- Target Q3 FY2027 TTM: not observable at registration (`ttm_period_inputs_missing`)

## Draft

- **Path:** `CRM/research/falsifier_drafts/01d9e3c381ada1ca50dc1fe5.json`
- **Spec ID:** `crm-operating-business-oe-2026q3-v2` (revision 2)
- **Status:** `awaiting_review`
- **Metric:** normalized owner earnings TTM at Q3 FY2027 vs low-case anchor **14,402 USD millions**
- **Threshold basis:** low-case `owner_earnings` proof node (TTM OCF minus TTM capex per `normalized_owner_earnings_ttm_m_v2`)
- **Historical replay:** passed
- **Target period not observable at registration:** yes

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
