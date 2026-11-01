# Full backtest with tradability assumed

Every signal-qualified security is assumed borrowable and accessible. This is a completed **assumption-based simulation**, using observed market data where available and explicit estimates for unknown execution, costs and exits. It does not claim that historical fills or lending terms were observed.

Market window: 2023-01-19 through 2026-10-12. Fixed $100,000 maximum position, $10 million reference account, 20 sessions including entry, 60-minute entry window, 10% participation and improved permitted offer (E2). The account retains three issuers; the independent comparison removes that capacity limit.

| Signal / scenario | Three-slot net P&L | Closing drawdown | Account entries | No-slot-limit net P&L | Independent entries |
|---|---:|---:|---:|---:|---:|
| Share growth ≥25% / Base assumptions | $53,141.43 | −$213,241.54 | 72 | $252,963.63 | 160 |
| Share growth ≥25% / Lower costs / better fills | $86,118.02 | −$212,307.78 | 72 | $307,295.77 | 160 |
| Share growth ≥25% / Higher costs / weaker fills | −$9,155.07 | −$191,490.37 | 71 | $136,424.43 | 158 |
| Third-plus only / Base assumptions | $119,774.78 | −$213,242.26 | 78 | $506,802.21 | 198 |
| Third-plus only / Lower costs / better fills | $174,143.69 | −$212,207.81 | 78 | $584,940.32 | 198 |
| Third-plus only / Higher costs / weaker fills | $100,000.72 | −$191,756.33 | 77 | $341,348.68 | 196 |

The default share-growth screen has 170 qualifying events. The base account attempts 79, enters 72, has 7 no-fills, excludes 90 for occupied slots and 1 for an already-open issuer. 1 remain open with $9.90 marked liability. Independent attempts: 170; entries: 160; no-fills: 10; open positions: 4. All 210 events remain individually auditable, including events outside the signal and not yet eligible at the cutoff.

Base account: $68,692.53 before separately charged costs; borrow $12,818.44, fees $1,357.82, locates $927.23, impact $447.61. Spread and exit premiums are embedded in fill prices. Mean entry $3,585.51, 72 partial fills. Base account excluding its best issuer: $502.54; excluding its best five: −$27,736.25.

Estimated data coverage in base account: 56 entries contain estimated quotes, 0 use proxy entry paths, 10 exits use capture/venue estimates, 23 require residual completion premiums and 45 session marks are carried. 0 entries use the $5 fallback; 0 unresolved-factor sessions. Peak modeled collateral $624,393.80; 0 closes exceed reference account equity.

## Assumptions

