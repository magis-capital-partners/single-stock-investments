# ASML — epistemic author forecast receipt (2026-11-13)

**Work:** `290e1242482eb2878775b1a4` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` (`status: awaiting_review`, spec revision 23)

## Facts

- **Evidence packet:** `3870d819795d6a33f33f8ccaac40242d1cf82d4404904b77297ae1b955cb0336` (admitted artifact: <!-- pragma: allowlist secret --> `ASML/investor-documents/DOWNLOAD_MANIFEST.json`, sha256 `7c7230276c87705b1c182adcdcf18b581d393ee33dea8cb0585761bcd27e4a85`).
- **Input SHA:** `b34a307c328fd02c767622467da404d946ed09de` · **Contract hash:** `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9`.
- **Threshold:** normalized owner earnings **< 13,024.816 USD millions** for FY ending **2026-12-31** (low-case DCF anchor per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`).
- **Observation plan:** `source_adapter: fact_ledger`, `source_hint: normalized_owner_earnings_m`, accepted forms `20-F` / `20-F/A`, canonical and source units USD millions with ledger FX evidence.
- **Historical replay (FY2025):** `falsifier_evidence_adapters.resolve_spec` → **13,024.816 USD millions** at measurement end 2025-12-31 (`source_preflight_passed`).
- **Forward period:** FY2026 resolves `period_end_mismatch` at registration (unobservable until expected 20-F ~2027-02-28).

## Inferences

- Probability **0.22** / severity **4** types the owner-earnings leg of the prose falsifier; a sub-threshold FY2026 print would compress distributable owner cash toward the low per-share bridge (382 USD vs 644 USD base per frozen contract).

## Epistemic loop / calibration

- **`health_state=COLLECTING`** (`_system/research/epistemic_loop_status.json`); **`calibration_status=insufficient_outcomes`**; **release_hash null** — calibration cannot change this analysis.
- **Analysis receipt:** route `quality_reinvestment`; named_challenge null; disposition **`not_applicable`**.

## Rejection remediation (prior draft `2750cd7278c04903d8dacb51`)

| Review reason | Response |
|---|---|
| `source_recipe_incompatible` | `fact_ledger` adapter + `normalized_owner_earnings_ttm_m_v2` (not `sec_companyfacts_ttm` on 20-F EUR rows) |
| `unit_mismatch` | Ledger `normalized_owner_earnings_m` in USD millions with evidenced EUR→USD conversion |
| `historical_replay_not_adapter_verified` | Independent `resolve_spec` FY2025 replay matches 13,024.816M anchor |

**Routed memory** observation `77414d5a` verified against FY2025 20-F and `valuation_fact_ledger.json` before use in threshold basis.
