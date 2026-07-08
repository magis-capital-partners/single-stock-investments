# Research Memory Upgrade

**Date:** 2026-07-08  
**Status:** Implemented (Phases 0–5, 7; Phase 6 Marvin integration deferred)

## Goal

Turn the Insights **Research memory** tab into a reliable, searchable claim index with correct evidence semantics, supplemental deep-dive ingestion, and separated payload loading for repo size limits.

## Shipped

- Pipeline: `build_research_memory.py` runs after letter rebuild, letter backfill, batch refresh, and `make research-memory`
- Schema v2: improved claim typing, deduped review queue, supplemental claims from deep dives / adversarial / valuation
- Payload split: `research_memory.json` + `research_memory_evidence.json` loaded separately (not embedded in `dashboard_data.json`)
- Validation: `validate_research_memory.py`
- UI: summary header, biotech panel wired, holdings-based book filter, ownership claims on ticker panel

## Deferred

- Phase 6: Marvin MEMORY.md bridge, Milly ingest, onboard gates
- Full evidence graph UI (source registry browser)

## Rebuild

```bash
make research-memory
python _system/scripts/validate_research_memory.py
make pages-sync
```
