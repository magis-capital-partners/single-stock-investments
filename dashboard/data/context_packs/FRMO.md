# Agent context pack: FRMO (FRMO Corporation)

## Identity (stable)
- Ticker: FRMO
- Company: FRMO Corporation
- Book: holdings
- Stance: hold
- Archetype: holding_co

## What this business is (stable)
FRMO Corporation is a Delaware holding company affiliated with Horizon Kinetics. It does not run an operating business. **[Fact]** It owns concentrated stakes in investment partnerships, exchange infrastructure (Miami International Holdings), Horizon Kinetics Holding Corp., and smaller fund and digital-asset positions. Revenue to shareholders comes from fair-value marks on those investments, advisory royalty interests, and fund economics, not from product sales. **[Fact]** As of February 28, 2026, total assets were $919.5 million and FRMO-attributable stockholders' equity was $376.7 million, about $8.55 per share. **[Fact]** Roughly 82% of FRMO's equity sits in a single consolidated investment position ("Investment A"). The stock trades OTC with thin liquidity.

## Why the market might be wrong (stable)
The market prices FRMO like a volatile mark-to-market fund, not like a sum of parts. **[Inference]** OTC trading, fair-value earnings swings (Q3 FY2026 diluted EPS $1.89 vs a $0.54 loss a year earlier), and concentration in one line item push generalist investors away. **[Inference]** Private stakes (MIH post-IPO, HKHC, Winland, catalyst names) are likely carried below economic value in GAAP marks. Horizon Kinetics calls this a **dormant asset** case: value sits in subsidiaries and listing events, not in trailing GAAP earnings. There is no clean equity yield curve with one dated payoff; return depends on a catalyst stack over several years.

## Returns (stable, percent per year)
- Base return: 21.9% per year (annualized return)
- Scenarios (percent per year): bear 7.2, base 21.9, bull 30.1

## Key assumptions (stable)
- Price today: **$7.0** (source: Yahoo FRMO close 2026-07-20)
- GAAP book per share: **$8.55** (source: Filing equity ÷ shares)
- Payoff price (Year 5): **$18.0** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **5** (source: Model choice in valuation.json (not company guidance))
- Investment A look-through (82% of equity) uplift: **+$4.5/sh** (source: Bottom-up ~$2.00/sh from weighted holdings (holdco_uplift_explanation.md) + ~$2.50/sh slack until look-through filed. GAAP 309M/44.02M=7.02 inside book.)
- HKHC 4.42% + royalty + subsidiary marks uplift: **+$2.0/sh** (source: Incremental: +2.00/sh (~88M). GAAP 37.4M/44.02M=0.85 inside book. SSI HK gap illustrative; HUMAN REVIEW.)
- MIH/MIAX direct stake uplift: **+$0.5/sh** (source: Incremental +0.50/sh. GAAP 13.9M/44.02M=0.32; ~271k MIAX sh at ~$51; price + fund look-through)
- Winland + CMSG + small options uplift: **+$0.4/sh** (source: Incremental +0.40/sh option value; Winland 5.5M + CMSG 0.7M in/near book)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model stock_specific.
- Confirm live OTC price (Stooq **$6.70**, 2026-05-22) (source: FRMO/research/thesis_card.json)
- Extend sum-of-parts lines (MIH, HKHC, funds) with economic fair values vs GAAP (source: FRMO/research/thesis_card.json)
- Approve **accumulate** at discount to book; size for thin liquidity (source: FRMO/research/thesis_card.json)
- Resolve Nov 2025 late filing notification in INDEX (source: FRMO/research/thesis_card.json)
- {'persona': 'pabrai', 'label': 'Mohnish Pabrai', 'verdict': 'watch', 'return_pct': 7.2, 'key_metric': 'downside_upside_ratio=0.239', 'conviction': 0.39, 'falsifier': 'dhando -> none OR net-debt/EBITDA > 3 OR bear return < -15%'} (source: FRMO/research/valuation.json#lens_consensus)

## Open questions (stable)
- Confirm live OTC price (Stooq **$6.70**, 2026-05-22)
- Extend sum-of-parts lines (MIH, HKHC, funds) with economic fair values vs GAAP
- Approve **accumulate** at discount to book; size for thin liquidity
- Resolve Nov 2025 late filing notification in INDEX

## Canonical pointers (open only when needed)
- valuation: FRMO/research/valuation.json (sha256 sha256:05facd22d1a715b5...)
- thesis_card: FRMO/research/thesis_card.json (sha256 sha256:e04e6d532b455545...)

## Excluded from this pack
- FRMO/research/valuation.json (full; returns block included, open only for assumption audit)
- FRMO/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
