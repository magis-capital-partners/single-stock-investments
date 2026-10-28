# Full-size announcement-day reverse-split backtest

**Backtest: $100,000 target per company. Future live pilot: one initial share
per company.** The historical study contains no one-share sizing cases.
Announcements through 2026-10-08; market data through 2026-10-12;
start 2023-01-01. Research only; all qualifying names are assumed accessible
and borrowable. No broker/Gateway connection, Theta access or paid acquisition.

The protocol was registered 2026-10-28T14:13:20.611Z, before this broader
run's outcomes. Earlier post-effective publications remain frozen. These
comparisons are exploratory and are not an untouched holdout.

## Full-size results by split history

The source-covered universe has **1028**
announcements across **723** issuers.
first: 669; second: 208; third_plus: 151.
Split number is determined using prior completed actions already known at the
announcement, a lower bound on lifetime history. The current action cannot
count as its own predecessor.

The unfiltered, three-slot, base-cost announcement book has **135**
entries, **-$180,017.28** net marked profit and **-$251,572.71**
worst daily closing drawdown. **2** positions remain open.
Actual mean entry is **$3,415.75**, not $100,000: participation,
flow capture and partial fills constrain the order target. Independent-opportunity
cases omit competition for slots; they are not a funded account result.

All following primary rows enter from the captured announcement clock and hold
20 sessions from entry. Fundamental and price filters use information available
at that announcement rather than the later effective split date.

| Split history | Filter | Pass / covered | Entries | Net marked P&L | Closing drawdown | Mean entry | Still open | Without best five |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | all | 1028/1028 | 135 | -$180,017.28 | -$251,572.71 | $3,415.75 | 2 | -$192,865.58 |
| all | rally | 863/899 | 132 | -$115,949.55 | -$234,032.03 | $4,255.48 | 1 | -$169,343.40 |
| all | rally_burn | 624/719 | 128 | -$319,445.83 | -$474,100.31 | $3,322.25 | 2 | -$366,538.19 |
| all | burn_weak_prior | 243/719 | 108 | $11,492.75 | -$54,097.86 | $2,740.34 | 2 | -$32,960.82 |
| first | all | 669/669 | 132 | -$296,472.08 | -$323,537.39 | $6,184.67 | 3 | -$313,002.04 |
| first | rally | 543/563 | 129 | -$310,061.11 | -$357,740.90 | $4,831.85 | 3 | -$325,814.22 |
| first | rally_burn | 355/419 | 117 | -$12,633.77 | -$53,869.20 | $4,273.31 | 3 | -$60,814.59 |
| first | burn_weak_prior | 141/419 | 87 | $1,663.69 | -$54,146.74 | $3,122.29 | 1 | -$42,195.32 |
| second | all | 208/208 | 103 | $46,057.40 | -$4,746.72 | $1,459.70 | 3 | $18,587.98 |
| second | rally | 185/194 | 99 | $35,033.94 | -$4,746.72 | $1,171.42 | 2 | $8,757.20 |
| second | rally_burn | 150/166 | 93 | $34,748.41 | -$4,746.72 | $1,086.08 | 2 | $8,471.67 |
| second | burn_weak_prior | 59/166 | 49 | $16,716.56 | -$12,722.14 | $1,229.02 | 0 | -$3,411.96 |
| third_plus | all | 151/151 | 73 | $109,951.92 | -$6,075.54 | $3,250.61 | 2 | $6,056.27 |
| third_plus | rally | 135/142 | 67 | $85,597.02 | -$11,305.11 | $2,681.60 | 2 | $468.89 |
| third_plus | rally_burn | 119/134 | 63 | $80,500.11 | -$12,002.82 | $3,113.59 | 2 | -$1,400.17 |
| third_plus | burn_weak_prior | 43/134 | 35 | $8,717.40 | -$3,101.24 | $1,108.46 | 2 | -$1,455.41 |

