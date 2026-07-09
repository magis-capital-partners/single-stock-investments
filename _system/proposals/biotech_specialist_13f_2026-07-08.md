# Biotech Specialist 13F Quant Layer

**Date:** 2026-07-08  
**Status:** Implemented (Phases 0–7 full roadmap, 2026-07-09). Insider / spend / consensus / SI / peer marked `live` in FACTOR_SPEC. Paper book on Biotech tab only (no Darwin). Multi-quarter ingest via `--backfill-quarters N`.

## Goal

Ingest biotech specialist fund 13F holdings for portfolio tickers, compute quant signals, and surface them in Research memory and Insights ownership events.

## Data layout

| Path | Role |
|------|------|
| `ownership/biotech_specialist_funds.json` | Fund registry |
| `ownership/fund_cik_registry.json` | SEC CIKs |
| `ownership/records/{quarter}.json` | Portfolio-filtered holdings |
| `ownership/records/full/{fund}/{YYYYQn}.json` | Full InfoTables + QoQ |
| `ownership/signals_latest.json` | Consensus / flow / factor signals |
| `ownership/paper_book_latest.json` | Tab paper long/short sleeve |
| `ownership/biotech_short_interest.json` | FINRA SI factors |
| `ownership/biotech_clinical_profiles.json` | Clinical peer clusters |
| `ownership/cusip_ticker_map.json` | CUSIP map learned at ingest |

## Shipped

- `ingest_specialist_13f.py` — SEC EDGAR 13F-HR parser; `--backfill-quarters N`; QoQ from full tables
- `build_specialist_13f_signals.py` — consensus, density, issuer/position size, history
- `build_biotech_issuer_mcap.py` / spend / insider / FINRA SI / clinical peers / composite / paper book / knowledge delta
- Biotech Memory tab: Book/Universe toggle, filters, short watchlist, paper book
- Context tier only — never overwrites Lawrence IRR

## Rebuild

```bash
make specialist-13f-ingest   # offline-safe publish path into research memory
make biotech-insider-fetch   # online Form 4 harvest (scheduled/manual)
make biotech-short           # online FINRA SI
make biotech-clinical        # online ClinicalTrials + optional returns
```

## Known limits

- Forward-return validation stub needs ≥4 full quarters (`validate_biotech_quant.py`)
- Name-based CUSIP matching; expand `cusip_ticker_map.json` over time
- 13F lag: filings ~45 days after quarter end
