# Biotech Specialist 13F Quant Layer

**Date:** 2026-07-08  
**Status:** Implemented (Phases 0–5, 7) + 2026-07-09 knowledge compounding (full InfoTable ingest, consensus v2, spend/insider/composite, methodology library UI). Peer momentum + short interest remain stubs.

## Goal

Ingest biotech specialist fund 13F holdings for portfolio tickers, compute quant signals, and surface them in Research memory and Insights ownership events.

## Data layout

| Path | Role |
|------|------|
| `ownership/biotech_specialist_funds.json` | Fund registry |
| `ownership/fund_cik_registry.json` | SEC CIKs |
| `ownership/records/{quarter}.json` | Portfolio-filtered holdings |
| `ownership/signals_latest.json` | Consensus / flow signals |
| `ownership/cusip_ticker_map.json` | CUSIP map learned at ingest |

## Shipped

- `ingest_specialist_13f.py` — SEC EDGAR 13F-HR parser (portfolio tickers only)
- `build_specialist_13f_signals.py` — consensus score, net flow, initiation/exit flags
- `build_insights.py` — `specialist_13f` ownership events
- Tighter biotech ticker gate (sleeve-based, exclude megacaps/exchanges)
- Dashboard biotech registry + quant signals tables

## Rebuild

```bash
make specialist-13f-ingest   # network required; uses SEC EDGAR
make research-memory
```

## Known limits

- Soleus / Paradigm share a CIK in registry; dedupe manually if needed
- Name-based CUSIP matching; expand `cusip_ticker_map.json` over time
- 13F lag: filings ~45 days after quarter end

## Deferred

- Phase 6: deep dive cites, Milly exit flags, PROPOSED MEMORY templates
- WhaleWisdom enrichment, 13D/G cross-ref, backtest stub
