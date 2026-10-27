# All-210 reverse-split data reconciliation

All 210 original candidate events now have source-bound cash and trailing operating cash flow. Dilution is calculable exactly for 209 events; the final event has a conservative bound that proves the fixed 25% threshold. No missing number was filled by an assumed zero.

| Input | Reconciled coverage |
|---|---:|
| Reported unrestricted cash | 210 / 210 |
| Total trailing operating cash flow | 210 / 210 |
| Exact comparable common-share growth | 209 / 210 |
| Dilution threshold, including one proven bound | 210 / 210 |
| Financial reports recovered and parsed | 608 |
| Current reports recovered and scanned | 1657 |
| Complete transaction submissions recovered | 69 |
| Source-classified completion/receipt claims | 162 |

## What changed

The extractor now reads original filing contexts, custom captions, explicit table zeroes and Cash as well as CashAndCashEquivalents. It reconciles continuing and discontinued operating cash flow and checks share class, reverse-split factors and retrospective restatements. Restricted cash remains separate. Transactions are grouped by economic deal so repeated announcements and cumulative ATM sales are not added twice.

Historical inputs use only filings public before each event decision. A fresh download does not make a later filing available earlier. Filing-date-only evidence becomes available at midnight New York time on the next calendar day. Source hashes and field evidence are preserved.

## Remaining eligibility limits

Four cash observations exceed the unchanged 200-day freshness limit: OLOX (223 days), LRHC (203), SEGG (216) and YYAI (201). YYAI also has a stale share observation. These observations are extracted, but their affected signals remain unknown. DFLI has no entry session in the original price cache; it has a prospective financial snapshot, with no invented price or fill.

KUST has an issued-share count for the earlier period rather than an exact outstanding count. Outstanding shares cannot exceed issued shares. After reconciling split units, its dilution lower bound is 1,970.13%, proving the 25% condition. Exact growth remains null.

21 events have nonnegative trailing operating cash flow. A cash/burn runway is not finite for those periods; null denotes no measured operating cash burn rather than failed extraction. Historical positive CFO does not guarantee future cash generation.

## Reconciled feature overlay

| Signal | Pass | Fail | Unknown |
|---|---:|---:|---:|
| reported_runway | 132 | 73 | 5 |
| S1 | 0 | 20 | 190 |
| S2 | 0 | 0 | 210 |
| S4 | 185 | 23 | 2 |
| S7 | 190 | 12 | 8 |

Reported runway passes below six months of cash divided by trailing annual operating cash burn. S4 passes at comparable share growth of at least 25%, subject to freshness and entry availability. Share comparisons use a 150–240-day interval, with denominator type recorded. S7 remains the saved third-plus screen excluding a single adjusted daily close-to-close rally of 50% or more in the five completed sessions before entry; missing history is excluded.

These counts describe candidate features, not executed trades. The original frozen backtest and performance figures have not been rewritten or rerun with this overlay.

## Financing limits

The 162 completion/receipt claims have source classifications by one analyst. They are not independent, outcome-blinded reviews. The original S2 promotion rule requires independent reconciliation of identity, cash, units and saleability. All 210 S2 values remain unknown. An automated scan returning no deal does not prove financing absence.

Net receipts, gross receipts, note face value, noncash consideration, restricted collateral and committed uses are separate fields. A diagnostic cash subtotal adds only supported net amounts in the balance currency with receipt intervals wholly after the balance date and public before the decision. It is not certified available cash. No event has fully verified financing-adjusted cash. Strict S1 therefore has no passing observations.

Examples: ETHZ investors could settle a $425 million placement with cash, ETH or both; the headline does not establish the cash mix. NBY reported $25 million cash plus about $109 million in tokens, with delayed exercise conditions on underlying shares. LRHC reported $9.635 million net receipts, but $9.5 million was allocated to crypto purchases, preferred redemptions and a controlled account. Net receipts cannot automatically become operating runway or immediately saleable float.

Some final fees, actual settlement mixes, collateral overlap and disbursement timing are not established by the reviewed disclosures. These remain explicit gaps. Finishing them requires additional source evidence and truthful independent reviews; assumed amounts or reviewers cannot satisfy those requirements.

## Reproduce and inspect

Run node _system/scripts/third_plus_reconciliation.cjs to rebuild from the existing local cache, without downloads or broker actions. Collection is separate: node _system/scripts/third_plus_reconciliation_collect.cjs metadata|filings|financing|terms, followed by the corresponding Python parsers. Recovery uses free SEC filings and $0 new market data.

The local reconciliation directory contains AUDIT.html (all 210 rows and full evidence), financing_claim_audit.local.json, source_inventory.local.json, reconciled_events.local.json and reconciled_features.local.json. The feature overlay preserves signals_v1 and is available for a newly registered replay. It is not automatically promoted into the original study or a live executor.

Aggregate reports and manifest are archived under runs/35bdfafcaf319be19a1359eafa05d4d6a0e4559e55bd46da46fbd2cbb484e31c/. Full local snapshots are archived under versions/35bdfafcaf319be19a1359eafa05d4d6a0e4559e55bd46da46fbd2cbb484e31c/. No Gateway, scheduler, order, paid data or sealed holdout was used.

Data version: 35bdfafcaf319be19a1359eafa05d4d6a0e4559e55bd46da46fbd2cbb484e31c. Built 2026-10-24T20:47:21.204Z.
