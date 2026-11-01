# CRH — epistemic author forecast receipt

**Work id:** `0c6457af11f4a63293a9b6da`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json` · **Status:** `awaiting_review`  
**Evidence hash / input SHA:** recorded in `CRH/research/agent_run_state.json` and `CRH/research/research_agent_manifest.json`.

## What was delivered

Prospective falsifier v3 **`crh-operating-owner-earnings-2026q3-v2`** (revision 2) types the owner-earnings leg of the valuation-contract prose falsifier: trailing-twelve-month normalized owner earnings at **2026-09-30** resolve **below 2,912 USD millions** (low-case `owner_earnings` anchor on the admitted `owner_earnings_reinvestment_dcf` proof trace).

## Facts (primary)

- **Admitted evidence:** `CRH/investor-documents/DOWNLOAD_MANIFEST.json` only (filing cadence for Q3 2025 10-Q **2025-11-05**, report **2025-09-30**).
- **Low-case anchor 2,912M:** Locked on traces.low.owner_earnings in the work packet (`contract_hash` `2e7fd931baba7ef94c5bf7d11d99524aa07390b0825fceb4e5324d48e59ea4c1`).
- **Historical replay Q3 FY2025 (end 2025-09-30):** Adapter `sec_companyfacts_ttm` resolves **2,605 USD millions** (`CRH/research/evidence/sec_companyfacts.json#normalized_owner_earnings_ttm_m@2025-09-30`).
- **Target Q3 FY2026:** Not observable at registration; expected publication **2026-11-05** per manifest cadence.

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

Routed observations repeat that this draft awaits **independent review** before promotion. Verified: draft remains `awaiting_review`; no self-review performed.

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`.
