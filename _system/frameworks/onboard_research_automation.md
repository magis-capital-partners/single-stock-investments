# Onboard → research automation

**Status:** 2026-06-02

## What runs automatically today

### A. Dashboard / GitHub **Marvin Onboard Ticker** (`marvin-onboard.yml`)

Triggered by **+ Add holding** (OAuth `repository_dispatch`) or manual **workflow_dispatch**.

| Step | Automatic? | Output |
|------|------------|--------|
| Scaffold folder, registry, thesis | Yes | Commit to `main` |
| SEC/IR download | Yes | PDFs, `INDEX.csv`, `_download_log.txt` |
| Third-party scan + cross-check scaffold | Yes | `source_inventory`, scaffold cross-check |
| Dashboard JSON | Yes | via `build_dashboard_data.py` |
| **Marvin deep dive** | Yes **if** `CURSOR_API_KEY` is set | Cursor Cloud Agent → **PR** |
| Human merge PR | No | Required for research on `main` |

Onboard workflow calls `onboard_ticker.py --no-deep-dive` (scaffold only), then `marvin_deep_dive.mjs` with `PICK_REASON=onboard`.

### B. Cloud agent PR → full analysis pipeline

When the agent finishes, it must run:

```bash
python _system/scripts/marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD
```

That runs mechanically (no extra human steps):

- Filing evidence (`build_filing_evidence.py`)
- Third-party + HK scan
- `marvin_valuation.py --write` → `valuation.json`
- `refresh_deep_dive_v2.py` → structured dive
- `lint_deep_dive.py --milly`
- Milly `adversarial_{date}.md`
- `fill_cross_check.py` / `check_cross_checks.py`
- `sync_classification.py`, `build_dashboard_data.py`

Narrative (deep dive prose, cross-check narrative) is written by the **cloud agent** per `_system/prompts/cloud_marvin_runbook.md`.

### C. Daily **Download & Dashboard Sync** (`daily-sync.yml`, 12:00 UTC)

| Job | What it does |
|-----|----------------|
| `download-and-sync` | `download_all_holdings.py` for every registry holding |
| `portfolio-news` | Polygon news ingest |
| `marvin-refresh` | Picks **one** holding and runs `marvin_deep_dive.mjs` |

Picker: `marvin_pick_ticker.py` (holdings only). Priority:

1. `onboard_pending` — onboard complete, `deep_dive_pending`, no dive yet (newest onboard first)
2. `no_deep_dive` — holding without any dive
3. `new_documents` / `new_valuation_news` — activity since last dive
4. Skip if all caught up (`--require-new`)

So a **new holding** gets a dive the same day as onboard **if** onboard fired the cloud agent; otherwise it is first in line for the next daily `marvin-refresh` job.

### D. After merge to `main`

- **Deploy Dashboard** runs when dashboard paths change (or after onboard/daily-sync via `workflow_run`).
- **Darwin refresh** (weekly / on mandate change) rebuilds portfolio weights.

## Requirements for full automation

| Secret / config | Purpose |
|-----------------|--------|
| `CURSOR_API_KEY` | Cloud Marvin in onboard + daily refresh |
| `ONBOARD_DISPATCH_TOKEN` | Dashboard OAuth dispatch (optional) |
| `POLYGON_API_KEY` | Daily news job |
| `HK_PDFS_ROOT` | HK vault on cloud VM (optional) |

Without `CURSOR_API_KEY`, onboard still scaffolds and downloads; you must run **Marvin Deep Dive** manually or wait for nothing (daily refresh errors).

## Manual overrides

```bash
# Force one ticker
gh workflow run marvin-deep-dive.yml -f ticker=WBI

# Daily pick with rotation when nothing new
gh workflow run marvin-daily-deep-dive.yml -f force_rotate=true
```

## Not automatic (by design)

- Approving `MEMORY.md` beliefs
- Promoting third-party sources to approved list
- Merging cloud PRs (human review gate)
- Live brokerage execution
