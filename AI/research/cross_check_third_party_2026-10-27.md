# AI — Cross-Check: Third-Party Sources

**Date:** 2026-10-27  
**Agent:** Marvin  
**Marvin dive:** `AI/research/deep_dive_2026-10-27.md`  
**Source inventory:** Phase 3 scan (`source_inventory_2026-10-27.md` when present); prior `source_inventory_2026-10-18.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party research sources are in `_system/frameworks/third_party_sources.md` for C3.ai. Institutional SC-13G filings under `third-party-analyses/activist_reports/long/` remain **context tier** only. The admitted evidence packet (`DOWNLOAD_MANIFEST.json` + `authorized_evidence.json`) is unchanged since the 2026-10-18 refresh; filing extracts and Marvin floor are unchanged.

**Synthesis:** Marvin floor only; no external blend. Universal contract remains **evidence_blocked** on prospective falsifier coverage (see `evidence_reconciliation_2026-10-27.md`).

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| primary | Filing digest / facts | `AI/research/evidence/filing_digest_2026-10-15.md`, `filing_facts_2026-10-15.json` | primary | Base case |
| manifest | Download manifest | `AI/investor-documents/DOWNLOAD_MANIFEST.json` | primary | Filing cadence |
| authorized | Contract blockers | `AI/research/authorized_evidence.json` | primary | Falsifier gate list |
| SC-13G* | Institutional holdings | `third-party-analyses/activist_reports/long/` | context | Not in IRR |
| insider | Insider panel | `AI/research/evidence/insider_signal_2026-10-15.md` | context | Not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue decline | FY2026 **$227.1M** vs FY2025 **$327.6M** | News themes align | filing_facts |
| Balance sheet | **$66.2M** cash; no long-term debt Apr-26 | n/a | 10-K FY2026 |
| CEO trading | Mixed Siebel 10b5-1 sales vs June purchase | Insider panel | insider_signal |

## Divergences

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash | **$0.80/sh** **[Assumption]** | No approved external estimate | Marvin-only |
| Contract | Four-component sum; **evidence_blocked** | n/a | No blend until falsifier gate clears |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.80/sh**; component base ~**$21/sh** | Synthesis per `valuation.json` (7-year model) | watch |
| External | — | — | — |
| **Blended best estimate** | **$0.80/sh** | Marvin synthesis (no approved external inputs) | **watch** |

**Weights:** 100% Marvin primary.

**Returns statement (blended):** With no approved third-party inputs, the blended best estimate equals Marvin synthesis at the mechanical price stub, subject to moat and owner-cash verification **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- Promote any Substack or fund letter to `third_party_sources.md` before inclusion in base IRR.
- SC-13G filings remain context tier only.

## Primary sources cited

1. `AI/research/deep_dive_2026-10-27.md`
2. `AI/research/authorized_evidence.json`
3. `AI/investor-documents/DOWNLOAD_MANIFEST.json`
