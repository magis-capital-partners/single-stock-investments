# Agent prompt: Dashboard information architecture (UI Phase 2)

Use when refactoring `dashboard/index.html`, `dashboard/insights-viz.js`, and `build_dashboard_data.py` for **maximum information, minimal redundancy**.

**Normative spec:** `_system/proposals/dashboard_information_architecture_2026-06-09.md`

---

## Goal

Refactor the portfolio dashboard so a human can decide on a holding in **one screen** without reading duplicate numbers. External insights (letters, macro, insider) are **context**, not second verdicts.

---

## Before you code

1. Read the proposal § **Field ownership** and § **Redundancy audit**.
2. Read current render paths: `selectTicker()`, `renderInsights()`, `InsightsViz.*` in `dashboard/insights-viz.js`.
3. Run `python _system/scripts/build_dashboard_data.py` and inspect one row (e.g. APLD) for `lenses`, `insights`, `classification`.

---

## Hard rules

1. **Never show the same metric twice** on ticker detail unless one is a link/tooltip to the other.
2. **House IRR** = Lawrence synthesis (`classification.analysis_irr_pct` / total synthesis). Label exactly `House IRR`.
3. **Lens blend** = `lenses.valuation_blend.blended_return_pct` + band. Label exactly `Lens blend`. Do not call either “Blended IRR” without qualifier.
4. **Stance priority:** `human_review.approved_stance` → else `lenses.consensus.stance` → else `classification.stance`. Show source in small text when not obvious.
5. **Personas:** show only `relevance > 0` as chips. Silent personas = count badge only (`+N silent`), not tabs.
6. **Insights on ticker detail:** default filter = `superinvestor_letter` only. Other sources behind filter pills.
7. **Max 3 insight rows** on ticker detail; link `evidence_ref` to GitHub blob URL via existing `github_blob_url()` pattern in `build_dashboard_data.py`.
8. **Do not** embed full `lenses.json` in HTML — use precomputed `decision_summary` + `active_lenses` from `build_dashboard_data.py`.
9. Keep static site: all data from `dashboard/data/dashboard_data.json` and `insights.json` — no runtime fetch beyond existing load.

---

## Implementation checklist

### Backend (`build_dashboard_data.py`)

- [ ] Add `decision_summary` object per ticker (see proposal schema).
- [ ] Add `active_lenses` array (relevance > 0, sorted by relevance desc).
- [ ] Add `silent_lens_count`.
- [ ] Add `insights_by_source` or tag each insight with `source` (already present) — sort letters first.
- [ ] Helper `github_blob_url(evidence_ref)` for letter `.txt` paths under repo.

### Backend (`build_insights.py`) — optional UI-3

- [ ] `theme_rankings_by_quarter: { "2026Q1": [...], "2026Q2": [...] }`
- [ ] Theme `fund_count` = distinct letter files, not keyword hit count.

### Frontend (`insights-viz.js`)

- [ ] Replace `renderPersonaTabs()` with `renderDecisionSummary()` + `renderLensChips()` + `renderLensExpand(persona)`.
- [ ] Replace `renderTickerInsightsStrip()` with `renderContextInsights(insights, { filter, maxRows: 3 })` + source pills.
- [ ] Replace `renderInsightsPanel()` — themes table + fund registry table; remove fund cards grid.
- [ ] Add `renderContributorTable(blend.contributors)` for Tier 4 accordion.

### Frontend (`index.html`)

- [ ] Refactor `selectTicker()` section order: Tier 0 → 1 → 2 → 3 → accordions.
- [ ] Remove duplicate IRR from Classification grid (keep archetype, moat, dhando, cycle only).
- [ ] Rename table header `Blended IRR` → `House IRR`; optional `Lens` column.
- [ ] Wire filter pill click handlers (no full page reload).

### QA

- [ ] `python _system/scripts/validate_dashboard_data.py`
- [ ] Manual: APLD detail — count numeric duplicates (target ≤ 2 per field)
- [ ] Manual: Insights tab — quarter toggle switches theme table
- [ ] Manual: letter insight link opens GitHub path

---

## Tier 0 template (copy structure)

```html
<div class="detail-section decision-summary">
  <h3>Decision</h3>
  <div class="metric-grid">
    <!-- stance, house_irr, lens_blend, agreement, dissent, as_of -->
  </div>
</div>
```

Use existing `.metric`, `.badge`, `.darwin-table` classes — no new CSS framework.

---

## Terminology (use in UI labels)

| Label | Meaning |
|-------|---------|
| House IRR | Lawrence total synthesis @ price |
| Lens blend | Relevance-weighted persona return mean |
| Band | Min–max of contributing persona returns |
| Agreement | % of relevant personas sharing majority verdict |
| Dissent | Highest-conviction opposing persona (one line) |

---

## Out of scope for this task

- Changing persona_lens math
- Auto-promoting insights into base IRR
- New framework markdown files (proposal already exists)

---

## Deliverables

1. Code changes per checklist
2. One-paragraph summary in `_system/reviews/pending/dashboard_ia_{date}.md` with before/after screenshot notes
3. Do not commit unless user asks
