# Epistemic author receipt — ASML — 2026-09-30

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | author_forecast |
| component_id | operating_business_and_net_assets |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| status | awaiting_review |
| input_sha | `3cf10f377948f50bb4f6a30b0328980e65572db8` |
| evidence_hash | `a2c333af2de3bc7ce1a28d919a5f7bf3c72d008acdca299cd5a12eba99d399f1` | <!-- pragma: allowlist secret -->
| contract_hash | `d434edd8a9cef1c4169933554387a22a0e323c1ac0f65d88f3f0e75d50eb7931` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |

## Rejection remediation (prior draft `2750cd7278c04903d8dacb51`)

1. **source_recipe_incompatible:** `observation_plan.source_adapter` = `fact_ledger` (ASML 20-F only; no 10-Q TTM path).
2. **unit_mismatch:** `source_unit` = USD millions; EUR filing facts converted in `valuation_fact_ledger.json`.
3. **historical_replay_not_adapter_verified:** FY2025 replay via `fact_ledger` resolves **13,024.816** USD millions (verified with `resolve_spec` on 2026-09-30).

## Calibration / epistemic loop

- **health_state:** COLLECTING (not inferring learning from diagnostic-only rows).
- **calibration_status:** insufficient_outcomes; **release_hash:** null.
- **route:** quality_reinvestment / owner_earnings_reinvestment_dcf.
- **named_challenge:** none (`learning_status` insufficient_outcomes on active route).
- **calibration_response:** not_applicable.

## Analysis receipt

| release_hash | route | named_challenge | response |
|--------------|-------|-----------------|----------|
| null | quality_reinvestment | null | not_applicable |

Disposition: **success** — draft frozen for independent review; no edit to canonical `falsifier_specs.json`.
