# Index Inclusion / Exclusion: Research Synthesis

**Date:** 2026-07-01
**Author:** Marvin
**Purpose:** Distill the downloaded literature (`papers/`) and provider rulebooks
(`methodology/`) into facts, inferences, and design implications for a dashboard
feature that tracks potential and confirmed index membership changes.

This is a research summary, not an approved belief. Nothing here is promoted to
`_system/memory/MEMORY.md`.

---

## 1. What the literature establishes (facts)

1. **Index changes move prices even without new fundamental information.** Additions
   to the S&P 500 historically earned a permanent positive abnormal return and deletions
   a negative one (Shleifer 1986; Harris & Gurel 1986). The info-free TSE 300 float
   experiment reproduced this (Kaul, Mehrotra & Morck 2000), so at least part of the
   move is pure demand pressure, evidence that demand curves for stocks slope down.

2. **The size of the move depends on the size of the demand shock and the stock's
   substitutability.** Impact is larger for stocks without close substitutes (Wurgler &
   Zhuravskaya 2002), larger for smaller / higher idiosyncratic-risk firms, and the
   implied demand elasticity rises with firm size (Petajisto 2011).

3. **The response is asymmetric and partly about awareness.** Additions historically
   produced a permanent price rise while deletion declines were more temporary, consistent
   with an "investor awareness" channel: inclusion puts a firm on more radars, exclusion
   does not erase it (Chen, Noronha & Singal 2004).

4. **Inclusion is not a clean information-free event for the S&P 500.** S&P uses
   discretion (an Index Committee, an earnings-viability screen), and added firms show
   rising analyst EPS forecasts and realized earnings (Denis et al. 2003; noted by
   Chang, Hong & Liskovich 2015). This is why the **Russell 1000/2000 cutoff** is the
   cleaner natural experiment: rank-based, mechanical, value-weighted, so stocks just
   below rank 1000 get Russell 2000 buying while those just above get almost none
   (Chang, Hong & Liskovich 2015).

5. **Inclusion changes comovement.** After joining the S&P 500 a stock's return comoves
   more with the index and less with non-members (Barberis, Shleifer & Wurgler 2005),
   a "habitat / category" effect, not just a one-time price jump.

6. **Better predictor of impact than "% indexed" is Benchmarking Intensity (BMI).**
   BMI = a stock's cumulative weight across all benchmarks, weighted by the AUM tracking
   each benchmark, scaled by market cap. Larger BMI *changes* at reconstitution predict
   larger index effects and lower subsequent returns (Pavlova & Sikorskaya 2023). Both
   active and passive managers buy adds and sell deletes.

7. **The classic S&P 500 index effect has largely disappeared.** Average addition
   abnormal return: 3.4% (1980s) -> 7.6% (1990s) -> 5.2% (2000s) -> 0.8% (2010s, not
   distinguishable from zero). Deletions: -4.6% -> -16.6% -> -12.3% -> -0.6%
   (Greenwood & Sammon 2022). Drivers:
   - smaller add/delete size relative to total index cap;
   - much lower trading costs (bid-ask spreads down ~10x since early 1990s);
   - **migrations**: >80% of recent S&P 500 adds simultaneously leave the S&P MidCap,
     so S&P 500 forced buying is offset by MidCap forced selling (smaller net shock);
   - **predictability / front-running**: more of the total move now happens *before*
     the official announcement; a simple "largest eligible firm" rule increasingly
     predicts additions;
   - deeper, more concentrated liquidity provision around the effective date.

8. **Long-run inclusion effect may even be negative for the firm.** Post-2000, S&P 500
   inclusion is associated with worse price informativeness, some governance/ROA decline,
   and payout/investment policies converging to index peers (Bennett, Stulz & Wang 2020).

## 2. Inference for our process

- The tradeable one-shot "index premium" alpha is now small for large-cap S&P 500 events,
  **but the signal value of anticipating membership changes has grown**, because more of
  the price move now happens before the announcement and events are more predictable.
  A watchlist that flags candidates *before* the Street consensus forms is where the edge is.
