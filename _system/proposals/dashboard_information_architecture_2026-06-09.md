# Proposal: Dashboard information architecture — max signal, min redundancy

**Date:** 2026-06-09  
**Status:** Implemented — UI Phase 2 (2026-06-09)  
**Author:** Marvin (draft)  
**Builds on:** `persona_lens_consensus_2026-06-08.md` (implemented), `fetch_superinvestor_letters.py` (implemented)

---

## Problem

The dashboard now has **four overlapping verdict layers** on one ticker:

| Layer | Where shown today | Redundant with |
|-------|-------------------|----------------|
| Lawrence synthesis IRR | Table column, Classification, deep dive | Lens blend (similar number, different label) |
| Classification stance | Table, Classification grid, deep dive badge | Lens consensus stance |
| Persona consensus | Persona tab (Consensus) | Classification + table stance |
| External insights | Insights tab + ticker strip | Same letter claim may appear in fund cards + strip |

Plus **noise**: macro context (VIX, WTI) sits beside letter claims in the same list; silent personas still appear as tabs; Insights tab theme counts inflate from keyword heuristics (152 funds mention “AI”).

**Goal:** One glance = decision-ready. One click = drill-down. **Never show the same number twice without a reason.**

---

## Design principles (non-negotiable)

1. **Single owner per fact** — each datum has one *primary* surface; elsewhere = link or badge only.
2. **Progressive disclosure** — summary → expand → source file. Default view ≤ 6 lines above the fold on ticker detail.
3. **Relevance gate UI** — if `relevance === 0`, hide (not grey). Max 3 active persona chips + “+N silent”.
4. **Source-labeled context** — external insights never share a row shape with house verdicts; always tagged `letter | macro | insider | third_party`.
5. **House vs context** — house numbers (IRR, stance) may drive sizing; context (`in_base_irr: false`) never duplicates house fields.

---

