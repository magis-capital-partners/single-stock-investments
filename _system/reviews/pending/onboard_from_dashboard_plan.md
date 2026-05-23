# Add Ticker from Dashboard → Download + Research Pipeline

**Date:** 2026-05-23  
**Agent:** Marvin  
**Status:** Implemented 2026-05-23  
**Related:** `dashboard_plan.md` Phase 2, `_system/prompts/onboard-new-stock.md`, SJT onboard (2026-05-21)

---

## Goal

From the portfolio dashboard, add a new ticker and kick off an automated pipeline that:

1. Registers the holding in portfolio metadata  
2. Scaffolds the ticker folder (market-appropriate layout)  
3. Downloads SEC filings, IR PDFs, and related documents  
4. Builds indexes and refreshes dashboard JSON  
5. Optionally triggers Marvin deep-dive research  
6. Surfaces progress and review items in the dashboard  

---

## Current state (gaps)

| What exists | Limitation |
|-------------|------------|
| Static dashboard (`dashboard/index.html`) | Read-only — no actions |
| Marvin onboard prompt | Manual, multi-file, agent-driven |
| `download_all_holdings.py` + `daily-sync.yml` | Only known tickers in config |
| `marvin-deep-dive.yml` | Research only — no scaffold/download |
| SJT onboard (reference) | Required edits to 4+ files: folder, `holdings.md`, `classification.json`, `us_ticker_config.json` |

**Core problem:** onboarding is a scattered manual workflow; the dashboard displays results but cannot start the chain.

**Constraint:** GitHub Pages is static — the browser cannot run Python or write to the repo directly. Any “Add ticker” button must trigger **GitHub Actions**, a **local helper**, or generate a **command the human runs**.

---

## Recommended architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard UI — "Add holding" panel                             │
│  (ticker, company, market, CIK, IR URL, run deep dive?)         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   Local dev mode     GitHub Actions      Copy-paste CLI
   POST localhost     workflow_dispatch    gh workflow run …
          │                 │
          └────────┬────────┘
                   ▼
        onboard_ticker.py  (new orchestrator)
                   │
     ┌─────────────┼─────────────┬──────────────┐
     ▼             ▼             ▼              ▼
  Scaffold    Register      Download      Post-process
  folder      metadata      (market)      indexes + JSON
                   │
                   ▼
        marvin-deep-dive.yml (optional)
                   │
                   ▼
        Pending review + dashboard refresh
```

### Design principles

1. **Single orchestrator CLI** — one entry point; dashboard and Actions both call it.  
2. **Registry as source of truth** — reduce drift across `holdings.md`, `classification.json`, `us_ticker_config.json`.  
3. **Reuse existing scripts** — do not rewrite SEC/JP/EU download logic.  
4. **Human gate preserved** — onboard writes pending review; MEMORY.md never auto-updated.  
5. **Progress visible** — job status file per ticker readable by dashboard build.

---

## Phase 1 — Orchestrator CLI (foundation)

**New file:** `_system/scripts/onboard_ticker.py`

### Inputs

| Arg | Required | Notes |
|-----|----------|-------|
| `--ticker` | Yes | e.g. `SJT`, `8697.T`, `TEQ.ST` |
| `--company` | Yes | Display name |
| `--market` | Yes | `US`, `JP`, `CA`, `EU`, `SE`, `OTC` |
| `--cik` | US | SEC CIK (lookup helper optional) |
| `--ir-url` | Recommended | One or more IR roots |
| `--deep-dive` | No | Chain to Marvin after download |
| `--dry-run` | No | Print plan without writes |

### Steps (ordered)

| Step | Action | Existing hook |
|------|--------|---------------|
| 1 | Validate ticker not in registry / folder | `list_tickers()` |
| 2 | Scaffold folder from `_system/templates/ticker-scaffold/` | Market template |
| 3 | Write `{TICKER}/README.md` | Onboard prompt step 3 |
| 4 | Create download wrapper | US: `download_us_investor_docs.py`; JP: PS1 stub; EU: `download_teq_st.py` pattern |
| 5 | Update `_system/portfolio/registry.json` | **New** — see below |
| 6 | Sync derived files from registry | Generate `holdings.md` row, `classification.json` entry, `us_ticker_config.json` (US) |
| 7 | Run download | Market-specific script |
| 8 | Run `build_folder_indexes.py` | INDEX.csv / document-index |
| 9 | Write `{TICKER}/research/thesis.md` scaffold + classification table | Defaults: stance `watch`, dhando `pending` |
| 10 | Write `_system/reviews/pending/{TICKER}_onboard_{date}.md` | Summary + gaps |
| 11 | Write `{TICKER}/.onboard_status.json` | `{phase, started, completed, errors}` |
| 12 | Run `build_dashboard_data.py` | Refresh JSON |
| 13 | Optional: invoke deep dive | Local: `marvin_deep_dive.mjs`; CI: re-dispatch workflow |

### New registry (Phase 1b — recommended in same PR)

**File:** `_system/portfolio/registry.json`

```json
{
  "SJT": {
    "company": "San Juan Basin Royalty Trust",
    "market": "US",
    "cik": "319655",
    "ir_roots": ["http://www.sjbasin.com"],
    "onboarded": "2026-05-21",
    "download": { "type": "us_shared", "options": { "download_8k_exhibits": true } }
  }
}
```

**Generators:**

- `holdings.md` — table rows from registry + folder mtimes  
- `classification.json` — merge registry defaults + thesis overrides  
- `us_ticker_config.json` — US entries only  
- `build_dashboard_data.py` — read registry first, folder scan as fallback  

*Migration:* one-time script to backfill registry from existing 19 holdings.

---

## Phase 2 — GitHub Actions workflow

**New file:** `.github/workflows/marvin-onboard.yml`

```yaml
on:
  workflow_dispatch:
    inputs:
      ticker:      { required: true }
      company:     { required: true }
      market:      { required: true, default: US }
      cik:         { required: false }
      ir_url:      { required: false }
      deep_dive:   { required: false, default: true, type: boolean }
