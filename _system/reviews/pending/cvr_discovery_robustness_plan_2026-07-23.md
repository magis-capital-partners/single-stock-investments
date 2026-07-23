# CVR auto-discovery + robustness plan

**Date:** 2026-07-23  
**Status:** Parts 1–4 implemented (awaiting merge)  
**Goal:** Automatically find new CVR / contingent-consideration candidates (SEC + secondary feeds), land them safely in the universe, and harden the sleeve/dashboard loop so discovery never breaks deploys.

---

## Operating model (unchanged)

| Book | Role |
|------|------|
| **Pre-close** | Opportunity funnel — still-listed target with contingent kicker |
| **Post-close** | Claim inventory — onboarded `*.CVR` stubs |

Pinned dashboard filter: **CVRs** (`cvr_all`) after All.

---

## Four parts

### Part 1 — Turn discovery on (schedule + secondary inbox + fail-soft) ✓

| Deliverable | Detail |
|-------------|--------|
| Scheduled discover | Weekly job in Data Pipeline (no new workflow file; 20-workflow cap) |
| Secondary CSV inbox | Auto-ingest `_system/reference/cvr/inbox/*.csv` → move to `inbox/processed/` |
| Fail-soft SEC | Never fail the job / never block Pages if EDGAR is down |
| Review queue | Write `_system/reviews/pending/cvr_discovery_YYYY-MM-DD.md` when +N candidates |
| Discovery health | Track consecutive empty/fail runs on `cvr_universe.json.discovery_state` |
| Sleeve guardrail | Only sleeve tickers with **complete** `cvr_terms.json` (not stubs) |
| Sync isolation | Discover job uses `--skip-sync` |

### Part 2 — High-quality SEC candidate pipeline ✓

| Deliverable | Detail |
|-------------|--------|
| CIK → ticker | Resolve tradeable **target** via company_tickers; deprioritize mega-cap acquirers |
| Filing filters | Prefer 8-K / DEFM14A / PREM14A / S-4; drop 10-K/10-Q risk-factor hits |
| Dedupe | By accession number + CIK; multi-filing updates `accessions[]` |
| Stub onboard | `{TICKER}/` + skeleton `cvr_terms.json` (`stub=true`) + `authorized_evidence.json` |
| Provenance | `research_agent_manifest.json` via `build_research_agent_manifest` |
| Expanded SEC queries | Contingent consideration / earnout family (context tier) |

### Part 3 — Secondary feeds that actually work ✓

| Deliverable | Detail |
|-------------|--------|
| Inbox contract | Documented CSV schema; reject rows without ticker |
| AlphaRank drop | `--sync-alpharank` + `CVR_ALPHARANK_DROP_PATH` / `ALPHARANK_CSV_PATH` |
| Non-SEC contingents | `--discover-non-sec-family` ECIP/bank heuristic SEC query |
| Alerting | Review note + optional Slack (`SLACK_WEBHOOK_URL`) for new / unhealthy / outside&lt;90d |
| Staging sleeve | Optional `--enable-watch-sleeve` → `cvr_watch` |

### Part 4 — Monitoring robustness ✓

| Deliverable | Detail |
|-------------|--------|
| Prices / p_market | `--refresh-prices` (Yahoo chart API) |
| Milestone refresh | `--refresh-milestones` heuristic on linked SEC HTML |
| Stage transitions | `--apply-transitions` pre→post; preserves `stage_history` |
| Integrity | `check_cvr_universe.py` (warn default; `--strict` fails) |
| Scoped sleeve sync | Only rewrites `cvr_contingent` (+ optional `cvr_watch`) membership |
| Agent handoff | `_system/data/cvr_agent_queue.json` via `--queue-stubs` / stub create |

---

## Target architecture

```text
Weekly Data Pipeline (cvr_discover)
  SEC --discover (+ expanded + non-sec family), fail-soft
  + AlphaRank drop → inbox/*.csv ingest
  + --create-stubs
       ↓
  cvr_universe.json (pre_close candidates, context tier)
  + stub folders (terms incomplete)
  + reviews/pending/cvr_discovery_*.md (+ Slack)
       ↓
Agent fills cvr_terms.json (stub=false, terms_complete=true)
       ↓
Nightly sync
  --refresh-prices --apply-transitions --queue-stubs
  sleeve (terms-complete only) → registry → dashboard CVRs filter
  check_cvr_universe.py
```

---

## Part checklist

- [x] **Part 1** — schedule, inbox, fail-soft, review, sleeve-ready policy  
- [x] **Part 2** — CIK, filters, stubs, expanded SEC queries  
- [x] **Part 3** — inbox schema hardening, AlphaRank path, alerts, non-SEC family  
- [x] **Part 4** — prices, milestones, transitions, integrity, scoped sync  

---

## Secrets / vars needed (human)

| Name | Type | Required? | Use |
|------|------|-----------|-----|
| `SLACK_WEBHOOK_URL` | Actions secret | Optional | Discovery / outside-date alerts |
| `CVR_ALPHARANK_DROP_PATH` | Actions variable | Optional | Folder/file of AlphaRank CSVs on runner or mounted Drive |
| AlphaRank login | External | Optional | No public API found — export CSV manually or script outside CI |

Other useful sources (no keys in-repo yet): OTC Markets news (MFBP-class), BioPharmCatalyst / FierceBiotech deal wires, EDGAR full-text (free), CourtListener for CVR litigation.

---

## Success metrics

1. New US pharma/biotech CVR 8-K appears in `pre_close_opportunities` within 7 days without human scrape.  
2. Dropping a screener CSV in `inbox/` adds candidates the next weekly run.  
3. SEC outage does not fail Data Pipeline or dashboard deploy.  
4. Raw candidates / stubs never appear on the pinned CVRs filter until terms are complete.  
