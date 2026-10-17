# Epistemic author receipt — ASML — 2026-10-17

| Field | Value |
|-------|-------|
| work_id | `290e1242482eb2878775b1a4` |
| task_type | author_forecast |
| component_id | operating_business_and_net_assets |
| draft | `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` |
| spec_id | asml-opbiz-oe-2026fy-v4 (revision 17) |
| evidence_hash | `e7738aa46d65832700c8dddd05af1f817af4e11e2793bc4c35e31a712e062abb <!-- pragma: allowlist secret -->` |
| epistemic_input_sha | `93ed3c5b3ec4ae63b3923f89bc785cf2fd7a4dc9` |
| disposition | success (draft awaiting_review) |

## Rejection remediation (2750cd7278c04903d8dacb51)

1. **source_recipe_incompatible** — addressed: `observation_plan.source_adapter=fact_ledger`, `source_hint=normalized_owner_earnings_m`; not `sec_companyfacts_ttm` (10-Q/10-K only).
2. **unit_mismatch** — addressed: `canonical_unit` and `source_unit` are USD millions; ledger field carries evidenced EUR/USD conversion.
3. **historical_replay_not_adapter_verified** — addressed: `preflight_spec` passed; FY2025 `resolve_spec` via fact_ledger returns 13,024.816 USD millions.

## Calibration (quality_reinvestment route)

- Epistemic loop: **COLLECTING** (not BOOTSTRAP_BLOCKED / DEGRADED / HALTED).
- Global calibration: **insufficient_outcomes**; `release_hash`: null.
- **named_challenge**: null — **calibration_response**: not_applicable.

## Routed memory

- Observation `77414d5a`: verified against `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m` and FY2025 20-F manifest entry; not promoted to belief.
