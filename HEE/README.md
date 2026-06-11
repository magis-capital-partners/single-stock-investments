# Hellenic Exchanges - Athens Stock Exchange S.A. (HEE)

**Listing symbol:** EXAE (ATHEX) · **Yahoo:** EXAE.AT  
**Market:** EU (Greece) · **Archetype:** croupier (exchange / clearing / CSD)

## Company

Hellenic Exchanges operates the Athens Stock Exchange (ATHEX), clearing house (ATHEXCLEAR), and central securities depository (ATHEXCSD). Euronext acquired 74.25% via tender offer completed November 2025.

## IR links

- Investor relations: https://www.athexgroup.gr/web/guest/investor-relations
- Annual reports (Euronext mirror): https://athens.euronext.com/en/listings/athex

## Folder map

```
HEE/
├── investor-documents/
│   ├── ir-athex/                    # Annual reports (PDF)
│   └── download_hee_investor_docs.py
├── research/                        # Marvin analysis
├── third-party-analyses/
├── INDEX.csv
└── document-index.csv
```

## Download

```bash
python HEE/investor-documents/download_hee_investor_docs.py
python _system/scripts/build_folder_indexes.py --ticker HEE
```
