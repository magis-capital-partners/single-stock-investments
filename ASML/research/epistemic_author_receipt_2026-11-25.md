# Epistemic author forecast receipt — ASML

**Date:** 2026-11-25  
**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` — `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`  
**Spec:** `asml-opbiz-oe-2026fy-v5` (revision 33, `awaiting_review`)

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `5603e3538d3cf15bfd5123951f756aebff878dfcdd999c31000aa32f975c3cfd` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `f0433632ae668ef30c9e3aa863653a88e180bd83` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| contract_hash | `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9` |

## Calibration / epistemic loop

- **health_state:** COLLECTING (not learning from diagnostic-only outcomes)
- **calibration_status:** insufficient_outcomes; **calibration_release_hash:** null
- **route:** quality_reinvestment / `owner_earnings_reinvestment_dcf`
- **named_challenge:** none (insufficient eligible outcomes on active route)
- **calibration_response:** not_applicable

## Remediation (prior review of draft 2750cd7278c04903d8dacb51)

1. **source_recipe_incompatible** — addressed: observation plan uses `fact_ledger` and `source_hint` `normalized_owner_earnings_m`; `sec_companyfacts_ttm` cannot resolve ASML 20-F EUR duration rows.
2. **unit_mismatch** — addressed: canonical and source units are USD millions; ledger field carries evidenced EUR/USD `fx_conversion` from FY2025 20-F.
3. **historical_replay_not_adapter_verified** — addressed: `resolve_spec` with cloned `measurement_period_end` 2025-12-31 returns 13,024.816 USD millions; forward FY2026 returns `period_end_mismatch` (expected before the 20-F).

## Disposition

Author forecast frozen at `status=awaiting_review`. No edit to canonical `falsifier_specs.json`. Routed memory observation 77414d5a verified against `valuation_fact_ledger.json` only; not promoted as belief.