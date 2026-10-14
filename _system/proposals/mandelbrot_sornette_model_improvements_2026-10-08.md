# Mandelbrot and Sornette on the dashboard models

Date: 2026-10-08. Research note. Not a new framework file.

## Status

Implemented the same day. The SPY error diagram (773 samples, 1996-01-17 through 2026-09-23, every tenth session after 750 closes) selected positive-bubble confidence of 40. That level caught 5 of 10 tested crashes and was in alarm on 3.5% of sample dates, so demotion is enabled. Live SPY on 2026-10-08 has positive confidence 40 and a critical-time dispersion of 189 trading days, so concentration is 0 and the market-path cap stays off. 1987 stays untested because SPY did not exist. Catalog: `_system/research/criticality_monitor/event_catalog.csv`. Diagram: `dashboard/data/criticality_error_diagram.json`.

## Scope

*The Misbehavior of Markets* (Mandelbrot) and *Why Stock Markets Crash* (Sornette) apply to market-path language and to how the sleeve summarizes risk. They do not revise Power Zone valuation, the universal valuation contract, company earnings nowcasts, or the respiratory KPI ladder.

Both books are cited here from their published arguments and from the dashboard's own criticality plan (`docs/criticality-flow-monitor-plan.md`, which points at chapters 5, 6, 7, and 9 of the local Sornette PDF). Neither book is filed under `research-vault/investment-wisdom/`.

## What already matches the books

Sornette's log-periodic power law is in production as `lppls-ensemble-v1`:

- Formula and Filimonov-style conditional linear solve in `_system/scripts/criticality/lppls.py`.
- Nested windows at 60, 120, 250, 500, and 750 sessions.
- Filters for oscillation count, amplitude, damping, and fit error.
- Positive and negative bubbles.
- Critical time reported as a 10th / median / 90th percentile range, with an explicit policy that the range is regime instability rather than a crash date.
- Universe of 24 market and sector symbols in `build_criticality_signals.py`. Research-only.

Adjacent, and easy to confuse with Mandelbrot: the Michael sleeve panel implements Ole Peters' time-average growth (`dashboard/functions/_lib/time_average_growth.js`). It already separates empirical time-average growth from the ensemble mean. The leverage objects still assume Brownian motion. The drag is sigma squared over 2. Equations cited are Peters 11, 13, 16, 17, and 19.

Drawdown is already a first-class risk object: NAV Calmar in `dashboard/functions/_lib/performance.js`, and the capitulation path. That matches Sornette's preference for drawdowns over a Gaussian daily value-at-risk. Do not add a bell-curve VaR module.

## Brief that was implemented

### Mandelbrot

| Idea | Where it bites | Behavior before this change |
|---|---|---|
| Noah effect. Discontinuities. A few days dominate cumulative variation. | Peters scale annotation | Sample sigma includes those days and still produces an optimal scale. |
| Joseph effect. Long memory. Variance does not scale with the square root of time. | `build_vol_metrics.py` (`spx_rv20` via sqrt(252)) and `performance.js` `annualisedVolatility` | One annualized volatility, no scaling check. |
| Mild z-scores understate clustered extremes. | `criticality/flow_stress.py` `_z_score` | Mean and standard deviation. Returns 0 below 10 observations. Vol metrics already publish a trailing percentile beside the z-score. |

A full multifractal trading-time model is a later research project. The operational slice is the Noah concentration flag and the scaling gap.

Noah gate, frozen in code: if the five largest absolute daily log returns account for more than half the sum of squared log returns in the sleeve window, set annotation reason `noah_concentration` and hide the scale (`show_scale: false`), the same way `annotationStatus` already hides the scale for a short window or a long characteristic time.

Scaling gap, now beside the annualized number: 20-session realized vol divided by 1-session realized vol, compared with the square root of 20. The annualized series stays, with a label when the gap is large.

### Sornette

The unfinished piece of the book was the test, not another formula. `docs/criticality-flow-monitor-plan.md` specifies an error diagram (missed events versus time in alarm) and an event catalog from 1987 through 5 August 2024, plus calm controls. That catalog and the frozen cutoff are now in the repo. See Status above.

Darwin still marks macro stress on its own (`_system/scripts/darwin/regime.py`: VIX 28 stressed, VIX 22 or a 10-year yield at or above 4.5 adapting). `_system/scripts/predictability.py` now also demotes market-path claims to `P1_ecology` when the error-diagram gate is on: dominant SPY confidence at or above the frozen cutoff and critical-time concentration at least 25. Thesis KPI hygiene stays put. Market-path wording is the only ceiling that moves.

Two smaller Sornette additions, both shipped:

- On the criticality rail, each fit labels whether the current move sits inside the historical tail or outside it with a qualified log-periodic fit.
- The Bitcoin snowball (`build_hk_snowball_model.py`) remains a power law of price against time. The same LPPLS ensemble now sits beside that panel. A smooth power law and a log-periodic acceleration stay different claims, and neither enters Power Zone valuation.

## Order completed

1. Event catalog and error diagram for the ensemble that already ships.
2. Noah gate on the Peters panel. Research-only. No valuation input.
3. Scaling gap beside sqrt(252) vol on the vol strip and the NAV panel.
4. SPY criticality as a market-path demotion in `build_claim_boundaries`, using the cutoff the error diagram selects.
5. Trailing percentile in forced-flow stress.
6. Bitcoin ensemble beside the snowball.

## Boundaries

- Research-only. No path into `valuation.json`, base IRR, `human_decision.json`, or order authority.
- The Peters formula stays. The annotation hides when the Brownian summary is a poor description of the sample.
- Critical time remains a window.
- No new file under `_system/frameworks/`.
