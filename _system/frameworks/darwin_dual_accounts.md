# Darwin dual accounts — Roth IRA + taxable paper books

**Tier 0 production:** Marvin `ira_marvin` champion, no GA/PPO/encoder/ensemble exploration.

## Accounts

| Account | Mandate | Rebalance | Max weight | Output |
|---------|---------|-----------|------------|--------|
| **roth** | `darwin_mandate_roth.json` | Semiannual | 15% | `roth_target_weights.json`, `darwin_portfolio_roth.json` |
| **taxable** | `darwin_mandate_taxable.json` | Quarterly | 12% | `taxable_target_weights.json`, `darwin_portfolio_taxable.json` |

Paper state: `_system/portfolio/paper/{account}.json` + `{account}_history.jsonl` + `{account}_adaptations.jsonl`.

## Commands

```bash
make darwin-build          # both accounts + dashboard refresh
python3 _system/scripts/build_darwin_portfolio.py --account roth
python3 _system/scripts/build_darwin_portfolio.py --account taxable
```

## Dashboard

**Darwin** tab → switch **Roth IRA (paper)** vs **Taxable (paper)**. Each view shows:

1. **Backtest vs paper** — in-sample walk-forward cumulative return vs live paper NAV since inception
2. Target weights, regime, bias scan, benchmarks

## Adaptation loop

Each `make darwin-build`:

1. Refreshes Marvin features (shared)
2. Runs regime + `ira_marvin` per account mandate
3. Updates proposed target weights
4. Marks paper NAV (Yahoo daily closes)
5. Appends adaptation log when policy or weights shift materially
6. Appends scorecard row per account

## Legacy paths

- `darwin_portfolio.json` = copy of Roth build
- `ira_target_weights.json` = copy of `roth_target_weights.json`
