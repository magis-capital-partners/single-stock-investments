# Cloud Marvin — canonical refresh runbook

**Ticker:** {{TICKER}} · **Date:** {{date}} · **Pick reason:** {{PICK_REASON}}

This file is the **single source of truth** for Cursor Cloud Agent runs (`marvin_deep_dive.mjs`). Local Marvin uses the same pipeline via `marvin_cloud_refresh.py`.

## Structure (mandatory)

Follow `_system/frameworks/deep_dive_structure.md` (v2 layout):

1. What this business is → Why the market might be wrong → Executive summary → Primary sources reviewed
2. Business & moat (Hohn mechanics; **Option scan** every ticker — `option_treatment.md`; segment map + AI infrastructure when overlays apply)
3. Payoff & return (five-question gate, dhando, stance proposal — **no** full valuation math here)
4. Risks & inversion
5. **## Valuation & IRR (assumption ledger)** — bridge, assumption ledger, **Growth explanation stress test** (`growth_explanation_stress_test.md`), segment build, IRR arithmetic
6. Classification · [HUMAN REVIEW] · [PROPOSED MEMORY]

**Prose:** `_system/frameworks/report_prose.md`, `archetype_valuation_prose.md`, `valuation-plain-english` rules.

Do **not** use the legacy five-section-only template as the final shape — run `refresh_deep_dive_v2.py` after narrative work.

## Phase 1 — Evidence (run first)

```bash
python _system/scripts/build_folder_indexes.py --ticker {{TICKER}}
python _system/scripts/build_filing_evidence.py {{TICKER}}
python _system/scripts/scan_hk_sources.py {{TICKER}} --write-references
```

For tickers in `hk_ticker_index.json` (TPL, ICE, MSB, SJT): read `hk_cross_reference.md` and every source in `{{TICKER}}/third-party-analyses/hk_scan_{{date}}.md`. Set `HK_PDFS_ROOT` on cloud/Linux to scan the full vault.

Read:

- `{{TICKER}}/research/evidence/filing_digest_{{date}}.md`
- `{{TICKER}}/research/evidence/document_inventory.json`
- Full-tier extracts under `{{TICKER}}/research/evidence/_text/`
- Prior latest `deep_dive_*.md` (carry stance, blends, human overrides unless filings contradict)

If **new_documents** or **new_valuation_news**: focus on what changed for owner cash and valuation; do not re-litigate unchanged facts.

## Phase 2 — Narrative + valuation inputs (you write)

1. Update `{{TICKER}}/research/valuation.json` inputs (price, FCF/sh, scenarios) from filings — preserve `approved_stance`, `override_reason`, `human_review` if present.
2. Hyperscalers (`GOOGL`, `AMZN`, `META`, `MSFT`) or registry `valuation_flags`: ensure `segment_build` + `ai_overlay` exist; run `python _system/scripts/seed_hyperscaler_overlays.py {{TICKER}}` when overlays missing. Complete **Option scan** per `option_treatment.md` — no auto-zero terminals.
3. Land / infrastructure with GAAP misstatement (e.g. `TPL`): set `nav_overlay` + `optionality_gate`; segment build for producing vs undeveloped reserves.
4. **Growth theory:** For each material growth rate, write Popper/Deutsch stress test per `growth_explanation_stress_test.md`; fill `growth_explanation` in `valuation.json`. Philosophy refs: `_system/reference/philosophy/deutsch-popper/INDEX.md`.
5. Write or update **`{{TICKER}}/research/deep_dive_{{date}}.md`** with filing-grounded narrative (`_system/prompts/deep_dive_filing_grounded_refresh.md`). Set header **Prior dive:** link to previous file.

## Phase 3 — Mechanical pipeline (run last; required)

```bash
python _system/scripts/marvin_cloud_refresh.py {{TICKER}} --date {{date}}
```

That script runs: HK scan (indexed tickers) → `marvin_valuation.py --write` → `refresh_deep_dive_v2.py` → `lint_deep_dive.py` → Milly adversarial → `sync_classification.py --fix` → `build_dashboard_data.py`.

Fix any lint errors before finishing the PR.

## Stance

- Gate stance: `stance_proposal.suggested` in `valuation.json`
- If `approved_stance` or `human_review.approved`: use **approved** stance in Classification and thesis; document override in [HUMAN REVIEW]

## PR checklist

- [ ] `deep_dive_{{date}}.md` passes `lint_deep_dive.py {{TICKER}}`
- [ ] `adversarial_{{date}}.md` present; dive header **Adversarial:** pass|blocked
- [ ] `classification.json` + `thesis.md` synced
- [ ] No secrets in commits
