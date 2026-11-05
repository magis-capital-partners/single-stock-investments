# CRH — epistemic author forecast (2026-11-05)

**Work id:** `0c6457af11f4a63293a9b6da`  
**Component:** `operating_business_and_net_assets` · **Method:** `owner_earnings_reinvestment_dcf`  
**Draft:** `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json` (`awaiting_review`)

## Summary

Revision **7** re-freezes the prospective v3 spec on the authorized epistemic input SHA and evidence packet (hashes in `research_agent_manifest.json` / `agent_run_state.json`). The falsifier fires if **normalized owner earnings (TTM)** at **2026-09-30** are **below 2,912 USD millions**, matching the low-case proof anchor on `operating_business_and_net_assets`.

## Source replay (verified at authoring)

| Check | Result |
|-------|--------|
| Source preflight | `source_preflight_passed` · `normalized_owner_earnings_ttm_m_v2` · `sec_companyfacts_ttm` |
| Historical replay (Q3 FY2025, end 2025-09-30) | **2,605 USD millions** |
| Target at registration (2026-11-05) | `ttm_period_inputs_missing` (prospective; not look-ahead) |

## Epistemic work receipt

- **Disposition:** success  
- **Published input SHA:** see `agent_run_state.json`  
- **Independent review:** required before promotion to `falsifier_specs.json`
