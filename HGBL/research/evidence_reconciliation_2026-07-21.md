# HGBL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `fee_franchises_after_corporate` | legacy_sensitivity | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $1.05 |
| `specialty_lending_notes` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.20 |
| `equity_method_investments` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.45 |
| `cash_inventory_ppe_net_working` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.35 |
| `debt_and_leases` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$0.17 |
| `preferred_liquidation_claim` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$0.02 |
| `debtx_commercial_loan_platform` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.05 |

## Reconciliation notes

### fee_earnings_power_and_multiple — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 segment operating income: Auction/Liquidation **$2.671M**, Refurbishment **$1.659M**, Brokerage (NLEX) **$6.116M**, Corporate **($4.965M)** → fee segments after corporate **$5.481M**. |
| source path | `HGBL/investor-documents/sec-edgar/10-K_20260312_rpt20251231_acc0001193125_26_104062.htm` segment note |
| calculation | After 25% tax proxy **$4.11M** ÷ **34.735M** shares = **$0.118/sh** after-tax; 10× capitalization × schedule adjustment = **$1.05/sh** base. |
| remaining uncertainty | FY2025 cash tax exceeded 25% proxy; Q1 2026 net income softened to **$0.717M**. |
| affected components | `fee_franchises_after_corporate` |
| valuation consequence | Through-cycle fee power anchored to filing segment table; multiple remains judgment. |
| falsifier | Through-cycle after-tax fee earnings fall such that capitalized value is below the low case ($0.80/sh). |

### emi_and_notes_realization — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 notes receivable net **$8.551M** ($0.246/sh carrying); equity-method investments **$19.442M** ($0.56/sh carrying). FY2025 equity-method earnings only **$0.123M** vs **$2.688M** in 2024. Largest specialty-lending borrower **76%** of gross notes (FY2025 10-K). |
| source path | `HGBL/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_211813.htm`; FY2025 10-K concentration disclosure |
| calculation | Notes base **$0.20/sh** = **81%** recovery on carrying; EMI base **$0.45/sh** = **80%** of carrying. |
| remaining uncertainty | Borrower default since June 2024; JV realizations lumpy. |
| affected components | `specialty_lending_notes`, `equity_method_investments` |
| valuation consequence | Asset components haircut filing carrying values; no separate goodwill double-count. |
| falsifier | Notes or EMI carrying impaired below low-case recovery ratios in a subsequent filing. |

### debtx_earn_in — met

| Field | Content |
|---|---|
| status | met |
| evidence | January 1, 2026 acquisition of substantially all assets of The Debt Exchange Inc. for **~$8.5M**; **$5.3M** goodwill recognized in 2026; Q1 Commercial Loans segment operating loss **($0.606M)**. |
| source path | `10-Q_20260507` Note on DebtX acquisition and segment table |
| calculation | Incremental option base **$0.05/sh** only; paid consideration and goodwill excluded from fee/tangible components via overlap control. Low case **$0** (failure). |
| remaining uncertainty | Platform must reach NLEX-like economics; pro forma in 10-Q is illustrative only. |
| affected components | `debtx_commercial_loan_platform` |
| valuation consequence | Option valued once as incremental earn-in, not added to fee franchise or PP&E. |
| falsifier | Commercial Loans segment remains loss-making with goodwill impairment below low case. |

### Overlap control — met

Unique overlap keys preserved; `double_counting_flags` empty. DebtX purchase price not counted in tangible net or fee franchise components.

## Facts vs judgments

**Facts (locked):** **34,734,754** shares Q1 2026; cash **$11.566M**; notes **$8.551M**; EMI **$19.442M**; third-party debt **$4.100M**; lease liabilities **$1.437M**; Series N preference **$0.563M**; FY2025 fee segment operating incomes as above.

**Judgments (bounded):** Fee capitalization 8–12× after-tax earnings; notes/EMI/tangible recovery ratios; DebtX incremental option **$0–0.25/sh**.

## Valuation consequence

Proof-complete additive schedule base **~$1.91/sh** vs price **~$1.26** implies **~51%** upside to component economic value and **~8.7%** annualized return over five years at base payoff. Security remains **watch** pending through-cycle fee confirmation and specialty-lending resolution; no human capital decision recorded.
