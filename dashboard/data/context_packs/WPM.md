# Agent context pack: WPM (Wheaton Precious Metals Corp.)

## Identity (stable)
- Ticker: WPM
- Company: Wheaton Precious Metals Corp.
- Book: holdings
- Stance: watch
- Archetype: compounder

## What this business is (stable)
Wheaton Precious Metals is the largest precious-metals streaming company. **[Fact]** It provides upfront capital to miners under precious metal purchase agreements (PMPAs) and receives a long-lived share of gold, silver, and other metal production at low cash costs, without operating mines. **[Fact]** FY2025 revenue was **$2.3 billion**, net earnings **$1.5 billion**, and operating cash flow **$1.9 billion** (`investor-documents/sec-edgar/EX99_1_2025_results_202602.htm`). **[Fact]** Operating cash flow per share (basic) was **$4.197** in 2025 versus **$2.266** in 2024 (same source). **[Fact]** The portfolio spans **23 operating mines** and **25 development and other projects** (EX-99.1). **[Fact]** Wheaton is Canadian-domiciled, listed on NYSE, TSX, and LSE.

## Why the market might be wrong (stable)
The stock may trade as fully priced precious-metals beta after a record 2025, while the contract book is still compounding through Antamina, new mine ramps, and a filed path to **~1.2 million** gold-equivalent ounces (GEOs) by 2030. **[Inference]** Index investors often bucket WPM with spot gold; the economics are closer to a diversified toll on global production with limited operating cost on Wheaton's books. **[Inference]** At roughly **$116** per share, the market may capitalize peak-cycle **$4.20** per share operating cash flow rather than mid-cycle owner cash near **$3.00** per share. **[Inference]** The February 2026 Antamina silver stream adds volume but also **$4.3 billion** upfront capital and term-loan leverage that screens may underweight.

## Returns (stable, percent per year)
- Base return: -1.03% per year (7yr IRR (total synthesis))
- Scenarios (percent per year): bear -7.6, base -1.6, bull 2.5

## Key assumptions (stable)
- Price today: **$115.74** (source: Yahoo WPM close 2026-06-08)
- Starting free cash flow per share: **$3.0** (source: Mid-cycle owner cash: between FY2024 ops CF/sh $2.266 and FY2025 $4.197 (EX-99.1); haircut from peak gold/silver prices; 2026 GEO guidance 860 to 940K supports volume ramp but not in starting cash flow)
- Growth in years 1 through 5: **6.0%** per year (source: 2026 GEO guidance 860–940K (EX-99.1); Antamina +70K GEOs from Apr 2026; mid-cycle metal prices)
- Growth in years 6 through 7: **4.0%** per year (source: Scenario base)
- Selling multiple in year 10: **18 times cash flow** (source: Scenario base)
- Time horizon: **7 years** (source: 7-year owner-cash model)

## Core compounder research monitoring
- Diagnostic 7-year cash-flow IRR: -1.5894030532549015% per year; status diagnostic. Research only.
- Buy bands: withheld; model evidence_blocked.
- Confirm normalized owner cash (**$3.00** vs filing **$4.197**) given 2026 GEO guidance and Antamina ramp. (source: WPM/research/thesis_card.json)
- Antamina **$4.3 billion** deal: approve accretion and leverage assumptions; confirm April 2026 close and deliveries. (source: WPM/research/thesis_card.json)
- CEO transition (Hodaly effective March 31, 2026): capital allocation track record. (source: WPM/research/thesis_card.json)
- Add full FY2025 Annual Report / AIF PDF to `investor-documents/`. (source: WPM/research/thesis_card.json)
- No approved third-party sources in base IRR. (source: WPM/research/thesis_card.json)

## Open questions (stable)
- Confirm normalized owner cash (**$3.00** vs filing **$4.197**) given 2026 GEO guidance and Antamina ramp.
- Antamina **$4.3 billion** deal: approve accretion and leverage assumptions; confirm April 2026 close and deliveries.
- CEO transition (Hodaly effective March 31, 2026): capital allocation track record.
- Add full FY2025 Annual Report / AIF PDF to `investor-documents/`.
- No approved third-party sources in base IRR.

## Canonical pointers (open only when needed)
- valuation: WPM/research/valuation.json (sha256 sha256:63b237f3e20d844a...)
- thesis_card: WPM/research/thesis_card.json (sha256 sha256:8485cde06f377470...)

## Excluded from this pack
- WPM/research/valuation.json (full; returns block included, open only for assumption audit)
- WPM/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
