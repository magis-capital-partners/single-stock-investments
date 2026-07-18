# Universe table + ticker detail UX plan

**Date:** 2026-07-18  
**Status:** implemented 2026-07-18  
**Scope:** Holdings universe columns + ticker click-through detail panel  
**Primary files:** `dashboard/index.html`, `dashboard/valuation-viz.js`, `dashboard/insights-viz.js`  
**Related:** `dashboard_information_architecture_2026-06-09.md` (tab IA); this plan is the holdings-table / detail-rail redesign.

---

## Problem (what the GYRO screenshot shows)

Clicking a ticker opens a 380px rail that looks like a decision cockpit but is mostly empty or disconnected:

| UI surface | Symptom | Root cause |
|---|---|---|
| Valuation decision â†’ Base return | Always `â€”` | `annualized_return_at_price_pct` missing on essentially all tickers; classification IRR unused |
| Valuation decision â†’ Power zone | Always `â€”` for most names | Strip reads `primary_power_zone`; persona zones live in `t.power_zones` and render later as chips |
| Valuation decision â†’ Gaps | `0 / 0` with no workbench | Gap counts only meaningful with valuation workbench |
| Human review banner | Thin line only | `human_review.notes[]` never rendered |
| Identity / sleeve | Raw ids (`real_assets_liquidation`) | Labels not preferred in identity line |
| Layout | Cramped tables in 380px | Rail never expands unless equity model / workbench present |
| Universe table | 19 dense columns | Ops + insight + valuation mixed; horizontal scroll; PDF column undercounts SEC |

The strip assumes **workbench-grade** fields. Most of the book is still **provisional component valuation** + persona power zones + classification IRR. The UI should degrade gracefully across those maturity levels instead of showing dashes.

---

## Design principles

1. **Answer first.** Opening a ticker should answer: what is it, what do we think, what is it worth vs price, what blocks a decision, what do I read next.
2. **One maturity path.** Provisional â†’ evidence-blocked â†’ decision-grade should change density and wording, not leave blank cards.
3. **Scan in the table, decide in the panel.** Table = triage; detail = judgment + evidence.
4. **No fake precision.** Prefer â€œnot builtâ€ / â€œuse classification IRRâ€ / â€œpersona fit onlyâ€ over `â€”`.
5. **Reuse existing tokens.** Keep dark theme, DM Sans / JetBrains Mono, badge system; fix information architecture, not skin.

---

## Target information architecture

### A. Universe table â€” column model

Replace the flat 19-column dump with a **default compact set** + optional column groups (toggle in toolbar, persisted in `localStorage`).

#### Default columns (always on)

| Column | Content | Notes |
|---|---|---|
| Ticker | Symbol + optional `M` / onboard badge | Keep |
| Company | Name | Keep; truncate with title tooltip |
| Mkt | Market badge | Keep |
| Sleeve | Human sleeve label | Prefer `investment_sleeve_label`; hide raw id |
| Stance | Badge | Keep |
| Val | Status badge + short subline | Keep; drop separate â€œNeedsâ€ if val subline covers gaps |
| Value | `$lowâ€“$high` Â· base | Compact; show `incomplete` only when truly missing |
| vs price | Signed % to base | Keep; tooltip distinguishes provisional |
| IRR | Classification / analysis IRR % | **New** â€” use existing `renderIrrCell` |
| Zone | Top persona power-zone chip or `â€”` | **New** â€” from `power_zones.in_zone[0]` |
| Dive | Deep-dive date link | Keep |

#### Optional groups (off by default)

| Group | Columns | When to enable |
|---|---|---|
| **Ops** | PDFs (drive + SEC combined), Complete, Download | Download / onboard sessions |
| **Insights** | Insight, Fresh, Source, Needs | Daily insight triage (or fold into Watchlist/Insights tabs) |
| **Index / activism** | Index, Activist | Event / activism sweeps |

**PDF cell fix:** show `drive_pdfs + SEC` as `12 Â· +49 SEC` (or single total with tooltip), never bare `0` when `sec_filings > 0`.

