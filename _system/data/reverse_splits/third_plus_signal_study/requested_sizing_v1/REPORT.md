# Requested $100,000 reverse-split sizing study

This is a separate sizing sensitivity on the existing third-plus cohort. Original frozen results and statistical decisions are preserved. Results are hypothetical and marked, on already explored history.

## Assumptions

| Setting | Requested case |
| --- | --- |
| Reference account | $10,000,000; accounting denominator, without broker funding/margin simulation |
| Initial cap per position | $100,000; replaces 0.25%-of-equity name allowance |
| Margin-capacity and sleeve-reserve gates | Removed |
| Prior volume | 10% of prior 20 completed sessions, in entry-day share units |
| Entry-day volume | 10% of final recorded volume; hindsight quantity input |
| Exit volume | 10% on each eligible cover session |
| Concurrent positions | Three; unchanged |
| Minimum follow-up / common maturity | Removed; recent positions stay open and marked |
| Planned exit | 20 sessions; unchanged |
| SSR route | Strict skips; unsupported capture proxy is separate |
| Costs | Frozen base: 50% borrow APR, 1.72% execution rate and dated fees |
| Sliced execution | Not simulated; no observed child orders, queue, impact curve or fills |

## Comparable results

Default signal: third-plus AND S7 rally veto AND common-share growth ≥25%. 2023-01-19 to 2026-10-12; 46 months including idle months.

| Case | Entries | Mean size | Net marked P&L | Closing drawdown | Historical monthly mean | Open |
| --- | --- | --- | --- | --- | --- | --- |
| Original $1m reference | 40 | $749.24 | $7,997.10 | -$2,455.39 | $173.85 | 2 |
| Requested · $100k cap / $10m account | 41 | $11,388.19 | $102,545.83 | -$77,572.39 | $2,229.26 | 3 |
| Requested · prior-volume entry sizing | 48 | $16,591.83 | $221,552.25 | -$64,891.07 | $4,816.35 | 2 |
| Requested · SSR capture sensitivity | 30 | $13,373.66 | $83,862.45 | -$52,773.62 | $1,823.10 | 3 |

Requested median exposure: $2,537.29. 2 entries reach 95% of the $100k target. Total marked P&L is 1.025% of reference NAV across the full window. Monthly means are not income forecasts. Closing drawdown misses intraday and gap risk.

## Admissions and incomplete follow-up

| First terminal state | Events |
| --- | --- |
| selected | 170 |
| common_maturity_excluded | 0 |
| missing_session | 0 |
| missing_entry | 0 |
| missing_liquidity | 1 |
| overlap | 0 |
| zero_capacity | 0 |
| entered | 41 |
| ssr_rejected | 100 |
| risk_capacity | 28 |
| verified_evidence_missing | 0 |

No common maturity exclusions remain. KUST (October 1, 2026 split, intended October 6 entry) is newly admitted and unfinished at the October 12 cutoff. The other three formerly immature candidates are SSR-restricted. A missing session or price is still missing; no future exit is invented. Tiny unresolved/fractional balances continue occupying one of three slots. The SSR proxy can produce fewer entries because early admitted names can block later ones.

## Every signal under requested sizing

| Rule | Candidates | Entries / issuers | Net marked P&L | Closing drawdown | Open |
| --- | --- | --- | --- | --- | --- |
| Third-plus only | 210 | 42 / 34 | -$140,775.91 | -$255,430.83 | 3 |
| Third-plus + rally veto | 190 | 42 / 34 | $96,404.89 | -$83,713.33 | 3 |
| Existing score ≥60 | 47 | 16 / 14 | $24,158.81 | -$5,389.10 | 1 |
| Negative operating cash flow | 167 | 43 / 40 | $27,791.36 | -$154,430.05 | 2 |
| Reported runway <6 months | 123 | 31 / 29 | -$42,990.79 | -$206,888.87 | 2 |
| Share growth ≥25% | 170 | 41 / 34 | $102,545.83 | -$77,572.39 | 3 |
| Operating loss | 165 | 43 / 40 | $33,737.54 | -$154,430.05 | 2 |
| Revenue decline ≥15% | 43 | 16 / 14 | $42,795.04 | -$5,389.10 | 1 |
| Operating margin decline ≥8pp | 55 | 20 / 17 | $39,138.26 | -$6,365.50 | 1 |
| Accrual ratio ≥10% | 23 | 10 / 9 | $14,631.79 | -$4,169.92 | 0 |
| Profit without operating cash | 2 | 0 / 0 | $0.00 | $0.00 | 0 |
| Negative equity | 43 | 15 / 9 | -$6,839.65 | -$158,099.06 | 1 |
| Framework debt-maturity distress | 0 | 0 / 0 | $0.00 | $0.00 | 0 |
| Previous split within 180 days | 70 | 29 / 21 | $84,925.95 | -$21,580.84 | 1 |
| Weak split-day close | 54 | 10 / 10 | $18,496.99 | -$21,580.84 | 1 |
| Prior 20-session return ≤−20% | 148 | 34 / 28 | $49,305.05 | -$74,627.29 | 2 |
| Cash burn + dilution | 149 | 36 / 34 | $101,325.65 | -$78,444.37 | 2 |
| Short reported runway + dilution | 107 | 30 / 29 | -$36,276.22 | -$200,648.43 | 2 |
| Operating loss + dilution | 147 | 36 / 34 | $103,754.85 | -$78,444.37 | 3 |
| Short runway + dilution + operating loss | 107 | 30 / 29 | -$36,276.22 | -$200,648.43 | 2 |
| Short runway + dilution + revenue decline | 26 | 9 / 8 | $14,381.40 | -$5,389.10 | 1 |

