# Agent context pack: CME (CME Group Inc.)

## Identity (stable)
- Ticker: CME
- Company: CME Group Inc.
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
CME Group is the world's largest listed derivatives marketplace: futures and options on interest rates, equity indexes, foreign exchange, energy, metals, and agricultural products, plus clearing, market data, and collateral services. **[Fact]** Customers pay transaction, clearing, and market-data fees; CME does not take directional market risk on customer positions. **[Fact]** FY2025 total revenues were **$6,520.6 million**, operating income **$4,229.5 million**, and net income **$4,072.2 million** (`investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001156375_26_000009.htm`). **[Fact]** Q1 2026 revenues were **$1,880.1 million** with operating income **$1,309.7 million** and net income **$1,154.3 million** (`investor-documents/sec-edgar/10-Q_20260424_rpt20260331_acc0001156375_26_000020.htm`). Terry Duffy is Chairman and CEO.

## Why the market might be wrong (stable)
There is no dated payoff or structural discount here. **[Inference]** Q1 2026 operating margin is far above a typical mid-cycle year because rates and volatility lifted interest-rate and equity-index volumes; the market may treat that run rate as permanent. **[Inference]** Our base return uses FY2025 owner cash per share (**$11.40**), not the Q1 2026 earnings pace. Return is franchise earnings power at price, not a mispricing signal with a known catalyst date.

## Returns (stable, percent per year)
- Base return: 12.01% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 4.8, base 11.2, bull 15.3

## Key assumptions (stable)
- Price today: **$252.65** (source: Stooq CME.US close 2026-06-03)
- Starting free cash flow per share: **$11.4** (source: FY2025 cash from operations $4,277.1M minus ~$200M capital spending, divided by ~359M diluted shares (10-K FY2025))
- Cycle adjustment (starting cash): **mid** (source: FY2025 mid-cycle base; Q1 2026 revenue and operating income run above trend and are not inflated into starting cash flow)
- Growth in years 1 through 5: **7.0%** per year (source: Mid-cycle owner cash; exit near current ~22x cash flow multiple)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **22 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 11.19475246895006% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- First Marvin deep dive; no approved third-party sources in base IRR. (source: CME/research/thesis_card.json)
- Entry band **$210–220** for ~15% base return is illustrative pending human price confirmation. (source: CME/research/thesis_card.json)
- Confirm FY2025 capital spending line in 10-K cash flow statement for FCF tie-out. (source: CME/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 11.2, 'key_metric': 'archetype=croupier', 'conviction': 0.06, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: CME/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 13.2, 'key_metric': 'payoff_lens=operating', 'conviction': 0.06, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: CME/research/valuation.json#lens_consensus)

## Open questions (stable)
- First Marvin deep dive; no approved third-party sources in base IRR.
- Entry band **$210–220** for ~15% base return is illustrative pending human price confirmation.
- Confirm FY2025 capital spending line in 10-K cash flow statement for FCF tie-out.

## Canonical pointers (open only when needed)
- valuation: CME/research/valuation.json (sha256 sha256:b46fe98875e70f27...)
- thesis_card: CME/research/thesis_card.json (sha256 sha256:0e128762924dd7b0...)

## Excluded from this pack
- CME/research/valuation.json (full; returns block included, open only for assumption audit)
- CME/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
