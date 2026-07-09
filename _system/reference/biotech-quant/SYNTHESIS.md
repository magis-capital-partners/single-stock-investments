# Biotech Quant: Research Synthesis

**Date:** 2026-07-09  
**Author:** Marvin  
**Purpose:** Distill Verdad *Biotech Investing* (2026), serial essays, podcast, and secondary digests into facts, inferences, and dashboard design rules.

This is a research summary, not an approved belief. Nothing here is promoted to
`_system/memory/MEMORY.md`. Quant scores belong in `biotech_overlay` / ownership
signals, not base Lawrence IRR, until a human approves the source in
`third_party_sources.md`.

**Primary source:** `_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf`  
**Machine spec:** `_system/reference/biotech-quant/FACTOR_SPEC.json`

---

## 1. Sector facts (Verdad)

1. Of ~1,000 biotechs that reached $200M+ market cap over ~30 years, **~67% lost money**.
   Roughly half of losers were acquired at negative total returns; many survivors trade
   as "zombie biotechs" below cash.
2. Biotech is a large share of small-cap universes and has **low pairwise correlation**
   versus other sectors — attractive for diversified quant, dangerous for concentrated
   fundamental shorts.
3. Traditional profit-based value and own-price momentum are **inverted** in biotech
   (cheap-on-P/E and high-momentum names underperform).
4. Verdad built specialist holdings, insider disclosures, and a point-in-time set of
   **130,000+ clinical trials** to rebuild quality, value, and momentum.

---

## 2. Expert / quality signals

### 2.1 Specialist 13F consensus (strongest single quality proxy)

- Define specialist as funds with **>50% of 13F market value in biotech**.
- Sort names by specialist concentration: Q1 ~−2% ann. → Q5 ~+20% ann. (**~22 ppt**).
- Signal is strongest when **multiple** specialists own the name (consensus > hero pick).
- Hold periods are long (~2 years); 13F lag remains informative.
- ~72% of specialist dollars sit in large names, but **alpha is largest in small caps**
  (~30% vs ~0% in the smallest third for high vs zero specialist concentration).
- ETFs (e.g. ARKG) count as **one vote**.

### 2.2 Insiders

- Use **buys**, not sells. Downweight **CEO** buys; upweight **CFO / other officers**.
- Prefer **counts** over dollar size. Horizon is months, not days.
- Filtered insider Q1→Q5 roughly 0% → +20% ann. in Verdad tables.

### 2.3 Short sellers

- Most-shorted biotech quintile ~−19% ann.; least-shorted ~+16%.
- Prefer **diversified** short books (many weak names) over concentrated conviction shorts.
- Short book mainly **dampens volatility**, not lottery-ticket alpha.

---

## 3. Rebuilt value and momentum

### 3.1 Spend-based value

```
spend ≈ revenue − cash_flow_from_operations   # cash out the door
spend_value = market_cap / cumulative_spend   # lower = cheaper
```

- Clinical spend is a better pipeline anchor than profits when revenue is zero.
- Spend-value Q1→Q5 roughly −6% → +19% ann.; Verdad finds spend value often
  **stronger than specialist alone** for rebalancing because it moves with price.

### 3.2 Peer / cohort momentum

- Own-price momentum inverted (post-catalyst mean reversion).
- Group companies by clinical-program similarity (indication, phase, modality).
- Momentum = return of **similarity-weighted peers**, not the stock's own trail.
- Peer-momentum Q1→Q5 roughly −1% → +12% ann.

### 3.3 Blended model

- Quality (specialists + insiders + shorts) + spend value + peer momentum.
- Blended Q1→Q5 roughly −17% → +21% (**~38 ppt**).
- Illustrative L/S (Verdad backtest, net of costs): ~19.1% return / ~18.9% vol vs XBI
  ~3.7% / ~33% (Jan 2015–Aug 2025). Treat as **context**, not a live mandate.

---

## 4. Marvin design implications

| Rule | Implementation |
|------|----------------|
| Never show book megacaps as biotech unless quant-universe gate passes | `is_biotech_quant_universe_ticker()` |
| Specialist consensus is live quality factor | `build_specialist_13f_signals.py` |
| Ban P/E and own-price momentum in biotech overlay | `FACTOR_SPEC.json` `banned_for_biotech` |
| Spend / insider / peer / short feed composite | `biotech_overlay` on `valuation.json` |
| Library findings are context tier | `third_party_sources.md` + methodology claims |
| Knowledge compounds via claims + UI catalog | `from_biotech_methodology()` + Biotech tab |

---

## 5. Methodology claim bullets (for research memory)

These evergreen claims are ingested as `claim_type: methodology` (capped):

1. Specialist consensus (>50% biotech funds) is the primary biotech quality screen.
2. Prefer names owned by multiple specialists; unique single-fund ideas underperform consensus.
3. Traditional P/E value is inverted in biotech; use spend vs market cap instead.
4. Own-price momentum is inverted; use clinical peer-cohort momentum.
5. Insider buys matter when non-CEO (especially CFO); sells are mostly noise.
6. Short interest identifies losers; size shorts for diversification, not conviction.
7. 13F lag is acceptable because specialist holds are multi-year and illiquid in small caps.
8. Small-cap specialist concentration carries more return than large-cap specialist dollars.
9. Blended quality + spend value + peer momentum spreads returns more than any single factor.
10. Biotech quant is an overlay; it does not replace Lawrence IRR for compounders.

---

## 6. Open research (Verdad pipeline → our backlog)

- PIPE / penny warrant ownership not in equity 13F tables
- Strategic big-pharma stakes as a separate holder type
- Intra-quarter 13D/G updates
- Subsector-normalized spend value (oncology vs derm)
- Full ClinicalTrials.gov similarity engine at scale
