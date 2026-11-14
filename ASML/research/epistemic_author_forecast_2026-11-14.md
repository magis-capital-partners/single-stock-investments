# ASML — epistemic author forecast (2026-11-14)

**Work ID:** `290e1242482eb2878775b1a4` · **Component:** `operating_business_and_net_assets` · **Spec:** `asml-opbiz-oe-2026fy-v5` (revision 23) · **Status:** `awaiting_review`

## Admission

- **Evidence packet:** `d9ab8079b2e10c720a33b47d34febf144726a4d23f56860b46c29b62c5a19513` (admitted artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`, sha256 `7c7230276c87705b1c182adcdcf18b581d393ee33dea8cb0585761bcd27e4a85`). <!-- pragma: allowlist secret -->
- **Input SHA:** `bc3e805d2f8d8add1a702fcc18f50d81d8075898`
- **Contract hash:** `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9`

## Forecast summary

Types the owner-earnings leg of the operating business falsifier: FY2026 normalized owner earnings (USD millions, `lt` comparator) vs low-case anchor **13,024.816** from FY2025 OCF minus capex with evidenced EUR/USD conversion in `valuation_fact_ledger.json#normalized_owner_earnings_m`.

## Rejection remediation (draft 2750cd7278c04903d8dacb51)

1. **Source recipe:** `observation_plan.source_adapter` = `fact_ledger`, `source_hint` = `normalized_owner_earnings_m` (not `sec_companyfacts_ttm`, which only accepts 10-Q/10-K).
2. **Units:** `canonical_unit` and `source_unit` = USD millions; EUR filing amounts convert via locked ledger FX.
3. **Adapter replay:** `resolve_spec` FY2025 replay = **13,024.816** USD millions; FY2026 forward = `period_end_mismatch` (unobservable at registration).

## Calibration / epistemic loop

- **Health:** COLLECTING · **Calibration:** insufficient_outcomes · **release_hash:** null · **Response:** not_applicable (calibration cannot change this analysis).

## Artifacts

- Draft: `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`
- Provenance: ASML research manifest and run state (epistemic dispatch packet 2026-11-14).