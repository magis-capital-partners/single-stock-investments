# Single Stock Investments

Personal single-stock research workspace with Marvin (research agent) infrastructure.

## Holdings

8697.T · 3905.T · APLD · QDEL · TEQ.ST · ICE · CSGP · SPGI · FRMO · OTCM · CPRT · BN · AMZN · GOOGL · KEWL · CSU · DHR · WBI

See [`_system/portfolio/holdings.md`](_system/portfolio/holdings.md).

## Dashboard

Static portfolio dashboard (etf-dashboard styling) in [`dashboard/`](dashboard/).

**Equity model viz:** Click a ticker with an **M** badge (pilot `7176.T`) to view earnings model charts in the detail panel. Rebuild: `python _system/scripts/build_dashboard_data.py` (includes model ingest). Spec: [`_system/prompts/dashboard_equity_model_viz.md`](_system/prompts/dashboard_equity_model_viz.md). **v2 upgrade (R², PM diagnostics):** [`_system/prompts/equity_model_v2_pm_diagnostics.md`](_system/prompts/equity_model_v2_pm_diagnostics.md).

**Darwin IRA:** [Research download plan](_system/frameworks/darwin_ira_research_plan.md) · copy PDF: `_system/scripts/copy_darwin_investor_pdf.ps1`

**Darwin tab (phases 0–4):** [Adaptive portfolio layer](_system/frameworks/darwin_portfolio_tab_proposal.md) · [Source alignment](_system/frameworks/darwin_source_alignment.md) — Holdings | **Darwin** on the dashboard. Rebuild:

```powershell
pip install -r _system/scripts/requirements-darwin.txt
python3 _system/scripts/build_darwin_portfolio.py --download
python3 _system/scripts/build_dashboard_data.py
```

Use `--fast` for CI-speed training. Reference PDFs: [`_system/reference/quant-evolution/`](_system/reference/quant-evolution/).

**Local preview:**

```powershell
python _system/scripts/build_dashboard_data.py
cd dashboard
python -m http.server 8765
```

Open http://localhost:8765/

**Live site (GitHub Pages, same repo):**

https://magis-capital-partners.github.io/single-stock-investments/

## Agents

- [`_system/agents/MARVIN.md`](_system/agents/MARVIN.md) — research + downloads
- [`_system/agents/VICKI.md`](_system/agents/VICKI.md) — browser / IR harvest

## GitHub integration

