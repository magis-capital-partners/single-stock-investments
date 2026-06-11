# Vicki brief — TASE IR harvest

**Date:** 2026-06-11  
**Status:** dispatched (`_system/data/vicki_dispatch_queue.json`)  
**Ticker:** TASE (Tel Aviv Stock Exchange Ltd.)  
**IR root:** https://www.tase.co.il/en/investor_relations  
**Financial reports:** https://www.tase.co.il/en/content/kne/financial_reports  

## Problem

Marvin curl/Maya API returns **403 Forbidden** from cloud VMs. FY2024 deep dive uses PR Newswire press release only; no local PDF mirror.

## Priority documents (Maya disclosure IDs)

| Doc | Maya report | PDF path (browser session required) |
|-----|-------------|-------------------------------------|
| FY2024 financial statements | [1649220](https://maya.tase.co.il/he/reports/1649220) | `https://maya.tase.co.il/rpdf/1649001-1650000/P1649220-00.pdf` |
| FY2024 investor presentation | [1649225](https://maya.tase.co.il/he/reports/1649225) | `https://maya.tase.co.il/rpdf/1649001-1650000/P1649225-00.pdf` |

Save to:

```
TASE/official-reports/annual-reports/
TASE/presentations-and-media/
```

## Browser notes

- Open Maya report page first, then click/download PDF (session cookie required).
- Financial reports page is JS-rendered; use Maya search or investor-relations links.
- Verify `%PDF` magic bytes before marking complete.

## After harvest

```bash
python _system/scripts/build_folder_indexes.py --ticker TASE
python _system/scripts/build_filing_evidence.py TASE
python _system/scripts/update_onboard_download_status.py
```
