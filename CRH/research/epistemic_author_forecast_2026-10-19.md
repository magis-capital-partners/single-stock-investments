# CRH — epistemic author forecast receipt (operating business)

**Work id:** `0c6457af11f4a63293a9b6da`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** work id `0c6457af11f4a63293a9b6da` under `CRH/research/falsifier_drafts/` · **Status:** `awaiting_review`

## What was delivered

Prospective falsifier v3 **`crh-operating-owner-earnings-2026q3-v3`** types the owner-earnings leg of the valuation-contract prose falsifier: trailing-twelve-month normalized owner earnings at **2026-09-30** resolve **below 2,912 USD millions** (low-case `owner_earnings` anchor on the `owner_earnings_reinvestment_dcf` proof trace in `CRH/research/valuation_contract.json`).

## Facts (primary)

- **Low-case anchor 2,912M:** Locked on the low trace per admitted calculation proof in the work packet (`CRH/research/valuation_fact_ledger.json` normalized_owner_earnings_m; FY2025 10-K accession `0001628280-26-009043`).
- **Historical replay Q3 FY2025 (end 2025-09-30):** Adapter `sec_companyfacts_ttm` resolves **2,605 USD millions** (`CRH/research/evidence/sec_companyfacts.json#normalized_owner_earnings_ttm_m@2025-09-30`), filed **2025-11-05** per `CRH/investor-documents/DOWNLOAD_MANIFEST.json` (admitted packet artifact).
- **Target Q3 FY2026:** Not observable at registration; expected publication **2026-11-05** per manifest filing cadence.

## Inference

- A fire would imply distributable owner cash has fallen below the automated low-case bridge; incremental ROIC and reinvestment-rate judgments are separate and not resolvable from SEC TTM alone.

## Calibration and epistemic loop (analysis receipt)

| Field | Value |
|-------|--------|
| Epistemic loop | **COLLECTING** (not BOOTSTRAP_BLOCKED / DEGRADED / HALTED) |
| Calibration | **insufficient_outcomes** — cannot change threshold, probability, or sizing |
| Active route | `quality_reinvestment` |
| `release_hash` | `null` |
| Named challenge | `null` |
| Response | **not_applicable** |

## Routed memory (inbox only)

Routed observations repeat that this draft awaits **independent review** before promotion (`falsifier_specs.json`). Verified: draft remains `awaiting_review`; no self-review performed.

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`.

## Epistemic work receipt

- **Disposition:** success  
- **Published input SHA:** recorded in run-state JSON alongside this receipt date
