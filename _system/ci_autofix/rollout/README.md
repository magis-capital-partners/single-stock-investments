# CI Autofix rollout (ls-algo + etf-dashboard)

Prepared commits for repos the cloud agent cannot push to directly (`cursor[bot]` lacks write access to `GoldmanDrew/*`).

## Option A — apply script (recommended)

From a machine logged in as a user with push access:

```bash
gh auth login -h github.com
bash _system/ci_autofix/apply_rollout.sh all
```

Dry run:

```bash
bash _system/ci_autofix/apply_rollout.sh all --dry-run
```

## Option B — git bundle

```bash
git clone https://github.com/GoldmanDrew/ls-algo.git && cd ls-algo
git pull /path/to/single-stock-investments/_system/ci_autofix/rollout/ls-algo.bundle HEAD:main
git push origin main

git clone https://github.com/GoldmanDrew/etf-dashboard.git && cd etf-dashboard
git pull /path/to/single-stock-investments/_system/ci_autofix/rollout/etf-dashboard.bundle HEAD:main
git push origin main
```

## What's included

### ls-algo
- `risk_dashboard/tests/test_metrics.py` — bucket_5 sleeve count + fixture fixes (146 tests pass)
- `_system/ci_autofix/` — Magis CI Autofix package
- `.github/workflows/ci-autofix.yml` — triggers on Risk Dashboard, EOD PnL, Universe Discovery, Dashboard Recovery
- `.github/ci-autofix.yml` — repo notes for agents

### etf-dashboard
- `_system/ci_autofix/` + workflow/config (same pattern)
- Triggers on Build Data & Deploy Pages, Nightly, Market Hours, Deploy Pages safety net, Corporate Actions

## Required secrets (both repos)

Set at org or repo level after merge:

```powershell
gh secret set SLACK_WEBHOOK_URL --org GoldmanDrew --visibility all
gh secret set CURSOR_API_KEY --org GoldmanDrew --visibility all
```

Or per-repo if org secrets are not used.
