# Third-party sources (approval workflow)

**Purpose:** Marvin may **blend** only human-approved external research into IRR and stance. Everything else is cited as **pending** until you approve.

**Approved today:** See `approved_substacks.md` (SSI, Lemon Cakes).  
**This file:** Proprietary letters, sell-side notes, fund letters, and other PDFs in ticker folders.

---

## Status levels

| Status | Marvin may use in IRR / stance? | Where to register |
|--------|----------------------------------|-------------------|
| **approved** | Yes — full blend per `external_view_blend.md` | Row in **Approved registry** below |
| **context** | No — cite for mental models / cross-check; not in base IRR | `{TICKER}/third-party-analyses/hk_scan_*.md` + `hk_ticker_index.json` |
| **pending** | No — cite in report, flag **[PENDING APPROVAL]** | `{TICKER}/third-party-analyses/pending.md` |
| **rejected** | No — do not cite | Note in pending file with date |

**Horizon Kinetics** quarterly commentaries and Stahl shelf essays default to **context** until human adds an approved row. Workflow: `hk_cross_reference.md`.

---

## Approved registry

| ID | Publisher | Tickers | Path | Approved |
|----|-----------|---------|------|----------|
| `ssi` | Special Situation Investing | FRMO, CMSG, KEWL, … | `approved_substacks.md` | 2026-05-26 |
| `lci` | Lemon Cakes Investing | FRMO, CMSG, … | `approved_substacks.md` | 2026-05-26 |
| `mcintyre` | McIntyre Partnerships | QDEL | `QDEL/investor-documents/research-notes/McIntyre_Partnerships_Q1_2026_Letter.pdf` | **2026-05-28** (human: yes — QDEL blend) |
| `apld_pf3_summary` | Applied Digital / Marvin shop summary (PF3 PR) | APLD | `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md` | **2026-05-28** (human: yes) |
| `apld_reiterate_buy` | Research note (run-the-table bull case) | APLD | `APLD/investor-documents/research-notes/What Would A Run The Table Scenario Look Like_ Reiterate BUY.pdf` | **2026-05-28** (human: yes — catalyst / bull framing; not sole IRR anchor) |
| `sohn_rosen_vtrs` | Sohn Conference Foundation / David Rosen (Rubric Capital) | VTRS | `VTRS/investor-documents/research-notes/2026-05-27_Sohn_Digging_Deeper_VTRS_excerpt.md` | **2026-06-02** (human: yes — Idorsia Phase III catalyst / deep-value framing; not sole IRR anchor) |
| `hk_context_teq` | HK extracts + inventory context (TEQ.ST) | TEQ.ST | `TEQ.ST/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved for synthesis blend) |
| `hk_context_tpl` | HK + SSI + LCI context (TPL) | TPL | `TPL/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_frmo` | HK + SSI + LCI context (FRMO) | FRMO | `FRMO/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_cmsg` | HK + SSI + LCI + IR PDFs (CMSG) | CMSG | `CMSG/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_msb` | HK + SSI context (MSB) | MSB | `MSB/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_ice` | HK context (ICE) | ICE | `ICE/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_sjt` | HK context (SJT) | SJT | `SJT/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_kewl` | HK + SSI context (KEWL) | KEWL | `KEWL/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |

---

## Pending registry (human action required)

Marvin scans `{TICKER}/investor-documents/research-notes/` and flags new files here.

| Ticker | File | Type | Status |
|--------|------|------|--------|
| — | — | — | *(none)* |

**To approve:** Add a row to **Approved registry**, update `valuation.json` → `estimates.external[]`, re-run refresh.

---

## Per-ticker files

| File | Purpose |
|------|---------|
| `{TICKER}/third-party-analyses/references.md` | Index of approved + pending URLs/PDFs + HK scan |
| `{TICKER}/third-party-analyses/hk_scan_{date}.md` | Auto HK / Stahl source map (`scan_hk_sources.py`) |
| `{TICKER}/third-party-analyses/pending.md` | Queue for human approval |
| `{TICKER}/research/cross_check_*` | Agreements / divergences / synthesis |

---

## Report language

- **Approved:** “McIntyre (approved third party) assumes …” / “Polaris bull note (approved) …”
- **Pending:** “(**[PENDING APPROVAL]** — not in IRR) …”
- Never fold pending sources into `valuation.json` base IRR without approval.

---

## Discovery on refresh

- `scan_third_party_sources.py` — **every universe ticker**: build `source_inventory_{date}.md` (approved, pending, Substacks, HK, research-notes, shorts).
- `scan_hk_sources.py` — HK-indexed tickers only (called via `--with-hk`).
- `scaffold_cross_check.py` / agent narrative — **required** `cross_check_third_party_{date}.md` or named cross-check per `third_party_cross_reference.md`.
- `check_cross_checks.py` — verify inventory + cross-check exist for registry holdings.
- `refresh_deep_dive_v2.py` — append new `research-notes/` PDFs to `pending.md`.
