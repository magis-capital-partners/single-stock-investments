# LLM token governance

**Status:** authoritative workflow, 2026-07-18

Cursor agents are exception-handling judgment workers. Downloads, parsing, scoring, Power Zone routing, valuation workbenches, pricing, dashboards, queue construction, and committee assembly stay deterministic.

## Admission path

Every active Cursor consumer passes through `.github/actions/llm-gate/action.yml` and `_system/scripts/llm_call_gate.py`. The gate hashes the evidence, checks prior state, blocks unchanged evidence, enforces cooldowns and budgets, reserves the call before dispatch, and records the outcome in an append-only cached ledger.

| Consumer | Normal admission | Budget | Deterministic replacement |
|---|---|---:|---|
| Research coordinator | Material new evidence and an evidence manifest | 1 repo call/day; 1 ticker/day; 24h cooldown | downloads, indexes, extracts, valuation pipeline, dashboard |
| Investment Committee | A queued judgment role with a unique evidence hash | 5-call baseline; at most 9 after explicit escalation | proposer, evidence tribunal, valuation reconciliation, research-loop assembly |
| Vicki IR | Active IR gap after deterministic adapter failure | 2 repo calls/day; 1 ticker/day; 72h cooldown | reusable site adapter and ordinary downloader |
| CI Autofix | Repeated narrow code/test/schema failure with a stable signature | 2 repo calls/day; one signature/week | notify-only issue for platform, auth, permissions, transient and unclassified failures |

## Research workflow

`research-agent-dispatch.yml` is the only workflow allowed to invoke the Marvin action. Onboard, daily sync, manual deep dive, auto-pick, and batch modes all call this dispatcher. It selects one eligible ticker, builds a compact evidence manifest, and suppresses the agent when the same evidence was already processed. A completed agent stores `research/agent_run_state.json`; the next run must have a different evidence hash.

The agent receives the manifest in its prompt and is limited to source synthesis, conflicts, uncertainty, and narrative judgment. It must finish with `marvin_cloud_refresh.py`, which runs the deterministic pipeline and records completion state.

## Investment Committee workflow

The proposer is deterministic. Round one uses three independent reviewers plus one pre-mortem; the chair is the fifth and final baseline call. The system adds targeted research only when the evidence tribunal is insufficient and adds three second-round reviewers only when there is no two-vote majority, material score dispersion, or material return dispersion. This makes five calls the normal case and nine the hard maximum.

Power Zones remain authoritative for method selection. Committee agents review evidence and assumptions; they do not restore or write the deprecated Marvin valuation methodology. Deterministic reconciliation writes the canonical committee support artifacts, and capital authority remains human-only.

## IR and CI exceptions

Vicki must create or repair a reusable adapter, never perform an open-ended one-off harvest. A working adapter suppresses future calls until a new adapter failure or IR gap appears.

CI Autofix is notify-only by default. It dispatches only for test, code, or schema failures with actionable logs after the same signature repeats twice. Broad failures, duplicate signatures, large failure sets, and environmental failures do not receive an agent.

## Audit and operations

Pinned `@cursor/sdk` lockfiles and `npm ci` make dispatch startup reproducible and faster. Ledgers live under `.llm-state/<consumer>/ledger.jsonl` in Actions cache and are uploaded as run artifacts after admitted calls. Run `summarize_llm_ledger.py` over downloaded ledgers to produce JSON or Markdown call/suppression reports. Manual `force` exists for incident recovery, remains ledgered, and must not be used for routine rotation.

The legacy static CI rollout is fail-closed. Org installs must use `_system/ci_autofix/install_org_repos.ps1`, which copies the current policy, gate, ledger workflow, and pinned package.
