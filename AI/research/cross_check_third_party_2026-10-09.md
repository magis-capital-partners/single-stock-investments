# AI — Cross-Check: Third-Party Sources

**Date:** 2026-10-09  
**Agent:** Marvin  
**Marvin dive:** `AI/research/deep_dive_2026-10-09.md`  
**Source inventory:** `AI/third-party-analyses/source_inventory_2026-07-25.md` (latest indexed; mechanical scan in Phase 3)  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party research sources are in `_system/frameworks/third_party_sources.md` for C3.ai. Institutional SC-13G filings under `third-party-analyses/activist_reports/long/` remain **context tier** only. News and insider panels were checked against FY2026 10-K and Q3 FY2026 10-Q extracts; there is no external valuation to blend into base IRR.

**Synthesis:** Marvin floor only; no external blend. Universal contract remains **evidence_blocked** on prospective falsifier coverage for the `cycle_reserve` component (see `authorized_evidence.json`).

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| primary | Filing digest / facts | `AI/research/evidence/filing_digest_2026-08-06.md`, `filing_facts_2026-08-06.json` | primary | Base case |
| manifest | Download manifest | `AI/investor-documents/DOWNLOAD_MANIFEST.json` | primary | Filing cadence |
| SC-13G* | Institutional holdings | `third-party-analyses/activist_reports/long/` | context | Not in IRR |
| news | News index | `AI/research/news/news_index.json` | context | Catalyst flags |
| insider | Insider panel | `AI/research/evidence/insider_signal_2026-10-08.md` | context | Not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue decline | FY2026 **$227.1M** vs FY2025 **$327.6M** | News continues to cite post-peak revenue pressure | filing_facts_2026-08-06.json |
| Balance sheet | **$66.2M** cash; no long-term debt Apr-26 | n/a | 10-K FY2026 |
| CEO trading | Siebel June 2026 open-market purchase; later 10b5-1 sales | News aligns on mixed signal | insider_signal_2026-10-08.md |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash | **$0.80/sh** normalized **[Assumption]** | No third-party owner-cash estimate | Marvin-only |
| Contract value | Four-component sum; **evidence_blocked** | n/a | No blend until falsifier gate clears |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.80/sh** owner cash; component base ~**$20.98/sh** at prior price stub | Lawrence base **30.6%** per year (7-year model); contract legacy audit ~**9.9%** at **$10.82** | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$0.80/sh** owner cash | **30.6%** Lawrence base (no approved external inputs) | **watch** |

**Weights:** 100% Marvin primary.

**Returns statement (blended):** With no approved third-party inputs, the blended best estimate equals Marvin Lawrence base **30.6%** per year over seven years at the modeled price, subject to moat and owner-cash verification **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- Promote any Substack or fund letter to `third_party_sources.md` before inclusion in base IRR.
- SC-13G filings remain context tier only.
- Re-run `scan_third_party_sources.py` after Phase 3 if inventory date advances beyond 2026-07-25.

## Primary sources cited

1. `AI/research/deep_dive_2026-10-09.md`
2. `AI/research/evidence/filing_facts_2026-08-06.json`
3. `AI/investor-documents/DOWNLOAD_MANIFEST.json`
4. `AI/research/authorized_evidence.json`
