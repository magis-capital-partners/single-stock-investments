# Verdad-Style Biotech Quant: Reverse-Engineered Methodology & Marvin Implementation Plan

**Date:** 2026-07-09  
**Source:** [Investing in Biotech with Verdad Capital](https://www.buysidedigest.com/podcast/investing-in-biotech-with-verdad-capital/) (Yet Another Value Podcast, Feb 2026) + Verdad *Investing in Biotech* paper (linked from show notes)  
**Status:** Implemented Phases A–D (2026-07-09). Source of truth: `_system/reference/biotech-quant/` (`SYNTHESIS.md`, `FACTOR_SPEC.json`).

---

## 0. Executive summary

Verdad Capital treats biotech as a **quant-friendly but structurally weird** sector: money-losing, event-heavy, uncorrelated, and ~25% of Russell 2000. Traditional value (EV/EBIT) fails. Their edge is a **multi-factor long/short model** built from signals that make sense *on biotech's own terms*:

1. **Specialist 13F consensus** (who owns it among biotech-only funds)
2. **Spend-based value** (cumulative cash burn vs market cap)
3. **Insider buys** (CFO / non-CEO; not CEO; counts not dollars)
4. **Short interest / borrow** (diversified short book, not conviction shorts)
5. **Cohort momentum** (clinical-trial similarity clusters, not single-ticker events)

Returns come from **frequent rebalancing** on relative scores, not from predicting Phase 3 outcomes. Events are too sparse; behavior (volatility, drift, relative cheapness) is the trade.

This plan maps each Verdad layer to data sources, formulas, Marvin scripts, dashboard surfaces, and validation gates.

---

## 1. Why biotech needs a separate quant stack

### 1.1 The sector problem (Verdad framing)

| Standard quant assumption | Biotech reality |
|---------------------------|-----------------|
| Profits exist | Most names pre-revenue or pre-profit |
| Financial statements anchor value | R&D burn dominates; GAAP misleads |
| Events are diversifiable | Trial readouts are lumpy but **too few** for event studies at portfolio scale |
| Sectors correlate | Biotech is **least correlated** sector — diversifier |
| Exclude money losers | Would drop ~25% of Russell 2000 |

**Marvin implication:** Do not pipe biotech through `lawrence_irr` / EV-EBIT screens. Tag `payoff_lens: biotech_quant` and route to this stack.

### 1.2 Design principle: meet biotech on its own terms

Verdad's rule: only use factors with **face validity** to sector specialists. Every signal was field-tested by interviewing biotech PMs, then backtested.

**Marvin rule:** Base-case IRR deep dives stay separate. Biotech quant is an **overlay** (`valuation.json` → `biotech_overlay`) until human promotes a name to full compounder work.

---

## 2. Universe construction (Step 1)

### 2.1 Verdad: investable biotech universe

1. Start from **US listed equities** with biotech/pharma/life-science exposure (small + mid cap emphasis).
2. **Specialist fund filter** defines the ownership signal universe (~70 funds today, growing over time).
3. Rebalance universe quarterly as funds enter/exit "specialist" status.

### 2.2 Verdad: specialist fund definition

> **>50% of 13F portfolio market value in biotech** → specialist fund.

Properties:

- Funds **drop in/out automatically** as their portfolio mix changes.
- No performance filter on specialists ("70 funds, 5 terrible — who cares").
- **ETFs count as one vote** (e.g. ARK Genomic Revolution = single specialist holder).
- **Big pharma strategic stakes** (Pfizer 13F) can appear but are flagged as messy; research pipeline item.

### 2.3 Marvin implementation (shipped + next)

| Item | Status | Path / script |
|------|--------|----------------|
| Specialist fund registry | Shipped | `ownership/biotech_specialist_funds.json` |
| CIK registry | Shipped | `ownership/fund_cik_registry.json` |
| 13F ingest | Shipped | `ingest_specialist_13f.py` |
| **>50% biotech portfolio rule** | **Not shipped** | Compute from full 13F, not our book |
| **Dynamic specialist in/out** | **Not shipped** | Quarterly fund classification job |
| **Quant universe gate** | **Shipped 2026-07-09** | `is_biotech_quant_universe_ticker()` — portfolio tickers excluded unless 13F + biotech classification |

### 2.4 Quant universe gate (Marvin-specific fix)

Our ingest matches 13F holdings **only to portfolio tickers** (name/CUSIP fuzzy match). That pulled megacaps (GOOGL, AMD) into the biotech tab.

**Rule (shipped):** A name appears in biotech quant UI only if:

1. It has ≥1 specialist 13F record in our ingest, **and**
2. It passes `is_biotech_ticker()` (sleeve / watchlist / company name) **or** `issuer_is_biotech()` on 13F issuer name.

Portfolio holdings like CPRT, AMZN, NVDA are **excluded** unless explicitly on `biotech_watchlist` with valid specialist holdings.

---

## 3. Core signal: Specialist ownership consensus (Step 2)

### 3.1 Verdad discovery process

1. Interview biotech PMs → "We follow what other specialists own."
2. Download 13F history for all specialist funds.
3. Test: **consensus ownership predicts forward returns** better than picking "best" managers.

### 3.2 Verdad metrics

| Metric | Definition | Interpretation |
|--------|------------|----------------|
| **Specialist count** | # specialist funds holding name | More = better quality filter |
| **Core vs all** | Subset of "best known" funds (optional) | Additive, not replacement for consensus |
| **Relative specialist density** | Specialist holders / all institutional holders | Controls for small caps with few total holders |
| **Zero specialists** | No specialist owns name | ~zero return contribution — avoid |
| **High consensus** | Multiple specialists | Strong long candidate pool |

Key insight: **Consensus beats hero picking.** Names where only one specialist has a unique view underperform the crowded specialist longs.

### 3.3 Verdad: what specialist ownership is *not*

- Not an event predictor (M&A timing not modeled).
- Not a Phase 3 classifier.
- A **quality + lower-volatility behavior** filter for diversified portfolios.
- Slow-moving (13F lag ~45 days; specialists illiquid in small caps).

### 3.4 Marvin formulas (current + target)

**Current (`build_specialist_13f_signals.py`):**

```
consensus_score = min(100, core_count×18 + specialist_count×6 + adds×4 − trims×3 − exits×8)
```

**Target (Verdad-aligned):**

```
specialist_count      = |{fund_id ∈ specialist_universe : shares > 0}|
total_holders         = |{all 13F filers with position}|  # requires broad 13F, not just specialists
specialist_density    = specialist_count / max(total_holders, 1)
consensus_rank        = percentile(specialist_count) within universe
density_rank          = percentile(specialist_density)
consensus_composite   = 0.6 × consensus_rank + 0.4 × density_rank
```

**Flow flags (keep):**

- `initiation_signal`: ≥2 core funds new in quarter
- `exit_signal`: any core fund full exit
- `concentration_flag`: core fund position ≥ $100M (configurable)

### 3.5 Data pipeline steps

1. **Ingest** — For each specialist CIK, fetch latest 13F-HR InfoTable XML (SEC EDGAR).
2. **Normalize** — CUSIP → ticker map; issuer name fallback; learn map over time.
3. **Diff** — Compare quarter Q vs Q−1: new / add / trim / exit / unchanged.
4. **Score** — Write `signals_latest.json` + append `records/{YYYYQn}.json`.
5. **Publish** — `build_research_memory.py` → dashboard biotech tab; `build_insights.py` → ownership events.

### 3.6 Dashboard surfaces

- **Biotech → Quant signals** table: consensus, core funds, all specialists, net flow, flags.
- **Ticker panel → Ownership claims** from specialist 13F flow.
- **Review queue** if quant-universe name missing 13F after ingest.

---

## 4. Value signal: Spend anchor (Step 3)

### 4.1 Verdad definition

Traditional value fails. Verdad anchors "value" to **cumulative spend**:

```
spend = revenue − cash_flow_from_operations
      ≈ all cash out the door (R&D + SG&A + everything)
```

**Value ratio:**

```
spend_value = market_cap / cumulative_spend
            (or inverse: spend / market_cap — lower mcap per dollar spent = cheaper)
```

Intuition: Company that spent $500M on trials is worth more than one that spent $10M **at the same market cap**. Assume constant ROI on spend (dumb but works in aggregate).

**Finding:** Spend value **outperformed specialist signal** in their attribution — because it gives a **time-varying rebalance anchor** (specialist counts move slowly).

### 4.2 Marvin implementation plan

| Step | Action |
|------|--------|
| 4.2.1 | Pull XBRL `Revenue` + `NetCashProvidedByUsedInOperatingActivities` from existing filing extracts |
| 4.2.2 | Compute TTM spend; maintain cumulative spend series per ticker |
| 4.2.3 | Store in `ownership/biotech_fundamentals.json` or extend `kpi_trends.json` |
| 4.2.4 | Rank spend_value within biotech quant universe quarterly |
| 4.2.5 | Surface in biotech tab column + optional `[Assumption]` row in deep dive overlay |

**Not for base IRR** without human review — pre-revenue names break Lawrence math.

---

## 5. Insider signal (Step 4)

### 5.1 Verdad rules

| Rule | Detail |
|------|--------|
| Use **buys only** | Sells are routine (option exercises, 10b5-1) |
| **Downweight CEO buys** | CEOs buy for optics; weak signal |
| **Upweight CFO + non-CEO exec** | CFOs bearish; buys meaningful |
| **Count-based** | Not dollar size (avoid "$ rich person" bias) |
| **Horizon** | Predictive for **months**, not days |
| **Mechanism** | Livelihood bet, not "beat next quarter" |

### 5.2 Marvin implementation plan

| Step | Action |
|------|--------|
| 5.2.1 | Filter Form 4 ingest to open-market **P** purchases |
| 5.2.2 | Tag role: CEO / CFO / other officer / director |
| 5.2.3 | Score: `insider_buy_count_90d` excluding CEO; bonus for CFO |
| 5.2.4 | Merge into biotech quant composite (weight TBD by backtest) |
| 5.2.5 | Already partial: `valuation.json#insider_signal` in memory — extend role split |

---

## 6. Short book construction (Step 5)

### 6.1 Verdad philosophy

- Biotech **fertile for shorts** (~60–70% of names lose money over time).
- **Dangerous** if concentrated (trial pop → annihilation).
- Most specialist funds **abandoned stock-level shorts** → hedge with XBI only.
- Quant approach: **70 weak names** not **7 high-conviction frauds**.

### 6.2 Verdad short factors

1. **Zero specialist ownership**
2. **Expensive on spend value** (high mcap / low cumulative spend)
3. **Negative cohort momentum**
4. **High short interest** (works sector-wide; borrow cost often eats edge)
5. **Position sizing + liquidity** caps

Short book purpose: **volatility dampening**, not alpha from being right on frauds. Can lose money on shorts net and still improve portfolio.

### 6.3 Marvin implementation plan

| Step | Action |
|------|--------|
| 6.3.1 | Add `short_interest` + `borrow_rate` from approved market data vendor |
| 6.3.2 | Compute `short_candidate_score` for quant universe |
| 6.3.3 | Dashboard: short watchlist tab (biotech only) — **no auto-stance in base IRR** |
| 6.3.4 | Milly adversarial: flag if Marvin long thesis overlaps high short score |

---

## 7. Momentum by indication / cohort (Step 6)

### 7.1 Verdad problem

Need to classify biotech companies that **change over time** (lead program shifts, phase changes, indication pivots).

### 7.2 Verdad solution

1. Aggregate **ClinicalTrials.gov** (or equivalent) data per company over time.
2. Build **time series of descriptors** (indication, phase, modality).
3. **Similarity graph:** each company vs all others → "most similar peer index."
4. Momentum = performance vs **similarity-weighted peer basket**, not single indication label.

Handles messy cases (Phase 3 Alzheimer + 10 preclinical oncology programs) without hand-labeling dominant indication.

### 7.3 Marvin implementation plan

| Phase | Deliverable |
|-------|-------------|
| 7.A | `biotech_clinical_profiles.json` — trial counts by phase/indication per ticker |
| 7.B | Similarity matrix (cosine on indication vectors) |
| 7.C | `cohort_momentum_12m` factor |
| 7.D | Theme cross-link to existing `theme_rankings` (obesity, mRNA, etc.) |

**Dependency:** trial data ingest (FDA/ClinicalTrials API or third-party).

---

## 8. Composite portfolio construction (Step 7)

### 8.1 Verdad process (inferred)

```
For each rebalance date t:
  1. Universe U_t = listed biotech ∩ liquidity floor
  2. For each name i ∈ U_t:
       s_specialist(i)  = f(consensus_count, density)
       s_value(i)       = g(spend_value)
       s_insider(i)     = h(insider_buys_non_ceo)
       s_momentum(i)    = m(cohort_return)
       s_short(i)       = short_interest, borrow, inverse specialist
  3. Normalize ranks → z-scores or percentile ranks
  4. Long score L(i) = w·s vector (weights from backtest / shrinkage)
  5. Short score S(i) = w'·s vector (different weights)
  6. Optimize: target net beta, sector neutrality optional, max name weight, min liquidity
  7. Rebalance monthly or on 13F drop + price drift threshold
```

### 8.2 Marvin v1 weights (proposal — backtest to confirm)

| Factor | Long weight | Short weight |
|--------|-------------|--------------|
| Specialist consensus | 0.35 | −0.40 |
| Spend value | 0.30 | −0.25 |
| Insider buys (non-CEO) | 0.10 | 0 |
| Cohort momentum | 0.15 | −0.15 |
| Short interest | 0 | 0.20 |

### 8.3 What Marvin publishes vs what Verdad trades

Marvin **does not** auto-trade. Outputs:

- Ranked long/short **candidate lists**
- **Stance hints** for `[HUMAN REVIEW]` on watchlist names
- **Memory claims** citing 13F + insider + spend
- Optional paper portfolio in `darwin_mandate.json` sleeve (future)

---

## 9. Enhancements in Verdad research pipeline (Step 8)

Items Verdad flagged as active research (not in v1 paper):

| Enhancement | Issue | Marvin ticket |
|-------------|-------|---------------|
| **PIPE / penny warrants** | Specialists often own via warrants not in 13F equity table | Parse 13D/G + warrant schedules |
| **Strategic pharma stakes** | Pfizer/JNJ equity stakes informative but messy | Tag `holder_type: strategic_pharma` |
| **13G/13D intra-quarter** | 13F stale | Optional Vicki scrape + event overlay |
| **Sector-level spend value** | Oncology vs dermatology spend norms differ | Subsector normalization |
| **AI classification** | Trial similarity at scale | Phase 7 similarity engine |

---

## 10. Rebalancing & turnover (Step 9)

### 9.1 Verdad

- Rebalance on **relative** value/risk among names, not event calendar.
- 13F signal **slow** — specialists can't exit small caps fast.
- Consensus names **lower vol / higher Sharpe** → fit risk-targeted portfolio.

### 9.2 Marvin cadence

| Trigger | Action |
|---------|--------|
| New 13F quarter filed | `make specialist-13f-ingest` |
| Weekly | Refresh prices + spend value ranks |
| On deep dive | Snapshot specialist count in assumption ledger |
| Monthly batch | `batch_portfolio_refresh.py` |

---

## 11. Validation & backtest plan (Step 10)

### 11.1 Minimum backtest (before Darwin sleeve)

1. Universe: biotech quant names with 5+ years 13F history (subset).
2. Long top quintile specialist consensus; short bottom quintile.
3. Add spend value long/short spread.
4. Report: CAGR, vol, max DD, turnover, 13F lag sensitivity.
5. Compare vs XBI buy-and-hold.

### 11.2 Live validation gates

- `validate_research_memory.py` — no relative evidence URLs; quant universe count > 0 after ingest
- `check_cross_checks.py` — third-party biotech letters vs specialist ownership
- Milly pass on any **long stance** driven primarily by quant overlay

---

## 12. Marvin file / script map

```
_system/reference/market-data/ownership/
  biotech_specialist_funds.json    # fund registry
  fund_cik_registry.json           # SEC CIKs
  records/{YYYYQn}.json            # holdings snapshots
  signals_latest.json              # quant signals (filtered universe)
  cusip_ticker_map.json            # learned CUSIP map
  biotech_fundamentals.json        # [planned] spend value inputs

_system/scripts/
  ingest_specialist_13f.py         # SEC ingest (portfolio-filtered today)
  build_specialist_13f_signals.py  # consensus + flow
  build_research_memory.py           # dashboard payload
  memory_common.py                   # is_biotech_quant_universe_ticker()
  build_biotech_spend_value.py       # [planned]
  build_biotech_insider_scores.py    # [planned]
  backtest_biotech_quant.py          # [planned]

dashboard/
  insights-viz.js                  # Biotech sub-tab
  data/research_memory.json        # quant signals surface

_system/proposals/
  verdad_biotech_quant_methodology_2026-07-09.md  # this file
```

---

## 13. Phased rollout

| Phase | Scope | ETA |
|-------|-------|-----|
| **0** | Fund registry + CIK + ingest | Done |
| **1** | Consensus signals + dashboard + quant universe gate | Done 2026-07-09 |
| **2** | Full-universe 13F (not portfolio-filtered) + specialist % rule | Next |
| **3** | Spend value factor from XBRL | Next |
| **4** | Insider role-split buys | Next |
| **5** | Short interest + borrow overlay | Later |
| **6** | Clinical trial cohort momentum | Later |
| **7** | Composite rank + paper portfolio | Later |
| **8** | Backtest + Darwin sleeve integration | Later |
| **9** | PIPE/warrant + 13D/G enhancements | Research |

---

## 14. Immediate next actions (post this plan)

1. Run `make specialist-13f-ingest && make research-memory` after quant universe filter.
2. Deploy dashboard (`skip_rebuild=true`).
3. Human: mark true biotech names on `biotech_watchlist` in registry for portfolio holdings that should stay visible.
4. Open Phase 2 ticket: ingest **all** 13F holdings from specialist funds, not only portfolio name matches.
5. Open Phase 3 ticket: spend value from existing filing extracts.

---

## 15. References

- Verdad Capital biotech paper (PDF — link in Buyside Digest show notes)
- [Buyside Digest podcast transcript](https://www.buysidedigest.com/podcast/investing-in-biotech-with-verdad-capital/)
- Marvin: `biotech_specialist_13f_2026-07-08.md`, `research_memory_ui_organization_2026-07-09.md`
- SEC 13F-HR InfoTable XML schema
