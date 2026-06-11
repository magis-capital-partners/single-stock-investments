# MTA — Cross-Check: Third-Party Sources

**Date:** 2026-06-11
**Agent:** Marvin
**Marvin dive:** `MTA/research/deep_dive_2026-06-11.md`
**Source inventory:** `MTA/third-party-analyses/source_inventory_2026-06-11.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for MTA. Marvin stance rests on **primary filings** (40-F exhibits 99-1/2/3) and IR materials (May 2026 corporate presentation, March 2026 factsheet). Company-cited sell-side consensus NAV (**$7.75**/share) and average price target (**$9.75**) appear in IR factsheet only and are flagged **[PENDING APPROVAL]** for base IRR.

**Synthesis:** Marvin floor only; no external blend in base case.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| SEC exhibit99-1/2/3 (FY2025) | Primary filing | in folder | Revenue, cash flow, GEOs, debt |
| IR corporate presentation May 2026 | Primary IR | in folder | GEO outlook, NPV by stage |
| IR factsheet Mar 2026 | Primary IR | in folder | Capital structure, consensus NAV |
| Sell-side consensus (via IR) | External aggregate | **[PENDING APPROVAL]** | NAV **$7.75**; target **$9.75** |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue | **$11.7M** | n/a | exhibit99-3.htm |
| FY2025 operating cash | **$4.4M** | n/a | exhibit99-3.htm |
| FY2025 GEOs | **3,436** | n/a | exhibit99-3.htm |
| Portfolio size | **99** royalties/streams | n/a | factsheet.pdf |
| Debt | **$12.2M** long-term revolver | n/a | exhibit99-2.htm |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| NAV per share | Not in Lawrence FCF₀; overlay only | IR cites **$7.75** consensus NAVPS | Pending approval; context for NAV discount only |
| Return at price | Lawrence base **-16.3%** | IR implies upside to **$9.75** target | Do not blend into base IRR without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.048**/sh FY2025 operating cash | **-16.9%** Lawrence base / **-14.56%** synthesis | watch |
| External (combined) | Consensus NAV **$7.75** | Not in base IRR | context only |
| **Blended best estimate** | **Filing cash + unapproved NAV overlay** | **-14.56%** synthesis (Marvin-only base) | **watch** |

**Weights:** Marvin filing path **100%** for base IRR; consensus NAV **0%** until promoted in `third_party_sources.md`.

**Returns statement (blended):** At **$6.82** per share, Marvin expects about **-14.56%** per year on the total-synthesis base case using FY2025 operating cash per share; consensus NAV is cited for context only.

## [HUMAN REVIEW]

- [ ] Promote sell-side consensus NAV if human approves for overlay sizing
- [x] Primary SEC exhibits downloaded and cited
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material external source approved

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] MTA cross-check 2026-06-11: filings-only base; IR consensus NAV pending approval.

## Primary sources cited

1. `MTA/investor-documents/sec-edgar/exhibit99-2.htm`
2. `MTA/investor-documents/sec-edgar/exhibit99-3.htm`
3. `MTA/investor-documents/ir-mta/factsheet.pdf`
4. `MTA/research/deep_dive_2026-06-11.md`
