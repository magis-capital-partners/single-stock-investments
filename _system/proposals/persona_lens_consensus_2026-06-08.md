# Proposal: Persona-lens layer + deterministic consensus

**Date:** 2026-06-08
**Status:** **Implemented 2026-06-08** — Phases 0–4 (persona lenses, insights layer, dashboard, Darwin features)
**Author:** Marvin (draft for human decision)
**Supersedes:** none. Extends `decision_stack.md`, `classification.md`, `analysis_arsenal.md`, `total_synthesis_irr.md`.

---

## Problem

Every holding produces **one verdict**: the Lawrence "total synthesis" IRR (`valuation.json` → `synthesis.total_synthesis_pct`). The geniuses (Stahl, Munger, Pabrai, Hohn, Lawrence, HK, Mihaljevic) are *inputs* that get blended into that single number, so the **disagreement between lenses is collapsed before anyone sees it**.

Two consequences, both raised by the human:

1. **The lens is keyed to the business type, not the investor.** `payoff_lens`/`archetype` pick a *toolkit*; you cannot see "what does Pabrai conclude vs. Greenblatt vs. Stahl on *this same stock*" side by side. A bank and a biotech trade on different things, but the system has no first-class "which investor owns this kind of business, and what would they track" object.
2. **One horizon and one metric set per stock.** The insight *higher valuation → tighter timeline → fewer key metrics* has no home: `horizon_years` is a single global field (7 for NVDA), not a function of (persona, valuation richness).

We want N investor lenses as **first-class, separable outputs**, each with its own universe, 1–3 key metrics, horizon, and bar — then a **debate-to-consensus** step that reconciles them, weighted by which analysis best fits the business type.

---

## Constraints

**Must keep**
- `valuation.json` as the **single source of facts**. Personas *read*; they never recompute or restate numbers. Disagreement is about weighting/interpretation only.
- Lawrence total-synthesis IRR as a computed input (now one voice in the consensus, still the math anchor).
- Milly adversarial gate, `[PROPOSED <GENIUS>]` memory loop, framework-governance four-layer discipline.

**Must not break**
- The existing single-fact-set invariant (one set of numbers Milly can audit).
- Reproducibility: re-running the pipeline on unchanged inputs yields **identical** verdicts.

