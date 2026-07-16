# Citi valuation evidence reconciliation — 2026-07-15

## Scope and source

This reconciliation tests Citi's normalized returns, distributable capital and stress claims against Citigroup's [2025 Annual Report and Form 10-K](https://www.citigroup.com/rcs/citigpa/storage/public/Annual_Report/2025/citi-2025-annual-report.pdf).

## Facts reconciled

- Tangible common equity was $169.618 billion at December 31, 2025, equal to $97.06 per share on 1.7475 billion common shares. This directly supports the model's $97 base tangible-book component.
- Reported 2025 RoTCE was 7.7%; excluding two notable items it was 8.8%. Revenue was $85.2 billion and Citi returned $17.6 billion to common shareholders. Transformation expense was approximately $3.3 billion, up 14% year over year.
- The standardized CET1 ratio was 13.2% versus an 11.6% required ratio, while the advanced-approaches ratio was 11.9% versus 10.5% required. Citi was above regulatory requirements and classified as well capitalized, but the roughly 1.4–1.6 percentage-point spread is not equivalent to freely distributable capital.
- Total allowance for credit losses was $21.373 billion at year-end, including $16.194 billion of consumer loan allowance. The reported allowance is a fact; its adequacy in a severe consumer, corporate, market, operational and legal stress remains a judgment.
- Citi's five operating businesses reported record revenue, but the filing does not provide a complete allocation of tangible common equity by segment. All Other contains corporate treasury, transformation, legacy and divestiture effects. Therefore segment RoTCE cannot be independently rebuilt from public segment tables without capital-allocation assumptions.

## Acceptance-test results

### `segment_rotce_normalization` — open, materially narrowed

Firmwide TCE, reported/adjusted RoTCE and transformation expense are reconciled. The acceptance test is not met because segment tangible capital and through-cycle credit costs are not fully disclosed, preventing an independently reproducible segment excess-return bridge for the model's -$10/$15/$45 franchise component. Required next evidence is a consistent segment tangible-capital allocation and normalized credit/expense schedule across at least one full cycle. Falsifier: firmwide RoTCE remains below the cost of tangible equity after transformation spending normalizes.

### `distributable_capital` — open, materially narrowed

Actual CET1 capital buffers and share count are reconciled, but the transformation-and-excess-capital component's $0/$10/$25 range is not reproducible from the headline ratio alone. Stress capital requirements, management buffers, RWA migration, final regulatory rules and execution costs can consume the apparent spread. Required next evidence is a quarterly CET1 walk from regulatory minimum through management buffer, planned RWA, stress losses and approved capital distributions. Falsifier: CET1 headroom fails to expand as transformation costs decline or capital return requires operation near the regulatory floor.

### `stress_claims` — open

Reported allowances and regulatory ratios provide starting facts, not an independently reviewed stress bridge. The acceptance test is not met for the model's -$30/-$15/-$5 reserve because correlated consumer credit, corporate credit, funding, market, legal and operational losses have not been rebuilt under a common severe scenario. Required next evidence is a portfolio-level stress tied to balances, loss rates, funding spread, expenses and post-stress CET1. Falsifier: modeled post-stress CET1 falls below the binding requirement or loss absorption exceeds the low-case reserve.

## Valuation consequence

Every material component is valued, but no unresolved estimate is promoted to fact. Adjusted tangible book remains the primary anchor; normalized franchise value, capital release and the stress reserve remain explicit, non-overlapping adjustments. The security remains evidence-blocked pending the three reproducible bridges above.
