# CVR secondary-feed inbox

Drop screener CSVs here (AlphaRank M&A, special-sit exports, manual lists).  
The **Monday 15:00 UTC** Data Pipeline `cvr-discover` job runs:

```bash
python _system/scripts/refresh_cvr_universe.py --discover --ingest-inbox --write-review --skip-sync
```

Each `*.csv` is ingested then moved to `processed/YYYY-MM-DD_<filename>`.

## CSV contract (minimum)

| Column (any of) | Required | Notes |
|-----------------|----------|--------|
| `ticker` / `Ticker` / `symbol` / `Symbol` | yes | Equity symbol |
| Any cell containing `cvr`, `contingent`, `earnout`, or `earn-out` **or** `cvr`/`has_cvr` = true/1/yes | yes | Row filter |

Optional columns are ignored but preserved in notes via filename.

## Example

See `../examples/sample_screener_inbox.csv` (schema only — keep live drops in this folder).

## What happens next

1. Tickers land in `cvr_universe.json` → `pre_close_opportunities` as **context tier**.  
2. A review note is written under `_system/reviews/pending/cvr_discovery_*.md`.  
3. They do **not** appear on the dashboard **CVRs** filter until `{TICKER}/research/cvr_terms.json` exists (Part 2 stubs / agent diligence).  
