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
refresh_cvr_universe.py
  → sync cvr_contingent tickers from cvr_universe.json
  → ensure registry holdings + classification.investment_sleeve
  → refresh display fields on cvr_terms.json
  → sync_investment_sleeves.py
build_dashboard_data.py
  → row["cvr"] payload + pinned sleeve_filters cvr_all
```

**Hooks**

- Nightly / light download: `download_all_holdings.py` → `daily_refresh` runs refresh before dashboard build
- CI profiles: `ci_rebuild_profile.py` inserts refresh before every `build_dashboard_data.py`
- Direct workflows: `ls-algo-universe.yml`, `letter-backfill.yml`

**Optional discovery**

```bash
python _system/scripts/refresh_cvr_universe.py --discover
python _system/scripts/refresh_cvr_universe.py --ingest-csv path/to/screener.csv
```

SEC / CSV hits land as context-tier `pre_close` candidates until an agent fills `cvr_terms.json` from primary exhibits.

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
