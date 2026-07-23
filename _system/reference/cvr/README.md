# Contingent Value Rights (CVR) — reference library

**Created:** 2026-07-23  
**Purpose:** Source corpus + automatic dashboard sleeve for CVR / contingent consideration.

## Operating model

| Book | Role | Dashboard |
|------|------|-----------|
| **Pre-close** | Opportunity funnel | Still-listed target stock with contingent kicker |
| **Post-close** | Universe / claim inventory | Onboarded `*.CVR` stubs (and any tradeable CVRs) |

Pinned sleeve filter: **CVRs** (`cvr_all`) — first sleeve button after **All** on the holdings dashboard.

## Where things live

| Artifact | Path |
|----------|------|
| Universe registry | `cvr_universe.json` |
| Sleeve membership | `_system/portfolio/investment_sleeves.json` → `cvr_contingent` |
| Per-name terms | `{TICKER}/research/cvr_terms.json` |
| Term sheet index | `examples/term_sheet_index.md` |
| Refresh script | `_system/scripts/refresh_cvr_universe.py` |

### Current membership

| Book | Tickers |
|------|---------|
| Pre-close | `MFBP` |
| Post-close | `ABMD.CVR`, `MRTX.CVR`, `PRVL.CVR` |

## Automatic pipeline

```text
# Weekly (Monday 15:00 UTC) — discovery only
refresh_cvr_universe.py --discover --ingest-inbox --write-review --skip-sync
  → SEC full-text 8-K CVR search (fail-soft)
  → inbox/*.csv secondary feed → inbox/processed/
  → append context-tier pre_close_opportunities
  → reviews/pending/cvr_discovery_*.md
  → discovery_state health counters

# Nightly / every dashboard build — sync only (no SEC)
refresh_cvr_universe.py
  → sleeve cvr_contingent = universe tickers with cvr_terms.json (ready policy)
  → registry holdings + classification
  → display refresh on terms
  → sync_investment_sleeves.py
build_dashboard_data.py
  → row["cvr"] payload + pinned sleeve_filters cvr_all
```

**Hooks**

- Weekly discovery: Data Pipeline cron `0 15 * * 1` → job `cvr-discover`
- Nightly / light download: `download_all_holdings.py` → sync before dashboard build
- CI profiles: `ci_rebuild_profile.py` inserts sync before every `build_dashboard_data.py`
- Direct workflows: `ls-algo-universe.yml`, `letter-backfill.yml`

**Secondary feeds**

Drop CSVs in `inbox/` (see `inbox/README.md`). Schema sample: `examples/sample_screener_inbox.csv`.

**Manual discovery**

```bash
python _system/scripts/refresh_cvr_universe.py --discover --ingest-inbox --write-review --skip-sync
python _system/scripts/refresh_cvr_universe.py --ingest-csv path/to/screener.csv --write-review
```

SEC / CSV hits land as context-tier `pre_close` candidates and stay **off** the dashboard CVRs filter until `{TICKER}/research/cvr_terms.json` exists.

**Roadmap:** `_system/reviews/pending/cvr_discovery_robustness_plan_2026-07-23.md` (Parts 1–4).

## Local papers

| Path | Status |
|------|--------|
| `practitioner/Cleary_Gottlieb_CVRs_in_Pharma_Deals.pdf` | Downloaded |
| `practitioner/Wachtell_Lipton_CVR_Guide.pdf` | Downloaded |
| `papers/DiVA_Earnout_Expected_Payout_Models.pdf` | Downloaded |
| Chatterjee/Yan + Edwards SSRN | Manual / Cloudflare-blocked — see `papers/` queue |

## Related docs

- `research_brief_2026-07-23.md` — literature synthesis  
- `cvr_base_rates.json` — practitioner priors (context tier)  
- `_system/reviews/pending/cvr_agent_master_plan_2026-07-23.md` — build plan  
