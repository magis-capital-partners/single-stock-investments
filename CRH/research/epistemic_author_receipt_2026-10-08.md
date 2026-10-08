# Epistemic author forecast receipt — CRH — 2026-10-08

**Work ID:** `0c6457af11f4a63293a9b6da`  
**Task:** `author_forecast`  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `fe55176ec6ca1728564108460f5b02bad9f92a73bfe5faf17aaf435a623e6190` <!-- pragma: allowlist secret --> |
| primary_evidence_hash | `7914038ff37d95a7f4b33e37348e4fedf0e0048f87124c72c866d51d8e096c2a` <!-- pragma: allowlist secret --> |
| input_sha | `572896eb0b467719699e9bcafb7564cbf39a454b` <!-- pragma: allowlist secret --> |
| component_fingerprint | `bec50643c728d39be77d8deeccb51f780006382bbed0c4787ea24ef3ad3e4353` |
| contract_hash | `cede8cb42fa5a67ee4e5c63011d4de1bcdf0f025986fba494cfa97e99806c707` |

## Epistemic loop

- **health_state:** COLLECTING (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED)
- **calibration_status:** insufficient_outcomes
- **eligible_scored_outcomes:** 1 on `owner_earnings_reinvestment_dcf` (below minimum 20; do not infer weights from diagnostics)

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

Calibration cannot yet change analysis weights or thresholds.

## Routed memory verification

No routed observations in the admitted manifest.

## Draft

- **Path:** `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json`
- **Spec:** `crh-operating-owner-earnings-2026q3-v1` (revision 1)
- **Status:** `awaiting_review`
- **Claim:** TTM normalized owner earnings at 2026-09-30 **< 2,912 USD millions**
- **Historical replay:** Q3 FY2025 TTM **2,605 USD millions** (`sec_companyfacts_ttm`); Q1 FY2026 TTM **2,999 USD millions** (interim, not target period)
- **Observable after:** ~2026-11-05 (Q3 FY2026 10-Q cadence per `CRH/investor-documents/DOWNLOAD_MANIFEST.json`)

## Work receipt

| disposition | published_input_sha |
|---|---|
| success | `572896eb0b467719699e9bcafb7564cbf39a454b` <!-- pragma: allowlist secret --> |

Independent review required before promotion to `falsifier_specs.json`.
