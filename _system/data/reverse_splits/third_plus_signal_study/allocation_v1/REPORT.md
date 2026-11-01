# Complete filter-stacking and sizing experiment

All 210 frozen reverse-split events, 119 issuers, 38 registered policies, three cost/fill scenarios, two slot definitions and two budget regimes. Every security remains assumed tradable. 3025 distinct sizes/cost execution paths were replayed, with fresh fills, costs and exits rather than scaled trade profits. All 36 original controls reproduce to the cent and trade count.

The registered protocol is [protocol.json](protocol.json), SHA-256 13c1b2c4321f86672e28ab61b0a39155024c55c59609338ace40940f681e1166. No new market data, broker socket, ThetaData, paid acquisition or sealed holdout is used. Market cutoff 2026-10-12. The entire historical period had already been inspected; these are retrospective tests, not a prospective validation.

## Same execution, capital and tail-risk assumptions

E2 permitted offer, 60 minutes, 10% participation, 20-session horizon, $100k maximum requested position and $10m reference account. Base uses the existing 50% APR/spread/fill model; favorable and stress inputs remain unchanged.

The common-budget regime reserves $300k gross and $600k additional loss under a minimum +200% squeeze. Morning inventory uses only the prior inventory and known current opening prices. Same-arrival reservations use requested budgets, including eventual no-fills. These caps prevent additional admissions when exceeded; they do not invent a successful liquidation or guarantee a bound on loss. Original-budget controls omit these new sleeve limits.

The daily-budget comparisons allocate the same intended $50k per admitted parent, either equally or by signal weights, with the same $100k maximum. Budgets round down to $100; residual allocation and subsequent admissions can differ. Fixed $25k/$50k controls, original-budget comparisons, requested dollars and actual fills make underinvestment visible.

## All fixed policies · three issuers · common budget

