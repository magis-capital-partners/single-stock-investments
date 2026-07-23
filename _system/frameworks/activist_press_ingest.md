# Activist press / letter ingest

**Purpose:** Capture long-activist open letters, board presentations, and press-wire campaigns that never appear as `SC 13D` / `DFAN14A` on the issuer CIK (example: Third Point + D.E. Shaw vs CoStar / CSGP).

**Machine registry:** `_system/frameworks/activist_firm_registry.json`  
**Seeds:** `_system/data/activist_press_seeds.json`  
**Orchestrator:** `python _system/scripts/scan_activist_sources.py`

---

## Lanes (all converge on the same index → triage → feed)

| Lane | `source` | Trigger |
|------|----------|---------|
| SEC EDGAR | `sec_edgar` | `ingest_methods` includes `sec_13d` |
| Firm website | `publisher_site` | `ingest_methods` includes `site_index` + `domains` / `rss_urls` |
| Press / letter digest | `press_wire` | curated seeds (+ optional live PDF/HTML download) |
| Local / Drive | `local` | files under `{TICKER}/third-party-analyses/activist_reports/` |

Legacy field `ingest_method` (string) is still honored; prefer `ingest_methods` (list).

---

## What counts as a signal

**Include**

- Open letter to the board
- Campaign presentation / white paper tied to a named issuer
- Nomination / proxy / standstill campaign press release
- Wire PDF exhibits (PR Newswire `mma…` media PDFs, Business Wire letter pages)

**Exclude**

- AUM updates, hiring, fund launches
- Generic quarterly investor letters with no target-company ask
- Issuer-only responses unless they embed the activist letter (then `context`)

---

## Quality gates (same as short publisher rows)

1. Title/URL (and seed body) must match a **portfolio ticker** (`publisher_match_allowed`).
2. Document body must verify (`body_verified` / `target_verified`) before the feed accepts the row.
3. `cleanup_activist_false_positives.py` drops wire/site mismatches.
4. Materiality: `open_letter` / `campaign_presentation` score near proxy/13D; unverified bodies → noise.

---

## Adding a missed campaign

1. Append a row to `_system/data/activist_press_seeds.json` with `firm_id`, `ticker`, `title`, `report_date`, `source_url`, optional `document_url` + `body_text`.
2. Optionally drop a fixture under `_system/scripts/fixtures/activist_wire/` for offline CI.
3. Run:

```bash
python _system/scripts/scan_activist_sources.py --wire-only --ticker CSGP --reconcile
```

4. Confirm `dashboard/data/activist_feed.json` and the Activist tab show `Wire` + letter badge.

---

## CLI

```bash
python _system/scripts/scan_activist_sources.py                  # SEC + site + wire
python _system/scripts/scan_activist_sources.py --wire-only
python _system/scripts/scan_activist_sources.py --site-only
python _system/scripts/scan_activist_sources.py --skip-wire
python _system/scripts/press_activist_digest.py --ticker CSGP
```

Daily CI (`data-pipeline.yml` activist slot) runs the full orchestrator; no workflow change required beyond deploying these scripts.

---

## Maintenance

- Weekly: `python _system/scripts/activist_registry_audit.py` (optional `--fail-on-ingest`).
- When a campaign is missed in production: **add a seed**, do not only chat about it.
- Prefer official newsrooms / Business Wire / PR Newswire over SERP scraping.
