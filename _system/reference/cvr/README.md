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
| Optional watch sleeve | `cvr_watch` (context stubs; opt-in `--enable-watch-sleeve`) |
| Per-name terms | `{TICKER}/research/cvr_terms.json` |
| Agent handoff queue | `_system/data/cvr_agent_queue.json` |
| Integrity check | `_system/scripts/check_cvr_universe.py` |
| Refresh script | `_system/scripts/refresh_cvr_universe.py` |

### Current membership

| Book | Tickers |
|------|---------|
| Pre-close | `MFBP` |
| Post-close | `ABMD.CVR`, `MRTX.CVR`, `PRVL.CVR` |

## Automatic pipeline

```text
# Weekly (Monday 15:00 UTC) — Parts 1–3 discovery
refresh_cvr_universe.py
  --discover --discover-non-sec-family
  --sync-alpharank --ingest-inbox --create-stubs
  --write-review --alert --skip-sync
  → SEC primary + expanded + ECIP/bank family (fail-soft)
  → AlphaRank drop path → inbox/ → processed/
  → CIK→target resolve, form filters, accession+CIK dedupe
  → stub folders (skeleton terms; sleeve NOT ready)
  → reviews/pending/cvr_discovery_*.md (+ optional Slack)

# Nightly / every dashboard build — Part 4 monitoring (no SEC)
refresh_cvr_universe.py --refresh-prices --apply-transitions --queue-stubs
  → Yahoo quotes → p_market / naive IRR display
  → pre→post stage transitions when close_date set
  → queue incomplete stubs for Marvin
  → sleeve = terms_complete only
check_cvr_universe.py
build_dashboard_data.py
```

**Sleeve guardrail:** `cvr_terms.json` must have `stub=false`, `terms_complete=true`, and max payout or milestones before a name appears on the pinned **CVRs** filter.

**Hooks**

- Weekly discovery: Data Pipeline cron `0 15 * * 1` → job `cvr-discover`
- Nightly / light download: `download_all_holdings.py`
- CI profiles: `ci_rebuild_profile.py` inserts refresh + check before every `build_dashboard_data.py`

**Secondary feeds**

| Feed | How |
|------|-----|
| CSV inbox | Drop files in `inbox/` (see `inbox/README.md`) |
| AlphaRank path | Set repo variable `CVR_ALPHARANK_DROP_PATH` or env `ALPHARANK_CSV_PATH` to a folder/file of CSVs; weekly job copies into inbox |
| Slack alerts | Optional secret `SLACK_WEBHOOK_URL` |

**Manual**

```bash
python _system/scripts/refresh_cvr_universe.py \
  --discover --discover-non-sec-family --ingest-inbox --sync-alpharank \
  --create-stubs --write-review --alert --skip-sync

python _system/scripts/refresh_cvr_universe.py \
  --refresh-prices --refresh-milestones --apply-transitions --queue-stubs

python _system/scripts/check_cvr_universe.py --strict
python _system/scripts/test_cvr_discovery.py
```

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
