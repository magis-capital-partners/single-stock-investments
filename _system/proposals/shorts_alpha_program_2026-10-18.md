# Shorts alpha program: raising net alpha in the short-selling backtest framework

**Date:** 2026-10-18
**Status:** proposal; nothing below changes a production threshold, a live position or an order permission.
**Readers:** Drew; Michael (owns reverse-split strategy decisions and `decisions.jsonl`).
**Builds on:** `reverse_split_sample_expansion_2026-10-12.md` (universe and defects), `shorts_net_edge_v2_2026-10-15.md` (RSI-2.0 net-edge sizing), `_system/frameworks/reverse_split_short_process.md` (RSI-1.0), the published studies in `_system/data/reverse_splits/` (`expansion_summary.json`, `execution_research.json`, `portfolio_research.json`, `net_edge_research.json`).
**Code touched by the work below:** `_system/scripts/reverse_splits/` (research package), `_system/scripts/build_short_quant_screen.py` (signal definitions), `_system/scripts/build_reverse_splits_dashboard.py` and the Shorts tab.

## 1. The answer in six lines

1. **The framework is rigorous and the edge is real but small and starved.** The verified post-split trade (short the official opening auction of the session after a reverse split, cover at that session's close) returns **+2.8% gross** [95% issuer-clustered CI +2.1%, +3.5%] on 671 events and 545 issuers since 2018-05, positive 65% of the time. After quote-based costs it nets **+2.05% of gross exposure**. The $50k account replay turns that into a **0.28% CAGR** because it trades 115 times in 8.5 years and sits idle 95% of sessions.
2. **Alpha is being lost in four places, none of them the signal:** (a) about 60% of verified events (399 of 671) are discarded because Rule 201 (SSR) is modeled as "cannot trade" rather than "cannot hit the bid"; (b) capacity is capped at 0.1% of ADV with instantaneous fills against the displayed book, which makes tickets so small that 148 of the remaining 272 events fail the $100 minimum and the $1 commission minimum alone costs 0.4–1.7% on the rest; (c) only the one-day horizon is costed with real quotes, while the 5- and 20-session holds show 2–5x the median return but are only replayed with a daily-range spread proxy that the README itself calls uncalibrated; (d) the only event family is the reverse split, so the account has ~170 opportunities a year.
3. **Three things should stop:** the pre-split announcement-cohort intraday trade (RSI-2.0 measured mean gross edge +0.56% and net −3.8%; 3 of 307 names positive), the daily-range spread proxy as a basis for any account result, and treating the 27-framework qualitative review as a *backtest* requirement (it is unevaluable historically; keep it as a live-trade governance gate).
4. **The biggest levers, in order of confidence × impact:** execution and capacity realism (participation over time, auction participation for size, SSR-compliant passive fills); horizon and exit design with explicit tail control; breadth (a generic weak-microcap intraday fade baseline, dilutive-financing and deficiency-notice event families, a cross-sectional short panel); then conditioning, fee modeling and portfolio construction.
5. **Everything stays pre-registered.** A hypothesis registry, fixed time splits (train 2018-05 to 2022-12, validate 2023 to 2024, holdout 2025 to 2026-10 kept sealed until the end of the program) and the forward paper cohort as final arbiter. The number of hypotheses tested is reported with every result.
6. **Honest expectation.** Per-trade net edge from ~2% to 3–5% at one to five sessions; trade count 3–5x via SSR-compliant execution and modeled participation; a de-idled account via a second and third event family. At $50k and 2.5% per name the dollar P&L stays small whatever the alpha; the deliverable is a validated, costed, forward-tracked edge per event family that scales with capital, not a $50k equity curve.

## 2. Where we stand (measured, 2026-10-15 snapshots)

### 2.1 Gross price behavior, verified actions only

| Cohort (entry → exit) | n events | issuers | mean | median | positive | 95% CI (issuer clusters) |
|---|---:|---:|---:|---:|---:|---|
| ex+1 open → same close (h1, the primary) | 671 | 545 | +2.8% | +2.8% | 65% | [+2.1%, +3.5%] |
| ex+1 → 5 sessions (h5) | 665 | 541 | +4.9% | +7.7% | 68% | [+1.0%, +8.0%] |
| ex+1 → 20 sessions (h20) | 608 | 498 | +6.0% | +14.8% | 67% | [−0.7%, +11.3%] |
| ex close → h5 | 629 | 516 | +4.8% | +8.7% | 70% | [−0.2%, +8.6%] |
| ex+5 → h5 | 663 | 542 | +0.3% | +3.0% | 60% | [−2.3%, +2.7%] |
| matched controls, h1 (score >= 60, same SIC division, price × 2, $vol × 3) | 27 | 27 | subject +2.6% vs control +1.1%; excess +1.5% | | | excess [−2.5%, +5.4%] |

Reading: the one-day effect is tight and consistent in 2019 and 2021–2025 (+2.7% to +4.1% a year; 2020 was +0.9% on 26 events) but weaker in 2026 (+1.4% [−0.1%, +2.9%], n = 167). Longer holds carry more median return and a much heavier left tail: mean falls far below median because a minority of names squeeze (worst one-day gross −67%; expected shortfall at 95% −25% on the 671 standardized outcomes). The controls say a material part of the one-day return may be a *generic* intraday fade in weak low-priced names rather than a split-specific effect; the control sample is too small (27) to settle that.

### 2.2 What costs do to it (quote-based account replay, `all_close`, 2018-05 to 2026-10)

| Component | ROG |
|---|---:|
| Official open → official close benchmark | +3.59% |
| Timing: entering at the 1 s midpoint and exiting at the pre-close midpoint rather than the auction prints (a small benefit, so the auction is not a price lever) | +0.24% |
| Half spread at entry and exit (listing-venue quotes) | −1.16% |
| Walking the displayed book | −0.22% |
| Commission ($0.005/share, $1 minimum) | −0.40% |
| **Net** | **+2.05%** |

115 trades, 112 issuers, win rate 50%, profit factor 1.69, 2,012 of 2,125 sessions idle, CAGR 0.28%, Sharpe 0.54 on 0.5% annual volatility. The 2023+ subperiod nets +3.9% ROG (Sharpe 1.29, 85 trades); 2018–2022 nets −2.2% (30 trades). Removing the ADV cap (269 trades, filled against displayed depth at 1 second) turns the book negative: spread 2.3% and depth 1.1% exceed the 2.6% benchmark. A 5% quote stop improves the tail (ES95 from 21% to 14% of gross) at no cost to the mean.

### 2.3 Where the events go

| Drop | Count | Why it matters |
|---|---:|---|
| SSR observed at entry, no delayed-entry path | 399 of 671 verified one-day events (59%); 417 of 691 in the RSI-2.0 replay (60%) | Rule 201 only forbids executing at or below the national best bid. A passive offer, an auction order or an uptick execution is legal. The framework treats it as a hard skip. |
| Capacity: 0.1% of prior 20-session ADV, $100 minimum notional, 3 names | 272 → 115 trades (148 fail the $100 minimum, 7 whole-share or capital, 2 SSR at execution) | Tickets of $100–$1,250; commission minimum becomes 0.4–1.7% |
| Fundamental screen >= 60 | 671 → 39 events | Gross +3.1% [+0.2%, +6.0%] on 39: no detectable gain over the unconditional +2.8%. The screen was never fit to outcomes. |
| No historical borrow | strict cases = 0 trades | Flat 50/100/300% scenarios bracket a distribution whose current median is 8.8%/yr (p75 60%, p90 165%) with 29% of one-day names not quoted at all |
| OTC | 2,921 of 2,936 verified OTC actions unpriced | Not fixable for free; stays out of scope |

### 2.4 Data already in hand (all local, licensed where noted)

- Databento venue history 2018-05 → 2026-10 for XNAS.ITCH, XNYS.PILLAR, XASE.PILLAR: daily bars for **every** instrument including later-delisted ones, `status` (SSR flag, halts), `statistics` (official auction prints), 226 monthly `definition` snapshots. This is a complete listed-microcap universe with printed prices; `$0` on the current plan. Event-window `bbo-1s` for 671 events and `mbp-10` for 35; `trades`/`mbp-1` not yet pulled.
- EDGAR: 128,077 reverse-split filing accessions discovered (2005+), 60,618 parsed; the shared 4 req/s limiter, lifecycle classifier (proposal / board / scheduled / effective / cancelled) and availability clock already exist and are reusable for any filing-defined event.
- SEC companyfacts for 6,473 CIKs, filtered by `filed` date before extraction (true point-in-time).
- IBKR public borrow file archived every weekday since 2026-10-13 (~4,600 names/day with fee and quantity).
- FINRA short interest: **zero** real rows in the ledger (17,223 synthetic ADV-only rows). SEC fails-to-deliver, Reg SHO threshold lists and FINRA daily short-sale volume: not ingested. All four are free.
- Execution/cost model: matched-donor spread and depth forecasts (MAE 1.0% on entry half-spread), carry engine with settlement calendar (T+2/T+1), whole-share sizing, FINRA 4210 maintenance floors, squeeze stress scenarios.
- Forward protocol `reverse_split_intraday.v1` live since 2026-10-14: 28 registry events enrolled, 0 completed observations, awaiting broker evidence.

## 3. Why alpha is low, and what is not the problem

**Not the problem.** Point-in-time discipline, survivorship handling, issuer-clustered inference, the refusal to relax thresholds after inspection, the manifest/hash chain. Keep all of it; the plan builds on it.

**The problem is design scope.** The machine was built to test one hypothesis ("short the next session after a verified reverse split") under the most conservative executable assumptions, and it has answered that question: a small, consistent gross edge that tiny tickets and conservative fills consume. Nothing in the framework yet asks *which* names, *how long*, *how to get filled*, *how big*, or *what else* carries the same mechanism. That is where the alpha is.

Five binding constraints, with the lever that releases each:

| Constraint | Evidence | Lever |
|---|---|---|
| SSR modeled as exclusion | About 60% of events skipped | Model Rule 201-compliant execution (passive at the offer, opening auction, uptick) with fill probability from trade prints; test whether the SSR cohort's return differs |
| Capacity modeled as instantaneous displayed-book fills at 0.1% ADV | 115 trades; no-cap case negative | Participation over time (VWAP 09:30–10:30 at 1–2% of volume) priced from trade prints; auction entry; tiered commissions and passive rebates modeled explicitly |
| Only h1 is costed with quotes | h5 median +7.7%, h20 +14.8% replayed only with the range proxy | Quote-based exits at 2, 5, 10 and 20 sessions through the existing carry engine, with pre-registered tail rules |
| One event family, ~170 priced listed events a year | 95% idle sessions | Generic weak-microcap fade baseline; dilutive financing (424B5, 8-K 3.02, warrant inducements, ATM programs) and deficiency-notice (8-K 3.01) families; cross-sectional short panel |
| Selection is a fixed, unfitted 7-signal threshold | score >= 60 adds nothing measurable | Walk-forward conditional model on PIT features, with sizing by expected net edge and squeeze risk; the forward cohort validates it |

## 4. Design principles for the program

1. **Register before you run.** Every hypothesis gets an id, a cohort definition, horizon, exit rule, cost model, success metric and kill criterion written to a registry *before* the replay, extending the existing `plan.json` practice. Results that cite no registered id do not publish.
2. **Fixed time splits.** Train 2018-05 to 2022-12; validate 2023-01 to 2024-12; holdout 2025-01 to 2026-10 sealed (results computed but not displayed or read) until the program's final review. Issuer-clustered bootstrap intervals everywhere, as today.
3. **Count the hypotheses.** Each published result states how many hypotheses were tested in its family. A result needs t >= 3 (or its bootstrap equivalent) in validation, not 2, before it earns a forward cohort.
4. **Costs are measured, not assumed, wherever a quote exists.** The range proxy is retired as a basis for account results. Borrow stays an explicit scenario until the forward archive supplies dated fees; the scenario grid is replaced by the *archive's* fee distribution for the relevant population, not a flat 100%.
5. **Forward paper cohorts arbitrate.** A hypothesis that passes validation is frozen as a protocol version and enrolled in the forward ledger; the dashboard shows registered, validated and forward-tracked status per family.
6. **Mechanism before pattern.** Each family states the economic mechanism (forced issuance after a split, offering overhang, retail attention decay) and the falsifier. A pattern without a mechanism is reported but not promoted.
7. **Nothing touches the Gateway or ThetaData.** Prices and quotes from Databento (quoted before every pull, budgeted), filings from EDGAR, borrow from the public file. Unchanged.

## 5. Workstreams

### WS-A. Execution and capacity realism on the existing event (highest confidence)

*Mechanism:* the gross edge exists; the account result is a fill-model artifact.

- **A1. Opening-auction participation.** The benchmark already uses the official opening print, and the 1 s midpoint entry has beaten it by 0.24% ROG, so the auction is a *size and legality* lever, not a price lever. Replay entry as an auction order (MOO/LOO short; under Rule 201 the order must be priced above the bid, so model both the restricted and unrestricted forms) and quantify how often the opening-cross volume in `statistics` supports the modeled size at the printed price.
- **A2. Participation over time.** Pull `trades` and `mbp-1` for event sessions (ex+1, plus ex+2…ex+5 for WS-B) with a declared budget; price a 60-minute participation schedule at 1%, 2% and 5% of printed volume. Cost = realized VWAP minus arrival midpoint plus spread crossing fraction. This replaces "0.1% ADV or nothing" with a cost curve and lets the account size by expected cost, not a fixed cap.
- **A3. SSR-compliant fills.** For restricted sessions, simulate a passive offer at the NBO with a queue model fitted to `mbp-1` and prints; report fill rate, time-to-fill and adverse selection. Also report the *gross* h1 return of SSR-restricted versus unrestricted sessions; the direction is unknown and this is a pre-registered two-sided test.
- **A4. Commission schedule.** Model IBKR tiered (per share, $0.35 minimum, exchange fees, rebates for adding liquidity) beside fixed; passive fills from A3 earn rebates only when the fill model says they filled.
- **A5. Account design sensitivity.** Replay at $50k, $250k and $1M with the cost curve from A2 to show where the strategy's capacity actually ends. This is the number Drew needs to decide whether the sleeve is worth running.

*Done when:* a cost curve (bp vs participation) with intervals per year and venue; SSR-cohort gross return with CI; the account replay re-run on the train/validate splits with auction entry and participation fills; trade count and net ROG by split. *Kill:* if participation at 1% ADV costs more than the benchmark in validation, capacity really is the edge's ceiling and the program shifts weight to WS-C.

### WS-B. Horizon and exit design with tail control (high impact, medium confidence)

*Mechanism:* post-split selling pressure (index/ETF deletions, retail exits, covenant-driven offerings) persists for days; the risk is the squeeze tail.

- **B1. Quote-based multi-session exits.** Extend `portfolio_research` exit rules to close at session 2, 5, 10 and 20 with the carry engine (settled days, collateral rounding, the archive's fee distribution for the population instead of flat rates), real end-of-session quotes, and per-trade margin marks using the minute highs already collected.
- **B2. Tail rules, pre-registered.** Candidates: cover on a +X% move from entry using next-quote fills (X in {10, 20, 30}), cover on a halt resumption, cover when borrow quantity in the archive drops to zero (forward only), size by the squeeze stress already in RSI-1.0. Evaluate on train, choose at most one on validation, report the rest.
- **B3. Day-2 re-entry.** Many ex+1 covers at the close are followed by a further fade (ex+1 close → h1 +2.0% [+0.5%, +3.0%]). Test a two-session structure: cover at close, re-short at the next open if no SSR, versus hold overnight, with overnight gap risk measured on the venue bars.
- **B4. Per-share floors.** FINRA 4210 $2.50/share and house $5 minimums dominate margin for sub-$2 names; report ROM beside ROG so sizing uses the binding denominator.

*Done when:* a horizon × exit matrix on train and validate with net ROG, ROM, ES95, worst issuer, and holding-days; one pre-registered multi-session protocol frozen for the forward ledger. *Kill:* no horizon beyond h1 beats h1 on net ROM with ES95 inside the RSI-1.0 sleeve budget in validation.

### WS-C. Breadth: new event families on the same machine (largest pool, most work)

Every family runs the same pipeline the splits run today: EDGAR or price-based discovery → verification tier → event study (gross, clustered CIs) → quote-based costs → account replay → forward enrollment. One family at a time, each registered before its event list is built.

- **C1. Generic weak-microcap intraday fade (baseline, cheapest).** Universe: listed common/ADS from the `definition` snapshots, price under $5, prior 20-session dollar volume in the tradable range, no corporate action within 30 days. Trade: short the official open, cover the official close, next session after a day with (i) nothing, (ii) a −10% close, (iii) a +20% close. Purpose: establish the generic fade the controls hinted at (+1.1%), so every event family is measured as *excess over the fade*, and decide whether the fade itself is a tradable baseline. Mechanism reference: the intraday-versus-overnight return decomposition documented for retail-heavy and lottery-like stocks; verify against the literature before relying on it.
- **C2. Dilutive financings.** Events: 424B5 prospectus supplements pricing registered directs and public offerings, 8-K Item 3.02 unregistered sales, warrant inducement agreements, ATM program establishment (8-K 1.01 with an equity distribution agreement), S-3 effectiveness for shelf-less names. Clocks: EDGAR acceptance timestamp (press release timestamp when available). Mechanism: supply overhang and discounted pricing; the literature on seasoned offerings is long-run negative and the microcap version is acute. Hypotheses at h1, h5 and h20 from the first session after disclosure.
- **C3. Listing deficiency and delisting notices.** 8-K Item 3.01 (bid price, equity, market value notices; panel hearings; delisting determinations). Mechanism: forced action (reverse split or equity raise) within a known window. Also the natural *early* clock for the split family: measure whether shorting at the notice, with modeled borrow, beats waiting for the split.
- **C4. Going-concern first appearance.** EDGAR full-text search for "substantial doubt" in 10-K/10-Q, keyed to the first filing where the language appears for a CIK. Mechanism: financing need becomes public. h5 to h60 horizons; this is a slower, borrow-heavy family.
- **C5. Parabolic microcap reversal.** Day-after fade of names up more than 50% or 100% on the day on at least 10x prior volume, from venue bars, with SSR status (not restricted when up) and halt history. Mechanism: attention-driven overpricing and mean reversion; borrow is the binding constraint, so this family is forward-only for net results and relies on WS-E's archive.
- **C6. De-SPAC lockup and warrant windows; Russell deletions.** Lower priority; well-known, crowded, and dependent on reference data not yet in the repo.

*Done when (per family):* registered hypothesis, verified event ledger with denominators, event study with clustered CIs on train and validate, cost-adjusted account replay, excess over the C1 fade, and a go/no-go for forward enrollment. *Kill (per family):* validation excess over the fade not distinguishable from zero after costs, or capacity below $100k per year at 1% participation.

### WS-D. Conditioning: which names, how big

*Mechanism:* the split population is heterogeneous; the current threshold screen cannot separate the +15% medians from the −60% tails.

- **D1. Feature set, strictly PIT.** Split ratio and whether the ratio exceeds what regaining the $1 bid requires; pre-split price, market value and dollar volume; prior 5/20/60-session returns and realized volatility; prior-day move and SSR state; repeat-splitter cohort and days since the last split; shares outstanding growth over 1 and 2 years (`dei:EntityCommonStockSharesOutstanding`, the serial-dilution signal); cash runway, operating cash burn, debt to assets, accruals from the existing extractor; ATM/shelf capacity and a 424B5 within the prior 180 days (from C2); deficiency notice age (from C3); going-concern flag (from C4); FINRA short interest and days to cover (WS-E); fails-to-deliver and threshold-list membership (WS-E); borrow fee and quantity (forward only); market state (small-cap index 5-session return, VIX level).
- **D2. Model.** Regularized linear and a shallow gradient-boosted model, trained on the train split with issuer-grouped cross-validation, predicting gross h1 and h5 short return and the probability of a +50% adverse excursion. Report validation IC, decile spreads and calibration; promote only if the top-half/bottom-half spread in validation exceeds the cost of trading the bottom half. The existing score >= 60 screen is the baseline every model must beat.
- **D3. Sizing by expected net edge and squeeze risk.** Replace equal-size with the RSI-2.0 quarter-mean/second-moment rule using D2's forecasts, capped by the stress budget. Compare against equal size on validation only.
- **D4. Decay monitoring.** The 2026 weakening (+1.4% vs +3.4–4.1% in 2023–2025) is either composition, crowding or noise. Track the forward cohort's rolling 50-event mean against the validation interval; a breach is a review trigger, not a parameter change.

*Done when:* validation IC and decile table; a frozen model file (like `technical_model_v3.json`) with its feature list and training window; a sizing rule in the forward protocol. *Kill:* no model beats the unconditional +2.8% top-half selection on validation with t >= 3.

### WS-E. Borrow and positioning data (enables everything above)

- **E1. Keep the daily IBKR archive and widen it.** Archive all ~20k names, not only ledger names, so C1–C5 have fees from day one of their forward cohorts. Store quantity and fee; record "absent from file" explicitly (no inventory is a fact, not a missing value).
- **E2. Free positioning history, ingested once and then weekly.** FINRA consolidated short interest files (twice monthly, several years of history available); SEC fails-to-deliver (twice monthly since 2004); Reg SHO threshold lists (daily, exchange archives); FINRA daily short-sale volume files. These replace the ledger's synthetic ADV-only rows and give every event a positioning vector at entry.
- **E3. Fee model.** Fit a cross-sectional model of the archive's fee on price, market value, SI/float, days to cover, FTD quantity, threshold-list days, volatility and listing venue; refit monthly as the archive grows; report out-of-sample MAE. Use it as (i) a historical fee *covariate*, never an invoice, and (ii) a sensitivity replacing flat rates with the fitted distribution per name.
- **E4. Fee as a signal.** Pre-register: within each family, names in the top fee tercile (forward) or top predicted-fee tercile (historical) earn larger gross short returns but lower net returns; the shorting-premium literature predicts both. This decides whether the sleeve should avoid or seek expensive names.

*Done when:* positioning tables with coverage by year; fee model with OOS error; the strict-forward cohort nonzero for every active family. *Kill:* none; this is infrastructure.

### WS-F. Portfolio construction and risk

- **F1. Sleeve of families.** Combine the validated families with the RSI-1.0 budgets (name loss 0.5% under +200%, sleeve 2%, 3 names per family or a shared cap) and measure idle time, turnover, correlation of family P&L and the joint squeeze stress across families.
- **F2. Market exposure.** Measure each family's beta to a small-cap index over its holding window; if intraday fades are market-neutral by construction, say so with numbers; if multi-session holds carry beta, test a cheap hedge (small-cap index short) as a declared variant, not a default.
- **F3. Governance.** Drawdown and squeeze triggers that pause a family (not the sleeve) pending review; a monthly reconciliation of forward paper fills against modeled fills, which is the only real test of WS-A.

### WS-G. Validation protocol and infrastructure

- **G1. Hypothesis registry.** `_system/data/reverse_splits/hypotheses.jsonl`: id, family, declared_at, cohort, horizon, exit, cost model, metric, success and kill criteria, split, status. `check_reverse_splits.py --strict` refuses a published result whose hypothesis id is missing or declared after the result's build time.
- **G2. Split enforcement.** `portfolio_research` and `universe_study` take a `--split` argument; holdout outputs are written under `local/holdout/` and excluded from `publish` until an unlock entry is appended to the registry.
- **G3. Event-family generalization.** An `event_families` table and a family id on every event, disclosure and outcome so the replay, cost model and dashboard serve splits, offerings, notices and fades with one code path.
- **G4. Dashboard.** The Shorts tab gets a hypotheses board (registered / validated / forward-tracked / killed), per-family event studies with the fade baseline, and the forward ledger per family. Capacity curves from WS-A replace the single-account CAGR as the headline.
- **G5. Tests.** Each workstream lands with tests in `_system/scripts/tests/reverse_splits/` (170 today): registry enforcement, split sealing, fill-model invariants (no fill below the NBB under SSR, no fill beyond printed volume), carry-engine settlement cases, positioning ingest round-trips.

## 6. Hypothesis registry, initial entries

All horizons from the first session after the event is public. Gross returns are short returns. Success thresholds are on the **validation** split, issuer-clustered, with the hypothesis count stated.

| Id | Family | Hypothesis | Metric | Success | Kill |
|---|---|---|---|---|---|
| H1 | Split | SSR-restricted sessions have a different gross h1 return than unrestricted sessions | mean difference | either direction, t >= 3 | CI covers zero: treat as same population and trade both |
| H2 | Split | Passive offer entries under SSR fill at least 50% of the time within 15 minutes with adverse selection under 0.5% | fill rate, cost | both met | fill rate under 25% |
| H3 | Split | Participation at 1% of first-hour volume costs under 1.5% round trip | cost curve | under 1.5% | over benchmark |
| H4 | Split | Opening-cross volume supports the modeled order (order <= 5% of the cross) at the printed price in at least 80% of events, including SSR sessions | feasibility share | >= 80% | under 50% |
| H5 | Split | h5 net ROM with one pre-registered tail rule exceeds h1 net ROM | net ROM, ES95 | higher with ES95 inside budget | lower or ES95 breach |
| H6 | Split | ex+1 close → ex+2 close carries positive gross return not explained by the fade | excess over C1 | t >= 3 | not distinguishable |
| H7 | Fade | Sub-$5 listed names fade intraday on no-event days | mean gross h1 | reported, not promoted | n/a |
| H8 | Fade | Fade is larger after a −10% close than after a +20% close | difference | reported | n/a |
| H9 | Financing | 424B5-priced offerings carry negative abnormal h5 excess over the fade | excess | t >= 3 | not distinguishable |
| H10 | Financing | Warrant inducements and ATM establishment carry negative h20 excess | excess | t >= 3 | not distinguishable |
| H11 | Notice | 8-K 3.01 bid-price notices predict negative h20 excess with modeled fee under 50% | excess net | t >= 3 | fee-adjusted zero |
| H12 | Going concern | First "substantial doubt" filing predicts negative h20 excess | excess | t >= 3 | not distinguishable |
| H13 | Parabolic | +100% days on 10x volume fade next session; gross only until forward fees | mean gross h1 | t >= 3 | not distinguishable |
| H14 | Conditioning | A PIT model's top half beats the unconditional h1 mean | top-half mean minus all | t >= 3 | fails |
| H15 | Conditioning | Shares-outstanding growth over 2 years is the single strongest feature | rank | reported | n/a |
| H16 | Fee | Top predicted-fee tercile has higher gross and lower net h5 than the bottom tercile | both | both | neither |
| H17 | Portfolio | Two validated families reduce idle sessions below 50% at equal sleeve risk | idle share | yes | no |

## 7. Sequencing

| Phase | Weeks | Work | Done when |
|---|---|---|---|
| 0 | 1 | G1 registry and G2 splits; H1 and H7 measured from data already local (status flags, venue bars); expand matched controls to all 671 events without the score filter | registry live; SSR cohort and fade baseline numbers on train and validate; control n in the hundreds |
| 1 | 2–4 | WS-A: trades/mbp-1 pulls for 671 × up to 6 sessions under a declared budget; auction feasibility; participation cost curve; SSR passive fill model; tiered commissions; account sensitivity at three sizes (H2–H4) | cost curve and SSR fill results published; account replay rerun on train/validate |
| 2 | 3–6 | WS-B multi-session quote-based exits and tail rules (H5, H6); WS-E positioning ingests and fee model (E1–E3) | horizon × exit matrix; positioning coverage table; fee model OOS error |
| 3 | 5–10 | WS-C families in order C1, C2, C3, then C4/C5 (H8–H13); WS-D model (H14–H16) once features from C2/C3/E2 exist | per-family event study, costs, go/no-go; frozen conditioning model or a documented null |
| 4 | 8–12 | WS-F sleeve construction (H17); G3/G4 generalization and dashboard; forward protocols v2 for every validated family | sleeve replay on validate; forward enrollment live for each validated family |
| 5 | end | Unseal holdout; final review; promote or kill per family | written review against the registry; nothing promoted on holdout alone |

Phases overlap by design; each is a lane that can run in its own worktree. Phase 0 is one session of work and is the highest information-per-hour step in the program.

## 8. Expected impact and what would make us stop

| Quantity | Today | Realistic after Phases 0–2 | Requires |
|---|---|---|---|
| Net edge per trade, h1 | +2.05% ROG | +2.5% to +3.0% | tiered commissions, passive fills, sizing by expected cost |
| Net edge per trade, best horizon | not costed with quotes | +3% to +5% ROM at h2–h5 if tail rule validates | WS-B |
| Trades per year under modeled capacity | ~14 | 50–80 | SSR-compliant fills, 1% participation |
| Idle sessions | 95% | under 50% | one additional validated family |
| Capacity of the split family at 1% participation | unknown | measured | WS-A2 |

Stop conditions for the program as a whole: the SSR cohort and the participation cost curve both fail (H1–H3), which would mean the only tradable version is the one already measured; or the fade baseline (H7) explains the whole split effect and itself does not survive costs, which would mean the mechanism is a general microcap pattern without a tradable form at our size. Either outcome is a result worth publishing on the Shorts tab.

## 9. Decisions needed

1. **Model Rule 201 as a price constraint instead of an exclusion** (WS-A3). This changes a conservative convention Michael set; the conservative path stays as a reported variant.
2. **Admit multi-session holds as research cohorts** (WS-B). RSI-1.0 is a five-session process; the intraday overlay is one day. A horizon matrix is research, not a rule change, but Michael should approve the cohorts before they are run.
3. **Data budget.** Databento `trades` and `mbp-1` for roughly 4,000 event sessions, quoted before pulling; propose a $50 cap. FINRA, SEC FTD and threshold lists are free.
4. **Account design.** Is $50k the deployable size, or a research proxy for a $250k–$1M sleeve? The capacity curve (A5) is computed either way, but the headline the dashboard shows should match the real intent.
5. **Scope of families.** Approve C1–C3 now; C4–C6 after the first three report.
6. **The 27-framework qualitative gate** stays a live-trade governance requirement and is removed as a backtest admission condition; historical results are labeled "screen-only" as today.
7. **Holdout seal.** Agreement that 2025-01 to 2026-10 results are not read until the final review, with the unlock recorded in the registry.

## 10. What is deliberately out of scope

- Pre-2018 pricing licences and OTC price history (no free source; the free universe is not yet exhausted).
- Options-implied signals for this universe (no listed options on most names); they belong to the larger-cap Short Alpha ledger, which this plan does not change.
- Any Gateway, ThetaData or broker connection. Forward paper fills continue to be imported as dated records.
- Changing RSI-1.0 thresholds. Every result here is a new version with a new registry entry.
