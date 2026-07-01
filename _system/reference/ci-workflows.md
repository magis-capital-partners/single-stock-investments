# CI workflows reference

All workflow **names and triggers are preserved**. Shared logic lives in composite actions and reusable workflows so behavior stays the same while deploy chaining and rebuild steps stay DRY.

## Architecture

```
Data pipelines (commit to main)
  Daily Download & Dashboard Sync
  Drive Intake Sync
  Activist Scan Sync
  Portfolio News Ingest
  Darwin Portfolio Refresh
  Marvin Onboard Ticker
        │
        │ workflow_run (success)
        ▼
Deploy Dashboard (GitHub Pages)
  ├─ optional: Deploy OAuth proxy (push or manual flag)
  └─ rebuild (darwin-fast) + validate + Pages deploy

Agent workflows (open PRs — deploy on merge via push paths)
  Marvin Deep Dive / Daily / Batch
  Vicki IR Harvest
```

## Shared components

| Path | Purpose |
|------|---------|
| `.github/actions/rebuild-data/` | Parameterized dashboard rebuild (`intake-full`, `activist`, `darwin-full`, `darwin-fast`) |
| `.github/actions/commit-main/` | `ci_push_main.sh` with `data-commit-main` concurrency |
| `.github/actions/marvin-agent/` | Cursor SDK + `marvin_deep_dive.mjs` |
| `.github/actions/vicki-agent/` | Cursor SDK + `vicki_ir_harvest.mjs` |
| `.github/workflows/_deploy-oauth.yml` | Wrangler deploy (reusable) |
| `.github/workflows/_publish-dashboard.yml` | Rebuild + validate + Pages deploy (single job) |
| `.github/workflows/_marvin-agent.yml` | Matrix-friendly Marvin wrapper |
| `.github/workflows/_vicki-agent.yml` | Matrix-friendly Vicki wrapper |

## Workflow capability matrix

| Workflow | Schedule / trigger | Commits main? | Chains deploy? |
|----------|-------------------|---------------|----------------|
| Daily Download & Dashboard Sync | 12:00 UTC, manual | Yes | Yes |
| Drive Intake Sync | :20 hourly, manual | Yes | Yes |
| Activist Scan Sync | 06:00 UTC, manual | Yes | Yes |
| Portfolio News Ingest | :30 every 6h, manual | Yes | Yes |
| Darwin Portfolio Refresh | Mon 12:00 UTC, push paths, manual | Yes | Yes |
| Deploy Dashboard (GitHub Pages) | push paths, manual, workflow_run | No | N/A (is deploy) |
| Deploy OAuth Proxy (Cloudflare) | push oauth-proxy, manual | No | No |
| Marvin Onboard Ticker | manual, repository_dispatch | Yes | Yes |
| Marvin Deep Dive | manual | No (PR) | On merge |
| Marvin Daily Deep Dive | manual | No (PR) | On merge |
| Batch Marvin Deep Dive | manual, push queue | No (PR) | On merge |
| Vicki IR Harvest | manual, push queue | No (PR) | On merge |
| Research quality (PR) | PR paths | No | No |
| CI Autofix | workflow_run failures, manual | Maybe | No |

## Rebuild profiles

| Profile | Used by | Steps |
|---------|---------|-------|
| `intake-full` | Drive Intake Sync | Full registry, PDF store sync, insights, memory, activist feed, dashboard data; optional docs mirror |
| `activist` | Activist Scan Sync | Registry, activist feed, dashboard data; optional docs mirror |
| `darwin-full` | Darwin Portfolio Refresh | IRA tier A+B, full Darwin build, dashboard data |
| `darwin-fast` | Deploy Dashboard | IRA tier A (best effort), Darwin fast, NOL screener, dashboard data, validate |

All rebuild profiles pass `OAUTH_CLIENT_ID` and `OAUTH_PROXY_URL` into `build_dashboard_data.py`.

## Concurrency

| Group | Workflows | Behavior |
|-------|-----------|----------|
| `data-commit-main` | All pipelines that push to main | Queue; never cancel mid-run |
| `dashboard-deploy` | Deploy Dashboard | Queue Pages deploys |
| Per-ticker / per-task | Marvin onboard, deep dive, batch, Vicki | Isolate parallel agent runs |

## OAuth setup

1. Deploy worker: `cd dashboard/oauth-proxy && npx wrangler login && npx wrangler deploy`
2. Set repo **variable** `OAUTH_PROXY_URL` (not secret) to the worker URL
3. Optional CI: secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
4. Deploy Dashboard bakes `exchange_url` into `dashboard/data/oauth_config.json`

Manual redeploy OAuth before dashboard: **Deploy Dashboard → Run workflow → check "Redeploy Cloudflare OAuth proxy"**.

## Daily timeline (UTC)

| Time | Workflow |
|------|----------|
| `:20` every hour | Drive Intake Sync |
| `:30` every 6 hours | Portfolio News Ingest |
| `06:00` daily | Activist Scan Sync |
| `12:00` daily | Daily Download & Dashboard Sync |
| `12:00` Monday | Darwin Portfolio Refresh (queues with daily sync via `data-commit-main`) |

## Which workflow should I run?

| Task | Workflow |
|------|----------|
| Live site stale after data commit | Deploy Dashboard (GitHub Pages) — should also auto-run via workflow_run |
| OAuth sign-in fails | Deploy OAuth Proxy, then Deploy Dashboard; verify `OAUTH_PROXY_URL` variable |
| Refresh all holdings PDFs | Daily Download & Dashboard Sync |
| Import Drive PDFs now | Drive Intake Sync |
| SEC activist scan only | Activist Scan Sync |
| News refresh only | Portfolio News Ingest |
| Darwin rebalance data | Darwin Portfolio Refresh |
| Onboard new ticker | Marvin Onboard Ticker |
| Deep dive one ticker | Marvin Deep Dive |
| Auto-pick ticker with new docs | Marvin Daily Deep Dive |
| Batch deep dives from queue | Batch Marvin Deep Dive |
| IR gap browser harvest | Vicki IR Harvest |
