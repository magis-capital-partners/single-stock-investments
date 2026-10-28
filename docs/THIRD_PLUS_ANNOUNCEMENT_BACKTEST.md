# Full-size announcement-day reverse-split backtest

**Backtest: $100,000 target per company. Future live pilot: one initial share
per company.** The historical study contains no one-share sizing cases.
Announcements through 2026-10-10; market data through 2026-10-12;
start 2023-01-01. Research only; all qualifying names are assumed accessible
and borrowable. No broker/Gateway connection, Theta access or paid acquisition.

The protocol was registered 2026-10-28T20:29:00.489Z, before the corrected full
run's outcomes. Earlier exploratory runs informed the data repairs; this is not
a claim of a previously unseen strategy or data set. Earlier post-effective publications remain frozen. These
comparisons are exploratory and are not an untouched holdout.

## Full-size results by split history

The source-covered universe has **1651**
announcements across **1108** issuers.
first: 996; second: 368; third_plus: 287.
Split number is determined using prior completed actions already known at the
announcement, a lower bound on lifetime history. The current action cannot
count as its own predecessor.

The unfiltered, independent-opportunity, base-cost announcement replay has **1564**
entries, **-$143,469.36** net marked profit and **-$277,548.04**
worst drawdown from daily marks. **38** positions remain open.
Mean modeled entry is **$2,907.82**, not $100,000: participation,
flow capture and partial fills constrain the order target. Independent-opportunity
cases omit competition for slots; they are not a funded account result.

All following primary rows enter from the captured announcement clock and hold
20 sessions from entry. Fundamental and price filters use information available
at that announcement rather than the later effective split date.

| Split history | Filter | Pass / covered | Entries | Net marked P&L | Daily-mark drawdown | Mean entry | Still open | Without best five |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | all | 1651/1651 | 1564 | -$143,469.36 | -$277,548.04 | $2,907.82 | 38 | -$276,185.62 |
| all | rally | 1436/1482 | 1354 | -$61,372.51 | -$274,418.41 | $2,315.57 | 32 | -$178,264.85 |
| all | rally_burn | 921/1064 | 867 | -$102,902.75 | -$259,196.22 | $1,342.91 | 18 | -$160,524.15 |
| all | burn_weak_prior | 242/1064 | 226 | -$6,361.90 | -$49,559.45 | $1,413.62 | 4 | -$33,992.93 |
| first | all | 996/996 | 935 | -$214,330.34 | -$230,896.82 | $3,456.39 | 21 | -$256,203.46 |
| first | rally | 839/859 | 781 | -$74,370.97 | -$126,848.27 | $2,783.99 | 18 | -$116,192.37 |
| first | rally_burn | 505/594 | 467 | -$31,951.63 | -$70,377.18 | $1,571.90 | 8 | -$66,822.99 |
| first | burn_weak_prior | 133/594 | 123 | -$34,548.01 | -$48,293.39 | $1,634.44 | 2 | -$47,534.26 |
| second | all | 368/368 | 351 | $53,211.61 | -$19,140.48 | $1,773.70 | 6 | $15,543.94 |
| second | rally | 332/345 | 316 | $57,254.52 | -$22,883.84 | $1,388.95 | 5 | $21,469.44 |
| second | rally_burn | 229/252 | 218 | $33,709.83 | -$14,053.78 | $894.96 | 3 | $11,037.95 |
| second | burn_weak_prior | 58/252 | 52 | $8,064.74 | -$7,032.98 | $1,101.15 | 1 | -$2,452.91 |
| third_plus | all | 287/287 | 278 | $17,649.37 | -$235,569.75 | $2,494.76 | 11 | -$94,299.57 |
| third_plus | rally | 265/278 | 257 | -$44,256.06 | -$236,832.18 | $2,031.43 | 9 | -$130,905.52 |
| third_plus | rally_burn | 187/218 | 182 | -$104,660.95 | -$223,612.69 | $1,291.89 | 7 | -$131,888.26 |
| third_plus | burn_weak_prior | 51/218 | 51 | $20,121.38 | -$4,374.61 | $1,199.66 | 1 | $2,656.59 |

Each history/filter row is a separately replayed portfolio with its own independent
paths. The split-history groups partition those paths; their unfiltered profits
sum to the independent combined result. Three-slot books compete for capacity
and their subgroup profits must not be added to reconstruct that account.

### Attempt every candidate without competition for slots

