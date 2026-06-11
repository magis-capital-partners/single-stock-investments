# Bolsa Mexicana de Valores SAB de CV (BOLSAA.MX)

**Market:** Mexico (BMV)  
**Exchange:** Bolsa Mexicana de Valores  
**Ticker:** BOLSAA (BMV)

## Company

Grupo BMV operates Mexico's primary stock exchange, equity and derivatives clearing, central securities depository (Indeval), market data (Valmer), and OTC brokerage (SIF ICAP). Listed parent: Bolsa Mexicana de Valores, S.A.B. de C.V.

## Investor relations

- IR hub: https://www.bmv.com.mx/en/investor-relations
- Financial reports: https://www.bmv.com.mx/en/investor-relations/financial-reports
- Integrated annual reports: https://www.bmv.com.mx/en/bmv-group/bmv-annual-report

## Folder map

```
BOLSAA.MX/
├── README.md
├── INDEX.csv
├── document-index.csv
├── _download_log.txt
├── investor-documents/
│   ├── download_bolsaax_investor_docs.py
│   ├── DOWNLOAD_MANIFEST.json
│   └── ir-bmv/              # annual + quarterly PDFs
├── research/
│   ├── thesis.md
│   ├── valuation.json
│   ├── deep_dive_2026-06-11.md
│   └── evidence/
└── third-party-analyses/
```

## Download

```bash
python BOLSAA.MX/investor-documents/download_bolsaax_investor_docs.py
python _system/scripts/build_folder_indexes.py --ticker BOLSAA.MX
```

## Research status

- **Onboarded:** 2026-06-11 (Royalty King + HK exchange screen)
- **Last research:** 2026-06-11 (first deep dive)
