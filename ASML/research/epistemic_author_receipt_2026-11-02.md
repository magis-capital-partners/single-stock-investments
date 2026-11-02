# Epistemic author forecast receipt — ASML

**Date:** 2026-11-02  
**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` — `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`  
**Spec:** `asml-opbiz-oe-2026fy-v5` (awaiting_review)

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `cef89f34b0c4713b1899b0f3d883703232bc26f7c3a348be85708975742b0400` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `444d036a1f77851845e9b59b281c85ae1eb76f6c` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| contract_hash | `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9` |

## Calibration / epistemic loop

- **health_state:** COLLECTING (not learning from diagnostic-only outcomes)
- **calibration_status:** insufficient_outcomes; **calibration_release_hash:** null
- **route:** quality_reinvestment
- **named_challenge:** none
- **calibration_response:** not_applicable

## Remediation (prior review of draft 2750cd7278c04903d8dacb51)

1. **source_recipe_incompatible** — addressed: `fact_ledger` adapter + `normalized_owner_earnings_m`; preflight passed 2026-11-02.
2. **unit_mismatch** — addressed: USD millions canonical/source units with ledger `fx_conversion`.
3. **historical_replay_not_adapter_verified** — addressed: `resolve_spec` FY2025 → 13,024.816M USD; FY2026 → `period_end_mismatch` (expected at registration).

## Disposition

Author forecast frozen at `status=awaiting_review`. No edit to canonical `falsifier_specs.json`.
