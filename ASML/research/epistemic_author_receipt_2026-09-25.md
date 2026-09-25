# Epistemic author forecast receipt — ASML — 2026-09-25

**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` (revision after rejection of `2750cd7278c04903d8dacb51`)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `f4f927a2c18ef46bbc1ece57831694bd51ade0e85d6c222faff2e1de694c5941` <!-- pragma: allowlist secret --> |
| input_sha | `7f0dee83d7d6983c069919b20938abbce60e9c40` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| contract_hash | `d434edd8a9cef1c4169933554387a22a0e323c1ac0f65d88f3f0e75d50eb7931` |

## Epistemic loop

- **health_state:** COLLECTING
- **calibration_status:** insufficient_outcomes (`release_hash: null`)
- **eligible_scored_outcomes (global):** 1 on route method `owner_earnings_reinvestment_dcf`; **learning_status:** collecting (below minimum 20)

Calibration cannot yet change analysis weights, thresholds, or sizing. Diagnostic outcomes do not count as learning.

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

## Rejection remediation

| Prior reason | Revision |
|---|---|
| source_recipe_incompatible | `observation_plan.source_adapter` set to `fact_ledger` (20-F annual filer; sec_companyfacts_ttm accepts 10-Q/10-K only) |
| unit_mismatch | `source_unit` set to `USD millions`; locked ledger field carries evidenced EUR/USD `fx_conversion` |
| historical_replay_not_adapter_verified | Replay via `fact_ledger`; FY2025 anchor 13,024.816 USD millions at `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m` |

Mechanical check on 2026-09-25: `preflight_spec` passed; forward `resolve_spec` for FY2026 returns `period_end_mismatch` (not observable at registration).

## Routed memory

Observation `77414d5a` verified against `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m` and FY2025 20-F (`ASML/investor-documents/DOWNLOAD_MANIFEST.json` accession 0001628280-26-011378); confirmation only.

## Draft

- **Path:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`
- **Spec ID:** `asml-opbiz-oe-2026fy-v4` (revision 3)
- **Status:** `awaiting_review`
- **Metric:** normalized_owner_earnings FY2026 vs low-case anchor 13,024.816 USD millions
- **Adapter:** fact_ledger / normalized_owner_earnings_m
- **Historical replay:** passed (FY2025 = 13,024.816 USD millions via fact_ledger)
- **Target period not observable at registration:** yes (FY2026 20-F expected ~2027-02-28)

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
