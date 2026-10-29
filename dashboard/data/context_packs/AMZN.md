# Agent context pack: AMZN (Amazon.com)

## Identity (stable)
- Ticker: AMZN
- Company: Amazon.com
- Book: holdings
- Stance: hold
- Archetype: compounder

## What this business is (stable)
Amazon.com is a global retailer and technology platform. **[Fact]** Customers pay for physical and digital goods (North America and International stores), cloud infrastructure (AWS), advertising, and third-party seller services. **[Fact]** Cash to shareholders comes from operating cash flow after capital spending on logistics and data centers, not from a single product line. **[Fact]** FY2025 net sales were **$716.9 billion** (+12%); Q1 2026 net sales **$181.5 billion** (+17%). **[Fact]** AWS is the profit engine: Q1 2026 AWS sales **$37.6 billion** (+28%) with segment operating income margin **37.7%**. **[Inference]** Reported free cash flow is temporarily depressed by AI-related capital spending while operating cash flow remains large.

## Why the market might be wrong (stable)
There is **no clear dated mispricing signal** (HK predictive attribute: **none**). **[Inference]** The market prices Amazon as a growth compounder with embedded artificial intelligence optionality, not as a distressed asset. **[Inference]** The debate is whether **normalized owner cash flow** after capital spending (not trailing twelve-month free cash flow of **$1.2 billion**) supports the multiple at today's price. Return is **franchise earnings power at price**, contingent on capital spending moderating toward a **~$90 billion** sustainable run rate versus trailing purchases of **$147.3 billion**.

## Returns (stable, percent per year)
- Base return: 3.14% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -5.2, base 1.7, bull 6.9

## Key assumptions (stable)
- Price today: **$250.88** (source: Yahoo AMZN close 2026-10-02)
- Starting free cash flow per share: **$5.35** (source: Q1-26 TTM OCF \.5B less normalized capex ~\ / ~10.95B diluted shares (valuation.json))
- Growth in years 1 through 5: **9.0%** per year (source: AWS/ads/chips growth; capex moderates toward ~60% of OCF by Y5)
- Growth in years 6 through 7: **7.0%** per year (source: Scenario base)
- Selling multiple in year 10: **24 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)
- AI inflection FCF₀ (sensitivity): **$9.0/sh** (source: [Assumption] capex ~$90B sustainable vs $147B TTM; needs mgmt guide)
- AI inflection implied return: **16.0%** (source: `marvin_valuation.py` overlay)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 1.6722676291436187% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- Confirm live price before acting on IRR. (source: AMZN/research/thesis_card.json)
- Hold override?** Quality compounder with sub-15% IRR at spot. (source: AMZN/research/thesis_card.json)
- Track quarterly capital spending versus operating cash flow; strip Anthropic gains from net income. (source: AMZN/research/thesis_card.json)
- Model path from **$147B** TTM capex toward **~$90B** sustainable. (source: AMZN/research/thesis_card.json)
- Reconcile Lawrence normalized owner cash ($5.35/sh) with contract reinvestment DCF ($11.64/sh base value). (source: AMZN/research/thesis_card.json)

## Open questions (stable)
- Confirm live price before acting on IRR.
- Hold override?** Quality compounder with sub-15% IRR at spot.
- Track quarterly capital spending versus operating cash flow; strip Anthropic gains from net income.
- Model path from **$147B** TTM capex toward **~$90B** sustainable.
- Reconcile Lawrence normalized owner cash ($5.35/sh) with contract reinvestment DCF ($11.64/sh base value).
- VIC PDF pending approval; do not blend into base IRR.

## Canonical pointers (open only when needed)
- valuation: AMZN/research/valuation.json (sha256 sha256:6345e161e3c55a95...)
- thesis_card: AMZN/research/thesis_card.json (sha256 sha256:f2a8117d0e2e2ecc...)

## Excluded from this pack
- AMZN/research/valuation.json (full; returns block included, open only for assumption audit)
- AMZN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
