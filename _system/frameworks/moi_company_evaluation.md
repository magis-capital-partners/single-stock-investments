# Manual of Ideas — company evaluation rules (comprehensive)

**Source:** John Mihaljevic, *The Manual of Ideas* (Wiley, 1st ed. 2013).  
**Wisdom path:** `_system/reference/investment-wisdom/mihaljevic/`  
**Full text (after EPUB install):** `Manual-of-Ideas-full-text.txt`  
**Companion:** `analysis_arsenal.md`, `decision_stack.md`, `moi_lens.md`

**Purpose:** Exhaustive evaluation checklist Marvin can apply when researching any name. Not every rule applies to every ticker — tag `payoff_lens` first, then open the matching chapter block.

**MOI repeating pattern (every strategy chapter):**
1. Why it works  
2. Uses and misuses  
3. Screening  
4. Beyond screening  
5. Key questions  

---

## Part A — Universal rules (every company, Ch 1)

Cast yourself as **capital allocator / owner**, not trader or copycat.

### A1. Valuation bounds (three lenses)

| Bound | Question | Marvin tool |
|-------|----------|-------------|
| **Replacement value** (upper) | What would a rational acquirer pay to recreate this franchise? | Segment build, peer M&A comps |
| **Liquidation value** (lower) | What do assets fetch in a distressed sale? | NAV floor, net-net, bear SOTP |
| **Earnings power** (middle) | Normalized owner cash yield on enterprise value? | Lawrence FCF₀, EV/EBIT |

**Rule A1.1:** State where price sits vs these three bounds when data allows (above replacement / between / below liquidation).

**Rule A1.2:** Losses compound against long-term appreciation — do not normalize away structural loss segments without explicit rationale.

**Rule A1.3:** Size limits apply to mammals and companies (Pabrai) — position size must match liquidity and thesis durability.

### A2. Stock selection framework

**Rule A2.1:** Flexible yet concrete — all companies reduce to **equity value vs market value**.

**Rule A2.2:** Return on capital employed **plus reinvestment runway** — high ROC on existing capital is meaningless without reinvestment at similar returns.

**Rule A2.3:** Separate **business performance** from **stock performance** in every operating snapshot.

### A3. Idea funnel (pre-dive)

**Rule A3.1:** Rank ~20 pre-qualified ideas → narrow to **3–5** compelling names before full deep dive.

**Rule A3.2:** Log **passes** and **foregone** ideas in `{TICKER}/research/decision_log.md` with one-line reason.

**Rule A3.3:** Proceed to deep dive only if: six questions sketched, no disqualifying misuse, return sketch beats portfolio median OR strategic sleeve need.

### A4. Three MOI questions (Q5 enrichment)

Answer in **Why the market might be wrong** (prose, not a duplicate table):

| # | Question | Required when |
|---|----------|---------------|
| Q5a | **Source of inefficiency** — mechanical, informational, analytical, or behavioral? | `asset` or `event` lens |
| Q5b | **Margin of safety** — what protects capital if thesis is slow or half wrong? | Always (maps to dhando + floor) |
| Q5c | **Path to value creation** — named catalyst + timeline, or self-help (buyback, divest)? | `asset` or `event` lens |

**Rule A4.1:** Without identifiable inefficiency, higher probability the valuation has a flaw.

**Rule A4.2:** Margin of safety is **not** a separate MOI table — it is Q3 (dhando + floor) in Payoff & return.

### A5. Uses & misuses (mandatory lens failure mode)

**Rule A5.1:** Under Risks & inversion, state **lens failure mode** when `payoff_lens` is `asset`, `event`, or `levered`.

**Rule A5.2:** Every strategy has characteristic misuses — name at least one that applies to *this* ticker.

---

## Part B — Deep value / Graham-style (Ch 2)

**Trigger:** `payoff_lens: asset`, net-net, cigar butt, liquidation thesis.

### Why it works
- Market over-discounts tangible distress; price leads fundamentals at inflection.
- Holy grail (rare): asset protection **plus** high ROC unless near-term profit collapse.

### Screening rules

