# Filter recommendation after the reconciled-data replay

Use third-or-later reverse split plus the saved 50% daily-rally veto as the research reference. The rule excludes a name if any single adjusted daily close-to-close rise in the five completed sessions before entry is at least 50%; this is not a cumulative five-day-return rule. Missing observations exclude the candidate.

Keep actual common-share dilution of at least 25% over a comparable 150–240-day interval as the leading fundamental A/B test. It is not yet a proven mandatory filter. Rapid repeat splitting within 180 days is a secondary timing hypothesis with only 20 traded issuers.

Do not add negative operating cash flow, short reported runway or operating loss as mandatory standalone conditions based on this study. Their historical conditional profits were worse than the saved screen. Revenue decline of at least 15%, operating margin decline of at least eight percentage points, the existing score >=60, accrual quality and negative equity can inform underwriting; their small samples or weaker matched profit do not justify automatic admission.

| Rule (all additions include saved base) | Trades / issuers | 20-session net marked P&L | 10-session net marked P&L | 20-session closing drawdown |
|---|---:|---:|---:|---:|
| Third-plus + rally veto | 41 / 33 | $7,385.20 | $6,270.42 | −$2,419.39 |
| Share growth ≥25% | 40 / 33 | $7,997.10 | $6,074.91 | −$2,455.39 |
| Previous split within 180 days | 28 / 20 | $7,586.38 | $5,262.27 | −$2,150.22 |
| Reported runway <6 months | 30 / 28 | −$5,030.36 | −$12,279.01 | −$16,976.66 |
| Negative operating cash flow | 43 / 40 | −$2,239.26 | −$10,824.18 | −$15,437.54 |
| Operating loss | 44 / 41 | −$1,632.69 | −$10,686.65 | −$15,437.54 |
| Revenue decline ≥15% | 16 / 14 | $4,252.47 | $3,287.08 | −$537.98 |
| Operating margin decline ≥8pp | 20 / 17 | $3,874.15 | $2,488.01 | −$637.21 |
| Existing score ≥60 | 16 / 14 | $2,383.62 | $1,556.55 | −$537.98 |

These figures span January 2023 through October 12, 2026, over 46 common calendar months. The primary account is a declared $1 million research reference with a $25,000 target, 1% participation, three-name maximum and unchanged squeeze reserves. Mean admitted size is only $714.53 for the saved screen and $749.24 for dilution. The figures are modeled, include unresolved marked obligations where reported, and do not establish what $25,000 actual fills would earn.

The dilution addition gains only $611.90 at 20 sessions. Its issuer-bootstrap 95% incremental interval is about −$914 to +$2,474, and it loses about $195.51 versus the saved screen at 10 sessions. At full hypothetical $25,000 fills and strict SSR it also earns less: $173,881.98 versus $181,992.48. This is not a robust optimized winner.

A filter can reduce eligible candidates while increasing actual admitted trades. Excluding a position frees name, sleeve, capital or overlap capacity, so another candidate can enter. These are complete portfolio replays, not deletion of selected rows from an old trade ledger. Weaker businesses can still experience large squeezes.

## Tests that should decide whether to keep a filter

1. Data integrity: freeze pre-entry filings; use total CFO and matching fiscal periods/currencies; reconcile share classes and splits; preserve restricted cash, stale facts, known bounds and unknown values. All 210 feature snapshots pass the source-clock audit.
2. Fair comparisons: compare each addition against both the saved screen and a saved-screen control with the added feature observed. Both controls retain the rally veto. Keep candidate, rejection, executed-trade and issuer counts.
3. Statistical uncertainty: cluster by issuer, use six-month calendar blocks, and adjust the 19 current comparisons with Holm. The dilution improvement spans zero; every adjusted p-value is 1. Previously tried historical configurations remain an additional selection limitation.
4. Stability: repeat at 10 sessions, 0.1%/1%/5% participation, 20%/50%/150% APR cost cases, and full target separately. Remove the best one and five issuers and inspect all calendar cohorts. Retain partial covers, stale marks and unreturned loans.
5. Chronology: train only on fully closed and returned-loan positions before a 20-session embargo. Require 30 prior training issuers; the current walk-forward never reaches that gate and therefore retains the saved rule in every evaluated quarter.
6. Live evidence: independently reconcile financing cash, security terms and saleable float; document actual locate quantity/APR, fills, recalls and cover costs. Complete the six-lens thesis, catalyst, valuation, contrary evidence and falsifiers.
7. Prospective proof: freeze the candidate rule before new observations, log every eligible decision and rejection, and evaluate actual net costs and tail losses. Fifty decisions across thirty issuers is a review checkpoint, not automatic proof or trading authority.

No rule passes all declared research-candidate gates. Two positions remain unresolved in the saved and dilution primary runs; sparse verified borrow/fill evidence cannot be supplied by a price backtest. Dated historical industry applicability remains unknown for 141 events. The strict debt-maturity route qualifies no candidates, with 138 unknown observations, so it has not been meaningfully evaluated.

The first run had a bug in the covered controls that admitted rally-veto failures. The corrected run preserves S7 pass, adds a regression test and records exact code hashes in implementation_revision.json. Primary strategy ledgers and thresholds did not change. The first run remains archived and marked superseded.

[Complete report](REPORT.md) · [Machine-readable results](summary.json) · [Validation](validation.json)

Data version: 33d69eb13f5e743c147956469fd9698710101e2f963be225ee96b12b77fb14a1.
