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
`docs/` mirroring in `ci_push_main.sh`. This folder retains research
documentation and the write contract.

### Remaining mirror removed October 12 2026

The old `docs/index.html`, copied visualization scripts, stylesheet and OAuth
copies remained after the sync writer was retired. They could show a different
dashboard from the canonical `dashboard/` app. The remaining UI copies and
`.nojekyll` were removed, along with the dead `pages-sync` target and the stale
sync call in `event-triage`. Research Markdown, `WRITE_MAP.md` and the document
inventory are retained. Cloudflare Pages builds from `dashboard/`; another
serving tree would add an unused writer and another source of stale views.

## Darwin allocator (2026-10-16)

The Darwin tab showed an IRR-driven Roth IRA paper book (`build_darwin_portfolio.py`,
`_system/scripts/darwin/`, `dashboard/data/darwin_*`). Its refresh workflow had been
dead since 2026-08-23, every name in its universe had failed research eligibility,
and the book held 100% cash. The tab now shows the **Darwin Covered Call** signal
(`build_darwin_covered_call.py`, `darwin-covered-call.yml`).

Removed: the `darwin/` package's allocator modules (features, policies, genetic,
PPO, encoder, ensemble, paper portfolio, observatory, point-in-time backtests, the
synthetic covered-call overlay and options cache), the `build_darwin_*` and
`check_darwin_pit.py` scripts, the Darwin mandates, the paper books' event and
adaptation logs, the IRA/Roth/taxable target weights,
`research_events.jsonl` (only Darwin read it), the regime briefs, the
`darwin` / `darwin-full` rebuild profiles and checkout profile, and the Darwin
framework notes and investor-letter copies.

Left in place, frozen: `_system/portfolio/paper/roth.json` and `taxable.json`.
Nothing writes them any more, but `build_valuation_universe_tiers.py` reads their
positions as the only Tier 1 signal (13 names on 2026-10-16), and Tier 1 is what
`run_security_decision_pipeline.py` and the Tier 1 readiness queue act on.
Deleting them would empty Tier 1. Move those names to explicit `overrides` in
`valuation_universe_policy.json` (or another position source) before removing them.

Kept and moved to `_system/scripts/marketdata/`: price fetchers, symbol mapping,
external-repo paths, the returns importer, S&P 500 membership, the macro regime
(used by the Insights macro strip), valuation-history archiving (used by
`marvin_valuation.py`), and the ls-algo universe and S&P refresh scripts. The
mass onboarder became `_system/scripts/sp500_mass_onboard.py`. The World Model's
market-path cap now reads VIX and its term structure from `vol_metrics_latest.json`
instead of the frozen Darwin observatory.

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
