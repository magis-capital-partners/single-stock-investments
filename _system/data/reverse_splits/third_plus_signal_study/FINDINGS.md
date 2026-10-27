# Findings: added signals for third-and-later reverse splits

The completed run contains 472 scenario definitions and 341 distinct portfolio replays. All 27 tests pass. Both earlier full-size baselines reproduce exactly.

No signal or combination passed all historical promotion gates. No live policy was activated.

## Main comparison

The primary reference is $1 million NAV, a $25,000 target reduced by the existing capital and 1% volume constraints, strict restricted/unknown SSR exclusion, a 20-session hold, 1.72% execution sensitivity and 50% annual borrow sensitivity. It is a hypothetical historical account, not the user's actual account.

| Rule | Trades / issuers | Net marked P&L | Maximum drawdown |
|---|---:|---:|---:|
| Third-plus alone | 41 / 33 | -$16,386 | $25,417 |
| Avoid a >=50% daily rise in the prior five sessions | 41 / 33 | +$7,385 | $2,419 |
| Weak split-day close | 10 / 10 | +$1,832 | $2,150 |
| Measured share dilution | 6 / 6 | +$1,319 | $981 |
| Rapid repeat splits | 29 / 22 | -$14,926 | $28,012 |
| Existing 20-session weakness | 34 / 27 | -$21,032 | $25,287 |

The recent-rally veto is the most interesting risk-filter observation in this reference account. Its incremental issuer-bootstrap interval is approximately -$1,184 to +$72,852; the six-month-block interval also includes zero. Removing its five best issuers leaves a small loss. It therefore fails the uncertainty, multiplicity, concentration and unresolved-obligation gates.

Identical trade counts do not imply identical trades: filtering changes portfolio admission and allocation under shared constraints.

The effect does not generalize automatically to full fills. Under strict SSR and hypothetical full $25,000 positions, the twenty-session baseline earns approximately $223,044 versus $181,992 with the rally veto. Allocation and capacity matter as much as the filter's headline result.

## Fundamentals remain data-limited

The source audit examined 149 financing documents, including 89 with completion-language leads. None has the independent source-bound review required to establish a reconciled deal. S2 and its three financing-dependent combinations therefore have no eligible verified selections. Their zero-trade results are missing evidence, not evidence that financing is unhelpful.

Only 13 raw candidate events pass the new pro forma cash-pressure test and 17 pass the comparable share-dilution test before portfolio constraints. These leave only three and six executed research positions respectively. Those cells cannot establish optimal financial rules.

Future work should resolve these source records before comparing cash-plus-financing combinations. The implementation includes review imports, so corrected evidence can produce a new versioned run without inventing historical facts.

## What was completed

- Seven as-of features with explicit pass/fail/unknown states.
- Thirteen core rule arms and feature-covered comparators.
- Capacity, cost, capital, source-clock and repeat-history sensitivities.
- Issuer/calendar uncertainty, multiple-test adjustment and concentration checks.
- Walk-forward selection with matching capital limits and a twenty-session embargo.
- Delayed-confirmation and next-open risk-exit implementations and tests.
- An immutable, manual forward shadow evidence workflow.

No finalist qualified, so the additional timing/exit experiments were not searched on rejected rules. The forward journal remains empty; actual future evidence cannot be manufactured by implementing the software.

## Validation corrections

The first attempt exposed a missing-entry cache-hash serialization error before new comparisons ran. Post-run validation then caught a walk-forward fallback that omitted the reference account's capital limits. Both are corrected and documented with exact before/after code hashes. The original protocol is preserved. Primary signal results were unchanged by the walk-forward fix; the corrected fallback now exactly matches the baseline.

The detailed report includes all primary results, ten-session replication, scenarios, monthly ledgers, unresolved liabilities and reasons each rule failed its gates.