Independent opportunities, full dollar target, base costs and 20 sessions from
entry. These diagnostics retain modeled partial fills but remove the three-slot
and same-issuer overlap restrictions. They are not a capital-constrained account.

| History | Filter | Entries | Net marked P&L | Mean entry | Still open |
| --- | --- | --- | --- | --- | --- |
| all | all | 1564 | -$143,469.36 | $2,907.82 | 38 |
| all | burn_dilution | 364 | $68,107.14 | $1,197.55 | 6 |
| first | all | 935 | -$214,330.34 | $3,456.39 | 21 |
| first | burn_dilution | 110 | $13,988.19 | $1,221.28 | 2 |
| second | all | 351 | $53,211.61 | $1,773.70 | 6 |
| second | burn_dilution | 118 | $25,298.88 | $1,105.29 | 0 |
| third_plus | all | 278 | $17,649.37 | $2,494.76 | 11 |
| third_plus | burn_dilution | 136 | $28,820.06 | $1,258.42 | 4 |

## Three-company capacity comparison

This alternative admits opportunities chronologically with a $100,000 target
and at most three open issuers. Each row is its own account replay; subgroup
profits cannot be added to reconstruct the combined three-slot book.

| History | Entries | Net marked P&L | Daily-mark drawdown | Mean fill |
| --- | --- | --- | --- | --- |
| all | 137 | $3,060.19 | -$12,260.43 | $3,006.43 |
| first | 133 | $4,287.05 | -$14,796.32 | $2,401.85 |
| second | 118 | $22,756.31 | -$5,763.95 | $1,311.64 |
| third_plus | 89 | -$91,939.29 | -$236,631.98 | $4,094.92 |

## Every fundamental filter and predefined combination

Each cell: **passing / feature-covered candidates; entries; net marked P&L**.
Base costs, independent opportunities, immediate regular-session announcement attempt, 20
sessions from entry and the full dollar target. The dashboard also provides
same-feature-coverage controls: both passing and failing companies where the
required inputs exist, with identical execution and capacity. Unknowns do not
pass. Zero entries are not evidence of zero return or of a bad stock-selection rule.

