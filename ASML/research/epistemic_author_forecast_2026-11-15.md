# ASML — epistemic author forecast (2026-11-15)

**Work ID:** `290e1242482eb2878775b1a4` · **Component:** `operating_business_and_net_assets` · **Spec:** `asml-opbiz-oe-2026fy-v5` (revision 24) · **Status:** `awaiting_review`

## Admission

- **Evidence packet:** `de8e74a69ba75dc6a5fb97c870746a49b01e82e2d2411949d8d06403e5aa59f1` (admitted artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`, sha256 `7c7230276c87705b1c182adcdcf18b581d393ee33dea8cb0585761bcd27e4a85`). <!-- pragma: allowlist secret -->
- **Input SHA:** `ac58bb195b0d97bf8cdab504ef405d591d111f22`
- **Contract hash:** `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9`

## Forecast summary

Types the owner-earnings leg of the operating business falsifier: FY2026 normalized owner earnings (USD millions, `lt` comparator) vs low-case anchor **13,024.816** from FY2025 OCF minus capex with evidenced EUR/USD conversion in `valuation_fact_ledger.json#normalized_owner_earnings_m`.

## Rejection remediation (draft 2750cd7278c04903d8dacb51)

1. **Source recipe:** `observation_plan.source_adapter` = `fact_ledger`, `source_hint` = `normalized_owner_earnings_m` (not `sec_companyfacts_ttm`, which only accepts 10-Q/10-K).
2. **Units:** `canonical_unit` and `source_unit` = USD millions; EUR filing amounts convert via locked ledger FX.
3. **Adapter replay:** `resolve_spec` FY2025 replay = **13,024.816** USD millions; FY2026 forward = `period_end_mismatch` (unobservable at registration).

## Calibration / epistemic loop

- **Health:** COLLECTING (not BOOTSTRAP_BLOCKED; loop is collecting eligible outcomes but has not met minimum same-route sample).
- **Calibration:** `insufficient_outcomes` for route `quality_reinvestment` / method `owner_earnings_reinvestment_dcf` (2 eligible scored outcomes vs 20 minimum); **release_hash:** null.
- **Analysis receipt:** route `quality_reinvestment`, named_challenge null, disposition **not_applicable** (calibration cannot change this analysis).

## Routed memory

- Observation `77414d5a` (FY2025 normalized owner earnings anchor) was verified against `valuation_fact_ledger.json` and primary 20-F filing; ledger value matches adapter replay.

## Artifacts

- Draft: `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`
- Provenance: `ASML/research/research_agent_manifest.json`, `ASML/research/agent_run_state.json` <!-- pragma: allowlist secret -->