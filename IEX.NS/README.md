# Indian Energy Exchange Limited (IEX.NS)

**Ticker:** IEX.NS | **Exchange:** NSE (BSE: 540750) | **Market:** IN  
**Last updated:** 2026-06-04

India's primary power exchange (electricity, RECs, gas). Listed October 2017. Regulated by CERC.

**IR:** https://www.iexindia.com/investors/financials  
**Also:** https://www.iexindia.com/investors/investors-highlights

## Folder map

```
IEX.NS/
├── official-reports/
│   ├── annual-reports/
│   └── interim-reports/
├── presentations-and-media/
├── investor-documents/
│   └── download_iex.ns_investor_docs.py   # BSE PDF harvest
├── research/
└── INDEX.csv
```

## Download

```bash
python3 IEX.NS/investor-documents/download_iex.ns_investor_docs.py
python3 _system/scripts/build_folder_indexes.py --ticker IEX.NS
```

**Note:** `doc.iexindia.com` blocks cloud egress (403). BSE filings download via script; latest FY24-25 annual and Q4 FY26 IR PDFs flagged for Vicki (`research/shopbot/iex_ir_harvest_brief_2026-06-04.md`).
