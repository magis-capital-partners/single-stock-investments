# Paper note: short sellers and fundamental analysis

**Type:** paper note (an original summary in our words; nothing is quoted from the paper)
**Status:** archived reference
**Adapted from:** Michael's Short-Selling desk paper note of 2026-02-02; rewritten for the SSI library.

## Citation

Patricia M. Dechow, Amy P. Hutton, Lisa Meulbroek and Richard G. Sloan, "Short-sellers, fundamental analysis, and stock returns," *Journal of Financial Economics* 61 (2001), 77-106. DOI: [10.1016/S0304-405X(01)00056-3](https://doi.org/10.1016/S0304-405X(01)00056-3).

## Question

Do short sellers, taken as a group, pick their targets with the same ratios a fundamental analyst would use, and do those targets go on to do worse than the rest of the market?

## Finding, in our words

The authors look at where short interest sits relative to simple fundamentals-to-price ratios (book value, earnings and cash flow against price, and a value estimate against price). Short positions cluster in firms where those ratios are low, that is, where the price is high relative to the fundamentals, and the positions are unwound as the ratios drift back toward normal. The low-ratio firms that attract shorts underperform afterward, and the shorts appear to pick within the low-ratio group rather than shorting it wholesale: they lean toward names where a low ratio does not look justified by growth, and they stay away when the position would be expensive or risky to hold.

The desk reading is deliberately narrow. Short sellers have historically concentrated where price has run ahead of fundamentals, and that concentration has lined up with later underperformance. That is a reason to do the fundamental work on an idea, not a reason to skip it, and not a reason to short every expensive stock.

## How the desk uses it

- A new idea whose claim rests on the gap between price and reported fundamentals starts in the `accounting` category and its lenses (`accounting`, `revenue_recognition`, `earnings_vs_cash`, `working_capital`) before any story category.
- The paper's cost point is our tradability gate: a sound fundamental view with no borrow or a crowded short is still a candidate, not a position (`borrow_and_carry`, `crowding_squeeze`).
- A paper note is filed when a result changes how we screen, not to store an abstract. This one justifies putting fundamentals-to-price ratios into the quant screen as a reason to open a file, which is how `build_short_quant_screen.py` treats them.

## What this note will not hold

No copied tables, equations or abstract. The public version is linked above; the implication is written here in our words.
