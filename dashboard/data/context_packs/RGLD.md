# Agent context pack: RGLD (Royal Gold Inc.)

## Identity (stable)
- Ticker: RGLD
- Company: Royal Gold Inc.
- Book: holdings
- Stance: watch
- Archetype: compounder

## What this business is (stable)
Royal Gold is a precious-metals royalty and streaming company headquartered in Denver. **[Fact]** It acquires and holds royalties, streams, and similar interests that entitle it to a share of production or revenue from mines operated by third parties, without Royal Gold acting as the mine operator. **[Fact]** Shares trade on Nasdaq (RGLD). **[Fact]** FY2025 revenue was **$1,030 million**, operating income **$638 million**, and net income **$466 million** (diluted earnings **$6.69** per share) per `investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0000085535_26_000008.htm`. **[Fact]** FY2025 cash from operations was **$705 million**; the balance sheet expanded sharply after the Sandstorm Gold combination (goodwill and deferred taxes rose; total assets **$9.54 billion** at year-end 2025 versus **$3.39 billion** at year-end 2024).

## Why the market might be wrong (stable)
The stock may trade as levered gold beta at a full multiple after the Sandstorm combination, while the underlying model is a high-margin toll on ounces with limited sustaining capital spending. **[Inference]** FY2025 earnings power benefited from both metal prices and enlarged attributable production; the market can treat peak-year cash flow as permanent. **[Inference]** Goodwill and deferred tax liabilities from purchase accounting make book value a poor anchor, but the economic asset is the contracted cash stream portfolio, not GAAP intangibles. **[Inference]** Proof-first component math at base case sums to about **$152** per share of economic value versus a price near **$217**, suggesting the market embeds development optionality and mid-cycle gold assumptions not yet reproduced in filing-locked owner-cash paths.

## Returns (stable, percent per year)
- Base return: 10.67% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 2.5, base 9.3, bull 15.4

## Key assumptions (stable)
- Price today: **$187.36** (source: Yahoo RGLD close 2026-07-20)
- Starting free cash flow per share: **$9.0** (source: FY2025 cash from operations $704.8M minus immaterial capital spending, divided by ~78M diluted shares (pre-full Sandstorm weighting); Q1 2026 run-rate ~$8.3/sh on ~85M shares)
- Growth in years 1 through 5: **4.0%** per year (source: Combined portfolio growth near inflation plus modest development ramp; exit ~22x cash flow)
- Growth in years 6 through 7: **2.5%** per year (source: Scenario base)
- Selling multiple in year 10: **22 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 9.306690807115746% per year; status diagnostic. Research only.
- Buy bands: withheld; model stock_specific.
- Pending VIC PDF not in base IRR. (source: RGLD/research/thesis_card.json)
- Sandstorm deferred tax and development conversion timing remain widest judgment bands. (source: RGLD/research/thesis_card.json)
- Live price and final base IRR after mechanical refresh. (source: RGLD/research/thesis_card.json)
- Typed moat-impairment falsifiers are missing. (source: RGLD/research/valuation_contract.json)
- Tracked lens-investor history must be reconciled; existing specialist signals do not establish Hohn coverage. (source: _system/lenses/personas.json)

## Open questions (stable)
- Pending VIC PDF not in base IRR.
- Sandstorm deferred tax and development conversion timing remain widest judgment bands.
- Live price and final base IRR after mechanical refresh.

## Canonical pointers (open only when needed)
- valuation: RGLD/research/valuation.json (sha256 sha256:d1718afa3d3d88fc...)
- thesis_card: RGLD/research/thesis_card.json (sha256 sha256:cea251d012963cb0...)

## Excluded from this pack
- RGLD/research/valuation.json (full; returns block included, open only for assumption audit)
- RGLD/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
