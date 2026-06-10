# Batch onboard — 2026-06-10

**Manifest:** `_system\portfolio\onboard_batch_2026-06-10_land_otc.json`

| Ticker | Status | Notes |
|--------|--------|-------|
| WRLC | ok | 0 |
| PDER | ok | 0 |
| BVERS | ok | 0 |
| GCCO | ok | 0 |

## Next steps (analyses)

1. **Deep dives:** `gh workflow run marvin-deep-dive.yml -f ticker=TICKER` for each new holding, or wait for daily `marvin-refresh` (`onboard_pending` priority).
2. **Mechanical refresh** (after dive + `valuation.json`): `python _system/scripts/marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD`
3. **Canadian (ALS.TO, PSK.TO):** IR-only download via `us_ticker_config`; add SEDAR PDFs or Vicki brief if IR scrape is thin.

## [HUMAN REVIEW]

- **BKRB:** folder symbol BKRB; SEC filings under **BRK-B** (CIK 1067983).
- **MRSH:** NYSE reticker from MMC; filings may still reference MMC in filenames.
- **BN:** skipped (already onboarded).

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] Batch onboard 2026-06-10: 4 tickers added.