Each history/filter row is a separately replayed portfolio with its own three
slots. The combined book competes for capacity differently; subgroup profits
must not be added to reconstruct the combined account.

### Attempt every candidate without competition for slots

Independent opportunities, full dollar target, base costs and 20 sessions from
entry. These diagnostics retain modeled partial fills but remove the three-slot
and same-issuer overlap restrictions. They are not a capital-constrained account.

| History | Filter | Entries | Net marked P&L | Mean entry | Still open |
| --- | --- | --- | --- | --- | --- |
| all | all | 972 | -$988,835.48 | $3,760.00 | 19 |
| all | burn_dilution | 259 | $163,176.53 | $2,002.84 | 5 |
| first | all | 628 | -$1,159,070.52 | $4,815.76 | 8 |
| first | burn_dilution | 83 | $52,361.21 | $2,544.06 | 1 |
| second | all | 199 | $66,944.45 | $1,457.49 | 4 |
| second | burn_dilution | 82 | $28,138.63 | $1,189.76 | 0 |
| third_plus | all | 145 | $103,290.59 | $2,347.49 | 7 |
| third_plus | burn_dilution | 94 | $82,676.69 | $2,234.25 | 4 |

## Every fundamental filter and predefined combination

Each cell: **passing / feature-covered candidates; entries; net marked P&L**.
Base costs, three slots, immediate regular-session announcement attempt, 20
sessions from entry and the full dollar target. The dashboard also provides
same-feature-coverage controls: both passing and failing companies where the
required inputs exist, with identical execution and capacity. Unknowns do not
pass. Zero entries are not evidence of zero return or of a bad stock-selection rule.

