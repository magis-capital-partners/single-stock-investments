# ASML — epistemic author forecast receipt (2026-11-10)

**Work:** `290e1242482eb2878775b1a4` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` (`status: awaiting_review`)

## Facts

- **Evidence packet:** `773910cefafad1befb28ddc198307299047d0555cd570a9572a21615e5662300` (admitted artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`). <!-- pragma: allowlist secret -->
- **Input SHA:** `585ecb44c381d0370fd4ee28b276c9f9f03af944` · **Contract hash:** `50c7e6ea066142ed07e03bc9c82bc3f22c92acefe0c9a691f3bd452233fc7fc9`.
- **Threshold:** normalized owner earnings **&lt; 13,024.816 USD millions** for FY ending **2026-12-31** (low-case DCF anchor per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`).
- **Observation plan:** `source_adapter: fact_ledger`, `source_hint: normalized_owner_earnings_m`, accepted forms `20-F` / `20-F/A`, `canonical_unit` and `source_unit` USD millions with ledger FX evidence.
- **Historical replay (FY2025):** `falsifier_evidence_adapters.resolve_spec` → **13,024.816 USD millions** at measurement end 2025-12-31.
- **Forward period:** FY2026 resolves `period_end_mismatch` at registration (unobservable until ~2027-02-28 20-F).

## Inferences

- Probability **0.22** / severity **4** types the prose falsifier leg where owner cash falls below the low-case reinvestment bridge; material equity impact ~41% of component range spread (low 382 vs base 644 USD per share).

## Epistemic loop / calibration

- **`health_state=COLLECTING`** (`_system/research/epistemic_loop_status.json`); **`calibration_status=insufficient_outcomes`**; **release_hash null** — calibration cannot change this analysis.
- **Analysis receipt:** route `quality_reinvestment`; named_challenge null; disposition **`not_applicable`**.

## Rejection remediation (prior draft `2750cd7278c04903d8dacb51`)

| Review reason | Response |
|---|---|
| `source_recipe_incompatible` (sec_companyfacts_ttm vs 20-F) | Switched to `fact_ledger` adapter |
| `unit_mismatch` (EUR companyfacts) | Ledger field carries evidenced EUR→USD conversion |
| `historical_replay_not_adapter_verified` | Independent `resolve_spec` FY2025 replay passes |

**Routed memory** observation `77414d5a` (owner earnings anchor) verified against primary 20-F / ledger — promoted into threshold basis only after verification.
