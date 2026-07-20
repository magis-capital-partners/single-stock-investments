# Retired features and artifacts

One note per retirement, per the 2026-07 dashboard overhaul. If you need any
of these back, they live in git history before the commit that added this file.

## docs/ GitHub Pages mirror (2026-07-20)

The `docs/` folder was a full copy of `dashboard/` kept for a legacy
branch-based Pages deploy. GitHub Pages now deploys via workflow artifact
(`dashboard-pages.yml` uploads `dashboard/` directly), so the mirror only
doubled repo size and CI conflict surface. Removed: the `docs/` tree,
`_system/scripts/sync_pages_docs.py`, the per-script `docs/data` writers in
`build_insights.py` / `build_index_membership.py` /
`refresh_valuation_dashboard_rows.py` / `portfolio_news_common.py`, and the
`docs/` mirroring in `ci_push_main.sh`. This folder now holds only this log.

## Darwin taxable track (2026-07-20)

`darwin_portfolio_taxable.json` and `darwin_backtest_report_taxable.md` were
artifacts of the retired Darwin taxable paper book (UI already said
"taxable track retired"; the Roth IRA book is the only live Darwin track).

## Insights Themes / Overview tabs (2026-07-20)

The Themes sub-tab was folded into Letters, and Overview into Pipeline
status, months ago. Removed the localStorage remap shims and the dead theme
rendering code (`renderThemeRankings`, theme momentum, sentiment bars) from
`dashboard/index.html` and `dashboard/insights-viz.js`. Macro themes still
exist in the data (`theme_rankings*` in insights) for time-model quarter
hints; only the dead UI went away.

## One-shot migration scripts (2026-07-20)

Moved to `_system/scripts/attic/` (excluded from CI): `migrate_to_registry.py`,
`vic_local_intake.py`, `migrate_drive_pdf_store_layout.py`,
`migrate_economic_value_config.py`, `plan_drive_reorg.py`,
`organize_drive_orphan_folders.py`. See `attic/README.md`.

## Reviewed and kept (2026-07-20)

- `portfolio_news.json` — still an input to `build_insights.py` (events lane);
  the SPA no longer fetches it directly.
- `research_memory_evidence.json` — build artifact required by
  `validate_research_memory.py`; not fetched by the SPA.
- Biotech script cluster (`build_biotech_*.py`) — still wired into the
  `insights` and `full` CI rebuild profiles and the Research memory biotech
  sub-tab; kept until that lane is explicitly retired.
- `irr_model.py`, `dropbox_ingest.py`, `import_drive_letter_orphans.py` —
  actively referenced by builders/workflows; not legacy.

## Monolithic browser payloads (2026-07-20)

`dashboard_data.json` and `insights.json` remain as pipeline contracts, but
the SPA no longer downloads them: it boots from `data/core.json` and
lazy-fetches `data/tickers/{TICKER}.json`, `data/insights/{section}.json`,
and standalone artifacts on demand.