| Announcement-time screen | First documented | Second documented | Third or later |
| --- | --- | --- | --- |
| Every candidate | 996/996; 935 entries; -$214,330.34 | 368/368; 351 entries; $53,211.61 | 287/287; 278 entries; $17,649.37 |
| No 50% daily rally | 839/859; 781 entries; -$74,370.97 | 332/345; 316 entries; $57,254.52 | 265/278; 257 entries; -$44,256.06 |
| As-of financial score ≥60 | 181/515; 172 entries; -$21,806.33 | 76/193; 74 entries; $13,408.78 | 57/147; 55 entries; $26,630.54 |
| Rally veto + As-of financial score ≥60 | 151/441; 143 entries; $549.83 | 69/179; 67 entries; $12,042.13 | 52/141; 51 entries; $4,246.91 |
| Legacy financial score ≥60 | 207/551; 196 entries; -$16,164.85 | 87/208; 84 entries; $24,285.62 | 64/160; 62 entries; $31,271.47 |
| Rally veto + Legacy financial score ≥60 | 172/472; 162 entries; $4,981.38 | 77/192; 74 entries; $19,798.18 | 58/154; 57 entries; $7,528.37 |
| Cash pressure incl. identified financing | 336/701; 315 entries; -$38,079.35 | 177/268; 169 entries; $28,380.15 | 124/199; 121 entries; -$98,429.16 |
| Rally veto + Cash pressure incl. identified financing | 279/594; 259 entries; $12,355.28 | 158/250; 151 entries; $29,188.76 | 115/191; 113 entries; -$117,163.99 |
| Recent completed equity-linked financing | 0/0; 0 entries; $0.00 | 2/2; 2 entries; $2,957.83 | 19/19; 16 entries; $11.56 |
| Rally veto + Recent completed equity-linked financing | 0/0; 0 entries; $0.00 | 2/2; 2 entries; $2,957.83 | 19/19; 16 entries; $11.56 |
| Previous split within 180 days | 0/0; 0 entries; $0.00 | 54/368; 53 entries; $10,057.34 | 131/287; 129 entries; -$6,408.60 |
| Rally veto + Previous split within 180 days | 0/0; 0 entries; $0.00 | 52/345; 51 entries; $12,860.62 | 123/278; 122 entries; -$51,668.83 |
| Share growth ≥25% | 163/633; 154 entries; $5,238.15 | 162/247; 155 entries; $23,980.89 | 172/197; 166 entries; $83,515.09 |
| Rally veto + Share growth ≥25% | 142/537; 133 entries; $17,466.88 | 143/228; 136 entries; $25,709.82 | 162/191; 157 entries; $88,634.79 |
| Original weak split-day close · RTH range required | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 |
| Rally veto + Original weak split-day close · RTH range required | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 |
| Prior 20-session return ≤−20% | 332/853; 312 entries; $4,548.68 | 182/340; 177 entries; $39,261.83 | 183/278; 181 entries; -$33,823.15 |
| Rally veto + Prior 20-session return ≤−20% | 329/853; 309 entries; -$4,337.23 | 177/340; 172 entries; $35,705.99 | 177/278; 175 entries; -$94,808.41 |
| Reported runway <6 months | 336/701; 315 entries; -$38,079.35 | 178/270; 170 entries; $30,395.09 | 148/226; 143 entries; -$94,531.26 |
| Rally veto + Reported runway <6 months | 279/594; 259 entries; $12,355.28 | 159/252; 152 entries; $31,203.71 | 138/218; 134 entries; -$115,998.40 |
| Negative operating cash flow | 597/701; 556 entries; -$120,753.08 | 252/270; 240 entries; $35,455.35 | 201/226; 195 entries; -$91,479.75 |
| Rally veto + Negative operating cash flow | 505/594; 467 entries; -$31,951.63 | 229/252; 218 entries; $33,709.83 | 187/218; 182 entries; -$104,660.95 |
| Operating loss | 619/660; 579 entries; -$140,341.52 | 257/267; 245 entries; $33,323.03 | 196/221; 190 entries; -$114,128.97 |
| Rally veto + Operating loss | 525/559; 487 entries; -$45,686.16 | 230/249; 219 entries; $34,477.99 | 184/214; 179 entries; -$107,162.25 |
| Revenue decline ≥15% | 163/444; 150 entries; -$34,542.01 | 70/172; 68 entries; $10,668.63 | 55/140; 53 entries; $15,828.47 |
| Rally veto + Revenue decline ≥15% | 141/379; 129 entries; -$3,859.16 | 59/160; 57 entries; $13,677.42 | 51/135; 50 entries; $12,264.50 |
| Operating margin decline ≥8pp | 203/424; 190 entries; -$31,323.41 | 76/168; 74 entries; $14,320.72 | 66/139; 64 entries; $32,804.32 |
| Rally veto + Operating margin decline ≥8pp | 171/363; 159 entries; -$14,203.48 | 68/156; 66 entries; $13,115.99 | 63/134; 62 entries; $9,995.49 |
| Accrual ratio ≥10% | 58/628; 56 entries; -$11,953.65 | 29/246; 26 entries; $13,124.74 | 22/210; 21 entries; $4,637.95 |
| Rally veto + Accrual ratio ≥10% | 47/536; 45 entries; -$7,879.16 | 29/231; 26 entries; $13,124.74 | 20/202; 19 entries; $2,295.77 |
| Profit without operating cash | 25/671; 25 entries; -$13,622.24 | 7/255; 6 entries; -$537.56 | 4/212; 4 entries; $2,874.52 |
| Rally veto + Profit without operating cash | 18/570; 18 entries; -$7,095.64 | 7/237; 6 entries; -$537.56 | 3/204; 3 entries; $1,515.04 |
| Negative equity | 162/670; 159 entries; -$31,834.21 | 56/257; 53 entries; $2,684.91 | 54/214; 53 entries; $74,647.68 |
| Rally veto + Negative equity | 125/571; 122 entries; $2,481.98 | 44/241; 41 entries; $7,695.82 | 49/206; 48 entries; $71,440.82 |
| Debt maturity + cash distress | 0/334; 0 entries; $0.00 | 0/76; 0 entries; $0.00 | 0/76; 0 entries; $0.00 |
| Rally veto + Debt maturity + cash distress | 0/271; 0 entries; $0.00 | 0/71; 0 entries; $0.00 | 0/72; 0 entries; $0.00 |
| Weak prior close · daily-range proxy where needed | 219/860; 203 entries; -$61,078.02 | 91/345; 83 entries; $11,352.01 | 74/279; 73 entries; $30,636.87 |
| Rally veto + Weak prior close · daily-range proxy where needed | 212/858; 196 entries; -$67,342.14 | 87/345; 79 entries; $8,715.56 | 71/278; 70 entries; $30,004.36 |
| Cash burn + dilution | 119/489; 110 entries; $13,988.19 | 124/211; 118 entries; $25,298.88 | 140/187; 136 entries; $28,820.06 |
| Short reported runway + dilution | 74/489; 71 entries; $4,913.94 | 87/211; 82 entries; $23,510.72 | 102/187; 99 entries; $25,236.18 |
| Operating loss + dilution | 117/462; 111 entries; $16,382.92 | 126/209; 120 entries; $25,692.85 | 137/184; 133 entries; $27,322.84 |
| Short runway + dilution + operating loss | 71/462; 68 entries; $4,737.07 | 87/209; 82 entries; $23,510.72 | 101/184; 98 entries; $25,203.18 |
| Short runway + dilution + revenue decline | 15/298; 15 entries; -$4,988.66 | 20/132; 19 entries; $7,727.28 | 27/117; 26 entries; $3,545.02 |
| Cash burn + weak prior close + rally veto | 133/594; 123 entries; -$34,548.01 | 58/252; 52 entries; $8,064.74 | 51/218; 51 entries; $20,121.38 |
| Cash burn + rapid repeat + rally veto | 0/0; 0 entries; $0.00 | 34/252; 33 entries; $9,890.98 | 75/218; 75 entries; -$119,830.65 |
| Cash pressure + recent financing | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/3; 0 entries; $0.00 |
| Cash pressure + financing + rally veto | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/3; 0 entries; $0.00 |
| Original cash/financing/weak split close | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 |
| Original weak split close + prior weakness | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 | 0/0; 0 entries; $0.00 |

