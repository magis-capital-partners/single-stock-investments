# Agent context pack: LSEG (London Stock Exchange Group)

## Identity (stable)
- Ticker: LSEG
- Company: London Stock Exchange Group
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
London Stock Exchange Group is a global financial markets infrastructure and data company. **[Fact]** Four divisions serve more than 44,000 customers: Data & Analytics (subscriptions and workflow), FTSE Russell (indices and asset-based fees), Risk Intelligence (compliance screening), and Markets (trading venues, clearing via LCH, and post-trade). **[Fact]** FY2025 total income excluding recoveries was **£8,986 million** (+7.1% organic), with adjusted EBITDA margin **50.3%** and equity free cash flow **£2,445 million** (`investor-documents/ir-lseg/annual_report_2025.pdf`, Financial review). **[Fact]** Q1 2026 total income excluding recoveries was **£2,415 million** (+9.8% organic), the strongest quarterly growth in more than five years (`investor-documents/ir-lseg/trading_update_q1_2026_rns_23apr2026.pdf`). The business earns toll-like fees on market activity, index assets under management, and recurring data subscriptions with minimal principal risk on core operations.

## Why the market might be wrong (stable)
No clear structural mispricing or dated payoff. **[Inference]** Quality croupiers (SPGI, ICE, LSEG) rarely trade to a 15% annual return; the market prices Refinitiv integration progress, AI-ready data distribution, and clearing entrenchment at a premium. **[Inference]** Q1 2026 acceleration (+9.8% organic income, Markets +15.5%) may be partly cyclical (volatile trading volumes) rather than a permanent step-up; we normalize on FY2025 equity free cash flow, not the upper half of 2026 guidance. **Predictive attribute:** none (franchise earnings at price, not yield-curve or market-structure discount).

## Returns (stable, percent per year)
- Base return: 14.65% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 8.0, base 13.5, bull 17.7

## Key assumptions (stable)
- Price today: **$91.26** (source: LSE ~9,126p close 2026-05-29 (shareprices.com))
- Starting free cash flow per share: **$4.67** (source: FY2025 equity free cash flow £2,445M ÷ 524M weighted average shares)
- Cycle adjustment (starting cash): **mid** (source: FY2025 mid-cycle base; Q1 2026 organic income +9.8% run-rate above trend (not inflated into starting cash flow))
- Growth in years 1 through 5: **7.0%** per year (source: 6.5-7.5% organic income guide; margin expansion; ~20× spot P/FCF → 22× exit)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **22 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Registry lists market as US; LSEG is **LSE-listed (LSEG:LON)**. Confirm whether portfolio holds GBP or ADR exposure. (source: LSEG/research/thesis_card.json)
- First dive; no prior stance or price confirmation from human. (source: LSEG/research/thesis_card.json)
- AI / LSEG Everywhere revenue not yet split in filings; monitor H1 2026 results (expected July 2026). (source: LSEG/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 13.5, 'key_metric': 'archetype=croupier', 'conviction': 0.175, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: LSEG/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 15.5, 'key_metric': 'payoff_lens=pending', 'conviction': 0.175, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: LSEG/research/valuation.json#lens_consensus)

## Open questions (stable)
- Registry lists market as US; LSEG is **LSE-listed (LSEG:LON)**. Confirm whether portfolio holds GBP or ADR exposure.
- First dive; no prior stance or price confirmation from human.
- AI / LSEG Everywhere revenue not yet split in filings; monitor H1 2026 results (expected July 2026).

## Canonical pointers (open only when needed)
- valuation: LSEG/research/valuation.json (sha256 sha256:534a26c6f744009c...)
- thesis_card: LSEG/research/thesis_card.json (sha256 sha256:c963820f477dc2a6...)

## Excluded from this pack
- LSEG/research/valuation.json (full; returns block included, open only for assumption audit)
- LSEG/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