| # | Rule |
|---|------|
| B1 | Start with **price** — tangible bargain metrics first (NCAV, P/B, P/TBV). |
| B2 | Augment screens: **buybacks**, **insider buying**, **working capital shrinkage**. |
| B3 | Prefer non-capital-intensive net-nets where asset value is realizable. |
| B4 | Ask: is value **growing**, **flat**, or **shrinking** after screen hit? |

### Beyond screening

| # | Rule |
|---|------|
| B5 | Stress liquidation in **industry distress** — buyers scarce; haircut assets 25–50% in bear. |
| B6 | Track trend on book value and working capital — balance-sheet-only value **erodes over time**. |
| B7 | Concentration risk — cigar butts deserve smaller position sizes. |
| B8 | Time works **against** low-ROC asset-rich businesses without cash return. |

### Key evaluation questions

1. Would liquidation play out in industry distress where buyers are scarce?  
2. Is asset value growing, flat, or shrinking?  
3. Is there a path from asset value to **cash return** (not just book)?  
4. What is insider behavior (buying vs selling)?  
5. Is this a non-capital-intensive net-net or an oxymoron?  

### Uses
- Genuine mispricing of tangible assets with catalyst to realize value.
- Temporary distress with intact asset base.

### Misuses (red flags)
- Overestimated liquidation in distress.  
- Asset-rich, low-ROC, no cash return — time erodes.  
- Creative destruction obsoletes assets.  
- Concentration in single cigar butt.  
- Buying because screen said cheap without trend on book/WC.  

**Marvin:** `irr_method: scenario` or yield_curve; cap stance at `watch` if low ROC + no cash return; bear case haircuts assets.

---

## Part C — Sum-of-the-parts / hidden assets (Ch 3)

**Trigger:** `payoff_lens: asset`, holdco discount, dormant asset, `valuation_mode: optionality`.

### Why it works
- Market prices consolidated earnings; non-core or hidden assets mispriced.
- Strategic flexibility: divest, repurchase, reinvest in high-return segment.

### Screening rules

| # | Rule |
|---|------|
| C1 | Identify **distinct** businesses/assets with separable economics. |
| C2 | Compare sum of parts to market cap — require **discount magnitude** stated as % of price. |
| C3 | Distinguish "buy-one-get-one-free" (~50% discount) vs "buy-ten-get-one-free" (~10% discount). |
| C4 | Ask: **how will hidden assets cease to be hidden?** |

### Beyond screening

| # | Rule |
|---|------|
| C5 | Do not over-slice — segment count must map to filing disclosures. |
| C6 | Value trap without catalyst — discount alone is insufficient. |
| C7 | Smart-money crowding can eliminate discount before you enter. |
| C8 | Report **premium to floor** and **discount to SOTP** separately when price > NAV. |

### Key evaluation questions

1. What is the catalyst to unlock hidden value (divestiture, spin, mark-to-market, listing)?  
2. Is management incentivized to close the discount?  
3. Is the discount large enough to compensate for no catalyst / illiquidity / governance?  
4. Are we double-counting assets already in Lawrence FCF?  
5. Would a rational acquirer pay replacement value for the core only?  

### Uses
- Holdco trading below look-through value with identifiable catalyst stack (FRMO pattern).
- Non-core asset worth more separated than embedded.

### Misuses
- Over-slicing segments without filing support.  
- Value trap — deep discount, no path to realization.  
- Crowding by specialists eliminates edge.  
- Treating GAAP book as floor when assets are off balance sheet (TPL pattern).  

**Marvin:** `optionality_gate`, `sotp_build`, `book_estimate`; discount magnitude in Payoff; do not use GAAP book as dhando when misstated.

---

## Part D — Good + cheap / Magic Formula (Ch 4)

**Trigger:** `payoff_lens: operating`, compounder at fear price, quality + cheap screen.

### Why it works
- Market conflates temporary problems with permanent impairment.
- Two-factor rank: **quality** (ROC on capital employed) + **cheapness** (EBIT/EV).

### Screening rules (Greenblatt)

| Metric | Definition |
|--------|------------|
| Quality | Operating income / (net working capital + net fixed assets) |
| Cheap | Operating income / enterprise value (leverage-neutral) |
| Rank | Combine ranks; top decile candidates |

