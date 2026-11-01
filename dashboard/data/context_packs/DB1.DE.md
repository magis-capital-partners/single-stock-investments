# Agent context pack: DB1.DE (Deutsche Boerse AG)

## Identity (stable)
- Ticker: DB1.DE
- Company: Deutsche Boerse AG
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
Deutsche Börse Group is a leading European market infrastructure operator spanning exchanges, clearing, custody, fund distribution, indices, and buy-side software. **[Fact]** Four segments cover the transaction value chain: Investment Management Solutions (SimCorp, ISS STOXX indices and ESG data), Trading & Clearing (Eurex derivatives, Xetra cash equities, commodities, FX and digital assets), Fund Services (Clearstream fund connectivity), and Securities Services (custody, settlement, fund processing). **[Fact]** FY2025 net revenue was **€6,026 million** (+3% versus **€5,829 million** in 2024); net revenue excluding treasury result was **€5,189 million** (+9%). EBITDA was **€3,512 million** and EBITDA excluding treasury result **€2,675 million** (+14%). Net profit attributable to shareholders was **€1,995 million**; diluted earnings per share **€10.90** and cash earnings per share **€11.65** (`investor-documents/ir-db1/annual_report_2025.pdf`, Results of operations). **[Fact]** Q1 2026 net revenue excluding treasury result was **€1,434 million** (+12% versus **€1,277 million**); EBITDA excluding treasury result **€683 million** (+18%); net profit attributable to Deutsche Börse AG shareholders **€585 million** (+11%) (`investor-documents/ir-db1/quarterly_statement_q1_2026.pdf`). The company earns toll-like fees on trading, clearing, data, and fund workflows with minimal balance-sheet principal risk on core operations.

## Why the market might be wrong (stable)
No dated structural discount or yield-curve setup. **[Inference]** Q1 2026 acceleration (+12% net revenue ex treasury, +18% EBITDA ex treasury) reflects elevated volatility in rates, commodities, and equities; the market may treat that pace as durable. **[Inference]** Declining treasury result (net interest from clearing cash) masks operating strength: total net revenue grew only 9% in Q1 2026 while operating segments grew faster. We normalize on FY2025 owner cash flow, not Q1 2026 peak volumes. **Predictive attribute:** none (franchise earnings at price, not market-structure exclusion).

## Returns (stable, percent per year)
- Base return: 14.48% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 7.9, base 13.4, bull 17.5

## Key assumptions (stable)
- Price today: **$246.4** (source: Yahoo Finance DB1.DE ~€246.40 (2026-06-11))
- Starting free cash flow per share: **$12.52** (source: FY2025 cash from operations ex CCP €2,672M minus capex (intangibles €325M + PP&E €55M) ÷ 183.1M shares)
- Cycle adjustment (starting cash): **mid** (source: FY2025 mid-cycle base; Q1 2026 net revenue ex treasury +12% run-rate above trend (not inflated into starting cash flow); treasury result declining with rates)
- Growth in years 1 through 5: **7.0%** per year (source: 8% organic revenue CAGR guide to 2028; ~20× spot P/FCF → 22× exit)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **22 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 13.37586756567339% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- First dive; no prior stance or live-price confirmation from human. (source: DB1.DE/research/thesis_card.json)
- Confirm EUR exposure sizing versus USD-reporting exchange peers (ICE, CME). (source: DB1.DE/research/thesis_card.json)
- Allfunds closing timeline and ISS STOXX litigation outcome may change treasury and segment mix. (source: DB1.DE/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 13.4, 'key_metric': 'archetype=croupier', 'conviction': 0.17, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: DB1.DE/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 15.4, 'key_metric': 'payoff_lens=operating', 'conviction': 0.17, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: DB1.DE/research/valuation.json#lens_consensus)

## Open questions (stable)
- First dive; no prior stance or live-price confirmation from human.
- Confirm EUR exposure sizing versus USD-reporting exchange peers (ICE, CME).
- Allfunds closing timeline and ISS STOXX litigation outcome may change treasury and segment mix.

## Canonical pointers (open only when needed)
- valuation: DB1.DE/research/valuation.json (sha256 sha256:00453e9b9aae0d01...)
- thesis_card: DB1.DE/research/thesis_card.json (sha256 sha256:c868ffb0aa85d7fc...)

## Excluded from this pack
- DB1.DE/research/valuation.json (full; returns block included, open only for assumption audit)
- DB1.DE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
