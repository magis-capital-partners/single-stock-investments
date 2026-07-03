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

## CI bootstrap checkout (all jobs)

GitHub requires `actions/checkout` before any `./.github/actions/*` reference. Every job therefore uses this **three-step bootstrap** instead of a composite checkout action:

1. `jlumbroso/free-disk-space@main` (when disk pressure matters)
2. `actions/checkout@v4` with sparse paths: `ci_checkout_workspace.sh`, **`ci_resolve_checkout_ref.sh`**, `ci_sparse_checkout_paths.py` (all three required)
3. `bash _system/scripts/ci_checkout_workspace.sh <profile> [ref] [depth]`

Ref resolution lives in `_system/scripts/ci_resolve_checkout_ref.sh` — **never** pass `GITHUB_REF_NAME` directly to `git fetch`. On `pull_request` events GitHub sets `GITHUB_REF_NAME=228/merge`, which is not a fetchable branch; the resolver uses `GITHUB_HEAD_REF` (PR branch) or `pull/N/merge` from `GITHUB_REF`.

| Profile | Sparse paths | Typical use |
|---------|--------------|-------------|
| `full` / `history` | disabled (full tree) | lint diffs, onboard |
| `minimal` / `marvin-agent` | `_system`, `.github` | prompt sync, agents |
| `news` / `marvin-pick` / `darwin` / `dashboard` | base + ticker paths from `ci_sparse_checkout_paths.py` | portfolio jobs |

### Guardrails (avoid regressions)

| Change | Required follow-up |
|--------|-------------------|
| Edit `ci_checkout_workspace.sh` or `ci_resolve_checkout_ref.sh` | Run `bash _system/scripts/test_ci_checkout_workspace.sh` locally; **CI bootstrap smoke** runs on PR |
| Edit any workflow bootstrap sparse-checkout block | Run `python _system/scripts/lint_ci_bootstrap.py`; smoke workflow lint job catches missing resolver script |
| Add a new `pull_request` workflow using bootstrap checkout | Ensure it either relies on the resolver (no explicit ref) or passes `${{ github.head_ref }}` |
| Add a new sparse profile | Update `ci_sparse_checkout_paths.py` and document in this table |
| Replace bootstrap with a composite action | **Don't** — composites cannot run before the first checkout |

**CI bootstrap smoke** (`.github/workflows/ci-bootstrap-smoke.yml`) runs unit tests plus a live `minimal` checkout on every PR that touches bootstrap scripts or research-quality workflow paths.

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
| CI bootstrap smoke | PR/push bootstrap paths | No | No |
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
