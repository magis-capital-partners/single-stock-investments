> Copy of the mesh root graph `C:\Users\drewg\Projects\.agent-memory\GRAPH.md` (copied 2026-10-12, verbatim below). It is cross-repo: of the hubs it names, only `research-equity` lives in this repo. Do not create the others here.

# Memory Mesh Graph

Absolute root: `C:\Users\drewg\Projects\.agent-memory`

## Nodes (repos)

| node_id | path | hub | write | may_read |
|---------|------|-----|-------|----------|
| `ls-algo` | `Projects/quant/ls-algo` | `borrow-etf` | `borrow-etf` | `borrow-etf` |
| `etf-dashboard` | `Projects/dashboards/etf-dashboard` | `borrow-etf` | `borrow-etf` | `borrow-etf` |
| `single-stock-investments` | `Projects/dashboards/single-stock-investments` | `research-equity` | `research-equity` | `research-equity` + local `_system/memory` |
| `dc-dashboard` | `Projects/quant/DC-Dashboard` | `diamond-creek` | `diamond-creek` | `diamond-creek` + **`borrow-etf` (RO)** |
| `research-vault` | `Projects/dashboards/research-vault` | `research-equity` | `research-equity` | `research-equity` + SSI `_system/memory` (RO) |
| `spx-0dte` | `Projects/options-trading/spx-0dte` | `spx-0dte` | `spx-0dte` | `spx-0dte` only |
| `diamond-creek-quant` | `Projects/quant/diamond-creek-quant` | `diamond-creek` | `diamond-creek` only | `diamond-creek` + **`borrow-etf` (RO)** |
| `dc-execution` | `Projects/quant/DC-Execution` | `diamond-creek` | `diamond-creek` only | `diamond-creek` + **`borrow-etf` (RO)** |

## Edges

```text
ls-algo  <──────RW──────>  etf-dashboard
                │
                │ RO (one-way)
                ▼
        diamond-creek-quant / dc-execution

single-stock-investments  <──────RW──────>  research-vault

spx-0dte  (no edges)
```

### Hard laws

1. **Write only your hub** (except bidirectional peers that share that hub).
2. **Diamond Creek never writes** `hubs/borrow-etf/**`. Upstream knowledge may be *cited* into `hubs/diamond-creek/` as a dated note with source path — never edited upstream from DCQ.
3. **SPX 0DTE never reads or writes** other hubs. No “helpful” borrowing of ETF/research memory.
4. **Do not invent edges.** If work needs a new share path, stop and ask the human.
5. **Secrets stay out of hubs** (keys, account IDs, session tokens).

## Hub file contract

Every hub has:

| file | role | who edits |
|------|------|-----------|
| `CONTEXT.md` | living domain model / vocabulary / current architecture truths | agents (careful) + human |
| `MEMORY.md` | durable approved beliefs / invariants | human promote only (agents propose) |
| `bridges.md` | shared data artifacts & path contracts between repos | agents + human |
| `daily/YYYY-MM-DD.md` | `[PROPOSED]` notes from sessions | agents |
| `decisions/YYYY-MM-DD-slug.md` | ADR-style decisions | agents when asked / after grill |

## Session protocol (non-trivial work)

1. Identify `node_id` from cwd (see table).
2. Read this `GRAPH.md` (permissions).
3. Read hub `CONTEXT.md` + `bridges.md`.
4. Skim hub `MEMORY.md` if decisions/invariants matter.
5. For Diamond Creek: also **read** `hubs/borrow-etf/CONTEXT.md` + `bridges.md` (RO).
6. For research-vault: also read SSI `_system/memory/MEMORY.md` as approved equity beliefs (RO unless human says promote).
7. End of useful session: append `[PROPOSED]` bullets to `daily/{date}.md` — do not silently rewrite `MEMORY.md`.
