# IRR assumption ledger (repeatable spec)

**Purpose:** Every deep-dive return must be reproducible. No unexplained payoffs, growth rates, or multiples.

**Placement:** `## Valuation & IRR (assumption ledger)` — **last major section**, after `## Risks & inversion`, **before** `## Classification`.  
**Not** inside Business & moat.

**Companion files:** `lawrence_irr.md` § F · `deep_dive_structure.md` · `archetype_valuation_prose.md` · `{TICKER}/research/valuation.json`

**Readable labels:** Assumption ledger rows use **plain English** (no `P₀`, `g1`, `FCF₀`). Archetype-specific examples: `archetype_valuation_prose.md`.

---

## Required structure (all tickers)

```markdown
## Valuation & IRR (assumption ledger)

**Price today:** $X (source, date)  
**Method:** {irr_method} · **Base IRR:** Y% · `valuation.json`

### Assumption ledger (base case)

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| 1 | Price today (P₀) | … | Filing / Stooq / exchange |
| 2 | … | … | … |
| N | Horizon (years) | … | Why N years |

{Method-specific buildup — every row must have a source or **[Assumption]** / **[HUMAN REVIEW]**}

**Growth rows (3–4):** Source column cites filing path, segment build, or **[Assumption]** with one-line mechanism in Business & moat — not a separate philosophy subsection.

### IRR arithmetic (show your work)

{Numbered steps; running sum for SOTP; formula for scenario/full}

**Upside / downside from price:** …

**Returns statement:** … (must match base % in executive summary)
```

**Do not include in deep dives:** valuation bridge overlay tables (theory-implied, falsifier-adjusted, Lawrence legacy, segment sum/implied rows), Popper/Deutsch stress-test subsections, or Deutsch check tables. Bear/bull sensitivity lives in `valuation.json` → `scenarios` only.

---

## Assumption ledger rules

1. **One row per input** that moves the IRR (price, shares, FCF₀, each growth rate, exit multiple, payoff, years, each SOTP line).
2. **Source column** must be one of:
   - **Filing:** `{TICKER}/path` + metric
   - **Market:** exchange + date
   - **Tool:** `marvin_valuation.py --ticker X`
   - **Approved Substack:** `ssi` / `lci` + post title
   - **Third party (approved):** see `third_party_sources.md`
   - **[Assumption]:** plain-English why you chose the number
   - **[HUMAN REVIEW]:** needs human sign-off
3. **No silent math.** If the report says “3% per year,” show `book × (1.03^5 − 1) = $Z/sh`.
4. **Multiples are results, not inputs.** e.g. `payoff ÷ book = 2.1×` only **after** the sum-of-parts.
5. **Tie-out slack** — if sub-lines do not sum to the model payoff, show a **Tie-out** row (do not hide the gap).
6. **Bear / bull** — document in `valuation.json` scenarios; one sentence in Payoff & return on what changes vs base (payoff, growth, or owner cash). No duplicate bridge table in the markdown.
7. **Growth** — rows 3–4 must cite filing, segment build, or **[Assumption]** with mechanism stated in Business & moat.

---

## Method templates

### `yield_curve` / holdco SOTP (`valuation_mode: optionality`)

- **Assumption ledger** + **incremental uplift table** (book + line₁ + … = payoff).
- Store lines in `valuation.json` → `scenarios.base.sotp_build` when possible.
- FRMO reference: `FRMO/research/deep_dive_2026-05-27.md` Step 3g.

### `scenario` / `full` (owner cash / FCF)

| # | Typical assumption |
|---|-------------------|
| 1 | P₀ |
| 2 | Owner cash or FCF₀ per share (normalization note) |
| 3 | Growth years 1–5 |
| 4 | Growth years 6–10 |
| 5 | Exit multiple year 10 |
| 6 | Years (10 for full Lawrence) |
| 7 | Terminal value check (show one explicit multiplication) |

Run `python _system/scripts/marvin_valuation.py --ticker X --write` and cite outputs.

### `segment_cashflow` overlay (`valuation_overlay` in `valuation.json`)

Use **with** `method: full` (or `scenario`). Consolidated ledger rows stay; **add**:

| # | Typical assumption |
|---|-------------------|
| … | Per-segment owner cash Y0, growth, exit multiple |
| … | Each option (base terminal $0; bull value) |
| … | Corporate capex drag / allocation |
| … | Sum PV/sh (in segment build subsection, not ledger duplicate rows) |

Subsections: `### Segment cash-flow build` + `#### Segment IRR arithmetic`. Spec: `segment_cashflow_valuation.md`.

### `pending`

- State why IRR is not computed.
- Payoff section: “IRR pending — see [HUMAN REVIEW].”

---

## Report order (overview first, valuation last)

| # | Section |
|---|---------|
| 1–4 | Header, What, Why, Executive summary (**one** base %, no math) |
| 5 | Primary sources reviewed |
| 6 | Business & moat (**no** IRR block) |
| 7–8 | Approved Substack / Blended estimate (if applicable) |
| 9 | Payoff & return (gates, dhando, stance — **points to Valuation & IRR**) |
| 10 | Risks & inversion |
| 11 | **Valuation & IRR (assumption ledger)** |
| 12 | Classification, [HUMAN REVIEW], [PROPOSED MEMORY] |

---

## Lint / handoff

```bash
python _system/scripts/build_filing_evidence.py {TICKER}
python _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python _system/scripts/refresh_deep_dive_v2.py {TICKER}
python _system/scripts/lint_deep_dive.py {TICKER} --strict
```
