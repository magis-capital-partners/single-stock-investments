# S&P 500 Completion Plan - 2026-07-10

## Status (updated 2026-07-10 afternoon)

- **S&P 500 data onboard: COMPLETE** — 503/503 in registry (batches 0–43).
- Dashboard rebuild pending after final loop (`build_dashboard_data.py`).
- Fully complete holdings (deep dive + valuation + Milly): ~42 (unchanged until CI unblocked).
- Cloud deep-dive workflow blocked by Cursor background-agent spend limit:
  `usage_limit_exceeded - Background Agent requires at least $2 remaining until hard limit`.

## Completed Checkpoints

1. Batch 22 onboard artifacts were rebased onto latest main, dashboard artifacts rebuilt, validated, and pushed.
2. FDXF source repair (CIK, IR, SEC + IR PDFs).
3. HONA source repair (CIK, IR, SEC filings).
4. **Batches 24–43** finished remaining ~197 names (optimized: per-ticker index/dashboard skip, batch-size 10).
5. Final batch: WYNN, XEL, XYL, YUM, ZBRA, ZBH, ZTS.

## Next Steps (research, not onboard)

1. **Fix Cursor spend limit**, then drain deep-dive backlog (~460 names with `deep_dive_pending`).
2. Do **not** push changes to `deep_dive_dispatch_queue.json` until spend is fixed (auto-triggers failing workflows).
3. Merge deep-dive PRs / rebuild dashboard after each wave.
4. Spot-check SEC=0 names (CIK 403 during bulk run) and re-run download scripts.
5. Darwin refresh once valuations exist (`make darwin-build`).
