# Agent context pack: BN (Brookfield Corporation)

## Identity (stable)
- Ticker: BN
- Company: Brookfield Corporation
- Book: holdings
- Stance: hold
- Archetype: platform

## What this business is (stable)
Brookfield Corporation is a global alternative-asset manager and owner of real-asset platforms. **[Fact]** Clients pay management and performance fees on capital deployed into infrastructure, real estate, credit, and private equity. **[Fact]** Owner economics are measured as distributable earnings, not GAAP net income. **[Fact]** Fee-bearing capital was **$672 billion** at June 30, 2026; insurance assets were **$191 billion**. **[Fact]** Trailing twelve month distributable earnings were **$6.2 billion**, or **$2.61 per share**. **[Inference]** Realizations are lumpy, so the base case grows owner cash without assuming a heroic carry year.

## Why the market might be wrong (stable)
There is **no dated Horizon Kinetics predictive attribute**. **[Inference]** The listed price (**$37.31** on 2026-09-17) sits far below Brookfield's own blended capital of **$66.64 per share** at June 30, 2026. GAAP marks on more than **$525 billion** of consolidated assets add noise. The combination with Brookfield Wealth Solutions is approved and expected to close this year, but that is a simplification path, not a known payoff date.

## Returns (stable, percent per year)
- Base return: 17.32% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear 11.8, base 16.5, bull 19.9

## Key assumptions (stable)
- Price today: **$37.31** (source: Yahoo BN 2026-09-17)
- Starting free cash flow per share: **$2.61** (source: LTM distributable earnings $2.61/sh per Q2 2026 supplemental (2026-Q2-BN-Supplemental.pdf))
- Growth in years 1 through 5: **8.0%** per year (source: Fee-related earnings grew 20% in Q2; trailing twelve month distributable earnings before realizations grew 7% per share. Base keeps 8% as a conservative path versus management 15%+ distributable earnings target.)
- Growth in years 6 through 7: **6.0%** per year (source: Scenario base)
- Selling multiple in year 10: **16 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: 16.45826448602666% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- Live price moved from **$42.39** (July dive) to **$37.31**. Confirm the quote is a regular-session close, not a bad print. (source: BN/research/thesis_card.json)
- Holdings already **hold**. Math now clears the 15% band. No agent capital decision. (source: BN/research/thesis_card.json)
- Management targets 15%+ distributable-earnings growth. Base uses 8%. Raising base growth to 10% would be a human override. (source: BN/research/thesis_card.json)
- The source-locked owner-earnings bridge falls below the level supporting the current decision-grade component. (source: BN/research/falsifier_specs.json)
- Tracked lens-investor history must be reconciled; existing specialist signals do not establish Hohn coverage. (source: _system/lenses/personas.json)

## Open questions (stable)
- Live price moved from **$42.39** (July dive) to **$37.31**. Confirm the quote is a regular-session close, not a bad print.
- Holdings already **hold**. Math now clears the 15% band. No agent capital decision.
- Management targets 15%+ distributable-earnings growth. Base uses 8%. Raising base growth to 10% would be a human override.

## Canonical pointers (open only when needed)
- valuation: BN/research/valuation.json (sha256 sha256:2c1f1038fa91a925...)
- thesis_card: BN/research/thesis_card.json (sha256 sha256:2d343228c88b8b61...)

## Excluded from this pack
- BN/research/valuation.json (full; returns block included, open only for assumption audit)
- BN/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
