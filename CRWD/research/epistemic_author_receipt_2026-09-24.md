# Epistemic author forecast receipt — CRWD — 2026-09-24

**Work ID:** `02ac4e724d95c942f9030caa`  
**Task:** `author_forecast` (re-publish on stable evidence gate)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `74891bf8c491c7d9128c18ab85d17a457e4e0db8c035bff0b4c7d093becbff4f` | <!-- pragma: allowlist secret -->
| input_sha | `bcd068dd9613ef819a2c0433b3fcca83c18c427a` |
| component_fingerprint | `7a98164fa9b6628c79e084acf62e6f53b327dbd7e06354785780736714433938` |
| contract_hash | `16ff1f43607c60258a11bd362368c743bf9ccfd3b840d3f6e2a75050d0121d9a` |

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

Changed artifact: `CRWD/investor-documents/DOWNLOAD_MANIFEST.json` (filing cadence for Q3 10-Q expectation ~2026-12-03, matching prior-year 2025-12-03).

## Mechanical checks (2026-09-24)

- `preflight_spec`: passed (`normalized_owner_earnings_ttm_m_v2`, `sec_companyfacts_ttm`)
- Historical replay Q3 FY2026 (period end 2025-10-31): **1,173.348 USD millions**
- Known Q1 FY2027 TTM at 2026-04-30: **1,505.198 USD millions** (above low-case anchor)
- Target Q3 FY2027 TTM: not observable at registration (`ttm_period_inputs_missing`)

## Draft

- **Path:** `CRWD/research/falsifier_drafts/02ac4e724d95c942f9030caa.json`
- **Spec ID:** `crwd-operating-owner-earnings-2027q3` (revision 2)
- **Status:** `awaiting_review`
- **Metric:** normalized_owner_earnings TTM at Q3 FY2027 vs low-case anchor **1,310.241 USD millions**
- **Threshold basis:** low-case `owner_earnings` proof node (TTM OCF minus TTM capex per `normalized_owner_earnings_ttm_m_v2`; FY2026 anchor from 10-K filed 2026-03-05)
- **Historical replay:** passed
- **Target period not observable at registration:** yes

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
