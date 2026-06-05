# Transcript pipeline — implementation proposal

**Date:** 2026-06-02  
**Status:** Implemented (v1.1 — 2026-06-05 sync-summary + legacy dedupe fix)

See `_system/prompts/transcript_pipeline_fix.md` for audit and fix prompt.

## Scope

Automated transcript harvest integrated into `daily-sync.yml`:

- **Storage:** `{TICKER}/investor-documents/transcripts/` (US), `03_Events/Transcripts/` (JP)
- **Sources:** Company IR / Q4 feeds, Polygon Benzinga earnings calendar (timing), Vicki brief on persistent gaps
- **OCR:** `pdf_ocr.py` — pypdf first, tesseract fallback for scanned PDFs
- **Verification:** Polygon earnings use etf-dashboard-style rules — `reported` only when actuals present; dashboard displays verified subset only

## Scripts

| Script | Role |
|--------|------|
| `download_transcripts.py` | Main harvest + manifest + Vicki brief |
| `polygon_earnings.py` | Shared verified earnings fetch/normalize |
| `transcript_common.py` | Paths, IR harvest, manifest, metadata |
| `pdf_ocr.py` | Scanned PDF OCR |
| `transcript_gap_report.py` | Pending review coverage report |

## Data files

- `_system/data/earnings_calendar.json` — portfolio Polygon cache (verified flags)
- `_system/data/transcript_sync_summary.json` — last run summary
- `{TICKER}/investor-documents/TRANSCRIPT_MANIFEST.json` — per-ticker transcript registry
- `{TICKER}/research/evidence/earnings_calendar.json` — verified-only per ticker

## Daily sync

`download_all_holdings.py` runs transcript harvest after SEC/IR downloads, before INDEX rebuild.

## [HUMAN REVIEW]

- Confirm Polygon plan includes Benzinga earnings expansion
- Vicki briefs in `{TICKER}/research/shopbot/transcript_harvest_{date}.md` need browser agent follow-up
