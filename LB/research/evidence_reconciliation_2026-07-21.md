# LB valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `current_fee_engine` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $42.85 |
| `net_debt` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$6.56 |
| `dormant_acreage` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $2.80 |
| `alpha_digital_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.00 |
| `pore_space_other_options` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $1.50 |

## Open evidence questions (not contract blockers)

| Question | Status | Notes |
|----------|--------|-------|
| Alpha Digital lease economics | **unresolved** | No executed Alpha Digital lease in primary packet; base option value correctly zero |
| Fee engine unit economics (volume vs price vs mix) | **partial** | Q1 2026 revenue +16% YoY; recurring vs one-time split not fully disclosed |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five additive components with unique overlap keys: lb_current_operations, lb_net_debt, lb_dormant_acreage, lb_alpha_digital, lb_other_options. No embedded double-count. |
| source path | `LB/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$40.59/sh** = $42.85 − $6.56 + $2.80 + $0.00 + $1.50. |
| remaining uncertainty | Up-C Class A attribution and Alpha Digital contract timing remain judgment-heavy. |
| affected components | All five additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026: long-term debt **$535.5M**; cash **$29.7M**; filing net debt **~$505.9M**; 2026 adjusted EBITDA guide **$210M–$230M**; **77.017M** economic units. |
| source path | `LB/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209491.htm`; `8-K_20260506_exhibit_lb-ex99_1.htm` |
| calculation | Fee engine: $220M EBITDA × 15× / 77.017M ≈ **$42.85/sh**. Net debt: $505.9M / 77.017M ≈ **−$6.56/sh**. |
| remaining uncertainty | EBITDA multiple and separately marked acreage fraction are bounded judgments, not filing marks. |
| affected components | `current_fee_engine`, `net_debt`, `dormant_acreage` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Trailing four-quarter adjusted EBITDA falls below **$180M** without offsetting acreage monetization. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 debt **$535.5M** vs cash **$29.7M**; sponsor-controlled Up-C; related-party WaterBridge revenue **~$36M** FY2025. |
| source path | `10-Q_20260507`; `10-K_20260226` |
| calculation | Net debt proof ties to filing balance sheet; low case adds **$71.8M** senior-claim stress reserve. |
| remaining uncertainty | Refinancing terms and Class A cash allocation through Up-C remain widest bands. |
| affected components | `net_debt`, `current_fee_engine` |
| valuation consequence | Downside claims reconciled to filings; fee engine valued before net debt (non-overlapping). |
| falsifier | Net debt rises above **$600M** while consolidated free cash flow falls below **$100M** annualized for two quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; dormant acreage explicitly excludes currently monetized streams in fee engine. |
| source path | `LB/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Long-term debt **$535.5M**; cash **$29.7M** (Q1 2026); **77.017M** economic units; 2026 adjusted EBITDA guide **$210M–$230M**; **315k+** surface acres; Q1 2026 revenue **$51.0M** (+16% YoY).

**Judgments (bounded):** Normalized EBITDA **$180M–$240M**; EV multiple **10×–20×**; separately marked acreage **20%** at **$722–$7,220/acre**; Alpha Digital success probability **0–25%** with base **zero**; pore-space portfolio reserve **$0–385M**.

## Valuation consequence

Proof-complete additive schedule base case **~$40.59 per share** vs price **~$78.12** implies component economic value roughly **48% below market**; Lawrence seven-year base remains near **−2%** on Class A owner cash. Alpha Digital and fee-engine mix remain widest judgment bands. Security remains **watch**; no human capital decision recorded.
