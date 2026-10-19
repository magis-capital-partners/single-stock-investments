# Short execution-cost audit — 2026-10-19

Research estimates from historical displayed quotes and books; no broker fills. Borrow and financing are excluded.

## Matched quote comparison

| Cohort | Entry delay | Matched events | Listing median | Multi-venue median | Multi-venue mean |
|---|---:|---:|---:|---:|---:|
| primary | 1s | 533 | 2.41% | 1.72% | 2.28% |
| primary | 30s | 622 | 2.23% | 1.54% | 1.96% |
| eligible | 1s | 220 | 2.55% | 1.97% | 2.47% |
| eligible | 30s | 261 | 2.34% | 1.63% | 2.01% |

## Displayed-book size test: primary, entry +1s

| Ticket | Full pairs / target events | Spread + depth median | Mean | P90 | Mean incl. commissions | Both legs within 1% of best quote |
|---:|---:|---:|---:|---:|---:|---:|
| $500 | 671 / 671 | 2.16% | 2.87% | 6.05% | 3.33% | 476 |
| $25,000 | 276 / 671 | 5.95% | 8.29% | 17.33% | 8.52% | 36 |
| $50,000 | 107 / 671 | 3.53% | 5.83% | 14.42% | 6.00% | 19 |
| $100,000 | 32 / 671 | 2.21% | 4.52% | 10.13% | 4.59% | 9 |

Same events supported at every size (selected with hindsight):

| Ticket | Common events | Median spread + depth | Mean |
|---:|---:|---:|---:|
| $500 | 32 | 0.55% | 1.10% |
| $25,000 | 32 | 1.02% | 1.90% |
| $50,000 | 32 | 1.29% | 2.61% |
| $100,000 | 32 | 2.21% | 4.52% |

## Displayed-book size test: primary, entry +30s

| Ticket | Full pairs / target events | Spread + depth median | Mean | P90 | Mean incl. commissions | Both legs within 1% of best quote |
|---:|---:|---:|---:|---:|---:|---:|
| $500 | 671 / 671 | 2.00% | 2.65% | 5.23% | 3.10% | 488 |
| $25,000 | 318 / 671 | 5.55% | 8.90% | 18.44% | 9.13% | 43 |
| $50,000 | 124 / 671 | 3.22% | 5.47% | 12.40% | 5.65% | 23 |
| $100,000 | 43 / 671 | 2.06% | 3.88% | 10.64% | 3.98% | 17 |

Same events supported at every size (selected with hindsight):

| Ticket | Common events | Median spread + depth | Mean |
|---:|---:|---:|---:|
| $500 | 43 | 0.55% | 0.79% |
| $25,000 | 43 | 0.85% | 1.51% |
| $50,000 | 43 | 1.42% | 2.07% |
| $100,000 | 43 | 2.06% | 3.88% |

## Displayed-book size test: eligible, entry +1s

| Ticket | Full pairs / target events | Spread + depth median | Mean | P90 | Mean incl. commissions | Both legs within 1% of best quote |
|---:|---:|---:|---:|---:|---:|---:|
| $500 | 282 / 282 | 2.42% | 3.03% | 6.15% | 3.46% | 194 |
| $25,000 | 126 / 282 | 5.80% | 7.40% | 15.97% | 7.56% | 29 |
| $50,000 | 59 / 282 | 2.74% | 5.33% | 13.98% | 5.44% | 15 |
| $100,000 | 24 / 282 | 2.06% | 4.67% | 9.71% | 4.73% | 8 |

Same events supported at every size (selected with hindsight):

| Ticket | Common events | Median spread + depth | Mean |
|---:|---:|---:|---:|
| $500 | 24 | 0.60% | 1.21% |
| $25,000 | 24 | 0.86% | 2.04% |
| $50,000 | 24 | 1.25% | 2.67% |
| $100,000 | 24 | 2.06% | 4.67% |

## Displayed-book size test: eligible, entry +30s

| Ticket | Full pairs / target events | Spread + depth median | Mean | P90 | Mean incl. commissions | Both legs within 1% of best quote |
|---:|---:|---:|---:|---:|---:|---:|
| $500 | 282 / 282 | 2.12% | 2.72% | 5.22% | 3.16% | 195 |
| $25,000 | 141 / 282 | 4.36% | 7.26% | 16.14% | 7.42% | 30 |
| $50,000 | 65 / 282 | 2.91% | 4.31% | 12.05% | 4.42% | 19 |
| $100,000 | 28 / 282 | 1.20% | 3.80% | 8.37% | 3.86% | 14 |

Same events supported at every size (selected with hindsight):

| Ticket | Common events | Median spread + depth | Mean |
|---:|---:|---:|---:|
| $500 | 28 | 0.62% | 0.85% |
| $25,000 | 28 | 0.74% | 1.44% |
| $50,000 | 28 | 0.90% | 1.90% |
| $100,000 | 28 | 1.20% | 3.80% |

## Bridge to the auction-price backtest: eligible cohort, entry +1s

| Ticket | Mean spread | Mean depth | Mean commissions | Mean timing shortfall | Mean total shortfall vs auction benchmark |
|---:|---:|---:|---:|---:|---:|
| $25,000 | 1.75% | 5.65% | 0.16% | -0.00% | 7.56% |
| $50,000 | 1.43% | 3.91% | 0.10% | 0.05% | 5.48% |
| $100,000 | 1.18% | 3.49% | 0.06% | 0.62% | 5.34% |

Timing measures background price differences between auction benchmarks and sampled continuous midpoints. It is not causal market impact. Every row retains its conditional supported sample.

## Remaining work

NBBO access: unavailable_no_configured_key. Verified NBBO events: 0. Actual broker fills: 0.
Prepared 4000 windows, including 595 for the deterministic 100-event pilot.
Multi-session exit costs remain unmeasured; no same-day spread estimate is relabeled as a measured multi-session cost.

- Multi-venue quotes cover observed feeds, not official consolidated NBBO.
- Cached decision quotes are matched exactly in clock; depth books add a modeled 100ms response and may mix sampled top quotes with deeper books.
- Full-order statistics exclude unsupported orders and are conditional on future cover depth; missing costs are not zero and these are not strategy returns.
- Different size rows have different surviving samples. Common-support rows hold the same events fixed but select a liquid subset with hindsight.
- Static books do not establish smart-router access, successful fills, replenishment, cancellations, price impact or borrow approval.
- Auction-to-continuous timing is separate from spread/depth. Multi-session exits and stops need additional dated quote paths.
- No real trades were submitted. New licensed NBBO data require configured existing access; no purchase or subscription upgrade is performed.
