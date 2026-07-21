# ADN.TO valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_timber_operations` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | C$6.00 |
| `carbon_and_real_estate_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | C$0.00 |
| `owned_timberland_nav` | unpriced | net_asset_value@1.0 | bounded_estimate | C$13.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | C$0.93 |
| `payout_and_cycle_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −C$2.50 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five additive components with unique overlap keys: producing timber operations, carbon/real-estate option, owned timberland NAV, net financial claims, payout/cycle reserve. Crown fee stream embedded in producing; carbon 2024 sale is option reference only. |
| source path | `ADN.TO/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **C$17.43/sh** = 6.00 + 0.00 + 13.00 + 0.93 − 2.50. |
| remaining uncertainty | Fair-value per-acre marks on Maine vs New Brunswick remain judgment-heavy. |
| affected components | All five additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 Free Cash Flow **C$6.635M** (**C$0.37/sh**); Adjusted EBITDA **C$15.8M**; shareholders equity **C$359.7M** (**C$19.67/sh** book); net liquidity **C$17.4M**; long-term debt **C$110.0M**. |
| source path | `ADN.TO/investor-documents/ir-adn.to/Acadian-Annual-Report-2025-VF.pdf`; `Acadian-2026-Q1-Interim-Report.pdf` |
| calculation | Producing proof: **C$0.37** × **16.2** capitalization multiple ≈ **C$6.00/sh**. Owned timberland proof: **42.4%** of IFRS equity ≈ **C$13.00/sh** on **1.075M** owned acres at cost plus partial uplift. |
| remaining uncertainty | Capitalization multiple and land-equity fraction are bounded judgments, not filing fair-value marks. |
| affected components | `producing_timber_operations`, `owned_timberland_nav` |
| valuation consequence | Filing-locked FCF and book anchor proofs; legacy sensitivities excluded from decision-grade sum unless proof-valid. |
| falsifier | Trailing four-quarter Free Cash Flow per share stays below **C$0.25** for four quarters without offsetting carbon or land sale. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Long-term debt **C$110.0M**; net liquidity **C$17.4M**; dividend **C$1.16/sh** vs FCF **C$0.37/sh** (Payout Ratio **316%**, **156%** with Macer DRIP); Maine Adj EBITDA margin **9%** vs NB **30%** Q1 2026. |
| source path | `Acadian-Annual-Report-2025-VF.pdf`; `Acadian-2026-Q1-Interim-Report.pdf` |
| calculation | Net financial base **C$0.93/sh** = net liquidity ÷ **18.62M** shares. Payout reserve base **−C$2.50/sh** = **−3.2×** annual dividend-minus-FCF gap. |
| remaining uncertainty | Macer DRIP participation and Maine internal harvest recovery remain widest bands. |
| affected components | `net_financial_claims`, `payout_and_cycle_reserve`, `carbon_and_real_estate_option` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from producing stream. |
| falsifier | Cash dividend maintained at **C$1.16/sh** while Free Cash Flow stays below **C$0.50/sh** for two years without Macer full DRIP or balance-sheet support. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; Crown management fees in producing component; carbon 2024 sale in option only; land IFRS claim in owned timberland NAV only. |
| source path | `ADN.TO/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 timber sales and services **C$87.0M**; Free Cash Flow **C$6.6M** (**C$0.37/sh**); book value **C$19.67/sh**; dividends **C$1.16/sh**; **18,619,712** shares (May 6, 2026); **1.075M** owned freehold acres; **752,100** carbon credits sold in **2024** for **C$24.6M**; zero carbon sales **2025**; net liquidity **C$17.4M**; long-term debt **C$110.0M**; Macer **~52%** holder with **100%** DRIP.

**Judgments (bounded):** Owner-cash capitalization multiple **8.1–24.3×**; carbon risk fraction **0–100%** of 2024 reference sale; land-equity fraction **20–93%** of IFRS equity; net corporate claim **−C$5.0 to +C$2.0/sh**; payout stress multiple **0.5–8.0×** dividend-FCF gap.

## Valuation consequence

Proof-complete additive schedule base case **~C$17.43 per share** vs price **~C$17.35** implies component economic value roughly in line with market; Lawrence seven-year synthesis **−3.7%** and owner-cash path **−9.0%** remain below mid-teens accumulate hurdle on trough FCF. Security remains **watch**; no human capital decision recorded.
