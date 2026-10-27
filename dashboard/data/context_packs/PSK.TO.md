# Agent context pack: PSK.TO (PrairieSky Royalty Ltd.)

## Identity (stable)
- Ticker: PSK.TO
- Company: PrairieSky Royalty Ltd.
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
PrairieSky Royalty Ltd. is Canada's largest passive oil and natural gas royalty company. **[Fact]** It collects cash from third-party operators on **18.6 million acres** of royalty lands (**9.9 million** fee-simple mineral title acres plus **8.7 million** gross overriding royalty acres) without drilling wells, paying operating costs, or bearing abandonment liabilities (`PrairieSky-Royalty-Presentation-April-2026-POST-AGM.pdf`). **[Fact]** FY2025 funds from operations were **$353.0 million** (**$1.50** per share) on royalty production averaging **25,855** barrels of oil equivalent per day; dividends declared were **$1.04** per share (`PSK-2025-YE-MDA.pdf`). **[Fact]** Q1 2026 funds from operations were **$94.9 million** (**$0.41** per share) on **26,293** BOE per day; net debt was **$257.7 million** with **232.4 million** shares outstanding (`2026-Q1-MDA-FINAL.pdf`). **[Fact]** The company employs roughly **70** Calgary-based staff and returns essentially all excess cash via dividends and opportunistic share repurchases.

## Why the market might be wrong (stable)
The market may price PrairieSky as a mature Western Canadian yield stock and underweight the perpetual undeveloped acreage option embedded in fee-simple mineral title. **[Inference]** Third-party spuds on PrairieSky lands totaled **201** wells in Q1 2026 (Clearwater, Mannville Stack, Duvernay, Basal Quartz), with oil royalty production up **6%** year over year while the company carries **zero** operating capital spending. **[Inference]** US and PFIC tax friction (15% Canadian withholding, Form 8621) may keep some yield-focused US accounts on the sidelines despite a **~3.1%** cash dividend at today's price and a conservative **65%** payout ratio in Q1 2026.

## Returns (stable, percent per year)
- Base return: 6.06% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -1.5, base 5.2, bull 9.5

## Key assumptions (stable)
- Price today: **$34.5** (source: Yahoo PSK.TO close 2026-07-20)
- Starting free cash flow per share: **$1.5** (source: FY2025 funds from operations $1.50/sh per PSK-2025-YE-MDA.pdf; Q1 2026 run-rate $0.41/sh ($1.64 annualized))
- Growth in years 1 through 5: **4.0%** per year (source: 4% per-share FFO growth (6% oil royalty CAGR offset by commodity mix); exit 18x; dividend $1.06 sustained)
- Growth in years 6 through 7: **3.0%** per year (source: Scenario base)
- Selling multiple in year 10: **18 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 5.165739140236016% per year; status diagnostic. Research only.
- Buy bands: withheld; model stock_specific.
- First deep dive from batch onboard 2026-06-03; verify PFIC treatment for US taxable accounts. (source: PSK.TO/research/thesis_card.json)
- Confirm CAD price source vs TSX close on review date. (source: PSK.TO/research/thesis_card.json)
- Undeveloped acreage overlay left at explicit zero in base; human may size NAV overlay separately. (source: PSK.TO/research/thesis_card.json)
- {'persona': 'pabrai', 'label': 'Mohnish Pabrai', 'verdict': 'pass', 'return_pct': -1.5, 'key_metric': 'downside_upside_ratio=0.158', 'conviction': 0.825, 'falsifier': 'dhando -> none OR net-debt/EBITDA > 3 OR bear return < -15%'} (source: PSK.TO/research/valuation.json#lens_consensus)
- Typed moat-impairment falsifiers are missing. (source: PSK.TO/research/valuation_contract.json)

## Open questions (stable)
- First deep dive from batch onboard 2026-06-03; verify PFIC treatment for US taxable accounts.
- Confirm CAD price source vs TSX close on review date.
- Undeveloped acreage overlay left at explicit zero in base; human may size NAV overlay separately.

## Canonical pointers (open only when needed)
- valuation: PSK.TO/research/valuation.json (sha256 sha256:e6de98081854a3af...)
- thesis_card: PSK.TO/research/thesis_card.json (sha256 sha256:8f04de739963f18d...)

## Excluded from this pack
- PSK.TO/research/valuation.json (full; returns block included, open only for assumption audit)
- PSK.TO/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