| Announcement-time screen | First documented | Second documented | Third or later |
| --- | --- | --- | --- |
| Every candidate | 669/669; 132 entries; -$296,472.08 | 208/208; 103 entries; $46,057.40 | 151/151; 73 entries; $109,951.92 |
| No 50% daily rally | 543/563; 129 entries; -$310,061.11 | 185/194; 99 entries; $35,033.94 | 135/142; 67 entries; $85,597.02 |
| As-of financial score ≥60 | 124/354; 87 entries; -$36,602.18 | 38/116; 34 entries; $14,396.71 | 40/91; 35 entries; $32,271.71 |
| Rally veto + As-of financial score ≥60 | 99/294; 76 entries; $1,646.46 | 34/107; 32 entries; $11,975.12 | 35/85; 32 entries; $2,961.13 |
| Legacy financial score ≥60 | 143/379; 91 entries; -$21,372.88 | 48/130; 43 entries; $25,677.50 | 46/101; 39 entries; $37,042.76 |
| Rally veto + Legacy financial score ≥60 | 112/313; 82 entries; $8,384.43 | 43/119; 40 entries; $23,292.33 | 40/95; 35 entries; $6,350.15 |
| Cash pressure incl. identified financing | 248/512; 110 entries; -$174,597.81 | 116/178; 81 entries; $36,703.80 | 86/123; 56 entries; $41,695.12 |
| Rally veto + Cash pressure incl. identified financing | 194/419; 105 entries; -$127,983.54 | 102/165; 77 entries; $30,721.83 | 77/116; 53 entries; $83,354.03 |
| Recent completed equity-linked financing | 0/0; 0 entries; $0.00 | 1/1; 1 entries; $80.95 | 15/15; 14 entries; $1,240.91 |
| Rally veto + Recent completed equity-linked financing | 0/0; 0 entries; $0.00 | 1/1; 1 entries; $80.95 | 13/13; 12 entries; $2,596.87 |
| Previous split within 180 days | 0/0; 0 entries; $0.00 | 26/208; 25 entries; $13,831.66 | 55/151; 41 entries; $88,927.91 |
| Rally veto + Previous split within 180 days | 0/0; 0 entries; $0.00 | 26/194; 25 entries; $13,831.66 | 49/142; 38 entries; $82,034.36 |
| Share growth ≥25% | 139/470; 92 entries; -$56,872.39 | 114/170; 75 entries; $46,487.95 | 118/133; 66 entries; $88,880.55 |
| Rally veto + Share growth ≥25% | 113/383; 82 entries; -$43,285.43 | 99/156; 68 entries; $36,306.54 | 107/127; 61 entries; $84,132.11 |
| Original weak split-day close · unavailable before split | 11/55; 8 entries; -$15,625.65 | 6/19; 6 entries; $619.33 | 4/21; 4 entries; $8,141.42 |
| Rally veto + Original weak split-day close · unavailable before split | 9/52; 6 entries; -$1,907.68 | 6/18; 6 entries; $619.33 | 4/20; 4 entries; $8,141.42 |
| Prior 20-session return ≤−20% | 235/561; 107 entries; -$9,346.07 | 107/194; 69 entries; $28,297.29 | 88/142; 52 entries; $37,259.79 |
| Rally veto + Prior 20-session return ≤−20% | 232/561; 107 entries; -$9,936.01 | 103/194; 67 entries; $25,822.94 | 84/142; 50 entries; $14,983.63 |
| Reported runway <6 months | 248/512; 110 entries; -$174,597.81 | 116/179; 81 entries; $36,703.80 | 103/143; 62 entries; $39,422.27 |
| Rally veto + Reported runway <6 months | 194/419; 105 entries; -$127,983.54 | 102/166; 77 entries; $30,721.83 | 90/134; 57 entries; $81,554.48 |
| Negative operating cash flow | 440/512; 121 entries; -$29,892.73 | 168/179; 95 entries; $39,160.38 | 135/143; 68 entries; $84,247.86 |
| Rally veto + Negative operating cash flow | 355/419; 117 entries; -$12,633.77 | 150/166; 93 entries; $34,748.41 | 119/134; 63 entries; $80,500.11 |
| Operating loss | 453/477; 125 entries; -$181,341.05 | 169/175; 94 entries; $37,030.93 | 135/143; 68 entries; $84,247.86 |
| Rally veto + Operating loss | 366/390; 120 entries; -$133,498.15 | 151/164; 92 entries; $34,779.31 | 120/134; 63 entries; $81,099.51 |
| Revenue decline ≥15% | 112/316; 78 entries; -$6,543.66 | 38/106; 34 entries; $17,563.72 | 29/89; 26 entries; $11,178.32 |
| Rally veto + Revenue decline ≥15% | 91/262; 68 entries; $8,490.91 | 31/97; 28 entries; $14,544.84 | 24/83; 22 entries; $2,780.29 |
| Operating margin decline ≥8pp | 145/304; 86 entries; -$10,709.69 | 41/101; 36 entries; $15,361.49 | 45/89; 38 entries; $32,505.05 |
| Rally veto + Operating margin decline ≥8pp | 116/252; 76 entries; $10,190.95 | 35/93; 33 entries; $13,140.34 | 41/83; 35 entries; $4,156.13 |
| Accrual ratio ≥10% | 49/460; 43 entries; $54.22 | 15/164; 14 entries; $10,020.87 | 19/134; 17 entries; $4,393.62 |
| Rally veto + Accrual ratio ≥10% | 40/379; 37 entries; $25,732.56 | 15/152; 14 entries; $10,020.87 | 15/126; 13 entries; $695.62 |
| Profit without operating cash | 16/488; 16 entries; $4,368.24 | 5/167; 4 entries; -$668.00 | 2/135; 2 entries; $1,359.18 |
| Rally veto + Profit without operating cash | 12/399; 12 entries; $35,613.57 | 5/155; 4 entries; -$668.00 | 1/127; 1 entries; -$22.86 |
| Negative equity | 129/488; 86 entries; -$85,899.01 | 35/169; 31 entries; $19,528.21 | 36/134; 33 entries; $74,029.96 |
| Rally veto + Negative equity | 94/400; 69 entries; -$56,545.11 | 29/156; 26 entries; $13,200.29 | 32/126; 29 entries; $73,834.35 |
| Debt maturity + cash distress | 0/241; 0 entries; $0.00 | 0/50; 0 entries; $0.00 | 0/40; 0 entries; $0.00 |
| Rally veto + Debt maturity + cash distress | 0/196; 0 entries; $0.00 | 0/47; 0 entries; $0.00 | 0/37; 0 entries; $0.00 |
| Weak prior completed-session close | 219/567; 109 entries; -$310,624.93 | 75/195; 58 entries; $23,141.41 | 51/143; 39 entries; $14,020.78 |
| Rally veto + Weak prior completed-session close | 208/563; 108 entries; -$316,836.34 | 70/194; 54 entries; $17,568.72 | 50/142; 39 entries; $13,571.10 |
| Cash burn + dilution | 89/346; 68 entries; $49,566.43 | 86/144; 62 entries; $29,374.01 | 98/124; 58 entries; $80,426.39 |
| Short reported runway + dilution | 56/346; 50 entries; $11,381.32 | 59/144; 49 entries; $24,412.09 | 73/124; 52 entries; $81,238.14 |
| Operating loss + dilution | 87/325; 70 entries; $15,646.32 | 87/143; 63 entries; $30,165.55 | 99/124; 58 entries; $81,025.78 |
| Short runway + dilution + operating loss | 56/325; 50 entries; $11,381.32 | 58/143; 49 entries; $24,824.43 | 73/124; 52 entries; $81,238.14 |
| Short runway + dilution + revenue decline | 12/206; 12 entries; -$1,464.47 | 11/84; 11 entries; $8,613.61 | 15/76; 13 entries; $1,921.45 |
| Cash burn + weak prior close + rally veto | 141/419; 87 entries; $1,663.69 | 59/166; 49 entries; $16,716.56 | 43/134; 35 entries; $8,717.40 |
| Cash burn + rapid repeat + rally veto | 0/0; 0 entries; $0.00 | 19/166; 18 entries; $12,382.81 | 39/134; 31 entries; $76,446.04 |
| Cash pressure + recent financing | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 1/2; 1 entries; $371.64 |
| Cash pressure + financing + rally veto | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 1/2; 1 entries; $371.64 |
| Original cash/financing/weak split close | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 |
| Original weak split close + prior weakness | 5/52; 3 entries; $2,278.55 | 6/18; 6 entries; $619.33 | 4/20; 4 entries; $8,141.42 |

