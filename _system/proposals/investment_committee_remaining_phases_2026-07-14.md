# Investment Committee: remaining phases

## Outcome

Move the Phase 0/1 manual pilot into a repeatable process without turning the committee into a vote-counting machine. The system should improve explanations, expose disagreement, and leave the actual capital decision with one named owner.

## Requirements retained — and why

- **Frozen evidence packet:** necessary to prevent different agents from silently answering different questions.
- **Three isolated raters:** sufficient by default. Three distinct error profiles provide diversity; five agents add cost and correlated prose unless a specific coverage gap justifies a fourth review outside the formal vote.
- **Outside pre-mortem:** necessary because it attacks the shared premise rather than merely adjusting a score.
- **Dissent-first synthesis:** necessary because an average can conceal a decision-critical objection.
- **One research loop maximum:** enough to resolve the most important missing facts without letting the process rationalize indefinitely.
- **One human owner:** necessary for accountability. Agents must not decide position size.
- **Hard-to-vary explanation contracts:** every material claim must state mechanism, evidence, distinguishing test, competing explanation, falsifier, and valuation link.

Not retained: automatic consensus weighting, automatic sizing, a fixed five-rater panel, repeated research loops, and a requirement that every specialist opine on every stock.

## Phase status

### Phase 0 — protocol and schema: complete

The record defines frozen evidence, calibrated scores, abstention, pre-mortem, blind rounds, dissent, gates, and owner-controlled final state.

### Phase 1 — manual pilot: complete

The six-name pilot established that isolation and evidence abstention are feasible. It remains a test fixture, not the production runner.

### Phase 2 — repeatable orchestration: implemented

`investment_committee_pipeline.py` now:

1. discovers and hashes the evidence packet;
2. selects three method-diverse raters from component needs and default error profiles;
3. creates isolated first- and second-round work packets plus a separate pre-mortem;
4. validates completeness, score anchors, identities, independence groups, and evidence immutability;
5. assembles only complete work into a dissent-first committee record.

`evidence_blocked` means a decision-critical fact is unavailable or unreconciled. It is a valid analytical result, not a negative investment vote.

### Phase 3 — stock dashboard: implemented

Each stock view should lead with committee state, second-round vote split, score medians, strongest dissent, unresolved facts, and owner decision. Component valuation remains directly below it so objections can be traced to the affected value driver.

### Phase 4 — calibration: implemented conservatively

`committee_calibration.py` consumes an explicit outcome ledger conforming to `_system/templates/committee_outcome_schema.json` and reports method-level coverage and directional accuracy. Incomplete or price-only outcomes are excluded. Results remain descriptive until a method has at least 20 completed observations.

### Phase 5 — rollout: operational next step

Run the production workflow first on TPL and two contrasting names. Review whether each rater contributed a distinct error model. Then roll out only when a full-committee trigger exists: new position, material thesis change, decision-critical evidence conflict, or valuation crossing the portfolio hurdle. Routine refreshes stay lightweight.

## Investment Committee flow

`proposer -> frozen packet -> 3 blind raters + outside pre-mortem -> one targeted research loop -> blind re-score -> dissent-first synthesis -> accountable owner`

The synthesis reports consensus, but does not erase minority reasoning or blend incompatible valuation methods into a false precision number.