**Non-goals**
- **No hand-authored persona prose.** Every verdict is a pure function of shared data (the human's explicit requirement: repeatable + scalable). Optional narrative is **templated** from the structured result, never free-written per stock.
- No intraday signals, no new fact sources beyond what the shared layer already holds.

---

## Success criteria (measurable)

- `persona_lens.py {TICKER}` is **deterministic**: same inputs → byte-identical `lenses.json`. A lint asserts this (re-run + diff).
- A persona verdict cites **only** keys that already exist in the shared data layer (no new per-stock data entry).
- **≤ 1 new framework file** (`persona_lens_consensus.md`). Persona specs + relevance matrix live as **data** (`personas.json`), not prose frameworks. Consensus lives in a **script**, surfaced via `valuation.json`/`lenses.json` keys.
- Dashboard renders **only relevance-gated** personas per ticker (a deep-value lens stays silent on a pre-revenue biotech).
- Consensus stance and dissent ledger reproducible from `lenses.json` alone.

---

## Governance answers (required by `framework_governance.md`)

| Question | Answer |
|---|---|
| Which decision-stack question? | Spans Q1–Q6, but the **new** object is a *per-persona reconciliation* of existing answers — not a new question. |
| Can it be a section of an existing triggered doc? | The *mechanics* extend `analysis_arsenal.md` (relevance matrix row) + `classification.md` trigger map. The *consensus concept* is new → warrants one framework file. |
| Can it be a `valuation.json` key + script instead? | **Mostly yes** — personas/consensus are derived by script into `lenses.json` + `valuation.json` keys. This is why there is no hand-authored layer. |
| Which lint/script enforces it? | `persona_lens.py` (build), `persona_consensus.py` (reconcile), determinism lint, Milly divergence check. |

**Conclusion:** one new framework file (`persona_lens_consensus.md`), one data file (`personas.json`), two scripts, schema additions. No framework-per-persona, no framework-per-ticker.

---

## Proposed change (four layers)

### Normative — `_system/frameworks/persona_lens_consensus.md` (new, one file)

Defines: the persona contract, the business-type → persona relevance matrix, the deterministic consensus algorithm, and the horizon/metric-compression rule. Persona *parameters* live in data (`personas.json`), not here.

### Operative

- `_system/lenses/personas.json` — machine-readable persona specs (below).
- `_system/scripts/persona_lens.py {TICKER}` — pure function: shared data → per-persona verdict.
- `_system/scripts/persona_consensus.py {TICKER}` — deterministic reconciliation → consensus stance + dissent ledger.
- `{TICKER}/research/lenses.json` — output (below). Referenced (not duplicated) into `dashboard_data.json` by `build_dashboard_data.py`.
- New `valuation.json` block `lens_consensus` (summary: stance, agreement score, top dissent).

### Narrative

- Dashboard ticker detail: sub-tab strip `Consensus | Hohn | Pabrai | Stahl | Greenblatt | Buffett/Weschler | …`, only relevance-gated personas active. Reuses the existing `.view-tab` component (`dashboard/index.html`).
- Deep dive gains a compact, **generated** "Lens consensus" table (stance, agreement %, dissents) — no prose written by hand.

### Adversarial

- Determinism lint (re-run `persona_lens.py`, diff must be empty).
- Milly **divergence check**: flag when consensus stance disagrees with Lawrence stance gate, or when a high-relevance persona dissents from a `core` holding.

---

## Persona roster

Existing personas are promotions of current question-owners; **Greenblatt** and **Buffett/Weschler** are new and **lack source folders** (see Dependencies).

| Persona | Universe filter (relevance) | 1–3 key metrics (derived) | Base horizon | Bar | Library source |
|---|---|---|---|---|---|
| **Hohn** | High-barrier oligopoly/franchise; activist angle | FCF yield; growth; named primary risk present | 3–5 yr | ~15% IRR | `tci/` ✓ |
| **Pabrai** | Understandable, low debt, owner-operator | downside/upside ratio; net debt/EBITDA; dhando flag | 2–3 yr | bounded bear, low downside | `pabrai/` ✓ |
| **Stahl** | Hard assets, croupiers, inflation beneficiaries | archetype fit; reinvestment moat; hard-asset cover | 10+ yr | indestructibility + scarcity | `stahl/`, `horizon-kinetics/` ✓ |
| **Munger** | Quality + circle of competence (already moat lens) | moat trend; ROIC; inversion red-flags | 10+ yr | durable advantage | `munger/` ✓ |
| **Greenblatt** | Special situations + high return on capital | EBIT/EV (earnings yield); ROIC | 2–3 yr | top-decile yield × ROIC | **MISSING** |
| **Buffett/Weschler** | Durable moat, owner-earnings, quality at fair price | owner-earnings yield; ROE/retention; reinvestment runway | 10+ yr | quality at fair price | **MISSING** (lean on `munger/` + add Berkshire letters) |
| **Mihaljevic (MOI)** | Idea-funnel / special-situation discovery | inefficiency source; catalyst date | varies | uses-not-misuses screen | `mihaljevic/` ✓ |
| **Horizon Kinetics** | Dated contractual payoffs; royalty/trust | equity yield-curve return; predictive attribute | dated | time-arbitrage | `horizon-kinetics/` ✓ |

`Lawrence` is not a persona tab — it is the IRR math that all personas consume and one explicit voice in consensus.

---

## Relevance calibration — explainable + hard-to-vary (the linchpin)

If relevance is hand-picked, the whole consensus is arbitrary (easy to vary = bad explanation, Deutsch). **Relevance is therefore a deterministic function of measurable business attributes, not a number set per archetype.**

### (a) Each persona's *universe* = cited, falsifiable criteria

Relevance ∈ {high=1.0, medium=0.5, low/silent=0.0} is **derived**, not assigned:

| Persona | Universe criteria (measurable) | Source anchor | Falsifier (flips relevance) |
|---|---|---|---|
| Greenblatt | ROIC high **and** EBIT/EV yield high | *Little Book* | ROIC < median → not a "good" business |
| Pabrai | Low net debt **and** bounded downside (dhando) | `pabrai/` | net-debt/EBITDA > 3 → outside universe |
| Stahl | Hard-asset / croupier / inflation pass-through | `stahl/`, `horizon-kinetics/` | no asset intensity & no pricing power → silent |
| Hohn | High barriers + oligopoly + positive FCF | `tci/` | commoditized / structurally loss-making → silent |
| Buffett/Weschler | Durable moat + ROE + reinvestment runway | Berkshire letters (to add) | eroding moat / no reinvestment runway → drops |
| Munger | Quality + circle of competence | `munger/` | outside competence → silent |
| MOI | Inefficiency source + special situation | `mihaljevic/` | efficiently priced, no catalyst → silent |
| HK | Dated contractual payoff / royalty | `horizon-kinetics/` | no dated payoff → silent |

### (b) Three-way hard-to-vary anchor (per criterion)

1. **Sourced** to the investor's own stated principle — can't change without contradicting the citation.
2. **Falsifiable** — a named attribute value flips it (column 4).
3. **Reproducible** — computed from the *same shared data*; re-run identical.

Mapping to the discrete scale uses **published thresholds**: `high` if all criteria met, `medium` if one, else `silent`. The old archetype grid survives only as a **derived coarse prior** for display, not the source of truth.

### (c) Empirical validation loop — letters DB as ground truth

The superinvestors who *actually own* a business reveal which lens fits it. Calibration check (script):

> Per persona, compute the **match rate** between our `high`-relevance names and the holdings of real-world investors who map to that persona (`superinvestor-letters/insights.json` → `maps_to_persona`). Persistent mismatch = miscalibrated criteria → revise with human, log in `corrections.md`.

This makes relevance **falsifiable against reality**, not self-asserted. Milly adds a per-ticker adversarial pass ("is any silent persona obviously the actual owner here?").

### (d) Sparsity rule

Per ticker, few personas may be `high`; a lens is plausibly an owner or it is silent. **No "everything is medium" cop-out.** Discrete + sparse + attribute-derived = hand-traceable.

---

## Deterministic consensus ("debate" made reproducible)

The "debate" is a transparent, repeatable reconciliation — not LLM free-text — so it scales and re-runs identically. There are **two separate outputs**: a **valuation blend** (one number + band) and a **stance reconciliation** (downstream). Keeping them separate is part of explainability.

### Common unit (so different methods are comparable)

Personas value the business by different methods (Greenblatt: EBIT/EV; Hohn: EPS-path × exit; Buffett/Weschler: owner-earnings yield; Stahl: long-horizon scarcity). We do **not** average fair values. Each persona reports in one unit it can always produce: **expected annualized return at today's price, over its own horizon.** Annualizing makes a 3-yr and a 10-yr view commensurable, and it is already the house unit (Lawrence IRR). No one must agree on intrinsic value — only on "what return from here, my way."

> Caveat (accepted): annualized returns over different horizons embed different terminal/reinvestment assumptions. We accept this for **precision + explainability**; the band (below) carries the honest disagreement.

### Valuation blend — fixed-weight mean (the number)

**Precision over accuracy:** a plain relevance-weighted mean with **declared, fixed** weights — no conviction term, no fitting, no optimization. Hand-traceable; small input change → small traceable output change.

```
blended_return = Σ_p ( relevance_p · return_p ) / Σ_p relevance_p
   over personas where relevance_p > 0     # silent personas (relevance 0) excluded
```

Weights are the matrix values (1.0 / 0.5 / 0.0), published in `personas.json`, **not learned**. Report **three** pieces, never a lone point:

1. **Central** = the weighted mean (additive: "each persona contributed X").
2. **Band** = `[min, max]` of contributing personas' returns (honest spread).
3. **Weighted median** = robustness cross-check. Mean–median divergence is a **flag** to inspect the outlier dissent, not something to smooth away.

**Conviction is dropped from the headline number** (resolves open question #2). It stays only for ordering the dissent ledger — making the blend reactive would trade away precision/stability.

Worked example (`compounder`; Buffett 1.0, Hohn 1.0, Munger 0.5, Pabrai 0.5, Greenblatt/Stahl 0.0):

```
Hohn 9%(1.0) + Buffett 11%(1.0) + Munger 10%(0.5); Pabrai silent (rich price)
blended = (9 + 11 + 5) / (1.0 + 1.0 + 0.5) = 25 / 2.5 = 10.0%
band = [9%, 11%]   median ≈ 10% (agrees → no flag)   dissent = Pabrai (out of universe)
```

Edge cases: **all silent** → no number, output "no lens owns this"; **one contributor** → blend = that persona, flagged low-coverage; **`pass`** (relevant but below bar) still contributes its computed return (drags the mean down); **`silent`** (relevance 0) is excluded entirely.

### Stance reconciliation (downstream, separate)

```
for each persona p with relevance > 0:
    metrics_p, horizon_p, verdict_p, conviction_p   # as derived above
stance = band( blended_return vs portfolio_bar ), gated by dhando/moat
agreement_pct = share of contributing personas on the majority verdict side
dissent_ledger = personas opposing the stance, with key metric + falsifier (ordered by conviction)
```

- **Dissents are preserved, never averaged away** — the ledger is the visible debate.
- Lawrence IRR enters as one persona-return in the blend (its % vs. the portfolio bar).
- Both outputs are fully reconstructible from `lenses.json`.

### Horizon / metric-compression rule

```
valuation_richness = clamp( (price / lens_fair_value) or (bar - implied_irr), 0..1 )
horizon_p = round( horizon_base_p · (1 - 0.5·valuation_richness) )   # richer → shorter
metric_count_p = 3 if richness < 0.33 else 2 if richness < 0.66 else 1  # richer → fewer, faster metrics
```

When you pay up, the lens tracks fewer, faster-moving metrics (near-term growth/guidance) over a compressed horizon.

---

## Schemas

### `_system/lenses/personas.json` (persona spec — edit here, not in prose)

```json
{
  "pabrai": {
    "label": "Mohnish Pabrai",
    "source": "_system/reference/investment-wisdom/pabrai/",
    "relevance_by_archetype": { "turnaround": 1.0, "optionality": 0.5, "compounder": 0.5, "croupier": 0.0 },
    "horizon_base_yrs": 3,
    "key_metrics": [
      { "name": "downside_upside_ratio", "from": "scenarios", "fn": "bear_to_bull_span" },
      { "name": "net_debt_ebitda", "from": "inputs", "fn": "leverage" },
      { "name": "dhando", "from": "classification_inputs.dhando" }
    ],
    "bar": { "rule": "dhando in [full,partial] AND downside_upside_ratio <= 0.4" },
    "falsifier": "net_debt_ebitda rises above 3 OR dhando -> none"
  }
}
```

### `{TICKER}/research/lenses.json` (generated output)

```json
{
  "ticker": "NVDA",
  "as_of": "2026-06-07",
  "shared_inputs_ref": "valuation.json@2026-06-07",
  "lenses": [
    { "persona": "hohn", "relevance": 1.0, "verdict": "watch", "conviction": 0.6,
      "horizon_yrs": 3, "meets_bar": false,
      "key_metrics": [ {"name":"fcf_yield","value":2.8}, {"name":"dc_growth_y1_5","value":18} ],
      "falsifier": "Data Center growth sustained >25% for 4 quarters" },
    { "persona": "pabrai", "relevance": 0.0, "verdict": "silent",
      "why_silent": "Rich valuation; downside unbounded — outside dhando universe." }
  ],
  "valuation_blend": {
    "unit": "expected_annual_return_at_price",
    "blended_return_pct": 10.0,
    "band_pct": [9.0, 11.0],
    "weighted_median_pct": 10.0,
    "median_mean_flag": false,
    "contributors": [
      {"persona":"hohn","relevance":1.0,"return_pct":9.0},
      {"persona":"buffett_weschler","relevance":1.0,"return_pct":11.0},
      {"persona":"munger","relevance":0.5,"return_pct":10.0}
    ],
    "excluded_silent": ["pabrai","greenblatt","stahl"]
  },
  "consensus": {
    "stance": "watch", "agreement_pct": 67,
    "dissents": [ {"persona":"pabrai","verdict":"pass","key_metric":"downside_unbounded","conviction":0.7} ]
  }
}
```

---

## Insights layer (multi-source) + superinvestor letters database

A normalized **insight record** that every data source emits, so one UI surface aggregates them and the consensus engine can cite them as **context** (never auto-driving base IRR).

### Normalized insight record

```json
{ "source": "superinvestor_letter|macro|insider|third_party|theme|news",
  "as_of": "2026-07-15", "scope": "portfolio|ticker|theme", "ref": "GOOGL",
  "claim": "Ackman added GOOGL on AI re-rating", "direction": "bullish",
  "evidence_ref": "superinvestor-letters/2026Q2/pershing.txt",
  "in_base_irr": false, "confidence": "med" }
```

Existing sources are **adapters** into this shape: `context_overlay` (macro), `insider_signal` (Form 4), `third-party-analyses/`, `market-data/themes/`. The letters DB is one more adapter. Discipline: `in_base_irr: false` by default; promotion to base case requires `[HUMAN REVIEW]` (same as today's `context_overlay`/`insider_signal`).

### Superinvestor letters — efficient storage

Copyrighted + heavy → **commit structured extraction, gitignore raw PDFs** (MOI-epub discipline). Files arrive via `INCOMING/` (human drop or Vicki browser agent — Dropbox shared folders are not script-fetchable).

```
_system/reference/superinvestor-letters/
  INCOMING/                     # raw drop (gitignored)
  2026Q1/ {fund}.pdf (gitignored)  {fund}.txt (extracted)
  2026Q2/ ...
  letters_index.json            # fund, manager, quarter, date, source, file
  insights.json                 # per-letter structured record (UI reads this; small)
  manifest.csv
```

Per-letter record (re-runnable templated extraction via `build_superinvestor_insights.py`):

```json
{ "fund": "Pershing Square", "manager": "Ackman", "quarter": "2026Q2", "letter_date": "2026-07-15",
  "themes": [ {"theme": "AI capex digestion", "stance": "cautious", "quote": "...", "tickers": ["GOOGL"]} ],
  "positions": [ {"ticker": "GOOGL", "action": "add", "thesis": "...", "conviction": "high"} ],
  "macro_views": ["rates plateau"], "maps_to_persona": ["buffett_weschler","hohn"] }
```

`maps_to_persona` is what feeds the relevance validation loop (above).

### Insights UI

- New top-level tab `Insights` (beside `Holdings | Darwin`): **theme ranking** across funds this quarter (count of funds + net sentiment) and **per-fund cards**.
- Per-ticker detail: **"Who owns / discusses this"** strip — ticker-scoped insight records, linking the letters DB to the persona tabs.
- Builder: `build_insights.py` merges all adapters → `dashboard/data/insights.json`; `build_dashboard_data.py` references it.

## Risks of simplification

| Risk | Guardrail |
|---|---|
| **Personas collapse into six DCFs** (noise the human wants killed) | Each persona's `key_metrics` + `bar` must be **distinct** and named; determinism lint + a "distinctness" check (no two personas with identical metric set per archetype). |
| **Consensus theater** (debate that just re-prints the average) | Dissent ledger is mandatory and surfaced; Milly flags when no dissent appears on a contested name. |
| **Fake precision on new personas** (Greenblatt/Buffett with no library) | Greenblatt = public magic-formula (EBIT/EV, ROIC) — well-defined from data. Buffett/Weschler gated until Berkshire-letter source is added (Dependencies). |
| **Two sources of truth** | `lenses.json` references `valuation.json@date`; never restates numbers; Milly audits one fact set. |
| **Consensus overrides judgment** | Consensus is advisory; human still sets stance. Divergence vs. Lawrence gate is a `[HUMAN REVIEW]` flag, not an auto-trade. |
| **Relevance is arbitrary** (whole consensus is then arbitrary) | Relevance derived from cited, falsifiable attribute criteria; validated against letters-DB holdings; Milly per-ticker check; sparsity rule. |
| **Letters/insights leak into base IRR** | Every insight `in_base_irr: false`; promotion needs `[HUMAN REVIEW]` — same discipline as `context_overlay`/`insider_signal`. |
| **Letter extraction drifts run-to-run** | Templated schema + versioned extractor; store output, diff on re-run; copyright PDFs gitignored. |

## Redundancy we keep on purpose

Milly adversarial pass; Lawrence IRR math; `[PROPOSED <GENIUS>]` human-promotion memory loop; cross-check pipeline; the single-fact-set invariant.

---

## Dependencies (Phase 0 blockers)

- **Greenblatt source:** add `investment-wisdom/greenblatt/` (e.g. *The Little Book That Beats the Market*, *You Can Be a Stock Market Genius*) — or proceed with public-formula derivation only, clearly labeled.
- **Buffett/Weschler source:** add `investment-wisdom/buffett/` (Berkshire shareholder letters) before enabling that tab; until then it inherits `munger/` quality lens.
- Confirm `EBIT/EV`, `ROIC`, `net-debt/EBITDA`, asset-intensity are derivable from current `valuation.json`/filings for the universe (relevance criteria inputs), or add as shared-data keys.
- **Superinvestor letters:** human drops 2026 Q1/Q2 PDFs (Dropbox) into `superinvestor-letters/INCOMING/`, or dispatch Vicki to harvest. Confirm copyright stance (gitignore raw, commit extracts).

---

## Implementation scope

- [x] Docs only (this proposal)
- [x] Framework: `persona_lens_consensus.md` (1 file)
- [x] Data: `_system/lenses/personas.json` (universe criteria + thresholds + source + falsifier)
- [x] Scripts: `persona_lens.py`, `persona_consensus.py`, `relevance_calibration_check.py`, determinism lint; wire into `marvin_cloud_refresh.py` + `build_dashboard_data.py`
- [x] Insights: `build_superinvestor_insights.py`, `build_insights.py` → `dashboard/data/insights.json`; `.gitignore` raw letter PDFs
- [x] Cursor rules: add trigger row to `classification.md` map; note in `investment-frameworks.mdc`
- [x] CI/Makefile: determinism via `lint_persona_lens.py --portfolio`
- [x] Dashboard: persona sub-tabs + consensus panel + `Insights` tab + per-ticker "who owns/discusses" strip

## Arsenal row (new trigger)

| Tool | Trigger | Doc |
|------|---------|-----|
| Persona-lens consensus | every ticker with `valuation.json` (relevance-gated personas only) | `persona_lens_consensus.md`; build via `persona_lens.py` + `persona_consensus.py` |

---

## Phased rollout

- **Phase 0** — Approve this proposal; source Greenblatt + Buffett/Weschler; ingest 2026 Q1/Q2 letters; freeze `personas.json` universe criteria + thresholds.
- **Phase 1** — `persona_lens.py` for the personas covered by library sources (Hohn/Pabrai/Stahl/Munger/MOI/HK); attribute-derived relevance; determinism lint; `lenses.json` for all tickers.
- **Phase 1b** — Letters DB: `build_superinvestor_insights.py` → `insights.json`; `relevance_calibration_check.py` (match rate vs holdings).
- **Phase 2** — `persona_consensus.py` (valuation blend + stance) + dissent ledger + `valuation.json` `lens_consensus` block; Milly divergence + relevance checks.
- **Phase 3** — Dashboard persona sub-tabs + consensus panel + horizon/metric compression + `Insights` tab + per-ticker "who owns/discusses" strip.
- **Phase 4** — Persona verdicts emit `[PROPOSED <PERSONA>]` into daily log; optional Darwin feature = "persona agreement %" + "superinvestor overlap".

---

## Open questions for human

1. Greenblatt/Buffett-Weschler: source the PDFs first (cleaner), or ship public-formula derivations labeled `[no library]` and backfill?
2. ~~Consensus weighting relevance × conviction vs relevance-only?~~ **Resolved:** valuation blend uses **relevance-only fixed weights** (precision over accuracy); conviction only orders dissents.
3. Which tickers get persona tabs first — all 62, or `core`/`accumulate` holdings only for Phase 1?
4. Keep Lawrence total-synthesis as the displayed "house number" alongside consensus, or replace the headline with consensus stance?
5. Common unit confirmed as **annualized return at today's price** — accept the cross-horizon caveat, or normalize all personas to a single fixed horizon (e.g. 7 yr) for strict comparability?
6. Letter extraction: fully automated LLM pass (scales, some noise) vs. human-in-the-loop confirm per fund (cleaner, slower)? And commit the `.txt` extracts or keep them local too (copyright)?
7. Relevance thresholds (e.g. "ROIC high" = top tercile vs top quartile): set absolute, or percentile within our universe? Percentile is more stable as the book changes.
