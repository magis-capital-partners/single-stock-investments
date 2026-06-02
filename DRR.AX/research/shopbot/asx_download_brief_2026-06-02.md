# Vicki brief — DRR.AX ASX document harvest

**Date:** 2026-06-02  
**Ticker:** DRR.AX (Deterra Royalties Limited, ASX)  
**Issue:** US SEC download script returns zero filings; Cloud agent manually scraped 25 PDFs from deterraroyalties.com.

## Needed

1. **March 2026 quarter portfolio update** (ASX headline 30 Apr 2026; documentKey `2924-03085232-6A1323496`)
2. **FY2025 Annual Report** PDF (if not already on IR annual-reports page under a non-obvious filename)
3. Ongoing ASX announcement auto-download (replace US-only `download_us_investor_docs.py` path)

## IR URLs

- https://www.deterraroyalties.com/investors/asx-announcements/
- https://www.deterraroyalties.com/investors/annual-and-half-year-reports/
- https://www.deterraroyalties.com/investors/presentations/

## Success criteria

- PDFs land in `DRR.AX/investor-documents/asx-announcements/` or `official-reports/`
- `build_filing_evidence.py DRR.AX` produces at least one **full-tier** extract
- Append run to `DRR.AX/_download_log.txt`
