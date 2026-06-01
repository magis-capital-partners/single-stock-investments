# Manual of Ideas — framework suggestions for Marvin

**Date:** 2026-06-01  
**Status:** **Implemented** 2026-06-01 — see `_system/frameworks/moi_lens.md` and wisdom `mihaljevic/`
**Source:** John Mihaljevic, *The Manual of Ideas: The Proven Framework for Finding the Best Value Investments* (Wiley, 1st ed. 2013; 2nd ed. 2023/2025)  
**Method:** Full chapter map + key takeaways synthesized from CFA Institute review, Rational Walk, O'Reilly TOC, and detailed chapter summaries (Jeremy Silva, 2020). **The copyrighted PDF was not downloaded** — purchase via [Wiley](https://www.wiley.com/en-us/The+Manual+of+Ideas%3A+The+Proven+Framework+for+Finding+the+Best+Value+Investments%2C+2nd+Edition-p-9781119270324) or add to `_system/reference/investment-wisdom/mihaljevic/` when licensed.

**Purpose:** Propose rule changes that complement existing Munger / Pabrai / Stahl / Lawrence / Hohn stack without duplicating it.

---

## Executive summary

MOI is an **idea-generation cookbook**, not a single valuation method. Its distinctive contribution is a repeating structure per strategy:

1. Why it works  
2. **Uses and misuses** (where investors blow themselves up)  
3. Screening  
4. **Beyond screening** (qualitative work screens miss)  
5. Key questions  

Marvin already excels at **deep-dive quality** (Hohn mechanics, Lawrence IRR ledger, Milly adversarial pass, optionality overlays). MOI would strengthen Marvin most in four gaps:

| Gap | MOI fix |
|-----|---------|
| **Discovery / onboarding** | Tag each idea with MOI bucket; maintain idea funnel before deep dive |
| **Misuse guardrails** | Mandatory "uses & misuses" block per archetype |
| **Catalyst & inefficiency** | Formalize *why mispriced* beyond HK predictive tags |
| **Time & process** | Special-situation annualized return; investment diary; pass log |

---

## What Marvin already covers well

| MOI chapter | Marvin equivalent |
|-------------|-------------------|
| Ch 3 SOTP / hidden assets | `optionality_valuation.md`, `option_treatment.md`, Hohn SOTP, `segment_cashflow_valuation.md` |
| Ch 4 Good + cheap (Magic Formula) | Lawrence 5 questions, compounder archetype, Greenblatt-adjacent quality checks in `quality_checklist.md` |
| Ch 5 Jockey stocks | Munger incentive bias, Hohn capital return, gate 3 (aligned management) |
| Ch 6 Follow leaders | `Cloning + verify` in `mental_models.md`; `third_party_sources.md` / approved Substacks |
| Ch 8 Spinoffs / events | Stahl spinoff PDF; `portfolio_news` spinoff tags; BN/SPGI workflow |
| Ch 1 Capital allocator | Lawrence stance, Pabrai fat pitch, decision stack layer 5 |

---

## Proposed rules (prioritized)

### P0 — High impact, low friction

#### 1. Add `moi_bucket` to Classification

**File:** `_system/frameworks/classification.md`, `valuation.json`, `sync_classification.py`

Tag the **primary idea source** (not archetype — orthogonal):

| Value | When |
|-------|------|
| `deep_value` | Net-net, liquidation floor, cigar butt |
| `sotp_hidden` | Sum-of-parts, dormant asset, holdco discount |
| `good_cheap` | High ROC + cheap EV/EBIT; quality at fear price |
| `jockey` | Thesis is management / capital allocation |
| `superinvestor_signal` | Idea originated from 13F / letter / clone |
| `small_cap_inflection` | Micro/small; legacy + growth split |
| `special_situation` | Event-driven; near-term catalyst |
| `equity_stub` | Leveraged equity; range-of-outcomes |
| `international_value` | Non-US listing; country/regional lens |
| `compounder_core` | Default for incumbent Lawrence compounders |

