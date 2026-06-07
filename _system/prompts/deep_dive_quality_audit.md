# Deep dive quality audit and simplification pass

Use after Marvin writes or refreshes `{TICKER}/research/deep_dive_{date}.md`, or when a human flags gaps / N/A / redundancy.

**Goal:** One readable report. Every number has a source or **[Assumption]** / **[HUMAN REVIEW]**. No duplicate sections. Mechanical blocks come from `valuation.json`; narrative stays in Business & moat.

**Read first:** `deep_dive_structure.md`, `report_prose.md`, `irr_assumption_ledger.md`, `growth_explanation_stress_test.md`

**Mechanical QA:**
```bash
python3 _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python3 _system/scripts/refresh_deep_dive_v2.py {TICKER}
python3 _system/scripts/lint_deep_dive.py {TICKER} --strict
python3 _system/scripts/lint_adversarial.py {TICKER}
```

---

## Task

Audit `{TICKER}/research/deep_dive_{date}.md` against `{TICKER}/research/valuation.json` and filing evidence. Fix issues in **this order** (simplicity first: delete before adding).

### Phase 1 — Delete redundancy (say once)

| Pattern | Keep | Remove / merge |
|---------|------|----------------|
| Acreage, renewables, repurchases, stance | Executive summary OR What this business is | Do not repeat full blocks in both |
| IRR % | Executive summary (one %) + Valuation returns statement (one sentence) | IRR in Mental models, Payoff, duplicate returns statements |
| NAV / overlay | One labeled figure per lens in Payoff `Optionality overlay` | Scattered ~$1,180 vs ~$1,875 vs ~$3,445 without labels |
| Bear / bull detail | `valuation.json` scenarios | Extra bridge tables; more than one sentence in Payoff |
| Deprecated blocks | — | `### Valuation bridge`; Popper/Deutsch weight tables; `### Growth explanation stress test`; weight-scheme falsifier lists (see `growth_explanation_stress_test.md` § Removed) |
| Synthesis | One `### Total synthesis IRR` table + `#### Synthesis arithmetic` + **one** returns line | Second `**Returns statement:**`; duplicate synthesis prose |

**Rule:** Business & moat has **no** IRR math, assumption ledger, or segment PV tables.

### Phase 2 — Fix missing / broken data (N/A, None, placeholders)

Run this checklist; each failure needs a fix or explicit **[HUMAN REVIEW]**:

1. **Assumption ledger** — Every row has a real value. Delete rows that render `$None`, `n/a`, or `external_view_blend` with no `per_share` in JSON (e.g. `estimates.blended_best` without `per_share`).
2. **Segment cash-flow build** — If `valuation_overlay: segment_cashflow`:
   - Run `marvin_valuation.py --write` so `segment_build` gets `owner_cash_y0_per_share`, `pv_per_share_at_*`, and `reconciliation`.
   - Table must not be all `n/a`. Missing PV → fix JSON, not hand-type `n/a`.
   - Footer `Lawrence base` must match `results.base.return_pct` (not stale pre-refresh %).
   - Include `#### Segment IRR arithmetic` with sum PV vs price tie-out.
3. **Thematic context** — If a row is `stale` or `latest: null` in `context_overlay`, either refresh via `fetch_market_inputs.py` / `marvin_cloud_refresh.py` or **drop the row** (do not publish six duplicate stale macro lines).
4. **Seven-year / trend tables** — Replace `per 20XX annual` with actual share counts or omit the column.
5. **Catalyst path** — Replace `(? years)` with a range or **[HUMAN REVIEW]**.
6. **`not_in_model_requires_refresh`** — Each JSON item → one bullet under Risks or [HUMAN REVIEW].

### Phase 3 — Reconcile inconsistent numbers (same concept, one label)

Before editing prose, write a **lens table** (internal scratch, not in report):

| Lens | Field | Source in JSON |
|------|-------|----------------|
| Tax book / equity | $/sh | `inputs.book_per_share` |
| Run-rate NAV (today rentals × multiple) | $/sh | Current filings capitalized |
| Steady-state NAV (GB ramp) | $/sh | `nav_overlay.overlay_nav_per_share` or `scenarios.base.sotp_build` |
| Third-party full asset NAV | $/sh | `estimates.external[].nav_per_share_base` |
| Lawrence stance gate | % | `implied_return.lawrence_stance_gate_pct` or `results.base.return_pct` |
| Display / synthesis return | % | `implied_return.base_pct` / `synthesis.total_synthesis_pct` |

