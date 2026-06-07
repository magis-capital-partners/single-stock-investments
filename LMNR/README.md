# Limoneira Company (LMNR)

**Ticker:** LMNR | **Exchange:** Nasdaq | **CIK:** 1342423 | **Market:** US  
**Last updated:** 2026-06-06

## Company

Limoneira is a diversified citrus grower, packer, and California land/water owner with real estate development through the Harvest at Limoneira joint venture (Lewis Group). Fiscal year ends October 31.

- **IR:** https://www.limoneira.com (investor subsite redirects; SEC primary)
- **Sector:** Agriculture production — crops (SIC 0100)

## Folder map

```
LMNR/
├── README.md
├── INDEX.csv
├── _download_log.txt
├── investor-documents/
│   ├── sec-edgar/          # 128 SEC filings (10-K, 10-Q, 8-K, proxy)
│   ├── ir-lmnr/
│   └── download_lmnr_investor_docs.py
├── research/
│   ├── thesis.md
│   ├── valuation.json
│   ├── deep_dive_2026-06-06.md
│   └── cross_check_third_party_2026-06-06.md
└── third-party-analyses/
```

## Download

```bash
python3 LMNR/investor-documents/download_lmnr_investor_docs.py
```

## Research

| File | Description |
|------|-------------|
| `research/deep_dive_2026-06-06.md` | Onboard deep dive |
| `research/valuation.json` | Lawrence yield-curve + nav_overlay |
| `research/thesis.md` | One-line thesis + classification |
