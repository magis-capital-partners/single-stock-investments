# All-stock one-pager rollout — 2026-11-19

Every one of the 986 stocks in the verified coverage snapshot receives the six-tab research layout. Source-backed financial histories are available for 760 stocks and shareholder-return histories for 933. Missing histories and unpublished model inputs remain explicit gaps; source refreshes do not upgrade valuation eligibility.

The full-data rendering check exercised all 5,916 tabs without errors. Representative operating-company, bank and EUR-reporting pages were inspected on desktop and mobile. The return comparison was checked against matching stock/SPY observation dates. The [production deployment](https://github.com/magis-capital-partners/single-stock-investments/actions/runs/44477344958) succeeded at commit `61ec94eeac9cd0bbd72f47297982890109bf51d8`. The live AAPL page was checked for all six tabs, quarterly and full financial history, an in-dashboard fund-letter passage, and matching SPY/price-only return comparisons.

| Published data | Measured bytes | Limit |
| --- | ---: | ---: |
| Startup core after navigation repairs, full-universe staging check | 5,898,510 | 6,000,000 |
| Largest stock detail file, full-universe staging check | 1,874,612 | 20,971,520 |
| Largest JSON asset in the complete production publication | 16,668,716 | 20,971,520 |

The production run separately enforced both size limits against the complete research library. It prepared all 986 briefs, repaired navigation in 1,919 publication files, and recorded 52,042 repaired references and 4,406 unavailable originals. These reference counts include relative-path normalization and are not a count of distinct broken URLs. The live fund-letter reader was verified even where the original Git destination is unavailable.

Financial and return inputs are preserved in 52 private parts, each below 8 MiB, with complete read-back checksum verification. Git contains only the small part index, metadata counterparts and private asset receipts. The generated full input snapshot is not committed.

Historical cash distributions are normalized to the price share basis once. The corrected snapshot retains available pre-1970 history and takes precedence over older pilot caches. Twenty-five vendor histories that materially conflict with adjusted prices are withheld with a source-review explanation; 28 other listings have no usable provider history. The benchmark uses the same calculation version and matching observed dates.

Owned Git destinations are checked against Git trees, including sparse checkouts. Existing text counterparts are preferred to invented PDF paths. Relative proof references retain their original text while navigation uses the verified destination. Missing originals are visibly unavailable; in-app research readers and external publisher links remain separate navigation options.

Validation covers fiscal boundaries, YTD differences, reporting currencies, parent versus consolidated claims, pre-1970 exchange dates on Windows, source resolution, partition completeness, display controls, return math, private preservation, publication coverage, hosting limits and workflow behavior.