- For our smaller / less-liquid / less-substitutable holdings (many are non-US, thin-float,
  or micro/OTC), the classic effect is more likely to still bite. Prioritize alerts by
  a proxy for demand-shock size: (float-adjusted) size of the move relative to ADV, and
  BMI change if obtainable, not just "is it going in the index."
- **Russell reconstitution is the most rules-based, calendar-driven event** and therefore
  the most forecastable (rank by total market cap on the last business day of April;
  banding of +/-2.5% around rank 1000). This is the best first target for a deterministic
  "proximity to cutoff" score.
- Distinguish **potential** (proximity to an eligibility boundary, pre-announcement) from
  **confirmed** (an index provider has announced an add/delete with an effective date).
  These are two different UI states with different confidence and different actions.
- Watch for **corporate-action deletions** (M&A, going-private, bankruptcy, failure to
  meet continued-listing / float / viability rules), not just size-driven ones. Deletions
  from forced selling can still be sharp for illiquid names.

## 3. Provider rules that the feature must encode (facts, refresh quarterly)

### S&P 500 (S&P DJI U.S. Indices Methodology)
Additions decided ad hoc by the Index Committee, typically announced a few business days
before the effective date. Addition eligibility (not continued membership):
- **Domicile / listing:** U.S. company on NYSE / NYSE Arca / NYSE American / Nasdaq.
- **Market cap:** unadjusted company market cap in the current S&P 500 band
  (reviewed quarterly; e.g. >= US$22.7bn as of July 2025, was US$20.5bn earlier in 2025).
  MidCap 400 and SmallCap 600 have their own bands.
- **Float:** float-adjusted market cap >= 50% of the index cap threshold; IWF >= 0.10.
- **Financial viability:** positive as-reported (GAAP) earnings in the most recent quarter
  AND summed over the trailing four quarters.
- **Liquidity:** annual dollar value traded / float-adjusted cap >= 1.0; >= 250,000 shares
  traded in each of the six months before evaluation.
- Migrations between S&P 500 / 400 / 600 are common and blunt the net demand shock.

### Russell (FTSE Russell US Indexes Construction & Methodology)
- **Rank day:** last business day of April (and October from 2026, semi-annual).
- Rank all eligible US securities by **total market capitalization**; largest 4,000 =
  Russell 3000E. Russell 1000 = top ~1,000; Russell 2000 = next ~2,000.
