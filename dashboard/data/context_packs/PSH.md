# Agent context pack: PSH (Pershing Square Holdings, Ltd.)

## Identity (stable)
- Ticker: PSH
- Company: Pershing Square Holdings, Ltd.
- Book: holdings
- Stance: watch
- Archetype: holding_co

## What this business is (stable)
PSH is Ackman's LSE-listed closed-ended vehicle: concentrated large-cap longs, weekly NAV, persistent double-digit discount, active share repurchases. It is tagged as a fund NAV-discount idea, not an operating compounder.

## Why the market might be wrong (stable)
The shares trade at -34.5% vs reported NAV. The inefficiency is market-structure and/or accounting marks, not a hidden factory.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: USD 50.5 (source: Yahoo PSHD.L (USD line) ~$50.50 (2026-07-20); GBP line PSH.L ~3768p.)
- Reported NAV: USD 77.06 (source: Company weekly NAV $77.06 per share as of 2026-07-14 (PSH site).)
- Discount to reported NAV: -34.5% vs reported NAV (source: price / NAV - 1)
- Fund edge tag: classic (source: sleeve taxonomy)
- Horizon: 5 years (source: [Assumption])
- Base payoff: ~90% of liquid/reported NAV (source: [Assumption])

## Open questions (stable)
- Approve live NAV/price marks and any non-zero recovery probability.
- Confirm mandate fit (liquidity, fees, currency).

## Verified claims (stable, cited)
- [assumption] Base payoff: ~90% of liquid/reported NAV (source: PSH/research/thesis_card.json)
- [assumption] Discount to reported NAV: -34.5% vs reported NAV (source: PSH/research/thesis_card.json)
- [assumption] Fund edge tag: classic (source: PSH/research/thesis_card.json)
- [assumption] Horizon: 5 years (source: PSH/research/thesis_card.json)
- [pending] PSH is Ackman's LSE-listed closed-ended vehicle: concentrated large-cap longs, weekly NAV, persistent double-digit discount, active share repurchases. It is tagged as a fund NAV-discount idea, not an operating compounder. (source: PSH/research/thesis_card.json)
- [assumption] Price today: USD 50.5 (source: PSH/research/thesis_card.json)
- [assumption] Reported NAV: USD 77.06 (source: PSH/research/thesis_card.json)
- [pending] The shares trade at -34.5% vs reported NAV. The inefficiency is market-structure and/or accounting marks, not a hidden factory. (source: PSH/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — PSH

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `PSH/research/evidence/document_inventory.json`  

Documents in folder: **1** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| inventory | other | — | `investor-documents/PSH-Fact-Sheet-March-2026.pdf` | 0 |

## Canonical pointers (open only when needed)
- deep_dive: PSH/research/deep_dive_2026-07-20.md (sha256 sha256:8cbef50daaedf40e...)
- filing_digest: PSH/research/evidence/filing_digest.md (sha256 sha256:2939ff8c90a619ec...)
- adversarial: PSH/research/adversarial_2026-07-20.md (sha256 sha256:d30f5e7569ce18dc...)
- valuation: PSH/research/valuation.json (sha256 sha256:833be5b1b6b2ea50...)
- thesis_card: PSH/research/thesis_card.json (sha256 sha256:d6fee5a84864fe64...)

## Excluded from this pack
- PSH/research/valuation.json (full; returns block included, open only for assumption audit)
- PSH/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
