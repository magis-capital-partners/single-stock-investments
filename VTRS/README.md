# Viatris Inc (VTRS)

**Ticker:** VTRS | **Market:** US (NASDAQ)  
**CIK:** 1792044  
**IR:** https://investor.viatris.com  
**Last updated:** 2026-06-02

## Folder map

| Path | Contents |
|------|----------|
| `investor-documents/sec-edgar/` | SEC 10-K, 10-Q, 8-K, proxies |
| `investor-documents/ir-vtrs/` | IR PDFs (harvest when available) |
| `research/` | Marvin deep dives, valuation, evidence |
| `third-party-analyses/` | Source inventory |

## Download

```bash
python3 VTRS/investor-documents/download_vtrs_investor_docs.py
```

Rebuild indexes: `python3 _system/scripts/build_folder_indexes.py --ticker VTRS`
