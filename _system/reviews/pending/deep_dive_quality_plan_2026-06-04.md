# Deep dive quality plan — FRMO / TPL gold standard

**Date:** 2026-06-04  
**Author:** Marvin (analysis pass)  
**Reference dives:** `FRMO/research/deep_dive_2026-06-04.md`, `TPL/research/deep_dive_2026-06-04.md`  
**Contrast:** `MRSH/research/deep_dive_2026-06-03.md`, portfolio `deep_dive_2026-06-04.md` batch (mechanical refresh)

---

## 1. What FRMO and TPL actually deliver

Both are ~3,500–3,700 words and pass `lint_deep_dive.py`. Length alone is **not** the differentiator (many refreshed dives are 2,200–3,200 words). The gap is **filing-grounded specificity** and **archetype-complete overlays**.

### FRMO (holding_co / yield_curve)

| Dimension | What “good” looks like |
|-----------|-------------------------|
| **Business model** | Explains non-operating holdco; names Investment A (~82%), MIH, HKHC, royalties with **dollar marks** from Q3 FY2026 quarterly |
| **Why mispriced** | OTC friction, mark volatility, dormant-asset framing; ties to Horizon Kinetics vocabulary |
| **Primary sources** | **Tiered inventory** (full / partial / scan) tied to `INDEX.csv` + `document_inventory.json` (41 files) |
| **Operating snapshot** | Balance sheet lines with YoY; separates **unrealized gains** from owner economics |
| **Mental models** | 7 rows with **named sources** (SSI, Lemon Cakes, HK extracts, cross-check paths) |
| **Thesis pillars** | 4 pillars: mechanism + numbers + **filing path per row** |
| **Look-through** | Table: stake, GAAP carrying, economic gap, driver (MIH IPO, lockup) |
| **Governance** | Late filing, tax restatement Jan 2026, related-party lease, board change, insider % |
| **Valuation** | **SOTP ledger** (10+ uplift lines), stepped payoff build to $18/sh, ties to `sotp_build` in JSON |
| **Third party** | Approved Substacks in narrative; cross-check file linked in header |

### TPL (infrastructure + segment + NAV)

| Dimension | What “good” looks like |
|-----------|-------------------------|
| **Business model** | Acreage, royalty vs water segment; FY2025 + Q1 2026 **revenue/OI/OCF** from 10-K/10-Q paths |
| **Why mispriced** | **1888 trust assets at zero on balance sheet**; explains why GAAP book is wrong floor |
| **Primary sources** | Full-tier SEC paths; notes IR PDF extract failures honestly |
| **Segment map** | **Exact segment revenue table** ($411.7M royalties, $307.5M water, % of total) |
| **HK block** | Auto-scan + `cross_check_HK_*.md`; predictive attributes named |
| **Option scan** | Complete; NAV / land optionality tied to `nav_overlay` |
| **Valuation** | Lawrence cash path **plus** segment/NAV overlay; 32 ledger rows; segment IRR tie-out |
| **Risks** | Permian cycle, produced-water regulation, special dividend normalization |

### What mechanical refresh alone does **not** add

`refresh_deep_dive_v2.py --all` (Jun 2026 batch) mainly:

- Reorders sections to v2 layout  
- Syncs executive summary / returns statement % to `valuation.json`  
- Renders valuation ledger / synthesis blocks from JSON  

It **preserves** prior narrative if present; it does **not** require tiered sources, pillar tables, look-through, or HK blocks. Tickers refreshed without a prior **Phase 2 narrative pass** stay structurally valid but narratively thin.

---

## 2. Portfolio snapshot (2026-06-04 dives)

| Tier | Tickers | Issue |
|------|---------|--------|
| **Gold** | FRMO, TPL, KEWL, BWEL, VTRS, GOOGL, LB | Strong overlays and/or multi-pass narrative |
| **Adequate structure** | Most names with `deep_dive_2026-06-04.md` | Pass lint; pillars present; ledger 18–30 rows |
| **Thin evidence** | ICE, 3905.T, IDA.AX, DRR.AX (partial) | Missing tiered sources table or &lt;15 ledger rows |
| **No dive** | 21 batch-onboard (HE, CBOE, FNV, …) | Thesis only; `valuation.json` absent |