```

### Job steps

1. Checkout repo  
2. Setup Python 3.12  
3. Run `python _system/scripts/onboard_ticker.py ...`  
4. Commit and push (bot): folder, registry, logs, manifest, dashboard JSON  
5. If `deep_dive`: trigger `marvin-deep-dive.yml` via `gh workflow run`  
6. Comment on run summary with links to pending review + PR (if deep dive)

**Secrets:** none for download; `CURSOR_API_KEY` only if deep dive chained.

**Rate limits:** SEC User-Agent already in US downloader; respect ~10 req/s.

---

## Phase 3 — Dashboard UI

**File:** `dashboard/index.html` + optional `dashboard/onboard.js`

### UI elements

1. **"+ Add holding"** button in header (next to filters)  
2. **Modal form:** Ticker, Company, Market (dropdown), CIK (US), IR URL, checkbox "Run Marvin deep dive after download"  
3. **Submit behavior** (mode-dependent):

| Mode | Behavior |
|------|----------|
| **GitHub Pages (production)** | Show copy-ready `gh workflow run marvin-onboard.yml -f ticker=…` block + link to [Actions → Run workflow](https://github.com/GoldmanDrew/single-stock-investments/actions/workflows/marvin-onboard.yml) |
| **Local dashboard** (`python -m http.server`) | Optional: POST to `localhost:8766/onboard` if local server running |

### Status display

Extend `build_dashboard_data.py` to read `{TICKER}/.onboard_status.json`:

| Dashboard field | Source |
|-----------------|--------|
| `onboard_phase` | `scaffold` / `downloading` / `complete` / `failed` |
| `onboard_errors` | Last error message |
| Badge | "Onboarding…" spinner or "Failed" on detail panel |

Show in-progress tickers even before first download completes (registry entry exists, folder created).

### Watchlist merge (optional Phase 3b)

Read `_system/watchlist/companies.md` into dashboard as separate section; "Promote to holding" pre-fills add form.

---

## Phase 4 — Local helper server (optional, dev-friendly)

**New file:** `_system/scripts/dashboard_onboard_server.py`

- Flask/FastAPI on port 8766  
- `POST /api/onboard` → subprocess `onboard_ticker.py`  
- `GET /api/status/{ticker}` → read `.onboard_status.json`  
- CORS allow `localhost:8765`  

**Dev workflow:**

```powershell
# Terminal 1
python _system/scripts/dashboard_onboard_server.py

