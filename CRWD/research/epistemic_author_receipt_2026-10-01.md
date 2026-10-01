# Epistemic author forecast receipt — CRWD — 2026-10-01

**Work ID:** `02ac4e724d95c942f9030caa`  
**Task:** `author_forecast` (re-publish on stable evidence gate)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `a0a9c5dfd02ff97c6e3de3b0a4a8d3efa09b64d34e94fa5d0bc547d4aaa37967` | <!-- pragma: allowlist secret -->
| input_sha | `25038faf706f9c0d67e99d5957bd7d729d12d44c` |
| component_fingerprint | `7a98164fa9b6628c79e084acf62e6f53b327dbd7e06354785780736714433938` |
| contract_hash | `e4d69722ad9f65326e7098b3850633523dce3da8019362830811421e5505380e` |

## Epistemic loop

- **health_state:** COLLECTING (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED)
- **calibration_status:** insufficient_outcomes
- **eligible_scored_outcomes:** 1

Diagnostic scored outcomes do not count as learning. Calibration cannot yet change analysis weights, thresholds, or sizing.

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

## Evidence boundary

Changed artifact: `CRWD/investor-documents/DOWNLOAD_MANIFEST.json` (sha256 `75b5f9ea14faa9ec33c36b8de30a064f7e7d259997a9215002b8757d15004b45`). Used for Q3 10-Q filing cadence expectation (~2026-12-03, matching prior-year 2025-12-03).

## Mechanical checks (2026-10-01)

- `preflight_spec`: passed (`normalized_owner_earnings_ttm_m_v2`, `sec_companyfacts_ttm`)
- Historical replay Q3 FY2026 (period end 2025-10-31): **1,173.348 USD millions**
- Known Q1 FY2027 TTM at 2026-04-30: **1,505.198 USD millions** (above low-case anchor)
- Target Q3 FY2027 TTM: not observable at registration

## Draft

- **Path:** `CRWD/research/falsifier_drafts/02ac4e724d95c942f9030caa.json`
- **Spec ID:** `crwd-operating-owner-earnings-2027q3` (revision 3)
- **Status:** `awaiting_review`
- **Metric:** normalized owner earnings TTM at Q3 FY2027 vs low-case anchor **1,310.241 USD millions**
- **Threshold basis:** low-case `owner_earnings` proof node (TTM OCF minus TTM capex per `normalized_owner_earnings_ttm_m_v2`; FY2026 anchor from 10-K)
- **Historical replay:** passed
- **Target period not observable at registration:** yes

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
