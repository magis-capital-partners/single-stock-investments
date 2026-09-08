# Onboard New Stock

Use the **onboard orchestrator** (dashboard or CLI) — do not manually edit four files.

## Dashboard (cloud) — NOT WIRED UP

`marvin-onboard.yml` was deleted in `2fe5873e268` and no workflow dispatches
`onboard_ticker.py`. The **+ Add holding** button has no backing workflow.
Use the CLI below, or the CI batch path, until it is rebuilt.

### OAuth App setup (one time, repo admin)

1. [New OAuth App](https://github.com/settings/developers) — enable **Device Flow**
2. Copy **Client ID** → repo variable **`OAUTH_CLIENT_ID`**
3. Deploy CORS proxy (required): see `dashboard/oauth-proxy/README.md` → set **`OAUTH_PROXY_URL`**

## CLI (local)

```powershell
python _system/scripts/onboard_ticker.py --ticker TICKER --company "Name" --market US --ir-url "https://ir.example.com"
```

## GitHub Actions

The only live automated path is `ls-algo-universe.yml`, which onboards a bounded
batch off the LS-algo gap queue via `run_ls_algo_equity_onboard_all.py`. It takes
no ticker input — to onboard a specific name, use the CLI.

## Batch (local)

```powershell
python _system/scripts/batch_onboard_tickers.py _system/portfolio/onboard_batch_YYYY-MM-DD.json
```

## Watchlist only

```powershell
python _system/scripts/onboard_ticker.py --ticker XYZ --company "Name" --market US --watchlist-only
```

Promote from watchlist: dashboard watchlist chip → pre-fills form → submit with **from_watchlist**.

## Registry (source of truth)

`_system/portfolio/registry.json` — syncs to `holdings.md`, `classification.json`, `us_ticker_config.json`:

```powershell
python _system/scripts/sync_portfolio_from_registry.py
```

## Marvin checklist (automatic)

1. Scaffold folder (market template)
2. Register in `registry.json`
3. Run download (US/JP/EU/CA routing)
4. `build_folder_indexes.py` + `build_dashboard_data.py`
5. `_system/reviews/pending/{TICKER}_onboard_{date}.md`
6. Marvin deep dive via Cloud Agent (PR)

Do not write to MEMORY.md without [PROPOSED].
