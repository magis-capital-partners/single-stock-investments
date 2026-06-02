# Analysis Arsenal

**Purpose:** Full toolkit — every lens Marvin *can* apply. **Not** every tool on every dive.

**Core (always):** `_system/frameworks/decision_stack.md` — six orthogonal questions.  
**MOI comprehensive rules:** `_system/frameworks/moi_company_evaluation.md` — full Ch 1–10 evaluation checklist.  
**This file:** triggered tools keyed by `payoff_lens` or situation.

---

## Six orthogonal questions (required every deep dive)

Answer once. Do not duplicate in separate MOI / Lawrence subsections.

| # | Question | Why it exists | Primary outputs |
|---|----------|---------------|-----------------|
| **1. What is it?** | You cannot value what you do not understand | Circle of competence | Archetype, cycle, Hohn operating snapshot |
| **2. Will it last?** | Terminal value and multiple depend on durability | Moat gate | `moat` |
| **3. Is the bear bounded?** | Position sizing and dhando need a floor | Asymmetric payoff | `dhando`, bear case in valuation |
| **4. What return at this price?** | Capital has an opportunity cost | Lawrence bar | `implied_irr`, `irr_method` |
| **5. Why mispriced?** | Without an edge, you are the greater fool | HK + MOI | Predictive attribute; inefficiency; catalyst if asset/event |
| **6. What do we do?** | Analysis must end in action | Stance gate | `stance` |

**Where in the report:** Q1–2 in Business & moat · Q3–4 in Payoff & return + Valuation · Q5 in Why the market might be wrong · Q6 in Payoff + Classification.

---

## Payoff lens (one tag — picks the toolkit)

Replaces verbose `moi_bucket` lists. Set `classification_inputs.payoff_lens` in `valuation.json`.

| Lens | When | Primary tools to open |
|------|------|------------------------|
| `operating` | Modelable FCF; compounder, croupier, platform | Hohn pillars, Lawrence `full`, segment overlay if multi-segment |
| `asset` | SOTP, NAV, deep value, holdco discount | `optionality_valuation.md`, `option_treatment.md`, discount magnitude |
| `event` | Spinoff, index, dividend cut, dated catalyst | `special_situation_lens.md`, Stahl spinoffs, annualized return |
| `levered` | High leverage, recovery bet | `equity_stub_valuation.md`, scenario IRR only |
| `pending` | Not yet classified | Set on onboard; resolve in dive |

**Optional discovery tags** (prose or `decision_log` only — not footer required): clone, jockey thesis, small-cap, international. Use when idea source matters for process, not for stance math.

Legacy `moi_bucket` values map 1:1 → `payoff_lens` (see `moi_lens.md`).

---

## Triggered tools (open when relevant)

### Idea generation & discovery (MOI)

| Tool | Trigger | Doc / source |
|------|---------|--------------|
| Idea funnel | Watchlist / onboard | `idea_funnel.md` |
| Deep value / net-net | `asset` + liquidation thesis | MOI Ch 2; `mihaljevic/` |
| Good + cheap screen | Quality at fear price | MOI Ch 4; compounder Tier 2 |
| Clone + verify | Idea from 13F / letter | `mental_models.md` — cloning conviction |
| Small-cap investability | Micro / illiquid | `idea_funnel.md` § small-cap |
| International pre-check | Non-US listing | `idea_funnel.md` § international |

### Business & durability

| Tool | Trigger | Doc |
|------|---------|-----|
| Hohn operating mechanics | Always | `hohn_business_analysis.md` |
| Tier 2 archetype models | `archetype` set | `archetype_models.json` |
| Munger inversion / psychology | Risks, cross-check | `mental_models.md`, `munger/` |
| Management invert | Gate 3 fail or jockey thesis | `hohn_business_analysis.md` § Management invert |
| AI infrastructure overlay | Hyperscaler / `ai_overlay` | `ai_infrastructure_valuation.md` |
| Growth explanation stress test | Optional JSON only — not in markdown | `growth_explanation_stress_test.md` |

### Valuation & payoff

| Tool | Trigger | Doc |
|------|---------|-----|
| Lawrence 10yr IRR | `operating`, modelable FCF | `lawrence_irr.md`, `marvin_valuation.py` |
| HK equity yield curve | Dated contractual payoff | `mental_models.md` Tier 3 |
| Segment cash-flow sum | Multi-segment compounder | `segment_cashflow_valuation.md` |
| Optionality / NAV overlay | `asset` lens | `optionality_valuation.md` |
| Option treatment ladder | Every dive — scan table | `option_treatment.md` |
| Equity stub scenarios | `levered` lens | `equity_stub_valuation.md` |
| External view blend | Approved third party cited | `external_view_blend.md` |

### Events & structure

| Tool | Trigger | Doc |
|------|---------|-----|
| Special situation inefficiency list | `event` lens | `special_situation_lens.md` |
| Spinoff / simplification | Conglomerate, BN, SPGI | Stahl spinoffs PDF |
| Milly adversarial pass | After every deep dive | `MILLY.md` |

---

## Lens failure mode (Q5 guardrail — one line)

When `payoff_lens` is `asset`, `event`, or `levered`, add under **Risks & inversion**:

> **Lens failure mode:** {how this idea type usually breaks — e.g. value trap without catalyst, stale 13F, point estimate on levered equity}

Skip for plain `operating` unless a non-standard tool was used.

This replaces the separate "Uses & misuses (MOI)" table — same intent, one sentence minimum.

---

## Pre-dive gate (watchlist / onboard only)

Not required for incumbent holding refreshes.

1. `payoff_lens` tagged  
2. Six questions sketched (even brief)  
3. No disqualifying failure mode (e.g. asset lens with no catalyst and thin discount)  
4. Return sketch beats portfolio median **or** strategic sleeve need  

Pass → `decision_log.md` one line. Proceed → standard Marvin pipeline.

---

## Wisdom sources

| Genius | Folder | Use for |
|--------|--------|---------|
| Munger | `munger/` | Q2, inversion, psychology |
| Pabrai | `pabrai/` | Q3 dhando, sizing |
| Stahl | `stahl/` | Q1 archetype, spinoffs, diversification |
| Horizon Kinetics | `horizon-kinetics/` | Q5 predictive attributes, yield curve |
| Hohn / TCI | `tci/` | Q1 mechanics, Q4 bridge |
| Mihaljevic / MOI | `mihaljevic/` | Discovery, failure modes, event toolkit |

**Catalog:** `mental_models.md` for full model list with triggers.
