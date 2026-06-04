# Simplex Financial Holdings Co., Ltd. (7176.T)

**Exchange:** Tokyo Stock Exchange (TSE Prime)  
**Market:** Japan  
**Sector:** Investment management, ETF listing and management, open innovation  
**IR (live PDFs):** https://www.simplexasset.com/sfh/ (frames entry: https://www.simplex-f-holdings.com/)

## Business (summary)

Japan-based asset manager serving institutional investors (family offices, pensions, governments, banks) and retail via proprietary and third-party ETFs (Nikkei, TOPIX, leveraged/inverse, thematic). Three lines: fund management, ETF platform, open innovation between investors and banks.

## Folder map

| Path | Contents |
|------|----------|
| `01_Official/` | Annual securities reports, governance reports |
| `02_Quarterly/` | Earnings releases and explanatory materials |
| `03_Events/` | Presentations, Q&A, transcripts |
| `04_Strategy/` | Medium-term plans |
| `06_References/` | EDINET and external links (not mirrored locally) |
| `_scripts/download_and_organize.ps1` | IR PDF harvest (adapt from `8697.T`) |
| `_pdf_urls.txt` | Canonical PDF URL list |
| `INDEX.csv` | Machine index for evidence pipeline |
| `research/` | Marvin thesis, deep dives, valuation, evidence |
| `third-party-analyses/` | Source inventory and cross-checks |
| `_download_log.txt` | Append-only download history |

## Download

```bash
python3 7176.T/_scripts/download_sfh_ir.py
python3 _system/scripts/build_folder_indexes.py --ticker 7176.T
python3 _system/scripts/build_filing_evidence.py 7176.T
```

Feeds: `sfh/financial_results/feed.xml`, `sfh/ir_information/feed.xml`, `sfh/shareholders_meeting_notice/feed.xml`.

**有価証券報告書 (yuho):** not on company feeds; use EDINET filer **E31267** when API key available.

## Research status

Onboarded 2026-06-04. **136 IR PDFs** mirrored (2026-06-04). Deep dive `research/deep_dive_2026-06-04.md`; refresh after yuho if needed.
