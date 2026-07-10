# MO — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `MO/research/deep_dive_2026-07-10.md`
**Source inventory:** `MO/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

This cross-check triangulates **1** indexed third-party source against primary Altria filings. The sole approved entry (`hk_context_frmo`) is **FRMO / Horizon Kinetics portfolio context** and does **not** analyze Altria (MO). **Marvin floor only** for MO-specific owner cash and stance. No approved third-party source supports blending external return assumptions into base IRR.

**Synthesis (best estimate):** Lawrence consolidated base **~7.4%** per year at **$71.59** on FY2025 owner cash **$5.42** per share. Third-party adds no material adjustment.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| hk_context_frmo | HK + SSI + LCI context (FRMO) | `FRMO/third-party-analyses/references.md` | approved | [x] reviewed — not MO-specific |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| — | — | — | FRMO references cover FRMO, TPL, GBTC, MIAX — not Altria |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| MO tobacco economics | FY2025 FCF $9.1B; pricing offsets volume decline | No MO coverage in indexed source | 100% Marvin floor |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $5.42/sh FCF (FY2025 filed) | **7.4%** / 7yr base | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$5.42/sh** | **7.4%** | **watch** |

**Weights:** 100% Marvin filings — indexed approved source does not address MO.

**Returns statement (blended):** At today's price, we expect about **7.4%** per year over 7 years on filed owner cash; no third-party blend applied.

## [HUMAN REVIEW]

- [x] Every **approved** source reviewed against filings (FRMO context — not MO-relevant)
- [x] Every **pending** source cited with **[PENDING APPROVAL]** only (none indexed)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material (not material)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] MO: third-party cross-check 2026-07-10 — Marvin floor only; FRMO/HK context source does not cover Altria.

## Primary sources cited

1. `MO/research/deep_dive_2026-07-10.md`
2. `MO/third-party-analyses/source_inventory_2026-07-10.md`
3. `FRMO/third-party-analyses/references.md`
4. `MO/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0000764180_26_000017.htm`
5. `MO/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0000764180_26_000058.htm`
