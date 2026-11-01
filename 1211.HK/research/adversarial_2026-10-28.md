---
block_final: false
consistency: pass
ticker: 1211.HK
dive: deep_dive_2026-10-28.md
---

# Adversarial review: BYD Company Limited (1211.HK)

**Date:** 2026-10-28
**Reviewer:** Milly pass (the supplied research note challenged against the deep dive and the valuation tool)
**Dive:** [deep_dive_2026-10-28.md](deep_dive_2026-10-28.md)
**Valuation:** [valuation.json](valuation.json)

## What was attacked

1. Identity. 1211.HK is the Hong Kong H-share line, currency HKD. The security master name on the bare symbol BYD is BOYD GAMING CORP. The dive refuses that symbol. 002594.SZ and BYDDY are named as the same issuer in other currencies, not as a second holding. No factual miss found on identity.
2. Currency. The price and the owner-cash input in `valuation.json` are HKD. The earnings build is CNY 3.22 times 1.176, rounded to HKD 3.79. A bare dollar sign is not used for either currency. The old bug that labelled a reais figure as dollars is not repeated here.
3. Starting cash. Free cash flow is rejected, with the reason written down: FY2025 free cash flow was negative CNY 97.7 billion and the payables moved. Using earnings as owner cash assumes maintenance spending matches depreciation. The dive calls that generous. Agreed. It is a labeled judgment, not a hidden boost.
4. The tool. `marvin_valuation.py` returns -5.2%, 7.7%, and 16.5% per year at HKD 70.45. That matches the supplied case at one decimal. The unrounded base is 7.6719%. The headline is not a blend. Agreed.
5. The debt charge. The prompt text ties CNY 143 billion (about HKD 18.50 a share, excess payables plus perpetual bonds) to a 4.0% annual return and a 15% price of HKD 32.2. The tool does not. Those two outputs belong to the HKD 16.10 charge (excess trade and bills only): 4.0% at HKD 86.55, and a 15% price of HKD 32.19. The fuller HKD 18.50 charge returns 3.5% and a 15% price of HKD 29.79. The dive reports the difference and does not overwrite the tool. Agreed.
6. Missing filings. The annual reports and the interim report are cited through a research note. The PDFs are not in the folder. That is a source gap, not a number the dive invented on top of the note. It stays in human review. It is not treated as a closed audit.
7. Pass conclusion. At HKD 70.45 the base return is 7.7% per year. Calling that a wait, with a buy zone of HKD 32 to HKD 48, follows the hurdle and the debt sensitivity. It is not a claim that the business has no scale.

## Factual errors

None that require a rewrite of the tool's annual returns. The HKD 18.50 versus HKD 16.10 mix-up is a labeling error in the request summary, and the dive keeps the tool's split. Gaps below stay as human review.

## Inference gaps

- Official PDF bytes, page ties, and the ISIN.
- Third-quarter 2026 results, due 29 October 2026. The starting earnings figure is stale the day after this note.
- Whether "other payables" and supply-chain notes should be inside the debt charge. The dive leaves them out and says so.
- Items the source note itself marked unconfirmed are not promoted to facts.

## Consistency

The executive summary, the returns statement, the classification row, and `valuation.json` `implied_return.base_pct` are the same 7.7% base case. Bear -5.2% and bull 16.5% are scenario results, not the headline. The 4.0% figure is the payables sensitivity, not the base case.