**Rule D1:** Exclude financials and utilities from pure Magic Formula screens (Greenblatt convention).

**Rule D2:** Tweaks that help: forward earnings, international universe, ROC hurdle before ranking cheapness.

### Beyond screening

| # | Rule |
|---|------|
| D3 | Test ROC **sustainable** vs transitory (fad, one-time mix, cyclical peak). |
| D4 | Confirm **reinvestment runway** at similar returns — no runway = no compounding. |
| D5 | Flag cyclicality in `cycle` field — mid-cycle vs peak vs trough. |
| D6 | Do not eliminate candidates because "stomach churn" without MOI-approved tweaks. |
| D7 | Watch M&A rollups inflating ROC; insider selling at screen hit. |

### Key evaluation questions

1. Is high ROC transitory (fad, cyclical peak, one-time cost cuts)?  
2. Where can reinvested capital earn similar returns for 5–10 years?  
3. Are subjective filters removing the highest prospective names?  
4. Is cheapness due to permanent impairment or temporary fear?  
5. Could this be a **one-decision stock** (10–20 year hold, pricing power > inflation)?  

### Uses
- Quality compounder temporarily cheap on fixable problem.
- Systematic discipline against narrative chasing.

### Misuses
- Transitory high ROC from fad or cyclical peak.  
- No reinvestment runway — ex-growth value trap.  
- Subjective filters that drop best candidates psychologically.  
- Cyclicality ignored — buying peak earnings.  
- M&A rollup masking organic decay.  

**Marvin:** Lawrence `full`; `quality_checklist.md`; `cycle` field; growth mechanism in Business & moat.

---

## Part E — Jockey stocks / great managers (Ch 5)

**Trigger:** Thesis is management / capital allocation; `payoff_lens: operating` with jockey emphasis.

### Why it works
- Exceptional capital allocators compound per-share value over decades.
- Buffett: great business first, great manager second — jockey alone is insufficient.

### Screening proxies

| Proxy | What to check |
|-------|---------------|
| ROCE trend | Stable or improving vs peers |
| Capital per share growth | Real economic growth, not dilution |
| Asset turnover | Operational efficiency |
| Margins | Pricing power vs cost discipline |
| Capex trends | Maintenance vs growth vs empire-building |
| Insider buying | Skin in the game |
| Stock ownership | CEO/CFO meaningful stake |

### Beyond screening

| # | Rule |
|---|------|
| E1 | **Invert first** — eliminate bad actors before celebrating good ones. |
| E2 | **Compensation acid test** — pay vs owner economics over 3–5 years. |
| E3 | **Blank-check question:** If I gave you $1B / $10M / $1M tomorrow, what would you do? Judge **actions** (buybacks, M&A, capex, dividends), not proxy rhetoric. |
| E4 | Find underappreciated CEOs: humble, conservative, non-promotional. |
| E5 | Celebrity CEO premium — flag if narrative > track record. |
| E6 | Separate business performance from stock performance. |

### Key evaluation questions

1. What has management done with free cash flow historically?  
2. Are acquisitions dilutive to ROIC or accretive?  
3. Is compensation aligned with long-term per-share value?  
4. Would you trust this team with your family's capital for 10 years?  
5. Is the jockey thesis independent of a mediocre business (red flag)?  

### Uses
- Owner-operator with decades of rational capital allocation.
- Underfollowed CEO with strong ROCE and insider alignment.

### Misuses
- Hero worship without business quality.  
- Confusing stock price rise with managerial skill.  
- Ignoring empire-building M&A.  
- Proxy-season promises vs multi-year actions.  

**Marvin:** Gate 4 (aligned management); Hohn fieldwork; `[HUMAN REVIEW]` on compensation outliers.

---

## Part F — Follow the leaders / superinvestors (Ch 6)

**Trigger:** Idea from 13F, investor letter, clone; discovery tag in decision_log.

### Why it works
- Skilled investors do heavy lifting; edge is in **verification** and **timing**.

### Screening / sourcing

| Source | Use |
|--------|-----|
| 13F filings | Starting watchlist only |
| Partner letters | Process learning + thesis hints |
| Conference transcripts | Qualitative context |

