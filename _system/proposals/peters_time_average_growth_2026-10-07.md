# Time-average growth (Peters) — portfolio diagnostic, v1

**Date:** 2026-10-07
**Status:** built 2026-10-07. Panel is on Michael's portfolio scope (`#/michael`, positions). Drew, LS Algo, and the combined account do not render it.
**Source:** Ole Peters, *Optimal Leverage from Non-ergodicity*, SFI working paper 2009-02-004. Drive: `Papers / Santa Fe Institute Working Papers / 2009 / 09-02-004_optimal-leverage-from-non-ergodicity.pdf`.
**Surface:** Michael's sleeve only (`#/michael`). Not Drew, not LS Algo, not SPX, not the combined account. Not a valuation input.

## 0. Scope lock (2026-10-07)

v1 runs on Michael's residual book: the Magis account after ls-algo names and SPX / XSP are removed. That is the book behind `GET /api/v1/sleeves/book?owner=michael`, with `dashboard/data/sleeves_michael.json` as the offline fallback. The saved snapshot (2026-08-13) is 63 names, 49 long and 14 short, net about 94% of that sleeve's NAV and gross about 100%. Shorts are small in dollars next to the longs, so the mix is a long book with a short overlay. Peters' single-portfolio leverage still applies. The hedged-book withhold (net near zero, gross large) would not have fired on that snapshot.

Ten of those names are not USD (4 CAD, 4 EUR, 1 JPY, 1 MXN). They need a dollar total return before they enter the mix. LS Algo stays out, which is the same cut the sleeve already makes. The panel is rendered on the Michael tab, not on the shared Portfolio performance page.

## 1. Decision

Add one diagnostic that answers a single question:

> If the current stock mix were rebalanced every day, how fast does a reinvested dollar grow, and is today's scale already past the point where more leverage slows that growth?

The number is a property of a hypothetical constant-mix path. It is not broker NAV, not an investor return, not a target weight, and not a house value.

Peters' own section 4 is the scope fence. He derives optimal leverage under continuous rebalancing, zero costs, lognormal prices, known drift and volatility, and no extra charge for borrowing. He says those assumptions overestimate optimal leverage, and that a sensible real-world figure for a broad index sits nearer 1 than the textbook 1.54. v1 prints the textbook object with those caveats on the panel. It does not "correct" the formula into a recommended size.

## 2. What stays untouched

| System | Rule |
|---|---|
| `valuation.json`, universal contract, IC packet, `human_decision.json` | This artifact is not an input. `decision_authority.py` does not read it. |
| Legacy Lawrence IRR | No new row, no stance change. |
| Darwin champion / genetic / PPO weights | No feed. Darwin evolves our policies. This describes the current mix. |
| Magis / World Model strip | No forecast sentence. Predictability class stays off `P4_allocation`. |
| Order desk | No ticket, no proposed quantity. |
| IB Gateway | No socket. Prices come from Yahoo chart v8, the same fetcher as technicals. |
| NetLiquidation series | Do not run the formula on it. `performance.js` already records that NAV moves with deposits and withdrawals. Peters' process is self-financing: gains stay in, and wealth is not reset. |

Schema flags on every payload: `research_only: true`, `in_base_irr: false`, `authority: "none"`.

## 3. The object, in Peters' notation

He studies one risky portfolio plus a riskless asset. Leverage `l` is the fraction of wealth in the risky portfolio.

- `l = 0` is all cash.
- `l = 1` is fully invested in the risky portfolio.
- `l = 2` is borrowing one dollar per dollar of wealth and putting both in the risky portfolio.

For geometric Brownian motion the two averages differ by Itô's correction (his equations 8 and 11):

- Ensemble return (average across hypothetical paths): `μ`
- Time-average growth (what one reinvested account experiences): `⟨g⟩ = μ − σ²/2`

On the leveraged mix (his equations 16 and 17):

