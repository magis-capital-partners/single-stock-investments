# Darwin dual accounts — data architecture (simplified)

Design goal: **one batch job, four layers, two accounts**. No duplicate legacy paths. Tier 0 only until data and OOS gates justify ML.

## Mental model

```
Marvin (beliefs)  →  Features (curated)  →  Allocation (per account)  →  Serving (UI)
                         ↑                        ↑
                   research/valuation      paper marks (weights + NAV)
```

| Layer | What | Canonical path | Refresh |
|-------|------|----------------|---------|
| **L0 Input** | Registry, `valuation.json`, returns CSVs | `{TICKER}/research/`, `market-data/returns/` | Marvin refresh / download tier A |
| **L1 Curated** | Feature snapshot | `dashboard/data/darwin_features.json` | Once per `darwin-build` |
| **L2 Account** | Weights + backtest summary | `darwin_portfolio_{roth\|taxable}.json`, `{account}_target_weights.json` | Per account, same job |
| **L3 Paper** | Live book (weights + NAV) | `paper/{account}.json`, `paper/{account}_events.jsonl` | Per account, same job |
| **L4 Serving** | UI bundle only | `dashboard/data/darwin_serving.json` | Built last; **dashboard reads only this** |

## Accounts (config only)

Two JSON configs. Diff is intentional; everything else is shared code.

| Field | Roth | Taxable |
|-------|------|---------|
| File | `darwin_mandate_roth.json` | `darwin_mandate_taxable.json` |
| Rebalance | semiannual | quarterly |
| Max weight | 15% | 12% |
| Watch cap | 5% | 3% |
| Policy | `ira_marvin` | `ira_marvin` |

`tier: 0` means: **no** encoder, GA, PPO, ensemble, exploration, stress sim, or per-run question scaffolds.

## Single job

```bash
make darwin-build
```

DAG (idempotent):

1. `build_features()` → write `darwin_features.json` (once)
2. `rebuild_events_log()` + optional external sync (once)
3. For `account_id` in `[roth, taxable]`:
   - `ira_marvin` weights + walk-forward backtest
   - Write L2 artifacts
   - Update L3 paper (weights + NAV from **returns CSV**, not N×Yahoo)
   - Append one row to `paper/{account}_events.jsonl` if date or weights changed
4. `build_serving()` → `darwin_serving.json`
5. PIT audit (once, roth only)

## Paper contract (L3)

**State** (`paper/{account}.json`):

```json
{
  "account_id": "roth",
  "inception_date": "2026-06-03",
  "initial_nav_usd": 100000,
  "policy_id": "ira_marvin",
  "weights_pct": { "AMZN": 15.0 },
  "last_mark": { "date": "2026-06-03", "nav_usd": 100000, "cumulative_return_pct": 0.0 }
}
```

**Events** (`paper/{account}_events.jsonl`): append-only. `event` = `inception` | `mark` | `rebalance`.

NAV on each run: `nav *= (1 + Σ weight_i × last_monthly_return_i)` from `market-data/returns/{TICKER}.csv`. Missing CSV → weight excluded from return (logged in state).

## Backtest vs paper (what we compare)

| Track | Meaning | Trust for decisions |
|-------|---------|---------------------|
| **Backtest** | Historical sim with rebalance rules | Sanity check only until returns panel is long and real |
| **Paper** | Forward book from inception | Operational track record |

Do not treat in-sample backtest as OOS edge.

## What we removed (on purpose)

- Duplicate writes: `darwin_portfolio.json`, `ira_target_weights.json` (use `darwin_serving` + `roth_*` only)
- Third log file `*_adaptations.jsonl` (merged into `_events.jsonl`)
- Per-ticker Yahoo on every build (use returns vault)
- Per-account markdown backtest reports in Tier 0 (optional `darwin explain` later)
- ML stack in Tier 0 production path

## Extension ladder (later, not now)

| Tier | Add when |
|------|----------|
| 1 | Correlation cluster caps; full return CSV coverage |
| 2 | GA on `ira_marvin` knobs only + PIT OOS gate |
| 3 | PPO / encoder; ensemble in **lab** mandate only |

## Operators

| Command | Use |
|---------|-----|
| `make darwin-build` | Daily / after Marvin refresh |
| `make darwin-roth` | Roth only |
| `make darwin-taxable` | Taxable only |
| `make darwin-pit-check` | Leakage + build |

Human approves `{account}_target_weights.json` before real trades.