**MRSH** (~2,550 words): Good compounder narrative and segment map; weaker than FRMO/TPL on **filing path density** (12 cites vs 27), no HK/Substack block, no SOTP (correct for archetype).

---

## 3. Root causes of uneven depth

1. **Two-step pipeline conflated** — Team sometimes treats `marvin_cloud_refresh.py` as “the deep dive.” Runbook Phase 2 (narrative) must precede Phase 3 (mechanical).  
2. **No depth lint** — `lint_deep_dive.py` checks section order, IRR match, banned prose; not citation count, pillar quality, or evidence tier.  
3. **Evidence tier gap** — `build_filing_evidence.py` + full-tier `_text/` required before numbers in tables; many tickers still on digest-only or failed PDF extract (3905.T).  
4. **Overlay JSON not seeded** — FRMO-quality SOTP needs `sotp_build` / `catalyst_paths`; TPL needs `segment_build` + `nav_overlay`. `seed_dive_overlays.py` helps but does not write prose.  
5. **Batch onboard skipped Phase 2** — 21 names have scaffold thesis only.  
6. **Milly checks facts, not richness** — Adversarial pass catches errors, not “generic mental models.”

---

## 4. Target standard (rubric)

Score each dive **0–2** per row (0 = missing, 1 = partial, 2 = FRMO/TPL level). **Pass bar: ≥18/24** before “final” (excluding archetype-specific rows marked N/A).

### Universal (all tickers)

| # | Criterion |
|---|-----------|
| 1 | Primary sources table: **full + partial** tiers with paths and “role in report” |
| 2 | Operating snapshot: **≥8 metrics** with latest, prior/YoY, filing path |
| 3 | Run-rate vs one-off paragraph (M&A, specials, unrealized, divestitures) |
| 4 | Thesis pillars: **≥3 rows** with mechanism, numbers, evidence path |
| 5 | Mental models: **≥3 rows** with named framework + source path |
| 6 | Option scan: full 8-question table per `option_treatment.md` |
| 7 | Fieldwork / management: specific facts or explicit “none” + what would upgrade |
| 8 | Risks: primary risk + **≥3 bullets** citing filing or event |
| 9 | Assumption ledger: **≥8 rows**, each with source or **[Assumption]** |
| 10 | IRR arithmetic: numbered steps; no orphan payoffs |
| 11 | Executive summary: 120–180 words, one synthesis %, no formulas |
| 12 | Milly adversarial file linked; factual blockers cleared |

### Archetype-specific (score N/A if not applicable)

| Archetype | Extra criteria |
|-----------|----------------|
| **holding_co** | Look-through table; SOTP payoff build; catalyst timeline |
| **optionality / NAV** | GAAP vs economic floor explained; `nav_overlay` in prose |
| **segment_cashflow** | Segment map with $ from 10-K note; segment build in §11 |
| **compounder** | Growth mechanism in Business & moat; falsifier filing YoY cited |
| **HK-indexed** | HK scan block + cross-check path |

---

## 5. Implementation plan

### Phase A — Governance (1–2 days human + script)

| Step | Action | Owner |
|------|--------|-------|
| A1 | Adopt rubric above as `_system/frameworks/deep_dive_quality_rubric.md` | Human approve |
| A2 | Add `lint_deep_dive_depth.py` — fail on rubric thresholds (configurable strict mode) | Engineering |
| A3 | Extend Milly YAML: `narrative_depth: thin | adequate | gold` + bullet gaps | Engineering |
| A4 | Update `cloud_marvin_runbook.md`: **“Refresh-only ≠ deep dive”** banner | Done in plan |

### Phase B — Tooling prerequisites

| Step | Action |
|------|--------|
| B1 | `make research-check` runs depth lint after structure lint |
| B2 | `audit_deep_dive_depth.py --portfolio` → CSV in `_system/reviews/pending/` |
| B3 | `seed_dive_overlays.py --all --write` for holdco/optionality names (no FRMO overwrite) |
| B4 | `build_filing_evidence.py` gate: depth lint warns if `full_tier_count < 2` |

