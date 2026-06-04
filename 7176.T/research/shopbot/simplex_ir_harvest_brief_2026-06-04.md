# Vicki brief — 7176.T Simplex Financial Holdings IR harvest

**Date:** 2026-06-04  
**Agent:** Marvin (shopbot handoff)  
**IR root:** https://www.simplex-f-holdings.com/

## Objective

Populate `7176.T/_pdf_urls.txt` and run `7176.T/_scripts/download_and_organize.ps1` so `build_filing_evidence.py 7176.T` extracts Tier 1 text from local PDFs.

## Priority downloads (Japan template)

| Priority | Document type | Target folder | Notes |
|----------|---------------|---------------|-------|
| 1 | Latest **yuho** (有価証券報告書) / annual securities report | `01_Official/` | Segment note, shares outstanding, cash flow |
| 2 | Latest **quarterly** earnings release + explanatory materials | `02_Quarterly/` | AUM, fee revenue by line |
| 3 | **Corporate governance** report | `01_Official/` | Board, compensation |
| 4 | **Medium-term plan** / strategy deck | `04_Strategy/` | Growth targets if disclosed |
| 5 | EDINET cross-check | `06_References/` | Link only if mirror blocked |

## Fields needed for Marvin refresh

- Diluted shares (verify ~300M)
- Fund vs ETF vs Open Innovation revenue and operating profit
- AUM by product (¥ trillion)
- Normalized owner cash (OCF minus capital spending, or adjusted net income)
- Related-party and key-person risk

## Blockers

- `_pdf_urls.txt` is empty; `document_inventory.json` shows **0** local PDFs as of 2026-06-04.
- Marvin deep dive uses public profile + web only until harvest completes.

## Success criteria

- `INDEX.csv` updated via `build_folder_indexes.py --ticker 7176.T`
- `build_filing_evidence.py 7176.T` returns full or partial extract on latest yuho
- Re-run `marvin_cloud_refresh.py 7176.T --date YYYY-MM-DD`
