# Agent context pack: FNV (Franco-Nevada Corporation)

## Identity (stable)
- Ticker: FNV
- Company: Franco-Nevada Corporation
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Franco-Nevada is a Toronto- and New York-listed gold-focused royalty and streaming company. **[Fact]** It earns cash from gross-metal-equivalent ounces (GEOs) on third-party mines without operating production assets or mine-level capital spending. **[Fact]** FY2025 revenue was **$1,822.8 million** (+64%); operating cash flow **$1,493.7 million** (+80%); **519,106** GEOs sold including **11,208** from Cobre Panamá (`investor-documents/ir-fnv/NR-Franco-Nevada-Reports-Record-2025-Results-vF-2026-03-10.pdf`). **[Fact]** The company reports **no debt** and **$3.1 billion** available capital at year-end 2025, rising to **$3.4 billion** at March 31, 2026 (`investor-documents/ir-fnv/NR-Franco-Nevada-Reports-Record-Q1-2026-Results-vFinal-2026-05-12.pdf`). **[Fact]** Quarterly dividend is **$0.44** per share (16% increase for 2026; **$1.76** annualized).

## Why the market might be wrong (stable)
The market may treat Franco-Nevada as a passive gold beta at a peak multiple and underweight the portfolio option stack. **[Inference]** Record FY2025-Q1 2026 cash flows embed elevated gold, silver, and (in Q2 outlook) oil prices; a quality premium may compress if commodities normalize. **[Inference]** Cobre Panamá restart, recent acquisitions (Cascabel buy-back, Victoria Gold portfolio, Bullabulling), and operator exploration spend on the royalty book are not fully in 2026 GEO guidance. **[Inference]** Unlike operating miners, Franco-Nevada benefits from higher oil prices without proportionate cost inflation (CEO Q1 2026 remarks).

## Returns (stable, percent per year)
- Base return: 7.22% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -0.4, base 5.6, bull 10.4

## Key assumptions (stable)
- Price today: **$215.2** (source: Yahoo FNV close 2026-07-23)
- Starting free cash flow per share: **$7.75** (source: FY2025 net cash from operating activities $1,493.7M / 192.7M weighted average shares (2025 annual report MD&A))
- Growth in years 1 through 5: **4.0%** per year (source: 2026 GEO guidance 510-570k; fixed conversion ratios; dividend $1.76/yr; mid-single-digit cash flow growth [Assumption] off FY2025 record)
- Growth in years 6 through 7: **3.0%** per year (source: Scenario base)
- Selling multiple in year 10: **24 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 5.569219348576412% per year; status diagnostic. Research only.
- Buy bands: withheld; model stock_specific.
- SEC EDGAR folder not yet populated. (source: FNV/research/thesis_card.json)
- Q1 2026 CRA refund and Cascabel buy-back: confirm normalized owner cash if promoting overlay. (source: FNV/research/thesis_card.json)
- Cobre Panamá probability and terminal value are **[Assumption]**. (source: FNV/research/thesis_card.json)
- Synthesis weights pending human approval in `valuation.json`. (source: FNV/research/thesis_card.json)
- {'persona': 'pabrai', 'label': 'Mohnish Pabrai', 'verdict': 'pass', 'return_pct': -0.4, 'key_metric': 'downside_upside_ratio=0.038', 'conviction': 0.77, 'falsifier': 'dhando -> none OR net-debt/EBITDA > 3 OR bear return < -15%'} (source: FNV/research/valuation.json#lens_consensus)

## Open questions (stable)
- SEC EDGAR folder not yet populated.
- Q1 2026 CRA refund and Cascabel buy-back: confirm normalized owner cash if promoting overlay.
- Cobre Panamá probability and terminal value are **[Assumption]**.
- Synthesis weights pending human approval in `valuation.json`.

## Canonical pointers (open only when needed)
- valuation: FNV/research/valuation.json (sha256 sha256:4bc4c01db4e9b32c...)
- thesis_card: FNV/research/thesis_card.json (sha256 sha256:ef3029a49790f4d9...)

## Excluded from this pack
- FNV/research/valuation.json (full; returns block included, open only for assumption audit)
- FNV/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
