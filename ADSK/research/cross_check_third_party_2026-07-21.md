# ADSK — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin  
**Marvin dive:** `ADSK/research/deep_dive_2026-07-21.md`  
**Source inventory:** `ADSK/third-party-analyses/source_inventory_2026-07-10.md` *(Phase 3 refresh)*  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

---

## Executive summary

No **approved** third-party sources are in `_system/frameworks/third_party_sources.md` for ADSK as of this scan. Marvin stance rests on **primary filings** (FY2026 10-K, Q1 FY2027 10-Q). **Context tier:** Starboard Value activist proxy materials (Mar 2025) and Soroban Capital passive 13G (2018) are indexed but not in base IRR.

**Synthesis:** Marvin floor only; no external blend in base case.

---

## Sources in scope

| Source | Type | Tier | In base IRR? |
|--------|------|------|--------------|
| Primary filings (10-K, 10-Q) | SEC | primary | yes |
| Starboard DFAN14A (Mar 2025) | activist_proxy | context | no |
| Soroban SC-13G/A (Feb 2018) | registry_13g | context | no |
| *(none approved)* | — | — | — |

---

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Subscription model | ~98% recurring revenue; transition largely complete | Starboard agrees subscription shift improved predictability | FY2026 10-K; DFAN14A Mar 2025 |
| Capital return | $1.4B buybacks FY2026 | Starboard seeks larger buybacks / margin focus | FY2026 10-K; activist materials |
| RPO / backlog | $8.3B RPO at Jan 31, 2026 | n/a (no approved external) | FY2026 10-K |

---

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Margin expansion | Base case assumes steady non-GAAP margins | Starboard argues for sharper cost discipline and higher FCF conversion | **[PENDING APPROVAL]** — activist thesis not in base IRR |
| Growth durability | Base 6% owner-cash growth years 1–5 | No approved sell-side or Substack view indexed | Marvin-only |
| SBC / dilution | Reserve −$12/sh base for dilution risk | Starboard highlights SBC as governance issue | Context only; reserve captures partial bear |

---

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (component sum) | ~$254/sh base | Mechanical Lawrence synthesis (Phase 3) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$254/sh base** | **Marvin-only** | **watch** |

**Weights:** 100% Marvin primary until human promotes approved third-party sources.

**Returns statement (blended):** Base component sum ~$254 per share vs ~$218 price implies modest mid-single-digit annual return at today's price; stance **watch** pending human review of activist margin thesis and SBC normalization.

---

## [HUMAN REVIEW]

- [ ] Starboard activist materials: promote to approved registry or keep context-only?
- [ ] Re-run `scan_third_party_sources.py` when Substacks or fund letters added
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material external source approved

---

## Primary sources cited

1. `ADSK/investor-documents/sec-edgar/10-K_20260303_rpt20260131_acc0000769397_26_000015.htm`
2. `ADSK/investor-documents/sec-edgar/10-Q_20260529_rpt20260430_acc0000769397_26_000044.htm`
3. `ADSK/research/evidence_reconciliation_2026-07-21.md`
4. `ADSK/third-party-analyses/activist_reports/long/DFAN14A_20250326_acc0000921895_25_000885.htm` *(context)*
