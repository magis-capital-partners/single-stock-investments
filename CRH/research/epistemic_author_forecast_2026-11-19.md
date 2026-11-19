# CRH — epistemic author forecast (`operating_business_and_net_assets`)

**As of:** 2026-11-19 · **Work id:** `0c6457af11f4a63293a9b6da`

## Summary

Draft **`crh-operating-owner-earnings-2026q3-v18`** (revision 18) rebinds admission to the authorized evidence packet (`evidence_hash_b64` `yfKHxIg2qJpLwWyTzMb7kLqyc58XtY9nRvWjCgzCTfc=` on `agent_run_state.json`) and epistemic input SHA `69932c0fe5a401e3c1d6910bb1686521ed1440ba`. The prospective test is unchanged: Q3 FY2026 TTM normalized owner earnings below **2,912 USD millions** (low-case DCF anchor), resolved via `normalized_owner_earnings_ttm_m_v2` and `sec_companyfacts_ttm`.

## Facts

- Component fingerprint and contract hash match the frozen work packet in `research_agent_manifest.json`.
- Source preflight: **passed** (`normalized_owner_earnings_ttm_m_v2` / `sec_companyfacts_ttm`).
- Historical replay (Q3 FY2025): **2,605M** vs threshold **2,912M** (unchanged in observation plan).
- Target Q3 FY2026: `resolve_spec` at information cutoff still returns `ttm_period_inputs_missing`.
- Status: **`awaiting_review`** — no edit to `falsifier_specs.json` on this run.

## Inferences / opinions

- **Probability 34%:** Same ex-ante weight as v17; not calibration-derived (`global_status=insufficient_outcomes` on route `quality_reinvestment`).
- **Severity 4 / ~56.5% component impact:** Mechanical mapping from low-case per-share value ($26.05) vs base ($59.87) on the admitted proof.

## Receipts

- Draft: `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json`
- Author receipt: `CRH/research/epistemic_author_receipt_2026-11-19.md`
- Run state: `CRH/research/agent_run_state.json`