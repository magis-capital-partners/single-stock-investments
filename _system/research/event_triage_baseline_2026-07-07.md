# Event triage baseline — What changed

**Date:** 2026-07-07  
**Pipeline:** `build_insights.py` → `event_materiality.py` → `event_triage.py`  
**Rules:** `_system/data/event_triage_rules.json`

## Method

Mechanical triage assigns each event a **materiality score (0–100)** and a **tier**:

| Tier | Threshold | Default UI |
|------|-----------|------------|
| signal | score ≥ 55 + promote rules | Signal tab (default) |
| context | score ≥ 25 | Context tab |
| noise | below 25 or demoted | Hidden unless Noise tab |

Sort order in UI: **date descending**, then materiality.

## Known false-positive patterns (addressed)

| Pattern | Rule | Example |
|---------|------|---------|
| Small-base balance % spike | `small_base_pct` + magnitude dampening | Cash +320% on $500k prior |
| Filing refresh metadata | `filing_refresh_only` | "Filing facts refreshed" |
| Parser skip flags | `parser_skip_flags` | segment_context pairing |
| Non-book tickers | `non_book_ticker` | Watchlist-only headlines |
| Stale filing metrics | `stale_event` | >365d without confirmed inflection |
| Low confidence large move | `large_move_low_conf` → human_review | Equity +250%, parser low |

## Golden test coverage

Run: `make event-triage-check`

Fixture: `_system/scripts/fixtures/event_triage_golden.jsonl` (12 labeled cases)

## Human review queue

Borderline rows: `_system/reviews/pending/event_triage_{date}.md`

Re-triage only: `make event-triage`

## Tuning workflow

1. Review human queue weekly
2. Add misfires to golden JSONL
3. Adjust thresholds in `event_triage_rules.json` only (no one-off code)