## Information hierarchy (what owns what)

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 0 — Action row (ticker detail, always visible)        │
│  Stance · House IRR · Lens blend · Agreement · Dissent?     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  TIER 1 — Identity (collapsed by default if long)           │
│  Archetype · Moat · Dhando · Payoff lens · Cycle            │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  TIER 2 — Active lenses only (chips, not full tabs)         │
│  Hohn watch 9% · Pabrai pass · [+4 silent]                  │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  TIER 3 — External context (filtered default: letters only) │
│  Who discusses · max 3 rows · link to evidence              │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  TIER 4 — Deep (details / accordions)                       │
│  Persona drill-down · Macro · Infra · Deep dive · Files     │
└─────────────────────────────────────────────────────────────┘
```

### Field ownership (eliminate duplication)

| Field | Primary surface | Secondary (allowed) |
|-------|-----------------|---------------------|
| **House IRR** (Lawrence synthesis) | Tier 0 label `House 11.9%` | Table sort column only (same value) |
| **Lens blend** | Tier 0 `Blend 8.7% [1–17]` | Persona expand only — not in Classification |
| **Stance** | Tier 0 badge — **approved human stance if set**, else lens consensus | Table badge (same source) |
| **Archetype / moat / dhando** | Tier 1 compact row | Not repeated in persona tabs |
| **Persona return/verdict** | Tier 2 chips OR expanded persona panel | Never in Classification grid |
| **Letter / macro insights** | Tier 3 with source chip | Insights tab = portfolio aggregate only |
| **Theme rankings** | Insights tab only | Not on ticker detail |
| **Calibration table** | Insights tab footer | Not on ticker detail |

**Remove from ticker detail:** duplicate “Blended IRR” inside Classification when Tier 0 exists. **Remove:** full persona tab strip default-open; replace with chips + single expand.

---

## Holdings table (scan layer)

Keep columns minimal — **decision scan**, not analysis dump:

| Column | Source | Notes |
|--------|--------|-------|
| Ticker | — | |
| Archetype | classification | badge |
| House IRR | `classification.analysis_irr_pct` | rename header from “Blended IRR” → **House IRR** |
| Lens blend | `lenses.valuation_blend.blended_return_pct` | new column OR tooltip on IRR |
| Stance | approved or consensus | |
| Lens Δ | `house − blend` if >2pp | flags disagreement |
| Deep dive | link | |

Drop from table: completeness bar (move to Tier 4), duplicate stance sources.

---

## Insights tab (portfolio context — no house verdicts)

Restructure into **two panes only**:

### Pane A — Letter themes (quarter-scoped)

- Quarter toggle: `2026Q1 | 2026Q2 | All`
- Table: Theme · Letters mentioning · Net sentiment · Top tickers (linked)
- **Fix:** theme counts = distinct *letters*, not raw keyword hits per paragraph
- Click theme → filtered ticker list (holdings highlighted)

### Pane B — Fund registry

- Search box + sort by name / ticker overlap with **our book**
- Row: Fund · Quarter · Tickers in our book · Sample claim · Open extract
- **Remove:** duplicate fund “cards” grid (merge into sortable table)
- Cap display with pagination, not arbitrary 12-card slice

**Remove from Insights tab:** persona calibration (move to `_system/reviews/` or admin footnote link) unless match rate ≠ n/a.

---

## Ticker detail (implementation spec)

### Tier 0 — Action row (single `metric-grid` 2×3)

```
┌──────────────┬──────────────┬──────────────┐
│ Stance       │ House IRR    │ Lens blend   │
│ watch        │ 11.9%        │ 8.7% [1–17]  │
├──────────────┼──────────────┼──────────────┤
│ Agreement    │ Dissent      │ As of        │
│ 91%          │ Stahl hold   │ 2026-06-07   │
└──────────────┴──────────────┴──────────────┘
```

- If `human_review.approved_stance`: show **Approved** badge; lens consensus as subtext `(lens: watch)`.
- If `lens_consensus.lawrence_divergence`: amber ⚠ on House IRR.

### Tier 1 — Identity (one line + optional expand)

`compounder · moat widening · dhando partial · operating lens`

### Tier 2 — Active lenses (chips)

`Hohn watch 8.6% · Munger watch 8.6% · Lawrence 11.9%` · `[+5 silent]`

Click chip → inline expand (metrics + falsifier), not separate tab strip.

### Tier 3 — External context

Filter pills: `[Letters]` `[Macro]` `[Insider]` `[All]` — default **Letters**.

Max **3 rows**; each row:

```
[letter] Pershing · add · APLD · "…claim…" · ↗ extract
```

`↗` opens GitHub blob or local path from `evidence_ref`.

**Do not** show macro rows when Letters filter active.

### Tier 4 — Accordions (unchanged content, reordered)

1. Marvin deep dive (thesis + summary)
2. Persona consensus detail (contributors table from blend)
3. Infrastructure / equity model
4. Recent developments / files

---

## Data contract changes (minimal)

Extend `build_dashboard_data.py` ticker row:

```json
{
  "decision_summary": {
    "stance": "watch",
    "stance_source": "lens_consensus|approved",
    "house_irr_pct": 11.9,
    "lens_blend_pct": 8.68,
    "lens_band_pct": [1.3, 16.6],
    "agreement_pct": 91,
    "top_dissent": { "persona": "stahl", "verdict": "hold" },
    "divergence": false,
    "as_of": "2026-06-07"
  },
  "active_lenses": [
    { "persona": "hohn", "label": "Hohn", "verdict": "watch", "return_pct": 8.6, "relevance": 1.0 }
  ],
  "silent_lens_count": 5,
  "insights": [ "... max 10; UI slices to 3 per filter ..." ]
}
```

Precompute in Python — **UI does not parse lenses.json shape**.

Insights tab: add `theme_rankings_by_quarter` in `build_insights.py`.

---

## Redundancy audit (delete list)

| Remove | Replace with |
|--------|--------------|
| Classification grid duplicate IRR | Tier 0 House IRR |
| Persona sub-tab strip (default) | Tier 2 chips + expand |
| Fund cards grid on Insights tab | Fund registry table |
| Mixed-source insight list (default) | Letters-only filter default |
| Theme keyword inflation | Distinct-letter counting |
| “Blended IRR” label | **House IRR** vs **Lens blend** (two defined terms) |

---

## Success criteria

- Ticker detail **Tier 0–2** fits on one laptop screen without scroll (≤ ~400px).
- No numeric field appears **more than twice** on ticker detail (table column exempt).
- Insights tab loads with **one** primary table visible (themes); fund registry collapsed or second tab.
- Letter insight row click → evidence opens in <2 clicks.
- `validate_dashboard_data.py` checks `decision_summary` required keys when `lenses` present.

---

## Implementation phases

| Phase | Scope | Effort |
|-------|--------|--------|
| **UI-1** | `decision_summary` in build_dashboard_data + Tier 0–2 ticker detail refactor | 1 day |
| **UI-2** | Insight source filters + evidence links + remove Classification IRR dup | 0.5 day |
| **UI-3** | Insights tab quarter toggle + theme fix + fund table | 1 day |
| **UI-4** | Holdings table House vs Lens columns | 0.5 day |
| **UI-5** | Deep dive generated Tier 0 block (optional sync) | 0.5 day |

**Agent prompt:** `_system/prompts/dashboard_information_architecture.md`

---

## Non-goals

- Real-time insight streaming
- In-browser PDF viewer (GitHub links sufficient)
- Merging house IRR and lens blend into one number
- Showing all 4,004 insight records in UI

---

## Open decisions

1. Table: add **Lens blend** column vs keep IRR-only with hover band?
2. Default stance: **approved** always wins, or show both when they differ?
3. Hide **Infrastructure** block behind accordion by default?