**Fix rules:**
- Never mix lenses in one sentence (e.g. "1.2× NAV" using $1,875 in exec but "1.9× overlay" using $1,180 in Gate 5).
- Label in prose: **run-rate overlay**, **Marvin blended overlay**, **Groundbreaker asset NAV**.
- Gate 5 "cheap vs normalized" must use the **same** overlay NAV cited in Payoff.
- Classification row must name the metric: `Implied 7yr IRR (synthesis)` vs `(Lawrence)` — match the % source.
- Cross-check doc synthesis % must match dive (re-run refresh after `valuation.json` update).

### Phase 4 — Framework compliance (errors)

| Check | Pass criteria |
|-------|----------------|
| Section order | `deep_dive_structure.md` table |
| Primary IRR label | Exec + returns statement use same % as `implied_return.base_pct`; Payoff cites Lawrence gate separately when different |
| Plain English | No `P₀`, `FCF₀`, `g1`, `g2`, `bn`, `mgmt` in narrative or ledger (`report_prose.md`) |
| Option scan | Present for every ticker; treatments match `valuation.json` `option_scan` |
| Look-through | Only for holdco; optionality names use `nav_overlay` in Payoff, not duplicate SOTP in Moat |
| Em dashes | ≤1 per report |
| Executive summary | 120–180 words; one base % only |
| Adversarial | Milly pass linked; fix blocking factual errors before final |

### Phase 5 — Simplify synthesis (when `synthesis.status: complete`)

Keep **only**:
1. `### Total synthesis IRR (all sources)` — path / return / weight table (5–7 rows max)
2. `#### Synthesis arithmetic (show your work)` — weighted sum + qual pp
3. One line: `**Returns statement (synthesis):**` OR `**Returns statement:**` (not both with same %)
4. Optional one-line `**[HUMAN REVIEW]:**` if `synthesis.human_approval: pending`

Remove: `#### Why these weights (Popper / Deutsch)`, `#### Weight-scheme falsifiers`, `#### Deutsch checks` — philosophy stays in `_system/reference/philosophy/`, not the dive.

---

## Output

1. **Audit memo** (chat or `{TICKER}/research/qa_{date}.md` if human asked for file):
   - Missing data (table)
   - Redundancy (table)
   - Errors / inconsistencies (table)
   - Prioritized fix list (P0 = wrong number, P1 = N/A block, P2 = bloat)

2. **Edits** — Apply fixes via refresh pipeline first; hand-edit only preserved narrative blocks (exec summary, growth mechanism, risks).

3. **Re-run lint** — `lint_deep_dive.py --strict` must pass; Milly re-pass if facts changed.

---

## Anti-patterns (do not reintroduce)

- Publishing stale macro tables with ten `n/a (stale)` rows
- Segment build table present but empty (delete section until JSON populated)
- Two NAV figures in Gate 5 and Executive summary without labels
- `Blended owner cash | $None` ledger row
- Stale footer `Lawrence base: -21%` when JSON says `-8.7%`
- Total synthesis + full Popper/Deutsch appendix (duplicate epistemology)
- Using Permian production indicators as primary context for non-Permian tickers without one-line scope note

---

## AZLCZ reference gaps (2026-06-05 — use as regression test)

When changing refresh or lint, confirm these do not recur:

- Segment build all `n/a`; orphan `Lawrence base: -21%`
- NAV $1,180 (run-rate look-through) vs $1,875 (blended) vs $3,445 (GB) unlabeled
- Gate 5 `~1.9× overlay` vs exec `~1.2×` on different NAV bases
- Ledger row `Blended owner cash | $None`
- Duplicate thematic rows (HY OAS, UST 10Y/2Y ×2)
- Cross-check synthesis `-6.16%` vs dive `-5.5%` after refresh drift
- Classification `Implied 7yr IRR (Lawrence)` showing synthesis %
- Mental models row with IRR % (belongs at end only)
