# Transcript harvest brief — LMNR

**Date:** 2026-06-23  
**Agent:** Marvin transcript pipeline  
**Reason:** No local transcript 14 days after verified reported earnings  

## Context

- Portfolio ticker: **LMNR**
- IR roots: *(none configured)*

## Polygon earnings (verified reported)

- Date: 2026-06-09
- Fiscal period: Q2 FY2026
- Verification: reported_actuals

## Vicki task

1. Open IR events / earnings page (handle JS if needed).
2. Download latest earnings call **transcript PDF** (or save HTML if PDF unavailable).
3. Place file in:
   - `investor-documents/transcripts/` (US)
   - or market-appropriate transcripts folder.
4. Re-run: `python _system/scripts/download_transcripts.py LMNR`

## [HUMAN REVIEW]

- Confirm transcript matches the reported earnings period before citing in research.

