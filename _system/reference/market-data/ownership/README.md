# Ownership data (biotech specialists + tracked great funds)

Static ownership layer for the dashboard research memory, biotech quant signals, and curated great-fund overlays.

## Layout

| Path | Purpose |
|------|---------|
| `biotech_specialist_funds.json` | Human-curated biotech specialist fund registry |
| `fund_cik_registry.json` | SEC CIK map for specialist 13F ingest |
| `records/{quarter}.json` | Portfolio-filtered specialist 13F holdings per quarter |
| `signals_latest.json` | Biotech quant signals (consensus, flow, initiations) |
| `tracked_funds.json` | Curated great mutual-fund / value-shop registry |
| `tracked_fund_cik_registry.json` | SEC CIK map for tracked-fund 13F ingest |
| `tracked_funds/records/{quarter}.json` | Portfolio-filtered tracked-fund holdings |
| `tracked_funds/signals_latest.json` | Light QoQ ownership signals for tracked funds |
| `managers.json` | Public manager name and SEC CIK. No origin notes. |
| `13f/positions/{quarter}/{manager}.csv` | Full 13F book for tracked, biotech, and active managers |
| `13f/changes/{quarter}.json` | Share changes versus the prior quarter on file |
| `13f/filings.jsonl` | Accession index. A repeat run skips a saved accession. |
| `cusip_ticker_map.json` | CUSIP to ticker map. Name guesses are not written back. |
| `cache/` / `tracked_funds/cache/` | Raw SEC filing caches (gitignored) |

## Rebuild

```bash
make specialist-13f-ingest      # biotech specialists (+ quant chain)
make tracked-funds-13f-ingest   # great funds / value shops
make research-memory            # merge into research_memory.json
```

## Cadence

- **13F ingest:** daily check at 13:29 UTC (Data Pipeline `thirteen-f`). A manager is downloaded only when the latest holdings accession is not already saved. Quarter labels use the period of report. The daily job reloads two periods. The 21st of February, May, August, and November reloads twelve. A 13F notice is not a book: the overlap builder sums the other managers named on that notice for the same period (Vanguard Group files this way from 2026). Another firm's book is copied only when the names share a rare word.
- **International:** `intl/nport/` is Form N-PORT for tracked managers' non-US holdings. `intl/edinet/status.json` is Japan's 5 percent reports. Without `EDINET_API_KEY` the EDINET file stays empty. Optional `OPENFIGI_API_KEY` is not required. HKEX, SEDI, ASX, and UK/EU notices are not scraped.
- **CIK verify:** annually or when a fund restructures
- **Fund registry:** human edits only (`tracked_funds.json` / `biotech_specialist_funds.json`)

## Data limits

- Older `records/` files store portfolio tickers only. `13f/positions/` stores the full public 13F book.
- Overlap advisers (the large passive complexes) stay in `dashboard/data/overlap_holdings.json`, filtered to the book.
- Tracked-fund holdings and the Held by panel are context (see `third_party_sources.md`). They are not an input to the base return.
- Dashboard loads `research_memory.json` separately from `dashboard_data.json`
- Claim ledger capped at 12,000 rows; source registry capped at 4,000 entries
