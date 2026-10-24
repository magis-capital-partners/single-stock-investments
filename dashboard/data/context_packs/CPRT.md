# Agent context pack: CPRT (Copart)

## Identity (stable)
- Ticker: CPRT
- Company: Copart
- Book: holdings
- Stance: core
- Archetype: compounder

## What this business is (stable)
Copart operates a global salvage-vehicle auction platform: insurers assign total-loss vehicles; Copart stores them at yard networks and sells them via online bidding (VB3). **[Fact]** Revenue comes from seller fees, buyer fees, and ancillary services on units processed, plus interest on buyer float balances. **[Fact]** Q3 FY2026 (Apr 2026) revenue was $1.24 billion (+2.1% YoY) with diluted EPS $0.43; international growth offset US units down 4%. FY2025 operating income was $1.70 billion on ~$3.97 billion GAAP revenue. The model is capital-light after land is in place with minimal leverage.

## Why the market might be wrong (stable)
No dated payoff, but two parallel mispricing reads: (1) **transitory US volume** softness while international mix grows; (2) **GAAP book understates owned yard land** carried at decades-old historical cost while recent Copart purchases trade at **$150K–$800K+ per acre** depending on market. **[Inference]** At ~$33 the stock prices mid-cycle cash flow, not the embedded real-estate optionality Copart deliberately bought (>90% owned acreage per ESG letter).

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$33.07** (source: NASDAQ close ~May 26, 2026 (Yahoo Finance))
- Starting free cash flow per share: **$1.25** (source: FY2025 OCF $1.80B − capex $0.57B ÷ ~978M diluted shares (10-K FY2025))
- Growth in years 1 through 5: **7.0%** per year (source: International mix + modest U.S. recovery; re-rate toward historical quality multiple from trough)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **24 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Confirm live price before sizing adds (source: CPRT/research/thesis_card.json)
- Approve comp-based land roll-up before promoting overlay into stance (source: CPRT/research/thesis_card.json)
- Assessor tie-out: yards 151, 59, 148 (recorded purchases) plus Phoenix/Houston/Denver assumption acres (source: CPRT/research/thesis_card.json)
- Close registry gap to 281 facilities (international scrape) (source: CPRT/research/thesis_card.json)
- Override watch → **core** documented: quality + dhando full despite <15% IRR at de-rated price (source: CPRT/research/thesis_card.json)

## Open questions (stable)
- Confirm live price before sizing adds
- Approve comp-based land roll-up before promoting overlay into stance
- Assessor tie-out: yards 151, 59, 148 (recorded purchases) plus Phoenix/Houston/Denver assumption acres
- Close registry gap to 281 facilities (international scrape)
- Override watch → **core** documented: quality + dhando full despite <15% IRR at de-rated price

## Canonical pointers (open only when needed)
- valuation: CPRT/research/valuation.json (sha256 sha256:5b1fb4dbb56c4cd6...)
- thesis_card: CPRT/research/thesis_card.json (sha256 sha256:aa623734f7f35f53...)

## Excluded from this pack
- CPRT/research/valuation.json (full; returns block included, open only for assumption audit)
- CPRT/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