**Archetype:** move off the default table into the detail identity line (still filterable via sleeves / search). Optional group if needed.

#### Filters (keep, tighten labels)

- Markets / sleeves / vals stay.
- â€œNeeds workâ€ becomes a vals-adjacent toggle that also matches insight `needs_work` **or** critical gaps > 0.
- Add optional **Power zone** filter later (persona chips) once Zone column ships.

#### Sort defaults

- Default sort: stance priority then |vs price| or IRR (document choice in UI).
- Persist last sort + column groups in `localStorage`.

---

### B. Ticker detail â€” panel redesign

#### Layout

1. **Wider detail by default** when a ticker is selected: `minmax(420px, 42vw)` rail (not only when workbench/model exists). Keep `.model-expanded` full-bleed for equity-model / workbench deep work.
2. **Sticky header** inside `#detail`: ticker, company, close/back affordance, deep-dive link.
3. **Section order (fixed):**

```
1. Sticky header + one-line thesis (if any)
2. Decision hero          â† redesigned strip
3. Human review           â† richer, collapsible
4. Identity chips         â† archetype / moat / dhando / sleeve (labels)
5. Valuation body         â† workbench OR legacy components (one primary)
6. Power zones            â† persona chips + primary zone callout
7. Read next              â† deep dive, folder, essential insights (top 3)
8. Context (collapsed)    â† dossier, research memory, letters, activist, files
9. Infra (collapsed)      â† completeness, downloads, SEC counts
```

Dead code to wire or delete: `tier0`/`tier2` stubs, unused `consensusDetail`, unused `renderInvestmentCommittee` / lens chips.

#### Decision hero (replace current 6-metric grid)

Three visual bands:

**Band 1 â€” Position**
- Stance (large badge)
- Valuation readiness (decision-grade / provisional / evidence-blocked)
- As-of date

**Band 2 â€” Price vs value**
- Live / last price
- Base value per share
- Upside/downside % (colored)
- Lowâ€“high range as a small track (reuse component range visual)

**Band 3 â€” Return & method (fallback chain)**
1. `annualized_return_at_price_pct.base` if present â†’ label **Base return at price**
2. Else `classification.analysis_irr_pct` / `implied_irr` â†’ label **Thesis IRR (classification)** with subtext that it is not price-implied workbench return
3. Else show **Return not modeled** (not `â€”`)

**Power zone cell**
1. `valuation_decision.primary_power_zone` if set
2. Else first of `power_zones.in_zone` with persona label + fit %
3. Else **No persona zone** (not `â€”`)

**Gaps cell**
- If workbench: `critical / open` + next action
- If provisional without workbench: hide gap counters; show one line: *Provisional component valuation â€” workbench not built*
- If evidence-blocked: list top gap ids / next action only

#### Human review

Render when `human_review` is truthy:
- Entry band / approved stance / override (existing)
- **`notes[]` as bullets** (currently dropped â€” GYRO has four)
- Collapse if only empty scaffolding

#### Valuation body

- Prefer workbench tabs when present (expand rail).
- Else legacy component schedule, but **move** under a clear heading â€œComponent valuation (provisional)â€ and put the decision hero above it so users see price/value before the accounting table.
- Pricing cross-check and properties stay as secondary cards.

#### Power zones section

- Promote above dossier/memory (already listed in new order).
- Show primary zone in hero; full chip row here with fit/score tooltips (existing markup).

#### Read next

Single card:
- Deep dive link + date + one-line thesis
- Folder / IR links
- Top 3 essential insight bullets (not the full essentials wall)

Everything else starts collapsed (`<details open>` only for active valuation body).

---

## Data / builder work (small, paired with UI)

| Change | Where | Why |
|---|---|---|
| Populate or stop advertising `annualized_return_at_price_pct` | `build_dashboard_data.py` / valuation decision builder | Either compute from price + payoff, or omit so UI uses classification IRR fallback |
| Set `primary_power_zone` from top `power_zones.in_zone` when null | builder or UI fallback (UI fallback first) | Unblocks Zone column + hero without waiting for workbench |
| Sleeve labels everywhere | registry / classification sync | Kill raw ids in table + identity |
| PDF + SEC composite for table | `build_dashboard_data.py` or cell renderer | Fix `0` PDF optics |
| Optional: expose `display_irr` + `display_irr_source` on ticker | builder | One field for table + hero |

