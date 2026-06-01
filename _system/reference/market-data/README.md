# Market data for Darwin IRA backtests

Populated by `_system/scripts/download_ira_research.py`.

| Path | Contents |
|------|----------|
| `returns/{TICKER}.csv` | Monthly returns (Yahoo or synthetic) |
| `benchmarks/spy_us.csv` | SPY daily (Stooq) |
| `benchmarks/bnd_us.csv` | Bond ETF proxy |
| `french/` | Fama-French 5-factor monthly |
| `macro/` | FRED CPI, 10Y, VIX |
| `ira_download_manifest.json` | Last download log |

See `_system/frameworks/darwin_ira_research_plan.md`.
