'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),S=require('./announcement_study.cjs');
const file=path.join(S.ROOT,'docs/THIRD_PLUS_ANNOUNCEMENT_BACKTEST.md'),usd=x=>(x<0?'-':'')+'$'+Math.abs(x).toLocaleString('en-US',{maximumFractionDigits:2,minimumFractionDigits:2});
function report(d){
 const base={cohort:'scheduled_disclosures',ordinal:'all',timing:'announce_now',holding:'entry20',size:'usd100k',scenario:'base',filter:'all',capacity:'unlimited'},find=patch=>d.models.find(m=>Object.entries({...base,...patch}).every(([k,v])=>m[k]===v));
 const groups=['all','first','second','third_plus'],table=(headers,rows)=>['| '+headers.join(' | ')+' |','| '+headers.map(()=>'---').join(' | ')+' |',...rows.map(row=>'| '+row.join(' | ')+' |')].join('\n');
 const overview=groups.flatMap(ordinal=>['all','rally','rally_burn','burn_weak_prior'].map(filter=>find({ordinal,filter}))),b=find({}),r=b.summary;
 const matrix=d.arms.map(a=>[a.label,...groups.slice(1).map(ordinal=>{const m=find({ordinal,filter:a.id});return m.signal_pass+'/'+m.feature_covered+'; '+m.summary.entered+' entries; '+usd(m.summary.net_pnl);})]);
 const sensitivity=groups.flatMap(ordinal=>['favorable','base','stress'].map(scenario=>find({ordinal,scenario})));
 const holding=groups.flatMap(ordinal=>['entry20','scheduled_split20'].map(h=>find({ordinal,holding:h})));
 const independent=groups.flatMap(ordinal=>['all','burn_dilution'].map(filter=>find({ordinal,filter,capacity:'unlimited'})));
 const best=groups.map(ordinal=>d.models.filter(m=>Object.entries({...base,ordinal}).filter(([k])=>k!=='filter').every(([k,v])=>m[k]===v)&&m.summary.entered-m.summary.price_imputed_entries>=20).sort((a,b)=>b.summary.pnl_without_price_imputation-a.summary.pnl_without_price_imputation)[0]).filter(Boolean);
 return `# Full-size announcement-day reverse-split backtest

**Backtest: $100,000 target per company. Future live pilot: one initial share
per company.** The historical study contains no one-share sizing cases.
Announcements through ${d.disclosure_through}; market data through ${d.market_through};
start ${d.first}. Research only; all qualifying names are assumed accessible
and borrowable. No broker/Gateway connection, Theta access or paid acquisition.

The protocol was registered ${d.protocol.registered_at}, before the corrected full
run's outcomes. Earlier exploratory runs informed the data repairs; this is not
a claim of a previously unseen strategy or data set. Earlier post-effective publications remain frozen. These
comparisons are exploratory and are not an untouched holdout.

## Full-size results by split history

The source-covered universe has **${d.cohorts.scheduled_disclosures.events}**
announcements across **${d.cohorts.scheduled_disclosures.issuers}** issuers.
${groups.slice(1).map(g=>g+': '+d.cohorts.scheduled_disclosures.ordinal_counts[g]).join('; ')}.
Split number is determined using prior completed actions already known at the
announcement, a lower bound on lifetime history. The current action cannot
count as its own predecessor.

The unfiltered, independent-opportunity, base-cost announcement replay has **${r.entered}**
entries, **${usd(r.net_pnl)}** net marked profit and **${usd(r.max_drawdown_dollars)}**
worst drawdown from daily marks. **${r.open_positions}** positions remain open.
Mean modeled entry is **${usd(r.mean_position)}**, not $100,000: participation,
flow capture and partial fills constrain the order target. Independent-opportunity
cases omit competition for slots; they are not a funded account result.

All following primary rows enter from the captured announcement clock and hold
20 sessions from entry. Fundamental and price filters use information available
at that announcement rather than the later effective split date.

${table(['Split history','Filter','Pass / covered','Entries','Net marked P&L','Daily-mark drawdown','Mean entry','Still open','Without best five'],overview.map(m=>[m.ordinal,m.filter,m.signal_pass+'/'+m.feature_covered,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.max_drawdown_dollars),usd(m.summary.mean_position),m.summary.open_positions,usd(m.summary.pnl_without_best5_issuers)]))}

Each history/filter row is a separately replayed portfolio with its own independent
paths. The split-history groups partition those paths; their unfiltered profits
sum to the independent combined result. Three-slot books compete for capacity
and their subgroup profits must not be added to reconstruct that account.

### Attempt every candidate without competition for slots

Independent opportunities, full dollar target, base costs and 20 sessions from
entry. These diagnostics retain modeled partial fills but remove the three-slot
and same-issuer overlap restrictions. They are not a capital-constrained account.

${table(['History','Filter','Entries','Net marked P&L','Mean entry','Still open'],independent.map(m=>[m.ordinal,m.filter,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.mean_position),m.summary.open_positions]))}

## Three-company capacity comparison

This alternative admits opportunities chronologically with a $100,000 target
and at most three open issuers. Each row is its own account replay; subgroup
profits cannot be added to reconstruct the combined three-slot book.

${table(['History','Entries','Net marked P&L','Daily-mark drawdown','Mean fill'],groups.map(ordinal=>{const m=find({ordinal,capacity:'three'});return [ordinal,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.max_drawdown_dollars),usd(m.summary.mean_position)];}))}

## Every fundamental filter and predefined combination

Each cell: **passing / feature-covered candidates; entries; net marked P&L**.
Base costs, independent opportunities, immediate regular-session announcement attempt, 20
sessions from entry and the full dollar target. The dashboard also provides
same-feature-coverage controls: both passing and failing companies where the
required inputs exist, with identical execution and capacity. Unknowns do not
pass. Zero entries are not evidence of zero return or of a bad stock-selection rule.

${table(['Announcement-time screen','First documented','Second documented','Third or later'],matrix)}

### Highest fitted profit excluding missing entry prices, with at least 20 remaining entries

These rank profit excluding missing-price entries on the same accepted book,
without replacing those positions. They are retrospective leaders within each split-history group at one fixed
timing/cost/holding setup. They are not validated winners or production selections.
Raw net dollars also reflect different exposure, slot use and data coverage.

${table(['Group','Filter','Entries','Net marked P&L','Without missing-price entries','Covered-control P&L','Daily-mark drawdown','Without best five'],best.map(m=>[m.ordinal,m.filter,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.pnl_without_price_imputation),usd(m.coverage_control.net_pnl),usd(m.summary.max_drawdown_dollars),usd(m.summary.pnl_without_best5_issuers)]))}

## Sensitivity checks

Unfiltered announcement entries by split history; no slot competition; 20 sessions
from entry. Three-slot and other filtered cases are in the publication.

${table(['History','Costs','Entries','Net marked P&L','Daily-mark drawdown','Without best five'],sensitivity.map(m=>[m.ordinal,m.scenario,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.max_drawdown_dollars),usd(m.summary.pnl_without_best5_issuers)]))}

Two distinct cover rules use only information known when the announcement arrives:
session 20 from actual entry, or session 20 counting the originally announced
first split-adjusted trading day as session one. Later rescheduling does not improve the planned exit.

${table(['History','Holding rule','Entries','Net marked P&L','Daily-mark drawdown'],holding.map(m=>[m.ordinal,m.holding,m.summary.entered,usd(m.summary.net_pnl),usd(m.summary.max_drawdown_dollars)]))}

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
- ${d.cohorts.scheduled_disclosures.exact_metadata} source-cohort announcements
  have saved SEC acceptance timestamps. Acceptance is a publication proxy, not
  proof of the first issuer press release or when a trader received it.
  ${d.cohorts.scheduled_disclosures.prior_release_date_assumptions} events instead use an earlier
  action-specific original-release date found in the filing. Availability is
  assumed at 23:59:59 New York time, with all announcement features frozen at
  that date's start to avoid unknown-hour reaction leakage; entry then waits
  for a regular session. Missing hours are never invented as observed clocks.
  ${d.cohorts.scheduled_disclosures.without_completed_match} episodes have no
  match in the completed-event control; that does not prove they were cancelled.
- The separate completed-event timing control intersects valid announcement
  episodes with completed events, deduplicates physical actions, and has
  ${d.cohorts.completed_matched.events} announcements and is conditioned on
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
**${d.action_audit.completed_without_nominal_anchor}** records use that explicit basis. ${d.action_audit.paired_distribution_unit_reviews} reviewed conversions pair with distributions, so a nominal price jump is not required; ${d.action_audit.source_cash_distribution_reviews} reviews specify cash repayments per old share. The audit applies
**${d.action_audit.actions}** actions and replaces **${d.action_audit.replaced_conflicting_factors}**
conflicting factors. Legal dates and first split-adjusted trading dates are
counted once. **${d.action_audit.estimated_unit_transition_dates}** trading dates use
explicitly labeled five-session transition estimates.

ADS changes use the change in ordinary shares per ADS rather than the new
ordinary-share denominator alone; they do not mechanically change the ordinary
share count used in dilution screens. Authorization ranges and clock strings
cannot become split ratios. **${d.action_audit.excluded_fund_issuers}** fund/ETF/ETN/closed-end
issuers are outside this operating-stock study. ${d.action_audit.reviewed_actions} difficult clauses have
explicit source-bound ratio/date reviews with immutable original-text receipts.
Historical mentions in later filings cannot overwrite an earlier action.
Distinct Class A/Class B ratios use the listed class; aggregate share-count
comparisons crossing different class ratios require separate proof and otherwise
remain unknown. Issuer security headers take
precedence over unrelated ticker references in filing text.

**${d.action_audit.assumed_price_aliases}** historical-symbol mappings remain same-issuer
price-continuity assumptions, not broker-confirmed identities. The published
source-action audit includes all mappings, clauses, ratios, dates, receipts and
**${d.action_audit.remaining_nominal_discontinuities}** flagged source-associated nominal
unit discontinuities. **${r.unresolved_action_paths}** entered positions in the primary
independent-opportunity book cross those flagged transitions; **${r.split_proxy_sessions}**
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
not an observed fee. The primary book charges **${usd(r.costs.event_allowance)}**.
A source-specified cash repayment per old share takes precedence. For other
consolidations paired with capital repayment or a spin-off, an unknown
distribution is settled as an estimated cash-equivalent liability equal to the
mechanical unit reduction at the prior mark; the
primary book charges **${usd(r.costs.capital_repayment)}**. This assumption omits
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

In the unfiltered primary book, **${r.proxy_entry}/${r.entered}** entries use a
price-tape proxy, **${r.intraday_proxy_entries}** use intraday price proxies and
**${r.next_price_imputations}** use later-price imputations and
**${r.unpriced_entries}** still use the $5 placeholder. Excluding all
**${r.price_imputed_entries}** missing-price positions from the same accepted
book, without refilling capacity, leaves **${usd(r.pnl_without_price_imputation)}**. Without the best five
issuers, the same accepted portfolio's profit is **${usd(r.pnl_without_best5_issuers)}**;
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
**${usd(r.modeled_margin_requirement)}** in modeled margin reserve and exceeds
the $10 million reporting reference plus marked P&L on **${r.margin_breach_days}**
sessions. Capital availability is assumed: this study reports margin rather
than rejecting orders for insufficient funding. The reporting reference is
not an account funding proof or a new live capital allocation.

## Reproduction and review

There are **${d.model_count}** cases, **${d.arms.length}** prespecified filter arms,
four split-history groups, three cost scenarios, two capacity modes, three
announcement entry clocks and two holding rules. The completed-event control
also includes its post-effective policy reference. Every case uses full sizing.

- Full cached rebuild: \`node _system/scripts/third_plus_execution/announcement_study.cjs --source-root <cached-source-root>\`.
- Offline checks: the same command with \`--check\`, then
  \`node _system/scripts/third_plus_execution/announcement_report.cjs --check\`.
- Public announcement audit: \`dashboard/data/${d.event_audit.file}\`. Rows are
  unfiltered independent base opportunities, not the three-slot account ledger.
  They include timestamps, source links, initial price basis, feature states,
  assumed entries, exits and marked profit for review.
- Full detailed local paths: ignored
  \`local/third_plus_signal_study/announcement_full_v8/audit.local.json\`.
- Protocol, implementation, raw/parsed financial inputs, score dependencies,
  prices, action repairs, archive index, exchange calendar and each publication
  shard have receipts. Browser and offline checks verify exact bytes.

Publication \`${d.data_version}\`; protocol \`${d.protocol.sha256}\`.

Next evidence: earlier issuer-news coverage with receipt clocks, event-time
prices, actual loan/cost terms and prospective fills. The
[autonomous live plan](THIRD_PLUS_LIVE_EXECUTOR_PLAN.md) uses one initial share
per company, an independent IBKR arrangement and no SPX Gateway dependency.
`;
}
function main(check=false){const d=S.check(),p=JSON.parse(fs.readFileSync(path.join(S.ROOT,S.REL,'protocol.json'),'utf8'));assert.deepEqual(p,d.protocol);assert.equal(S.sha(JSON.stringify(p.protocol)),p.sha256);assert.deepEqual(p.protocol,S.protocol());const text=report(d);if(check)assert.equal(fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n'),text,'Announcement findings are stale');else fs.writeFileSync(file,text);console.log(check?'Verified full-size announcement findings':'Wrote full-size announcement findings');}
module.exports={report};if(require.main===module)main(process.argv.includes('--check'));
