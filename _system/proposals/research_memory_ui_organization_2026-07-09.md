# Research Memory UI Organization

**Date:** 2026-07-09  
**Status:** Implemented (2026-07-09)

## Problems

1. **Broken evidence links** — ~1,324 claims store relative repo paths (`CPRT/research/deep_dive_*.md`) instead of GitHub blob URLs. On GitHub Pages, "Deep dive" links resolve to the dashboard origin and 404.
2. **Flat layout** — 11k+ claim ledger, biotech registry, quant signals, and review queue stack vertically with no sub-navigation.
3. **Wrong filters for context** — Letter quarter pills dominate the memory tab even though most claims are not letter-dated.
4. **Source column not actionable** — Source title is plain text; evidence link is a separate column with broken hrefs.

## Plan

### Phase 1 — Fix evidence URLs (builder + UI)

- Resolve every `evidence_ref` / relative path in `build_research_memory.py` via `best_document_url()` and `GITHUB_REPOSITORY`.
- Use `evidenceLink()` in all memory render paths as defense-in-depth.
- Validation: warn when claim ledger rows have non-http evidence URLs.

### Phase 2 — Memory sub-navigation

Sub-tabs within Research memory:

| Tab | Content |
|-----|---------|
| **Claim ledger** (default) | Filterable claim table |
| **Biotech** | Specialist registry, 13F signals, biotech ticker queue |
| **Review queue** | Human review items |

### Phase 3 — Memory-specific filters

- Hide letter quarter/year pills on memory tab; show note that claims span all research dates.
- Type pills: All · Thesis · Variant · Risk · Ownership · Fundamentals · Deep dive
- Biotech-only checkbox (holdings overlap filter unchanged)

### Phase 4 — Ledger table cleanup

- Columns: Ticker · Type · Direction · Claim · Evidence (linked label)
- Footer with filtered row count
- Ticker buttons jump to Holdings detail (existing behavior)

### Phase 5 — Rebuild and deploy

```bash
python _system/scripts/build_research_memory.py
python _system/scripts/validate_research_memory.py
```

Deploy-only Pages publish (`skip_rebuild=true`).