| Policy | Base net | Closing drawdown | Stress net | Entries | Filled dollars | Without best issuer, reallocated | Without best five, reallocated | Worst issuer omission |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rank repeat / weak close only | $153,764.66 | −$213,273.19 | $60,735.81 | 73 | $445,179.85 | $97,511.78 | −$20,785.57 | $97,511.78 |
| Cash burn + operating loss | $153,680.46 | −$213,273.19 | $60,470.22 | 72 | $444,719.79 | $97,427.58 | −$20,723.05 | $97,427.58 |
| Cash burn · $100k | $153,552.23 | −$213,273.19 | $60,680.41 | 73 | $445,118.34 | $97,299.35 | −$20,723.05 | $97,299.35 |
| Cash burn · squeeze-adjusted cap | $153,552.23 | −$213,273.19 | $60,680.41 | 73 | $445,118.34 | $97,299.35 | −$20,723.05 | $97,299.35 |
| Cash burn + prior price weakness | $148,992.10 | −$213,291.84 | $100,242.85 | 66 | $437,320.29 | $92,938.73 | −$21,346.68 | $92,938.73 |
| Cash burn + margin decline | $143,283.53 | −$214,133.55 | $49,629.75 | 41 | $372,489.79 | $29,883.37 | −$31,229.24 | $29,883.37 |
| Rapid repeat · $100k | $139,899.77 | −$44,570.77 | $89,232.83 | 49 | $228,764.33 | $79,451.58 | $122.69 | $79,451.58 |
| Cash burn + weak close | $129,996.32 | −$9,855.32 | $93,183.83 | 45 | $218,747.93 | $69,047.09 | −$102.10 | $69,047.09 |
| Cash burn + rapid repeat | $129,700.17 | −$44,570.77 | $84,420.71 | 40 | $207,555.52 | $69,251.98 | −$439.93 | $69,251.98 |
| All candidates · $100k | $119,774.78 | −$213,242.26 | $100,000.72 | 78 | $387,251.31 | $63,521.90 | −$18,089.50 | $63,521.90 |
| Grouped signals · rank only | $108,778.92 | −$213,273.19 | $16,702.63 | 76 | $352,651.55 | $52,526.04 | −$20,449.02 | $52,526.04 |
| Rally veto · $100k | $108,596.31 | −$213,273.19 | $16,607.60 | 76 | $352,514.61 | $52,343.43 | −$20,449.02 | $52,343.43 |
| Uncapped correlated signal count | $108,596.31 | −$213,273.19 | $16,607.60 | 76 | $352,514.61 | $52,343.43 | −$20,449.02 | $52,343.43 |
| Weak close increases target | $95,234.92 | −$61,104.27 | $65,695.25 | 73 | $251,307.42 | $39,603.68 | −$2,538.20 | $39,603.68 |
| Cash burn + dilution | $95,011.56 | −$213,241.54 | $29,945.81 | 70 | $349,070.21 | $39,820.40 | $36,780.70 | $39,820.40 |
| Cash burn + short runway | $94,359.38 | −$213,209.66 | $14,215.76 | 65 | $331,295.67 | $38,106.49 | −$28,459.84 | $38,106.49 |
| Matched daily budget · rank only | $94,029.36 | −$113,044.33 | $56,659.16 | 73 | $276,959.29 | $60,546.39 | −$8,345.96 | $60,546.39 |
| Matched daily budget · rank and size | $94,029.36 | −$113,044.33 | $56,659.16 | 73 | $276,959.29 | $60,546.39 | −$8,463.06 | $60,546.39 |
| Cash burn · $50k | $93,816.93 | −$113,044.33 | $56,603.76 | 73 | $276,897.78 | $60,333.96 | −$8,283.44 | $60,333.96 |
| Matched daily budget · uniform | $93,816.93 | −$113,044.33 | $56,603.76 | 73 | $276,897.78 | $60,333.96 | −$8,283.44 | $60,333.96 |
| Matched daily budget · size only | $93,816.93 | −$113,044.33 | $56,603.76 | 73 | $276,897.78 | $60,333.96 | −$8,400.53 | $60,333.96 |
| Repeat increases target | $90,783.88 | −$61,104.27 | $40,847.87 | 73 | $233,954.51 | $38,176.99 | −$2,538.20 | $38,176.99 |
| Cash burn + revenue decline | $88,463.14 | −$212,416.25 | $21,089.67 | 30 | $280,104.44 | −$25,640.30 | −$30,902.17 | −$25,640.30 |
| Cash burn + legacy score | $87,387.85 | −$213,209.03 | $19,751.30 | 39 | $283,757.59 | −$25,591.80 | −$27,543.72 | −$25,591.80 |
| Grouped signals · rank and size | $86,009.01 | −$213,273.19 | $15,638.43 | 76 | $317,078.67 | $33,164.98 | −$20,449.02 | $33,164.98 |
| Grouped signals · squeeze-adjusted | $86,009.01 | −$213,273.19 | $15,638.43 | 76 | $317,078.67 | $33,164.98 | −$20,449.02 | $33,164.98 |
| Grouped signals · size only | $85,826.40 | −$213,273.19 | $15,543.40 | 76 | $316,941.73 | $33,164.98 | −$20,449.02 | $33,164.98 |
| Grouped signals · past-issuer shrinkage | $85,211.75 | −$101,196.00 | $26,175.55 | 76 | $239,478.43 | $32,367.72 | −$6,767.73 | $32,367.72 |
| Rank and size repeat / weak close | $83,641.73 | −$61,104.27 | $52,983.59 | 73 | $226,366.82 | $52,349.87 | −$2,600.72 | $52,349.87 |
| Repeat / weak close · squeeze-adjusted | $83,641.73 | −$61,104.27 | $52,983.59 | 73 | $226,366.82 | $52,349.87 | −$2,600.72 | $52,349.87 |
| Repeat / weak-close tiers | $83,429.30 | −$61,104.27 | $52,928.20 | 73 | $226,305.31 | $52,320.04 | −$2,538.20 | $52,320.04 |
| Weak close · $100k | $76,687.83 | −$9,855.32 | $55,354.75 | 47 | $156,847.06 | $21,381.42 | $60,859.53 | $21,381.42 |
| Rank and size · past-issuer shrinkage | $73,166.36 | −$61,104.27 | $47,770.92 | 73 | $210,068.17 | $45,104.26 | −$2,600.72 | $45,104.26 |
| Cash burn · $25k | $53,184.50 | −$61,104.27 | $30,649.75 | 73 | $176,308.85 | $36,774.91 | −$2,538.20 | $36,774.91 |
| Dilution · $100k | $53,141.43 | −$213,241.54 | −$9,155.07 | 72 | $258,156.55 | $480.01 | $36,511.31 | $480.01 |
| Cash burn + negative equity | $52,218.08 | −$213,230.90 | $16,819.50 | 31 | $238,653.31 | −$8,230.11 | −$31,966.34 | −$8,230.11 |
| Cash burn + repeat + weak close | $9,314.48 | −$3,878.89 | $4,886.66 | 16 | $12,866.02 | $1,249.17 | −$693.41 | $1,249.17 |
| Cash burn + accruals | $1,639.61 | −$1,203.68 | $77.20 | 21 | $7,714.22 | $1,044.99 | −$400.54 | $1,044.99 |

