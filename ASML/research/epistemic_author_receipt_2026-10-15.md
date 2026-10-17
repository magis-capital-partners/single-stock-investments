# ASML epistemic author receipt — 2026-10-15

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | `author_forecast` |
| component_id | `operating_business_and_net_assets` |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| spec_id | `asml-opbiz-oe-2026fy-v4` (revision 15) |
| status | `awaiting_review` |
| evidence_hash | `7a61c937fdf34df3dd7693864b0eb5fc9a77160b667903f1ac304f2e7dcdd837` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `7bec3000349b84ab76ef1c79a98b8691749fe400` |
| contract_hash | `8b786852dfd6951955be063e99baece87e2ce373a45f5ea9a8ef7a895b768f1c` |
| calibration_release_hash | null |
| route | `quality_reinvestment` |
| named_challenge | null |
| calibration_response | `not_applicable` |

**Calibration:** Epistemic loop `health_state=COLLECTING`; `calibration_status=insufficient_outcomes`; `release_hash=null`. Calibration cannot change this analysis.

**Rejected-draft remediation:** Prior draft `2750cd7278c04903d8dacb51` used `sec_companyfacts_ttm` (10-Q/10-K only, EUR rows empty for ASML 20-F). This revision uses `fact_ledger` / `normalized_owner_earnings_m` with USD millions and evidenced FX on the ledger field.

**Adapter replay:** `resolve_spec` FY2025 (measurement end 2025-12-31) → 13,024.816 USD millions; `preflight_spec` passed.

**Disposition:** success (draft frozen for independent review; no edit to `falsifier_specs.json`).
