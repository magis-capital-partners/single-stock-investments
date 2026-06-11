# Batch onboard — 2026-06-11

**Manifest:** `_system/portfolio/onboard_batch_2026-06-11_royalty_king.json`

| Ticker | Status | Notes |
|--------|--------|-------|
| 0388.HK | ok | 0 |
| ABX | ok | 0 |
| ASX.AX | ok | 0 |
| B3SA3.SA | ok | 0 |
| BMYS.KL | ok | 0 |
| BOLSAA.MX | ok | 0 |
| BSM | ok | 0 |
| BYMA | ok | 0 |
| CDZI | ok | 0 |
| DB1.DE | ok | 0 |
| ENX.PA | ok | 0 |
| EVR | ok | 0 |
| GPW.WA | ok | 0 |
| GROY | ok | 0 |
| HEE | ok | 0 |
| KRP | ok | 0 |
| MTA | ok | 0 |
| NDAQ | ok | 0 |
| NRP | ok | 0 |
| NZX.NZ | ok | 0 |
| PSE | ok | 0 |
| S68.SI | ok | 0 |
| TASE | ok | 0 |
| TFPM | ok | 0 |
| X.TO | ok | 0 |
| XP | ok | 0 |

## Next steps (analyses)

1. **Deep dives:** `gh workflow run marvin-deep-dive.yml -f ticker=TICKER` for each new holding, or wait for daily `marvin-refresh` (`onboard_pending` priority).
2. **Mechanical refresh** (after dive + `valuation.json`): `python _system/scripts/marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD`
3. **Canadian (ALS.TO, PSK.TO):** IR-only download via `us_ticker_config`; add SEDAR PDFs or Vicki brief if IR scrape is thin.

## [HUMAN REVIEW]

- **BKRB:** folder symbol BKRB; SEC filings under **BRK-B** (CIK 1067983).
- **MRSH:** NYSE reticker from MMC; filings may still reference MMC in filenames.
- **BN:** skipped (already onboarded).

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] Batch onboard 2026-06-11: 26 tickers added.
