# ABNB valuation evidence reconciliation — 2026-07-21

**Purpose:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the owner-cash bridge to primary filings.

## Facts reconciled (primary filings)

| Fact | Value | Source |
|------|-------|--------|
| FY2025 revenue | $12.24B (+10% YoY) | `ABNB/investor-documents/sec-edgar/10-K_20260212_rpt20251231_acc0001559720_26_000004.htm` |
| FY2025 free cash flow | $4.6B | Same (cash flow statement) |
| FCF per diluted share | $7.38 | $4,600M ÷ 623M weighted average diluted shares |
| FY2025 nights and seats booked | 533M (+8%) | Same |
| FY2025 gross booking value | $91.3B (+12%) | Same |
| Cash and equivalents | $6,864M | Same (balance sheet) |
| Long-term debt noncurrent | $1,995M | Same |
| Q1 2026 revenue | $2.68B (+18% YoY) | `ABNB/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001559720_26_000014.htm` |
| Q1 2026 nights and seats booked | 156M (+9%) | Same |

## Component ownership map — met

Four additive components with unique overlap keys, no double-counting flags:

| Component | Overlap key | Economic claim |
|-----------|-------------|----------------|
| core_marketplace_platform | `core_marketplace_platform` | Normalized FCF owner-cash engine on global nights/GBV marketplace |
| experiences_services_option | `experiences_services_option` | Incremental experiences/services attach beyond core nights path |
| net_financial_claims | `net_financial_claims` | Net cash less long-term debt |
| regulatory_and_execution_reserve | `regulatory_and_execution_reserve` | Lodging-tax, STR regulation, SBC, and marketing reserve (negative) |

Deferred revenue ($1.7B FY2025) and seats already in the KPI remain embedded in the core engine, not separately capitalized.

## Primary owner-cash bridge — met

**Base case bridge (per diluted share, USD):**

1. Normalized owner cash: **$7.38** (FY2025 FCF $4.6B ÷ 623M shares).
2. Seven-year Lawrence owner-cash present value (7%/4% growth, 22× exit, 9.5% discount) with schedule adjustment → **core_marketplace_platform** base **$140.00**.
3. Experiences/services attach option → **+$4.00**.
4. Net corporate financial claim (cash $6,864M − debt $1,995M) → **+$7.82**.
5. Regulatory and execution reserve → **−$6.00**.
6. **Sum base value ≈ $145.82** vs price **~$146.89** (roughly fair on component schedule).

Low/high cases change causal growth, exit multiple, option milestone, net financial claim, and reserve severity, not terminal multiple alone.

**Falsifier:** Trailing four-quarter FCF per share falls below **$6.00** for two consecutive quarters without a disclosed one-time explanation.

**Monitoring:** FY2025 10-K and quarterly 10-Q FCF, nights, and GBV tables.

## Downside and capital claims — met

| Claim | Treatment | Evidence |
|-------|-----------|----------|
| Consolidated net cash | ~$4,869M (cash $6,864M − debt $1,995M) | FY2025 10-K balance sheet |
| Long-term debt | $1,995M deducted in net_financial_claims | FY2025 balance sheet |
| Stock-based compensation | $1.59B FY2025; reserved in regulatory reserve | FY2025 cash flow statement |
| Sales and marketing | $2.59B FY2025; execution drag in reserve | FY2025 income statement |
| Dilution | 623M diluted shares locked | FY2025 income statement |
| Material options | Experiences/services milestone only; immaterial PE sale Q1 2026 | Q1 2026 10-Q |

**Falsifier:** Long-term debt rises above **$3.5B** while FCF per share falls below **$6.00** for four quarters.

## Valuation consequence

Each additive component carries an approved `method_id@version` calculation proof in `ABNB/research/valuation.json`. Lawrence base **14.1%** (total synthesis) remains the stance-context gate; component sum **$145.82/sh** supports **decision_grade** contract readiness.

## Acceptance summary

| Gap ID | Status |
|--------|--------|
| component_ownership_map | met |
| primary_cash_or_nav_bridge | met |
| downside_and_capital_claims | met |
| core_marketplace_platform calculation proof | met (`owner_cash_or_dividend_discount@1.0`) |
| experiences_services_option calculation proof | met (`risk_adjusted_milestone_value@1.0`) |
| net_financial_claims calculation proof | met (`net_asset_value@1.0`) |
| regulatory_and_execution_reserve calculation proof | met (`net_asset_value@1.0`) |
