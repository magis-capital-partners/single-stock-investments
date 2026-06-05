# Transcript pipeline — audit & fix prompt

**Date:** 2026-06-05  
**Status:** Fix in progress  
**Prepended context:** `_system/prompts/_prefix.md`

---

## Problem statement

`transcript_sync_summary.json` does not reflect portfolio-wide transcript state. Single-ticker runs (e.g. `marvin_cloud_refresh.py CPRT`) overwrite the summary with one ticker. Legacy transcript PDFs (~247 files across ICE, META, CBOE, etc.) are not registered in manifests unless a full `--register-legacy` run completes. Polygon earnings calendar is empty without API key, so gap detection cannot verify latest quarter coverage.

---

## Audit findings (2026-06-05)

### P0 — Summary corruption on partial runs

| Issue | Location | Impact |
|-------|----------|--------|
| Summary replaced, not merged | `download_transcripts.py` main() | `marvin_cloud_refresh.py {TICKER}` writes 1-ticker summary, destroying prior 55-ticker state |
| `marvin_cloud_refresh` calls per-ticker harvest | `marvin_cloud_refresh.py` L148 | Every cloud refresh clobbers portfolio summary |

**Evidence:** `_system/data/transcript_sync_summary.json` contained only `IDA.AX` or `CPRT` after isolated runs.

### P0 — Legacy registration never ran at scale

| Issue | Location | Impact |
|-------|----------|--------|
| Only 3/55 manifests exist | `**/TRANSCRIPT_MANIFEST.json` | CBOE (27), PCYO (1), RPRX (1) only |
| ~247 legacy transcript PDFs unregistered | `ir-ice/`, `ir-meta/`, etc. | Gap report shows ICE/META as zero coverage despite 125+ files |
| Full portfolio run blocks on IR harvest | `harvest_transcript_urls()` | 55 tickers × Q4 feeds + HTML scrape × 0.12s sleep → 10+ min; legacy step never reached in interrupted runs |

### P0 — Legacy registration dedupe bug

| Issue | Location | Impact |
|-------|----------|--------|
| `add_manifest_entry` treats `original_url=""` as duplicate | `transcript_common.py` | Only **1** legacy PDF registered per ticker; ICE stuck at 1/125 |

**Fix:** Only dedupe on `original_url` when non-empty.

### P1 — Logic bugs

| Issue | Location | Fix |
|-------|----------|-----|
| `register_legacy=args.register_legacy or True` | `download_transcripts.py` L276 | Always True; flag is meaningless. Use `--no-register-legacy` opt-out |
| No per-ticker error isolation | `process_ticker()` | One exception aborts run before summary write |
| Summary lacks manifest counts / errors | summary schema | Cannot diagnose without reading each ticker folder |

### P1 — Polygon earnings disabled

| Issue | Location | Impact |
|-------|----------|--------|
| `POLYGON_API_KEY` unset | `polygon_earnings.py` | `earnings_calendar.json` has 0 events, `polygon_enabled: false` |
| Gap report shows 0/55 covered | `transcript_gap_report.py` | Cannot detect missing latest-quarter transcripts |

**Note:** This is env config, not code bug. Document in summary `polygon_enabled` flag.

### P2 — Coverage gaps (expected, not bugs)

- 45/55 tickers have zero transcript files
- CPRT IR returns 503; needs Vicki shopbot brief
- JP transcripts live in `03_Events/Transcripts/` (8697.T has 2)
- Gap report ignores unregistered legacy files (by design until manifest exists)

---

## Fix plan (implement in order)

### Step 1 — Summary merge + schema (P0)

In `download_transcripts.py`:

1. Add `_merge_sync_summary(new_rows, tickers_processed)` — merge into existing `transcript_sync_summary.json` by ticker key when partial run.
2. Add top-level aggregates:
   ```json
   {
     "as_of": "...",
     "run_mode": "full|partial",
     "tickers_processed": 55,
     "totals": { "downloaded": N, "legacy_registered": N, "manifest_entries": N, "errors": N, "vicki_briefs": N },
     "polygon_enabled": false,
     "tickers": [...]
   }
   ```
3. Per-ticker row add: `manifest_entries`, `error` (null or message), `ir_roots_count`.

### Step 2 — Legacy-only fast path (P0)

Add `--legacy-only` flag: skip IR harvest + Vicki + Polygon fetch; only `scan_legacy_transcripts` + summary merge. Use for backfill:

```bash
python _system/scripts/download_transcripts.py --legacy-only --skip-earnings-fetch
```

### Step 3 — Register-legacy flag fix (P1)

Replace `or True` with:
```python
parser.add_argument("--no-register-legacy", action="store_true")
# register_legacy=not args.no_register_legacy  (default: register)
```

### Step 4 — Error isolation (P1)

Wrap `process_ticker` in try/except; record `error` field; continue to next ticker.

### Step 5 — marvin_cloud_refresh (P0)

After per-ticker transcript run, do **not** rely on summary for portfolio state. Either:
- Pass `--no-summary` on single-ticker refresh and let daily sync own summary, OR
- Merge summary (Step 1 handles this).

### Step 6 — Backfill + verify

```bash
python _system/scripts/download_transcripts.py --legacy-only --skip-earnings-fetch
python _system/scripts/transcript_gap_report.py
python _system/scripts/test_transcript_pipeline.py
```

**Acceptance criteria:**
- `transcript_sync_summary.json` has 55 ticker rows after legacy-only run
- ICE manifest entries ≥ 100
- Single-ticker `download_transcripts.py CPRT` merges CPRT row without dropping other 54
- Tests pass

### Step 7 — Polygon (human / env)

Set `POLYGON_API_KEY` in cloud agent secrets. Re-run without `--skip-earnings-fetch` to populate earnings calendar.

---

## Agent task template

```
Read _system/prompts/transcript_pipeline_fix.md and _system/prompts/_prefix.md.

Implement Steps 1–5. Run Step 6 verification. Commit on branch cursor/transcript-sync-fix-2b9f.

Do NOT edit _system/memory/MEMORY.md.
Log session notes to _system/memory/daily/{today}.md as [PROPOSED] only.
```

---

## Files to touch

| File | Change |
|------|--------|
| `_system/scripts/download_transcripts.py` | merge summary, legacy-only, flag fix, error isolation |
| `_system/scripts/test_transcript_pipeline.py` | tests for summary merge |
| `_system/proposals/transcript_pipeline_2026-06-02.md` | note fix applied |
