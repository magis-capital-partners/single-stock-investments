# ASML: epistemic author forecast receipt (operating business)

**Work id:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json` · **Status:** `awaiting_review`  
**Evidence packet:** `9a242d6a9c7d449441ee41b77fbc4d3fcbe12cc84436dfb276b3cec0f96fe08e` (manifest artifact: `ASML/investor-documents/DOWNLOAD_MANIFEST.json`). <!-- pragma: allowlist secret -->  
**Gate input SHA:** `ac4ab6a443785671944dc3179c631f9a5ac74f55`

## What was delivered

Prospective falsifier v3 **`asml-opbiz-oe-2026fy-v5`** (spec revision **21**) remains frozen for independent review after remediation of draft `2750cd7278c04903d8dacb51`. Forecast: FY2026 normalized owner earnings (USD millions) at **2026-12-31** resolve **below 13,024.816** (low-case owner earnings node on the `owner_earnings_reinvestment_dcf` proof trace).

## Facts (primary)

- **Low-case anchor 13,024.8M:** OCF EUR 12,658.5M minus capex EUR 1,573.6M on FY2025 20-F (accession `0001628280-26-011378`), USD conversion at 2025-12-31 per `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`.
- **Historical replay FY2025:** `fact_ledger` `resolve_spec` at cutoff 2026-11-09 returns **13,024.816 USD millions** (blocker null).
- **Forward FY2026 at registration:** `resolve_spec` returns **`period_end_mismatch`** (target not yet observable).
- **Forms:** ASML reports on **20-F / 20-F/A** only; observation plan uses **`fact_ledger`**, not `sec_companyfacts_ttm`.
- **Routed memory lead** (77414d5a) matches the locked ledger field; verified against ledger, not promoted from inbox alone.

## Inference

- A fire would compress the bounded per-share range toward the low case (~382 USD per share vs ~644 base). Reinvestment rate and incremental ROIC remain judgment legs and are not typed here.

## Rejection remediation (draft `2750cd7278c04903d8dacb51`)

| Review reason | Author response |
|---------------|-----------------|
| `source_recipe_incompatible` | Observation plan `source_adapter=fact_ledger`, `source_hint=normalized_owner_earnings_m`. |
| `unit_mismatch` | Canonical and source units USD millions; ledger carries evidenced EUR/USD conversion. |
| `historical_replay_not_adapter_verified` | Adapter replay on FY2025 reproduces threshold anchor via fact ledger. |

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
