# Biotech specialist ownership data

Static ownership layer for the dashboard research memory and biotech quant signals.

## Layout

| Path | Purpose |
|------|---------|
| `biotech_specialist_funds.json` | Human-curated fund registry (28 funds) |
| `fund_cik_registry.json` | SEC CIK map for 13F ingest |
| `records/{quarter}.json` | Portfolio-filtered 13F holdings per quarter |
| `signals_latest.json` | Quant signals (consensus, flow, initiations) |
| `cusip_ticker_map.json` | CUSIP to ticker map learned during ingest |
| `cache/` | Raw SEC filing cache (gitignored if large) |

## Rebuild

```bash
make specialist-13f-ingest   # fetch SEC 13F for funds with CIKs
make research-memory       # merge into research_memory.json
```

## Cadence

- **13F ingest:** quarterly after 13F filing window (45 days after quarter end)
- **CIK verify:** annually or when a fund restructures
- **Fund registry:** human edits only

## Data limits

- Records files store **portfolio tickers only** (not full fund portfolios)
- Dashboard loads `research_memory.json` separately from `dashboard_data.json`
- Claim ledger capped at 12,000 rows; source registry capped at 4,000 entries
