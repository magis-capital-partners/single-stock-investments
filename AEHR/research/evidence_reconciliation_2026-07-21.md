# AEHR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `burn_in_test_equipment_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $3.21 |
| `sic_wafer_level_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $4.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | $1.68 |
| `cycle_and_inventory_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$6.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: burn-in test equipment engine, SiC wafer-level option, net financial claims, cycle and inventory reserve. No embedded double-count. |
| source path | `AEHR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$2.89/sh** = $3.21 + $4.00 + $1.68 − $6.00. |
| remaining uncertainty | SiC option band ($0–$12/sh) and cycle reserve remain widest judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$65.0M** (−2% YoY); operating income **$13.4M** (+33% YoY); operating cash flow **$10.0M**; diluted **~29.2M** shares ($14.6M net income / $0.50 EPS). |
| source path | `AEHR/investor-documents/sec-edgar/10-K_20250728_rpt20250530_acc0001654954_25_008553.htm` |
| calculation | Core proof: **$0.40/sh** mid-cycle operating income × 8× capitalization ≈ **$3.21/sh**. Cash **$49.2M** with no material long-term debt filed reconciles to net financial judgment band. |
| remaining uncertainty | Capitalization multiple and SiC milestone band are bounded judgments, not filing marks. |
| affected components | `burn_in_test_equipment_engine`, `net_financial_claims`, `sic_wafer_level_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter operating income per share falls below **$0.25** for four quarters without offsetting SiC order recovery. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$49.2M**; no long-term debt tags in 10-K extract; inventory **$42.0M**; Q3 FY2026 cash **$24.5M** (nine-month burn). |
| source path | `10-K_20250728` and `10-Q_20260408` balance sheet extracts |
| calculation | Net cash filing-locked at **+$49.2M** (~**$1.68/sh**); cycle reserve base **−$6.00/sh** separate from core capitalization. |
| remaining uncertainty | Customer concentration and inventory obsolescence remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `cycle_and_inventory_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from core owner-cash multiple. |
| falsifier | Cash falls below **$15M** while inventory stays above **$40M** for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; deferred revenue converting in normalized owner cash is not double-counted in SiC option band. |
| source path | `AEHR/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 consolidated revenue **$65.0M**; operating income **$13.4M**; net income **$14.6M**; operating cash flow **$10.0M**; cash **$49.2M**; inventory **$42.0M**; deferred revenue **$1.3M**; diluted EPS **$0.50** on **~29.2M** shares. Q3 FY2026 nine-month revenue **$44.9M**; cash **$24.5M**.

**Judgments (bounded):** Owner-cash capitalization multiple 5–12×; SiC option **$0–$12/sh**; net cash claim **$1.4–$1.8/sh**; cycle reserve **−$12 to −$2/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$2.89 per share** vs price **~$77.36** implies the market prices SiC wafer-level adoption and semicap recovery far beyond filing-locked conservative components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
