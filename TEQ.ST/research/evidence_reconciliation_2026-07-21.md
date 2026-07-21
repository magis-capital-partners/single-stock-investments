# TEQ.ST valuation evidence reconciliation — 2026-07-21

**Purpose:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the owner-cash bridge to FY2025 primary filings.

## Facts reconciled (primary filings)

| Fact | Value | Source |
|------|-------|--------|
| Net sales FY2025 | 1,800.0 MSEK (+15%) | `TEQ.ST/official-reports/annual-reports/2026-03-21 - Årsredovisning 2025.pdf` |
| EBITA FY2025 | 203.1 MSEK (+36%); margin 11.3% | Same |
| Organic net sales | −5% | Same (MD&A) |
| Operating cash flow | 184.6 MSEK (+92%) | Not 27 |
| FCF ex-acquisitions | 173.1 MSEK | Operating CF 184.6 minus non-acquisition investing 11.5 MSEK (Not 27) |
| Shares outstanding | 17,165,756 | Same (shareholder table) |
| FCF ex-acquisitions per share | 10.08 SEK | 173.1 ÷ 17,165,756 |
| Cash and bank | 209.5 MSEK | MD&A finansiering och likviditet |
| Contingent consideration (earnouts) | 195.6 MSEK | Not 14 |
| Net debt (ex leases) | 286.6 MSEK | MD&A |
| Goodwill impairment FY2025 | 73.0 MSEK | MD&A |
| Equity ratio (soliditet) | 42.8% | Key metrics table |

## Component ownership map — met

Four additive components with unique overlap keys; no embedded double-count:

| Component | Overlap key | Economic claim |
|-----------|-------------|----------------|
| core_engine | `core_engine` | Operating portfolio owner cash on normalized FCF ex-acquisitions |
| reinvestment_or_assets | `reinvestment_or_assets` | Incremental bolt-on M&A reinvestment runway |
| net_financial_claims | `net_financial_claims` | Parent cash, contingent consideration, and liquidity headroom |
| downside_reserve | `downside_reserve` | First North liquidity and execution reserve (negative) |

Goodwill, operating debt service, and acquisition spend are not capitalized twice: M&A outflows sit in the reinvestment runway component; earnouts sit in net financial claims; operating owner cash uses FCF ex-acquisitions only.

## Primary owner-cash bridge — met

**Base case bridge (per share, SEK):**

1. Normalized owner cash: **10.08** (173.1 MSEK FCF ex-acquisitions ÷ 17,165,756 shares).
2. Capitalization on existing portfolio (**core_engine**, `owner_cash_or_dividend_discount@1.0`) → **126.45**.
3. Incremental reinvestment runway on nine FY2025 acquisitions (**reinvestment_or_assets**, `owner_earnings_reinvestment_dcf@1.0`) → **+22.13**.
4. Net financial claim after contingent consideration and bounded credit headroom (**net_financial_claims**, `net_asset_value@1.0`) → **+7.90**.
5. Small-cap liquidity and execution reserve (**downside_reserve**, `net_asset_value@1.0`) → **−14.22**.
6. **Sum base value ≈ 142.26 SEK** vs legacy scaffold **142.2 SEK** vs price **~158 SEK** (−10% vs component base).

Low/high cases change capitalization multiples, reinvestment runway, net financial claim, and reserve severity—not terminal multiple alone.

**Falsifier:** FY2026 FCF ex-acquisitions falls below **130 MSEK** for two consecutive reporting periods without a disclosed portfolio restructuring that explains the decline.

**Monitoring:** Annual report Not 27 and year-end report FCF bridge.

## Downside and capital claims — met

| Claim | Treatment | Evidence |
|-------|-----------|----------|
| Cash | 209.5 MSEK in net_financial_claims | MD&A |
| Contingent consideration | 195.6 MSEK liability deducted | Not 14 |
| Net debt ex leases | 286.6 MSEK — not additive (serviced by operating cash) | MD&A |
| Undrawn credit | Bounded in structural liquidity judgment | 100 MSEK check + ~77 MSEK facility |
| Dilution | 17,165,756 shares locked | Shareholder table |
| CEO bonus option (6,000 MSEK threshold) | Context only; not valued separately | Bolagsstyrningsrapport |
| Downside reserve | downside_reserve component | Goodwill impairment + First North liquidity |

**Falsifier:** Contingent consideration step-up above **250 MSEK** without offsetting acquisition economics, or equity ratio below **35%** with covenant pressure.

## Valuation consequence

Each additive component carries an approved `method_id@version` calculation proof in `TEQ.ST/research/valuation.json`. Lawrence base **14.4%** and total synthesis **18.14%** remain stance-context gates; component sum supports **decision_grade** contract readiness.

## Acceptance summary

| Gap ID | Status |
|--------|--------|
| component_ownership_map | met |
| primary_cash_or_nav_bridge | met |
| downside_and_capital_claims | met |
| core_engine calculation proof | met (`owner_cash_or_dividend_discount@1.0`) |
| reinvestment_or_assets calculation proof | met (`owner_earnings_reinvestment_dcf@1.0`) |
| net_financial_claims calculation proof | met (`net_asset_value@1.0`) |
| downside_reserve calculation proof | met (`net_asset_value@1.0`) |
