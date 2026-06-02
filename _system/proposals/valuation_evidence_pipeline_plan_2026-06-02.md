# Valuation evidence pipeline (phases 0–6)

**Date:** 2026-06-02  
**Pilot:** KEWL  

## Phase 0 — Transcripts committed

- `download_transcripts.py {TICKER} --register-legacy`
- `build_management_evidence.py {TICKER}`
- Human-attested transcript until IR PDF available

## Phase 1 — Market inputs

- `fetch_market_inputs.py {TICKER} --merge` → `research/market_inputs.json`
- Rule: `_system/frameworks/market_inputs_freshness.md` (spot within 7 days)

## Phase 2 — Economic NAV / GAAP vs fair value

- Ticker-specific refresh (KEWL: `refresh_kewl_valuation.py` after `marvin_valuation.py --write`)
- `nav_overlay`, `optionality_gate.floor_metric` = `nav_per_share`

## Phase 3 — Option overlay

- Probability-weighted production royalty at spot copper
- `overlay_options`, catalyst paths in `valuation.json`

## Phase 4 — Filing facts

- `build_filing_evidence.py`; manual or script seed in `filing_facts_{date}.json` when OTC parse thin
- `check_evidence_completeness.py` gate

## Phase 5 — Narrative refresh

- `deep_dive_{date}.md`, pending review copy, thesis update

## Phase 6 — Cloud pipeline

- `marvin_cloud_refresh.py {TICKER} --date {date} --reindex`
- `make research-check TICKER={TICKER}` (PYTHON=python3)
- Milly `adversarial_{date}.md`

## KEWL checklist (2026-06-02)

| Step | Status |
|------|--------|
| Transcript + management_facts | Done |
| Copper spot merged | Done (~$6.67/lb) |
| Economic floor vs GAAP book | Done (~$20.9/sh) |
| Lawrence base stance gate | -8.3% @ $55 |
| Deep dive + adversarial | 2026-06-02 |
| Cross-check verify | 2026-06-01 on file |
| Evidence completeness | After refresh_kewl filing_facts seed |