| Item | URL |
|------|-----|
| **Operational repo** | [github.com/magis-capital-partners/single-stock-investments](https://github.com/magis-capital-partners/single-stock-investments) |
| **Research vault (private)** | [github.com/magis-capital-partners/research-vault](https://github.com/magis-capital-partners/research-vault) — letters, HK PDFs, licensed sources |
| **Dashboard (Pages)** | [magis-capital-partners.github.io/single-stock-investments](https://magis-capital-partners.github.io/single-stock-investments/) |

Sensitive reference corpora live in **`research-vault`**; this repo holds code, portfolio, CI, and dashboard payloads. See [`_system/reference/research-vault-split.md`](_system/reference/research-vault-split.md) for setup.

**Local vault clone:**

```powershell
git clone git@github.com:magis-capital-partners/research-vault.git ..\research-vault
$env:RESEARCH_VAULT_ROOT = "..\research-vault"
powershell -ExecutionPolicy Bypass -File _system/scripts/setup_local.ps1
```

### One-time Pages setup

1. **Settings → General → Change repository visibility → Public**
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**
3. Run **Actions → Deploy Dashboard (GitHub Pages) → Run workflow**

You can delete the old `DASHBOARD_SYNC_TOKEN` secret and archive `single-stock-dashboard` if no longer needed.

### Workflows

See **`_system/reference/ci-workflows.md`** for the full capability matrix, shared actions, and orchestration diagram.

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`daily-sync.yml`](.github/workflows/daily-sync.yml) | Daily 12:00 UTC + manual | Deterministic download/news, then call the evidence-gated research dispatcher |
| [`drive-intake-sync.yml`](.github/workflows/drive-intake-sync.yml) | Hourly :20 UTC + manual | Import Drive PDFs → activist scan → rebuild → **chains Deploy Dashboard** |
| [`activist-scan-sync.yml`](.github/workflows/activist-scan-sync.yml) | Daily 06:00 UTC + manual | SEC/publisher activist scan → rebuild → **chains Deploy Dashboard** |
| [`portfolio-news.yml`](.github/workflows/portfolio-news.yml) | Every 6h :30 UTC + manual | Portfolio news ingest → **chains Deploy Dashboard** |
| [`darwin-refresh.yml`](.github/workflows/darwin-refresh.yml) | Mon 12:00 UTC + push paths + manual | Full Darwin rebuild → **chains Deploy Dashboard** |
| [`dashboard-pages.yml`](.github/workflows/dashboard-pages.yml) | Push paths + manual + workflow_run | Optional OAuth deploy → rebuild JSON → GitHub Pages |
| [`deploy-oauth-proxy.yml`](.github/workflows/deploy-oauth-proxy.yml) | Push oauth-proxy + manual | Cloudflare Worker deploy (or local Wrangler) |
| [`marvin-onboard.yml`](.github/workflows/marvin-onboard.yml) | Manual + repository_dispatch | Onboard and download deterministically, then request evidence-gated research |
| [`marvin-deep-dive.yml`](.github/workflows/marvin-deep-dive.yml) | Manual compatibility UI | Route deep-dive, auto-pick, and serial batch requests through one dispatcher |
| [`research-agent-dispatch.yml`](.github/workflows/research-agent-dispatch.yml) | Reusable + manual | The only Marvin agent entrypoint; builds manifest, gates, deduplicates, dispatches |
| [`power-zone-universe.yml`](.github/workflows/power-zone-universe.yml) | Nightly + manual | Route registry universe → contracts → workbenches → pricing → gated IC |
| [`investment-committee.yml`](.github/workflows/investment-committee.yml) | Manual stage advance | Five-call committee baseline; conditionally escalate to at most nine calls |
| [`vicki-ir-harvest.yml`](.github/workflows/vicki-ir-harvest.yml) | Manual + push queue file | Repair/create a reusable IR adapter only after deterministic failure |
| [`research-quality.yml`](.github/workflows/research-quality.yml) | PRs touching `**/research/**` | Lint dives + verify cloud prompt sync |
| [`llm-governance.yml`](.github/workflows/llm-governance.yml) | Agent/workflow PRs + main | Enforce token policy, evidence gates, call budgets, lockfiles, and deprecations |
| [`ci-autofix.yml`](.github/workflows/ci-autofix.yml) | Failed workflow_run + manual | Notify by default; agent only for repeated narrow code/test/schema signatures |

See [`_system/reference/ci-workflows.md`](_system/reference/ci-workflows.md) for composite actions (hidden from sidebar) and orchestration diagram.

### Marvin pipeline (local = cloud)

1. **Narrative** — filing-grounded write per `_system/prompts/cloud_marvin_runbook.md` and `deep_dive_structure.md`
2. **Mechanical** — one command:

```powershell
python _system/scripts/marvin_cloud_refresh.py TICKER --date 2026-05-29
```

3. **All holdings** — `python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29`

The authoritative valuation close is `python _system/scripts/run_security_decision_pipeline.py --scope all`. Marvin remains the evidence/narrative coordinator; Power Zones route methods and reviewers, the universal contract controls readiness, and only `human_decision.json` authorizes capital.

**INDEX.csv:** prefer per-ticker regen: `python _system/scripts/build_folder_indexes.py --ticker SNOW` (avoid full-portfolio regen unless intentional).

**Dropbox research ingestion:** source-preserving bulk intake for the Stahl/Horizon Kinetics and SumZero Dropbox folders lives in [`_system/frameworks/dropbox_ingestion.md`](_system/frameworks/dropbox_ingestion.md). Run `python _system/scripts/dropbox_ingest.py --stahl-password stahl`; raw archives stay local while manifests, indexes, extracted text, and summaries are written under `_system/dropbox_ingestion/`.

**SumZero Insights bridge:** `python _system/scripts/build_sumzero_index.py` scans the local `~/Downloads/SumZero Ideas.zip` archive, writes a compact committed index at `_system/reference/data-sources/sumzero_ideas_index.json`, and feeds matched holdings/watchlist ideas into the dashboard Insights tab. Raw SumZero documents stay local/ignored; `make persona-insights` refreshes the index before rebuilding dashboard data.

**Letter → ticker consensus pipeline (dataroma-style):** evidence-tiered matching that resolves superinvestor-letter mentions to a canonical security universe and aggregates a cross-fund consensus. Run in order:

```powershell
python _system/scripts/build_security_master.py        # canonical universe: book + Tier-A symbols harvested from letters
python _system/scripts/build_superinvestor_insights.py # tiered per-letter mentions, fund_id + real letter dates
python _system/scripts/calibrate_letter_dates.py --gold  # letter date parser gate (_eval/letter_date_gold.jsonl)
python _system/scripts/calibrate_letter_matching.py --gold  # precision/recall gate vs _eval/gold.jsonl (must PASS)
python _system/scripts/build_insights.py               # adds the consensus block (most-discussed / activity / by-ticker)
python _system/scripts/build_dashboard_data.py          # ticker payload; insights load from dashboard/data/insights.json
```

Matching logic lives in [`letter_matching.py`](_system/scripts/letter_matching.py) (Tier A = explicit ticker syntax, Tier B = verified company name; word/benchmark/credential collisions are gated out). Curate funds in [`_system/reference/superinvestor-letters/funds.json`](_system/reference/superinvestor-letters/funds.json) (uncurated letters are grouped deterministically and listed in `funds_unresolved.json`). The dashboard **Insights → Consensus** tab renders the result with quarter/book/search facets. Current calibration: precision 0.97 / recall 0.94.

### Cursor models and billing

| Context | Model | Notes |
|---------|--------|--------|
| **IDE Composer** (local Marvin chat) | Your Cursor setting (e.g. Composer 2.5) | Uses your plan’s Composer allowance |
| **Research coordinator** | `composer-2.5` in `marvin_deep_dive.mjs` | One evidence-changed ticker/day through the shared admission gate |
| **Investment Committee** | `composer-2.5` | Five-call baseline; up to nine only on evidence or disagreement escalation |
| **Vicki / CI Autofix** | `composer-2.5` | Exception-only, with cooldown, deduplication, and daily budgets |
| **Python scripts** | No LLM | Power Zone router, universal contract/workbench, pricing gates, dashboard build; `marvin_valuation` is compatibility-only |

All active cloud consumers use the shared policy, stable evidence hashes, append-only audit ledgers, pinned SDK lockfiles, and `npm ci`. See [`_system/frameworks/llm_token_governance.md`](_system/frameworks/llm_token_governance.md).

Push to `main` after downloads or research triggers a Pages deploy automatically when dashboard-related paths change.

**Onboard → research:** Dashboard **+ Add holding** triggers deterministic scaffold/download, then the shared dispatcher. A cloud PR starts only when an evidence manifest is ready and not previously processed. See `_system/frameworks/onboard_research_automation.md`.

**Daily analysis loop:** `daily-sync` downloads holdings and news, then the dispatcher picks at most one eligible holding. Unchanged evidence, duplicate hashes, cooldowns, and the one-call daily budget all suppress Cursor.

### Secrets (Settings → Secrets → Actions)

| Secret | Required for | How to get |
|--------|--------------|------------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Drive intake + PDF store sync | Full service-account JSON for `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`; folder access is already on the Shared Drive |
| `RESEARCH_VAULT_REPO_URL` | Letter backfill + insight rebuilds | `https://github.com/magis-capital-partners/research-vault.git` |
| `RESEARCH_VAULT_CLONE_TOKEN` | Clone/push private vault from CI | Fine-grained PAT with **Contents read+write** on `research-vault` |
| `CURSOR_API_KEY` | Gated research, committee judgment, IR adapter repair, and narrow CI autofix | [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations) |
| `HK_PDFS_ROOT` | Optional — full HK vault on cloud agent VM (default `/opt/cursor/hk_pdfs`) | [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents); see `_system/frameworks/hk_cross_reference.md` |

### Local publish

```powershell
powershell -ExecutionPolicy Bypass -File _system/scripts/publish_github.ps1
```

Rebuilds dashboard JSON and pushes to `main`. Pages deploy runs via GitHub Actions (no second repo).

### Marvin session → GitHub

After local Marvin work:

```powershell
python _system/scripts/build_dashboard_data.py
git add -A
git commit -m "research: YOUR_MESSAGE"
git push origin main
```

Or run **Actions → Marvin Deep Dive** with mode `deep-dive` and a ticker; review and merge the PR the cloud agent opens (must end with `marvin_cloud_refresh.py` per runbook).

Dashboard links use **filename date** (not mtime) for latest `deep_dive_*.md` / `adversarial_*.md`.

### Public repo note

This repo contains portfolio research and ticker theses. Licensed letter/HK corpora are in the private **`research-vault`** repo. Review GitHub Pages access separately before assuming dashboard data is private.

For unlimited GitHub Actions minutes, the **operational** repo can be made public (vault stays private). See `_system/reference/research-vault-split.md`.

## Structure

- **Ticker folders** — official PDFs, indexes, download scripts
- **`_system/`** — memory, frameworks, prompts, reviews
- **`dashboard/`** — static portfolio UI