## Incremental tests · common budget

Each row changes a declared allocation choice; a positive profit difference alone does not establish a better policy. The matched daily-budget rows provide the direct comparison at a common intended daily allocation.

| Control → test | Base profit change | Change in absolute drawdown | Change in filled dollars | Stress profit change |
|---|---:|---:|---:|---:|
| Cash burn · $100k → Cash burn + rapid repeat | −$23,852.06 | −$168,702.42 | −$237,562.82 | $23,740.30 |
| Cash burn · $100k → Cash burn + weak close | −$23,555.91 | −$203,417.88 | −$226,370.41 | $32,503.42 |
| Cash burn · $100k → Cash burn + repeat + weak close | −$144,237.75 | −$209,394.30 | −$432,252.32 | −$55,793.75 |
| Cash burn · $100k → Rank repeat / weak close only | $212.43 | $0.00 | $61.51 | $55.40 |
| Cash burn · $100k → Repeat / weak-close tiers | −$70,122.94 | −$152,168.92 | −$218,813.03 | −$7,752.21 |
| Cash burn · $100k → Rank and size repeat / weak close | −$69,910.50 | −$152,168.92 | −$218,751.52 | −$7,696.82 |
| Matched daily budget · uniform → Matched daily budget · rank only | $212.43 | $0.00 | $61.51 | $55.40 |
| Matched daily budget · uniform → Matched daily budget · size only | $0.00 | $0.00 | $0.00 | $0.00 |
| Matched daily budget · uniform → Matched daily budget · rank and size | $212.43 | $0.00 | $61.51 | $55.40 |
| Grouped signals · rank and size → Grouped signals · past-issuer shrinkage | −$797.25 | −$112,077.19 | −$77,600.24 | $10,537.12 |
| Uncapped correlated signal count → Grouped signals · size only | −$22,769.91 | $0.00 | −$35,572.88 | −$1,064.20 |
| Cash burn · $100k → Cash burn · squeeze-adjusted cap | $0.00 | $0.00 | $0.00 | $0.00 |

Negative change in absolute drawdown means a smaller closing drawdown. Positive change in profit can come from different deployed capital; inspect both columns.

## Chronological selection

At each January boundary, only fully completed earlier trades and loan returns can score a policy. Earlier unfinished entries still occupy their original admission slots. Require 20 traded issuers in both completed base and stress training sets; choose the best positive worst-cost profit/drawdown ratio, otherwise use the fixed cash-burn $100k fallback. The same plan is then replayed under all three future cost scenarios. Existing positions retain their entry sizing and exits when the annual selection changes.

### three slots / matched budget

Base $152,134.01, closing drawdown −$213,273.19, stress $60,331.40, 65 entries and $439,272.87 filled dollars.

| Test year | Policy chosen before year | Eligible positive training policies | Fallback | Year net |
|---|---|---:|---|---:|
| 2024 | Cash burn · $100k | 0 | true | −$24,558.07 |
| 2025 | Cash burn · $100k | 0 | true | $121,010.53 |
| 2026 | Cash burn + weak close | 28 | false | $57,108.76 |

2023 uses the fixed starting policy. Omitting the strongest issuer and retraining: $95,880.82; strongest five, retrained: −$20,723.05.

