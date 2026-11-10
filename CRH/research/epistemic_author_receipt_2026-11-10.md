# CRH — epistemic author forecast receipt

**Work id:** `0c6457af11f4a63293a9b6da`  
**Task:** `author_forecast` · **Component:** `operating_business_and_net_assets`  
**Draft:** `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json` · **Status:** `awaiting_review`  
**Evidence hash / input SHA:** `CRH/research/agent_run_state.json` (use `evidence_hash_b64` if literals are redacted in the working tree).

## What was delivered

Prospective falsifier v3 **`crh-operating-owner-earnings-2026q3-v12`** (revision 12) types the owner-earnings leg of the valuation-contract prose falsifier: trailing-twelve-month normalized owner earnings at **2026-09-30** resolve **below 2,912 USD millions** (low-case `owner_earnings` anchor on the admitted `owner_earnings_reinvestment_dcf` proof trace).

## Facts (primary)

- **Admitted evidence:** `CRH/investor-documents/DOWNLOAD_MANIFEST.json` (normalized content SHA `f9214ccf1a62e6216065fb9106d3c15eb570e88de9ff46a6d1e60f30cf5ecf99`).
- **Admission packet:** Gate-bound evidence hash via `evidence_hash_b64` in `agent_run_state.json` (authorized dispatch; not rebinding to newer queue digest). Epistemic input SHA is recorded on the draft and run state with pragma allowlist.
- **Low-case anchor 2,912M:** Locked on traces.low.owner_earnings in the work packet (`contract_hash` `bd620a53edf5039b9434177e2cbb06669d54209ff49ae136ef27404044ddaa1d`).
- **Historical replay Q3 FY2025 (end 2025-09-30):** Adapter `sec_companyfacts_ttm` resolves **2,605 USD millions** (`CRH/research/evidence/sec_companyfacts.json#normalized_owner_earnings_ttm_m@2025-09-30`).
- **Target Q3 FY2026:** Not observable at registration; resolver returns `ttm_period_inputs_missing`; expected publication **2026-11-06** per observation plan.

## Inference

- A fire would imply distributable owner cash has fallen below the automated low-case bridge; incremental ROIC and reinvestment-rate judgments are separate and not resolvable from SEC TTM alone.
- Revision 12 rebinding only: threshold (2,912M), probability (34%), and observation plan unchanged from v11.

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

Routed observations repeat that this draft awaits **independent review** before promotion. Verified against primary evidence: draft remains `awaiting_review`; no self-review performed.

## Role boundaries

Author run only. No outcome scoring, no edits to `falsifier_specs.json`, no `human_decision.json`.