### Highest fitted net profit with at least 20 entries

These are retrospective leaders within each split-history group at one fixed
timing/cost/holding setup. They are not validated winners or production selections.
Raw net dollars also reflect different exposure, slot use and data coverage.

| Group | Filter | Entries | Net marked P&L | Covered-control P&L | Closing drawdown | Without best five |
| --- | --- | --- | --- | --- | --- | --- |
| all | burn_dilution | 104 | $134,674.58 | $11,831.86 | -$8,756.22 | $10,431.63 |
| first | burn_dilution | 68 | $49,566.43 | -$46,477.26 | -$14,871.37 | -$1,943.83 |
| second | only_S4 | 75 | $46,487.95 | $43,119.36 | -$4,745.66 | $16,601.66 |
| third_plus | all | 73 | $109,951.92 | $109,951.92 | -$6,075.54 | $6,056.27 |

## Sensitivity checks

Unfiltered announcement entries by split history; three slots; 20 sessions
from entry. Other filtered and unlimited-opportunity cases are in the publication.

| History | Costs | Entries | Net marked P&L | Closing drawdown | Without best five |
| --- | --- | --- | --- | --- | --- |
| all | favorable | 135 | -$437,023.37 | -$591,515.13 | -$460,228.98 |
| all | base | 135 | -$180,017.28 | -$251,572.71 | -$192,865.58 |
| all | stress | 135 | -$170,449.35 | -$171,080.27 | -$175,602.01 |
| first | favorable | 132 | -$303,612.25 | -$369,518.53 | -$330,365.83 |
| first | base | 132 | -$296,472.08 | -$323,537.39 | -$313,002.04 |
| first | stress | 132 | -$316,841.34 | -$334,442.21 | -$321,960.29 |
| second | favorable | 103 | $84,379.07 | -$6,806.13 | $41,873.53 |
| second | base | 103 | $46,057.40 | -$4,746.72 | $18,587.98 |
| second | stress | 103 | $6,911.56 | -$4,148.96 | -$4,593.06 |
| third_plus | favorable | 73 | $149,668.24 | -$6,137.88 | $15,765.61 |
| third_plus | base | 73 | $109,951.92 | -$6,075.54 | $6,056.27 |
| third_plus | stress | 73 | $62,460.60 | -$7,571.70 | -$5,508.81 |

