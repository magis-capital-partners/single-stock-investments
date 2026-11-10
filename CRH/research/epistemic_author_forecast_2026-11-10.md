# CRH — epistemic author forecast (`operating_business_and_net_assets`)

**As of:** 2026-11-10 · **Work id:** `0c6457af11f4a63293a9b6da`

## Summary

Draft **`crh-operating-owner-earnings-2026q3-v12`** registers a prospective test that Q3 FY2026 TTM normalized owner earnings fall below the low-case DCF anchor of **2,912 USD millions**, tying the prose falsifier on `operating_business_and_net_assets` to `normalized_owner_earnings_ttm_m_v2` via `sec_companyfacts_ttm`.

## Facts

- Component fingerprint and contract hash match the frozen work packet in `research_agent_manifest.json`.
- Source preflight: **passed** (`normalized_owner_earnings_ttm_m_v2` / `sec_companyfacts_ttm`).
- Historical replay (Q3 FY2025): **2,605M** vs threshold **2,912M**.

## Inferences / opinions

- **Probability 34%:** Weights cyclical construction demand and integration capex against the prior-year Q3 replay already below the anchor; not a calibration-derived weight (`insufficient_outcomes`).
- **Severity 4 / ~56.5% component impact:** Mechanical mapping from low-case per-share value ($26.05) vs base ($59.87) on the admitted proof.

## Receipts

- Draft: `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json`
- Author receipt: `CRH/research/epistemic_author_receipt_2026-11-10.md`
- Run state: `CRH/research/agent_run_state.json`