```
⟨g(l)⟩ = μ_riskless + l · μ_excess − l² · σ² / 2
l_opt  = μ_excess / σ²
```

`μ_excess` and `σ` belong to the risky portfolio at `l = 1`. The ensemble term rises in a straight line with `l`. The time-average term turns down because of the square. Differentiating and setting the slope to zero gives `l_opt`.

Two further objects from the same section, shown as context, never as a countdown:

- Characteristic time (equation 13), the scale on which the growth trend is as large as the noise: `t_c = σ² / (μ − σ²/2)²`. For his S&P illustration (`μ_excess = 0.05`, `σ = 0.18`, riskless `0.05`) this is between 4 and 5 years. He says comparisons of similar portfolios are meaningful only on much longer scales.
- Critical leverage `l_c` (equation 19), where `⟨g⟩` is zero. Above it the time-average growth is negative. At it, `t_c` is infinite: the path is noise for as long as you watch.

v1's risky portfolio is **the current stock mix**, scaled so the stock weights sum to 1. Today's net stock weight is the `l` we are actually running. We do not search for a different mix. Peters notes that the growth-optimal portfolio of all possible portfolios sits on the efficient frontier; building that frontier is a later project and is out of this plan.

## 4. Headline versus annotation

Drift estimated from a year of daily returns is too noisy to identify `l_opt` for ordinary equity volatility. Peters' own `t_c` says so. The panel therefore has two layers.

**Headline, always, when the mix can be built.** These are sample facts about the hypothetical path. They do not require a forward drift.

| Field | Definition |
|---|---|
| Ito drag | `l_now² · σ² / 2`. The gap between the ensemble return and the time-average growth at the scale we are running. Depends on volatility and scale, not on the estimated drift. |
| Empirical growth | `252 × mean(ln(1 + r_t))` on the constant-mix daily simple returns defined below. |
| Empirical ensemble | `252 × mean(r_t)` on the same series. |
| Empirical gap | Ensemble minus growth. A check on the Ito drag. They match closely when the mix looks like his diffusion; a wide disagreement is shown, not hidden. |

**Annotation, model, often unidentified.** `l_opt`, `l_c`, and `t_c` from equations 17, 19, and 13, using the estimated excess drift of the fully invested mix.

Status of the annotation, and only this status:

| Status | Rule |
|---|---|
| `past_peak` | The whole drift band (estimate ± one standard error) puts `l_opt` below `l_now`. Even the high drift says today's scale is past the peak. |
| `room` | The whole band puts `l_opt` above `l_now`. |
| `unidentified` | The band straddles `l_now`, or `t_c` is longer than 3 years, or fewer than 252 sessions. Show drag and empirical growth. Do not print a scale suggestion. |

Standard error of the annualized mean log return is `σ / sqrt(N)`, with `σ` treated as known. That is the band on the drift. There is no second window on the panel. A 3-year estimate may be stored in the parameter file for a later sensitivity. It is not a second headline.

`l_opt` above 1 is labeled an upper bound: the derivation charges borrowing at the riskless rate and charges nothing to trade.

## 5. How the current mix is built

Wealth base is broker NAV, so weights are fractions of the same dollar the rest of the page uses.

Eligible position:

- `sec_type == STK`
- Adjusted-close history of at least 252 sessions
- A USD total-return series (local adjusted close times the FX rate when the listing is not USD)
- Finite positive prices, no zero-volume filter beyond what the Yahoo fetcher already drops

Everything else stays out: options, warrants, CVRs, futures. Their market value still counts in NAV, so it reduces the stock weight. They do not get a Peters row. A name that fails the history or FX check is listed under omitted and is left out of the mix.

Let `w_i` be signed stock market value over NAV (shorts negative).

- `l_now = Σ w_i` (net stock weight)
- Fully invested mix `v_i = w_i / l_now` when `l_now` is not near zero
- Daily simple return of the constant-mix book at scale `l_now`:

