# Agent context pack: CSU (Constellation Software)

## Identity (stable)
- Ticker: CSU
- Company: Constellation Software
- Book: holdings
- Stance: core
- Archetype: compounder

## What this business is (stable)
Constellation Software Inc. is a Canadian holding company that acquires and holds vertical market software (VMS) businesses. **[Fact]** Customers are niche industry users paying maintenance and license fees on mission-critical software. **[Fact]** Cash is generated as free cash flow available to shareholders (FCFA2S) and redeployed almost entirely into new acquisitions at hurdle rates. **[Fact]** FY2025 revenue was **$11.62B** (+15%); Q1 2026 revenue **$3.18B** (+20%) with organic growth disclosed in the shareholder letter. **[Fact]** FY2025 net income was **$586M** (-24% YoY) while Q4 2025 net income was **$166M** (-48% vs prior Q4). **[Inference]** GAAP net income is a poor owner metric because earnout fair-value swings and Lumine investment revaluations distort reported earnings.

## Why the market might be wrong (stable)
There is **no clear dated mispricing signal** (HK predictive attribute: **none**). **[Inference]** Generalists focus on GAAP net income volatility and law-of-large-numbers concerns, while the owner metric FCFA2S (**$79.42/sh** FY2025) compounds steadily. Return is serial acquirer reinvestment at price: the question is whether hurdle-rate deals remain available as scale grows, not whether a hidden asset is marked wrong tomorrow.

## Returns (stable, percent per year)
- Base return: 12.08% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 4.3, base 10.9, bull 15.6

## Key assumptions (stable)
- Price today: **$2780.49** (source: Yahoo CSU.TO close 2026-07-20)
- Starting free cash flow per share: **$79.42** (source: FY2025 FCFA2S $1683.0M ÷ 21.19153M diluted shares per CSU/official-reports/Q4-2025-Shareholder-Report.pdf)
- Growth in years 1 through 5: **12.0%** per year (source: FCFA2S reinvested at hurdle; Q1 2026 +20% revenue / 6% organic supports pipeline)
- Growth in years 6 through 7: **8.0%** per year (source: Scenario base)
- Selling multiple in year 10: **28 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 8.850344884764432% per year; status diagnostic. Research only.
- Buy bands: withheld; model stock_specific.
- Confirm CSU.TO price and USD conversion for live IRR. (source: CSU/research/thesis_card.json)
- Extract Q1 2026 MDA / financial statements (inventory tier, 0 chars in evidence build). (source: CSU/research/thesis_card.json)
- Map Topicus/Lumine/Volaris stake NAV vs consolidated. (source: CSU/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 10.9, 'key_metric': 'archetype=compounder', 'conviction': 0.045, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: CSU/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 12.9, 'key_metric': 'payoff_lens=pending', 'conviction': 0.045, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: CSU/research/valuation.json#lens_consensus)

## Open questions (stable)
- Confirm CSU.TO price and USD conversion for live IRR.
- Extract Q1 2026 MDA / financial statements (inventory tier, 0 chars in evidence build).
- Map Topicus/Lumine/Volaris stake NAV vs consolidated.

## Canonical pointers (open only when needed)
- valuation: CSU/research/valuation.json (sha256 sha256:6c4bc6aadd7cffbc...)
- thesis_card: CSU/research/thesis_card.json (sha256 sha256:21e911a8ca7f8021...)

## Excluded from this pack
- CSU/research/valuation.json (full; returns block included, open only for assumption audit)
- CSU/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