- **Banding** to cut turnover: an existing member near a breakpoint stays put unless it
  moves outside the band. Bands: +/-2.5% cumulative market cap around breakpoint #1000
  (also #200, #500); +/-0.5% around #2000; none at #50, #3000, #4000.
- **Effective:** after close on the 4th Friday of June (and 2nd Friday of December, 2026).
  Additions/deletions and shares/float published in advance (about 5 Fridays prior for June).
  A lockdown period precedes implementation.
- IPOs added quarterly; sizeable IPOs get fast entry.

### Others (deferred, note only)
MSCI GIMI (semi-annual index reviews, size-segment cutoffs, foreign inclusion factors);
Nasdaq-100 (annual December reconstitution, top non-financial Nasdaq names); FTSE, TOPIX,
STOXX for our international holdings. Not yet encoded.

## 4. Design implications (feeds the build plan)

1. Compute a per-ticker **eligibility scorecard** against S&P 500 and Russell cutoffs from
   data we already fetch (price, shares, float, market cap in `valuation.json` /
   `fetch_equity_prices.py`, plus GAAP earnings sign from filing evidence). Output a
   **distance-to-boundary** and a **status**: `member`, `inclusion_candidate`,
   `deletion_risk`, or `n/a`.
2. Rank candidates by an **impact proxy** (demand-shock size vs ADV; BMI change where
   available) so the dashboard surfaces the names where the effect is still likely to matter,
   consistent with Greenwood & Sammon and Pavlova & Sikorskaya.
3. Add an **`index_change` news category** so confirmed provider announcements (S&P DJI
   press releases, FTSE Russell notices) and reputable news become `refresh_eligible`
   events, flowing through the existing `insights.json` -> `events` pipeline.
4. Track a **reconstitution / rebalance calendar** (static config, dated) so the UI can
   show "next Russell recon: 4th Friday June" and count down.
5. Separate **potential** vs **confirmed** in the UI, with a confidence tag and a note that
   the average large-cap S&P 500 effect is now near zero, so the alert is primarily a
   watch / research trigger, not a mechanical trade.

## 5. Open questions for [HUMAN REVIEW]
- Which indices matter most for our universe (heavy in exchanges, royalties, non-US small caps)?
  Likely Russell 2000/1000, S&P 400/600, MSCI, plus home-market indices (TOPIX, FTSE, STOXX).
- Do we have (or want to license) benchmark AUM data to compute true BMI, or approximate it?
- Source of record for confirmed announcements: provider RSS/press pages vs Polygon/Google News.

---

## 6. Model validation — float-impact forced flow (2026-07-15)

Implements Horizon Kinetics *Russell 2000 Index Construction* (Jan 2013) axioms in
`_system/scripts/index_flow_impact.py` + `_system/data/index_aum.json`.

### Axiom check (APLD June 2026 graduation)

| Check | Result |
|-------|--------|
| Both sides modeled (R2000 sell + R1000/Midcap buy) | Pass |
| Microcap skipped for top-of-R2000 weight | Pass |
| Net flow negative (graduation ≠ inflow) | Pass |
| Low (ETF-observed) % of float | **−3.3%** (target −3% to −5%) |
| Base (ETF + index-fund est.) % of float | **−6.4%** |
| High (BMI ×1.75) % of float | **−11.4%** (scenario only) |
| HK weight-cliff ratio (sell demand / buy demand) | **~10×** |
| Within ±50% of observed ETF share-count estimate (~3% float from IWM+IWO+IWN+VTWO) | Pass on **low** tier |

### Other June 2026 cases

| Ticker | Event | Modeled note |
|--------|-------|--------------|
| APLD | R2000 → R1000/Midcap | Validated above; float_pct + ADV in `index_float_adv.json` |
| BE (Bloom Energy) | R2000 → R1000 (LSEG commentary) | Seeded approximate float; refine when exact float/ADV available |
| R1000 → R2000 demotion | Unit-tested synthetic | Net % float positive (buying), opposite of graduation |

### False-positive fix (2026-07-16)

Dashboard showed identical −6.4% / +7.1% blocks because style/subset headlines and a
broken portfolio-median breakpoint (~$86.5B) fed the calculator. Fixes:

| Gate | Behavior |
|------|----------|
| `style_subset` events (Top 50, Defensive, 2500, Value Benchmark, bare reclass) | `n_a` — no size-migration legs |
| Ambiguous `reclassify` without explicit R1000↔R2000 pair | `n_a` |
| `add` when seed already lists membership | `n_a` (`already_member`) |
| Inferred R2000 exit when membership unknown | only if mcap ≤ 4× breakpoint (~$22.8B) |
| Russell breakpoint | dated **$5.7B** in `index_rules.json` (LSEG June 2026), not portfolio median |
| Display | `~+X.X%*` muted when `float_unknown`; HK cliff badge only on genuine breakpoint + float_adj |

Post-fix: AMD/AMAT/AMP/CPRT/HE/WEST style rows → "—"; mega-cap R2000 candidates gone; APLD unchanged.

### Residuals / caveats

- Cap-weighted pure single-index adds share the same % of float (= AUM / index_total_mcap), independent of stock size. Rank top impacts by |$ flow| and prefer migrations / confirmed events. Asterisk display when float unknown.
- Index total mcap is total (not float-adj) from recon summaries → weights slightly understated.
- BMI high tier is scenario-only; default display is **base**.
- Unit tests: `_system/scripts/tests/test_index_flow_impact.py`, `test_index_event_extract.py`.
- Float/ADV refresh: `python _system/scripts/fetch_float_adv.py` (Yahoo primary, SEC shares fallback).
