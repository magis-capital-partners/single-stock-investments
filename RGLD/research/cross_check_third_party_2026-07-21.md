# RGLD — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin (contract backfill)  
**Marvin dive:** `RGLD/research/deep_dive_2026-07-21.md`  
**Source inventory:** `RGLD/third-party-analyses/source_inventory_2026-07-20.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin base **8.06%** per year (total synthesis) and Lawrence owner-cash path **6.7%** per year from primary filings and `valuation.json`. Proof-first component schedule base **~$152/sh** vs price **~$217**. One pending VIC PDF and historical activist SC 13D filings are **context only**; no approved third-party source is in base IRR.

**Synthesis (best estimate):** Marvin **8.06%** base · stance **watch**; external sources adjust conviction on catalyst timing, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| vic | VIC PDF intake | `RGLD/third-party-analyses/vic/vic_pdf_2026-06-20_rgld-vic-pdf_21b5ea5eca.pdf` | pending | **[PENDING APPROVAL]** |
| activist_long | Elliott SC 13D series (2018–2020) | `RGLD/third-party-analyses/activist_reports/long/` | context | ownership context only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| High-margin royalty model | ~62% operating margin FY2025 | VIC likely agrees qualitatively | 10-K FY2025 |
| Sandstorm scale step-change | Revenue +43% YoY FY2025 | Not numerically blended | 10-K FY2025 |
| Base return anchor | **8.06%** synthesis / **6.7%** Lawrence | No approved numeric IRR | `valuation.json` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **6.7%–8.06%** (Lawrence / synthesis) | Pending VIC not in base | Marvin **100%** numeric until human promotes |
| Component value | **~$152/sh** base proof schedule | Market **~$217** embeds optionality | Gap is development timing and gold cycle, not filing error |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$9/sh** owner cash; **~$152/sh** components | **8.06%** synthesis | **watch** |
| External (combined) | Narrative / catalyst | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | **8.06%** | **watch** |

**Weights:** Marvin **100%** on numbers until VIC or other sources are human-approved; indexed third party **0%** numeric (context on governance and activism only).

**Returns statement (blended):** We expect **8.06%** per year at today's price on the Marvin synthesis base case; pending third-party sources may raise or lower conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Review pending VIC PDF before any numeric promotion
- [ ] Confirm activist SC 13D context remains non-material to base case
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## Primary sources cited

1. `RGLD/investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0000085535_26_000008.htm`
2. `RGLD/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0000085535_26_000028.htm`
3. `RGLD/research/valuation.json`
4. `RGLD/research/evidence_reconciliation_2026-07-21.md`
