# Vicki brief — IEX.NS IR document harvest (India)

**Date:** 2026-06-04  
**Ticker:** IEX.NS (Indian Energy Exchange Limited, NSE / BSE 540750)  
**Market:** IN

## Problem

Cloud agent gets **403** from `doc.iexindia.com` CDN. BSE `AttachHis` / `AnnPdfOpen` PDFs work with browser Referer.

## Priority downloads

1. **Annual Report FY 2024-25** — `https://www.iexindia.com/investors/financials` (Annual Report FY 2024-25 link)
2. **Q4 FY26 audited results** (23 Apr 2026) — press release + investor presentation from investors-highlights
3. **FY25 annual report** if separate from FY24-25 on IR

## Target folders

```
IEX.NS/official-reports/annual-reports/
IEX.NS/official-reports/interim-reports/
IEX.NS/presentations-and-media/
```

## After harvest

```bash
python3 _system/scripts/build_folder_indexes.py --ticker IEX.NS
python3 _system/scripts/build_filing_evidence.py IEX.NS
```

Append run to `IEX.NS/_download_log.txt`.
