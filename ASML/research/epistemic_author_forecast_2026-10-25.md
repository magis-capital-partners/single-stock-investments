# ASML: epistemic author forecast receipt (operating business)

**Work id:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` · **Status:** `awaiting_review`  
**Evidence packet:** `ac3bff91b4bbe6ae2b9afec26b932590ee44393f12264320fa8499a50306cbef` (manifest artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`). <!-- pragma: allowlist secret -->  
**Gate input SHA:** `786118736e8ada71dd6726f07b67645f6932ef60` <!-- pragma: allowlist secret -->

## What was delivered

Prospective falsifier v3 **`asml-opbiz-oe-2026fy-v4`** (spec revision **24**) re-freezes the owner-earnings leg for independent review after rejection of draft `2750cd7278c04903d8dacb51`. Forecast: FY2026 normalized owner earnings (USD millions) at **2026-12-31** resolve **below 13,024.816** (low-case owner earnings node on the `owner_earnings_reinvestment_dcf` proof trace).

## Facts (primary)

- **Low-case anchor 13,024.8M:** OCF EUR 12,658.5M minus capex EUR 1,573.6M on FY2025 20-F (accession `0001628280-26-011378`), USD conversion at 2025-12-31 per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`.
- **Historical replay FY2025:** `fact_ledger` adapter `resolve_spec` returns **13,024.816 USD millions** (measurement end 2025-12-31; verified 2026-10-25 via `falsifier_evidence_adapters.resolve_spec`).
- **Forms:** ASML reports on **20-F / 20-F/A** only; observation plan uses **`fact_ledger`**, not `sec_companyfacts_ttm`.
- **Target FY2026:** Not observable at registration (`blocker_reason=period_end_mismatch` on ledger as of 2026-10-25); expected publication **2027-02-28** per prior 20-F cadence in `DOWNLOAD_MANIFEST.json`.
- **Routed memory lead** (FY2025 owner earnings ~$13.0B) matches the locked ledger field; no thesis change from inbox delivery alone.

## Inference

- A fire would compress the bounded per-share range toward the low case (~382 USD per share vs ~644 base). Reinvestment rate and incremental ROIC remain judgment legs and are not typed here.

## Rejection remediation (draft `2750cd7278c04903d8dacb51`)

| Review reason | Author response |
|---------------|-----------------|
| `source_recipe_incompatible` | Observation plan `source_adapter=fact_ledger`, `source_hint=normalized_owner_earnings_m`. |
| `unit_mismatch` | Canonical and source units USD millions; ledger carries evidenced EUR/USD conversion. |
| `historical_replay_not_adapter_verified` | Adapter replay on 2025-12-31 reproduces threshold anchor via fact ledger. |

## Calibration and epistemic loop (analysis receipt)

| Field | Value |
|-------|--------|
| Epistemic loop | **COLLECTING** (not BOOTSTRAP_BLOCKED / DEGRADED / HALTED) |
| Calibration | **insufficient_outcomes** on route `quality_reinvestment` |
| Active route | `quality_reinvestment` |
| `release_hash` | `null` |
| Named challenge | `null` |
| Response | **not_applicable** |

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`. Prior rejected draft preserved.
