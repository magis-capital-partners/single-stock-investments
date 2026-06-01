# Manual of Ideas Lens (Mihaljevic)

**Purpose:** Idea-generation and misuse guardrails from John Mihaljevic's *The Manual of Ideas*. Complements the decision stack (Munger / Pabrai / Stahl / Lawrence / Hohn); does not replace Lawrence IRR or Hohn operating mechanics.

**Source:** `_system/reference/investment-wisdom/mihaljevic/`  
**Related:** `idea_funnel.md`, `special_situation_lens.md`, `equity_stub_valuation.md`, `classification.md` (`moi_bucket`)

---

## When to read

- **Onboard / discover** — tag `moi_bucket`, run idea funnel gate  
- **Every deep dive** — MOI three questions in "Why the market might be wrong"; uses & misuses table  
- **SOTP / optionality / events** — discount magnitude, annualized return, catalyst path  

---

## MOI three questions (required in every dive)

Under **Why the market might be wrong**, answer in plain English:

| Question | What to name |
|----------|--------------|
| **Source of inefficiency** | Mechanical (index deletion, spinoff orphan, K-1), informational (buried 8-K), analytical (complexity), or behavioral (fear/greed) |
| **Margin of safety** | What limits capital loss if thesis is slow or half wrong |
| **Path to value creation** | Named catalyst + timeline, or self-help (buyback, divest, simplification) |

**Mandatory path:** when `moi_bucket` is `special_situation` or `sotp_hidden` — else flag `[HUMAN REVIEW]`.

Align inefficiency with HK **predictive attribute** when both apply (not either/or).

---

## Uses & misuses (required subsection)

Under **Risks & inversion**, after primary risk:

```markdown
### Uses & misuses (MOI)

| Uses (why this bucket fits) | Misuses (how this idea type fails) |
|-----------------------------|-------------------------------------|
| … | … |
```

Minimum **one misuse row** when `moi_bucket` ≠ `compounder_core`. See bucket cheat sheet below.

---

## `moi_bucket` values

Orthogonal to Stahl **archetype** — tags how the idea was found / how payoff works.

| Value | When |
|-------|------|
| `compounder_core` | Default Lawrence compounders; modelable FCF, no event catalyst |
| `deep_value` | Net-net, liquidation floor, cigar butt |
| `sotp_hidden` | SOTP, dormant asset, holdco NAV discount |
| `good_cheap` | High return on capital + cheap price; quality at fear |
| `jockey` | Thesis is management / capital allocation |
| `superinvestor_signal` | 13F, letter, clone — verify from primaries |
| `small_cap_inflection` | Micro/small; legacy decline + growth segment |
| `special_situation` | Event-driven; near-term catalyst |
| `equity_stub` | Leveraged equity; range-of-outcomes |
| `international_value` | Non-US listing; country/regional lens |

Set in `valuation.json` → `classification_inputs.moi_bucket` and Classification footer.

---

## Bucket cheat sheet — characteristic misuses

| Bucket | Misuses to flag |
|--------|-----------------|
| `deep_value` | Liquidation overstated in distress; asset erosion; low ROC + no cash return; over-concentration |
| `sotp_hidden` | Over-sliced segments; smart-money crowding; value trap without catalyst; "buy-ten-get-one-free" discount |
| `good_cheap` | Transitory ROC (fad); no reinvestment runway; subjective filters dropping best candidates |
| `jockey` | Celebrity CEO premium; trusting proxy rhetoric over actions |
| `superinvestor_signal` | Macro basket ≠ endorsement; stale 13F; hero worship without own work |
| `special_situation` | No named inefficiency; ignoring time / annualized return |
| `equity_stub` | Point estimate vs range; idiosyncratic failure vs industry selloff |
| `small_cap_inflection` | Illiquidity; screen passed for wrong reason; non-recurring EPS |

---

## Valuation bounds (Ch 1 — one line in Valuation section)

Where data allows, state **price vs bounds**:

| Bound | Marvin tool |
|-------|-------------|
| Replacement (upper) | Segment build / peer acquisition comps |
| Liquidation (lower) | NAV floor, net-net, `floor_pass` |
| Earnings yield | Lawrence starting FCF / enterprise value |
| Return on capital + reinvestment | Hohn pillars + segment reinvestment |

Example: "Price sits between liquidation floor and replacement cost; earnings yield below 15% target."

---

## Discount magnitude (SOTP / optionality)

When NAV or SOTP overlay exists:

- Report **premium to fair NAV** (or discount) as **% of price**  
- MOI rule: distinguish **buy-one-get-one-free** (~50% off) from **buy-ten-get-one-free** (small discount)  
- Explicit line: "Discount is / is not large enough to compensate for [no catalyst / illiquidity / governance]."

Spec: `optionality_valuation.md`.

---

## Decision diary

On **pass**, **watch** after dive, or **onboard reject**, append to `{TICKER}/research/decision_log.md`:

```
{date} | {TICKER} | {pass|watch|reject} | {moi_bucket} | {one-line reason}
```

Also log `[PROPOSED MOI]` bullets in `_system/memory/daily/{date}.md` when process changes.

---

## Read order

1. This file  
2. `idea_funnel.md` (discover)  
3. Bucket-specific: `special_situation_lens.md` or `equity_stub_valuation.md` when triggered  
4. `mental_models.md` — cloning conviction score if `superinvestor_signal`
