# AI — Evidence reconciliation

**Date:** 2026-10-15  
**Ticker:** AI  
**Contract status:** evidence_blocked  
**Authorized evidence:** injected agent manifest listing `authorized_evidence.json` and `DOWNLOAD_MANIFEST.json`

## Status

Contract backfill run (injected manifest). All four additive components carry **valid** `calculation_proof` graphs with approved method identifiers. **Decision grade** remains blocked by the prospective falsifier gate on every component introduced after cutover:

> `core_engine`, `reinvestment_runway`, `net_financial_claims`, `cycle_reserve`

No `epistemic_work_item` was injected in `research_agent_manifest.json`; v3 forecast authoring and independent review were out of scope for this packet.

## Component reconciliation

| Component | Method | Proof | Filing anchor | Falsifier gate |
|-----------|--------|-------|---------------|----------------|
| `core_engine` | `owner_cash_or_dividend_discount@1.0` | valid | FY2026 10-K owner-cash bridge | missing v3 spec |
| `reinvestment_runway` | `owner_earnings_reinvestment_dcf@1.0` | valid | FY2026 10-K pipeline context | missing v3 spec |
| `net_financial_claims` | `net_asset_value@1.0` | valid | Cash **$66.2M**; LTD **$0** Apr-30-2026 | missing v3 spec |
| `cycle_reserve` | `midcycle_capacity_value@1.0` | valid | Judgment reserve; price input synced to **$11.34** (2026-10-08) | missing v3 spec |

**Remaining uncertainty:** `cycle_reserve` and `reinvestment_runway` rows are judgment-heavy (SBC dilution, hyperscaler competition, Federal pipeline conversion). Resolvable v3 forecasts need pre-registered metrics with historical replay (for example TTM SBC per share, diluted share count growth, or Federal revenue share). Alternatively, typed **untestable** dispositions require human-approved epistemic review before promoter append to `falsifier_specs.json`.

**Valuation consequence:** Universal contract stays **evidence_blocked**; committee and capital action disabled per `valuation_contract.json` `decision_eligibility`.

## Acceptance test (contract backfill)

| Field | Result |
|-------|--------|
| Additive components identified | pass (4/4) |
| Overlap keys non-overlapping | pass |
| Calculation proofs attached | pass |
| Owner-cash vs GAAP | Normalized **$0.80/sh** **[Assumption]**; not GAAP net income |
| Prospective falsifier coverage | **open** — queue `author_forecast` per component |

## Next steps (human / epistemic queue)

1. Dispatch `author_forecast` work items for missing components when cohort allows.
2. Independent `review_forecast` before promoter appends to `AI/research/falsifier_specs.json`.
3. Re-run `python _system/scripts/marvin_cloud_refresh.py AI --date YYYY-MM-DD` after approved specs land.

## Epistemic loop (read-only)

**Health:** `COLLECTING` (`_system/research/epistemic_loop_status.json`, as_of 2026-10-14). Calibration **global_status:** `insufficient_outcomes`; **release_hash:** null. Calibration did not change weights, stance, or sizing this run.
