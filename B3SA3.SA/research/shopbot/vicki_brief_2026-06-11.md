# Vicki brief — B3SA3.SA IR harvest

**Date:** 2026-06-11  
**Ticker:** B3SA3.SA  
**IR root:** https://www.b3.com.br/en_us/about-b3/investor-relations/

## Task

Harvest quarterly earnings releases, material facts, and presentation PDFs from B3 investor relations. Onboard download was skipped; Marvin used FY2024 annual PDF only.

## Priority documents

1. Latest quarterly results (2025 quarters if available)
2. Earnings presentation decks
3. Governance / proxy materials
4. Historical annual reports (2022–2023) for trend

## Output

Place PDFs under `B3SA3.SA/official-reports/` and update `document-index.csv` + `INDEX.csv`.

## Blockers

B3 IR site may use dynamic JavaScript; use browser agent if static scrape returns zero PDFs.
