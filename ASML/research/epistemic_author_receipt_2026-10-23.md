# ASML epistemic author receipt — 2026-10-23

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | `author_forecast` |
| component_id | `operating_business_and_net_assets` |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| spec_id | `asml-opbiz-oe-2026fy-v4` |
| spec_revision | 22 |
| status | `awaiting_review` |
| evidence_hash | `6e4e4df6101646b39843968807df322a094f9985d1209403bc75d0c51ca1080f` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `cf3ba63e1817faeec62f7777d2f4ca0d45332234` | <!-- pragma: allowlist secret -->
| contract_hash | `5512118aa814b15d424031b02216db92e04fb7beaf896813266b3c6c1fc578a6` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| calibration_release_hash | null |
| route | `quality_reinvestment` |
| named_challenge | null |
| calibration_response | `not_applicable` |

**Epistemic loop:** `health_state=COLLECTING`; `calibration_status=insufficient_outcomes`; `release_hash=null`. Calibration cannot change this analysis.

**Rejection remediation (2750cd7278c04903d8dacb51):**

1. **source_recipe_incompatible:** observation plan uses `source_adapter=fact_ledger` and `source_hint=normalized_owner_earnings_m` with accepted forms 20-F/20-F/A. Not `sec_companyfacts_ttm`.
2. **unit_mismatch:** canonical and source units are USD millions; EUR source values converted in `ASML/research/valuation_fact_ledger.json`.
3. **historical_replay_not_adapter_verified:** independent `resolve_spec` with measurement end 2025-12-31 returns **13,024.816 USD millions** via `fact_ledger` (verified 2026-10-23).

**Forecast:** FY2026 normalized owner earnings **below 13,024.816 USD millions** (comparator `lt`); probability **0.22**; observable after **2027-02-28**.

**Routed memory:** Observation `77414d5a153b58ee0e6b0748` verified against ledger and FY2025 20-F accession `0001628280-26-011378`; not promoted.

**Disposition:** success (draft frozen; separate reviewer required).
