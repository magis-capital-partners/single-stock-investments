# Agent context pack: MIAX (Miami International Holdings)

## Identity (stable)
- Ticker: MIAX
- Company: Miami International Holdings
- Book: holdings
- Stance: watch
- Archetype: croupier

## What this business is (stable)
Miami International Holdings (MIAX) owns and operates U.S. SEC-regulated securities exchanges and related market infrastructure. **[Fact]** The **MIAX Exchanges** include MIAX Options, MIAX Pearl (options and equities), MIAX Emerald, and MIAX Sapphire. **[Fact]** The group also operates the **Bermuda Stock Exchange**, **MIAX Futures Exchange**, and proprietary matching technology. **[Fact]** Revenue is primarily **transaction and clearing fees**, **access fees**, and **market data** (Q1 2026 fee mix: ~$315M transaction/clearing, ~$33M access, ~$13M market data, ~$8M other, in thousands per `10-Q_20260508`). **[Fact]** FY2025 consolidated revenue was **$1.364 billion** (+19.6% versus $1.140 billion in FY2024); net income **$70 million** (versus **$102 million** in FY2024 when debt-extinguishment and intangible-sale gains boosted earnings). **[Fact]** Cash and equivalents **$434 million** at 12/31/2025; about **69.8 million** diluted shares (FY2025 10-K).

## Why the market might be wrong (stable)
**[Inference]** The stock listed recently and trades near **~19 times** normalized free cash flow per share at **~$40**, so the market may be capitalizing fast revenue growth and futures/options share gains ahead of proven margin expansion. **[Inference]** FY2025 reported net income fell year over year even as revenue rose, because FY2024 included large non-operating gains (debt extinguishment and intangible dispositions per 10-K XBRL), which can make the franchise look weaker than mid-cycle owner cash. **[Inference]** No approved third-party work is in the file yet; return at this price is mostly **operating toll growth at a full multiple**, not a dated mispricing catalyst.

## Returns (stable, percent per year)
- Base return: 13.29% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 4.1, base 11.0, bull 17.4

## Key assumptions (stable)
- Price today: **$40.32** (source: Stooq MIAX.US close 2026-06-03)
- Starting free cash flow per share: **$2.08** (source: FY2025 OCF $167.8M minus capex $22.8M, divided by ~69.8M diluted shares (10-K))
- Cycle adjustment (starting cash): **mid** (source: FY2025 mid-cycle; exclude FY2024 debt-extinguishment and intangible-sale gains from owner-cash start; Q1 2026 EPS spike not in base FCF)
- Growth in years 1 through 5: **7.0%** per year (source: MIAX Futures OCC clearing, Pearl/Emerald share gains; mid-cycle toll growth)
- Growth in years 6 through 7: **5.0%** per year (source: Scenario base)
- Selling multiple in year 10: **18 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 11.036676309864337% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- Confirm post-IPO float, insider selling, and fully diluted share count after offering (source: MIAX/research/thesis_card.json)
- Separate Q1 2026 recurring earnings from IPO-related or one-time items before changing starting cash (source: MIAX/research/thesis_card.json)
- OCC futures clearing: treat May 2026 press as **[Assumption]** until 8-K/10-Q quantifies revenue (source: MIAX/research/thesis_card.json)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 11.0, 'key_metric': 'archetype=croupier', 'conviction': 0.05, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: MIAX/research/valuation.json#lens_consensus)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 13.0, 'key_metric': 'payoff_lens=operating', 'conviction': 0.05, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: MIAX/research/valuation.json#lens_consensus)

## Open questions (stable)
- Confirm post-IPO float, insider selling, and fully diluted share count after offering
- Separate Q1 2026 recurring earnings from IPO-related or one-time items before changing starting cash
- OCC futures clearing: treat May 2026 press as **[Assumption]** until 8-K/10-Q quantifies revenue

## Canonical pointers (open only when needed)
- valuation: MIAX/research/valuation.json (sha256 sha256:829ab4d1ba1d09b5...)
- thesis_card: MIAX/research/thesis_card.json (sha256 sha256:db031cb8c8d0e3d7...)

## Excluded from this pack
- MIAX/research/valuation.json (full; returns block included, open only for assumption audit)
- MIAX/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