### Highest fitted profit excluding missing entry prices, with at least 20 remaining entries

These rank profit excluding missing-price entries on the same accepted book,
without replacing those positions. They are retrospective leaders within each split-history group at one fixed
timing/cost/holding setup. They are not validated winners or production selections.
Raw net dollars also reflect different exposure, slot use and data coverage.

| Group | Filter | Entries | Net marked P&L | Without missing-price entries | Covered-control P&L | Daily-mark drawdown | Without best five |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | only_S4 | 475 | $112,734.13 | $135,293.46 | -$50,798.73 | -$41,195.44 | $7,111.42 |
| first | only_S4 | 154 | $5,238.15 | $19,525.89 | -$178,608.54 | -$16,228.25 | -$22,372.17 |
| second | all | 351 | $53,211.61 | $68,430.35 | $53,211.61 | -$19,140.48 | $15,543.94 |
| third_plus | rally_S4 | 157 | $88,634.79 | $88,634.79 | $114,869.05 | -$41,373.84 | $7,185.35 |

## Sensitivity checks

Unfiltered announcement entries by split history; no slot competition; 20 sessions
from entry. Three-slot and other filtered cases are in the publication.

| History | Costs | Entries | Net marked P&L | Daily-mark drawdown | Without best five |
| --- | --- | --- | --- | --- | --- |
| all | favorable | 1561 | $416,229.59 | -$323,050.60 | $219,856.43 |
| all | base | 1564 | -$143,469.36 | -$277,548.04 | -$276,185.62 |
| all | stress | 1564 | -$860,437.58 | -$861,296.55 | -$904,662.65 |
| first | favorable | 933 | $139,513.46 | -$51,400.74 | $65,053.04 |
| first | base | 935 | -$214,330.34 | -$230,896.82 | -$256,203.46 |
| first | stress | 935 | -$685,232.73 | -$685,232.73 | -$698,592.15 |
| second | favorable | 350 | $175,872.93 | -$21,704.94 | $111,152.75 |
| second | base | 351 | $53,211.61 | -$19,140.48 | $15,543.94 |
| second | stress | 351 | -$79,840.69 | -$83,936.69 | -$91,060.80 |
| third_plus | favorable | 278 | $100,843.20 | -$329,317.27 | -$59,144.78 |
| third_plus | base | 278 | $17,649.37 | -$235,569.75 | -$94,299.57 |
| third_plus | stress | 278 | -$95,364.15 | -$154,733.82 | -$134,414.73 |

