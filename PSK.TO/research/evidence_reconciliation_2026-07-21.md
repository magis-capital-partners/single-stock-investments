# PSK.TO valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_stream` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | C$21.37 |
| `development_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | C$2.76 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | C$4.14 |
| `depletion_and_realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −C$4.14 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: producing royalty stream, development inventory option, net financial claims, depletion reserve. No embedded double-count. |
| source path | `PSK.TO/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **C$24.13/sh** = 21.37 + 2.76 + 4.14 − 4.14. |
| remaining uncertainty | Undeveloped acreage conversion timing remains judgment-heavy. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 funds from operations **C$353.0M** (**C$1.50/sh**); Q1 2026 FFO **C$94.9M** (**C$0.41/sh**); Canadian royalty owner cash = funds from operations (no operating capex). |
| source path | `PSK.TO/official-reports/PSK-2025-YE-MDA.pdf`; `PSK.TO/official-reports/2026-Q1-MDA-FINAL.pdf` |
| calculation | Producing proof: **C$1.50** × **14.25** capitalization multiple ≈ **C$21.37/sh**. Base uses FY2025 filing rate, not Q1 2026 peak. |
| remaining uncertainty | Capitalization multiple is a bounded judgment, not a filing mark. |
| affected components | `producing_royalty_stream` |
| valuation consequence | Filing-locked FFO anchors producing proof; legacy sensitivities excluded from decision-grade sum unless proof-valid. |
| falsifier | Trailing four-quarter FFO per share falls below **C$1.20** without offsetting acquisition cash flow. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 net debt **C$257.7M**; shareholders equity **C$2,528M**; **0.6×** net debt / EBITDA; no operating abandonment liability on royalty lands. |
| source path | `PSK.TO/official-reports/2026-Q1-MDA-FINAL.pdf`; `PSK.TO/official-reports/2026-Q1-Financial-Statements-FINAL.pdf` |
| calculation | Net equity **C$2,270.3M** ÷ **232.4M** shares = **C$9.77/sh**; base financial claim **C$4.14/sh** = **42.4%** fraction. Depletion reserve base **−C$4.14/sh** = **−2.76×** FY2025 FFO proxy. |
| remaining uncertainty | Commodity trough severity and NCIB dilution remain widest bands. |
| affected components | `net_financial_claims`, `depletion_and_realization_reserve`, `development_inventory_option` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from producing stream. |
| falsifier | Net debt / EBITDA exceeds **3×** for two consecutive quarters or share count rises faster than FFO per share for two years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; E&E option in `development_inventory_option`; producing stream does not re-capitalize the same undeveloped acres. |
| source path | `PSK.TO/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 FFO **C$1.50/sh**; Q1 2026 FFO **C$0.41/sh**; **232.4M** shares; net debt **C$257.7M**; shareholders equity **C$2,528M**; E&E assets **C$1,468M**; Q1 2026 lease bonus **C$12.3M**.

**Judgments (bounded):** FFO capitalization multiple **9.65–18.84×**; E&E risk fraction **0–136.5%** of book; net-equity claim fraction **10.5–70.5%**; depletion multiple **0.69–5.75×** FFO.

## Valuation consequence

Proof-complete additive schedule base case **~C$24.13 per share** vs price **~C$34.46** implies component economic value below market; Lawrence seven-year base **5.2%** and synthesis **6.06%** remain below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