### Phase C — Marvin workflow (per ticker)

Enforce order from `cloud_marvin_runbook.md`:

```
1. build_filing_evidence.py + read filing_digest + full-tier _text/
2. scan_third_party_sources.py --with-hk
3. Write valuation.json inputs (human-approved overlays preserved)
4. Write cross_check_third_party_{date}.md
5. Write deep_dive_{date}.md using deep_dive_filing_grounded_refresh.md prompt
   — copy FRMO/TPL sections as checklist, not as template boilerplate
6. marvin_cloud_refresh.py {TICKER} --date {date}
7. milly-repass if needed
8. lint_deep_dive.py + lint_deep_dive_depth.py
```

**Prompt addition:** `_system/prompts/deep_dive_filing_grounded_refresh.md` should include explicit “FRMO/TPL checklist” appendix (tiered sources, pillars, look-through/segment, governance facts).

### Phase D — Portfolio rollout (priority queue)

| Priority | Tickers | Rationale |
|----------|---------|-----------|
| **P0** | Holdings with capital at risk + thin dives | ICE, 3905.T, META (no prior dive link), RMV.L, LB |
| **P1** | Core compounders refreshed mechanically only | AMZN, GOOGL, BN, CSU, DHR — add segment/AI blocks where JSON exists |
| **P2** | Batch onboard (21) | Full cloud Marvin per `onboard_batch_2026-06-03.json`; skip mechanical-only |
| **P3** | Already strong | FRMO, TPL, KEWL, BWEL, VTRS — **maintain** on refresh; do not replace with thin regen |

**Rule:** For P1–P3, **edit forward** from latest `deep_dive_*.md`; do not delete narrative to run refresh on empty body.

### Phase E — Human quality filter

| Step | Action |
|------|--------|
| E1 | Human reads rubric scorecard for P0 names in `_system/reviews/pending/` |
| E2 | Promote only `[PROPOSED]` beliefs after approved review (existing pipeline) |
| E3 | Dashboard: show depth grade next to IRR (optional UI follow-up) |

---

## 6. Success metrics

| Metric | Baseline (Jun 2026) | Target |
|--------|---------------------|--------|
| Dives with tiered sources table | ~70% | 100% of holdings with dive |
| Dives ≥18/24 rubric | ~40% (est.) | 90% within 2 refresh cycles |
| Holdings with `valuation.json` + dive | 30 / 51 | 51 / 51 |
| Full-tier filing extracts (≥2 docs) | varies | All US/Japan/EU core holdings |
| Mechanical-only dives (depth lint fail) | ~15 | 0 |

---

## 7. What not to do

- **Do not** run `refresh_deep_dive_v2.py --all` on the portfolio as a substitute for narrative work.  
- **Do not** copy FRMO’s SOTP math onto compounders (archetype mismatch).  
- **Do not** inflate word count with synthesis/Popper tables (removed from v2 spec for narrative sections; keep synthesis capstone only).  
- **Do not** mark dives FINAL without Milly + depth lint pass + human spot-check on P0.

---

## 8. Immediate next actions

1. Human: approve rubric thresholds (Section 4).  
2. Engineering: implement `lint_deep_dive_depth.py` (Phase A2).  
3. Marvin: P0 queue — **ICE**, **3905.T**, **META** filing-grounded refresh (new dated dive, not refresh-only).  
4. Marvin: P2 — cloud Marvin on batch onboard tickers in holdings order (FNV, CBOE, HE, …).  
5. Log progress in `_system/reviews/pending/deep_dive_depth_scorecard_{date}.csv` after audit script exists.

---

## References

- `FRMO/research/deep_dive_2026-05-26.md` (original narrative; 2026-06-04 preserves it)  
- `TPL/research/deep_dive_2026-06-02.md` (inaugural filing-grounded)  
- `_system/frameworks/deep_dive_structure.md`  
- `_system/prompts/cloud_marvin_runbook.md` Phase 2 vs 3  
- `_system/scripts/seed_dive_overlays.py` (FRMO-style JSON, not prose)
