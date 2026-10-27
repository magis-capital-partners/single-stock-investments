# Recalculated third-plus fundamental-filter study

The saved starting rule is third-or-later reverse split plus the prior five-session 50% daily-rally veto. The study tests 19 additions using reconciled data and fixed framework thresholds. These are conditional historical replays; a higher historical number is not an established optimal or live-profitable policy.

Primary: 20 sessions, $25,000 target, $1 million reference NAV, unchanged squeeze reserves, three-name maximum, 1% participation and strict SSR skips. Actual positions are usually much smaller than $25,000. Common window 2023-01-19 to 2026-10-12; 46 calendar months, including idle months. Borrow availability and fills are not verified.

## Every primary comparison

| Addition to saved rule | Candidates | Trades / issuers | Net marked P&L | Change vs saved | Max closing drawdown | Open | Holm p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Third-plus only | 210 | 41 / 33 | −$16,385.97 | −$23,771.17 | −$25,416.57 | 2 | reference |
| Third-plus + rally veto | 190 | 41 / 33 | $7,385.20 | $0.00 | −$2,419.39 | 2 | reference |
| Existing score ≥60 | 47 | 16 / 14 | $2,383.62 | −$5,001.58 | −$537.98 | 1 | 1.000 |
| Negative operating cash flow | 167 | 43 / 40 | −$2,239.26 | −$9,624.46 | −$15,437.54 | 1 | 1.000 |
| Reported runway <6 months | 123 | 30 / 28 | −$5,030.36 | −$12,415.56 | −$16,976.66 | 1 | 1.000 |
| Share growth ≥25% | 170 | 40 / 33 | $7,997.10 | $611.90 | −$2,455.39 | 2 | 1.000 |
| Operating loss | 165 | 44 / 41 | −$1,632.69 | −$9,017.89 | −$15,437.54 | 2 | 1.000 |
| Revenue decline ≥15% | 43 | 16 / 14 | $4,252.47 | −$3,132.73 | −$537.98 | 1 | 1.000 |
| Operating margin decline ≥8pp | 55 | 20 / 17 | $3,874.15 | −$3,511.05 | −$637.21 | 1 | 1.000 |
| Accrual ratio ≥10% | 23 | 10 / 9 | $1,434.91 | −$5,950.29 | −$416.63 | 0 | 1.000 |
| Profit without operating cash | 2 | 0 / 0 | $0.00 | −$7,385.20 | $0.00 | 0 | 1.000 |
| Negative equity | 43 | 15 / 9 | −$3,554.41 | −$10,939.61 | −$15,808.75 | 1 | 1.000 |
| Framework debt-maturity distress | 0 | 0 / 0 | $0.00 | −$7,385.20 | $0.00 | 0 | 1.000 |
| Previous split within 180 days | 70 | 28 / 20 | $7,586.38 | $201.18 | −$2,150.22 | 0 | 1.000 |
| Weak split-day close | 54 | 10 / 10 | $1,831.63 | −$5,553.57 | −$2,150.22 | 1 | 1.000 |
| Prior 20-session return ≤−20% | 148 | 34 / 28 | $3,541.95 | −$3,843.25 | −$2,550.43 | 2 | 1.000 |
| Cash burn + dilution | 149 | 36 / 34 | $4,165.29 | −$3,219.91 | −$1,692.39 | 2 | 1.000 |
| Short reported runway + dilution | 107 | 29 / 28 | −$4,363.23 | −$11,748.43 | −$16,355.58 | 1 | 1.000 |
| Operating loss + dilution | 147 | 35 / 33 | $4,395.94 | −$2,989.26 | −$1,692.39 | 2 | 1.000 |
| Short runway + dilution + operating loss | 107 | 29 / 28 | −$4,363.23 | −$11,748.43 | −$16,355.58 | 1 | 1.000 |
| Short runway + dilution + revenue decline | 26 | 9 / 8 | $1,424.61 | −$5,960.59 | −$537.98 | 1 | 1.000 |

The largest observed primary P&L is Share growth ≥25% at $7,997.10. This is a descriptive ranking after the registered comparisons. 0 rules meet every declared research-candidate gate.

## Filters and coverage

| Feature | Pass | Fail | Unknown |
| --- | --- | --- | --- |
| S7 | 190 | 12 | 8 |
| score60 | 56 | 80 | 74 |
| burn | 185 | 20 | 5 |
| reported_runway | 132 | 73 | 5 |
| S4 | 185 | 23 | 2 |
| operating_loss | 182 | 17 | 11 |
| revenue15 | 49 | 75 | 86 |
| margin8 | 59 | 63 | 88 |
| accrual10 | 28 | 165 | 17 |
| profit_no_cash | 3 | 191 | 16 |
| negative_equity | 46 | 146 | 18 |
| debt_distress | 0 | 72 | 138 |
| S3 | 77 | 113 | 20 |
| S5 | 55 | 153 | 2 |
| S6 | 154 | 47 | 9 |

