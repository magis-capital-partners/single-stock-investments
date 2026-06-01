# Third-party cross-reference (universe-wide)

**Purpose:** Every ticker in `_system/portfolio/registry.json` must have a **third-party source inventory** and a **cross-check file** that triangulates Marvin (primary filings) against **all** external material before stance is final.

**Related:** `third_party_sources.md`, `approved_substacks.md`, `external_view_blend.md`, `hk_cross_reference.md` (HK subset).

---

## Source types (all tickers)

| Type | Location | Status default |
|------|----------|----------------|
| **Approved registry** | `_system/frameworks/third_party_sources.md` | approved |
| **Approved Substacks** | `{TICKER}/third-party-analyses/references.md` | context (approved publisher) |
| **Research notes PDFs** | `{TICKER}/investor-documents/research-notes/` | pending until approved |
| **Horizon Kinetics / Stahl** | `hk_scan_*.md` when indexed | context |
| **Short / activist** | `{TICKER}/third-party-analyses/short_reports/` | context |
| **Pending queue** | `{TICKER}/third-party-analyses/pending.md` | pending |

**Approved** sources may blend into IRR per `external_view_blend.md`. **Pending** and **context** sources must be cited but not folded into base IRR without human approval.

---

## Mandatory workflow (every universe ticker)

### On onboard or new deep dive

```bash
python _system/scripts/scan_third_party_sources.py {TICKER} --with-hk --date YYYY-MM-DD
python _system/scripts/scaffold_cross_check.py {TICKER} --date YYYY-MM-DD   # if none exists
```

1. Read `{TICKER}/third-party-analyses/source_inventory_{date}.md`
2. Read every listed source (or document why skipped)
3. Write or complete `{TICKER}/research/cross_check_third_party_{date}.md` OR a named cross-check (`cross_check_McIntyre_*.md`, `cross_check_HK_*.md`, `cross_check_approved_substacks_*.md`)
4. Deep dive header links cross-check when material
5. Verify: `python _system/scripts/check_cross_checks.py {TICKER}`

### When no third-party exists

Cross-check is still **required**. Document: *"Marvin floor only; no third-party indexed as of {date}."*

### When third-party is added later

Re-run scan + update cross-check (do not leave stale inventory).

---

## Cross-check template (required sections)

1. **Executive summary** — one paragraph synthesis
2. **Sources in scope** — table from inventory (every row reviewed)
3. **Agreements (facts)** — Marvin vs external on business mechanics
4. **Divergences** — normalization, horizon, multiple, stance
5. **Blended estimate (best judgment)** — per `external_view_blend.md`
6. **[HUMAN REVIEW]** — approval gates
7. **Primary sources cited** — dive + inventory + each external path

Existing specialized cross-checks (QDEL McIntyre, FRMO Substacks) satisfy this requirement if they cover all inventory sources.

---

## Pipeline integration

| Step | Script |
|------|--------|
| Scan all sources | `scan_third_party_sources.py` |
| HK scan (TPL, ICE, MSB, SJT) | `scan_hk_sources.py` (via `--with-hk`) |
| Scaffold cross-check | `scaffold_cross_check.py` |
| QA all holdings | `check_cross_checks.py` |
| Full refresh | `marvin_cloud_refresh.py` (runs scan before valuation) |

```bash
make third-party-scan-all      # inventory for all holdings
make cross-check-all           # verify all holdings
make cross-check-all STRICT=1  # fail on incomplete stubs
```

---

## Adding a new ticker to the universe

1. `onboard_ticker.py` (creates folder + registry entry)
2. `scan_third_party_sources.py {TICKER} --with-hk`
3. `scaffold_cross_check.py {TICKER}`
4. Complete cross-check before first deep dive is marked final
5. Add Substacks / PDFs to `references.md` as discovered; re-scan

---

## Review pipeline

Material cross-checks → `_system/reviews/pending/{TICKER}_cross_check_*.md` → human discussion → `_system/reviews/approved/` → optional `valuation.json` `estimates.external[]`
