# Short activist / forensic research registry

**Generated from:** `_system/frameworks/activist_firm_registry.json` (2026-10-07).
**Do not edit the firm tables by hand.** Change the JSON, then run `python _system/scripts/render_short_activist_registry.py`.

Long and press campaigns stay in `_system/frameworks/activist_press_ingest.md`.

**Purpose:** Milly (adversarial reviewer) scans these publishers for reports on portfolio tickers. Not every name has coverage on every holding.

**Use:** Cross-reference only. A short report is **evidence to reconcile**, not a veto. Goal = **truth**, not bearishness for its own sake. Firms with side `both` are included because they publish shorts as well as longs.

---

## Tier 1 — Forensic short specialists (priority scan)

| Firm | Active | Ingest | What it is for |
|------|--------|--------|----------------|
| **Anson Funds** | yes | manual | — |
| **Blue Orca Capital** | yes | manual | Cloudflare WAF returns 403 to non-browser clients (verified 2026-08-26); site_index cannot fetch it. |
| **Bonitas Research** | yes | site_index | — |
| **Boring Business Research** | yes | manual | — |
| **Bucephalus Research** | yes | manual | Accounting, often Asia. |
| **Citron Research** | no | site_index | — |
| **Culper Research** | yes | manual | Cloudflare WAF returns 403 to non-browser clients (verified 2026-08-26); site_index cannot fetch it. |
| **Fuzzy Panda Research** | yes | site_index | — |
| **Glaucus Research** | no | manual | — |
| **Gotham City Research** | yes | site_index | — |
| **Grizzly Research** | yes | site_index | — |
| **Hindenburg Research** | no | site_index | Wound down January 2025 (Nate Anderson). Archive only, no new reports. |
| **Iceberg Research** | no | site_index | icebergresearch.com is a parked HugeDomains page as of 2026-08-26 — the site is gone. |
| **J Capital Research** | yes | manual | TLS chain fails verification even against the certifi bundle (verified 2026-08-26). |
| **Kerrisdale Capital** | yes | site_index, press_wire | Long/short letters and accounting. |
| **Morpheus Research** | yes | site_index | Founded 2025 by former Hindenburg staff. |
| **Muddy Waters Research** | yes | site_index | site:muddywatersresearch.com {TICKER} |
| **Scorpion Capital** | yes | site_index | — |
| **Spruce Point Capital** | yes | site_index | Spruce Point {company} |
| **Viceroy Research** | yes | site_index | — |
| **Wolfpack Research** | yes | site_index | — |

## Tier 2 — Activist shorts / hedge letters (secondary)

| Firm | Active | Ingest | What it is for |
|------|--------|--------|----------------|
| **Anathema Research** | yes | manual | Smaller forensic shorts. |
| **Bleecker Street Research** | yes | site_index | — |
| **BMF Reports** | yes | manual | Short letters. |
| **Chanos & Co.** | yes | manual | — |
| **Fugazi Research** | yes | manual | Local scorecard of published short reports versus the pre-report close. A row is a lead, not a thesis. |
| **Greenlight Capital** | yes | sec_13d, press_wire | — |
| **Hunterbrook Media** | yes | site_index | — |
| **Jehoshaphat Research** | yes | site_index | — |
| **Marcus Aurelius Value** | yes | manual | — |
| **Mariner Research** | yes | manual | — |
| **Night Market Research** | yes | manual | — |
| **Quintessential Capital** | yes | manual | — |
| **ShadowFall** | yes | manual | — |
| **Snowcap Research** | yes | site_index | — |
| **Unemon Research** | yes | manual | Short letters. |
| **White Diamond Research** | yes | manual | Short letters. |

---

## Non-short bears (Milly disclosure scan)

| Type | Search hints | Verdict in adversarial |
|------|--------------|------------------------|
| **SEC securities litigation** | `{company} class action 10b-5` | `litigation`. Not an automatic bear case. |
| **Late filing (OTC)** | `NT 10-K` `Notification of Late Filing` | `disclosure: hit` |
| **Restatement / non-reliance** | `should no longer be relied upon` Item 4.02 | `disclosure: hit` |
| **Auditor change** | `8-K` auditor resignation | `needs_human` |

---

## Scan universe

The scan universe is every holding in `_system/portfolio/registry.json`. A feed-eligible short in `{TICKER}/third-party-analyses/activist_reports_index.json` becomes a **lead** on the Shorts tab. It does not become a position.

Milly logs **hit / no hit / unclear** per ticker per refresh.

---

## Reconciliation rules (Milly)

1. **If short report exists:** Summarize **falsifiable claims** (numbers, accounting, legal).
2. **Check each claim** against latest 10-K/10-Q or local equivalent in `{TICKER}/investor-documents/`.
3. **Map to Marvin dive:** Did the deep dive address it? If not, record a **gap**. That is not an automatic downgrade.
4. **Verdict types:** `refuted_by_filing` | `partially_valid` | `unaddressed` | `stale` | `needs_human`
5. **Do not** change stance or IRR without human review unless there is a **factual error** in Marvin numbers (lint-level).

---

## Maintenance

- Add new firms in `activist_firm_registry.json`, then regenerate this file.
- Mark **inactive** firms; keep them for historical tickers.
- Store found reports in `{TICKER}/third-party-analyses/activist_reports/{long|short}/` with metadata in `activist_reports_index.json`.
- Markdown summaries may also live in `{TICKER}/third-party-analyses/short_reports/` with `source`, `date`, `url`, `summary.md`.
