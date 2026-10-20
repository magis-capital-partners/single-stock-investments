# ASML: epistemic author forecast receipt (operating business)

**Work id:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` · **Status:** `awaiting_review`  
**Provenance:** evidence packet hash and input SHA are recorded in `ASML/research/agent_run_state.json` (paired manifest in the same folder).

## What was delivered

Prospective falsifier v3 **`asml-opbiz-oe-2026fy-v4`** (spec revision **19**) re-freezes the owner-earnings leg after independent review rejected draft `2750cd7278c04903d8dacb51` for incompatible `sec_companyfacts_ttm` sourcing. Forecast: FY2026 normalized owner earnings (USD millions) at **2026-12-31** resolve **below 13,024.816** (low-case `owner_earnings` node on `owner_earnings_reinvestment_dcf` proof trace, contract hash `5512118aa814b15d424031b02216db92e04fb7beaf896813266b3c6c1fc578a6`).

## Facts (primary)

- **Low-case anchor 13,024.8M:** OCF EUR 12,658.5M minus capex EUR 1,573.6M on FY2025 20-F (accession `0001628280-26-011378`), USD conversion at 2025-12-31 per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`.
- **Historical replay FY2025:** `fact_ledger` adapter `resolve_spec` returns **13,024.816 USD millions** (measurement end 2025-12-31; resolve as-of **2026-02-26** after FY2025 20-F filed **2026-02-25** per `ASML/investor-documents/DOWNLOAD_MANIFEST.json`).
- **Forms:** ASML reports on **20-F / 20-F/A** only; observation plan uses **`fact_ledger`**, not `sec_companyfacts_ttm` (10-Q/10-K filter returns `ttm_period_inputs_missing` for this issuer).
- **Target FY2026:** Not observable at registration; expected publication **2027-02-28**.

## Inference

- A fire would compress the bounded per-share range toward the low case (~382 USD per share vs ~644 base). Reinvestment rate and incremental ROIC remain judgment legs and are not typed here.

## Calibration and epistemic loop (analysis receipt)

| Field | Value |
|-------|--------|
| Epistemic loop | **COLLECTING** (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED) |
| Calibration | **insufficient_outcomes** on route `quality_reinvestment` (`release_hash` null) — cannot change threshold, probability, or sizing |
| Active route | `quality_reinvestment` |
| `release_hash` | `null` |
| Named challenge | `null` |
| Response | **not_applicable** |

## Rejection remediation (draft 2750cd7278c04903d8dacb51)

1. **Source recipe:** `observation_plan.source_adapter=fact_ledger`, `source_hint=normalized_owner_earnings_m`.
2. **Units:** `canonical_unit` and `source_unit` are USD millions; EUR/USD conversion evidenced on ledger field.
3. **Adapter replay:** FY2025 `resolve_spec` verified on this run (see draft `adapter_replay_verification`).

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`. Prior rejected draft preserved.
