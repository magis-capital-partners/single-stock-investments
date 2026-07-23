# CVR auto-discovery + robustness plan

**Date:** 2026-07-23  
**Status:** Part 1 implemented (awaiting merge); Parts 2–4 pending  
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

### Part 1 — Turn discovery on (schedule + secondary inbox + fail-soft) ← **NOW**

Make candidate finding automatic without touching the dashboard hot path.

| Deliverable | Detail |
|-------------|--------|
| Scheduled discover | Weekly job in Data Pipeline (no new workflow file; 20-workflow cap) |
| Secondary CSV inbox | Auto-ingest `_system/reference/cvr/inbox/*.csv` → move to `inbox/processed/` |
| Fail-soft SEC | Never fail the job / never block Pages if EDGAR is down |
| Review queue | Write `_system/reviews/pending/cvr_discovery_YYYY-MM-DD.md` when +N candidates |
| Discovery health | Track consecutive empty/fail runs on `cvr_universe.json.discovery_state` |
| Sleeve guardrail | Only sleeve tickers with `research/cvr_terms.json` (context candidates stay off the filter) |
| Sync isolation | Discover job uses `--skip-sync` so global classification churn stays out of discovery commits |

**Out of scope for Part 1:** CIK resolution, stub folders, live prices, milestone parsing.

---

### Part 2 — High-quality SEC candidate pipeline

| Deliverable | Detail |
|-------------|--------|
| CIK → ticker | Resolve tradeable **target** (not acquirer) via company_tickers.json |
| Filing filters | Prefer 8-K 1.01/2.01, DEFM14A/PREM14A, S-4; drop risk-factor-only hits |
| Dedupe | By accession number + CIK, not ticker alone |
| Stub onboard | Create `{TICKER}/` + skeleton `cvr_terms.json` + `authorized_evidence.json` |
| Provenance | Minimal research_agent_manifest so later agent PRs can clear the gate |
| Expanded SEC queries | Also: contingent consideration / earnout / additional merger consideration (context tier) |

---

### Part 3 — Secondary feeds that actually work

| Deliverable | Detail |
|-------------|--------|
| Inbox contract | Documented CSV schema + sample; reject rows without ticker |
| AlphaRank drop | Optional Drive/path sync into `inbox/` before weekly discover |
| Non-SEC contingents | Query/heuristic family for bank/ECIP/OTC (MFBP-class) from IR/news → still require primary docs |
| Alerting | Review + optional Slack when: new candidates, discovery unhealthy (N empty runs), outside date &lt; 90d |
| Staging sleeve (optional) | `cvr_watch` for context-only names if we want them visible before terms |

---

### Part 4 — Monitoring robustness

| Deliverable | Detail |
|-------------|--------|
| Prices / p_market | Quote tradeable vehicle; refresh display IRR @ buy limit |
| Milestone refresh | Re-read linked SEC HTML/PDF; update paid/failed/extended |
| Stage transitions | Pre → post on close/delist; preserve history |
| Integrity | `check_cvr_universe.py` in CI: universe ↔ terms ↔ sleeve ↔ dashboard `cvr` |
| Scoped sleeve sync | Update only CVR classification rows (no full-universe sleeve rewrite) |
| Agent handoff | Auto-queue Marvin task when new ready stub appears |

---

## Target architecture

```text
Weekly Data Pipeline (cvr_discover)
  SEC --discover (fail-soft)
  + inbox/*.csv ingest
       ↓
  cvr_universe.json (pre_close candidates, context tier)
  + reviews/pending/cvr_discovery_*.md
       ↓
Part 2: stub folders + CIK target resolve
       ↓
Agent fills cvr_terms.json
       ↓
Nightly sync (already hooked, no --discover)
  sleeve (terms-ready only) → registry → build_dashboard_data → CVRs filter
       ↓
Part 4: prices, milestones, integrity
```

---

## Part checklist

- [x] **Part 1** — schedule, inbox, fail-soft, review, sleeve-ready policy  
- [ ] **Part 2** — CIK, filters, stubs, expanded SEC queries  
- [ ] **Part 3** — inbox schema hardening, AlphaRank path, alerts, non-SEC family  
- [ ] **Part 4** — prices, milestones, transitions, integrity, scoped sync  

---

## Success metrics

1. New US pharma/biotech CVR 8-K appears in `pre_close_opportunities` within 7 days without human scrape.  
2. Dropping a screener CSV in `inbox/` adds candidates the next weekly run.  
3. SEC outage does not fail Data Pipeline or dashboard deploy.  
4. Raw candidates never appear on the pinned CVRs filter until `cvr_terms.json` exists.  
