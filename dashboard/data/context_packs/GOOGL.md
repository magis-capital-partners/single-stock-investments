# Agent context pack: GOOGL (Alphabet Inc.)

## Identity (stable)
- Ticker: GOOGL
- Company: Alphabet Inc.
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Alphabet Inc. owns Google (Search, YouTube, Android, Chrome) and Google Cloud. **[Fact]** Advertisers and enterprises pay for ad auctions, cloud compute, and subscriptions; consumers use free products that drive query volume and data. **[Fact]** FY2025 revenue was **$402.8B** (+15%); Q1 2026 revenue **$109.9B** (+22%). **[Fact]** Reportable segments are **Google Services**, **Google Cloud**, and **Other Bets** (Waymo, etc.), plus **Alphabet-level activities** (centralized AI R&D). **[Fact]** FY2025 consolidated operating cash flow **$125.3B**, capital spending **$52.5B**, owner free cash flow **~$72.8B**; management guides **$180-190B** capital spending in 2026. **[Inference]** Owner economics depend on Cloud return on invested capital versus the capital spending step-up and whether Search monetization holds as interfaces shift to AI.

## Why the market might be wrong (stable)
There is **no clear dated mispricing signal** (predictive attribute: **none**). **[Inference]** At **~$386**, the stock prices Cloud AI optionality and Search resilience together. **[Inference]** A single consolidated free cash flow growth rate hides **divergent segment economics**: Services throws off most cash today while Cloud and Alphabet-level spend absorb the 2026 capital guide. **[Inference]** Proof-first component math sums to **~$348 per share** base economic value versus **~$386** price, implying the market embeds higher Cloud multiples or faster capex normalization than the bounded proof schedule.

## Returns (stable, percent per year)
- Base return: 0.12% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -7.7, base 0.5, bull 4.4

## Key assumptions (stable)
- Price today: **$386.0** (source: NASDAQ ~May 26, 2026 (CNBC quote; confirm live))
- Starting free cash flow per share: **$5.85** (source: FY2025 OCF $125.3B − capex $52.5B ÷ ~12.45B diluted shares (10-K))
- Growth in years 1 through 5: **11.0%** per year (source: Cloud AI mix shift; normalize post-capex ramp)
- Growth in years 6 through 7: **8.0%** per year (source: Scenario base)
- Selling multiple in year 10: **25 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- AI inflection FCF₀ (sensitivity): **$8.0/sh** (source: [Assumption] normalized ~2028 post-capex; needs filing bridge)
- AI inflection implied return: **10.2%** (source: `marvin_valuation.py` overlay)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 0.47592114643122674% per year; status diagnostic. Research only.
- Buy bands: withheld; model stock_specific.
- Confirm live price and diluted share count against latest filing. (source: GOOGL/research/thesis_card.json)
- Promote AI inflection or third-party views into base case only after human OK. (source: GOOGL/research/thesis_card.json)
- Stance and sizing require `human_decision.json`. (source: GOOGL/research/thesis_card.json)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'watch', 'return_pct': 0.5, 'key_metric': 'payoff_lens=pending', 'conviction': 0.575, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} (source: GOOGL/research/valuation.json#lens_consensus)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'watch', 'return_pct': 2.4, 'key_metric': 'archetype=compounder', 'conviction': 0.38, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} (source: GOOGL/research/valuation.json#lens_consensus)

## Open questions (stable)
- Confirm live price and diluted share count against latest filing.
- Promote AI inflection or third-party views into base case only after human OK.
- Stance and sizing require `human_decision.json`.

## Canonical pointers (open only when needed)
- valuation: GOOGL/research/valuation.json (sha256 sha256:173cc601789b5579...)
- thesis_card: GOOGL/research/thesis_card.json (sha256 sha256:8cea6511a4364698...)

## Excluded from this pack
- GOOGL/research/valuation.json (full; returns block included, open only for assumption audit)
- GOOGL/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
