# Every-name execution on cached and $0 data

This is an explicit one-second-bar execution sensitivity. It is not observed historical execution, a borrow-verified strategy, or proof of Rule 201 compliance. Raw licensed bars and private position ledgers remain outside the public repository.

## Coverage and outcomes

| Population | Events | Independent order attempts | Modeled fills, 60m | Modeled fills, exploratory 240m | Modeled fills, full session |
|---|---:|---:|---:|---:|---:|
| Original SSR skips | 100 | 100 | 98 | 100 | 100 |
| Every prior exclusion | 129 | 129 | 122 | 128 | 129 |
| Default signal | 170 | 170 | 155 | 166 | 169 |

Each independent opportunity is simulated without competition for issuer slots. It is a counterfactual attribution record. The account keeps three simultaneous short issuers; these independently executable opportunities cannot be summed as available account capacity. No-fill names remain no-fills, and signal failures remain failures.

## Account comparisons

$10m reference NAV, $100k initial parent ceiling, unchanged signal-anchored 20-session exit, 500ms latency, maximum $2k entry child, one working child per issuer. No margin-capacity or sleeve-risk admission gate. Covers can purchase at least one whole share even when its price exceeds the child-dollar ceiling.

| Policy | Entry window | Participation | Entries | Net marked P&L | Closing drawdown | Missing cover sessions |
|---|---:|---:|---:|---:|---:|---:|
| E0 | 30m | 5% | 24 | $11492.76 | $-28366.67 | 473 |
| E0 | 30m | 10% | 25 | $17258.87 | $-41998.07 | 473 |
| E0 | 60m | 5% | 27 | $76922.73 | $-30115.63 | 473 |
| E0 | 60m | 10% | 27 | $76016.16 | $-29641.20 | 473 |
| E0 | 240m | 5% | 21 | $30012.04 | $-38536.27 | 822 |
| E0 | 240m | 10% | 21 | $31886.84 | $-36587.82 | 822 |
| E0 | Full session | 5% | 12 | $-748.27 | $-4413.86 | 1535 |
| E0 | Full session | 10% | 12 | $211.56 | $-6632.22 | 1535 |
| E1 | 30m | 5% | 26 | $-3373.01 | $-53080.24 | 1175 |
| E1 | 30m | 10% | 44 | $-4470.39 | $-96887.96 | 695 |
| E1 | 60m | 5% | 28 | $-2319.71 | $-88747.92 | 1175 |
| E1 | 60m | 10% | 37 | $-436.17 | $-159687.70 | 853 |
| E1 | 240m | 5% | 16 | $-13746.79 | $-16802.54 | 1766 |
| E1 | 240m | 10% | 16 | $-25489.78 | $-31615.96 | 1766 |
| E1 | Full session | 5% | 11 | $-31449.01 | $-65421.42 | 2221 |
| E1 | Full session | 10% | 11 | $-45146.44 | $-70604.04 | 2221 |
| E2 | 30m | 5% | 42 | $-404.91 | $-75563.25 | 695 |
| E2 | 30m | 10% | 27 | $-6538.06 | $-128656.65 | 1175 |
| E2 | 60m | 5% | 35 | $981.11 | $-114029.25 | 853 |
| E2 | 60m | 10% | 28 | $-5783.86 | $-205761.24 | 1175 |
| E2 | 240m | 5% | 16 | $-17157.21 | $-20077.65 | 1766 |
| E2 | 240m | 10% | 16 | $-34091.59 | $-39802.61 | 1766 |
| E2 | Full session | 5% | 10 | $-34191.19 | $-68864.69 | 2221 |
| E2 | Full session | 10% | 10 | $-54543.93 | $-79707.73 | 2221 |

E0 is the matched restriction-skip control. E1 joins the modeled offer. E2 improves one modeled permitted increment. All 24 comparisons are retained for every one of the 21 frozen signals. The default remains the declared 60-minute E2/10% case. The 240-minute and full-session access extensions were added after examining first-hour no-fills and are exploratory. No parameter winner or untouched validation is claimed.

## Evidence and assumptions

- Historical usable borrow is assumed; fees use 50% APR with 150% stress.
- National-price eligibility is conditional; source venue quotes are never renamed NBBO.
- No own-order price impact is observed; add 10bp per executed side and 30bp stress.
- No new edge forecast filter; frozen signals and fixed execution deadlines decide attempts.
- Source gaps and missing covers retain liabilities and incomplete-result labels.
- Three issuer slots stay in the account model; independent opportunities are separate counterfactuals and cannot be summed as executable account capacity.
- A restricted short child receives no fill when its price is at/below the contemporaneous venue/proxy bid. Broker national-price protection is still assumed, not established by these data.
- For bars, 50% of the estimated volume at/above the working offer supplies assumed eligible fill flow; 25%/75% sensitivities are separate. This is a fraction of bar flow, not a probability of filling the parent.
- Missing quote paths use the previous completed bar close with an assumed 0.86% half spread. Current bar range/volume determine modeled execution only after submission; never entry admission.
- Fractional shorts may be covered by buying the next whole share. Full cash and fees are charged; any surplus long asset receives zero NAV credit and is reported as an uncredited reserve. No broker cash-in-lieu settlement is invented.
- The 240-minute and full-session extensions are exploratory access comparisons added after examining shorter-window no-fills. Full session ends 15 minutes before the actual close, including early closes. Report all windows; no untouched validation or optimality claim.

The source archive has 4847 event sessions: 69 with sampled quote paths and 4778 requiring the lagged-bar spread proxy. Empty queried bars are retained as zero observed flow. All new requests were quoted and refreshed at $0 before download; cumulative reserved acquisition cost is $0. No ThetaData, Gateway, broker session or sealed execution holdout was accessed.

The bar model sizes from information available before a child order, reserves cumulative and rolling past-flow capacity, then uses later bar range and volume to assign assumed fills. It never uses final-day volume to size an opening order. A uniform-within-bar price allocation and 25/50/75% capture sensitivities represent unknown buyer flow/queue. They are assumptions, not calibrated fill probabilities. Cover prices are quote/bar sensitivities; partial and unavailable covers retain obligations.

Fractional shorts can be covered through a whole-share overbuy. Full cash and commission are charged. Any surplus long asset is assigned zero NAV credit and reported as an uncredited reserve. This does not invent a cash-in-lieu broker settlement. Unresolved identities, missing prices and remaining shorts are never silently zeroed.

Primary account status: incomplete_exit_evidence. The marked result includes incomplete cover paths and cannot establish completed-strategy performance.

## Reproduce

```powershell
python _system/scripts/third_plus_execution/venue_capture.py plan --source-root <cache-repository>
python _system/scripts/third_plus_execution/venue_capture.py status --source-root <cache-repository>
python _system/scripts/third_plus_execution/venue_capture.py free-bars --source-root <cache-repository>
node _system/scripts/third_plus_execution/venue_study.cjs --source-root <cache-repository>
node _system/scripts/third_plus_execution/venue_publish.cjs
node --test _system/scripts/third_plus_execution/*.test.cjs
```

The exact source index is hash-bound and private. Public code/result hashes bind this publication. Broker behavior and borrow inventory require separate prospective confirmation; this change transmits no orders.

Publication 08ea8bc979e9061f968b973126e5ecad4912d3062ff6f2899bf5061d6b098044.
