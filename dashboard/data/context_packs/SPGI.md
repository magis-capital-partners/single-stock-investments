# Agent context pack: SPGI (S&P Global)

## Identity (stable)
- Ticker: SPGI
- Company: S&P Global
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
S&P Global sells financial intelligence: credit ratings on debt issuance, index licensing tied to benchmark AUM, Market Intelligence data subscriptions, Platts commodity benchmarks, and Mobility analytics (spin planned mid-2026). **[Fact]** Customers pay transaction fees when markets issue debt, recurring subscriptions for data, and AUM-linked index fees. **[Fact]** FY2025 revenue was **$15,336M** with operating income **$6,478M** and net income **$4,471M** (`investor-documents/sec-edgar/10-K_20260211_rpt20251231_acc0000064040_26_000013.htm`). **[Fact]** Q1 2026 revenue was **$4,171M** (+10% vs **$3,777M**) with GAAP diluted EPS **$4.69** vs **$3.54** and operating income **$2,002M** vs **$1,578M** (`investor-documents/sec-edgar/10-Q_20260428_rpt20260331_acc0000064040_26_000024.htm`). The business earns toll-like fees with minimal principal risk on core operations.

## Why the market might be wrong (stable)
No clear mispricing signal or dated payoff. **[Inference]** Quality compounders rarely trade to a 15% IRR; the market prices covenant-required ratings and S&P 500 index entrenchment at a premium. **[Inference]** May 2026 Market Intelligence leadership transition may create temporary concern, but 2026 guidance was reiterated per prior 8-K. Return is franchise earnings at price unless an issuance drought forces a cyclical re-rating.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$410.843** (source: Yahoo ~2026-05-26)
- Starting free cash flow per share: **$17.5** (source: FY2025 adj FCF ~$5.5B / 305.1M shares (113% payout of adj FCF))
- Cycle adjustment (starting cash): **mid** (source: Mid-cycle issuance; not peak Ratings spike in starting FCF)
- Growth in years 1 through 5: **7.0%** per year (source: 6-8% organic guide; ~23x spot P/FCF → 22x exit)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **22 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Model pro-forma SPGI ex-Mobility before sizing post-spin (source: SPGI/research/thesis_card.json)
- Hold** override for incumbent croupier allocation? (source: SPGI/research/thesis_card.json)
- Track billed issuance and index AUM monthly (source: SPGI/research/thesis_card.json)
- Confirm live price (~$411 May 27, 2026) (source: SPGI/research/thesis_card.json)
- Owner earnings, incremental returns, or reinvestment runway fall below the low-case bridge. (source: SPGI/research/falsifier_specs.json)

## Open questions (stable)
- Model pro-forma SPGI ex-Mobility before sizing post-spin
- Hold** override for incumbent croupier allocation?
- Track billed issuance and index AUM monthly
- Confirm live price (~$411 May 27, 2026)

## Canonical pointers (open only when needed)
- valuation: SPGI/research/valuation.json (sha256 sha256:cc31adef5613e39b...)
- thesis_card: SPGI/research/thesis_card.json (sha256 sha256:5dca0c52b96fc085...)

## Excluded from this pack
- SPGI/research/valuation.json (full; returns block included, open only for assumption audit)
- SPGI/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
