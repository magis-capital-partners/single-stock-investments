# Valuation evidence rollout queue

As-of: 2026-07-15  
Queue of record: [`valuation_followups.json`](valuation_followups.json)  
Worker prompt: [`../prompts/cursor_valuation_evidence_worker.md`](../prompts/cursor_valuation_evidence_worker.md)

## Cadence

One Cursor task = one ticker + one evidence gap. Merge to `main` only after validators pass.

## Phase 0 â€” infrastructure

- [x] Land generalized valuation stack on `main`
- [x] Encode worker prompt + Cursor rule
- [x] Smoke unit tests + MSB workbench rebuild

## Phase 1 â€” validation cohort (9 tickers)

| Order | Ticker | Gap | Priority | Status |
|------:|--------|-----|----------|--------|
| 1 | MSB | royalty_reserve_reconciliation | critical | open / partially_met |
| 2 | MSB | legal_option_record | critical | open / not_met |
| 3 | MSB | trust_net_assets | critical | accepted 2026-07-15 |
| 4 | TPL | tract_level_royalty_inventory | critical | open / not_met |
| 5 | TPL | water_economic_separation | high | open / partially_met |
| 6 | TPL | option_milestones_and_capital | high | open / partially_met |
| 7 | WBI | project_cohort_roic | critical | open / not_met |
| 8 | WBI | contract_quality | high | open / partially_met |
| 9 | WBI | refinancing_and_funding | high | open / partially_met |
| 10 | C | segment_rotce_normalization | critical | open / partially_met |
| 11 | C | distributable_capital | critical | open / partially_met |
| 12 | C | stress_claims | critical | open / partially_met |
| 13 | NUE | industry_capacity_map | critical | open / not_met |
| 14 | NUE | project_roic | critical | open / partially_met |
| 15 | NUE | through_cycle_segments | critical | open / partially_met |
| 16 | NVR | owner_earnings_cycle | critical | open / partially_met |
| 17 | NVR | controlled_lot_inventory | critical | open / partially_met |
| 18 | NVR | surplus_cash | critical | open / partially_met |
| 19 | BIIB | product_cash_flows | critical | open / partially_met |
| 20 | BIIB | pipeline_event_trees | critical | open / partially_met |
| 21 | BIIB | closing_claims | critical | open / partially_met |
| 22 | LB | alpha_digital_lease_economics | critical | open / not_met |
| 23 | LB | fee_engine_unit_economics | high | open / partially_met |
| 24 | AZLCZ | contract_and_ownership_waterfalls | critical | open / partially_met |
| 25 | AZLCZ | residual_acreage_overlap | high | open / partially_met |
| 26 | AZLCZ | water_right_realization | high | open / partially_met |

## Phase 2 â€” expansion waves

1. Registry core/hold: CPRT, CSU, 8697.T, AMZN, BN, DHR, FRMO, GOOGL, ICE, QDEL, SPGI, TEQ.ST
2. Thematic / sleeve adjacency (`ai_power_land`, royalty/land)
3. Existing `valuation.json` backfill
4. Remainder of registry (opportunistic)

## Rules

- Never weaken an acceptance test to close a gap.
- IC freeze only after material evidence change and critical gaps met or explicitly unavailable.
- Persona reviews stay in isolated tasks.

## Phase 2 status

- Core/hold (12): first-pass inventories written; all evidence-blocked.
- Thematic sleeves with valuation.json: first-pass inventories written; all evidence-blocked.
- valuation.json backfill and remainder of registry: still queued / opportunistic.
- No IC packet re-freeze: no critical acceptance test newly marked accepted this session.
