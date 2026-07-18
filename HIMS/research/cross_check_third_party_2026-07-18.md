# HIMS — Cross-Check: Third-Party Sources

**Date:** 2026-07-18  
**Agent:** Marvin  
**Marvin dive:** `HIMS/research/deep_dive_2026-07-18.md`  
**Source inventory:** `HIMS/third-party-analyses/source_inventory_2026-07-18.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed in the automated scan as of 2026-07-18. Marvin stance rests on **primary SEC filings** (FY2025 10-K, Q1 2026 10-Q, DEF 14A). A Spruce Point short report on Hims & Hers exists in the workspace reference library (`_system/reference/activist-reports/spruce_point/`) but is **not approved** and was not indexed by `scan_third_party_sources.py`; treat as **[PENDING APPROVAL]** context only if human promotes.

**Synthesis:** Marvin floor only; no external blend in base IRR.

## Sources in scope

| ID | Title | Path | Status | Reviewed |
|----|-------|------|--------|----------|
| (none indexed) | Primary filings only | `HIMS/investor-documents/sec-edgar/` | n/a | Yes |
| (reference only) | Spruce Point Hims & Hers report | `_system/reference/activist-reports/spruce_point/spruce_point_2023-07-13_hims-hers-health-inc.html` | **[PENDING APPROVAL]** | Skipped (not in inventory; dated 2023) |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | FY2025 revenue **$2.35B** (+59% YoY) | n/a | 10-K FY2025 |
| Profitability | FY2025 operating income **$105.6M**; net income **$128.4M** | n/a | 10-K FY2025 |
| GLP-1 regulatory risk | FDA February 2026 statement named company on compounded semaglutide | Spruce Point (2023) flagged compounding/marketing practices **[PENDING APPROVAL]** | 10-K Risk Factors |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Normalized owner cash | **$0.80/sh** after marketing and capex haircut on **$300M** FY2025 OCF | Spruce Point (2023) argued aggressive accounting/marketing **[PENDING]** — not in base | No blend; filings ground OCF and capex |
| Growth outlook | Q1 2026 revenue **+3.8%** YoY deceleration | n/a indexed | Base growth **10%** years 1–5 is **[Assumption]** citing slowdown |
| Stance | **watch** at **~0.7%** Lawrence base IRR | n/a | Marvin floor only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.80/sh** normalized | **~0.7%** per year (7yr Lawrence base) | watch |
| External (combined) | n/a | n/a | n/a |
| **Blended best estimate** | **$0.80/sh** | **~0.7%** per year | **watch** |

**Weights:** 100% Marvin floor (no approved external sources).

**Returns statement (blended):** At **$32.84**, Marvin base case is **~0.7%** per year on **$0.80** per share normalized owner cash; pending activist material is context only.

## [HUMAN REVIEW]

- [ ] Promote Spruce Point or other third-party sources to inventory if material to stance
- [ ] Confirm GLP-1 revenue mix and FDA compliance path with management or subsequent 8-K disclosures
- [ ] Blended estimate remains Marvin-only until human approves external sources

## Primary sources cited

1. `HIMS/investor-documents/sec-edgar/10-K_20260223_rpt20251231_acc0001773751_26_000022.htm`
2. `HIMS/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001773751_26_000076.htm`
3. `HIMS/research/evidence/filing_facts_2026-07-18.json`
4. `HIMS/third-party-analyses/source_inventory_2026-07-18.md`
