# Epistemic author receipt — CRWD — 2026-09-30

| Field | Value |
|-------|-------|
| work_id | `02ac4e724d95c942f9030caa` |
| task_type | author_forecast |
| component_id | operating_business_and_net_assets |
| draft | `CRWD/research/falsifier_drafts/02ac4e724d95c942f9030caa.json` |
| status | awaiting_review |
| input_sha | `a7a9c9da3db6f6f46415fa3ec2a425eee2f57144` |
| evidence_hash | `edd83eb5e019f8112d8d29c86a2cc9c79d64230a9eca9ee6bb183b9607cf98dd` <!-- pragma: allowlist secret --> |
| contract_hash | `e4d69722ad9f65326e7098b3850633523dce3da8019362830811421e5505380e` |
| component_fingerprint | `7a98164fa9b6628c79e084acf62e6f53b327dbd7e06354785780736714433938` |

## Calibration / epistemic loop

- **health_state:** COLLECTING (not inferring learning from diagnostic-only rows).
- **calibration_status:** insufficient_outcomes; **release_hash:** null.
- **route:** quality_reinvestment / owner_earnings_reinvestment_dcf.
- **named_challenge:** none (`learning_status` collecting on active route; eligible_scored_outcomes=1 is not a release).
- **calibration_response:** not_applicable.

## Analysis receipt

| release_hash | route | named_challenge | response |
|--------------|-------|-----------------|----------|
| null | quality_reinvestment | null | not_applicable |

## Evidence boundary

Admitted artifact: `CRWD/investor-documents/DOWNLOAD_MANIFEST.json` (filing cadence; Q3 10-Q expectation ~2026-12-03).

## Mechanical checks (2026-09-30)

- `preflight_spec`: passed (`normalized_owner_earnings_ttm_m_v2`, `sec_companyfacts_ttm`)
- Historical replay Q3 FY2026 (period end 2025-10-31): **1,173.348 USD millions**
- Known Q1 FY2027 TTM at 2026-04-30: **1,505.198 USD millions** (above low-case anchor)
- Target Q3 FY2027 TTM: not observable at registration

## Draft

- **Spec ID:** `crwd-operating-owner-earnings-2027q3` (revision 3)
- **Threshold:** normalized owner earnings TTM **below 1,310.241 USD millions** at measurement end 2026-10-31
- **Probability (author):** 0.26 — not calibration-adjusted

Disposition: **success** — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