The original 19 incremental statistical claims apply to the old primary, not these new account scenarios. No rule is declared optimal or validated by this sizing rerun.

## SSR meaning and all flagged securities

Rule 201 generally restricts short executions at or below the national best bid after a qualifying 10% decline, through the following trading day. A compliant order above the bid may fill; borrowing is a separate requirement. A reverse split is not itself the trigger. This is separate from threshold-security lists and broker locate rejection.

All 97 original default exclusions across 63 tickers match same-day cached XNAS.ITCH restricted status at or before 09:30 ET. This compares the same vendor-normalized source feed and date-valid symbology; exact trigger trades and independent broker permission were not reconstructed.

| Ticker | Events | Split date → restricted intended opening |
| --- | --- | --- |
| ABTC | 1 | 2026-07-06 → 2026-07-07 |
| ACON | 1 | 2025-03-28 → 2025-03-31 |
| ADTX | 5 | 2024-10-02 → 2024-10-04; 2025-03-17 → 2025-03-18; 2025-11-03 → 2025-11-04; 2026-03-09 → 2026-03-10; 2026-05-18 → 2026-05-19 |
| ALLR | 2 | 2024-04-09 → 2024-04-10; 2024-09-11 → 2024-09-12 |
| ALZN | 1 | 2025-05-12 → 2025-05-13 |
| APDN | 1 | 2025-03-14 → 2025-03-17 |
| APVO | 1 | 2025-05-27 → 2025-05-28 |
| AREB | 2 | 2025-10-03 → 2025-10-06; 2026-02-02 → 2026-02-03 |
| AUUD | 1 | 2026-04-01 → 2026-04-06 |
| BINI | 1 | 2025-09-22 → 2025-09-24 |
| BJDX | 1 | 2026-01-29 → 2026-02-02 |
| BNZI | 1 | 2026-05-08 → 2026-05-11 |
| BOXL | 1 | 2025-12-23 → 2025-12-24 |
| CDT | 2 | 2025-10-13 → 2025-10-14; 2026-03-27 → 2026-03-30 |
| CETX | 2 | 2024-11-26 → 2024-11-27; 2025-09-29 → 2025-09-30 |
| CMCT | 2 | 2026-03-26 → 2026-03-27; 2026-04-20 → 2026-04-23 |
| CNSP | 1 | 2025-02-21 → 2025-02-24 |
| CRKN | 1 | 2025-01-30 → 2025-01-31 |
| CYCC | 1 | 2025-07-07 → 2025-07-08 |
| DBGI | 2 | 2024-12-13 → 2024-12-16; 2026-07-24 → 2026-07-27 |
| EDBL | 3 | 2025-03-03 → 2025-03-04; 2026-02-03 → 2026-02-04; 2026-07-13 → 2026-07-14 |
| ELAB | 2 | 2025-09-02 → 2025-09-05; 2026-01-06 → 2026-01-07 |
| ENVB | 1 | 2025-10-28 → 2025-10-29 |
| FTFT | 2 | 2026-01-20 → 2026-01-21; 2026-08-31 → 2026-09-01 |
| GNLN | 3 | 2024-08-05 → 2024-08-06; 2025-06-27 → 2025-06-30; 2026-04-06 → 2026-04-07 |
| GNPX | 1 | 2026-07-16 → 2026-07-17 |
| GOVX | 1 | 2026-01-12 → 2026-01-13 |
| GPUS | 1 | 2024-11-25 → 2024-11-26 |
| GRI | 2 | 2024-06-18 → 2024-06-20; 2025-02-24 → 2025-02-25 |
| IPDN | 1 | 2026-09-14 → 2026-09-15 |
| JAGX | 4 | 2023-01-23 → 2023-01-24; 2024-05-23 → 2024-05-24; 2025-03-24 → 2025-03-25; 2026-04-30 → 2026-05-01 |
| KITT | 1 | 2026-04-21 → 2026-04-22 |
| KUST | 1 | 2026-04-22 → 2026-04-23 |
| MBRX | 1 | 2025-12-01 → 2025-12-02 |
| MNTS | 1 | 2025-12-18 → 2025-12-19 |
| MULN | 4 | 2024-09-17 → 2024-09-23; 2025-02-18 → 2025-02-19; 2025-04-11 → 2025-04-14; 2025-06-02 → 2025-06-03 |
| NDRA | 1 | 2024-11-07 → 2024-11-08 |
| NUWE | 1 | 2025-07-07 → 2025-07-08 |
| NVVE | 2 | 2025-12-15 → 2025-12-16; 2026-07-06 → 2026-07-07 |
| NXTT | 1 | 2026-08-10 → 2026-08-11 |
| ONCO | 1 | 2026-03-25 → 2026-03-30 |
| PBLA | 1 | 2024-01-18 → 2024-01-19 |
| PIXY | 2 | 2023-10-16 → 2023-10-17; 2024-10-14 → 2024-10-15 |
| PSTV | 1 | 2026-04-02 → 2026-04-06 |
| REVB | 2 | 2025-01-28 → 2025-01-31; 2026-01-28 → 2026-01-30 |
| RNAZ | 1 | 2025-05-15 → 2025-05-16 |
| RSLS | 2 | 2024-09-23 → 2024-09-25; 2025-05-09 → 2025-05-12 |
| SEGG | 1 | 2026-08-03 → 2026-08-04 |
| SHPH | 1 | 2026-06-11 → 2026-06-12 |
| SLRX | 1 | 2025-08-18 → 2025-08-19 |
| SONM | 1 | 2025-10-27 → 2025-10-28 |
| TNFA | 1 | 2025-09-02 → 2025-09-03 |
| TNXP | 1 | 2024-06-10 → 2024-06-11 |
| TRNR | 1 | 2026-02-24 → 2026-02-26 |
| VINO | 1 | 2024-05-01 → 2024-05-02 |
| VLCN | 2 | 2024-06-07 → 2024-06-10; 2024-11-11 → 2024-11-12 |
| VTAK | 1 | 2025-08-15 → 2025-08-18 |
| WHLR | 6 | 2024-09-20 → 2024-09-23; 2024-11-19 → 2024-11-20; 2025-01-28 → 2025-01-29; 2025-03-27 → 2025-03-28; 2026-07-28 → 2026-07-29; 2026-08-27 → 2026-08-28 |
| WINT | 1 | 2025-02-21 → 2025-02-24 |
| WISA | 1 | 2024-04-15 → 2024-04-16 |
| WKHS | 1 | 2025-12-08 → 2025-12-09 |
| XELA | 1 | 2023-05-15 → 2023-05-16 |
| XXII | 2 | 2024-12-17 → 2024-12-18; 2025-06-20 → 2025-06-23 |