# Terminal 2
cd dashboard; python -m http.server 8765
```

Dashboard detects `localhost` and enables one-click submit instead of copy-paste.

---

## Phase 5 — Research pipeline chaining

After download completes:

| Step | Owner | Output |
|------|-------|--------|
| Deep dive | `marvin_deep_dive.mjs` / Cloud Agent | `{TICKER}/research/deep_dive_{date}.md` |
| Pending review | Auto | `_system/reviews/pending/{TICKER}_deep_dive_{date}.md` |
| Cross-check | Manual / later prompt | `{TICKER}/research/cross_check_{date}.md` |
| Classification sync | `apply_thesis_classification.py` | thesis.md ← classification.json |

**Onboard default:** deep dive runs with `stance: watch`, frameworks from `mental_models.md` Tier 1.

**Vicki handoff:** if download returns 0 IR PDFs, set flag in onboard review → `{TICKER}/research/shopbot/` brief.

---

## Market-specific download routing

| Market | Script | Config location |
|--------|--------|-----------------|
| US | `download_us_investor_docs.py --ticker X` | `us_ticker_config.json` ← registry |
| CA | `download_csu.py` pattern or US if SEC-listed | registry |
| JP | `8697.T/_scripts/download_and_organize.ps1` template | `_pdf_urls.txt` stub |
| SE/EU | `download_teq_st.py` pattern | `document-index.csv` stub |
| OTC | `download_otc_api.py` | registry `cik: null` |

Add routing table to `onboard_ticker.py`; extend `download_all_holdings.py` to read registry instead of hardcoded lists.

---

## Files to create / modify

### New

| Path | Purpose |
|------|---------|
| `_system/scripts/onboard_ticker.py` | Main orchestrator |
| `_system/portfolio/registry.json` | Source of truth |
| `_system/scripts/sync_portfolio_from_registry.py` | Regenerate holdings.md, classification, us_ticker_config |
| `_system/scripts/migrate_to_registry.py` | One-time backfill from existing holdings |
| `.github/workflows/marvin-onboard.yml` | CI entry point |
| `_system/scripts/dashboard_onboard_server.py` | Optional local API (Phase 4) |
| `_system/prompts/onboard-new-stock.md` | Update steps 5–7 to reference registry + orchestrator |

### Modify

| Path | Change |
|------|--------|
| `dashboard/index.html` | Add holding modal + status badges |
| `_system/scripts/build_dashboard_data.py` | Read registry + onboard status |
| `_system/scripts/download_all_holdings.py` | Drive from registry |
| `_system/prompts/onboard-new-stock.md` | Point to CLI instead of manual multi-file |
| `dashboard_plan.md` | Add Phase 2g: onboard from dashboard |

---

## Implementation order (suggested)

| Sprint | Deliverable | Outcome |
|--------|-------------|---------|
| **1** | `registry.json` + migrate script + `sync_portfolio_from_registry.py` | Single registration source |
| **2** | `onboard_ticker.py` (US path first) | `python onboard_ticker.py --ticker X …` works end-to-end |
| **3** | `marvin-onboard.yml` | Remote trigger from GitHub Actions |
| **4** | Dashboard modal (command generator + status badges) | UX for add-holding |
| **5** | JP/EU/OTC routing in orchestrator | Non-US markets |
| **6** | Local onboard server (optional) | One-click local dev |
| **7** | Deep-dive chain + Vicki flag | Full research pipeline |

**MVP (Sprints 1–4):** US ticker from dashboard → GH Actions → folder + SEC download + dashboard row + pending review.

---

## Success criteria

- [ ] Add `TEST` (or real ticker) via workflow without manual edits to 4+ files  
- [ ] Dashboard shows new ticker within one build cycle (completeness may be low initially)  
- [ ] `_download_log.txt` populated; SEC PDFs in `investor-documents/`  
- [ ] Pending review doc written automatically  
- [ ] Optional deep dive PR opened within 2 hours  
- [ ] Failed downloads surface error in dashboard detail panel  

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Wrong CIK | CIK lookup helper (SEC company tickers JSON); human confirm in review doc |
| IR scrape returns 0 PDFs | Vicki handoff flag; do not mark onboard complete |
| GitHub Actions push conflicts | Concurrency group per ticker; pull before push |
| Static Pages can't trigger Actions | Command generator + GH Actions link; local server for dev |
| Registry / holdings drift | Registry is source of truth; CI check fails if derived files out of sync |
| SEC rate limiting | Existing 10 req/s; onboard runs off daily-sync cron |

---

## Open questions [HUMAN REVIEW]

1. **Registry migration:** Backfill all 19 holdings in Sprint 1, or lazy (new tickers only)?  
2. **Deep dive default:** Auto-run on every onboard, or opt-in checkbox?  
3. **Local server:** Worth Phase 4, or is `gh workflow run` copy-paste enough?  
4. **Watchlist:** Promote watchlist → holding in same flow, or separate?  
5. **Permissions:** Should onboard workflow use `GITHUB_TOKEN` push to `main`, or open a PR (safer)?  
6. **Private data:** Any tickers that must never hit public GitHub Pages dashboard?

---

## Thesis status

**unclear** — infrastructure feature; no investment thesis impact.

---

*Plan written 2026-05-23. Implement after human confirms sprint priority and open questions.*
