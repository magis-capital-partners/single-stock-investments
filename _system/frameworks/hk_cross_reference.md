# Horizon Kinetics cross-reference workflow

**Purpose:** HK-specific scan and mental models for indexed tickers (TPL, ICE, MSB, SJT). **Universe-wide third-party rules:** see `third_party_cross_reference.md`.

**Related:** `third_party_sources.md` (approval tiers), `external_view_blend.md` (when to blend), `mental_models.md` (Tier 3 HK models).

---

## Source tiers

| Tier | Location | Marvin use |
|------|----------|--------------|
| **In-repo extracts** | `_system/reference/investment-wisdom/horizon-kinetics/*.txt` | Always searchable; primary agent-readable HK text |
| **Stahl shelf PDFs** | `_system/reference/investment-wisdom/stahl/` | Croupier / exchange / diversification essays |
| **Full HK vault** | `HK_PDFS_ROOT` or Windows `hk_pdfs/` (400+ PDFs) | Filename + `book/build/text/` scan when path available |
| **Approved Substacks** | `{TICKER}/third-party-analyses/references.md` | SSI / LCI per `approved_substacks.md` |
| **Approved cross-checks** | `_system/reviews/approved/` | Human-approved HK lens vs filings (e.g. SJT) |

**HK commentaries = context tier by default.** Cite in narrative, Business & moat (mental models), and cross-check files. Do **not** put HK assumptions into `valuation.json` base IRR without human approval in `third_party_sources.md`.

---

## Mandatory steps (HK-indexed tickers)

Tickers in `hk_ticker_index.json` (today: **TPL, SJT, MSB, ICE**):

1. **Before narrative** — run HK scan:
   ```bash
   python _system/scripts/scan_hk_sources.py {TICKER} --write-references
   ```
2. **Read** `{TICKER}/third-party-analyses/hk_scan_{date}.md` and every curated source listed.
3. **Required:** write or update `{TICKER}/research/cross_check_HK_{date}.md` (or `cross_check_{date}.md`) using `external_view_blend.md` — agreements, divergences, synthesis. Every ticker in `hk_ticker_index.json` must have a cross-check file on record; refresh when the deep dive or material filings change.
4. **Deep dive** — Primary sources section must include the auto-generated `### Horizon Kinetics cross-reference` block (injected by refresh or `--inject-dive`).
5. **After refresh** — run `python _system/scripts/check_hk_cross_checks.py` (or `make hk-cross-check-all`) to verify scan + cross-check exist.

---

## Adding a new ticker

1. Add entry to `_system/reference/investment-wisdom/hk_ticker_index.json` (patterns, mental_models, curated rows).
2. Run `scan_hk_sources.py {TICKER} --write-references`.
3. Promote recurring hits from `source: scan` into `curated` in the index.
4. When human approves an HK blend, add row to `third_party_sources.md` **Approved registry**.

---

## Full vault on cloud / Linux

**Default cloud path:** `/opt/cursor/hk_pdfs` (`hk_paths.json` → `hk_pdfs_root_cloud_default`).

### One-time setup (Cursor Cloud Agents)

1. [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents): set **`HK_PDFS_ROOT=/opt/cursor/hk_pdfs`** (or your mount path).
2. Optional: set **`HK_PDFS_REPO_URL`** if the vault lives in a private git repo (cloned by `.cursor/environment.json` install).
3. Or attach the vault via **multi-repo environment** so `hk_pdfs` is on the VM at the path above.
4. Optional GitHub Actions secret **`HK_PDFS_ROOT`** — forwarded to the agent via `marvin_deep_dive.mjs` `envVars`.

Repo wiring: `.cursor/environment.json`, `_system/scripts/cloud_setup_hk_vault.sh`, `marvin_deep_dive.mjs`.

### Scan + auto extract refresh

```bash
python _system/scripts/refresh_hk_extracts.py   # copies newer vault text → horizon-kinetics/
python _system/scripts/scan_hk_sources.py TPL MSB SJT ICE --write-references
```

`refresh_hk_extracts.py` runs automatically in `marvin_cloud_refresh.py` and `scan_third_party_sources.py --with-hk`. Mapping: `hk_extract_manifest.json`. Status: `horizon-kinetics/extract_refresh_status.json`.

On Windows workspace the default path in `hk_paths.json` is used automatically.

**Approval:** You promote HK blends to `third_party_sources.md`. Agents cite HK as context only.

---

## Cross-check template (HK vs filings)

When HK has a dated thesis (e.g. SJT dividend reinstatement by May 2025):

| Lens | Claim | Primary-source check | Weight |
|------|-------|----------------------|--------|
| HK Q1 2025 | … | 10-K / 10-Q fact | … |
| Marvin floor | … | Filing-derived | … |
| **Synthesis** | … | Best estimate | stance input |

Record material synthesis in `valuation.json` → `estimates.external[]` only after human approval.

---

## Pipeline integration

| Step | Script |
|------|--------|
| HK scan | `scan_hk_sources.py` |
| Cross-check QA | `check_hk_cross_checks.py` |
| Full refresh | `marvin_cloud_refresh.py` (runs HK scan first for indexed tickers) |
| Dive inject | `refresh_deep_dive_v2.py` (reads latest `hk_scan_*.json`) |
| QA | `make hk-scan TICKER=TPL` · `make hk-cross-check-all` |
