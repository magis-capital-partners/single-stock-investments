# London Stock Exchange Group (LSEG)

**Ticker:** LSEG (LSEG:LON) | **Market:** UK / LSE  
**ISIN:** GB00B0SWJX34  
**Last updated:** 2026-06-01

## Investor relations

- https://www.lseg.com/en/investor-relations
- Annual reports: https://www.lseg.com/en/investor-relations/annual-reports
- Financial results: https://www.lseg.com/en/investor-relations/financial-results

## Folder map

| Path | Contents |
|------|----------|
| `investor-documents/ir-lseg/` | Annual reports, preliminary results, Q1 trading updates (PDF) |
| `research/` | Deep dives, valuation, evidence |
| `INDEX.csv` | Document index (auto-built) |

## Download

```bash
python3 LSEG/investor-documents/download_lseg_investor_docs.py
python3 _system/scripts/build_folder_indexes.py --ticker LSEG
```

UK-listed; not an SEC filer. Documents fetched from canonical LSEG IR PDF URLs.
