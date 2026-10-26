# SSR execution backtest implementation and data result

The replay engine and comparison runner are implemented. The current audited caches do not support an execution-realistic performance estimate. Missing history is not a zero fill, zero cost, or zero profit. No optimal execution method or achievable monthly profit is established.

The existing $102,546 requested-sizing result remains a hypothetical opening-fill diagnostic. It does not become an SSR execution result through this change. No broker orders, Gateway connections, paid downloads or sealed holdout reads occurred.

## What was run

All 21 frozen signal arms × four policies × two windows × two participation rates × three order-latency assumptions × two borrow-evidence modes = **2,016 model definitions**. The declared primary comparison family remains 12 methods/settings per signal arm, with four matched controls at 500ms and conditional-on-borrow evidence. This is a matrix evaluation with evidence gates, not 2,016 successfully populated performance backtests.

| Audit population | Events | Matched prepared files | Complete sampled 60m grids | Qualified event replays | Archived borrow approvals |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entire cohort | 210 | 67 | 63 | 0 | 0 |
| Default signals | 170 | 57 | 53 | 0 | 0 |
| Original requested SSR skips | 100 | 31 | 28 | 0 | 0 |

A complete sampled grid is a one-second venue quote/bar path, not consolidated NBBO, a timestamped aggressor/queue history, confirmed borrow or observed execution. This audit inspected the two named reuse indexes and matched prepared arrays. Raw Databento schema directories and expansion CSV headers were also inspected; this is not a reconstruction of every raw event. The prepared arrays and indexes are hash-bound; their full upstream raw records have not all been independently reconstructed.

## Primary comparison matrix: default dilution signal

| Policy | Window | Participation | Ready entries / selected | Result |
| --- | ---: | ---: | ---: | --- |
| E0 | 30m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E1 | 30m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E2 | 30m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E3 | 30m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E0 | 30m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E1 | 30m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E2 | 30m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E3 | 30m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E0 | 60m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E1 | 60m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E2 | 60m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E3 | 60m | 5% | 0 / 170 | Not estimable: execution evidence missing |
| E0 | 60m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E1 | 60m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E2 | 60m | 10% | 0 / 170 | Not estimable: execution evidence missing |
| E3 | 60m | 10% | 0 / 170 | Not estimable: execution evidence missing |

Every incomplete model withholds P&L, fill rate, average executed dollars, drawdown, uncertainty and rankings. A selected-sample backtest would give a misleading portfolio result: unknown earlier shorts could occupy the three issuer slots and alter later admissions. Controls use the same clear-status offer policy, clocks, costs and limits. The old opening-fill case is separate.

## What recorded flow can tell us

These are recorded venue-flow budgeting diagnostics for the 31 matched original SSR skips, capped at $100k and valued at the first valid sampled midpoint. They do not test the legal price, accessible buyer flow, queue, borrow, per-child costs, impact or covers. They are not simulated position sizes and are not a bound on consolidated US trading capacity. Four matched selected paths have incomplete sampled grids, so observed flow can be incomplete too.

| Window | Participation | Matched events | Mean recorded-flow dollar budget | Median | 90th percentile | Recorded budget reaches $100k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30m | 5% | 31 | $7,985 | $2,075 | $8,656 | 1 |
| 30m | 10% | 31 | $12,413 | $4,150 | $17,324 | 2 |
| 60m | 5% | 31 | $11,303 | $3,413 | $16,807 | 1 |
| 60m | 10% | 31 | $17,412 | $6,832 | $33,619 | 3 |

## Mechanics implemented

