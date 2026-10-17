# ASML epistemic author receipt — 2026-10-14

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | `author_forecast` |
| component_id | `operating_business_and_net_assets` |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| spec_id | `asml-opbiz-oe-2026fy-v4` |
| status | `awaiting_review` |
| evidence_hash | `16c81b65c08514d0b5b065ca071835e6b34fbb13789a0df1e0e1fb4b6a23f308` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `a77e6b45e8a174c159bba0578319a6b5caa5e93c` | <!-- pragma: allowlist secret -->
| contract_hash | `8b786852dfd6951955be063e99baece87e2ce373a45f5ea9a8ef7a895b768f1c` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| calibration_release_hash | null |
| route | `quality_reinvestment` |
| named_challenge | null |
| calibration_response | `not_applicable` |

**Epistemic loop:** `health_state=COLLECTING`; `calibration_status=insufficient_outcomes`; `release_hash=null`. Calibration cannot change this analysis.

**Rejection remediation (2750cd7278c04903d8dacb51):**

1. **source_recipe_incompatible:** observation plan uses `source_adapter=fact_ledger` and `source_hint=normalized_owner_earnings_m` (20-F accepted forms). Not `sec_companyfacts_ttm`.
2. **unit_mismatch:** canonical and source units are USD millions; EUR source values converted in `ASML/research/valuation_fact_ledger.json`.
3. **historical_replay_not_adapter_verified:** independent `resolve_spec` with measurement end 2025-12-31 returns **13,024.816 USD millions** via `fact_ledger` (verified 2026-10-14).

**Forecast:** FY2026 normalized owner earnings **below 13,024.816 USD millions** (comparator `lt`); probability **0.22**; observable after **2027-02-28**.

**Routed memory:** Observation `77414d5a` verified against ledger and FY2025 20-F; not promoted.

**Disposition:** success (draft frozen; separate reviewer required).
