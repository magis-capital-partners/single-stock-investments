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
| `cusip_ticker_map.json` | CUSIP to ticker map learned during ingest |
| `cache/` / `tracked_funds/cache/` | Raw SEC filing caches (gitignored if large) |

## Rebuild

```bash
make specialist-13f-ingest      # biotech specialists (+ quant chain)
make tracked-funds-13f-ingest   # great funds / value shops
make research-memory            # merge into research_memory.json
```

## Cadence

- **13F ingest:** quarterly after 13F filing window (45 days after quarter end)
- **CIK verify:** annually or when a fund restructures
- **Fund registry:** human edits only (`tracked_funds.json` / `biotech_specialist_funds.json`)

## Data limits

- Records files store **portfolio tickers only** (not full fund portfolios)
- Tracked-fund and Reddit social feeds are **context tier** (see `third_party_sources.md`); not base IRR
- Dashboard loads `research_memory.json` separately from `dashboard_data.json`
- Claim ledger capped at 12,000 rows; source registry capped at 4,000 entries
