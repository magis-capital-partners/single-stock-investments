# AIG — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin  
**Marvin dive:** `AIG/research/deep_dive_2026-07-21.md`  
**Source inventory:** `AIG/third-party-analyses/source_inventory_2026-07-21.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for AIG as of 2026-07-21. Activist SC-13G filings in `third-party-analyses/activist_reports/` document historical institutional ownership but are **context tier** only and not promoted to base IRR. Marvin stance rests on **primary filings** (FY2025 10-K, Q1 2026 10-Q). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none approved) | Primary filings only | `AIG/investor-documents/sec-edgar/` | primary | Base IRR anchor |
| activist context | SC-13G/A filings (multiple) | `AIG/third-party-analyses/activist_reports/long/` | context | Ownership history; not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Post-Corebridge focus | General Insurance three-segment platform | n/a | FY2025 10-K |
| Capital return | ~$3.9B repurchase authorization remaining | n/a | FY2025 10-K |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash metric | Adjusted after-tax income $7.09/sh | n/a | Filings-only |
| Book vs economic value | Component sum $76/sh vs adjusted book $78/sh | n/a | No external weight |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | ~$76/sh component sum | Lawrence base (mechanical sync) | watch |
| External (combined) | n/a | n/a | n/a |
| **Blended best estimate** | **~$76/sh** | **Filings-only** | **watch** |

**Weights:** 100% Marvin primary; no approved external sources.

**Returns statement (blended):** Pending mechanical Lawrence sync from `marvin_cloud_refresh.py`; filings-only base uses adjusted after-tax income $7.09/sh at ~$79.80 price.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AIG: third-party cross-check 2026-07-21; filings-only; activist SC-13G context tier.

## Primary sources cited

1. `AIG/research/deep_dive_2026-07-21.md`
2. `AIG/third-party-analyses/source_inventory_2026-07-21.md`
3. `AIG/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0000005272_26_000023.htm`
4. `AIG/investor-documents/sec-edgar/10-Q_20260501_rpt20260331_acc0000005272_26_000052.htm`
