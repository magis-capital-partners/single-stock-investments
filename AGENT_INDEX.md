# Agent Index (read this first)

Entry map for Grok Bot, Muse, Cursor, and any other agent reading this repo
as context. Do not glob the 1,000+ ticker folders. Use the ladder below.

## The ladder

| Level | File | Budget |
|---|---|---|
| L0 portfolio | `dashboard/data/portfolio_summary.json` | < 100 KB |
| L0 research index | `dashboard/data/research_manifest.json` | < 100 KB |
| L0 KPI inflections | `dashboard/data/kpi_summary.json` | < 100 KB |
| L1 per ticker | `dashboard/data/agent_shards/{TICKER}.json` | 10-35 KB |
| Context pack | `dashboard/data/context_packs/{TICKER}.md` (+ `.json` manifest) | task-budgeted |
| Canonical pointers | `{TICKER}/research/latest.json` | one file per ticker |
| L2 evidence | paths inside `latest.json` artifacts (valuation, digest, deep dive) | open only when needed |

## Rules

- Returns are always **percent per year**: `base_irr_pct: 13.98` means 13.98%
  per year. The unit is stated in every `returns` block
  (`unit: percent_per_year`). Never rescale.
- Issuer operating levels (monthly volume, market share, revenue per contract)
  are on each ticker shard and in `dashboard/data/kpi_summary.json` under
  `operating_latest`, including series that are not accelerating. The
  inflection list is still only accelerating and decelerating series.
- `latest.json` is the only source for which deep dive, digest, adversarial
  pass, or cross-check is current. Do not guess from dated filenames.
- Facts, inferences, and opinions are separated in `_system/data/claims.jsonl`
  (`claim_type`, `status`). Approved and verified claims outrank pending ones.
- Raw filing text lives in `{TICKER}/research/evidence/_text/`. Do not load it
  whole; search it through the chunk index (below).
- Schemas for every agent-facing file are in `_system/schemas/`. Lint with
  `python _system/scripts/lint_agent_data.py {TICKER}`.

## Commands an agent may run (read-only)

```bash
python _system/scripts/build_agent_context.py {TICKER} --task triage
python _system/scripts/agent_search.py --query "pricing power" --ticker {TICKER}
python _system/scripts/query_magis_index.py --query "royalty" --ticker TPL
python _system/scripts/lint_agent_data.py {TICKER}
```

Rebuild the committed stores after research changes (also wired per ticker
into `marvin_cloud_refresh.py` for cards, latest pointers, shards, and packs):

```bash
python _system/scripts/build_claim_store.py
python _system/scripts/build_chunk_store.py
python _system/scripts/build_memory_index.py
python _system/scripts/publish_agent_index.py
python _system/scripts/run_agent_eval.py --build-golden
```

## Tools (MCP)

`_system/scripts/agent_mcp_server.py` exposes `get_portfolio_summary`,
`get_ticker`, `get_valuation`, `get_claims`, `search`, and `get_context_pack`
over stdio JSON-RPC for agents without filesystem access.

## Write-back

Agents do not edit `valuation.json`, thesis cards, or memory directly.
Submit a structured proposal instead; a human approves it:

```bash
python _system/scripts/agent_proposals.py submit proposal.json
```

Proposals land in `_system/data/agent_proposals/inbox.jsonl` with status
`pending_human_review`. Nothing becomes final without a file in
`_system/reviews/approved/`.
