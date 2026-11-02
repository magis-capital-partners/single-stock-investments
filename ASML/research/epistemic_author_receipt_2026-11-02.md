# Epistemic author forecast receipt — ASML

**Date:** 2026-11-02  
**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` — `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`  
**Spec:** `asml-opbiz-oe-2026fy-v5` (awaiting_review)

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `f4ab06cd94beaa5d174588de6fe9ae327d5d8235faf7dbad0ba89c233e4027a0` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `f45df0ae59501ca2bb8dce6cbcbd6f7a88c2cc0a` |
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
