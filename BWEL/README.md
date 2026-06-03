# J.G. Boswell Company (BWEL)

**Ticker:** BWEL | **Market:** US (OTC Pink)  
**Exchange:** OTC Pink | **CIK:** — (non-SEC filer)  
**Last updated:** 2026-06-02

## Company

Large-scale California agribusiness (cotton, tomatoes, grains, orchards) with integrated ginning/processing and subsurface mineral interests. Family-controlled since 1921; shares trade thinly on OTC Markets.

## Document sources

| Source | URL |
|--------|-----|
| OTC disclosure | https://www.otcmarkets.com/stock/BWEL/disclosure |
| Latest annual (FY2025) | `investor-documents/ir-bwel/2025-06-30_Annual_Report.pdf` |

## Download

```bash
python3 BWEL/investor-documents/download_bwel_investor_docs.py
python3 _system/scripts/download_otc_api.py   # includes BWEL
```

## Folder map

```
BWEL/
├── investor-documents/ir-bwel/        # OTC annual reports (PDF)
├── investor-documents/research-notes/ # Books (e.g. The King of California)
├── research/                          # Marvin analysis
├── third-party-analyses/
└── INDEX.csv
```

## Reference book

*The King of California* (Arax & Wartzman, 2003) — see `investor-documents/research-notes/README.md`. Run:

```bash
python3 BWEL/investor-documents/download_king_of_california.py
```
