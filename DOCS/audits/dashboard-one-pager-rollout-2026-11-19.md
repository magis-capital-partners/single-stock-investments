# All-stock one-pager rollout — 2026-11-19

Every one of the 986 stocks in the verified coverage snapshot receives the six-tab research layout. Source-backed financial histories are available for 760 stocks and shareholder-return histories for 958. Missing histories and unpublished model inputs remain explicit gaps; source refreshes do not upgrade valuation eligibility.

The full-data rendering check exercised all 5,916 tabs without errors. Representative operating-company, bank and EUR-reporting pages were inspected on desktop and mobile. The return comparison was checked against matching stock/SPY observation dates.

| Published data | Measured bytes | Limit |
| --- | ---: | ---: |
| Startup core after navigation repairs | 5,898,510 | 6,000,000 |
| Largest stock detail file | 1,835,877 | 20,971,520 |
| Largest JSON asset, including the source-navigation index | 7,801,191 | 20,971,520 |

Financial and return inputs are preserved in 52 private parts, each below 8 MiB, with complete read-back checksum verification. Git contains only the small part index, metadata counterparts and private asset receipts. The generated full input snapshot is not committed.

Owned Git destinations are checked against Git trees, including sparse checkouts. Existing text counterparts are preferred to invented PDF paths. Relative proof references retain their original text while navigation uses the verified destination. Missing originals are visibly unavailable; in-app research readers and external publisher links remain separate navigation options.

Validation covers fiscal boundaries, YTD differences, reporting currencies, parent versus consolidated claims, pre-1970 exchange dates on Windows, source resolution, partition completeness, display controls, return math, private preservation, publication coverage, hosting limits and workflow behavior.
