# Onboard to research automation

**Status:** authoritative, 2026-07-18

## Onboard

Dashboard **+ Add holding** or manual `marvin-onboard.yml` scaffolds the ticker, downloads available filings and IR material, builds inventories/indexes, and refreshes dashboard data with deterministic Python. The onboard job does not invoke Cursor directly.

After collection, onboard calls `research-agent-dispatch.yml`. The dispatcher selects the ticker only when research evidence exists and the ticker is pending or materially changed, builds a compact stable manifest, and applies the shared LLM gate. Missing evidence, a previously completed evidence hash, cooldown, or budget exhaustion produces a successful no-op rather than an API call.

## Daily refresh

`daily-sync.yml` runs deterministic downloads and news ingest at 12:00 UTC, then calls the same dispatcher. The picker priority is:

1. onboard pending with ready evidence;
2. holding with no deep dive and ready evidence;
3. new primary documents;
4. valuation-relevant news.

Only one research call is admitted per repository day and one per ticker day. There is no automatic oldest-ticker rotation.

## Admitted cloud research

The agent receives the exact evidence manifest and handles synthesis, contradictions, uncertainty, and narrative judgment. It must finish with:

```bash
python _system/scripts/marvin_cloud_refresh.py TICKER --date YYYY-MM-DD
```

That deterministic close refreshes filing evidence, cross-checks, valuation compatibility artifacts, Power Zone routing, universal contracts/workbenches, pricing, committee eligibility, classifications, lint, and dashboard data. It also writes `research/agent_run_state.json` with the completed evidence hash so duplicate evidence cannot be reprocessed.

## Manual compatibility UI

`marvin-deep-dive.yml` retains deep-dive, auto-pick, and serial batch modes, but all modes call the shared dispatcher. `force` is reserved for an audited recovery from a broken state; it does not make routine refresh rotation token-efficient.

## Requirements and human gates

`CURSOR_API_KEY` is required only after admission. `POLYGON_API_KEY`, `RESEARCH_VAULT_CLONE_TOKEN`, and `HK_PDFS_ROOT` remain optional source enrichments. Without Cursor credentials, deterministic onboarding/downloads still finish, but an admitted research job reports the missing secret.

Humans still approve beliefs, source promotion, cloud PR merges, committee decisions, and any live capital action.
