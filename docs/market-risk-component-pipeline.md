# Market-risk component pipeline

The batch component publisher runs in GitHub Actions once per weekday at 22:19 UTC (18:19 Eastern during daylight time, 17:19 during standard time). This is the configured start time, not a guaranteed publication deadline.

Workflow: `.github/workflows/market-risk-components.yml`

The workflow checks out:

- `single-stock-investments` for the builder, breadth snapshot, SPX surface and volatility snapshots;
- `GoldmanDrew/etf-dashboard` for leveraged-ETF flows and holdings;
- `GoldmanDrew/ls-algo` for volatility and borrow context.

It does not check out the SPX trading repository or contact the brokerage Gateway.

It publishes a signed snapshot to the Cloudflare market-risk ingest Worker and verifies that the generated artifact contains the expected component coverage. Required repository secrets are `MARKET_RISK_INGEST_TOKEN` and `LS_ALGO_TOKEN`; the ingest URL is a non-secret workflow variable.

The former Windows Databento live monitor is disabled according to the current Forced Flow Daily workflow. Daily capitulation is refreshed by `.github/workflows/forced-flow-daily.yml` and the technical pipeline. The browser distinguishes daily observations from any timestamp-valid live record.

Each component keeps its own observation date. A successful ingest or a recent build timestamp does not establish that all sources cover the latest completed session. The publisher commits a durable static fallback at most once per UTC day; that existing gate can skip an improved later same-day fallback.

For the audited stale-input causes, the comparison-date bug fix, and the proposed staged close refresh, see [Dashboard cleanup and market risk freshness](dashboard-cleanup-and-market-risk-plan.md). The earlier 16:13/16:43 refreshes in that plan are not implemented schedules.

The legacy Windows batch task (`Magis Market Risk Component Pipeline`) was disabled after the first successful GitHub Actions publish. To run a local fallback manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\_system\scripts\run_market_risk_component_pipeline.ps1
```

Do not run the local batch publisher and GitHub Actions publisher simultaneously; both write the same snapshot lane.
