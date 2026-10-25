# Why fundamental calculations are unknown

> Reconciliation update: the [all-210 v2 report](reconciliation_v2/REPORT.md) supersedes the extraction-coverage counts below. This document records the original frozen study inputs.

Source: the completed offline third-plus study, version c9ae184106e4f65128574c1ed53387db0dd1129a10cd87e8afa5ee8cfc09b8d3. The raw companyfacts cache is present for all 119 candidate issuers. Missing files are not the main problem. The implemented features require values that were public before each historical entry, comparable accounting periods, and consistent cash/share units.

| Calculation | Calculable on third-plus universe | Calculable after saved rally veto |
|---|---:|---:|
| Existing composite fundamental score | 136/210 | 122/190 |
| Reported cash runway | 159/210 | 145/190 |
| Cash pressure after funding reconciliation | 41/210 | 36/190 |
| Recent completed dilutive financing | 0/210 | 0/190 |
| Comparable six-month share dilution | 21/210 | 20/190 |

Calculable includes both passing and failing observations. These are candidate events, before execution and portfolio constraints.

## Cash runway

Reported runway is calculable for 159 of 210 events. For the remaining 51, 43 lack a qualifying unrestricted cash observation no older than 200 days, 7 lack comparable trailing-twelve-month operating cash flow, and 1 has no decision session. A standard tag/freshness restriction can exclude an issuer even when its full filing contains useful information.

The adjusted cash-pressure feature is calculable for only 41 events because another 118 have known/provider-flagged fundraising since the cash balance that has not been reconciled. A completed financing can replenish cash. An announcement, registration or unclosed offering is insufficient to determine its cash effect. This is unfinished source reconciliation, not proof that all those cash balances are unavailable.

## Financing

The cache contains 149 financing documents and 89 completion-language leads, but 0 independently reconciled reviews. The study required two outcome-blinded reviews of transaction identity, closing, cash, saleability and share units. That is a study evidence requirement, not an SEC requirement. Extraction alone does not meet it. Accordingly S2 is unknown, rather than falsely marked as no financing. The same requirement blocks financing-dependent combinations.

## Share dilution

Only 21 of 210 events have a usable six-month comparison under the implemented rule: 139 lack two period-end common-share observations 150–240 days apart in the same filing; 26 cross a corporate action without a verified common restatement basis; 23 lack a fresh qualifying period-end share count; 1 has no decision session. The same-filing restriction is conservative and excludes many potentially recoverable cross-filing comparisons. Weighted-average EPS shares are not an interchangeable denominator.

## Closing the gaps

1. Reconcile the cached financing sources into unique actual deals, including net cash and actual issuance dates; import truthful independent reviews with the existing review-import command.
2. Extract additional share-count observations from the cached filings, then reconcile cross-filing share classes, split/ADS units and restatements under an explicitly versioned feature revision.
3. Recover absent standard/custom cash-flow tags and annual/YTD comparisons from original filings, preserving their historical public clocks. Reassess freshness only as a declared research change.
4. Rebuild and compare both the full universe and identical covered universes. Unknown must stay separate from false.

## Saved screen

The saved screen is third-or-later reverse split AND no single adjusted daily close-to-close rise of at least 50% in the five completed sessions before entry. It currently selects 190 events, vetoes 12 and excludes 8 unknowns. No additional fundamental condition is required. This is not a cumulative five-day rally test. It is saved for research reuse; the historical study did not validate it for live trading.
