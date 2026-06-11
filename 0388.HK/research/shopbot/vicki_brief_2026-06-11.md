# Vicki brief — 0388.HK IR harvest

**Date:** 2026-06-11  
**Ticker:** 0388.HK (Hong Kong Exchanges and Clearing Ltd)  
**IR root:** https://www.hkexgroup.com/investor-relations

## Problem

Onboard completed with **downloads skipped**. No official PDFs in `0388.HK/` except scaffold files. Marvin first deep dive relies on HKEX Group IR web disclosures until local mirror exists.

## Priority documents

1. FY2025 annual report (English) — `250317ar_e.pdf` pattern on hkexgroup.com
2. FY2024 annual report — https://www.hkexgroup.com/-/media/HKEX-Group-Site/ssd/Investor-Relations/Regulatory-Reports/documents/2025/250317ar_e.pdf
3. 2024 Q4 results presentation — hkex.com news release PDFs
4. 2026 Q1 results pack (ended 31 Mar 2026)
5. Latest regulatory reports and business statistics CSV/PDF

## Target folder layout (EU scaffold)

```
0388.HK/
├── official-reports/
├── presentations-and-media/
├── document-index.csv
└── INDEX.csv
```

## Success criteria

- At least **2 full-tier** extracts for `build_filing_evidence.py`
- `document-index.csv` populated
- Append run to `_download_log.txt`