**Rule:** Every deep dive and onboard sets `moi_bucket`. Stance logic unchanged; enables portfolio audit ("too much deep_value?").

#### 2. MOI three questions in "Why the market might be wrong"

**File:** `deep_dive_structure.md`, `report_prose.md`, `lint_deep_dive.py`

Require explicit answers (already partially in gate 5):

- **Source of inefficiency** — mechanical (index deletion, K-1, spinoff orphan), informational (8-K buried), analytical (complexity), or behavioral (fear/greed)?  
- **Margin of safety** — what protects capital if thesis is slow or half wrong?  
- **Path to value creation** — named catalyst + timeline, or self-help (buyback, divest)?

For `special_situation` and `sotp_hidden` buckets, **path to value creation is mandatory** or flag `[HUMAN REVIEW]`.

#### 3. "Uses & misuses" subsection per dive

**File:** `deep_dive_structure.md` → new subsection under **Risks & inversion** (or Payoff & return)

MOI's core pedagogical move. One short table:

| Uses | Misuses |
|------|---------|
| When this strategy fits *this* ticker | Known failure modes for this bucket |

**Examples by bucket:**

- **deep_value:** liquidation in distress understates impairments; time erodes asset-rich low-ROC businesses; concentration risk  
- **good_cheap:** transitory ROC from fad; no reinvestment runway; "improving" screen by dropping best candidates psychologically  
- **sotp_hidden:** over-slicing segments; crowding by smart money; value trap without catalyst  
- **superinvestor_signal:** macro basket ≠ stock endorsement; stale 13F; hero worship  
- **equity_stub:** point estimate vs range; company-specific vs industry-wide distress  

**Lint:** require ≥1 misuse row when `moi_bucket` ≠ `compounder_core`.

#### 4. Discount magnitude check (SOTP / optionality)

**File:** `optionality_valuation.md`, `archetype_valuation_prose.md`

MOI: "buy-one-get-one-free vs buy-ten-get-one-free."  

**Rule:** When NAV or SOTP discount >50%, report **discount as % of price** and **premium to floor** separately. Require explicit statement: "Discount is / is not large enough to compensate for [no catalyst / illiquidity / governance]."

TPL example: ~87% premium to overlay NAV — MOI would classify as *not* a compelling SOTP entry despite good business.

---

### P1 — Discovery & process

#### 5. Idea funnel before deep dive

**File:** new `_system/frameworks/idea_funnel.md`; wire into `investment_process.md` § Discover

MOI ranks ~20 pre-qualified ideas down to **3–5** compelling names. Marvin today jumps to full deep dive on holdings.

**Proposed workflow for watchlist / new names:**

```
Screen (quant or news) → MOI bucket tag → 3 MOI questions (brief) → 
Uses/misuses skim → Deep dive only if passes human or automated gate
```

**Gate sketch:** proceed to deep dive if (a) MOI questions answered, (b) no disqualifying misuse, (c) implied return sketch > portfolio median OR strategic sleeve need.

#### 6. Special-situation inefficiency registry

**File:** extend `mental_models.md` Tier 3 or new `_system/frameworks/special_situation_lens.md`

MOI Ch 8 taxonomy (align with existing `portfolio_news` tags):

| Inefficiency | Mechanism | Marvin hook |
|--------------|-----------|-------------|
| Index deletion | Forced selling | `market_structure_discount` |
| Dividend cancellation | Income fund selling | `transitory_problem` |
| Tax-loss selling | Calendar | daily scan Q4 |
| Spinoff | Orphan + index | Stahl + news tag |
| Rights offering | Complexity | — |
| Growth disappointment | Fear | Hohn reversion |
| Distressed seller | Non-fundamental | — |

**Rule:** If `moi_bucket == special_situation`, name the inefficiency in footer + estimate **annualized** return (MOI: time matters as much as absolute $ return).

#### 7. Investment decision diary

