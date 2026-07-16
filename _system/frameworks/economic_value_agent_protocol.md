# Economic-value agent protocol

This protocol applies to every new or materially refreshed security analysis. It standardizes the questions and evidence gates, not the answer or valuation method.

## Required sequence

1. Define the exact economic claim represented by one security and reconcile enterprise value to the common owner's units.
2. Inventory every material operating asset, financial asset, option, liability, and reserve. Weak evidence widens the range; it never creates an implicit zero.
3. State whether GAAP is primary evidence, a cross-check, reference only, or misleading historical cost.
4. Select a component method by economic mechanism: owner cash, reinvestment return, unit NAV, excess return, dated payoff, liquidation, or milestone option.
5. Apply the comparable hierarchy in order: issuer transaction, same-asset transaction, public peer, replacement cost, approved external analysis.
6. Reconcile gross comparable value to risked present value through timing, capital, probability, ownership, leverage, tax, control, liquidity, and realization adjustments.
7. Produce the deterministic valuation-proof table and reverse expectations. Do not average them.
8. Route the complete packet to three independent committee methods. Power zones choose reviewers; they do not choose the valuation answer.
9. Record the later dividend-aware outcome and calibrate only after sufficient observations.

Record a matured decision with:

```text
python _system/scripts/record_committee_outcome.py TICKER --committee-date YYYY-MM-DD --measurement-date YYYY-MM-DD --write
```

The recorder uses the same split, regular-dividend, and special-dividend ledger as the dashboard and refreshes method-level range and directional calibration.

## Publication gates

An analysis is `evidence_blocked` when the economic claim is missing, material components are incomplete, additive components overlap, asset comparables lack like-for-like adjustments, options lack risk/timing treatment, or enterprise value is not reconciled to the security's economic units.

Legacy operating-only estimates may remain visible as `inferred_minimal`, but they are not complete economic valuations.

## Simplicity rule

Do not create a universal mega-model. A security may combine small valuation modules, but every module must emit the same low/base/high, evidence, overlap, adjustment, and falsifier contract.
