# World Model (Courtenay foresight layer)

Operative JSON for SSI’s append-only World Model. **Context only** — never auto-inflates Lawrence base IRR.

## What we count

| Layer | Count | What it is |
|-------|------:|------------|
| **Industry nodes** | **13** | Capacity / pricing / regulatory checklists |
| · thesis industries | 11 | Hold / researched book clusters |
| · horizon industries | 2 | AGI + robotaxi (expert quotes + checklist) |
| Theme prediction cards | 11 | Includes `macro_regime` (**not** an industry) |
| Superorgs | 2 | ICE (portfolio) + hyperscaler demand proxy |
| Expert horizon CSVs | 2 | Public arrival-date quotes |
| KPI ledgers | **62** | Every industry-linked ticker (6 curated + 56 industry scaffolds) |

Strip field `counts.industry_nodes` must match the industry table below.

## Coverage map

| Industry node | Kind | Theme card(s) | Horizon / Superorg | Example tickers |
|---------------|------|---------------|--------------------|-----------------|
| `ai_power` | thesis | `ai_power_land` | Superorg hyperscaler | APLD, TPL, LB, WBI, AZLCZ, BWEL |
| `water_surface` | thesis | `water_surface`, `ai_power_land` | — | TPL, LB, WBI, GYRO, TRC, CDZI |
| `hyperscaler_cloud` | thesis | `ai_power_land` | Superorg + AGI horizon | AMZN, GOOGL, META, MSFT |
| `gold_royalty` | thesis | `gold_royalties` | — | RGLD, MSB, WPM, OR, FNV, TFPM |
| `exchange_markets` | thesis | `exchange_volatility` | Superorg ICE | ICE, 8697.T, CME, CBOE, 0388.HK |
| `market_data_indices` | thesis | `index_data_fees`, `exchange_volatility` | — | SPGI, MCO, MSCI, FDS, OTCM |
| `timber_land` | thesis | `timber_housing` | — | ADN.TO, RYN, PCH, WY |
| `btc_mining_power` | thesis | `btc_hash_power`, `ai_power_land` | — | CMSG, CLSK, IREN, HUT, APLD, MSTR |
| `energy_royalty` | thesis | `energy_royalty` | — | SJT, DMLP, PBT, SBR, KRP |
| `pharma_royalty` | thesis | `pharma_royalty` | — | RPRX, ABBV, LLY, VTRS |
| `nuclear_firm_power` | thesis | `nuclear_power`, `ai_power_land` | AGI horizon | SMR, CEG, VST, DNN |
| `agi` | horizon | `ai_power_land`, `macro_regime` | horizon `agi` | APLD, TPL, LB |
| `robotaxi` | horizon | `macro_regime` | horizon `robotaxi` | TSLA, UBER, JOBY, ACHR |

**Not industries:** `macro_regime` (cross-cutting regime card only).

## Universe → industry logic

We do **not** map all ~700 registry watch names. Industries come from researched / hold clusters. **Every** `linked_tickers` name gets a `kpi_ledger.json` so the strip shows the full bucket graph.

```bash
python _system/scripts/scaffold_industry_kpi_ledgers.py --write
python _system/scripts/check_kpi_ledger.py --write --mark-auto
python _system/scripts/build_world_model_snapshot.py
```

Scaffolded ledgers carry `scaffold_meta`; curated pilots (TPL, APLD, LB, ICE, RGLD, MSB) are never overwritten unless `--force-scaffolded`.

## Growth rule (when to add an industry)

Add a new `_system/reference/industry/{id}.json` only when **all** of:

1. A hold-book thesis **or** approved horizon needs capacity / pricing / regulatory checklist.
2. A theme prediction card **or** expert-horizon domain already exists.
3. At least one bind: linked tickers, Superorg, or horizon domain.

**Still deferred:** insurance/float (thin), rare earths, space launch / Starship, proptech-only (CSGP) until a second name joins.

## Auto-link → valuation & deep dives (implemented)

| Phase | Status | Mechanism |
|------:|--------|-----------|
| 1 | live | `refresh_deep_dive_v2.py` injects `#### World Model context` |
| 2 | live | `apply_world_model_context.py` writes `valuation.json` `world_model_context` |
| 3 | live | `--queue-reviews` on check/apply opens pending review files |
| 4 | live (gated) | Template `_system/reviews/templates/world_model_promote.md` |
| 5 | live | Runbook pre-check + `marvin_cloud_refresh.py` + weekly CI |

Proposal / detail: `_system/proposals/world_model_autolink_valuation_2026-07-23.md`.

```bash
python _system/scripts/build_world_model_snapshot.py
python _system/scripts/apply_world_model_context.py --all --write --queue-reviews
python _system/scripts/refresh_deep_dive_v2.py ICE
```

CI: Data Pipeline cron `0 16 * * 0` (Sunday UTC) → profile `world-model-weekly`.

## Layout

| Path | Role |
|------|------|
| `themes/{theme_id}.json` | Prediction cards |
| `superorg/{org_id}.json` | Five-pillar Superorg scorecards |
| `expert_horizons/{domain}.csv` | Public arrival-date quotes |
| `../industry/{node}.json` | Industry checklists |
| `../kpi/history/{YYYY-MM}.json` | Monthly cold snapshots |
| `../../linkages/` | Cross-ticker derivation edges |

**First portfolio Superorg:** `superorg/ice.json`.  
**Demand proxy Superorg:** `superorg/hyperscaler_ai_builders.json`.
