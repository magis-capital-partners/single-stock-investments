# AVAV — Cross-Check: Third-Party Sources

**Date:** 2026-07-20  
**Agent:** Marvin  
**Marvin dive:** `AVAV/research/deep_dive_2026-07-20.md`  
**Source inventory:** `AVAV/third-party-analyses/source_inventory_2026-07-20.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party research sources are indexed for AVAV as of this scan (0 approved, 0 pending, 0 context). Marvin stance rests on **primary SEC filings** only via `DOWNLOAD_MANIFEST.json` and `sec_companyfacts.json`. Activist SC-13G filings in the third-party folder are ownership disclosures only, not investment theses.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Source | Path | Status | Use |
|----|--------|------|--------|-----|
| (none) | Primary filings only | `AVAV/investor-documents/DOWNLOAD_MANIFEST.json` | filing | Base case |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale post-BlueHalo | FY2026 revenue **$1,976.8M** | n/a | 10-K FY2026; sec_companyfacts |
| Funded backlog | **~$1,183M** at Apr 30, 2026 | n/a | 10-K Item 1 |
| Integration-year losses | GAAP operating loss **-$311M**; goodwill impairment **~$241M** | n/a | 10-K FY2026 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Normalized owner cash | Segment adj EBITDA bridge to **~$2.75/sh** [Assumption] | n/a | No external view to reconcile |
| Stance | **watch** (integration + IRR gate) | n/a | Primary only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | ~$2.75/sh normalized owner cash | Pending mechanical IRR | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **Pending refresh** | **watch** |

**Weights:** No approved external sources; 100% primary filings.

**Returns statement (blended):** Pending `marvin_cloud_refresh.py` Lawrence and synthesis outputs.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only (none)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added later

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AVAV refresh 2026-07-20: BlueHalo integration year; funded backlog $1.18B; watch stance on normalized owner cash vs price.

## Primary sources cited

1. `AVAV/investor-documents/sec-edgar/10-K_20260629_rpt20260430_acc0001104659_26_078906.htm`
2. `AVAV/research/evidence/sec_companyfacts.json`
3. `AVAV/investor-documents/DOWNLOAD_MANIFEST.json`
4. `AVAV/third-party-analyses/source_inventory_2026-07-20.md`