Prefer **UI fallbacks first** (ship faster), then harden in JSON so mobile/export stay consistent.

---

## Implementation phases

### Phase 0 â€” Truthfulness hotfix (0.5â€“1 day)

No layout change; stop lying with dashes.

- [ ] Decision strip fallbacks for return + power zone + provisional gap copy (`valuation-viz.js`)
- [ ] Render `human_review.notes`
- [ ] PDF cell shows SEC when drive count is 0
- [ ] Prefer sleeve labels in identity line
- [ ] Expand detail rail whenever a ticker is selected (CSS)

**Exit:** GYRO-like provisional names show thesis IRR, persona zone, and review notes without empty hero.

### Phase 1 â€” Universe column reform (1â€“2 days)

- [ ] Default column set + `localStorage` column-group toggles
- [ ] Add IRR + Zone columns; demote Ops/Insights groups
- [ ] Archetype off-default
- [ ] Sort persistence
- [ ] Smoke: filters + sort + click still work

**Exit:** Table scannable without horizontal scroll on a 1440px laptop for the default set.

### Phase 2 â€” Detail IA reorder (1â€“2 days)

- [ ] Sticky header + one-line thesis
- [ ] Decision hero bands
- [ ] Section reorder + collapse defaults
- [ ] Wire or remove dead `consensusDetail` / lens / IC renderers
- [ ] Full-bleed only for workbench/equity model

**Exit:** First viewport of detail answers stance / value / return / zone / next read.

### Phase 3 â€” Polish + data hardening (1 day)

- [ ] Builder fields for `display_irr` / `primary_power_zone` backfill
- [ ] Empty/error states for missing deep dive, missing price, stale dossier
- [ ] Keyboard: `Esc` closes detail, `j`/`k` move selection (optional)
- [ ] Light visual polish: hero hierarchy, less nested tables above the fold
- [ ] Validate against AAOI/ASTS (new dives), GYRO (provisional land), one decision-grade name if any

---

## Explicit non-goals (this plan)

- Redesigning Insights / Darwin / Watchlist tabs (separate IA)
- New color theme or light mode
- Replacing valuation math / IRR ledger rules
- Mobile-first rewrite (desktop Magis workflow first; keep usable)

---

## Success criteria

1. Provisional ticker (GYRO): no critical hero fields show bare `â€”` when classification IRR or persona zones exist.
2. Default universe view â‰¤ ~11 columns; no required horizontal scroll at 1440px.
3. Click â†’ decision answer visible without scrolling past the fold on a 1080p screen.
4. Human review notes visible when present.
5. Power zone in table and hero agree for the same ticker.
6. `validate_dashboard_data.py` still green; Pages deploy-only still green.

---

## Test plan

- Manual: GYRO, AAOI, ASTS, one evidence-blocked, one decision-grade (if present), one incomplete valuation.
- Column toggles persist across reload.
- Filters (sleeve + vals + needs work) still match after column moves.
- Screenshot before/after first viewport of detail.
- Optional: small unit tests for fallback helpers in `valuation-viz` if extracted to pure functions.

---

## Open questions for human

1. Should default sort prioritize **stance** or **vs-price discount**?
2. Is classification IRR acceptable in the table labeled **Thesis IRR**, or only inside the detail hero?
3. Should Insights columns move permanently to the Insights / Watchlist tabs (recommended) or remain an optional universe group?
4. Detail close behavior: click outside / `Esc` / explicit Ã— â€” which minimum set?

---

## Suggested first PR

**Phase 0 only** â€” truthfulness fallbacks + notes + PDF/SEC + wider rail. Low risk, high visible fix on the exact GYRO failure mode, unblocks judging Phase 1â€“2 layout choices with real content.