Two distinct cover rules use only information known when the announcement arrives:
session 20 from actual entry, or session 20 after the effective date stated in
the original announcement. Later rescheduling does not improve the planned exit.

| History | Holding rule | Entries | Net marked P&L | Closing drawdown |
| --- | --- | --- | --- | --- |
| all | entry20 | 135 | -$180,017.28 | -$251,572.71 |
| all | scheduled_split20 | 103 | -$250,689.09 | -$311,908.15 |
| first | entry20 | 132 | -$296,472.08 | -$323,537.39 |
| first | scheduled_split20 | 111 | -$472,190.82 | -$501,798.42 |
| second | entry20 | 103 | $46,057.40 | -$4,746.72 |
| second | scheduled_split20 | 88 | $52,642.53 | -$4,746.72 |
| third_plus | entry20 | 73 | $109,951.92 | -$6,075.54 |
| third_plus | scheduled_split20 | 66 | $78,128.56 | -$13,797.49 |

## Point-in-time source construction

- Select the first captured definite scheduled-action clause per issuer and
  announced effective date, including pre-2023 lookback. Exclude proposals,
  authorizations, generic legal changes and disclosures arriving after their
  own stated effective date. Do not require a later completed split.
- 1028 source-cohort announcements
  have saved SEC acceptance timestamps. Acceptance is a publication proxy, not
  proof of the first issuer press release or when a trader received it.
  441 episodes have no
  match in the completed-event control; that does not prove they were cancelled.
- The separate completed-event timing control has
  1045 announcements and is conditioned on
  later completion. Its post-effective entry row recomputes later decision-time
  signals as a policy reference; differences include information and timing.
  It must not be presented as an unbiased announcement universe or a pure
  entry-time-only causal comparison. Frozen older results are separate.
- Financial statements and share facts are rebuilt from raw CompanyFacts and
  cached original filings at the announcement clock. Later filings, amendments
  and restatements cannot enter an earlier snapshot. Date-only financial filings
  conservatively become usable the next day. Cash/TTM observation freshness is
  200 days; period, currency, total CFO and share basis must be consistent.
- Cash burn, reported runway, operating loss, revenue decline, margin decline,
  accruals, profit without cash, equity and debt maturity reuse the existing
  source-reconciliation arithmetic. Share growth requires comparable six-month
  observations and action-unit proof. Scores are recomputed as of announcement;
  both the corrected missing-debt treatment and legacy score are labeled.
- Cash pressure adds only identified then-public funding flows, with incomplete
  source coverage explicit. Recent financing is a cached completed-claim
  diagnostic, not independent verification of issuance or saleable supply.
  Missing financing evidence is unknown, not proof of no financing.
- Prior rally and 20-session price weakness use completed adjusted sessions
  only. The original weak **split-day** close is unknown until that session
  actually finishes. A separately named weak **prior-session** close applies
  the same lower-quartile/below-open rule to the last completed session.

## Execution and accounting assumptions

Enter at or after the disclosure plus zero or five minutes, or at the next
regular-session open, never before 09:31 Eastern. Sixty-minute entry window
ends at least 15 minutes before the actual exchange close. After-hours news
waits for regular trading; no extended-hours executions are invented.

