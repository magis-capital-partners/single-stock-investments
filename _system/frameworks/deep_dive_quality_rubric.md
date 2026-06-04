# Deep dive quality rubric

**Gold references:** `FRMO/research/deep_dive_2026-06-04.md`, `TPL/research/deep_dive_2026-06-04.md`  
**Mechanical lint:** `lint_deep_dive.py` (structure, IRR, prose)  
**Depth lint:** `lint_deep_dive_depth.py` (this rubric)

## Scoring

Score each **universal** criterion **0–2**:

| Score | Meaning |
|-------|---------|
| 0 | Missing or boilerplate only |
| 1 | Present but thin (generic, few numbers, weak paths) |
| 2 | FRMO/TPL level: filing paths, numbers, mechanism |

**Pass bar:** **≥18 / 24** (twelve criteria × 2 points) before treating a dive as narrative-complete.

**Archetype extras** (below) are enforced as **errors** in `--strict` depth lint when applicable; they do not change the 24-point cap.

## Universal criteria (all tickers)

| # | Criterion | Score 2 requires |
|---|-----------|------------------|
| 1 | Primary sources | Tiered table with **full** and **partial** rows and document paths |
| 2 | Operating snapshot | **≥8** metrics with latest / prior and filing path |
| 3 | Run-rate vs one-off | Paragraph separating recurring owner cash from specials, M&A, marks |
| 4 | Thesis pillars | **≥3** rows: mechanism, numbers, evidence path |
| 5 | Mental models | **≥3** rows with named framework and source path |
| 6 | Option scan | `#### Option scan` table with **≥6** answered rows (`option_treatment.md`) |
| 7 | Fieldwork / management | Specific facts or explicit none + upgrade path |
| 8 | Risks | **Primary risk** plus **≥3** bullets tied to filing or dated event |
| 9 | Assumption ledger | **≥8** ledger rows with source or **[Assumption]** |
| 10 | IRR arithmetic | Numbered steps under `#### IRR arithmetic (show your work)` |
| 11 | Executive summary | **120–180** words, one synthesis %, no formulas |
| 12 | Milly | Header links `adversarial_*.md`; factual blockers cleared |

## Archetype-specific (N/A when not applicable)

| Archetype | Extra |
|-----------|--------|
| `holding_co` | Look-through table; SOTP or NAV build; catalyst path |
| `optionality` / NAV | GAAP vs economic floor; `nav_overlay` in prose |
| `segment_cashflow` | Segment map with dollars; segment build in valuation |
| `compounder` | Growth mechanism in Business & moat; falsifier with YoY cite |
| HK-indexed | HK scan block + `cross_check_HK_*.md` path |

## Workflow

1. **Phase 2:** Write filing-grounded narrative (`deep_dive_filing_grounded_refresh.md`).  
2. **Phase 3:** `marvin_cloud_refresh.py` syncs ledger/IRR only.  
3. **QA:** `lint_deep_dive.py` then `lint_deep_dive_depth.py` (use `--strict` before merge).

`refresh_deep_dive_v2.py` alone does **not** satisfy this rubric.

## Portfolio audit

```bash
python _system/scripts/audit_deep_dive_depth.py --portfolio
```

Writes `_system/reviews/pending/deep_dive_depth_scorecard_{date}.csv`.

## Grades (automation)

| Total | Grade |
|-------|-------|
| ≥22 | gold |
| ≥18 | adequate |
| ≥12 | thin |
| &lt;12 | incomplete |
