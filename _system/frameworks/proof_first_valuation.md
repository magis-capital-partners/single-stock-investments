# Proof-first valuation operating model

## Authority

The universal valuation contract is the only source of decision-grade security value. Marvin may collect evidence and write narrative research, but neither Marvin nor an Investment Committee persona may enter an unsupported component value.

The production chain is:

1. The research library supplies reusable valuation logic and failure modes.
2. The Power Zone router selects one approved primary method and at most two corroborating methods.
3. Issuer filings and contracts supply source-locked facts.
4. A deterministic calculation graph produces low/base/high component outputs.
5. The universal contract checks completeness, arithmetic, scenario order, overlap and evidence lineage.
6. Independent committee reviewers challenge method fit, facts, assumptions, falsifiers and omissions.
7. The dashboard displays the complete calculation trace and model hash.
8. Measured outcomes inform later calibration; they never rewrite formulas automatically.

## Value statuses

| Status | Meaning | Included in security value |
|---|---|---:|
| `calculated` | Locked facts and deterministic arithmetic fully reproduce the output. | Yes |
| `bounded_estimate` | The output is reproducible and every judgment is justified and inside an approved range. | Yes |
| `unpriced` | A material fact or defensible bound is unavailable. | No |
| `legacy_sensitivity` | A deprecated unsupported range is retained for change attribution. | No |

If any material additive component is unpriced, the complete low/base/high security value is withheld. `priced_components_per_share` may still be shown, with an explicit warning that it is not a security valuation.

## Calculation-proof format

Every fact includes a source reference, exact locator, as-of date, unit and `locked: true`. Every judgment includes a rationale and allowed minimum/maximum. Calculation nodes use only the allow-listed arithmetic operations in `calculation_proof.py`; arbitrary expressions and executable code are prohibited.

The graph records:

- every input and its fact/estimate/judgment classification;
- every dependency and intermediate value;
- symbolic and substituted arithmetic;
- low/base/high output nodes;
- source lineage and proof hash;
- validation errors and component status.

The same inputs and method version must reproduce the same output and hash.

## Method-card governance

The approved registry is `_system/reference/valuation_method_registry.json`. A card is eligible for production only when it defines:

- method ID, version, status and Power Zones;
- the exact economic claim;
- required inputs and equations;
- permitted judgments;
- causal scenario rules;
- double-counting exclusions;
- known failure modes;
- corroborating methods;
- library sources with stable locators.

Library material provides method provenance and base-rate candidates. Issuer facts must still come from primary company evidence. LLMs can find passages, propose mappings and explain calculations, but deterministic code performs the arithmetic.

## Committee responsibilities

- **Proposer:** submits a complete calculation proof.
- **Evidence tribunal:** verifies source lineage and locks facts.
- **Power Zone specialist:** tests method applicability.
- **Adversarial reviewer:** challenges judgments, overlap, scenario causality and hidden claims.
- **Calibration reviewer:** compares assumptions with measured historical outcomes.
- **Chair:** selects a defensible assumption set and preserves dissent.

The chair cannot waive a failed proof check. Disagreement must appear as different bounded assumptions or event cases, not an averaged price target.

## Migration and retirement

`run_security_decision_pipeline.py --scope all` is the canonical migration. For each security it:

1. refreshes its Power Zone route;
2. converts raw unsupported ranges to excluded legacy sensitivities;
3. evaluates calculation proofs;
4. withholds incomplete security values;
5. rebuilds workbenches and proof-completeness measures;
6. prices and opens committee work only for decision-grade contracts;
7. publishes the resulting state to the dashboard.

The legacy Marvin/Lawrence fields may remain temporarily for historical comparison. They are never read as production value by Contract v2 and can be deleted after every active security has a proof-complete baseline and its change history has been retained.

## MSB pilot

- The latest disclosed trust reserve is calculated as `$18.342m / 13.12001m units = $1.3980 per unit`.
- The producing royalty stream remains unpriced until contractual tiers, production cadence and finite reserves support a period-by-period distribution curve.
- Depletion and counterparty concentration are embedded in the producing-stream scenarios, not deducted through an arbitrary standalone reserve.
- The current arbitration remains unpriced until the claim, remedy, timing and collectibility are supported. The prior award is context, not a current comparable payoff.
- Former ranges remain visible only as excluded legacy sensitivities.

## Release gates

A decision-grade contract requires all of the following:

- every material economic claim is identified and priced exactly once;
- all component proofs are valid;
- low ≤ base ≤ high;
- event probabilities sum to one where applicable;
- component and enterprise-to-equity sums reconcile;
- no overlap key is duplicated among additive components;
- source facts are locked and traceable;
- judgments are bounded, justified and sensitivity-tested;
- stale material facts are refreshed;
- every change has a reason and before/after record;
- open primary-evidence blockers equal zero.
