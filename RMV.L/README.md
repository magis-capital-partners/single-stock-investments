# Rightmove PLC (RMV.L)

**Exchange:** London Stock Exchange (LSE)  
**Market:** UK  
**Sector:** Online UK residential property portal  
**IR:** https://plc.rightmove.co.uk/

## Folder map

| Path | Contents |
|------|----------|
| `official-reports/` | Annual report PDFs (FY2024, FY2025) |
| `investor-documents/ir-rightmove/` | RNS releases, results presentations |
| `investor-documents/download_rmv_investor_docs.py` | Canonical IR PDF downloader |
| `research/` | Marvin thesis, deep dives, valuation, evidence |
| `third-party-analyses/` | Source inventory and cross-checks |
| `presentations-and-media/` | Links to webcasts (not stored as PDFs) |
| `document-index.csv` | EU-style document map (sync with INDEX.csv) |
| `INDEX.csv` | Machine index for evidence pipeline |
| `_download_log.txt` | Append-only download history |

## Download

```bash
python3 RMV.L/investor-documents/download_rmv_investor_docs.py
python3 _system/scripts/build_folder_indexes.py --ticker RMV.L
python3 _system/scripts/build_filing_evidence.py RMV.L
```

## Research status

Onboarded 2026-06-04. Latest deep dive: `research/deep_dive_2026-06-04.md`.
