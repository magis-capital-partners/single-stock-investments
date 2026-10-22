# ASML: epistemic author forecast receipt (operating business)

**Work id:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` · **Status:** `awaiting_review`  
**Evidence packet:** `40897b20a71e57e4856f4c7c810cb6356a391124774fe4c7b7b4179a49784f8a` (manifest artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`). <!-- pragma: allowlist secret -->

## What was delivered

Prospective falsifier v3 **`asml-opbiz-oe-2026fy-v4`** (spec revision **21**) re-freezes the owner-earnings leg after independent review rejected draft `2750cd7278c04903d8dacb51` for incompatible `sec_companyfacts_ttm` sourcing. Forecast: FY2026 normalized owner earnings (USD millions) at **2026-12-31** resolve **below 13,024.816** (low-case owner earnings node on the `owner_earnings_reinvestment_dcf` proof trace).

## Facts (primary)

- **Low-case anchor 13,024.8M:** OCF EUR 12,658.5M minus capex EUR 1,573.6M on FY2025 20-F (accession `0001628280-26-011378`), USD conversion at 2025-12-31 per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`.
- **Historical replay FY2025:** `fact_ledger` adapter `resolve_spec` returns **13,024.816 USD millions** (measurement end 2025-12-31; verified on this run).
- **Forms:** ASML reports on **20-F / 20-F/A** only; observation plan uses **`fact_ledger`**, not `sec_companyfacts_ttm`.
- **Target FY2026:** Not observable at registration; expected publication **2027-02-28** per prior 20-F cadence in `DOWNLOAD_MANIFEST.json`.

## Inference

- A fire would compress the bounded per-share range toward the low case (~382 USD per share vs ~644 base). Reinvestment rate and incremental ROIC remain judgment legs and are not typed here.

## Calibration and epistemic loop (analysis receipt)

| Field | Value |
|-------|--------|
| Epistemic loop | **COLLECTING** |
| Calibration | **insufficient_outcomes** on route `quality_reinvestment` (`release_hash` null) |
| Active route | `quality_reinvestment` |
| `release_hash` | `null` |
| Named challenge | `null` |
| Response | **not_applicable** |

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`. Prior rejected draft preserved.
