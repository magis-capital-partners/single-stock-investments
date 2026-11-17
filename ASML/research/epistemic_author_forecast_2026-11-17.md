# ASML — epistemic author forecast (2026-11-17)

**Work ID:** `290e1242482eb2878775b1a4` · **Component:** `operating_business_and_net_assets` · **Spec:** `asml-opbiz-oe-2026fy-v5` (revision 26) · **Status:** `awaiting_review`

## Admission

- **Evidence packet:** `cd21995287b1fd7962cbbb37dff54eac69ffb42e214c317c85dbded8f84ef3bc` <!-- pragma: allowlist secret --> (admitted artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`, sha256 `7c7230276c87705b1c182adcdcf18b581d393ee33dea8cb0585761bcd27e4a85`).
- **Input SHA:** `140be8d766a733de28f4ca0eba4d62bf651b9f4d`
- **Contract hash:** `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9`
- **Component fingerprint:** `4080c692e2d41ed5e8c8bb19cc5abb21e04b5d945b4f3f58c4832093f0829480`

## Forecast summary

Types the owner-earnings leg of the operating business falsifier: FY2026 normalized owner earnings (USD millions, `lt` comparator) vs low-case anchor **13,024.816** from FY2025 operating cash flow minus capital spending with evidenced EUR/USD conversion in `valuation_fact_ledger.json#normalized_owner_earnings_m`.

## Rejection remediation (draft 2750cd7278c04903d8dacb51)

1. **Source recipe:** `observation_plan.source_adapter` = `fact_ledger`, `source_hint` = `normalized_owner_earnings_m` (not `sec_companyfacts_ttm`, which only accepts 10-Q/10-K).
2. **Units:** `canonical_unit` and `source_unit` = USD millions; EUR filing amounts convert via locked ledger FX.
3. **Adapter replay:** `resolve_spec` FY2025 replay = **13,024.816** USD millions (`blocker_reason` null); FY2026 forward = `period_end_mismatch` (unobservable at registration).

## Calibration / epistemic loop

- **Health:** COLLECTING (`_system/research/epistemic_loop_status.json` as_of 2026-10-31). Not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED.
- **Calibration:** `insufficient_outcomes` for route `quality_reinvestment` / method `owner_earnings_reinvestment_dcf`; **release_hash:** null.
- **Analysis receipt:** route `quality_reinvestment`, named_challenge null, disposition **not_applicable** (calibration cannot change this analysis).

## Routed memory

- Observation `77414d5a` (FY2025 normalized owner earnings anchor) was verified against `valuation_fact_ledger.json` and FY2025 20-F filing; ledger value matches adapter replay.

## Artifacts

- Draft: `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`
- Provenance: `ASML/research/research_agent_manifest.json` <!-- pragma: allowlist secret -->, `ASML/research/agent_run_state.json`