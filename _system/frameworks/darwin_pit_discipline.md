# Darwin point-in-time (PIT) discipline

**Status:** Implemented in `_system/scripts/darwin/pit*.py`  
**Related:** `mark_date_alignment.md`, `darwin_portfolio_tab_proposal.md` §8

## Two modes

| Mode | CLI | Features | Champion weights |
|------|-----|----------|------------------|
| **Production** | `build_darwin_portfolio.py` | Latest Marvin | `ira_marvin` or gated ML |
| **PIT research** | `--pit-backtest` | Files dated ≤ rebalance + lag | OOS metrics only; does not change IRA targets |

## Rules

1. **Research:** `valuation.as_of`, `deep_dive_YYYY-MM-DD`, registry `onboarded` / `removed` must be ≤ rebalance date + `research_publication_lag_days`.
2. **Returns:** Only months ≥ rebalance; no `synthetic_irr_prior` in PIT fitness.
3. **Macro:** `macro_state_as_of(rebalance_month)`, not latest FRED month.
4. **ML:** GA/PPO train on in-sample rebalance windows; `ml_selected` requires OOS Sharpe and `pit_oos_min_periods`.
5. **Events:** `research_events.jsonl` drives purge/embargo around Marvin refreshes.

## Artifacts (tracking)

| File | Purpose |
|------|---------|
| `_system/portfolio/research_events.jsonl` | Append-only research refresh log |
| `_system/reference/market-data/pit/darwin_features_*.json` | Daily feature snapshots |
| `_system/reference/market-data/pit/registry_*.json` | Daily registry snapshots |
| `{TICKER}/research/valuation_history/valuation_{as_of}.json` | Valuation versions |
| `dashboard/data/darwin_pit_status.json` | Latest audit + OOS summary |
| `dashboard/data/darwin_pit_status_history.jsonl` | Time series for improvement tracking |
| `dashboard/data/darwin_backtest_pit.json` | Full PIT backtest output |

## Commands

```bash
python3 _system/scripts/build_darwin_portfolio.py --sync-events   # rebuild events log
python3 _system/scripts/build_darwin_portfolio.py --pit-audit   # leakage report only
python3 _system/scripts/build_darwin_portfolio.py --pit-backtest
python3 _system/scripts/check_darwin_pit.py
make darwin-pit-check
```

## Improvement loop

1. Each production build appends `darwin_pit_status_history.jsonl`.
2. Fix leakage flags in audit before trusting genetic OOS.
3. Extend `valuation_history/` when running `marvin_valuation.py --write`.
4. Add returns CSVs (Tier A) to remove thin panels.
