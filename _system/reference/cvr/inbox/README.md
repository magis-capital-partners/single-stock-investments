# CVR secondary-feed inbox

Drop screener CSVs here (AlphaRank M&A, special-sit exports, manual lists).  
The **Monday 15:00 UTC** Data Pipeline `cvr-discover` job runs:

```bash
python _system/scripts/refresh_cvr_universe.py \
  --discover --discover-non-sec-family \
  --sync-alpharank --ingest-inbox --create-stubs \
  --write-review --alert --skip-sync
```

Each `*.csv` is ingested then moved to `processed/YYYY-MM-DD_<filename>`.

## CSV contract (strict minimum)

| Column (any of) | Required | Notes |
|-----------------|----------|--------|
| `ticker` / `Ticker` / `symbol` / `Symbol` | **yes** | Equity symbol; rows without ticker are **rejected** |
| Match text | **yes** | Any cell containing `cvr`, `contingent`, `earnout`, `earn-out`, `ecip` **or** `cvr`/`has_cvr` = true/1/yes |

Optional: `company`, `consideration`, `notes`, `max_payout`, `outside_date` (ignored for sizing; useful for review notes).

Invalid / missing tickers are counted and skipped (do not fail the job).

## AlphaRank / Drive drop (optional)

Set one of:

| Name | Where |
|------|--------|
| `CVR_ALPHARANK_DROP_PATH` | GitHub Actions **variable** (folder or file on the runner / mounted path) |
| `ALPHARANK_CSV_PATH` | Local env for manual runs |

Weekly `--sync-alpharank` copies `*.csv` from that path into this inbox before ingest.

There is **no AlphaRank API key** in-repo today. Export CSV from [AlphaRank M&A screener](https://alpharank.com/ma_screener/) (or similar) into the drop path / this folder.

## Example

See `../examples/sample_screener_inbox.csv` (schema only — keep live drops in this folder).

## What happens next

1. Tickers land in `cvr_universe.json` → `pre_close_opportunities` as **context tier**.  
2. `--create-stubs` scaffolds `{TICKER}/research/cvr_terms.json` with `stub=true` (not sleeved).  
3. Review note under `_system/reviews/pending/cvr_discovery_*.md` (+ Slack if `SLACK_WEBHOOK_URL` set).  
4. Agent completes terms (`stub=false`, `terms_complete=true`) → nightly sync sleeves onto **CVRs**.  
