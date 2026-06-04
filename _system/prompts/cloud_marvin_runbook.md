# Cloud Marvin — canonical refresh runbook

**Ticker:** {{TICKER}} · **Date:** {{date}} · **Pick reason:** {{PICK_REASON}}

This file is the **single source of truth** for Cursor Cloud Agent runs (`marvin_deep_dive.mjs`). Local Marvin uses the same pipeline via `marvin_cloud_refresh.py`.

## Framework read order (before writing)

1. `_system/frameworks/decision_stack.md`
2. `{{TICKER}}/research/valuation.json` → open **only** frameworks listed in `_system/frameworks/classification.md` **valuation.json trigger map**
3. Do **not** read moved stubs (`evidence_refresh.md`, `market_inputs_freshness.md`); use `optionality_valuation.md` § Mechanical refresh when `evidence_refresh` is set

## Structure (mandatory)

Follow `_system/frameworks/deep_dive_structure.md` (v2 layout):

1. What this business is → Why the market might be wrong → Executive summary → Primary sources reviewed
2. Business & moat (Hohn mechanics; **Option scan** every ticker — `option_treatment.md`; segment map + AI infrastructure when overlays apply)
3. Payoff & return (five-question gate, dhando, stance proposal — **no** full valuation math here)
4. Risks & inversion
5. **## Valuation & IRR (assumption ledger)** — assumption ledger, segment build (if overlay), IRR arithmetic. **No** valuation bridge overlay table or Popper/Deutsch subsections.
6. Classification · [HUMAN REVIEW] · [PROPOSED MEMORY]

**Prose:** `_system/frameworks/report_prose.md`, `archetype_valuation_prose.md`, `valuation-plain-english` rules.

Do **not** use the legacy five-section-only template as the final shape — run `refresh_deep_dive_v2.py` after narrative work.

**Refresh-only ≠ deep dive:** Phase 3 (`marvin_cloud_refresh.py`) syncs structure and IRR from `valuation.json`; it does **not** add filing-grounded narrative. Phase 2 must deliver FRMO/TPL-level depth (`_system/frameworks/deep_dive_quality_rubric.md`).

## Phase 1 — Evidence and sources (agent work)

**Optional index:** `python _system/scripts/build_folder_indexes.py --ticker {{TICKER}}`

**Mechanical evidence** runs in Phase 3 via `marvin_cloud_refresh.py`. For manual prep or debugging only:

```bash
python _system/scripts/build_filing_evidence.py {{TICKER}}
python _system/scripts/scan_third_party_sources.py {{TICKER}} --with-hk --date {{date}}
```

Read `{TICKER}/research/evidence/filing_digest_*.md` (latest), `document_inventory.json`, full-tier `_text/`, and `{TICKER}/third-party-analyses/source_inventory_{{date}}.md`. HK-indexed tickers (TPL, ICE, MSB, SJT): `hk_scan_{{date}}.md` when present.

If `evidence_refresh` is set: read `optionality_valuation.md` § **Mechanical refresh and market inputs** (not a separate framework file).

**Cloud HK vault:** `HK_PDFS_ROOT` defaults to `/opt/cursor/hk_pdfs` (see `.cursor/environment.json`). Set in [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents) and optionally GitHub Actions secret `HK_PDFS_ROOT`. Vault must exist on the VM (multi-repo environment, `HK_PDFS_REPO_URL` clone, or snapshot). Extracts auto-refresh from vault via `refresh_hk_extracts.py` before HK scan.

**Third-party approval:** Agents cite HK and pending sources as **context** only. **You** promote sources to `_system/frameworks/third_party_sources.md`; agents never auto-approve.

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
4. **Growth:** State mechanism in Business & moat; growth rows in assumption ledger cite filing or **[Assumption]**. Optional `growth_explanation` in `valuation.json` (not rendered in markdown).
5. **Third-party cross-check (required):** write or complete **`{{TICKER}}/research/cross_check_third_party_{{date}}.md`** per `third_party_cross_reference.md` + `external_view_blend.md`. Existing named cross-checks (McIntyre, Substacks, HK) count if they cover the inventory.
6. Write or update **`{{TICKER}}/research/deep_dive_{{date}}.md`** with filing-grounded narrative (`_system/prompts/deep_dive_filing_grounded_refresh.md`). Set header **Prior dive:** link to previous file.

## Phase 3 — Mechanical pipeline (run last; required)

**One command** (do not re-list substeps unless debugging):

```bash
python _system/scripts/marvin_cloud_refresh.py {{TICKER}} --date {{date}}
```

Includes: transcripts, filing + management evidence, market inputs, third-party scan, valuation write, `refresh_optionality_valuation` when `evidence_refresh.type` is set, deep dive v2 sync, lint, Milly, evidence completeness (strict when triggers apply), classification sync, dashboard, cross-check fill/verify.

| Also | Command |
|------|---------|
| Batch all holdings | `batch_portfolio_refresh.py --date {{date}}` (add `--milly` for Milly on each) |
| Local QA | `make research-check TICKER={{TICKER}} DATE={{date}}` |
| Strict evidence gate | `marvin_cloud_refresh.py ... --strict-evidence` |

For HK-indexed tickers: `python _system/scripts/check_hk_cross_checks.py {{TICKER}}`
For all holdings QA: `python _system/scripts/check_cross_checks.py`

Fix any lint errors before finishing the PR.

## Stance

- Gate stance: `stance_proposal.suggested` in `valuation.json`
- If `approved_stance` or `human_review.approved`: use **approved** stance in Classification and thesis; document override in [HUMAN REVIEW]

## PR checklist

- [ ] `deep_dive_{{date}}.md` passes `lint_deep_dive.py {{TICKER}}` and `lint_deep_dive_depth.py {{TICKER}}` (≥18/24)
- [ ] `adversarial_{{date}}.md` present; dive header **Adversarial:** pass|blocked
- [ ] `classification.json` + `thesis.md` synced
- [ ] No secrets in commits
