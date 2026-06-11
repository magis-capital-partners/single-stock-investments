# Total return panel — universe rollout plan

**Status:** BVERS pilot complete · batch on next `batch_portfolio_refresh.py` run  
**Owner:** Marvin mechanical pipeline  
**Script:** `_system/scripts/build_total_return_panel.py`

## Goal

For every registry holding, attach:

1. **Sum of all known distributions/dividends** per share (`distribution_history` in `valuation.json`)
2. **Total return chart** (price index vs price + distributions, rebased 100)
3. **Current market cap estimate** (price × shares outstanding)

## Phase 0 — Infrastructure (done)

- [x] `build_total_return_panel.py` — Yahoo monthly prices + filing distribution history
- [x] Hook in `marvin_cloud_refresh.py` after equity price fetch
- [x] Cursor rule `.cursor/rules/total-return-panel.mdc`
- [x] BVERS pilot with OTC distribution history from annual reports

## Phase 1 — BVERS pilot (done first)

1. Populate `inputs.distribution_history` from FY2021–FY2025 partner letters
2. Run `build_total_return_panel.py BVERS --date 2026-06-11`
3. Embed `#### Total return and market cap` in `deep_dive_*.md` Primary sources
4. Human approved all `[HUMAN REVIEW]` items (stance **watch** retained)

## Phase 2 — Next portfolio batch run

Command (same date as batch refresh):

```bash
python _system/scripts/batch_portfolio_refresh.py --date YYYY-MM-DD
```

`marvin_cloud_refresh.py` now runs the panel step per ticker automatically.

### Per-ticker agent checklist (batch)

| Step | Action |
|------|--------|
| 1 | Ensure `inputs.shares_outstanding` in `valuation.json` (10-K or annual report) |
| 2 | Add `inputs.distribution_history` from filings (dividends, distributions, or trust payouts) |
| 3 | Mechanical refresh builds panel + chart |
| 4 | If deep dive exists, add or verify Primary sources `#### Total return and market cap` block |

### Ticker tiers

| Tier | Examples | Distribution source | Risk |
|------|----------|---------------------|------|
| A — US dividend | DHR, CSU, WPM | 10-K dividend history | Low |
| B — Royalty LP / trust | DMLP, MSB, SBR, PBT, SJT | K-1 / trust distribution tables | Medium |
| C — OTC LP | BVERS, BWEL, HNFSA, GCCO, PDER, WRLC | Annual report partner letters | Thin price history |
| D — Non-US | 8697.T, TEQ.ST, RMV.L | Local filings; Yahoo suffix | FX not in panel v1 |
| E — Pre-revenue / no div | NBIS, SMR | Skip chart or price-only | Panel warns insufficient |

### Backfill priority (first batch wave)

1. **Core / hold:** CPRT, CSU, AMZN, GOOGL, ICE, SPGI, TEQ.ST, 8697.T
2. **Royalty / land sleeve:** TPL, MSB, DMLP, PSK.TO, FNV, RGLD, KEWL, BWEL
3. **Remainder:** all other `registry.json` holdings alphabetically

### Success criteria

- `total_return_panel.json` exists for ≥90% of holdings with `valuation.json`
- Deep dives for core holdings show chart in Primary sources within two batch cycles
- OTC names document cumulative distributions even when Yahoo history is short

## Phase 3 — Optional enhancements (later)

- SEC dividend scraper into `distribution_history` (US 10-K cash-flow supplements)
- Stooq fallback when Yahoo fails
- Portfolio-level dashboard tile (Darwin) aggregating `market_cap_m` by sleeve

## QA

```bash
python _system/scripts/build_total_return_panel.py TICKER --date YYYY-MM-DD
# Expect: OK TICKER: cum_div=... market_cap=...M chart=...
```

Failures are **optional** in pipeline; log and continue. Agent adds `distribution_history` on next narrative pass if missing.
