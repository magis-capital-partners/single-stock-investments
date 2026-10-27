# Corrected every-candidate execution audit

Historical executable account performance is **not established**. The former marked P&L and drawdown are retired, not restated as zero. Available bars and sampled venue quotes cannot establish historical usable borrow, national-price eligibility, queue priority, broker margin or complete loan/exit outcomes. No winning parameter or live strategy is selected.

## Repaired mechanics

- No synthetic bid/ask or fixed 1.72% spread replaces missing quotes. Missing, stale or partial quote capture is an evidence gap, not a no-fill.
- No uniform within-bar volume distribution. Optional bar diagnostics require fresh observed quotes and a whole bar strictly beyond the resting limit after acknowledgement; queue and capture remain unverified.
- Both buy and sell fills respect the working limit. Pending cancellations keep reservations. Bar data cannot establish observed fills or national-price compliance.
- Verified account mode requires archived usable borrow quantity, rate and expiry, loan recall terms, consolidated national quotes, venue book/trades and dated margin evidence. Unknown values remain unavailable; no fixed borrow APR is a historical observation.
- Dated issuer-bound primary filings follow TNFA into QCLS and distinguish DBGI OTC trading, its later Nasdaq return, and PIXY suspension. No delisting implies a zero liability or an assumed broker release.
- Account equity becomes unknown at the first unresolved live-position price or execution gap. Later admissions, P&L and drawdown are withheld, rather than running indefinitely on frozen marks and occupied slots.
- The three-issuer limit and explicit account risk budgets apply to the account. Independent entry diagnostics omit slot competition and cannot be summed as executable account capacity.
- Morning account equity and pending parent reservations determine admission. Future no-fills, proceeds and closing marks cannot change an earlier morning decision. Paid fractional-cover surplus remains a marked long asset.
- A separate 20-session official-auction price benchmark follows verified symbol continuity and split factors. It excludes costs and execution and reports missing/immature outcomes; complete-price-case averages are selected-sample diagnostics, not strategy returns.
- The 21 signals and 24 settings are retrospective comparisons, not an untouched validation set. No best historical setting is promoted.
- Historical borrow, OTC executions and actual broker settlements cannot be reconstructed by inventing observations. No broker, ThetaData or paid acquisition is used.

## Entire cohort remains visible

210 original events; 170 pass the default saved rally veto plus share-growth signal. All 21 frozen signals retain 24 account definitions. Required evidence is checked before calculating portfolio admissions and returns. Independent bar entry diagnostics do not substitute for those account results.

| Missing requirement in default account | Candidates |
|---|---:|
| borrow_history | 170 |
| dated_borrow_costs | 170 |
| dated_margin_costs | 170 |
| loan_terms | 170 |
| margin_history | 170 |
| national_prices | 170 |
| qualified_capture_missing | 170 |
| queue_and_trade_history | 170 |
| settlement_evidence | 170 |

The archive includes 4847 event sessions, 69 with sampled quotes and 4778 without. Missing source/symbol capture is preserved as a gap, not an empty observed market. Receipt/index/source hashes bind the local inputs. Raw licensed prices and position quantities remain private.

## Official-price benchmark

This is a separate price-only diagnostic, not executable P&L. 157 / 170 selected events have both official auction prices and resolved split/security continuity; 13 remain missing or immature. Complete cases are a selected subset.

| Outcome coverage | Events |
|---|---:|
| observed_price_pair | 157 |
| venue_exit | 2 |
| missing_official_price | 7 |
| immature | 4 |

## Security lifecycle sources

- TNFA (cik/1321834), 2025-09-25: symbol_change → QCLS. [Primary filing](https://www.sec.gov/Archives/edgar/data/1321834/000149315225015774/form8-k.htm).
- DBGI (cik/1668010), 2024-12-18: venue_exit → OTC. [Primary filing](https://www.sec.gov/Archives/edgar/data/1668010/000149315225003666/forms-1.htm).
- PIXY (cik/1675634), 2024-10-28: venue_exit → suspended_bankruptcy. [Primary filing](https://www.sec.gov/Archives/edgar/data/1675634/000147793224006691/pixy_8k.htm).
- DBGI (cik/1668010), 2025-08-20: venue_resume. [Primary filing](https://www.sec.gov/Archives/edgar/data/1668010/000149315225019083/forms-1.htm).

## Risk and validation

The hypothetical account retains three issuers and adds declared budgets: 0.25% equity per issuer, 1% sleeve gross, a 2% loss budget under a +200% squeeze, and 80% margin usage. These are model limits; verified mode still requires the historical broker schedule. A risk breach has no assumed successful liquidation. The 21 signals and 24 settings remain retrospective; no untouched validation claim is made.

Regression tests cover buy-limit violations, missing quotes, nonuniform bar paths, symbol transitions, split units, venue changes, stale-price gaps, evidence gating, fees and publication consistency. Passing mechanics tests does not establish historical profitability. Missing historical borrow, OTC executions or broker settlement records remain explicit unresolved inputs. No ThetaData, IB Gateway, broker session, paid acquisition or sealed holdout was accessed.

## Reproduce offline

```powershell
python _system/scripts/third_plus_execution/venue_capture.py normalize-free --source-root <cache-repository>
node _system/scripts/third_plus_execution/venue_study.cjs --source-root <cache-repository>
node _system/scripts/third_plus_execution/venue_publish.cjs
node --test _system/scripts/third_plus_execution/*.test.cjs
```

The normalizer uses existing receipt-verified files only and performs no downloads. Missing successor captures stay missing even when successor daily benchmark prices exist. Qualified replay inputs and historical lending/settlement evidence are required to produce an executable account estimate.

Publication 8e7f46d5c25ae69289850523469e3f7a461e5a3f763f70ea0de08a6b2157682a.
