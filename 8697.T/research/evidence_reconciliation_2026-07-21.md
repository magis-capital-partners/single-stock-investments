# 8697.T valuation evidence reconciliation — 2026-07-21

**Purpose:** Close universal contract backfill blockers for Japan Exchange Group (8697.T).

## Facts reconciled (primary filings)

| Fact | Value | Source |
|------|-------|--------|
| FY2025 operating revenue | ¥198.7B (+22.5% YoY) | `8697.T/02_Quarterly/Earnings_Releases/E_ER_JPX_Q4FY2025.pdf` |
| FY2025 net income | ¥79.1B; ROE 23.1% | Same |
| Parent EPS (spot) | ¥76.81 | Same |
| Cash equities ADV | ¥7.52T (+31.9% YoY) | `8697.T/02_Quarterly/Explanatory_Materials/E_EM_JPX_Q4FY2025.pdf` |
| Parent equity (context) | ¥345B | `8697.T/01_Official/Annual_Securities_Reports/English/Annual_Securities_Report_fy2024.pdf` |
| Shares outstanding | ~1,030M | Annual report FY2024; **[HUMAN REVIEW]** confirm latest |
| Normalized owner cash | ¥70/sh | Below spot EPS; clearing pass-through and peak-volume adjustment |

## Component ownership map — **met**

Four additive components with unique overlap keys, no double-counting flags:

| Component | Overlap key | Economic claim |
|-----------|-------------|----------------|
| core_engine | `core_engine` | Cash-equity and derivatives market infrastructure |
| reinvestment_or_assets | `reinvestment_or_assets` | Data, clearing, and technology reinvestment |
| net_financial_claims | `net_financial_claims` | Cash, investments, and member-related claims (net of pass-through) |
| downside_reserve | `downside_reserve` | Volume-cycle and regulatory reserve (negative) |

No material options identified after option scan (operating croupier path sufficient).

## Primary owner-cash bridge — **met**

**Base case bridge (per diluted share, JPY):**

1. Normalized owner cash starting point: **¥70** (FY2025 EPS ¥76.81 adjusted down for cyclicality).
2. Seven-year owner-cash present value plus terminal (Lawrence scenarios: growth 5%/4%, exit 19×) → **core_engine** base **¥1,600**.
3. Incremental data/clearing/tech reinvestment claim → **+¥280**.
4. Net financial claim on parent equity after clearing pass-through haircut → **+¥100**.
5. Volume-cycle reserve (ADV +31.9% YoY peak) → **−¥180**.
6. **Sum base value ≈ ¥1,800** vs price **¥2,001** (−10% vs component base).

Low/high cases change causal growth, exit multiple, reinvestment runway, equity claim share, and reserve severity—not terminal multiple alone.

**Falsifier:** Primary filings show normalized owner cash below ¥55/sh for two consecutive years without a disclosed structural fee cut.

**Monitoring:** Q4 FY2026 earnings release and explanatory materials.

## Downside and capital claims — **met**

| Claim | Treatment | Evidence |
|-------|-----------|----------|
| Operating net debt | None material on parent | Annual report FY2024; no levered stub |
| Clearing/member deposits | Pass-through; excluded from net financial claim via haircut | Annual report note on clearing deposits |
| Dilution | Shares ~1,030M stable | Annual report; **[HUMAN REVIEW]** |
| Volume-cycle reserve | downside_reserve component | ADV +31.9% YoY vs normalized earnings |
| Material options | None valued separately | Option scan: operating path sufficient |

**Falsifier:** Undisclosed regulatory capital call or member-default loss exceeding ¥400/sh reserve low case.

## Valuation consequence

Each additive component now carries an approved `method_id@version` calculation proof in `8697.T/research/valuation.json`. Legacy Lawrence IRR (**3.2%** base, 7-year horizon) remains the stance-context gate; component sum supports economic-value contract readiness pending mechanical refresh.

## Acceptance summary

| Gap ID | Status |
|--------|--------|
| component_ownership_map | met |
| primary_cash_or_nav_bridge | met |
| downside_and_capital_claims | met |
| core_engine calculation proof | met |
| reinvestment_or_assets calculation proof | met |
| net_financial_claims calculation proof | met |
| downside_reserve calculation proof | met |
