# ASML epistemic author receipt — 2026-10-16

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | `author_forecast` |
| component_id | `operating_business_and_net_assets` |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| spec_id | `asml-opbiz-oe-2026fy-v4` (revision 16) |
| status | `awaiting_review` |
| evidence_hash | `4a2ffd60895a38db9a1e38ea5aaa22507440f8f278193abdd42dc7f563d6f774` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `783834c03887b9a112c23d11b13df36f20b1243a` |
| contract_hash | `8b786852dfd6951955be063e99baece87e2ce373a45f5ea9a8ef7a895b768f1c` |
| calibration_release_hash | null |
| route | `quality_reinvestment` |
| named_challenge | null |
| calibration_response | `not_applicable` |

**Calibration:** Epistemic loop `health_state=COLLECTING`; `global_status=insufficient_outcomes`; `release_hash=null`. Calibration cannot change this analysis.

**Rejected-draft remediation (2750cd7278c04903d8dacb51):** Observation plan uses `fact_ledger` with `source_hint` `normalized_owner_earnings_m`, canonical USD millions, and FY 20-F forms. Prior `sec_companyfacts_ttm` path is not used.

**Evidence boundary:** Admitted packet per `research_agent_manifest.json` (DOWNLOAD_MANIFEST.json). Routed memory observation `77414d5a` verified against `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m` and FY2025 20-F companyfacts.

**Adapter replay:** `preflight_spec` passed; ledger normalized owner earnings 13,024.816 USD millions (FY2025 measurement end 2025-12-31).

**Disposition:** success (draft frozen for independent review; no edit to `falsifier_specs.json`).
