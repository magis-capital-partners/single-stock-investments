# CI workflows reference

Composite actions in `.github/actions/` are hidden implementation details. The Actions sidebar lists only `.github/workflows/`; none of those workflows exposes a manual Run workflow choice.

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
             └─ successful downloads → Power Zone Universe
                                           │
                                           └─ committee_work change
                                                → Auto - Investment Committee
                                                → isolated task PRs (≤3 parallel)
                                                → automatic PR merge after quality
                                                → next committee stage
                                                → deterministic assembly

Relevant data commits → Deploy Dashboard
IR failure queue       → Auto - IR Recovery (≤2 parallel)
Repeated CI failure    → Auto - CI Repair (notify-first)
Dashboard add holding  → repository event → Auto - Onboard Ticker
```

## Visible workflow ownership

| Workflow | Trigger | Responsibility |
|---|---|---|
| Data Pipeline | six separate schedules | Intake, activist, downloads, Drive, news |
| Auto - Daily Research | successful Data Pipeline download job | Admit one material evidence change |
| Auto - Research Queue | queue file change | Serial queued research |
| Research Agent Dispatcher | reusable only | Evidence manifest, token gate, research PR |
| Power Zone Universe | successful downloads; Monday fallback; authenticated API event | Canonical valuation route, contract, workbench, pricing, committee initialization |
| Auto - Investment Committee | committee packet/output change | Independent votes, conditional escalation, deterministic assembly |
| Auto - Agent PR Merge | Cursor PR events | Wait for research checks, resolve allowed conflicts, squash merge |
| Auto - IR Recovery | IR queue change | Exception-only browser adapter repair |
| Auto - Onboard Ticker | authenticated dashboard event | Deterministic scaffold/download then gated research |
| Darwin Portfolio Refresh | weekly and Darwin code changes | Full Darwin data rebuild |
| Darwin Research Snapshot | weekday schedule | Compact Darwin research contract |
| Letter Backfill | Sunday schedule | Import letters and rebuild insights |
| Deploy Dashboard | relevant push or successful upstream run | Validate and publish Pages |
| Deploy OAuth Proxy | OAuth source change | Deploy Cloudflare worker when configured |
| Research quality (PR) | research PR paths | Prompt sync and research lint |
| CI bootstrap smoke | CI bootstrap paths | Sparse checkout and push-helper tests |
| LLM Workflow Governance | agent/workflow paths | Budgets, timeouts, retention, deprecations |
| Security - Weekly Code Scan | Sunday schedule | Sparse sequential Actions, Python, and JavaScript CodeQL |
| Auto - CI Repair | selected failed workflows | Notify; agent only for repeated narrow signatures |

GitHub-managed Dependency Graph and Pages build/deployment can also appear in the sidebar. CodeQL default setup is disabled; the bounded weekly repository workflow owns code scanning.

## Capacity limits

- All runner jobs declare a timeout of at most 300 minutes.
- Normal research has one concurrent call, IR recovery two, and the committee three.
- Full document harvest runs twice weekly; five other days use `--light`.
- CI and committee audit artifacts contain only ledgers and expire after seven days.
- Large jobs free runner disk before checkout. Pages, Darwin, news, research selection, and agent jobs use sparse profiles.
- Direct writers serialize through `data-commit-main`; agent outputs arrive through PRs.
- Governance tests reject manual triggers, missing/excessive timeouts, excess parallelism, long artifact retention, and deprecated wrapper files.

## Checkout profiles

| Profile | Materialized content | Use |
|---|---|---|
| `full` / `history` | full tree | operations that genuinely need the corpus |
| `minimal` / `marvin-agent` | `_system`, `.github` | agents and utilities |
| `news` / `marvin-pick` | base plus holdings research metadata | news and evidence selection |
| `darwin` / `dashboard` | base only; zero ticker trees | Darwin and dashboard rebuild |
| `pages` | `_system`, `.github`, `dashboard`, `docs` | deploy-only |

Sparse ticker paths are applied once with `git sparse-checkout set --stdin`. Darwin/dashboard profiles have a hard cap of 200 extra paths.