**File:** `_system/memory/daily/{date}.md` + optional `{TICKER}/research/decision_log.md`

MOI Ch 8–9: log **passes** and **foregone** ideas with reasons; re-evaluate later.

**Rule:** On onboard reject or `watch` after dive, append one line to decision log: `{date} | {TICKER} | pass/watch | {moi_bucket} | {one-line reason}`.

Feeds human quality filter and Milly calibration.

#### 8. Cloning discipline upgrade (Ch 6)

**File:** `mental_models.md` → expand **Cloning + verify**

Add **conviction score** when idea from 13F/letter:

| Signal | Weight |
|--------|--------|
| New/increased position | + |
| >5% / >10% of issuer | ++ |
| Style congruence (same MOI bucket) | + |
| Letter commentary on thesis | ++ |
| High manager turnover | − |
| Macro/theme basket peer buys | disqualify as endorsement |

**Rule:** `superinvestor_signal` bucket requires independent primary-source verification **before** base IRR in valuation.json.

---

### P2 — Archetype-specific depth

#### 9. Deep value / net-net guardrails (Ch 2)

**File:** new archetype `deep_value` in `archetype_models.json` OR overlay flags in `valuation.json`

| Check | Fail action |
|-------|-------------|
| Liquidation value stressed for industry distress | Haircut assets 25–50% in bear |
| Low ROC + no cash return | Cap stance at `watch`; time works against |
| Single-name size | Portfolio rule: max X% in `deep_value` |
| Asset erosion | Require trend on book value / working capital |

Augment screens: insider buying, buybacks, working-capital release (MOI Ch 2).

#### 10. Good + cheap / Magic Formula misuse list (Ch 4)

**File:** `quality_checklist.md`, compounder Tier 2

After normalized ROC / EV/EBIT, explicitly test:

- [ ] ROC sustainable vs transitory (fad, one-time mix)  
- [ ] Reinvestment runway at similar returns  
- [ ] Not eliminating candidate because "stomach churn" without **MOI-approved** tweaks (forward EBIT, not extra subjective hurdles)  
- [ ] Cyclicality flagged in `cycle` field  

Rational Walk / MOI warning: layering subjective filters on quant screens often **removes** the highest prospective returns.

#### 11. Jockey / management block (Ch 5)

**File:** `hohn_business_analysis.md` or `quality_checklist.md`

Add **invert-first management screen**:

- Compensation vs owner economics (acid test)  
- Blank-check question: "If I gave you $1B / $10M tomorrow, what would you do?" — infer from **actions** (buybacks, M&A, capex), not proxy rhetoric  
- Celebrity CEO premium: flag if narrative > track record  
- Separate **business performance** vs **stock performance** in operating snapshot  

#### 12. Small-cap investability screen (Ch 7)

**File:** `investment_process.md` onboarding for micro/small

Before full dive, optional gate (adjust thresholds to Oakcliff size):

- Market cap floor  
- Revenue floor  
- Insider ownership ≥1%  
- Avg daily dollar volume  
- "Passed screen for wrong reason?" — e.g. low P/E due to one-time gain  

**Hidden inflection:** legacy declining segment + profitable growth segment → tag `small_cap_inflection`; require segment split in dive.

#### 13. Equity stub protocol (Ch 9)

**File:** new `_system/frameworks/equity_stub_valuation.md` (only if portfolio holds turnarounds)

High judgment; MOI says win rate may be <50% with lopsided payoffs.

| Requirement | Detail |
|-------------|--------|
| Range of outcomes | Bear / base / bull as **probability-weighted**, not single IRR |
| Leverage nature | Recourse vs non-recourse; **who owns the debt** |
| Distress type | Prefer **industry-wide** selloff vs idiosyncratic failure |
| Management alignment | Common equity vesting |
| Position size | De minimis until thesis tested |
| Stance cap | Default `watch` unless dhando `partial` with explicit floor |

Do **not** apply Lawrence 10yr `full` IRR method to pure stubs — force `irr_method: scenario`.

