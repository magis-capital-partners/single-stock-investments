# Epistemic author forecast receipt — CRWD — 2026-09-26

**Work ID:** `02ac4e724d95c942f9030caa`  
**Task:** `author_forecast` (stable evidence gate; see `research_agent_manifest.json`)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | see manifest `evidence_hash` field |
| input_sha | `586ddfdd35def5da48b6cfc7223cec3b8729e1e0` |
| component_fingerprint | `7a98164fa9b6628c79e084acf62e6f53b327dbd7e06354785780736714433938` |
| contract_hash | `e4d69722ad9f65326e7098b3850633523dce3da8019362830811421e5505380e` |

## Epistemic loop

- **health_state:** COLLECTING (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED)
- **calibration_status:** insufficient_outcomes
- **eligible_scored_outcomes:** 1 globally; active route `quality_reinvestment` / `owner_earnings_reinvestment_dcf` has `learning_status: collecting` with no named challenge

Diagnostic scored outcomes do not count as learning. Calibration cannot yet change analysis weights or thresholds.

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

## Evidence boundary

Changed artifact: `CRWD/investor-documents/DOWNLOAD_MANIFEST.json` (Q3 FY2026 10-Q filed 2025-12-03; Q3 FY2027 expectation ~2026-12-03).

## Mechanical checks (2026-09-26)

- `preflight_spec`: passed (`normalized_owner_earnings_ttm_m_v2`, `sec_companyfacts_ttm`)
- Historical replay Q3 FY2026 (period end 2025-10-31): **1,173.348 USD millions**
- Known Q1 FY2027 TTM at 2026-04-30: **1,505.198 USD millions** (above low-case anchor 1,310.241)
- Target Q3 FY2027 TTM: not observable at registration

## Draft

- **Path:** `CRWD/research/falsifier_drafts/02ac4e724d95c942f9030caa.json`
- **Spec ID:** `crwd-operating-owner-earnings-2027q3` (revision 3)
- **Status:** `awaiting_review`
- **Falsifier:** TTM normalized owner earnings at Q3 FY2027 below low-case proof anchor **1,310.241 USD millions** (comparator `lt`)

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
