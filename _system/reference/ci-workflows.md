# CI workflows reference

Composite actions in `.github/actions/` are hidden implementation details. The Actions sidebar lists only `.github/workflows/`. Only the allow-listed operations surfaces (Deploy Dashboard, Letter Backfill, Podcast Refresh) expose a manual Run workflow choice; the governance tests reject any other.

## Production flow

```text
Data Pipeline
  ├─ 03:00 daily       intake + full deterministic rebuild
  ├─ 06:00 daily       activist sources
  ├─ 12:00 M/T/Th/F/S  light market/download refresh
  ├─ 10:00 Sun/Wed     full document harvest
  ├─ 14:00 daily       Drive intake
  └─ every 6 hours     portfolio news
             │
             ├─ successful downloads → Auto - Daily Research (≤1 research call)
             ├─ successful downloads → LS-algo Universe Intake (onboard + evidence)
             └─ successful downloads → Power Zone Universe
                                           │
                                           └─ committee_work change
                                                → Auto - Investment Committee
                                                → isolated task PRs (≤3 parallel)
                                                → automatic PR merge after quality
                                                → next committee stage
                                                → deterministic assembly

Relevant data commits → Deploy Dashboard
New tickers            → LS-algo Universe Intake (registry-driven onboarding)
```

Pushes made with `GITHUB_TOKEN` (every batch lane, and automerge's squash
merges) start no workflow run, so `on: push` fires only for human pushes. Main
itself is tested on a schedule: Research quality every six hours and Python
tests daily.

## Visible workflow ownership

| Workflow | Trigger | Responsibility |
|---|---|---|
| Data Pipeline | six separate schedules | Intake, activist, downloads, Drive, news |
| Auto - Daily Research | successful Data Pipeline download job | Admit one material evidence change |
| Auto - Research Queue | deep-dive or contract-backfill queue push | Serial onboard queue, or ≤3 parallel contract_backfill jobs |
| Research Agent Dispatcher | reusable only | Evidence manifest, token gate, research PR |
| Power Zone Universe | successful downloads; Monday fallback; authenticated API event | Canonical valuation route, contract, workbench, pricing, committee initialization (sole owner of the valuation pipeline) |
| LS-algo Universe Intake | daily 02:45; successful downloads; dispatch | LS-algo screener onboard, evidence recovery, registry derivatives |
| Auto - Investment Committee | committee packet/output change; 4-hourly sweep | Independent votes, conditional escalation, deterministic assembly |
| Auto - Agent PR Merge | agent PR events (cursor/, codex/, claude/); Research quality and Python tests completions | Gate one head SHA, verify every check on it, squash with `sha=` pinned; resolve allowed conflicts but never merge the resolved head in the same run (it needs CI re-triggered, and the PR says so) |
| Letter Backfill | Sunday 16:00 + manual | Two jobs: download PDFs→commit vault, then extract→rebuild insights (6h each); skips existing PDFs by size/sha |
| Memory Digest | Sunday 14:00 | Aggregate unpromoted [PROPOSED] bullets + corrections into one pending review |
| Deploy Dashboard | relevant push or successful upstream run | Validate and publish Pages |
| Deploy OAuth Proxy | OAuth source change | Deploy Cloudflare worker when configured |
| Research quality | research PR paths; pushes to main on judged paths; every 6 hours (:37 past 01/07/13/19 UTC) | Research lint (touched deep dives only; failures already on main are labelled inherited), graph invariants, fact-ledger currency, SSI tests, dashboard integrity; every job tests the exact commit |
| Python tests | changes to `_system/**`, `.github/**` and the few files the suites read; daily 05:23 UTC | pytest over `_system/trading` and `_system/scripts/tests`; undefined names and parse errors (ruff F821) |
| Filing Sentinel gold set | filing-sentinel paths | Gold-set validation, evaluator and workflow tests on a sparse checkout |
| CI bootstrap smoke | CI bootstrap paths | Sparse checkout and push-helper tests |
| LLM Workflow Governance | agent/workflow paths | Budgets, timeouts, retention, deprecations |
| Security - Weekly Code Scan | Sunday schedule | Sparse sequential Actions, Python, and JavaScript CodeQL |

GitHub-managed Dependency Graph and Pages build/deployment can also appear in the sidebar. CodeQL default setup is disabled; the bounded weekly repository workflow owns code scanning.

## Retired workflows

Deleted on 2026-09-24. Listed so nobody restores one by accident; the
governance test's retired list rejects the first three if they reappear.

| Workflow | Why |
|---|---|
| Darwin Portfolio Refresh (`darwin-refresh.yml`) | Disabled since 2026-08-23 after failing every run from 2026-08-11; its ticker payload is rebuilt nightly by Data Pipeline intake-full |
| YouTube Research Refresh (`youtube-refresh.yml`) | Needed a self-hosted runner, which on a public repo would run fork PRs on the workstation; the lane runs as a local scheduled task (`youtube_lane.py`) |
| Auto - IR Recovery (`vicki-ir-harvest.yml`) | Every run failed (last 2026-06-17), and nothing had written its trigger queue since 2026-06-11 |
| Auto - CI Repair (`ci-autofix.yml`) | Removed with the repository-health supervisor rework |

## Capacity limits

- All runner jobs declare a timeout of at most 300 minutes.
- Normal research has one concurrent call and the committee three.
- Full document harvest runs twice weekly; five other days use `--light`.
- CI and committee audit artifacts contain only ledgers and expire after seven days.
- Large jobs free runner disk before checkout. Pages, news, research selection, agent jobs, Python tests and automerge use sparse checkouts.
- Direct writers serialize through `data-commit-main`; agent outputs arrive through PRs.
- Governance tests reject manual triggers, missing/excessive timeouts, excess parallelism, long artifact retention, and deprecated wrapper files.

## Checkout profiles

| Profile | Materialized content | Use |
|---|---|---|
| `full` / `history` | full tree | operations that genuinely need the corpus |
| `minimal` / `marvin-agent` | `_system`, `.github` | agents and utilities |
| `news` / `marvin-pick` | base plus holdings research metadata | news and evidence selection |
| `darwin` / `dashboard` | base only; zero ticker trees | dashboard rebuild (no workflow uses `darwin` since darwin-refresh.yml was deleted) |
| `pages` | `_system`, `.github`, `dashboard` | deploy-only |

Sparse ticker paths are applied once with `git sparse-checkout set --stdin`. Darwin/dashboard profiles have a hard cap of 200 extra paths.

For a pull_request run, `ci_resolve_checkout_ref.sh` resolves `refs/pull/N/head`, not the head branch, which automerge deletes on merge.
