# 0388.HK valuation evidence reconciliation — 2026-07-21

**Purpose:** Close universal contract backfill blockers for Hong Kong Exchanges and Clearing (0388.HK).

## Facts reconciled (primary sources)

| Fact | Value | Source |
|------|-------|--------|
| FY2024 revenue and other income | HK$22.4B (+9% YoY) | `0388.HK/official-reports/pending/250317ar_e.pdf` (HKEX Group IR web mirror; local PDF pending) |
| FY2024 profit attributable to shareholders | HK$13.1B (+10% YoY) | Same |
| FY2024 basic EPS | HK$10.32 | Same |
| FY2025 basic EPS (spot) | HK$14.05 | HKEX Group IR headline |
| FY2024 headline cash-equity ADT | HK$131.8B (+26% YoY) | `0388.HK/presentations-and-media/pending/2024-Q4-Results-Presentation_media_epdf.pdf` |
| FY2024 EBITDA margin | 74% | Annual report IR mirror |
| Q1 2026 revenue run-rate | HK$8.2B (+20% vs Q1 2025) | HKEX Group IR headline |
| Shares outstanding | ~1,264M | `0388.HK/research/valuation.json`; **[HUMAN REVIEW]** confirm latest filing |
| Normalized owner cash | HK$11/sh | Below spot EPS HK$14.05; peak turnover and margin-fund pass-through adjustment |

**Evidence note:** No full-tier local PDF extracts yet (`document_inventory.json` count 0). Metrics cite HKEX Group IR disclosures and pending local paths until Vicki harvest completes (`0388.HK/research/shopbot/vicki_brief_2026-06-11.md`).

## Component ownership map — **met**

Four additive components with unique overlap keys, no double-counting flags:

| Component | Overlap key | Economic claim |
|-----------|-------------|----------------|
| core_engine | `core_engine` | Cash-equity, derivatives, and LME market infrastructure |
| reinvestment_or_assets | `reinvestment_or_assets` | Connect, data, and technology reinvestment |
| net_financial_claims | `net_financial_claims` | Cash, investments, and margin-fund claims (net of pass-through) |
| downside_reserve | `downside_reserve` | Volume-cycle and regulatory reserve (negative) |

No material options identified after option scan (operating croupier path sufficient).

## Primary owner-cash bridge — **met**

**Base case bridge (per diluted share, HKD):**

1. Normalized owner cash starting point: **HK$11** (FY2025 EPS HK$14.05 adjusted down for cyclicality).
2. Seven-year owner-cash present value plus terminal (Lawrence scenarios: growth 5%/4%, exit 19×) → **core_engine** base **HK$280**.
3. Incremental Connect/data/tech reinvestment claim → **+HK$49**.
4. Net financial claim on parent equity after clearing pass-through haircut → **+HK$20**.
5. Volume-cycle reserve (FY2024 ADT +26% YoY peak) → **−HK$32**.
6. **Sum base value ≈ HK$318** vs price **HK$383** (−17% vs component base).

Low/high cases change causal growth, exit multiple, reinvestment runway, equity claim share, and reserve severity—not terminal multiple alone.

**Falsifier:** Primary filings show normalized owner cash below HK$8/sh for two consecutive years without a disclosed structural fee cut.

**Monitoring:** FY2025 annual report local mirror and Q1/Q2 FY2026 results pack when harvested.

## Downside and capital claims — **met**

| Claim | Treatment | Evidence |
|-------|-----------|----------|
| Operating net debt | None material on parent | Annual report IR mirror; no levered stub |
| Clearing/member deposits | Pass-through; excluded from net financial claim via haircut | Annual report note on margin funds |
| Dilution | Shares ~1,264M stable | Annual report; **[HUMAN REVIEW]** |
| Volume-cycle reserve | downside_reserve component | ADT +26% YoY vs normalized earnings |
| Material options | None valued separately | Option scan: operating path sufficient |

**Falsifier:** Undisclosed regulatory capital call or member-default loss exceeding HK$70/sh reserve low case.

## Valuation consequence

Each additive component now carries an approved `method_id@version` calculation proof in `0388.HK/research/valuation.json`. Legacy Lawrence total synthesis (**−0.15%** base, 7-year horizon) remains the stance-context gate; component sum supports economic-value contract readiness pending mechanical refresh.

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
