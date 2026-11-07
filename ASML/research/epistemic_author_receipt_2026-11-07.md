# Epistemic author forecast receipt — ASML

**Date:** 2026-11-07  
**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` — `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`  
**Spec:** `asml-opbiz-oe-2026fy-v5` (awaiting_review)

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `febf68083dd544af607c4b3c2c9f90dfff1f660251b16dd131041f0a758d96c0` | <!-- pragma: allowlist secret -->
| epistemic_input_sha | `9729bd3a39d0546e46dbc40da5595c275f4e57d3` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| contract_hash | `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9` |

## Calibration / epistemic loop

- **health_state:** COLLECTING (not learning from diagnostic-only outcomes)
- **calibration_status:** insufficient_outcomes; **calibration_release_hash:** null
- **route:** quality_reinvestment
- **named_challenge:** none
- **calibration_response:** not_applicable

## Remediation (prior review of draft 2750cd7278c04903d8dacb51)

1. **source_recipe_incompatible** — addressed: `observation_plan.source_adapter=fact_ledger`, `source_hint=normalized_owner_earnings_m`; `sec_companyfacts_ttm` cannot resolve ASML 20-F EUR rows.
2. **unit_mismatch** — addressed: canonical and source units are USD millions via ledger `fx_conversion` (EUR OCF/capex, 2025-12-31 rate).
3. **historical_replay_not_adapter_verified** — addressed: `resolve_spec` FY2025 replay → 13,024.816 USD millions (matches threshold); FY2026 forward remains unobservable at registration.

## Facts / inferences

- **[Fact]** FY2025 normalized owner earnings anchor 13,024.8 USD millions from `ASML/research/valuation_fact_ledger.json` (`normalized_owner_earnings_m`), OCF EUR 12,658.5M minus capex EUR 1,573.6M (`ASML/investor-documents/sec-edgar/20-F_20260225_rpt20251231_acc0001628280_26_011378.htm`).
- **[Fact]** Low-case per-share value 382.06 USD vs base 644.26 USD per frozen `calculation_proof` (`contract_hash` above).
- **[Inference]** Probability 0.22 that FY2026 owner earnings fall below the low-case anchor before observable resolution (~2027-02-28 20-F).
- **[Opinion]** Routed memory observation `77414d5a` matches the ledger anchor; verified against filings, not promoted to belief.

## Disposition

Author forecast frozen at `status=awaiting_review`. No edit to canonical `falsifier_specs.json`. Epistemic work receipt: **success** pending independent `review_forecast`.
