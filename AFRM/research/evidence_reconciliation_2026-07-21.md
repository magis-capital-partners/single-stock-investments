# AFRM valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `platform_owner_cash_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $20.96 |
| `wallet_and_card_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $8.00 |
| `net_corporate_liquidity` | unpriced | net_asset_value@1.0 | bounded_estimate | $1.71 |
| `credit_funding_stress_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$12.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: platform owner cash, wallet/card option, net corporate liquidity, credit/funding reserve. No embedded double-count. |
| source path | `AFRM/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$18.67/sh** = $20.96 + $8.00 + $1.71 − $12.00. |
| remaining uncertainty | Wallet/card milestone band ($0–$22/sh) and credit reserve remain widest judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$793.9M** on **341.0M** diluted shares (**$2.33/sh**); Q3 FY2026 cash **$1,723.4M**; corporate long-term debt **~$1,128.6M** (ex-securitization); total debt **$8,873.9M** mostly matched to loan receivables. |
| source path | `AFRM/investor-documents/sec-edgar/10-K_20250828_rpt20250630_acc0001820953_25_000080.htm`, `10-Q_20260507_rpt20260331_acc0001628280_26_032294.htm` |
| calculation | OCF ÷ shares = normalized owner cash; net corporate liquidity **($1,723.4M − $1,128.6M) / 348.6M shares ≈ $1.71/sh**. |
| remaining uncertainty | Corporate vs securitization debt split requires note reconciliation each quarter. |
| affected components | `platform_owner_cash_engine`, `net_corporate_liquidity` |
| valuation consequence | Filing-locked OCF and parent liquidity anchor component schedule; price stub replaced. |
| falsifier | FY2026 operating cash flow falls below **$400M** while provision for credit losses exceeds **$800M** for two consecutive quarters. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 provision for credit losses **$616.7M**; total long-term debt **$8,873.9M** at March 31, 2026; securitization funding **~$7,745M** matched to receivables. |
| source path | `10-K_20250828`, `10-Q_20260507` |
| calculation | Credit/funding reserve base **−$12.00/sh** separate from owner-cash multiple and net corporate liquidity. |
| remaining uncertainty | Recession severity and ABS market access drive reserve band width. |
| affected components | `credit_funding_stress_reserve`, `platform_owner_cash_engine` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from OCF capitalization. |
| falsifier | Securitization funding cost rises more than **300 bps** YoY while net charge-offs double for four quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; interest income embedded in OCF engine; securitization debt excluded from net corporate liquidity; loan receivables not separately NAV-capitalized. |
| source path | `AFRM/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 total revenue **$3.22B**, operating cash flow **$793.9M**, operating income **$1.20B**, net income **$985.3M**, provision for credit losses **$616.7M**, diluted shares **341.0M**; Q3 FY2026 cash **$1,723.4M**, total debt **$8,873.9M**, diluted shares **348.6M**.

**Judgments (bounded):** Wallet/card option **$0–$22/sh**; credit/funding reserve **−$22 to −$5/sh**; owner-cash multiple **6×–13×** on **$2.33/sh** OCF.

## Valuation consequence

Proof-complete additive schedule base case **$18.67 per share** vs price **~$75.32** implies the market prices sustained GMV growth, wallet expansion, and credit outperformance well above the conservative component sum. Lawrence scenario IRR and synthesis are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