Across all 210 events, 208 stored states match raw records. FWBI (December 18, 2023) has a recoverable raw restricted flag but a missing stored state; frozen selections stay preserved. DFLI has no original eligible entry session. No paid data were downloaded.

## Remaining execution work

A sliced-entry model needs timestamped participation budgets, quotes/trades, borrow approvals, compliant price limits, child-order fills, cancellation/expiry rules, partial-entry accounting, recalls and changing costs. Raising the cap does not establish an optimal execution schedule. The prior-volume-only sensitivity avoids final-day entry quantity information but still assumes an opening fill. The execution percentage is unchanged as size increases; actual impact is unverified.

Broker house margin remains a real constraint even when removed from this sensitivity. No live settings, Gateway connections, schedules or order permissions changed. Concurrent SPX exposure and margin were not replayed. Stale identities, fractional liabilities, financing-adjusted cash and underwriting gaps remain.

## Reproducibility

Scenario 5adf70d04d9cb68fe09c66d61bd4384b5f34db6df663d9059f0bf82cc7aef26b; parent 33d69eb13f5e743c147956469fd9698710101e2f963be225ee96b12b77fb14a1. The new engine first reproduces position records and daily accounting for all 21 frozen primary models, then runs 63 requested scenarios. Source input fingerprints are checked, and the original 189 model audits remain available. Every new funnel and monthly total reconciles. Raw prices/status messages and per-event returns remain local.

Use the requested-sizing and read-only SSR reproduction commands in the parent README, then rebuild the dashboard and run the report generator.

References: [SEC Rule 201 FAQ](https://www.sec.gov/files/divisions/marketreg/rule201faq.htm); [Nasdaq TotalView-ITCH §1.2.3](https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHspecification.pdf).
