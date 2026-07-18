# CI workflows reference

Shared logic lives in **composite actions** (`.github/actions/`) — these do **not** appear in the GitHub Actions sidebar. Only top-level workflow files in `.github/workflows/` are listed.

## Architecture (2026-07-18 token-governed consolidation)

```
Data Pipeline (single scheduled writer lane)
  ├─ 03:00 UTC  intake-full (nightly)
  ├─ 06:00 UTC  activist
  ├─ 12:00 UTC  downloads  ──► Daily Sync ──► Research Agent Dispatcher
  ├─ 14:00 UTC  drive intake (daily; skip rebuild if 0 imports)
  └─ :30 /6h    portfolio news
        │
        │ workflow_run (success)
        ▼
Deploy Dashboard (GitHub Pages) — deploy-only by default

Manual only
  Darwin Portfolio Refresh
  Legacy wrappers: Drive / Activist / News (emergency)

Agent admission (open PRs only after a shared gate)
  Research Agent Dispatcher, Investment Committee, Vicki IR Adapter, CI Autofix
```

## Composite actions (hidden from sidebar)

| Path | Purpose |
|------|---------|
| `.github/actions/rebuild-data/` | Dashboard rebuild via `ci_rebuild_profile.py` |
| `.github/actions/checkout-vault/` | Clone private `research-vault` |
| `.github/actions/commit-vault/` | Push letter corpus to vault |
| `.github/actions/commit-main/` | Push to main with rebase retry |
| `.github/actions/deploy-oauth/` | Wrangler OAuth proxy deploy |
| `.github/actions/publish-dashboard/` | Rebuild + validate + Pages deploy |
| `.github/actions/llm-gate/` | Evidence hashes, cooldowns, budgets, ledger reservation |
| `.github/actions/marvin-agent/` | Gated synthesis from a compact evidence manifest |
| `.github/actions/vicki-agent/` | Gated reusable IR adapter repair |

## CI bootstrap checkout (all jobs)

GitHub requires `actions/checkout` before any `./.github/actions/*` reference. Every job therefore uses this **three-step bootstrap** instead of a composite checkout action:

1. `jlumbroso/free-disk-space@main` (heavy profiles only: full tree, intake-full, darwin)
2. `actions/checkout@v4` with sparse paths: `ci_checkout_workspace.sh`, **`ci_resolve_checkout_ref.sh`**, `ci_sparse_checkout_paths.py` (all three required)
3. `bash _system/scripts/ci_checkout_workspace.sh <profile> [ref] [depth]`

Sparse ticker paths are applied with **`git sparse-checkout set --stdin`** (batched). Never loop `sparse-checkout add` per path.

| Profile | Sparse paths | Typical use |
|---------|--------------|-------------|
| `full` / `history` | disabled (full tree) | downloads, intake-full, activist |
| `minimal` / `marvin-agent` | `_system`, `.github` | agents |
| `news` / `marvin-pick` | base + **holdings-only** ticker paths | news / Marvin pick |
| `darwin` / `dashboard` | base only (`_system`, `.github`, `dashboard`, `docs`) | Darwin refresh |
| `pages` | `_system`, `.github`, `dashboard`, `docs` | Pages deploy-only |

`darwin` / `dashboard` must stay under **200** extra paths (`ci_sparse_checkout_paths.py --count`).

## Visible workflows

| Workflow | Schedule / trigger | Commits main? | Chains deploy? |
|----------|-------------------|---------------|----------------|
| **Data Pipeline** | multiple crons + manual job picker | Yes | Yes |
| Daily Download & Research Dispatch | daily / manual | No (gated research PR) | No |
| Darwin Portfolio Refresh | **manual only** | Yes | Yes |
| Drive / Activist / News | manual fallback only | Yes | Yes |
| Deploy Dashboard (GitHub Pages) | narrow push, manual, workflow_run | No | N/A |
| Deploy OAuth Proxy (Cloudflare) | push oauth-proxy, manual | No | No |
| Marvin Onboard / Research Dispatcher / Vicki | manual, daily, or queue | varies | On merge |
| Research quality (PR) | PR paths | No | No |
| CI bootstrap smoke | PR/push bootstrap paths | No | No |
| CI Autofix | upstream **failures ≥5 min** (not Deploy Dashboard) | Maybe | No |

## Rebuild profiles (`ci_rebuild_profile.py`)

| Profile | Alias | Used by |
|---------|-------|---------|
| `full` | `intake-full` | Data Pipeline nightly |
| `activist` | — | Data Pipeline / manual activist |
| `darwin` | `darwin-full` | Darwin Portfolio Refresh |
| `insights` | `pages-fast` | Deploy rebuild, Drive (when imports > 0) |
| `minimal` | — | light dashboard_data only |

**Removed:** `darwin-fast`.

## Deploy Dashboard speed model

| Trigger | Checkout | Rebuild | Typical runtime |
|---------|----------|---------|-----------------|
| `workflow_run` (chain) | `pages` | none | ~1–5 min |
| `push` (dashboard/docs only) | `pages` | none + validate | ~3–8 min |
| `push` (deploy scripts) | `pages` | `insights` | ~10–20 min |
| `workflow_dispatch` + skip rebuild | `pages` | none | ~3–5 min |

Mode selection: `_system/scripts/ci_dashboard_deploy_mode.sh`.

## Which workflow should I run?

| Task | Workflow |
|------|----------|
| Nightly full rebuild | Data Pipeline → `intake-full` (auto 03:00) |
| Drive PDFs | Data Pipeline → `drive` (auto 14:00) or Drive Intake Sync manual |
| Darwin refresh | **Darwin Portfolio Refresh** (manual) |
| Live site stale | Deploy Dashboard (skip rebuild) |
| Material evidence deep dive | Research Deep Dive Dispatch → Research Agent Dispatcher |
