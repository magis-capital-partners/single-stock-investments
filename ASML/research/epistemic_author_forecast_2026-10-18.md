# ASML: epistemic author forecast receipt (operating business)

**Work id:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` · **Status:** `awaiting_review`  
**Provenance:** evidence packet hash and input SHA recorded in `ASML/research/agent_run_state.json` (paired dispatch manifest under the same folder).

## What was delivered

Prospective falsifier v3 **`asml-opbiz-oe-2026fy-v4`** (spec revision **17**) re-freezes the owner-earnings leg after independent review rejected draft `2750cd7278c04903d8dacb51` for incompatible `sec_companyfacts_ttm` sourcing. Forecast: FY2026 normalized owner earnings (USD millions) at **2026-12-31** resolve **below 13,024.816** (low-case `owner_earnings` node on `owner_earnings_reinvestment_dcf` proof trace, contract hash `5512118aa814b15d424031b02216db92e04fb7beaf896813266b3c6c1fc578a6`).

## Facts (primary)

- **Low-case anchor 13,024.8M:** OCF EUR 12,658.5M minus capex EUR 1,573.6M on FY2025 20-F (accession `0001628280-26-011378`), USD conversion at 2025-12-31 per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`.
- **Historical replay FY2025:** `fact_ledger` adapter resolves **13,024.816 USD millions** (`preflight_spec` ok; `resolve_spec` with FY2025 plan on 2026-10-18).
- **Forms:** ASML reports on **20-F / 20-F/A** only; `sec_companyfacts_ttm` accepts 10-Q/10-K and returns `ttm_period_inputs_missing` for this issuer.
- **Target FY2026:** Not observable at registration; expected publication **2027-02-28** (FY2025 20-F filed **2026-02-25** per `ASML/investor-documents/DOWNLOAD_MANIFEST.json`).

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

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`. Prior rejected draft preserved; this revision addresses all three review rejection reasons via `fact_ledger` sourcing.
