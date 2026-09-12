# Epistemic author forecast receipt — ASML — 2026-09-12

**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` (revision of rejected draft `2750cd7278c04903d8dacb51`)  
**Component:** `operating_business_and_net_assets`  
**Method:** `owner_earnings_reinvestment_dcf` / `quality_reinvestment`

## Provenance

| Field | Value |
|-------|-------|
| evidence_hash | `becc2823ab61608c12bf74747ba5941aa0e1b73b49e4fa69ba8c677d70301384` | <!-- pragma: allowlist secret -->
| input_sha | `7c6e9fe0e804a7353c578b4708d55830e49ae24d` |
| component_fingerprint | `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480` |
| contract_hash | `de604b303ec62b1ca0dce4fefe6bf6bc20089600fb78109b4b4b39320d6282d5` |

## Epistemic loop

- **health_state:** COLLECTING
- **calibration_status:** insufficient_outcomes
- **eligible_scored_outcomes:** 0

Calibration cannot yet change analysis weights or thresholds. Diagnostic outcomes do not count as learning.

## Calibration receipt

| release_hash | route | named_challenge | response |
|---|---|---|---|
| null | quality_reinvestment | null | not_applicable |

## Rejection remediation

| Prior reason | Revision |
|---|---|
| source_recipe_incompatible | `observation_plan.source_adapter` set to `fact_ledger` (20-F annual filer; sec_companyfacts_ttm accepts 10-Q/10-K only) |
| unit_mismatch | `source_unit` set to `USD millions`; locked ledger field carries evidenced EUR/USD `fx_conversion` |
| historical_replay_not_adapter_verified | Replay via `fact_ledger`; `resolve_spec(FY2025)` returns 13,024.816 USD millions |

## Routed memory

Observation `77414d5a` verified against `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m` and FY2025 20-F; confirmation only.

## Draft

- **Path:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`
- **Spec ID:** `asml-opbiz-oe-2026fy-v4`
- **Status:** `awaiting_review`
- **Metric:** normalized_owner_earnings FY2026 vs low-case anchor 13,024.816 USD millions
- **Adapter:** fact_ledger / normalized_owner_earnings_m
- **Historical replay:** passed (FY2025 = 13,024.816 USD millions via fact_ledger)
- **Target period not observable at registration:** yes (FY2026 20-F expected ~2027-02-28)

## Disposition

`success` — draft frozen for independent review; canonical `falsifier_specs.json` not edited.
