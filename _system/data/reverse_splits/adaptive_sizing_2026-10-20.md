# Adaptive short sizing experiment — 2026-10-20

Retrospective walk-forward research. No new data downloads, trades or capital authority.
The rules were declared before this run, after prior full-sample research; this is not an untouched holdout.

Training starts with 56 eligible events. Test: 2023-01-03 to 2026-10-13, 226 events, fixed $10m NAV.
Same-day only: dated multi-session exit depth is unavailable. Existing longer-horizon dashboard sensitivities remain separate.

## Bull cost sensitivity

Additional impact 0.0000% per side; uncovered cover shares are hypothetically priced 2.0000% above the worst observed ask. These are assumptions, not measured impact or verified fills.

| Policy | Trades | Mean notional | Net P&L | Added CAGR | Max DD | Calmar | MC median CAGR | MC 95% max DD | Covers with modeled residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $25k | 32 | $24,963 | $35,050.27 | 0.0927% | 0.0241% | 3.854 | 0.0916% | 0.0445% | 4 |
| Fixed $50k | 17 | $49,988 | $33,696.41 | 0.0891% | 0.1584% | 0.563 | 0.0904% | 0.3640% | 2 |
| Fixed $100k | 8 | $99,978 | $-14,112.18 | -0.0374% | 0.4538% | -0.082 | -0.0250% | 1.3540% | 1 |
| Cost-filtered sizing | 10 | $42,477 | $18,593.91 | 0.0492% | 0.0080% | 6.167 | 0.0486% | 0.0309% | 0 |
| Edge + cost sizing | 7 | $24,991 | $14,696.93 | 0.0389% | 0.0068% | 5.694 | 0.0379% | 0.0137% | 1 |
## Base cost sensitivity

Additional impact 0.2500% per side; uncovered cover shares are hypothetically priced 5.0000% above the worst observed ask. These are assumptions, not measured impact or verified fills.

| Policy | Trades | Mean notional | Net P&L | Added CAGR | Max DD | Calmar | MC median CAGR | MC 95% max DD | Covers with modeled residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $25k | 32 | $24,963 | $30,693.39 | 0.0812% | 0.0272% | 2.989 | 0.0803% | 0.0525% | 4 |
| Fixed $50k | 17 | $49,988 | $27,442.85 | 0.0726% | 0.1729% | 0.420 | 0.0747% | 0.4183% | 2 |
| Fixed $100k | 8 | $99,978 | $-21,490.90 | -0.0570% | 0.5034% | -0.113 | -0.0422% | 1.5142% | 1 |
| Cost-filtered sizing | 7 | $39,262 | $16,971.56 | 0.0449% | 0.0054% | 8.264 | 0.0443% | 0.0160% | 0 |
| Edge + cost sizing | 5 | $24,993 | $13,348.21 | 0.0353% | 0.0000% | Unavailable | 0.0350% | 0.0000% | 1 |
## Bear cost sensitivity

Additional impact 0.5000% per side; uncovered cover shares are hypothetically priced 10.0000% above the worst observed ask. These are assumptions, not measured impact or verified fills.

| Policy | Trades | Mean notional | Net P&L | Added CAGR | Max DD | Calmar | MC median CAGR | MC 95% max DD | Covers with modeled residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $25k | 32 | $24,963 | $25,992.98 | 0.0688% | 0.0307% | 2.239 | 0.0677% | 0.0638% | 4 |
| Fixed $50k | 17 | $49,988 | $19,731.21 | 0.0522% | 0.1954% | 0.267 | 0.0557% | 0.5165% | 2 |
| Fixed $100k | 8 | $99,978 | $-31,192.93 | -0.0827% | 0.5762% | -0.144 | -0.0649% | 1.7939% | 1 |
| Cost-filtered sizing | 3 | $33,315 | $6,509.00 | 0.0172% | 0.0000% | Unavailable | 0.0172% | 0.0000% | 0 |
| Edge + cost sizing | 5 | $24,993 | $12,755.24 | 0.0338% | 0.0000% | Unavailable | 0.0337% | 0.0000% | 1 |