### Conviction score (clone discipline)

| Signal | Weight |
|--------|--------|
| New or increased position | + |
| >5% / >10% of issuer | ++ |
| Letter commentary on specific thesis | ++ |
| Style congruence (same payoff lens) | + |
| High manager turnover at fund | − |
| Macro/theme basket peer buys | **Disqualify** as stock endorsement |

### Beyond screening

| # | Rule |
|---|------|
| F1 | **Do your own work** — copying without context fails in drawdowns. |
| F2 | Stale 13F — reporting lag; position may be exited. |
| F3 | Macro basket ≠ endorsement of every name in theme. |
| F4 | Track investors matching **your** philosophy, not fame. |
| F5 | Independent primary-source verification **before** base IRR in valuation.json. |

### Key evaluation questions

1. Why does this investor own it — and is that reason still valid?  
2. Is their style congruent with ours (duration, leverage, archetype)?  
3. What do we see in filings that confirms or contradicts their thesis?  
4. Is the position size meaningful for their fund?  
5. Are we cloning the idea or the conviction level?  

### Uses
- Idea generation shortcut with mandatory verify pass.
- Learning process from letters of aligned investors.

### Misuses
- Hero worship.  
- Stale 13F as live thesis.  
- Theme basket as due diligence substitute.  
- Position sizing clone without independent conviction.  

**Marvin:** `third_party_sources.md` approval; cross-check required; never auto-approve external IRR.

---

## Part G — Small / micro cap (Ch 7)

**Trigger:** Micro/small cap; `payoff_lens: event` or `small_cap_inflection` tag.

### Investability screen (before full dive)

| Threshold | MOI-style gate |
|-----------|----------------|
| Market cap | >$50M (adjust for Oakcliff liquidity) |
| Revenue | >$10M trailing |
| Employees | ≥10 |
| Insider ownership | ≥1% |
| Avg daily dollar volume | Sufficient for intended position |

**Rule G1:** "Passed screen for wrong reason?" — e.g. low P/E from one-time gain.

### Why it works
- Neglected by institutions (size vs fund AUM).
- Few professionals work A→Z on small caps.
- Hidden inflection: legacy decline + profitable growth segment in same company.

### Beyond screening

| # | Rule |
|---|------|
| G2 | Qualitative work beyond screens — read full 10-K, call IR if needed. |
| G3 | Illiquidity discount — size position accordingly. |
| G4 | Non-recurring items buried in reports — normalize carefully. |
| G5 | Segment split required when legacy + growth coexist. |
| G6 | Volatility higher than large-cap — cycle field mandatory. |

### Key evaluation questions

1. Why is this neglected (size, listing, complexity, scandal)?  
2. Is neglect informational or deserved (fraud, obsolescence)?  
3. Is there a profitable segment hidden inside a declining whole?  
4. Can we build a position without moving the market?  
5. What would make an institution discover this name?  

### Uses
- Underfollowed compounder inflection.
- Complexity discount on readable business.

### Misuses
- Illiquidity trap — cannot exit.  
- Screen cheapness from non-recurring item.  
- Neglect because business is bad, not because it's small.  

**Marvin:** `idea_funnel.md`; segment map; `[HUMAN REVIEW]` on liquidity.

---

## Part H — Special situations / event-driven (Ch 8)

**Trigger:** `payoff_lens: event`; spinoff, index deletion, dividend cut, rights offering.

### Why it works
- Return often **independent of market** near term.
- Situations **end** — capital recycles.
- Mechanical sellers create non-fundamental dislocations.

### Inefficiency taxonomy

| Type | Mechanism | Examples |
|------|-----------|----------|
| Index deletion | Forced selling | S&P removal |
| Dividend cancellation | Income fund selling | MSB, SJT pattern |
| Tax-loss selling | Calendar | Q4 orphans |
| Spinoff | Orphan + index mismatch | BN, SPGI |
| Rights offering | Complexity discount | — |
| Growth disappointment | Fear overshoot | Hohn reversion |
| Distressed seller | Non-fundamental | Forced fund liquidation |
| Fear / greed | Behavioral | Panic selloff |
| Complexity | Analytical | K-1 trusts, holdco |

