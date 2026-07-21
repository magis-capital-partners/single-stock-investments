# AAOI valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (evidence hash `9c4deab9…`).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_operating_owner_cash` | legacy_sensitivity (via `operating_business_fallback`) | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $15.00 |
| `amazon_datacenter_option` | unmodeled | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.30 |
| `net_surplus_cash` | unmodeled | net_asset_value@1.0 | bounded_estimate | $3.67 |
| `dilution_concentration_reserve` | unmodeled | net_asset_value@1.0 | bounded_estimate | −$1.50 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys replace `operating_business_fallback`: normalized owner-cash engine, Amazon/datacenter option, net surplus cash, dilution/concentration reserve. |
| source path | `AAOI/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$17.47/sh** = $15.00 + $0.30 + $3.67 − $1.50. |
| remaining uncertainty | Segment-level owner-cash allocation remains [Assumption] by revenue share. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$455.7M** (+83% YoY); OCF **$174.4M**; capex **$179.1M**; normalized owner cash **$0.74/sh** (OCF minus **$130M** normalized capex ÷ 60.2M FY2025 diluted shares); Q1 2026 cash **$439.7M**; diluted shares **76.0M**. |
| source path | `AAOI/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001437749_26_005875.htm`; Q1 2026 10-Q |
| calculation | Normalized FCF **$44.4M** ÷ **60.2M** = **$0.74/sh** starting owner cash; seven-year Lawrence envelope capitalized in `core_operating_owner_cash` at **$15.00/sh** base. Cash **$439.7M** less **$300M** operating minimum judgment → **$3.67/sh** surplus. |
| remaining uncertainty | **$130M** normalized capex is [Assumption]: **$49M** above mid-cycle maintenance for Taiwan datacenter build. |
| affected components | `core_operating_owner_cash`, `net_surplus_cash` |
| valuation consequence | Filing-locked facts anchor proofs; legacy `operating_business_fallback` excluded from decision-grade sum. |
| falsifier | Two consecutive quarters of OCF below **$100M** with capex still above **$150M** annually. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Digicomm **53%** and Microsoft **29%** of FY2025 revenue; diluted shares **60.2M** FY2025 → **76.0M** Q1 2026 (+26%); multiple 424B5 equity offerings 2025–2026. |
| source path | FY2025 10-K major customers note; Q1 2026 10-Q share count |
| calculation | Downside reserve base **−$1.50/sh** = **−$114M** judgment reserve for customer concentration, dilution, and capex-trap risk (not full gross cash double-count). |
| remaining uncertainty | Further ATM or follow-on offerings would widen reserve band. |
| affected components | `dilution_concentration_reserve` |
| valuation consequence | Capital and concentration claims reconciled to filings once. |
| falsifier | Share count stabilizes below **70M** diluted and top-two customer share falls below **60%** for four quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; 800G datacenter ramp embedded in core DCF growth path; Amazon option incremental only; surplus cash uses operating-minimum haircut separate from core reinvestment. |
| source path | `AAOI/research/valuation.json` |
| calculation | `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$455.7M**; OCF **$174.4M**; capex **$179.1M**; cash **$439.7M** (Mar 2026); Digicomm **53%** / Microsoft **29%** customer share; shares **76.0M** diluted Q1 2026.

**Judgments (bounded):** Normalized capex **$130M**; operating cash minimum **$250–350M**; Amazon option **0–50%** probability on incremental volume; dilution/concentration reserve **−$3.00 to −$0.50/sh**.

## Valuation consequence

Proof-complete additive schedule base case **~$17.47 per share** vs price **~$99.77** implies component economic value far below market; Lawrence seven-year synthesis **−13.44%** remains the stance gate. Security stays **watch**; no human capital decision recorded.