- Start on the original eligible session at 09:31 ET. Test 30/60-minute windows, 5/10% participation and 100/500/2,000ms order latency. The deadline never restarts after a halt, delayed borrow or reject.
- Preserve the $10m NAV, $100k initial share budget, three concurrent issuer slots, no margin/sleeve admission cap and no minimum maturity requirement. Fix parent shares at floor($100k / valid arrival midpoint); record actual proceeds separately and cap their cumulative amount at $100k.
- Submit one child per issuer, at most $2k, with a five-second discretionary repricing interval. Reserve parent, borrow and observed-flow quantity through pending cancellation. Apply a rolling 60-second observed-flow limit as well as the cumulative cap. The older prior-ADV entry ceiling is replaced by observed intraday flow; incomplete prior liquidity alone is not an admission veto in this method.
- E1 joins the displayed offer; E2 improves one dated permitted increment above NBB when possible; E3 requires an attested native route. All use the same E1 offer policy when status is clear. E0 skips restricted entries with otherwise matched rules.
- Qualifying initially displayed orders preserve their price/priority on a bid rise only when the declared route supports that treatment. No client-selected short-exempt flag is introduced. Dated increments and route policy come from the input, not a universal penny assumption.
- Require later chosen-venue buyer-initiated eligible trade flow to consume queue ahead before partial passive fills. Unknown aggressor, auctions, duplicates and own prints do not generate fills. No bar-touch fill, cancellation credit or repeated use of unchanged displayed cover depth.
- Market/source gaps, unknown restriction, halt, expired borrow, edge failure and the fixed deadline cancel outstanding orders. Known borrow expiry is canceled ahead of its acknowledgement latency. Borrow revocation/expiry race fills remain liabilities and invalidate a borrow-complete evidence claim. Late fills remain in positions until acknowledged cancellation; a canceled request does not release reservations early.
- Keep conditional-on-borrow and archived-approval models separate. Approved quantity and expiry constrain the latter. Locate/pre-borrow expense can remain on an admitted no-fill decision.
- Charge the dated modeled fixed commission/SEC/TAF/CAT schedule once per occupied child; use 50% annual borrow and a 150% borrow stress. No duplicate flat 1.72% execution debit is added to replayed prices. Actual broker financing, venue rebates, taxes and operational costs remain unverified.
- Keep the original 20-session exit anchor. Attempt causal partial buybacks 90–15 minutes before close. Do not invent a final-print cover: retain residual/fractional, identity and stale-mark liabilities and retry on later observed sessions. Carry through known settlement/loan return; mark recent immature positions.
- Reconcile cash against marked liabilities, monthly changes and per-position P&L. Missing exit evidence blocks a complete-strategy claim. Issuer and calendar intervals and Holm-adjusted comparisons are computed only for complete matched paths, with a 12-comparison family per rule and an additional 252-comparison family across all exploratory signal arms; no winner is selected automatically.

## Data contract and exact gaps

The private archive index lives at local/third_plus_signal_study/ssr_execution_v1/archive/index.local.json beneath the existing reverse-split cache. Each file is SHA-256 checked, identity joined and rejected if outside the archive or marked synthetic. The input contract is documented in DATA_CONTRACT.md. Source attestations establish what the file claims to contain, not independent certification or live fill calibration.

209 scheduled entry sessions require qualified capture; 203 planned exits fall within the current calendar. Recent exits beyond the cutoff remain immature. A private requests.local.json enumerates all 210 events, dates, required schemas, exit windows and residual-cover follow-ups. Positive-cost acquisition is not authorized. Current quotes are unknown; no old price quote is reused.

Missing inputs include source-available edge forecasts, exact share/security identity and dated calendar/grid/route rules, full continuous consolidated NBBO, venue book and eligible trade history, dynamic restrictions/halts and receipt clocks, and enough exit/follow-up data. Borrow-verified models additionally need archived usable approvals, fees, expiry and recall terms. Native repricing additionally needs verified account/security/route behavior. Current borrow inventory does not establish historical locates.

The dashboard publishes all 210 categorical coverage decisions, all 21 arms, the full 96-definition-per-arm matrix, the 12 primary comparisons plus four controls, latency/borrow selectors, gap CSV and aggregate flow diagnostics. The existing opening-fill sensitivities remain separately labeled. No raw licensed prices, volumes, quantities, per-event returns or private source paths are published.

## Reproduce

~~~powershell
python _system/scripts/third_plus_execution/cache_audit.py --source-root <cache-repository> --project-root . --output _system/data/reverse_splits/third_plus_signal_study/ssr_execution_v1/cache_audit.json
node _system/scripts/third_plus_execution/study.cjs --source-root <cache-repository>
node _system/scripts/third_plus_execution/publish.cjs
node --test _system/scripts/third_plus_execution/*.test.cjs
node _system/scripts/third_plus_execution/publish.cjs --check
~~~

With an absent archive, the runner completes the entire evidence matrix and emits unavailable performance. Populate only qualified historical inputs to obtain conditional execution results. Synthetic fixtures test accounting and event behavior; they are never strategy evidence. Live implementation and order authorization are outside this change; the protected SPX Gateway is untouched.

Sources: [Rule 201](https://www.ecfr.gov/current/title-17/chapter-II/part-242/subject-group-ECFR1607681c7b4f78d/section-242.201), [Nasdaq Equity 4, 4763](https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-equity-4), and the prior SSR_EXECUTION_PLAN.md. Rechecked October 25, 2026 ET.

Publication d80d02e6ee9e6476b94bd48f121a21aab5ad1b3f7d077a01097ebe4adef86be8.