| Scenario | Annual borrow | Half-spread | Impact each side | Flow capture | Locate fee |
|---|---|---|---|---|---|
| Base | 50% | 86 bp | 10 bp | 50% | $0.01/share, $5 minimum |
| Favorable | 10% | 43 bp | 5 bp | 75% | None |
| Stress | 150% | 172 bp | 30 bp | 25% | $0.03/share, $15 minimum |

Ten-percent participation, 500 ms order acknowledgement and existing
commission/regulatory fee arithmetic. The locate charges and APR are scenario
assumptions, not verified IBKR terms. Gross before listed cash costs already
reflects execution prices and spread effects. Dividends, recalls and issuer-
specific involuntary closeout charges are not exhaustively reconstructed.
Cost scenarios also change flow capture, actual fills and later slot admissions;
the lower-cost scenario can therefore lose more dollars by taking more exposure.

Captured windows must cover the entire attempt without a recorded gap. A
partial capture is missing evidence, not an observed no-fill. Missing tapes use
flat price and prior ADV, not future daily volume. Unsupported intraday prices
use an already-known open or adjusted prior close, never future high/low/close.
Stress reduces these intraday short-entry proxies by 10%. Entirely unpriced
securities use an explicit counted $5 placeholder. Actual announcement jumps
remain unknown where quotes/bars were not captured.

In the unfiltered primary book, **131/135** entries use a
price-tape proxy, **31** use intraday price proxies and
**15** use the unpriced placeholder. Without the best five
issuers, the same accepted portfolio's profit is **-$192,865.58**;
this subtraction does not refill capacity. Data gaps and concentration must
be read alongside profit. Equal zero/five-minute results can be an artifact
of flat proxies and after-hours timing, not proof that reaction speed is irrelevant.

Three-slot admission follows actual arrivals, reserving pending no-fill windows
until they end and holding covered slots through that session. Loans accrue
calendar-day borrow after settlement until returned. Subsequent corporate actions
change owed units; whole-share overbuy, surplus cleanup and fees are paid.
Missing marks and exits retain explicit adverse-price estimates and a bounded
retry period; real residual positions would stay open until broker confirmation.
Closing drawdown is not maximum intraday loss, and the $10 million reporting
reference is not a new live capital or reserve allocation.

## Reproduction and review

There are **15288** cases, **49** prespecified filter arms,
four split-history groups, three cost scenarios, two capacity modes, three
announcement entry clocks and two holding rules. The completed-event control
also includes its post-effective policy reference. Every case uses full sizing.

- Full cached rebuild: `node _system/scripts/third_plus_execution/announcement_study.cjs --source-root <cached-source-root>`.
- Offline checks: the same command with `--check`, then
  `node _system/scripts/third_plus_execution/announcement_report.cjs --check`.
- Public announcement audit: `dashboard/data/third_plus_announcement_events.csv`. Rows are
  unfiltered independent base opportunities, not the three-slot account ledger.
  They include timestamps, source links, initial price basis, feature states,
  assumed entries, exits and marked profit for review.
- Full detailed local paths: ignored
  `local/third_plus_signal_study/announcement_full_v2/audit.local.json`.
- Protocol, implementation, raw/parsed financial inputs, score dependencies,
  prices, action repairs, archive index, exchange calendar and each publication
  shard have receipts. Browser and offline checks verify exact bytes.

Publication `25952bc6672d38164fe6196c330a932b88184b420986c62a7394b62dbb440b52`; protocol `854c9990ef17c7e47e3981e5c6e779ae2efd17602c953e297ca72250ff57b4f1`.

Next evidence: earlier issuer-news coverage with receipt clocks, event-time
prices, actual loan/cost terms and prospective fills. The
[autonomous live plan](THIRD_PLUS_LIVE_EXECUTOR_PLAN.md) uses one initial share
per company, an independent IBKR arrangement and no SPX Gateway dependency.
