# Technical signal study

This study replays the dashboard's two technical signals over their full price history to measure how accurately and precisely each one predicts forward returns and risk:

- **Index capitulation ladder** (risk page): `build_capitulation_daily.py` on top of `criticality/flow_stress.py`, covering SPY, QQQ, IWM, the sector SPDRs and macro ETFs.
- **Per-stock fear model** (holdings "Fear / tape" column and the stock setup panel): `build_technical_signals.py`. It produces the panic / pressure / exhaustion scores (0–100), the capitulation states and the setup phases.

Findings, charts and the study plan are in [`results/report.html`](results/report.html), also published as a private artifact. In short:

- Panic works as a risk gauge, but the stock's own realized volatility predicts the same risk better.
- Panic's return edge is faint and short-lived, and it has faded to nothing since 2020.
- The exhaustion logic has no edge.
- The ladder's top rungs cannot fire on daily bars.

## What "point-in-time" means here

Every score is recomputed for every session from the data available at that session's close, exactly as the nightly job would have published it:

- **Ladder replay:** calls the production code directly. It was checked against all 31 rows the dashboard has published (`capitulation_daily_history.jsonl`).
- **Stock replay** (`fear_vec.py`): a vectorized re-implementation of `calculate_snapshot`. `parity_test.py` compares it with the production function on random (stock, date) snapshots. The first run matched 560 of 560 on every state, phase and confirmation.

## Running it

Price data and intermediates are about 2.5 GB, so they live outside git. They go under `./data` (git-ignored) or wherever `TECH_STUDY_DATA` points.

```bash
cd _system/research/technical_signal_study
python fetch_bars.py          # full-history Yahoo daily bars for the dashboard universe + index ETFs
python parity_test.py 60 10   # replay vs production calculate_snapshot (expect 0 mismatches)
python index_replay.py        # ladder + SPY "market fear" replay, every session
python index_analysis.py      # -> results/index_results.json.gz
python stock_batch.py 2       # per-stock replay + forward outcomes (2 workers; RAM is tight on the workstation)
python stock_stage1.py        # per-stock stats, bucket accumulators, events, thin panel (streaming)
python stock_stage2.py        # cross-sectional ICs, decile spreads, Fama-MacBeth with controls
python stock_stage3.py        # per-stock verdicts (circular-shift null, BH-FDR, shrinkage)
python stock_stage4.py        # state-entry event study, by market regime / era / drawdown
python report.py              # -> results/report.html
```

The scripts call only the public Yahoo chart endpoint the dashboard already uses. **No ThetaData and no IB Gateway** (see the repo `CLAUDE.md`).

## Conventions

- **Entry** is the next session's close; next-open and signal-close variants are also computed. Horizons are 1, 5, 10, 21, 63, 126 and 252 sessions.
- **Stock averages** use log returns. Excess means log return minus SPY's (or the local index's), with SPY spliced to the S&P 500 price index before 1993.
- **Exclusions:** a stock-day is dropped within ±252 sessions of a one-day move larger than 3×, which catches corrupt split adjustments. Scores are used only once a stock has a full 756-session percentile window.
- **Inference:** Newey-West errors (lags equal to the horizon) for overlapping windows; bootstrap by calendar month for events; circular-shift nulls plus Benjamini-Hochberg for per-stock tests.

## Known limitations

- **Survivorship:** the universe is today's dashboard, and Yahoo drops delisted histories, so positive "buy the fear" results are upper bounds.
- **Beta:** excess returns are against SPY, not beta-adjusted.

Both are addressed by the phase 5 work as it lands; see the report's study plan.