### Screening rules

| # | Rule |
|---|------|
| H1 | Name the **specific inefficiency** — not generic "it's cheap." |
| H2 | Estimate **annualized return**, not just absolute upside. |
| H3 | Time component: when does situation resolve? |
| H4 | Cross-ref `portfolio_news` spinoff/event tags. |

### Beyond screening

| # | Rule |
|---|------|
| H5 | Without inefficiency, higher chance valuation is flawed. |
| H6 | Situation ends — plan exit in decision_log. |
| H7 | Investment diary: log passes for deliberate practice. |

### Key evaluation questions

1. What is the **source of inefficiency** (mechanical vs behavioral)?  
2. What is the **margin of safety** if catalyst slips 12–24 months?  
3. What is the **path to value creation** with dated catalyst?  
4. What is **annualized return** at current price and timeline?  
5. Who is the forced seller and when does selling stop?  

### Uses
- Dated catalyst with identifiable forced selling.
- Post-event orphan with temporary neglect.

### Misuses
- No mechanical seller — "special" in name only.  
- Ignoring time in return calculation.  
- Niche crowded by event-driven funds.  
- Catalyst passed but thesis kept on life support.  

**Marvin:** `special_situation_lens.md`; `irr_method: yield_curve` or scenario; lens failure mode required.

---

## Part I — Equity stubs / leveraged equity (Ch 9)

**Trigger:** `payoff_lens: levered`; high debt, turnaround, bankruptcy exit.

### Why it works
- Market ignores optionality of equity when debt constrains outcomes.
- Non-recourse debt sometimes mispriced.
- Industry-wide selloffs create mispriced stubs.

### Evaluation rules

| # | Rule |
|---|------|
| I1 | Force `irr_method: scenario` — **never** Lawrence 10yr `full` on pure stubs. |
| I2 | **Range of outcomes** — probability-weighted bear/base/bull, not point IRR. |
| I3 | **Recourse vs non-recourse** debt — who gets paid first? |
| I4 | **Who owns the debt** — aligned or adversarial? |
| I5 | Prefer **industry-wide** distress over idiosyncratic failure. |
| I6 | Management vesting in **common equity** — alignment check. |
| I7 | Win rate may be <50% — size **de minimis** until thesis tested. |
| I8 | Default stance `watch` unless partial dhando + explicit floor. |

### Key evaluation questions

1. What is equity worth in bear/base/bull restructuring scenarios?  
2. Is debt non-recourse at asset level?  
3. Is this industry cyclicality or company-specific failure?  
4. What triggers covenant breach or refinancing wall?  
5. Am I reaching after prior stub success (overconfidence)?  

### Uses
- Lopsided payoff with identifiable floor.
- Post-restructuring equity with clean capital structure path.

### Misuses
- Point estimate IRR on levered equity.  
- Idiosyncratic failure without industry context.  
- Overreach after one winner.  
- Ignoring debt owner incentives.  

**Marvin:** `equity_stub_valuation.md`; lens failure mode mandatory.

---

## Part J — International value (Ch 10)

**Trigger:** Non-US listing (8697.T, TEQ.ST, LSEG, CSU).

### Why it works
- Less efficient markets, fewer analysts, regional mispricings.
- Global businesses listed locally at domestic discount.

### Screening rules

| # | Rule |
|---|------|
| J1 | How **global** is revenue vs domestic listing? (especially Europe) |
| J2 | FT / local screens for candidate generation. |
| J3 | Exclude worst jurisdictions on **downside** — do not chase EM growth blindly. |

### Beyond screening

| # | Rule |
|---|------|
| J4 | Currency risk — translate owner cash, not just price. |
| J5 | Withholding tax on dividends — net yield to Oakcliff holder. |
| J6 | Governance / minority shareholder protection — `[HUMAN REVIEW]`. |
| J7 | Prefer **regional expert** coattails over generic screens. |
| J8 | ADR vs local listing liquidity and fee drag. |

### Key evaluation questions

1. Is this a global business priced as a domestic one?  
2. What jurisdiction risk caps position size?  
3. Are filings readable and timely (translation lag)?  
4. Who are local smart investors following this name?  
5. What is repatriation path for dividends and exit?  