### three slots / original budget

Base $152,134.01, closing drawdown −$213,273.19, stress $60,331.40, 65 entries and $439,272.87 filled dollars.

| Test year | Policy chosen before year | Eligible positive training policies | Fallback | Year net |
|---|---|---:|---|---:|
| 2024 | Cash burn · $100k | 0 | true | −$24,558.07 |
| 2025 | Cash burn · $100k | 0 | true | $121,010.53 |
| 2026 | Cash burn + weak close | 28 | false | $57,108.76 |

2023 uses the fixed starting policy. Omitting the strongest issuer and retraining: $95,880.82; strongest five, retrained: −$20,723.05.

### unlimited slots / matched budget

Base $261,596.60, closing drawdown −$213,273.19, stress $149,856.64, 116 entries and $646,871.05 filled dollars.

| Test year | Policy chosen before year | Eligible positive training policies | Fallback | Year net |
|---|---|---:|---|---:|
| 2024 | Cash burn · $100k | 0 | true | $96,798.82 |
| 2025 | Repeat increases target | 26 | false | $104,602.86 |
| 2026 | Weak close · $100k | 31 | false | $61,622.14 |

2023 uses the fixed starting policy. Omitting the strongest issuer and retraining: $93,540.78; strongest five, retrained: −$6,095.25.

### unlimited slots / original budget

Base $261,596.60, closing drawdown −$213,273.19, stress $149,856.64, 116 entries and $646,871.05 filled dollars.

| Test year | Policy chosen before year | Eligible positive training policies | Fallback | Year net |
|---|---|---:|---|---:|
| 2024 | Cash burn · $100k | 0 | true | $96,798.82 |
| 2025 | Repeat increases target | 26 | false | $104,602.86 |
| 2026 | Weak close · $100k | 31 | false | $61,622.14 |

2023 uses the fixed starting policy. Omitting the strongest issuer and retraining: $93,540.78; strongest five, retrained: −$6,095.25.

## Complete test scope and interpretation

- Cash burn plus every registered single overlay, plus repeat/weak-close pair and triple gates.
- Fixed-size controls; sizing alone; ranking alone; both; past-issuer shrinkage; and matched daily capital pools.
- Related distress, issuance and price evidence contributes at most one grouped point. The correlated raw-count policy is retained as a diagnostic comparator. Unknown overlays receive no bonus rather than an automatic rejection.
- Full tier bonus requires 20 distinct prior issuers in the same signal cell, each at least 24 sessions older.
- Squeeze variants cap targets using only 20 completed sessions of split-adjusted upward price moves, a minimum +200% stress and a $200k per-parent stress-loss budget. Missing price history retains the floor and remains tradable.
- Every one of 456 fixed-policy cases is replayed without each of 119 issuers and without its strongest one/five issuers, recomputing allocation and available capacity. Published leaveout distributions omit licensed per-event returns.
- Adaptive strongest-issuer removals retrain the annual choices. No later test-year result chooses an earlier policy.
- No rule is declared validated from this already-explored historical sample. Stress cases are assumptions rather than probability bounds. Open positions at the market cutoff remain marked and owed.

## Input receipts and reproduction

Existing venue index SHA-256 4a92d49764b796da191b00a4ce52425f77994c4a9aec5435d90fc1c44fe335d0. Daily OHLCV database SHA-256 5f1e5de9fcba98069245bcecfaf928b66c45659df6cd81a6a6dd4e78f0626ce0. Code, protocol, frozen feature decisions and original numerical controls are bound by the publication source fingerprints. Raw licensed prices and quantities remain local.

```powershell
node _system/scripts/third_plus_execution/allocation_study.cjs --register
node _system/scripts/third_plus_execution/allocation_study.cjs --source-root <existing-cache-repository>
node _system/scripts/third_plus_execution/allocation_publish.cjs --source-root <existing-cache-repository>
node _system/scripts/third_plus_execution/allocation_study.cjs --check
node _system/scripts/third_plus_execution/allocation_publish.cjs --check
```

Publication 0dee2805aa5569a4c5c7cfd93460eacdcb3c75615944b3b1322e7e8cd020c4be.