```
r_t = Σ_i w_i · R_i,t + (1 − Σ_i w_i) · r_f,daily
```

`R_i,t` is the simple USD total return of name `i`. Cash and the ineligible residual earn the riskless rate in this hypothetical. That is a model choice and it is printed in the lineage. It is not what the residual actually earned.

`σ` of the fully invested mix is the annualized sample standard deviation of its daily log returns (`ddof = 1`, 252-day year), matching the sample-variance comment already in `performance.js`. `μ` of that mix is empirical growth plus `σ²/2`, which is the inversion of equation 11. `μ_excess = μ − μ_riskless`.

If `|l_now| < 0.05` and gross stock weight exceeds 0.30, the book is hedged rather than a single long risky portfolio. Withhold book-level `l_opt`. Still show the empirical growth and Ito drag of the actual signed mix.

Per-name rows use the same formulas with that name as the only risky asset and `w_i` as its leverage. The row reads: this position, at its current fraction of NAV, rest of wealth in the riskless asset. It is not a instruction to hold the name alone.

## 6. Data

| Input | Source | Notes |
|---|---|---|
| Weights, NAV, side | `GET /api/v1/sleeves/book?owner=michael`, fallback `sleeves_michael.json` | Same book the Michael tab already shows. Drew and LS Algo are not read. |
| Prices | `fetch_yahoo_history` in `build_technical_signals.py` | Uses adjusted close (splits and dividends). Do not add a second Yahoo client. |
| FX | Yahoo `JPY=X`, `HKD=X`, `EURUSD=X`, and the other quote currencies already on the book | Wealth currency is USD. Missing FX omits the name. |
| Riskless rate | FRED `DGS3MO`, latest successful print | Continuously compounded `ln(1 + y)`. Stale rate is allowed and labeled with its date. No borrow spread in v1. |

Parameter file, rebuilt after the US close, not on a timer that touches the Gateway:

`dashboard/data/time_average_growth_params.json`

Per symbol: adjusted daily simple returns in USD for the trailing 252 sessions, plus `μ`, `σ`, `N`, start, end, currency, FX source. Shipping the return panel lets the worker build the covariance of whichever names are actually in the book. A diagonal "assume uncorrelated" volatility is not the headline. It may appear as a labeled sensitivity later. It is not in v1.

Universe is the stock symbols on Michael's sleeve. Do not estimate Drew, LS Algo, or the research list in `holdings.md`.

Refresh sits with the technicals/vol family. A failed Yahoo fetch keeps the previous symbol block and marks it stale. A stale block older than ten sessions is omitted from the mix the same way a missing block is.

## 7. Where it appears

One new section on the Michael tab, rendered from `dashboard/sleeve-viz.js` under the sleeve header. The shared Portfolio performance page is unchanged.

Title: **Time-average growth of the current mix**

First sentence on the panel, every time: this is a daily-rebalanced hypothetical of today's stock weights. It is not the NAV chart above it.

Book block:

- Ito drag, empirical growth, empirical ensemble, empirical gap
- `l_now`, gross stock weight, coverage (eligible stock NAV / NAV)
- Annotation status, and `l_opt` / `l_c` / `t_c` only when status is `past_peak` or `room`. When `unidentified`, the cells say why (`t_c` longer than 3 years, or the drift band straddles today's scale).
- Lineage button in the same pattern as the NAV chart: source paper, equation numbers, riskless series and date, window, omitted names.

Position table under the book block, eligible stocks only:

| Column | Meaning |
|---|---|
| Weight | `w_i` |
| Ito drag | at that weight |
| Empirical growth | name alone, rest of wealth riskless |
| Status | the same three-way rule |

No default change to the main positions grid. This table lives in the performance section so it cannot be read as a broker blotter.

Copy that must not appear on the panel: "target weight", "fair value", "buy", "sell", "IRR", "house". A small lint list in the node test scans the rendered headings.

If coverage of eligible stocks is under 50% of NAV, the book block shows the coverage fact and withholds `l_opt` even if the band would otherwise identify. Per-name rows for eligible stocks still render. A book that is mostly options is not a Peters portfolio.

## 8. Code layout

| Piece | Path | Job |
|---|---|---|
| Formula | `dashboard/functions/_lib/time_average_growth.js` | Equations 11, 13, 16, 17, 19. Mix builder. Status rule. No I/O. |
| Endpoint | `dashboard/functions/api/v1/sleeves/time-average.js` | Reads Michael's sleeve book only, joins `time_average_growth_params.json`, returns the panel payload. |
| Estimator | `_system/scripts/build_time_average_growth.py` | Yahoo + FX + FRED. Writes the params file. Does not write the panel. |
| Fixture | `_system/scripts/tests/fixtures/peters_2009_fig1.json` | His figure-1 numbers: riskless 0.05, excess 0.05, `σ = 0.18`, `l_opt ≈ 1.543`, `t_c` between 4 and 5 years. Figure-2 check: `μ = 0.05`, `σ = 0.45`, growth `≈ −0.051`, `l_opt ≈ 0.247`, `l_c ≈ 0.494` at a zero riskless rate. |
| UI | `dashboard/sleeve-viz.js`, Michael only | Renders the endpoint when `owner === 'michael'`. Does not reimplement the formula. |
| Fence test | `_system/scripts/tests/test_time_average_growth_fence.py` | `decision_authority.py`, valuation builders, and Darwin weight writers do not reference the params file or the endpoint. |

The formula lives in one JS module because the weights are known only when the book is served. Python does not grow a second copy. The node test and the Python fixture test both lock the same JSON vectors.

## 9. Phases

### Phase 0 — lock the fence

Land this plan. Add the fence test first, red, asserting the valuation and Darwin paths do not import the new names. No panel yet.

### Phase 1 — formula and fixtures

Implement `time_average_growth.js` against the figure-1 and figure-2 vectors, the status rule, the hedged-book withhold, and the coverage withhold. Include a case where the drift band straddles `l_now` and the status is `unidentified` even though a point `l_opt` exists. Include a case where Ito drag does not change when the drift input changes.

### Phase 2 — parameter file

`build_time_average_growth.py` for the sleeve symbols and any book snapshot the script is given. Stale-on-failure behavior. A unit test with a canned Yahoo payload, no network. Confirm a non-USD name is converted before `μ` and `σ` are stored.

### Phase 3 — endpoint

Join live weights. Omit options. Emit omitted reasons: `not_stock`, `short_history`, `missing_fx`, `stale_params`. Book math uses the overlapping dates of the included names only. If overlap is under 252 sessions, book status is `unidentified` with that reason.

### Phase 4 — panel

The Michael-tab section described above. Browser check: Drew and LS Algo are unchanged; the new section states it is a hypothetical of Michael's current weights; a fixture book with his figure-1 parameters renders `l_opt` near 1.54 and `t_c` near 4.6 years.

### Phase 5 — stop

Do not add suggested weights, a frontier, a borrow spread, transaction costs, or a write-back into Darwin or the contract. Those are separate decisions. Peters already flags costs and borrow as reasons his `l_opt` runs hot. Folding them in silently would turn the diagnostic into a sizer.

## 10. Done when

- Michael's tab shows drag and empirical growth for that sleeve's stock mix, with lineage back to equations 11 and 16.
- `l_opt` appears only with status `past_peak` or `room`, and the panel says a value above 1 is an upper bound.
- Drew, LS Algo, and the account NAV table are unchanged.
- No valuation, IC, human decision, or Darwin weight file changes because this ran.
- The figure-1 fixture is a test, and it matches `l_opt = 0.05 / 0.18²` and a characteristic time between 4 and 5 years.