### Uses
- Global compounder at local-market fear price.
- Regional croupier/exchange with structural moat.

### Misuses
- EM growth story ignoring governance.  
- Currency ignored in IRR.  
- Generic screen without local context.  

**Marvin:** `investment_process.md` non-US checklist; cite local filings in Primary sources.

---

## Part K — Cross-strategy synthesis rules

### K1. Payoff lens picker

| If primary return driver is… | Set `payoff_lens` | Open MOI part |
|------------------------------|-------------------|---------------|
| Normalized owner cash compounding | `operating` | D (+ A) |
| Asset / NAV / holdco discount | `asset` | C (+ B if distressed) |
| Dated catalyst / forced selling | `event` | H (+ G if small) |
| Leveraged equity optionality | `levered` | I |
| Not yet classified | `pending` | A3 funnel only |

### K2. Discount magnitude (SOTP / asset names)

**Rule K2.1:** When NAV or SOTP discount >50%, report discount as **% of price** AND **premium to floor** separately.

**Rule K2.2:** Explicit statement: "Discount is / is not large enough to compensate for [no catalyst / illiquidity / governance]."

**Rule K2.3:** TPL-style: price well **above** filing NAV overlay — MOI classifies as *not* compelling SOTP entry despite good business.

### K3. Annualized return (event names)

**Rule K3.1:** For dated catalysts, compute annualized return: `(payoff/price)^(1/years) - 1`.

**Rule K3.2:** Compare annualized return to Lawrence bar and portfolio median.

### K4. One-decision stock filter (optional quality bar)

For `core` stance on compounders: could we hold 10–20 years — pricing power above inflation, minimal obsolescence?

### K5. Marvin integration map

| MOI part | Primary Marvin file |
|----------|---------------------|
| A Universal | `decision_stack.md`, `idea_funnel.md` |
| B Deep value | bear scenario, asset haircuts |
| C SOTP | `optionality_valuation.md`, `current_book_estimate.md` |
| D Good+cheap | `quality_checklist.md`, Lawrence `full` |
| E Jockey | `hohn_business_analysis.md`, gate 4 |
| F Clone | `mental_models.md`, `third_party_cross_reference.md` |
| G Small cap | `idea_funnel.md` |
| H Special sit | `special_situation_lens.md` |
| I Equity stub | `equity_stub_valuation.md` |
| J International | `investment_process.md` |

---

## Part L — Master evaluation checklist (copy for any dive)

### Phase 1 — Classify
- [ ] Tag `payoff_lens` in `valuation.json`
- [ ] Pick MOI parts B–J that apply
- [ ] Set `irr_method` (full / yield_curve / scenario)

### Phase 2 — Universal (Part A)
- [ ] Price vs replacement / liquidation / earnings power
- [ ] Q5a inefficiency (if non-operating)
- [ ] Q5b margin of safety via dhando + floor
- [ ] Q5c path to value creation (if asset/event)
- [ ] Lens failure mode (if asset/event/levered)

### Phase 3 — Strategy-specific
- [ ] Complete screening rules for tagged MOI parts
- [ ] Complete beyond-screening rules
- [ ] Answer all key questions for tagged parts
- [ ] Name ≥1 misuse that applies to this ticker

### Phase 4 — Marvin outputs
- [ ] Assumption ledger + IRR arithmetic
- [ ] Option scan (every ticker)
- [ ] Cross-check third party
- [ ] Milly adversarial pass

---

## [HUMAN REVIEW]

- Promote selected rules into `lint_deep_dive.py` after discussion?
- Portfolio caps on `deep_value` + `equity_stub` sleeves?
- Require annualized return line for all `event` lens names?

## Source note

Rules synthesized from MOI 1st ed. (2013) chapter structure, workspace `Manual-of-Ideas-chapter-reference.txt`, CFA Institute / Rational Walk reviews, and pending framework review `_system/reviews/pending/moi_framework_suggestions_2026-06-01.md`. After licensed EPUB install, agents should prefer cite-by-path to `Manual-of-Ideas-full-text.txt`.