Two distinct cover rules use only information known when the announcement arrives:
session 20 from actual entry, or session 20 counting the originally announced
first split-adjusted trading day as session one. Later rescheduling does not improve the planned exit.

| History | Holding rule | Entries | Net marked P&L | Daily-mark drawdown |
| --- | --- | --- | --- | --- |
| all | entry20 | 1564 | -$143,469.36 | -$277,548.04 |
| all | scheduled_split20 | 1564 | -$114,019.98 | -$277,518.22 |
| first | entry20 | 935 | -$214,330.34 | -$230,896.82 |
| first | scheduled_split20 | 935 | -$259,914.87 | -$276,643.91 |
| second | entry20 | 351 | $53,211.61 | -$19,140.48 |
| second | scheduled_split20 | 351 | $55,949.71 | -$17,346.64 |
| third_plus | entry20 | 278 | $17,649.37 | -$235,569.75 |
| third_plus | scheduled_split20 | 278 | $89,945.18 | -$231,986.43 |

## Point-in-time source construction

- Use captured SEC 8-K/6-K event reports, including amendments. Proxy drafts,
  registration templates and proposed certificates are not definite announcements,
  even when they contain a sample effective date. Financial reports still supply
  point-in-time fundamentals.
- Select the first captured definite scheduled-action clause per issuer and
  announced first-trading date, including pre-2023 lookback. Exclude proposals,
  authorizations, open-ended implementation deadlines, embedded proxy drafts,
  warrant updates, registration-statement dates, generic legal changes and disclosures arriving after their
  own stated trading date. Re-read eligible source documents rather than trusting
  their older automated stage labels: definite scheduled actions can be
  recovered from a misclassified proposal. Pure authorizations remain excluded.
  Do not require a later completed split. Explicit revisions fold into a
  captured earlier announcement of the same action, preserving the original
  trigger and holding clock while accounting uses the actual later unit change.
- 1365 source-cohort announcements
  have saved SEC acceptance timestamps. Acceptance is a publication proxy, not
  proof of the first issuer press release or when a trader received it.
  226 events instead use an earlier
  action-specific original-release date found in the filing. Availability is
  assumed at 23:59:59 New York time, with all announcement features frozen at
  that date's start to avoid unknown-hour reaction leakage; entry then waits
  for a regular session. Missing hours are never invented as observed clocks.
  779 episodes have no
  match in the completed-event control; that does not prove they were cancelled.
- The separate completed-event timing control intersects valid announcement
  episodes with completed events, deduplicates physical actions, and has
  870 announcements and is conditioned on
  later completion. Its post-effective entry follows the source-bound unit transition where
  available and recomputes later decision-time
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
  the same lower-quartile/below-open rule to a completed price period. Where
  a full regular-session range was not captured, it is a labeled completed
  UTC-day-range proxy; it must not be equated to observed regular-session OHLC.

## Share-unit and security audit

Primary issuer reports and action press releases establish exact ratios. Warrant
agreements, tax annexes and draft certificates are excluded. Nominal prices
corroborate execution and never supply a fitted factor. A reported-completed
action can establish units without an unavailable pre-event price anchor;
**42** records use that explicit basis. 4 reviewed conversions pair with distributions, so a nominal price jump is not required; 3 reviews specify cash repayments per old share. The audit applies
**1620** actions and replaces **60**
conflicting factors. Legal dates and first split-adjusted trading dates are
counted once. **160** trading dates use
explicitly labeled five-session transition estimates.

ADS changes use the change in ordinary shares per ADS rather than the new
ordinary-share denominator alone; they do not mechanically change the ordinary
share count used in dilution screens. Authorization ranges and clock strings
cannot become split ratios. **15** fund/ETF/ETN/closed-end
issuers are outside this operating-stock study. 16 difficult clauses have
explicit source-bound ratio/date reviews with immutable original-text receipts.
Historical mentions in later filings cannot overwrite an earlier action.
Distinct Class A/Class B ratios use the listed class; aggregate share-count
comparisons crossing different class ratios require separate proof and otherwise
remain unknown. Issuer security headers take
precedence over unrelated ticker references in filing text.

**456** historical-symbol mappings remain same-issuer
price-continuity assumptions, not broker-confirmed identities. The published
source-action audit includes all mappings, clauses, ratios, dates, receipts and
**0** flagged source-associated nominal
unit discontinuities. **0** entered positions in the primary
independent-opportunity book cross those flagged transitions; **0**
modeled sessions carry an uncertain unit factor forward. This check does not prove
that every corporate event or symbol history is complete.

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