- burn: TTM total CFO <0
- reported_runway: Reported cash / negative TTM CFO <0.5 years; not financing-adjusted
- dilution: Split-adjusted common-share growth >=25% over 150–240 days; proven bounds retained as bounds
- operating_loss: TTM operating income <0
- revenue15: Same-tag TTM revenue YoY growth <=-15%
- margin8: TTM operating-margin YoY change <=-8 percentage points
- accrual10: (TTM NI - TTM CFO) / average exact current and year-ago assets >=10%; no last-asset fallback
- profit_no_cash: TTM NI>0 and TTM total CFO<0
- negative_equity: Reported stockholders equity<0
- debt_distress: Dated operating profile, negative total CFO, TTM and reconstructed-quarter reported runways <=1 year, operating loss, explicit next-12-month debt maturity>cash
- legacy_score60: Unmodified prior source-bound score>=60; diagnostic comparator, not a rebuilt score

Reported runway uses reported cash; it is not fully financing-adjusted cash. S1 and S2 remain unavailable for promotion. The strict financing/saleability and six-lens underwriting requirements have not been relaxed. Actual share dilution measures count growth, not immediately saleable supply. Negative equity is not by itself a bankruptcy forecast. Missing data, undefined growth with zero prior revenue, and inapplicable profiles remain unknown.

Dated historical profile coverage: {"operating":60,"unknown":141,"real_estate":9}. Unknown historical industry applicability remains a limitation of generic numeric screens. No current SIC was backfilled into past decisions. Accrual and cash-conversion signals share one economic family; cash burn and its runway ratio are also related. Combining them does not create independent confirmation.

## Capacity, costs and full-target benchmark

| Rule | Primary P&L | 10-session P&L | Stress P&L | 0.1% cap P&L | 5% cap P&L | Full $25k strict P&L | Full-target entries / total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Third-plus + rally veto | $7,385.20 | $6,270.42 | $4,560.56 | $1,221.56 | $10,255.78 | $181,992.48 | 73 / 73 |
| Reported runway <6 months | −$5,030.36 | −$12,279.01 | −$7,697.98 | −$456.15 | $463.75 | $11,510.66 | 40 / 40 |
| Share growth ≥25% | $7,997.10 | $6,074.91 | $5,104.44 | $1,282.11 | $12,375.99 | $173,881.98 | 68 / 68 |
| Cash burn + dilution | $4,165.29 | −$11,020.73 | $1,752.83 | $1,337.29 | $7,517.07 | $78,957.08 | 58 / 58 |
| Short reported runway + dilution | −$4,363.23 | −$12,482.67 | −$7,277.39 | −$400.08 | $2,463.65 | $3,400.17 | 35 / 35 |
| Operating loss + dilution | $4,395.94 | −$10,883.21 | $1,939.91 | $1,361.39 | $6,856.67 | $87,579.64 | 57 / 57 |
| Short runway + dilution + operating loss | −$4,363.23 | −$12,482.67 | −$7,277.39 | −$400.08 | $2,463.65 | $3,400.17 | 35 / 35 |

Full-target results remove the account and volume caps while retaining strict SSR. They assume the target can be borrowed, filled and covered. They are not estimates of achievable capacity or funded returns. The separate SSR proxy is an unsupported execution sensitivity. Base APR is 50%; lower-cost and stress APRs are 20% and 150%, with the frozen execution and fee scenarios. Dividends, bespoke locate fees and operational costs need observed records.

## Concentration and uncertainty

