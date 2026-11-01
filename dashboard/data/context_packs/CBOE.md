# Agent context pack: CBOE (Cboe Global Markets)

## Identity (stable)
- Ticker: CBOE
- Company: Cboe Global Markets
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
Cboe Global Markets operates exchange, clearing, and market-data infrastructure across options, equities, futures, and foreign exchange. **[Fact]** Customers pay transaction, clearing, listing, and subscription fees; the company does not take principal market risk. **[Fact]** FY2025 total revenues were **$4,714.2 million** (+15% versus **$4,094.5 million** in FY2024); operating income **$1,467.1 million**; net income **$1,100.0 million** (`investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001628280_26_010013.htm`). **[Fact]** Q1 2026 net revenues were **$1,272.8 million** (+6% versus **$1,195.0 million** in Q1 2025); net income **$385.7 million** (`investor-documents/sec-edgar/10-Q_20260501_rpt20260331_acc0001628280_26_029112.htm`). The franchise is anchored in proprietary index options (SPX, VIX) and a multi-venue U.S. equities stack (BZX, BYX, EDGA, EDGX) plus European and Asia-Pacific derivatives.

## Why the market might be wrong (stable)
There is no dated payoff or structural discount. **[Inference]** FY2025 and Q1 2026 benefited from elevated volatility and index trading; the stock at **~$285** embeds a premium multiple on strong recent cash flow. **[Inference]** Our base return uses FY2025 free cash flow per share (**$16.00**), not a peak run rate from Q1 2026 alone. Return is franchise earnings power at price, not a mispricing with a known catalyst date.

## Returns (stable, percent per year)
- Base return: 13.42% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 7.2, base 13.2, bull 16.3

## Key assumptions (stable)
- Price today: **$285.23** (source: Stooq CBOE.US close 2026-06-03)
- Starting free cash flow per share: **$16.0** (source: FY2025 OCF $1,752.6M minus capex $71.0M divided by ~105.1M diluted shares)
- Cycle adjustment (starting cash): **mid** (source: FY2025 mid-cycle base; Q1 2026 net revenues $1,272.8M (+6% YoY) above trend but not inflated into starting cash flow)
- Growth in years 1 through 5: **6.0%** per year (source: Mid-cycle FCF growth; Data Vantage mix shift; exit ~20x cash flow)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **20 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 13.17011271937889% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- First Marvin deep dive; batch onboard 2026-06-03. (source: CBOE/research/thesis_card.json)
- No third-party sources indexed; stance rests on filings only. (source: CBOE/research/thesis_card.json)
- Entry band **$250–255** for ~15% base annual return is model-derived, not human-approved. (source: CBOE/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 13.2, 'key_metric': 'archetype=croupier', 'conviction': 0.16, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: CBOE/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 15.2, 'key_metric': 'payoff_lens=operating', 'conviction': 0.16, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: CBOE/research/valuation.json#lens_consensus)

## Open questions (stable)
- First Marvin deep dive; batch onboard 2026-06-03.
- No third-party sources indexed; stance rests on filings only.
- Entry band **$250–255** for ~15% base annual return is model-derived, not human-approved.

## Canonical pointers (open only when needed)
- valuation: CBOE/research/valuation.json (sha256 sha256:4d996502ca700eee...)
- thesis_card: CBOE/research/thesis_card.json (sha256 sha256:252bfc1005fc9c1c...)

## Excluded from this pack
- CBOE/research/valuation.json (full; returns block included, open only for assumption audit)
- CBOE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
