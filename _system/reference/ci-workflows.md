# CI workflows reference

Shared logic lives in **composite actions** (`.github/actions/`) — these do **not** appear in the GitHub Actions sidebar. Only top-level workflow files in `.github/workflows/` are listed.

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
  ├─ optional: deploy-oauth composite action
  └─ publish-dashboard composite action

Agent workflows (open PRs)
  Marvin Deep Dive (modes: deep-dive | auto-pick | batch)
  Vicki IR Harvest
```

## Composite actions (hidden from sidebar)

| Path | Purpose |
|------|---------|
| `.github/actions/rebuild-data/` | Dashboard rebuild profiles |
| `.github/actions/commit-main/` | Push to main with rebase retry |
| `.github/actions/deploy-oauth/` | Wrangler OAuth proxy deploy |
| `.github/actions/publish-dashboard/` | Rebuild + validate + Pages deploy |
| `.github/actions/marvin-agent/` | Cursor SDK + deep dive |
| `.github/actions/vicki-agent/` | Cursor SDK + IR harvest |

## Visible workflows (~14)

| Workflow | Schedule / trigger | Commits main? | Chains deploy? |
|----------|-------------------|---------------|----------------|
| Daily Download & Dashboard Sync | 12:00 UTC, manual | Yes | Yes |
| Drive Intake Sync | :20 hourly, manual | Yes | Yes |
| Activist Scan Sync | 06:00 UTC, manual | Yes | Yes |
| Portfolio News Ingest | :30 every 6h, manual | Yes | Yes |
| Darwin Portfolio Refresh | Mon 12:00 UTC, push paths, manual | Yes | Yes |
| Deploy Dashboard (GitHub Pages) | push paths, manual, workflow_run | No | N/A |
| Deploy OAuth Proxy (Cloudflare) | push oauth-proxy, manual | No | No |
| Marvin Onboard Ticker | manual, repository_dispatch | Yes | Yes |
| Marvin Deep Dive | manual (3 modes), push queue | No (PR) | On merge |
| Vicki IR Harvest | manual, push queue | No (PR) | On merge |
| Research quality (PR) | PR paths | No | No |
| CI Autofix | workflow_run failures, manual | Maybe | No |
| CI Autofix Reusable | workflow_call only | — | — |
| pages-build-deployment | GitHub-managed | — | — |

## Marvin Deep Dive modes

| Mode | When to use |
|------|-------------|
| `deep-dive` | Single ticker (requires `ticker` input) |
| `auto-pick` | Pick holding with new docs; optional `force_rotate` |
| `batch` | Matrix from queue file or comma-separated `tickers` |

Queue file push (`_system/data/deep_dive_dispatch_queue.json`) auto-runs **batch** mode.

Daily auto-pick after download still runs inside **Daily Download & Dashboard Sync** (`marvin-refresh` job).

## Rebuild profiles

| Profile | Used by |
|---------|---------|
| `intake-full` | Drive Intake Sync |
| `activist` | Activist Scan Sync |
| `darwin-full` | Darwin Portfolio Refresh |
| `darwin-fast` | Deploy Dashboard (publish action) |

## Which workflow should I run?

| Task | Workflow |
|------|----------|
| Live site stale | Deploy Dashboard (GitHub Pages) |
| OAuth sign-in fails | Deploy OAuth Proxy, then Deploy Dashboard |
| Onboard new ticker | Marvin Onboard Ticker |
| Deep dive one ticker | Marvin Deep Dive → mode `deep-dive` |
| Auto-pick new docs | Marvin Deep Dive → mode `auto-pick` |
| Batch from queue | Marvin Deep Dive → mode `batch` (or push queue file) |
| IR gap harvest | Vicki IR Harvest |