## Interpretation

The base adaptive rule fills five $25k targets and earns less total modeled P&L than fixed $25k sizing. It does not demonstrate a portfolio-return uplift from fitting gross edge.
Five profitable admitted trades produce zero observed and resampled drawdown. That is not a credible estimate of unseen squeeze risk; Calmar is undefined.
All 226 test events remain in selection counts. Under the base adaptive rule, 194 lack full $25k entry depth inside the declared 3% limit and 27 fail the forecast net-edge buffer. Five are attempted.
The shared bootstrap now retains every boundary-month session. Omitting a partial final month could otherwise discard a real tail loss. This also corrects existing sleeve Monte Carlo calculations.

## Frozen protocol

- **version**: short_adaptive_sizing.v1
- **declared_on**: 2026-10-20
- **test_start**: 2023-01-03
- **test_end**: 2026-10-13
- **minimum_training_events**: 40
- **holding_sessions**: 1
- **nav**: 10000000
- **tickets**: (25000, 50000, 100000)
- **max_names**: 3
- **entry_squeeze_reserve_limit**: 0.1
- **net_edge_buffer**: 0.005
- **entry_limit_fraction**: 0.03
- **gross_ridge**: 32.0
- **gross_zero_prior_events**: 20
- **cost_neighbors**: 20
- **minimum_predicted_cover_support**: 0.5
- **features**: ['log entry midpoint', 'log prior 20-session venue dollar ADV', 'entry relative quoted spread', 'log reverse-split multiple']
- **training**: Expanding eligible-event history; only labels from strictly earlier sessions. No same-day labels, future covers or realized returns enter selection.
- **gross_model**: Ridge regression standardized using training data only, coefficients shrunk toward zero; pooled mean shrunk with 20 zero-edge pseudo-events. Gross labels are decision-midpoint to cover-midpoint short returns.
- **cost_model**: Entry decision-book sweep plus weighted 20-neighbor forecast of cover cost for the requested original shares. Censored prior covers retain explicit case-dependent residual-price assumptions; they are never silently dropped.
- **allocation**: Greedy descending expected net dollars, with alternatives reconsidered as the known entry reserve budget is used. Fixed-size policies use prior liquidity ordering. All share the same entry-book, issuer, three-name and 10%-NAV squeeze-reserve constraints.
- **entry**: Decide at open+1s. Require the full target within 3% of the midpoint; the IOC limit is the last bid needed in that decision book. Execute against the cached open+1.1s book, allowing partial/no fills.
- **cover**: Scheduled close-0.9s book sweep. Any residual shares receive a disclosed hypothetical price above the worst observed ask, with a case-dependent surcharge. These are modeled completions, not verified full fills.
- **risk**: 100% hypothetical house margin plus per-share floors; entry reserve is a +200% price loss plus 200% post-shock margin. Reported margin/stress use sums of individual observed intraday peak marks, a conservative envelope rather than a simultaneous account peak.
- **financing**: Same-session modeled closes are settled-flat: borrow and proceeds credit both zero. A delayed real cover could incur borrow and financing costs not measured here.
- **validation**: Retrospective walk-forward research designed after earlier full-sample inspection; parameters are not tuned to these test results. Prospective validation remains required.

## Limits

- Results depend on unverified borrows, hypothetical broker routing and displayed-book access.
- Missing cover depth is priced with explicit assumptions; it is not established executable net profitability.
- Extra impact and residual-cover surcharges are declared stress sensitivities, not measured calibration.
- Same-day test only. Multi-session exit costs remain unmeasured; no stop or profit target is used.
- Month bootstrap retains all boundary-month sessions and resamples the fitted policy P&L, without refitting the models or creating unseen squeezes.
- A handful of winning trades can produce zero observed and bootstrapped drawdown. That is not evidence of low tail risk.