#### 14. International value checklist (Ch 10)

**File:** `investment_process.md` for non-US tickers (8697.T, TEQ.ST, LSEG)

- How **global** is revenue vs domestic listing? (Europe question)  
- Country exclusion list for downside (MOI: exclude worst jurisdictions rather than chase EM growth)  
- Prefer **regional expert** coattails (local superinvestors) over generic screens  
- Currency / withholding / governance in [HUMAN REVIEW]  

---

### P3 — Structural / optional

#### 15. Unified valuation bounds (Ch 1)

MOI stock selection framework — map to existing tools:

| MOI lens | Marvin tool |
|----------|-------------|
| Replacement value (upper bound) | Segment build / peer acquisition comps |
| Liquidation value (lower bound) | NAV floor, net-net, `floor_pass` |
| Earnings yield | Lawrence FCF₀ / EV |
| Return on capital + reinvestment | Hohn pillars + segment reinvestment rate |

**Rule:** In Valuation section, one line: "Price vs bounds: above replacement / between / below liquidation" where data allows.

#### 16. Add MOI to wisdom library

**Path:** `_system/reference/investment-wisdom/mihaljevic/Manual-of-Ideas-2nd-ed.pdf` (human purchase)  
**INDEX.md:** genius row `John Mihaljevic / MOI` — idea generation, uses/misuses, special situations  
**Proposed memory tag:** `[PROPOSED MOI]` until human promotes

#### 17. One-decision stock filter (Tarasoff / MOI via Buffett lineage)

**File:** `mental_models.md` Tier 2 compounders

Optional quality bar for `core` stance: business you could hold 10–20 years — pricing power > inflation, minimal obsolescence risk. Not a hard gate; documents **why** compounders earn `core` vs `accumulate`.

---

## MOI chapter → Marvin file map

| Ch | MOI theme | Primary proposal target |
|----|-----------|-------------------------|
| 1 | Personal / capital allocator | `decision_stack.md` — owner mindset in exec summary |
| 2 | Deep value | `archetype_models.json`, `equity_stub` sizing |
| 3 | SOTP | `optionality_valuation.md` — discount magnitude |
| 4 | Good + cheap | `quality_checklist.md`, compounder prompts |
| 5 | Jockey | `hohn_business_analysis.md`, gate 3 |
| 6 | Follow leaders | `mental_models.md` cloning score |
| 7 | Small cap | `investment_process.md` investability |
| 8 | Special situations | new `special_situation_lens.md`, annualized return |
| 9 | Equity stubs | new `equity_stub_valuation.md` |
| 10 | International | `investment_process.md` non-US checklist |

---

## Suggested implementation order

1. **P0:** `moi_bucket` + three MOI questions + uses/misuses lint  
2. **P1:** special situation registry + decision diary + cloning score  
3. **P2:** deep_value / equity_stub / small-cap modules as holdings need them  
4. **P3:** wisdom PDF + unified bounds line  

---

## [HUMAN REVIEW]

- Purchase 2nd edition PDF for `_system/reference/investment-wisdom/mihaljevic/`?  
- Adopt `moi_bucket` in classification footer?  
- Portfolio cap on `deep_value` + `equity_stub` sleeves?  
- MOI annualized return required for event-driven names (MSB spinoff orphans, BN simplification)?  

---

## [PROPOSED MEMORY]

- **[PROPOSED MOI]** Idea quality improves when every thesis names **source of inefficiency**, **margin of safety**, and **path to value creation** — not just fair value.  
- **[PROPOSED MOI]** Each strategy has characteristic **misuses**; documenting them beside the thesis reduces repeat mistakes (deep value asset erosion, magic-formula transitory ROC, SOTP without catalyst).  
- **[PROPOSED MOI]** For event-driven and SOTP ideas, **annualized return** and **discount magnitude** matter as much as absolute upside.  
- **[PROPOSED MOI]** Copying superinvestors without style congruence and primary-source verification produces conviction that fails in drawdowns.
