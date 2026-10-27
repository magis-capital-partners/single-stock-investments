# Agent context pack: DRR.AX (Deterra Royalties Limited)

## Identity (stable)
- Ticker: DRR.AX
- Company: Deterra Royalties Limited
- Book: holdings
- Stance: watch
- Archetype: optionality

## What this business is (stable)
Deterra Royalties is an ASX-listed passive royalty company that receives cash from mining operators without operating mines or bearing production capital spending. **[Fact]** The cornerstone asset is a **1.232%** gross revenue royalty over BHP's Mining Area C (MAC) iron ore hub in Western Australia, plus **A$1 million** capacity payments per million dry metric tonnes of annual production increase (`DRR.AX/investor-documents/official-reports/250325-1HY25-Deterra-Royalties-Financial-Results-Declaration.pdf`). **[Fact]** FY2025 revenue was **A$263.4 million** (+10%); underlying EBITDA **A$250 million** (+10%); net profit after tax **A$155.7 million**; total dividends **22 cents** per share fully franked (`DRR.AX/investor-documents/asx-announcements/2931000.pdf`). **[Fact]** At 31 December 2024, net assets were **19.1 cents** per share while net tangible assets were **(42.1) cents** per share because royalty intangibles are excluded from NTA (same half-year report). **[Fact]** Net debt at 30 June 2025 was **A$271 million** with **A$205 million** undrawn on **A$500 million** credit facilities (FY25 results presentation).

## Why the market might be wrong (stable)
The market may treat Deterra as a single-commodity iron ore yield stock and miss the option stack in Thacker Pass lithium (first production late 2027) and the gold offtake book acquired via Trident. **[Inference]** FY2025 gold offtake net revenue margin was **A$21.5 million** on record gold prices, diversifying cash away from MAC iron ore alone. **[Inference]** The 1H25 interim dividend cut to **9 cents** (from **14.89 cents** in 1H24) may anchor yield screens on a trough payout rather than the **75% of NPAT** policy confirmed at FY25. Index and domestic yield buyers may underweight ASX royalty structures relative to US trust equivalents (MSB, SJT).

## Returns (stable, percent per year)
- Base return: 8.0% per year (annualized return)
- Scenarios (percent per year): bear 3.3, base 8.0, bull 13.9

## Key assumptions (stable)
- Price today: **$4.43** (source: Yahoo Finance DRR.AX close 2026-06-02 (AUD))
- Payoff price (Year 5): **$6.5** (source: Sum of parts / catalyst path in IRR steps)
- Horizon (years): **5** (source: Model choice in valuation.json (not company guidance))
- Cumulative dividends years 1-5 (~24c/yr) uplift: **+$1.2/sh** (source: 5 x AUD 0.24 from FY25 75% payout policy)
- Thacker Pass buyback milestone (probability-weighted) uplift: **+$0.35/sh** (source: US$13.2m buyback entitlement; first production late 2027 [Assumption])
- Terminal re-rate on normalized royalty yield uplift: **+$0.52/sh** (source: MAC hub ramp + gold offtake margin persistence [Assumption])

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: None% per year; status gap. Research only.
- Buy bands: withheld; model evidence_blocked.
- Confirm ASX market classification in `_system/portfolio/registry.json` (currently tagged US). (source: DRR.AX/research/thesis_card.json)
- Build dedicated ASX announcement download script or Vicki harvest for ongoing refreshes. (source: DRR.AX/research/thesis_card.json)
- Harvest March 2026 quarter portfolio update PDF. (source: DRR.AX/research/thesis_card.json)
- No third-party sources indexed; re-scan when Substacks or fund letters added. (source: DRR.AX/research/thesis_card.json)
- PDF extracts are scan-tier only; promote to full-tier when annual report PDF indexed. (source: DRR.AX/research/thesis_card.json)

## Open questions (stable)
- Confirm ASX market classification in `_system/portfolio/registry.json` (currently tagged US).
- Build dedicated ASX announcement download script or Vicki harvest for ongoing refreshes.
- Harvest March 2026 quarter portfolio update PDF.
- No third-party sources indexed; re-scan when Substacks or fund letters added.
- PDF extracts are scan-tier only; promote to full-tier when annual report PDF indexed.

## Canonical pointers (open only when needed)
- valuation: DRR.AX/research/valuation.json (sha256 sha256:70607771cf70bb04...)
- thesis_card: DRR.AX/research/thesis_card.json (sha256 sha256:ab73312c6a9159f7...)

## Excluded from this pack
- DRR.AX/research/valuation.json (full; returns block included, open only for assumption audit)
- DRR.AX/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