An extra unreconstructed corporate-action allowance is 1% of entry notional
in base, zero in favorable and 5% in stress. This is a model-risk cost estimate,
not an observed fee. The primary book charges **$45,478.34**.
A source-specified cash repayment per old share takes precedence. For other
consolidations paired with capital repayment or a spin-off, an unknown
distribution is settled as an estimated cash-equivalent liability equal to the
mechanical unit reduction at the prior mark; the
primary book charges **$72,014.82**. This assumption omits
later distributed-security price movements. Actual special cash
and stock distributions are not exhaustively reconstructed. Known halted cover
windows cannot be force-closed through the residual-price assumption.

Ten-percent participation, 500 ms order acknowledgement and existing
commission/regulatory fee arithmetic. The locate charges and APR are scenario
assumptions, not verified IBKR terms. Gross before listed cash costs already
reflects execution prices and spread effects. Dividends, recalls and issuer-
specific involuntary closeout charges are not exhaustively reconstructed.
Cost scenarios also change flow capture, actual fills and later slot admissions;
the lower-cost scenario can therefore lose more dollars by taking more exposure.

Captured windows must cover the entire attempt without a recorded gap. A
partial capture is missing evidence, not an observed no-fill. Missing tapes use
flat price and prior ADV, not future daily volume. Intraday price fallbacks
first use an already-known open or adjusted prior close.
Official auction opens are preferred. UTC-day OHLC opens are not regular-session
opens. Price signals use official closes after the actual close or fallback
UTC-day closes only after that UTC day ends. Missing-tape cover attempts use a
known official open or prior close, never the later close as if it were known
at the attempt. Bounded residual cleanup retains an assumed closing-price
premium. Stress reduces unsupported intraday short-entry proxies by 10%. Entirely unpriced
securities first use a labeled subsequent close within 20 sessions, adjusted
back into entry share units, assuming no unexplained price change over the gap.
That price is not admitted to any announcement-time filter. A counted $5
placeholder remains only if this also fails. Actual announcement jumps
remain unknown where quotes/bars were not captured.

In the unfiltered primary book, **1556/1564** entries use a
price-tape proxy, **409** use intraday price proxies and
**17** use later-price imputations and
**114** still use the $5 placeholder. Excluding all
**131** missing-price positions from the same accepted
book, without refilling capacity, leaves **$22,749.76**. Without the best five
issuers, the same accepted portfolio's profit is **-$276,185.62**;
this subtraction does not refill capacity. Data gaps and concentration must
be read alongside profit. Equal zero/five-minute results can be an artifact
of flat proxies and after-hours timing, not proof that reaction speed is irrelevant.

Three-slot admission follows actual arrivals, reserving pending no-fill windows
until they end and holding covered slots through that session. Loans accrue
calendar-day borrow after settlement until returned. Subsequent corporate actions
change owed units; whole-share overbuy, surplus cleanup and fees are paid.
Missing marks and exits retain explicit adverse-price estimates and a bounded
retry period; real residual positions would stay open until broker confirmation.
Daily marks prefer official closes and otherwise use completed UTC-day closes.
Daily-mark drawdown is not maximum intraday loss. The primary book peaks at
**$1,872,821.37** in modeled margin reserve and exceeds
the $10 million reporting reference plus marked P&L on **0**
sessions. Capital availability is assumed: this study reports margin rather
than rejecting orders for insufficient funding. The reporting reference is
not an account funding proof or a new live capital allocation.

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
  `local/third_plus_signal_study/announcement_full_v8/audit.local.json`.
- Protocol, implementation, raw/parsed financial inputs, score dependencies,
  prices, action repairs, archive index, exchange calendar and each publication
  shard have receipts. Browser and offline checks verify exact bytes.

Publication `ccee8274f0a9ac437230a87bbb553314f939d4ee0d59baf82cebf2e77b48d83a`; protocol `4f94689933116688ed23130efbeea4ab86450d6abb58aa863e73b34dac5bf5f2`.

Next evidence: earlier issuer-news coverage with receipt clocks, event-time
prices, actual loan/cost terms and prospective fills. The
[autonomous live plan](THIRD_PLUS_LIVE_EXECUTOR_PLAN.md) uses one initial share
per company, an independent IBKR arrangement and no SPX Gateway dependency.
