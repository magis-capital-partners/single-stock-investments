# Agent context pack: TEQ.ST (Teqnion AB)

## Identity (stable)
- Ticker: TEQ.ST
- Company: Teqnion AB
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Teqnion AB (TEQ.ST, Nasdaq First North) is a Swedish industrial serial acquirer. **[Fact]** The parent owned **38** operating subsidiaries at year-end 2025 (30 prior year) across niche industrial niches in Nordics and the UK. **[Fact]** FY2025 net sales were **1,800.0 MSEK** (+15%); organic net sales **-5%** after deliberate exits of unprofitable units. **[Fact]** FY2025 EBITA was **203.1 MSEK** (+36%) at an **11.3%** margin; EPS **5.74 SEK**. **[Fact]** Operating cash flow was **184.6 MSEK** (+92%); the board proposes **no dividend** for FY2025. Cash returns are modest; the model is reinvestment plus EPS growth.

## Why the market might be wrong (stable)
Reported **organic net sales -5%** may anchor sentiment while margin and cash-flow inflection are under-discounted. **[Inference]** FY2025 EBITA margin rose from **9.6%** to **11.3%** and Q1 2026 EBITA margin hit a record **14.3%** (prior interim, inventory tier), suggesting pruning is working. There is no dated HK payoff; mispricing, if any, is franchise quality at a full multiple (~**15.7×** FY2025 FCF/share at **~158 SEK**).

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$163.0** (source: Yahoo TEQ.ST close 2026-07-22)
- Starting free cash flow per share: **$10.08** (source: FY2025 FCF ex-acquisitions 173.1 MSEK ÷ 17,165,756 shares (TEQ.ST/official-reports/year-end-reports/2026-02-14 - Year-End Report 2025 - Teqnion AB.pdf; cross-check operating CF 184.6 MSEK less maintenance capex per TEQ.ST/official-reports/annual-reports/2026-03-21 - Årsredovisning 2025.pdf Note 27))
- Growth in years 1 through 5: **8.0%** per year (source: Margin hold + bolt-on M&A; exit ~16x P/FCF vs ~15.7x spot on FY2025 FCF/sh)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **16 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Confirm live TEQ.ST price before acting on IRR. (source: TEQ.ST/research/thesis_card.json)
- Re-extract Q1 2026 interim (inventory tier, 0 chars) to filing-ground Q1 metrics. (source: TEQ.ST/research/thesis_card.json)
- Verify FCF ex-acquisitions bridge vs operating CF 184.6 MSEK in annual. (source: TEQ.ST/research/thesis_card.json)
- {'persona': 'greenblatt', 'label': 'Joel Greenblatt', 'verdict': 'watch', 'return_pct': 11.18, 'key_metric': 'earnings_yield=6.18', 'conviction': 0.191, 'falsifier': 'FCF yield below universe median OR base IRR below median'} (source: TEQ.ST/research/valuation.json#lens_consensus)
- R12 cash flow falls below 85% of the 2026-Q2 run rate without a temporary working-capital explanation, organic decline persists, or EBITA margin falls below 9%. (source: TEQ.ST/research/falsifier_specs.json)

## Open questions (stable)
- Confirm live TEQ.ST price before acting on IRR.
- Re-extract Q1 2026 interim (inventory tier, 0 chars) to filing-ground Q1 metrics.
- Verify FCF ex-acquisitions bridge vs operating CF 184.6 MSEK in annual.

## Canonical pointers (open only when needed)
- valuation: TEQ.ST/research/valuation.json (sha256 sha256:05fcf8b676578856...)
- thesis_card: TEQ.ST/research/thesis_card.json (sha256 sha256:18cb22f17e127545...)

## Excluded from this pack
- TEQ.ST/research/valuation.json (full; returns block included, open only for assumption audit)
- TEQ.ST/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
