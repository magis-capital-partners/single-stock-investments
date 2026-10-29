# Agent context pack: ICE (Intercontinental Exchange)

## Identity (stable)
- Ticker: ICE
- Company: Intercontinental Exchange
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Intercontinental Exchange operates global exchange, clearing, and market-data infrastructure plus mortgage-technology workflows. **[Fact]** Customers pay transaction, clearing, listing, and subscription fees across three segments: Exchanges, Fixed Income and Data, and Mortgage Technology. Revenue scales with trading and clearing activity, not balance-sheet lending. **[Fact]** FY2025 net revenues were **$9,931M** with operating income **$4,929M** and net income **$3,315M** (`investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001571949_26_000004.htm`). **[Fact]** Q1 2026 net revenues were **$2,977M** (+20% YoY vs **$2,473M**); net income **$1,413M** vs **$797M** (`investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001571949_26_000007.htm`). CEO Jeffrey Sprecher has led the company since its founding.

## Why the market might be wrong (stable)
There is no dated payoff or structural discount here. **[Inference]** Q1 2026 operating income **$1,665M** (+36% YoY vs **$1,221M**) reflects elevated transaction activity; the market may treat that run rate as permanent. **[Inference]** Our base return uses mid-cycle FY2025 free cash flow per share (**$7.41**), not the Q1 peak. Return is franchise earnings power at price, not a mispricing signal with a known catalyst date.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: **$141.57** (source: Yahoo ICE close 2026-07-20)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Approved 2026-05-29:** Live price ~**$153** confirmed (slightly below spot). **Stance: hold** (override). Entry band **$115–125** for ~**15%** per year on base case agreed. (source: ICE/research/thesis_card.json)
- Open: Q1 2026 net income may include investment fair-value gains — quantify from Q2 10-Q when filed. (source: ICE/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 12.15, 'key_metric': 'archetype=compounder', 'conviction': 0.108, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: ICE/research/valuation.json#lens_consensus)
- {'persona': 'munger', 'label': 'Charlie Munger', 'verdict': 'hold', 'return_pct': 12.15, 'key_metric': 'moat=stable', 'conviction': 0.008, 'falsifier': 'Moat eroding/unproven or irr_method pending'} (source: ICE/research/valuation.json#lens_consensus)
- {'persona': 'buffett_weschler', 'label': 'Buffett / Weschler', 'verdict': 'hold', 'return_pct': 12.15, 'key_metric': 'owner_earnings_yield=None', 'conviction': 0.008, 'falsifier': 'Eroding moat or dhando none'} (source: ICE/research/valuation.json#lens_consensus)

## Open questions (stable)
- Approved 2026-05-29:** Live price ~**$153** confirmed (slightly below spot). **Stance: hold** (override). Entry band **$115–125** for ~**15%** per year on base case agreed.
- Open: Q1 2026 net income may include investment fair-value gains — quantify from Q2 10-Q when filed.

## Canonical pointers (open only when needed)
- valuation: ICE/research/valuation.json (sha256 sha256:dccf9e556e1c9120...)
- thesis_card: ICE/research/thesis_card.json (sha256 sha256:1eaae1259b4a84fd...)

## Excluded from this pack
- ICE/research/valuation.json (full; returns block included, open only for assumption audit)
- ICE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
