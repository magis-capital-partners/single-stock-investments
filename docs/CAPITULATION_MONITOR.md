# Capitulation monitor

The capitulation monitor is a timing and risk overlay. It cannot change valuation
readiness, clear an evidence blocker, change stance, or modify intrinsic value.

## What the evidence says (technical-fear-v3, 2026-10)

A point-in-time replay of this model over every dashboard stock's full history
(1962-2026, 4.9M stock-days, parity-checked against the production code) is in
`_system/research/technical_signal_study/` (`results/report.html`). In short:

- **Panic, pressure and exhaustion measure fear accurately, but are weak timing
  signals.** Panic's cross-sectional IC with the next 21 sessions is about
  +0.03 since 1976, about 0 since 2020, and it reverses at one year. Nothing is
  left after trading costs or on the point-in-time S&P 500 since 2007.
- **Exhaustion has no edge.** Higher readings were followed by slightly lower
  returns, at the stock level and on 22 of 24 indices.
- **The v2 setup phases misled.** "Stabilizing" labelled 49% of all stock-days
  and matched the baseline exactly, and "falling knife" days did better
  afterwards than "stabilizing" days. Both are retired in v3.
- **Context matters.** Market-driven selloffs have held up better than
  company-specific ones, which have done no better than average. In large caps
  since 2007, stock-specific panics in a calm market kept underperforming.

The v3 changes were validated on a 2018-2026 holdout the design never touched.

## What was reused from the ETF dashboard

The stock dashboard reuses four price-path ideas that are already operational in
the ETF dashboard:

- historical percentiles beside absolute measurements;
- volatility concentration ratio (VCR), which separates a one-day jump from a
  persistent high-volatility path;
- daily-versus-weekly volatility shape (`trend_ratio_20d`);
- explicit data grades, coverage, timestamps, and last-good-data preservation.

ETF-specific borrow, leverage, rebalance-flow, and decay logic is intentionally
not imported.

## Scores

Every eligible security receives four scores from 0 to 100:

- **Pressure** — severity and persistence of the decline.
- **Panic** — whether price, volume/range, volatility, and relative weakness are
  becoming climactic.
- **Exhaustion** — whether the latest session shows stabilization after stress.
- **Confidence** — coverage of the independent signal families.

Panic is composed from four families:

1. price dislocation;
2. selling climax;
3. volatility stress;
4. relative and path stress.

The model uses up to three years of trailing observations when ranking the latest
reading. Family aggregation prevents correlated price measures from masquerading
as independent confirmation.

## State policy

States progress from `normal` to `stress_building`, `panic`,
`capitulation_candidate`, `exhaustion_emerging`, and
`confirmed_exhaustion`.

A severe decline is never sufficient for confirmation. A candidate needs broad
independent extremes plus a selling climax. Confirmation additionally requires
multiple stabilization checks, including a positive session, an upper-half
close, a reclaim of the prior high, or cooling volume.

## Market context

The dashboard calculates a separate SPY-based US market fear reading using the
same transparent price-tape model. CNN Fear & Greed is linked as an attributed
external reference and is never blended into stock scores.

## Plain-language setup

The primary ticker read is expressed in investment language instead of
z-scores. Setup **phases** are descriptive in v3:

- `company_selloff` / `market_selloff` -- the stock is in panic or worse, split
  by whether its 20-session move is mostly company-specific or explained by its
  beta to the benchmark (`context.company_move_20d_pct` vs
  `context.market_move_20d_pct`);
- `trend_intact` (leading uptrend), `oversold_watch` (RSI below 35),
  `indeterminate`.

The pillars:

- **Direction** combines price versus the 50- and 200-day averages with 60-day
  performance versus the market benchmark.
- **Pressure** uses RSI plus the panic/exhaustion model to distinguish oversold
  from an actual stabilization signal.
- **Participation** uses Chaikin Money Flow, relative volume, and ATR to show
  whether volume confirms accumulation or distribution.

## Outlook (v3)

`outlook` adds two calibrated, holdout-validated reads. Frozen coefficients are
in `_system/scripts/technical_model_v3.json`, fit on 1990-2017 and reported on
2018-2026:

- **`risk.p_drop15_63d`** -- probability of falling another 15% below today's
  close within 63 sessions. **`risk.expected_vol_21d_pct`** -- next-month
  volatility. Holdout: drop AUC 0.66 (panic alone 0.52); volatility R2 0.54
  (realized volatility alone 0.47).
- **`rebound.score`** -- a risk-adjusted rank (0-100) among US stocks of the
  expected next-month return after removing each stock's market (beta) part.
  Holdout: IC 0.04-0.045 vs 0.018 for panic, with the top tenth beating the
  bottom tenth by about 1.4% a month before roughly 1.2% round-trip costs. It
  leans to lower-beta names. It does **not** predict beating SPY in a rising
  market (raw SPY-relative IC about 0.01, not significant).

## Track record

`_system/scripts/build_signal_track_record.py` runs in the nightly technicals
job:

- **Logs** every published signal to `_system/data/signal_track_record/ledger/`.
  The first write wins, so the ledger is what was published.
- **Grades** each signal when its 5/21/63-session outcomes mature.
- **Publishes** `dashboard/data/signal_track_record.json`: the live record next
  to the study's backtest expectation for the same signal
  (`technical_signal_expectations.json`).

The stock panel and the risk-page ladder show it.

Trend and stretch z-scores remain in the technical payload for research and
model diagnostics, but they are no longer primary interface elements. Trend z
measures the stock's multi-horizon and benchmark-relative return versus its own
history. Stretch z measures distance from the 50- and 200-day averages versus
the stock's own history.

## Float and short interest

The free market-structure refresh collects float shares, shares outstanding,
reported shares short, short interest as a percentage of float, change from the
prior report, and days to cover. Each distinct report date is retained so the
dashboard and D1 build a history without overwriting prior observations.

Reported short interest is deliberately kept separate from FINRA daily
short-sale volume. Short interest is a position snapshot reported twice per
month; daily short-sale volume is transaction flow and must not be labeled as
short interest.

The integrated decision picture links modeled valuation, business/KPI momentum,
the stock's technical setup, and internal SPY market context. It can identify
agreement or conflict, but technical or macro inputs cannot clear evidence gates
or change valuation authority.

## Automation

The weekday technical job:

1. fetches free float and reported short-interest data;
2. fetches free adjusted OHLCV, using Yahoo first and Stooq as fallback;
3. preserves a last-good snapshot when sources fail;
4. writes compact and full dashboard artifacts, adding the v3 outlook in a
   post-pass that needs the whole universe (breadth and cross-sectional ranks);
5. logs and grades the published signals (track record);
6. publishes through the existing Cloudflare Pages deployment flow. Only the
   SPY market-context row is seeded to D1. The risk page treats a D1 flow row
   as "live" only if it comes from the intraday forced-flow model and is fresh.

Validation and recalibration live in `_system/research/technical_signal_study/`.
Re-run its replay before changing any threshold, weight or label here.
