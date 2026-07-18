# Automatic Actions operating model

GitHub Actions is an event-driven production pipeline, not an operator menu. Repository workflows must not expose `workflow_dispatch`; the dashboard's authenticated onboarding event is the only user-initiated entry point.

## Flow ownership

1. **Data Pipeline** owns intake, activist data, downloads, Drive intake, and news on separate schedules. The jobs remain separate so a slow download cannot consume another job's time allowance.
2. **Power Zone Universe** runs after a successful download stage, with a weekly fallback. It deterministically routes each company to its valuation method, refreshes Power Zones, and creates frozen committee packets.
3. **Auto - Investment Committee** starts from internal events when a committee packet or task output lands. It selects one pending company, runs at most three isolated raters in parallel, and advances again when their PRs merge. An hourly catch-up tick recovers missed or budget-deferred events. Deterministic assembly replaces an extra agent call.
4. **Auto - Daily Research**, **Auto - Research Queue**, and **Vicki IR Harvest** run only from material-evidence or queue events. The shared LLM gate suppresses duplicate evidence and enforces per-consumer budgets.
5. Dashboard, Darwin, letter, OAuth, quality, security, and CI repair workflows respond only to schedules or relevant file changes.

## Capacity guardrails

- Every runner job has `timeout-minutes`; no job can consume GitHub's six-hour ceiling by accident.
- Agent fan-out is capped at three committee calls, two Vicki calls, and one research call at a time.
- Committee and CI ledgers are the only ordinary Actions artifacts and expire after seven days.
- Large repository jobs use sparse checkout or the bounded workspace checkout profiles. Full rebuild jobs free runner disk before materializing data.
- Writer jobs share the `data-commit-main` concurrency lane. Research and committee agents write PRs instead of racing direct commits.
- Governance tests fail changes that restore manual runs, omit a timeout, exceed parallelism caps, retain artifacts too long, or resurrect deprecated wrappers.

The result is automatic back-pressure: new evidence creates queued work, gates admit only necessary judgment calls, and merged outputs trigger the next bounded stage without a human choosing a workflow or mode.
