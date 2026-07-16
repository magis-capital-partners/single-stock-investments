# Valuation evidence rollout queue

As-of: 2026-07-15  
Queue of record: [`valuation_followups.json`](valuation_followups.json)  
Worker prompt: [`../prompts/cursor_valuation_evidence_worker.md`](../prompts/cursor_valuation_evidence_worker.md)

## Cadence

One Cursor task = one ticker + one evidence gap. Merge to `main` only after validators pass.

## Phase 0 — infrastructure

- [x] Land generalized valuation stack on `main`
- [x] Encode worker prompt + Cursor rule
- [ ] Smoke unit tests + MSB workbench rebuild (this session)

## Phase 1 — validation cohort (9 tickers)

| Order | Ticker | Gap | Priority | Status |
|------:|--------|-----|----------|--------|
| 1 | MSB | royalty_reserve_reconciliation | critical | open → document this session |
| 2 | MSB | legal_option_record | critical | open → document this session |
| 3 | MSB | trust_net_assets | critical | accepted 2026-07-15 |
| 4 | TPL | tract_level_royalty_inventory | critical | open |
| 5 | TPL | water_economic_separation | high | open |
| 6 | TPL | option_milestones_and_capital | high | open |
| 7 | WBI | project_cohort_roic | critical | open |
| 8 | WBI | contract_quality | high | open |
| 9 | WBI | refinancing_and_funding | high | open |
| 10 | C | segment_rotce_normalization | critical | open |
| 11 | C | distributable_capital | critical | open |
| 12 | C | stress_claims | critical | open |
| 13 | NUE | industry_capacity_map | critical | open |
| 14 | NUE | project_roic | critical | open |
| 15 | NUE | through_cycle_segments | critical | open |
| 16 | NVR | owner_earnings_cycle | critical | open |
| 17 | NVR | controlled_lot_inventory | critical | open |
| 18 | NVR | surplus_cash | critical | open |
| 19 | BIIB | product_cash_flows | critical | open |
| 20 | BIIB | pipeline_event_trees | critical | open |
| 21 | BIIB | closing_claims | critical | open |
| 22 | LB | alpha_digital_lease_economics | critical | open |
| 23 | LB | fee_engine_unit_economics | high | open |
| 24 | AZLCZ | contract_and_ownership_waterfalls | critical | open |
| 25 | AZLCZ | residual_acreage_overlap | high | open |
| 26 | AZLCZ | water_right_realization | high | open |

## Phase 2 — expansion waves

1. Registry core/hold: CPRT, CSU, 8697.T, AMZN, BN, DHR, FRMO, GOOGL, ICE, QDEL, SPGI, TEQ.ST
2. Thematic / sleeve adjacency (`ai_power_land`, royalty/land)
3. Existing `valuation.json` backfill
4. Remainder of registry (opportunistic)

## Rules

- Never weaken an acceptance test to close a gap.
- IC freeze only after material evidence change and critical gaps met or explicitly unavailable.
- Persona reviews stay in isolated tasks.