- Frozen 210-event cohort, 21 original signal definitions, 24 execution settings and three declared cost/fill scenarios. Signal unknowns retain their frozen classification; the all-candidate signal includes the entire cohort.
- The base keeps a $100,000 maximum short, $10 million reference equity, three concurrent issuers, entry from 09:31 for 60 minutes, 10% participation and 20 trading sessions including entry. No additional $25,000 risk cap is imposed.
- All borrow and venue access is assumed available. No loan recalls or forced margin liquidation in base; a collateral estimate of 200% of marked short value with a $2.50/share floor is reported, together with days exceeding reference equity. Excess collateral has no interest benefit; proceeds and idle cash interest are zero.
- Existing receipt-verified one-second Nasdaq bars and fresh sampled quotes take priority. Missing quotes use the preceding completed bar close with an assumed half-spread of 86 basis points in base. A tick above the bid estimates the improved offer, including under SSR; E1 joins the ask and E0 skips restricted names.
- Price-volume location within an OHLC range is assumed uniform, with 50% capture of eligible volume in base. Flat bars are handled exactly. This is an estimated fill allocation, not observed trades or queue evidence. Filled shares plus live reservations never exceed cumulative or rolling-minute participation limits.
- Children are capped at $2,000, have 500 ms acknowledgement/cancellation delay and reprice no faster than five seconds. Both sides fill at their working limit. Spread and separately charged impact/fees are included once.
- Missing or empty venue capture assumes external flow using a flat known opening price and uniform prior ADV across the session, while respecting any captured halt for that security. Unknown ADV assumes $1 million daily dollar volume. Neither final-day volume nor future closes size the morning entry. Price fallback is official open, daily open, completed prearrival bar, split-adjusted prior close, then a flagged $5 proxy.
- Cover orders begin in the last 90 minutes and stop 15 minutes before close on trading session 20; partial covers retry for at most three sessions. A missing captured cover uses that day’s observed close with estimated spread and prior-ADV flow, interpreted as a closing-price execution proxy. Any final residual closes at the observed close plus spread and 2% in base.
- When a cover price is unavailable, or a security has left Nasdaq, assume closeout at the last known split-adjusted nominal price plus spread and 10% in base. Missing marks carry that adjusted price until closeout. The separate stress case increases this premium to 50%; neither case assumes bankruptcy makes a short liability zero.
- Source-bound TNFA→QCLS continuity, venue transitions and reverse split factors apply to marks and quantities. Whole-share cover overbuy is paid for and the excess sold at an estimated bid with fees. Unresolved factors carry the last known factor and are counted.
- Borrow is charged on settled stock loans on calendar days using 102% collateral rounded up per share and APR/360; T+2 before May 28, 2024 and T+1 afterwards. Returns stop financing at cover settlement. Base APR is 50%, plus a one-time $0.01/share locate fee (minimum $5) and 10 bp impact per side. These are assumptions, not sourced historical lending rates.
- Same-day parent orders reserve slots until their windows finish, even when later unfilled. Fixed identifier order breaks ties. Positions covered later that day cannot free a morning slot. The independent all-candidate result removes slot competition and reports the concurrency and collateral it would require.
- Results stop at the frozen October 12, 2026 market cutoff. Not-yet-eligible events remain listed and immature positions remain open and marked; no future prices or exits are fabricated. Closing drawdown uses every daily mark, while the chart shows monthly changes.
- Favorable and stress assumptions are combined scenarios, not confidence bounds. All settings are retrospective comparisons. The historical-evidence audit remains separate from this authorized assumption-based simulation.

| Scenario | Borrow APR | Half-spread | Eligible capture | Impact / side | Locate / share (minimum) | Residual premium | Missing/OTC premium |
|---|---:|---:|---:|---:|---:|---:|---:|
| Base assumptions | 50% | 86 bp | 50% | 10 bp | $0.01 ($5) | 2% | 10% |
| Lower costs / better fills | 10% | 43 bp | 75% | 5 bp | $0 ($0) | 0.5% | 0% |
| Higher costs / weaker fills | 150% | 172 bp | 25% | 30 bp | $0.03 ($15) | 5% | 50% |

These scenario inputs are declared estimates, not calibrated historical lender quotes or probabilistic confidence limits. Price-volume allocation and queue capture are assumptions; fills respect modeled limits. The stress case can change admissions because its fills and exit dates differ. The historical-evidence audit remains available separately. No ThetaData, Gateway, live broker connection, paid acquisition or sealed holdout is used.

## Reference methodology

- [IBKR fixed commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
- [IBKR short sale cost methodology](https://www.interactivebrokers.com/en/pricing/short-sale-cost.php)

## Offline reproduction

```powershell
node _system/scripts/third_plus_execution/assumed_study.cjs --source-root <repository-with-existing-cache>
node _system/scripts/third_plus_execution/assumed_publish.cjs
node _system/scripts/third_plus_execution/assumed_study.cjs --check
node _system/scripts/third_plus_execution/assumed_publish.cjs --check
```

Archive index SHA-256: 4a92d49764b796da191b00a4ce52425f77994c4a9aec5435d90fc1c44fe335d0. It binds session receipt hashes and cached input files. Source code and frozen signal inputs are bound by the publication source hashes. No market data download is performed.

Publication ce3477a5bd209c93759fe2685d20eec41c55f0f8817722526ecd21ded5111fd4.
