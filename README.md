# Single Stock Investments

Personal single-stock research workspace with Marvin (research agent) infrastructure.

## Holdings

8697.T · 3905.T · APLD · QDEL · TEQ.ST · ICE · CSGP · SPGI · FRMO · OTCM · CPRT · BN · AMZN · GOOGL · KEWL · CSU · DHR · WBI

See [`_system/portfolio/holdings.md`](_system/portfolio/holdings.md).

## Dashboard

Static portfolio dashboard (etf-dashboard styling) in [`dashboard/`](dashboard/).

**Planned:** [Darwin adaptive portfolio tab](_system/frameworks/darwin_portfolio_tab_proposal.md) — neural + evolutionary allocation on top of Marvin research (low turnover). Reference PDFs: [`_system/reference/quant-evolution/`](_system/reference/quant-evolution/).

**Local preview:**

```powershell
python _system/scripts/build_dashboard_data.py
cd dashboard
python -m http.server 8765
```

Open http://localhost:8765/

**Live site (GitHub Pages, same repo):**

https://goldmandrew.github.io/single-stock-investments/

## Agents

- [`_system/agents/MARVIN.md`](_system/agents/MARVIN.md) — research + downloads
- [`_system/agents/VICKI.md`](_system/agents/VICKI.md) — browser / IR harvest

## GitHub integration

| Item | URL |
|------|-----|
| **Repository** | [github.com/GoldmanDrew/single-stock-investments](https://github.com/GoldmanDrew/single-stock-investments) (public) |
| **Dashboard (Pages)** | [goldmandrew.github.io/single-stock-investments](https://goldmandrew.github.io/single-stock-investments/) |

Everything lives in one repo: Marvin workspace + `dashboard/` for Pages. **No PAT required** for dashboard sync.

### One-time Pages setup

1. **Settings → General → Change repository visibility → Public**
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**
3. Run **Actions → Deploy Dashboard (GitHub Pages) → Run workflow**

You can delete the old `DASHBOARD_SYNC_TOKEN` secret and archive `single-stock-dashboard` if no longer needed.

### Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`daily-sync.yml`](.github/workflows/daily-sync.yml) | Daily 12:00 UTC + manual | Download holdings → commit → **auto Marvin refresh** if new docs |
| [`dashboard-pages.yml`](.github/workflows/dashboard-pages.yml) | Push to `main` (dashboard paths) + manual | Rebuild JSON → deploy `dashboard/` to GitHub Pages |
| [`marvin-deep-dive.yml`](.github/workflows/marvin-deep-dive.yml) | Manual (ticker input) | Cursor Cloud Agent deep dive → opens PR |
| [`marvin-daily-deep-dive.yml`](.github/workflows/marvin-daily-deep-dive.yml) | Manual only | Pick on new documents (or **force_rotate**) → cloud agent → PR |
| [`research-quality.yml`](.github/workflows/research-quality.yml) | PRs touching `**/research/**` | Lint dives + verify cloud prompt sync |

### Marvin pipeline (local = cloud)

1. **Narrative** — filing-grounded write per `_system/prompts/cloud_marvin_runbook.md` and `deep_dive_structure.md`
2. **Mechanical** — one command:

```powershell
python _system/scripts/marvin_cloud_refresh.py TICKER --date 2026-05-29
```

3. **All holdings** — `python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29`

**INDEX.csv:** prefer per-ticker regen: `python _system/scripts/build_folder_indexes.py --ticker SNOW` (avoid full-portfolio regen unless intentional).

### Cursor models and billing

| Context | Model | Notes |
|---------|--------|--------|
| **IDE Composer** (local Marvin chat) | Your Cursor setting (e.g. Composer 2.5) | Uses your plan’s Composer allowance |
| **GitHub Actions cloud Marvin** | `composer-2.5` in `marvin_deep_dive.mjs` | `CURSOR_API_KEY`; opens PR — not IDE tokens |
| **Python scripts** | No LLM | `marvin_valuation`, `refresh_deep_dive_v2`, dashboard build |

Cloud prompt stays aligned with local refresh via `_system/prompts/cloud_marvin_runbook.md`; CI runs `check_cloud_marvin_sync.py` on PRs.

Push to `main` after downloads or research triggers a Pages deploy automatically when dashboard-related paths change.

**Daily analysis loop:** `daily-sync` (12:00 UTC) downloads new SEC/IR files → on success, `marvin-daily-deep-dive` runs → picks tickers whose primary documents are **newer than their latest deep dive** → opens a Cursor PR. If nothing new, the deep dive workflow **skips** (use manual run + **force_rotate** to refresh the oldest dive anyway).

### Secrets (Settings → Secrets → Actions)

| Secret | Required for | How to get |
|--------|--------------|------------|
| `CURSOR_API_KEY` | Marvin deep dive in CI (manual + **daily auto**) | [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations) |
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

Or run **Actions → Marvin Deep Dive** with a ticker; review and merge the PR the cloud agent opens (must end with `marvin_cloud_refresh.py` per runbook).

Dashboard links use **filename date** (not mtime) for latest `deep_dive_*.md` / `adversarial_*.md`.

### Public repo note

Making this repo public exposes ticker PDFs, research notes, and `_system/memory/MEMORY.md`. Review contents before switching visibility.

## Structure

- **Ticker folders** — official PDFs, indexes, download scripts
- **`_system/`** — memory, frameworks, prompts, reviews
- **`dashboard/`** — static portfolio UI
