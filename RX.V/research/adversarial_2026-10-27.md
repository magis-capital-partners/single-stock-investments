---
block_final: false
consistency: pass
ticker: RX.V
dive: deep_dive_2026-10-27.md
---

# Adversarial review: BioSyent Inc. (RX.V)

**Date:** 2026-10-27
**Reviewer:** Milly pass (filing arithmetic challenged against the deep dive)
**Dive:** [deep_dive_2026-10-27.md](deep_dive_2026-10-27.md)
**Valuation:** [valuation.json](valuation.json)

## What was attacked

1. Identity. TSX Venture symbol RX is BioSyent Inc. and was trading on 27 October 2026. Yahoo RX.V is that common share in CAD. Yahoo BIOYF is the same legal name on the pink sheets in USD. The folder id is RX.V because a bare RX stub already sits in the security master as an unvalidated harvest, and RXO is a different U.S. issuer. One holding. No factual miss found.
2. Starting cash. The twelve-month build (2025 cash from operations, minus the first half of 2025, plus the first half of 2026, minus property and intangible additions) uses lines that are in the cash flow statements. The acquisition outflow is excluded. That choice is disclosed. It is the right maintenance definition. It still leaves Oral Science inside the cash figure for only four months, and the statements do not isolate that cash. Treating the partial year as if it were a normal year would overstate a run rate the company did not publish. The dive refuses that annualization. Agreed.
3. Share count. The denominator is the second-quarter 2026 diluted weighted average, not shares outstanding on 30 June 2026. That makes owner cash per share lower than a period-end basic count would. The dive says so. If buybacks after 30 June continued, the model is slightly harsh. That is not a factual error. It is a stated limit.
4. Growth of 6% then 3%, and a sale at 15 times, are not in any filing. The Canadian pharmaceutical sales growth (11% then 13%) is higher than 6%. Cash from operations grew more slowly. Gross profit fell as a share of sales after Oral Science. Using 6% is a judgment that can be wrong in either direction. The bull case at 13.5% per year still misses 15%. The pass does not depend on the 6% being exact.
5. Net cash is left out. A critic can say the buyer gets the cash as well as the earnings. The dive shows the June 2026 net figure and refuses to grow it. That is conservative and labeled. It is not a hidden asset given a value of nothing by accident.
6. Pass conclusion. At CAD 16.61 the tool's base return is 9.4% per year. Calling that a pass for new capital follows the house hurdle. It is not a claim that the business is poor. Combogesic is a real example of a returned license, not a metaphor.

## Factual errors

None that require a rewrite of the cited statement lines. Gaps below stay as human review.

## Inference gaps

- SEDAR issuer number, CUSIP, and ISIN. The official PDFs read on 27 October 2026 do not print CUSIP or ISIN.
- Dollar sales by brand, and a separate oral-health cash-from-operations line.
- The earn-out formula. The June estimate of contingent consideration is not split.
- A July-and-August issuer-bid share count on its own line. The half-year cancellation is 218,500 shares. The current bid's cancellation through 20 August 2026 is 250,000, measured from 15 December 2025.

## What the circular closed

Director and insider share counts, the 6 April 2026 record-date count of 11,437,090, 2025 pay, and the issuer-bid terms are now in the dive from the 6 April 2026 circular. Preferred shares outstanding are nil at 30 June 2026 and at 31 December 2025. One discussion sentence uses 162,061 as if it were a share count. Note 18 uses that figure as the share-capital dollar reduction and 218,500 as the share count. That is a wording clash, not a change to owner cash. Owner-cash inputs were re-added from the official 2025 and second-quarter 2026 cash flow statements and did not change. The latest completed close is still CAD 16.61 on 26 October 2026.

## Consistency

The executive summary, the returns statement, the classification row, and `valuation.json` `implied_return.base_pct` are the same 9.4% base case. Bear 1.4% and bull 13.5% are scenario results, not the headline.