| Rule | Without best issuer | Without best five | Issuer increment 95% | Calendar-block increment 95% | Decision |
| --- | --- | --- | --- | --- | --- |
| Third-plus + rally veto | $3,074.99 | −$109.61 | $0.00 to $0.00 | $0.00 to $0.00 | reference |
| Reported runway <6 months | −$6,382.98 | −$7,886.45 | −$31,232.79 to $113.15 | −$31,626.02 to −$696.10 | fewer_than_30_issuers, no_positive_matched_increment, uncertainty_or_multiplicity_gate_failed, drawdown_worse_than_saved, concentration_gate_failed, unresolved_short_obligations, risk_budget_breach, nonpositive_stress_profit |
| Share growth ≥25% | $3,686.90 | $640.57 | −$914.37 to $2,474.15 | −$111.70 to $1,947.41 | uncertainty_or_multiplicity_gate_failed, drawdown_worse_than_saved, unresolved_short_obligations |
| Cash burn + dilution | $2,812.66 | $897.99 | −$13,703.81 to $3,582.62 | −$9,144.80 to $1,655.44 | no_positive_matched_increment, uncertainty_or_multiplicity_gate_failed, unresolved_short_obligations |
| Short reported runway + dilution | −$5,715.85 | −$6,996.52 | −$30,354.20 to $1,186.47 | −$31,255.00 to $76.35 | fewer_than_30_issuers, no_positive_matched_increment, uncertainty_or_multiplicity_gate_failed, drawdown_worse_than_saved, concentration_gate_failed, unresolved_short_obligations, risk_budget_breach, nonpositive_stress_profit |
| Operating loss + dilution | $3,043.31 | $978.90 | −$13,628.47 to $3,737.16 | −$8,698.43 to $1,718.51 | no_positive_matched_increment, uncertainty_or_multiplicity_gate_failed, unresolved_short_obligations |
| Short runway + dilution + operating loss | −$5,715.85 | −$6,996.52 | −$30,354.20 to $1,186.47 | −$31,255.00 to $76.35 | fewer_than_30_issuers, no_positive_matched_increment, uncertainty_or_multiplicity_gate_failed, drawdown_worse_than_saved, concentration_gate_failed, unresolved_short_obligations, risk_budget_breach, nonpositive_stress_profit |

Concentration subtraction is retrospective and does not reallocate freed capital. Full issuer-removal replays are separately reported in summary.json for the declared focus arms. Matched covered-universe controls isolate feature selection from feature availability. Confidence intervals are conditional diagnostics; the Holm family covers the 19 current additions, not every prior project experiment.

## Chronology and selection

| Rule | 2023 entry-cohort P&L | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- |
| Third-plus + rally veto | $173.88 | $2,917.86 | $299.45 | $3,994.01 |
| Reported runway <6 months | $173.88 | $1,387.51 | −$825.94 | −$5,765.80 |
| Share growth ≥25% | $173.88 | $2,917.86 | $911.35 | $3,994.01 |
| Cash burn + dilution | $173.88 | $1,556.91 | $1,245.67 | $1,188.83 |
| Short reported runway + dilution | $173.88 | $1,387.51 | −$204.86 | −$5,719.75 |
| Operating loss + dilution | $173.88 | $1,556.91 | $1,245.67 | $1,419.48 |
| Short runway + dilution + operating loss | $173.88 | $1,387.51 | −$204.86 | −$5,719.75 |

Entry-cohort attribution includes each position through its final modeled mark/loan charges; it is not a separate fresh-account calendar return. Fresh-year account replays for focus rules are in summary.json.

Quarterly walk-forward uses only fully closed and returned-loan positions before a 20-session embargo. It requires 30 training issuers and corrected positive training evidence, otherwise retains the saved screen. Selected additions: 0 / 15 quarters. Walk-forward conditional P&L: $7,385.20. Previously explored 2023–2026 history is development data, not an untouched holdout.

## Required next tests

1. Preserve as-of facts, exact filing clocks, common share units, restricted cash and explicit unknown states.
2. Require positive matched incremental profit with issuer/calendar uncertainty, family correction, acceptable drawdown and issuer-removal stability; fewer than 30 issuers stays descriptive.
3. Pass shorter holding, capacity and cost stresses without relying on unavailable exits, fractional remnants or unreturned loans.
4. Reconcile actual financing cash, security terms and saleable float before testing strict cash-pressure/financing combinations as verified signals.
5. Freeze a prospective rule before new observations. Record all eligible decisions, rejects, locate quantity/APR, partial fills, recalls, covers and actual cash costs. The existing 50-decision/30-issuer checkpoint starts review; it does not prove profitability.
6. Complete the framework earnings-quality, cash/financing, operating impairment, disclosure/control, valuation/payoff and catalyst/path underwriting, including contrary evidence and falsifiers. A numeric screen cannot manufacture these fields.

## Reproduction and integrity

Implementation correction: the first v3 run accidentally let rally-veto failures into covered controls. The corrected comparisons retain S7 pass and relax only the added filter. Primary strategy ledgers and thresholds were unaffected; the first run is preserved. The source hashes and correction are recorded in implementation_revision.json.

Run node _system/scripts/third_plus_fundamental_study.cjs. Protocol, source/code fingerprints, every model definition and aggregate results are archived by version. Full feature evidence and trade/daily ledgers remain in the local study directory. Original frozen study, saved screen, forward policy and SPX executor are untouched.

Validation: 3 baseline reproductions, 225 unique replays, zero sealed-holdout files opened, zero new market-data spend, zero Gateway connections. Verified-execution entries remain 0.

Sources: [framework thresholds](../../../../scripts/build_short_quant_screen.py), [backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), [SEC short-sale requirements](https://www.sec.gov/investor/pubs/regsho.htm).

Data version: 33d69eb13f5e743c147956469fd9698710101e2f963be225ee96b12b77fb14a1.
