'use strict';
const S=require('./statistics.cjs');
const money=x=>Number.isFinite(x)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x):'—';
const pct=x=>Number.isFinite(x)?(100*x).toFixed(2)+'%':'—';
const ci=x=>x?x.map(money).join(' to '):'—';
const table=(heads,rows)=>'| '+heads.join(' | ')+' |\n| '+heads.map(()=>'---').join(' | ')+' |\n'+rows.map(r=>'| '+r.join(' | ')+' |').join('\n')+'\n';
function markdown(doc){
 let out='# Third-plus reverse splits: signal study\n\nBuilt '+doc.built_at+'. Prices through '+doc.price_asof+'. Research only; no production authority.\n\n';
 out+='## Result\n\n';
 out+=doc.finalists.length?'The historical gates retained '+doc.finalists.join(', ')+' for further shadow research. This is not verified executable profitability.\n\n':'No rule met every preregistered evidence and risk gate. The report identifies exploratory differences without calling them an optimal live strategy.\n\n';
 out+='The primary comparison uses a $1 million reference NAV, 20 sessions, 1% recorded share-volume/ADV participation, strict restricted/unknown SSR exclusion and conditional historical prices. The $25,000 target is reduced by the declared capital and volume constraints; it is not a promise of $25,000 fills. Ten sessions is the replication. Same issuer history, whole-share sizing, persistent loan/share liabilities and fee/carry mechanics are reused. Independently verified borrow entries remain zero.\n\n';
 out+='## Source and feature coverage\n\nAll '+doc.coverage_candidates+' candidate events are counted here; portfolio maturity, price, restriction and risk exclusions occur later.\n\n';
 out+=table(['Feature','Pass','Fail','Unknown'],Object.entries(doc.coverage).map(([k,v])=>[k,v.pass,v.fail,v.unknown]));
 out+='\nIndependent financing reviews: '+doc.audit.independent_financing_reviews+'. Cached financing documents audited: '+doc.audit.financing_documents+'; those with completion-language leads: '+doc.audit.completion_claim_documents+'. Leads, provider flags, signatures and semantic classification do not establish independently reconciled share issuance or cash proceeds. S2-dependent rules remain insufficient while those reviews are absent.\n\n';
 out+='S1 uses unrestricted cash and a matched annual or annual-plus-YTD TTM operating cash-flow construction. Known unresolved financing and provider financing flags block pro forma cash selection. Its remaining estimates are conditional on incomplete cache coverage; an undiscovered transaction could change them. S4 requires comparable same-filing period-end common shares, with a source clause when actions cross the measurement window. It never substitutes EPS weighted-average shares.\n\n';
 out+='## Primary rule comparison\n\nThe covered baseline has exactly the input availability needed for that rule. Compare both incremental columns: total profit can change merely because a feature is missing for some issuers. Intervals resample issuer-level differences and six-month calendar blocks of this already explored history. Holm adjusts the 11 new primary claims; these are development diagnostics, not a fresh confirmatory experiment.\n\n';
 out+=table(['Rule','Trades / issuers','Net P&L','Delta vs all','Delta vs covered','Worst drawdown','Monthly mean','Holm p','Status'],doc.primary.map(r=>[
 r.arm,r.summary.entered+' / '+r.summary.issuers,money(r.summary.net_pnl),money(r.vs_all.incremental_net),money(r.vs_covered.incremental_net),
 money(r.summary.max_drawdown_dollars),money(r.summary.common_mean_monthly),r.holm_p==null?'—':r.holm_p.toFixed(3),r.decision.status]));
 out+='\n'+table(['Rule','Issuer interval: incremental total','Calendar-block interval: incremental total','Open positions / liability','Main gate failures'],doc.primary.map(r=>[
 r.arm,ci(r.vs_all.issuer_bootstrap_95),ci(r.vs_all.calendar_block_total_95),r.summary.open_positions+' / '+money(r.summary.open_liability),r.decision.reasons.join(', ')||'—']));
 out+='\nMonthly averages use the same '+doc.common_months+' months beginning '+doc.common_first+' for every rule, including zero months. They are not forecast income. Closed and unresolved marked P&L remain separate in summary.json and local ledgers.\n\n';
 out+='## Ten-session replication\n\n';
 out+=table(['Rule','Trades / issuers','Net P&L','Max drawdown','Worst trade','Open liability'],doc.replication.map(r=>[r.arm,r.entered+' / '+r.issuers,money(r.net_pnl),money(r.max_drawdown_dollars),money(r.worst_trade),money(r.open_liability)]));
 out+='\n## Fill and cost sensitivities\n\nFull-size results have no capital admission cap. Recorded-volume cases are execution proxies; observed daily turnover is not pre-entry information or a locate. The passive-capture proxy is labeled unsupported and is never represented as legal-compliance or queue evidence. Strict SSR uses the existing status cache reconstructed at the entry open.\n\n';
 out+=table(['Rule','Horizon','Volume cap','Cost','SSR','Net P&L','Mean position','Max drawdown'],doc.sensitivities.map(r=>[
 r.arm,r.horizon,r.cap===null?'full target':pct(r.cap),r.cost,r.ssrMode,money(r.net_pnl),money(r.mean_position),money(r.max_drawdown_dollars)]));
 out+='\nCosts: lower 1% execution / 20% APR; base 1.72% / 50%; stress 4.25% / 150%; depth base 1.72% plus 4.23% times sqrt(order/$25k), capped at 80%, / 50% APR. Rates and depths are assumptions, not historical broker bills. Dividends, locate fees, servicing and forced-buy-in cash flows remain unobserved. Existing dated SEC/TAF fees are a frozen scenario.\n\n';
 out+='## Equal account-capital and stress budgets\n\nEach account uses a +200% price-rise stress, 0.5% NAV per-name loss reserve, 2% NAV sleeve reserve, three-name limit and 20% margin buffer. This implies nominal admission limits of 0.25% NAV per name and 1% NAV across the sleeve before other-system reservations. Other-system stress is set to zero for these conditional accounts; production use requires actual shared-account reservations. Admission uses prior available marks, not today’s later close. Subsequent mark breaches are flagged; these are not automatic guaranteed exits.\n\n';
 out+=table(['NAV','Rule','Trades','Net P&L','Max drawdown','Peak exposure','Mark breach sessions'],doc.accounts.map(r=>[
 money(r.nav),r.arm,r.entered,money(r.net_pnl),money(r.max_drawdown_dollars),money(r.peak_exposure),r.risk_breach_sessions]));
 out+='\n## Chronology, issuer concentration and controls\n\n';
 out+=table(['Rule','Entry year','Trades / issuers','Marked P&L through cutoff','Unresolved'],doc.primary.flatMap(r=>r.summary.entry_years.map(y=>[r.arm,y.year,y.n+' / '+y.issuers,money(y.net_pnl),y.open])));
 out+='\nEntry-year results include later carry and marks on that cohort through the cutoff. Calendar-month results below instead measure portfolio value changes during each month.\n\n';
 out+=table(['Rule','Without best issuer','Without best five issuers','Worst trade','Worst daily change','Worst adverse price rise'],doc.primary.map(r=>[
 r.arm,money(r.summary.pnl_without_best_issuer),money(r.summary.pnl_without_best5_issuers),money(r.summary.worst_trade),money(r.summary.worst_day),pct(r.summary.worst_adverse_price_return)]));
 out+='\n'+table(['Signal','Complete closed labels / issuers','Controlled coefficient','Cluster 95%','Status'],doc.controls.map(r=>[
 r.arm,r.n+' / '+r.issuers,pct(r.coefficient),r.normal_95?r.normal_95.map(pct).join(' to '):'—',r.status]));
 out+='\nControlled fits use as-of provider magnitude, ordinal 4+, year, log price and log prior ADV. Unresolved labels stay out of these fits and their attrition is explicit; they stay in portfolio liabilities. No controlled association is treated as causal. Provisional CIK/symbol class identity and mechanical action repairs remain limitations.\n\n';
 out+=table(['Diagnostic','Rule','Trades','Net P&L','Max drawdown'],doc.diagnostics.map(r=>[r.kind,r.arm,r.entered,money(r.net_pnl),money(r.max_drawdown_dollars)]));
 out+='\n## Walk-forward selection\n\nEach quarter can use only positions closed and modeled loan returns completed before a 20-session embargo. A rule needs at least 30 prior selected issuers and multiplicity-adjusted positive evidence; otherwise the baseline is retained. All historical years were already explored, so this is a causal development replay, not an untouched test.\n\n';
 out+=table(['Quarter','Training issuers','Selected rule','Reason'],doc.walk_forward.decisions.map(r=>[r.quarter,r.training_issuers,r.arm,r.reason]));
 out+='\nWalk-forward portfolio net P&L: '+money(doc.walk_forward.summary.net_pnl)+'; maximum drawdown '+money(doc.walk_forward.summary.max_drawdown_dollars)+'.\n\n';
 out+='## Delayed-entry and next-open exit stage\n\n'+doc.timing_stage.reason+'\n\n';
 if(doc.timing_stage.models.length)out+=table(['Variant','Rule','Trades','Net P&L','Max drawdown'],doc.timing_stage.models.map(r=>[r.kind,r.arm,r.entered,money(r.net_pnl),money(r.max_drawdown_dollars)]));
 out+='The implemented confirmation observes at most three completed post-split bars, requires a rebound followed by a close below the prior bar low, and enters only at a later session open. Matched delayed and signal-window baselines are supported. The 20% close-risk comparator executes at the following session’s observed open and does not clip gap losses to a stop price. These extra experiments run only for historical finalists.\n\n';
 out+='## Common-window monthly ledger\n\n';
 const selected=['baseline','S3','S5','S7'],months=doc.primary.find(r=>r.arm==='baseline').summary.common_monthly.map(r=>r.month);
 out+=table(['Month',...selected],months.map(m=>[m,...selected.map(id=>money(doc.primary.find(r=>r.arm===id).summary.common_monthly.find(x=>x.month===m)?.pnl))]));
 out+='\n## Forward shadow workflow\n\nProduction authority is none. Frozen shadow policy lists '+doc.finalists.length+' historical finalists. The journal contains '+doc.forward.eligible_decisions+' real enrollments and '+doc.forward.observed_fills+' observed fills; no historical record is fabricated as a prospective forecast.\n\n';
 out+='Manual commands: node _system/scripts/third_plus_signal_study.cjs build; review-import --input <review JSON>; shadow-import --input <evidence JSON>; shadow-status; verify. Review imports need source/issuer/hash bindings and two independent outcome-blinded reviewers. Shadow enrollment freezes aware source clocks, future entry, policy and input hashes; evidence imports preserve a tamper-evident append-only chain. There is no broker or scheduler command.\n\n';
 out+='A minimum future review point is 50 eligible decisions across 30 issuers. That is not statistical proof or permission to trade. The study requires actual approvals, attempts including failures, fills, all costs and reconciled loan returns to assess executable profit.\n\n';
 out+='## Reproduction and validation\n\nLegacy baseline checks: '+doc.validation.baselines.map(r=>r.horizon+' sessions delta '+money(r.delta)).join('; ')+'. The original accounting fixtures and new source/clock/missing-data/journal/portfolio tests are in the test suite. Protocol, source hashes, model manifest and audit aggregates are saved with this report. Raw source extracts, features, per-event returns, and full position ledgers remain in the ignored local directory.\n\n';
 out+='No designated sealed holdout was opened. No paid downloads, Gateway sockets, production policy changes or live orders occurred. No current rate or borrow quantity is backfilled into history. New entries require a fresh verified security and broker evidence even where a conditional historical feature passes.\n';
 return out;
}
function html(doc,md,curves){
 const esc=x=>String(x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 let body='',inTable=false,header=false;
 for(const line of md.split('\n')){
  if(line.startsWith('| ')){
   if(line.startsWith('| ---'))continue;
   if(!inTable){body+='<div class="scroll"><table>';inTable=true;header=true;}
   const tag=header?'th':'td';body+='<tr>'+line.slice(2,-2).split(' | ').map(v=>'<'+tag+'>'+esc(v)+'</'+tag+'>').join('')+'</tr>';header=false;continue;
  }
  if(inTable){body+='</table></div>';inTable=false;}
  if(/^#{1,3} /.test(line)){const n=line.match(/^#+/)[0].length;body+='<h'+n+'>'+esc(line.slice(n+1))+'</h'+n+'>';}
  else if(line.trim())body+='<p>'+esc(line)+'</p>';
 }
 const series=curves.map((r,i)=>({arm:r.arm,color:['#146a87','#b35629','#5f668f','#397b4e'][i],days:r.daily.filter(x=>x.date>=doc.common_first)}));
 const all=series.flatMap(s=>s.days.map(d=>d.pnl)),lo=Math.min(0,...all),hi=Math.max(0,...all),span=Math.max(1,hi-lo),zero=20+hi/span*250;
 const svg='<svg viewBox="0 0 1100 330" role="img" aria-label="Primary conditional cumulative net profit by fixed signal"><line x1="85" x2="1080" y1="'+zero+'" y2="'+zero+'" stroke="#aaa"/>'+series.map(s=>'<polyline fill="none" stroke="'+s.color+'" stroke-width="2" points="'+s.days.map((d,i)=>(85+i/Math.max(1,s.days.length-1)*995).toFixed(1)+','+(20+(hi-d.pnl)/span*250).toFixed(1)).join(' ')+'"/>').join('')+'<text x="0" y="20">'+money(hi)+'</text><text x="0" y="270">'+money(lo)+'</text>'+series.map((s,i)=>'<text x="'+(100+i*220)+'" y="320" fill="'+s.color+'">'+s.arm+'</text>').join('')+'</svg>';
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Third-plus reverse split signal study</title><style>body{max-width:1350px;margin:36px auto;padding:0 24px;font:16px/1.55 system-ui,sans-serif;color:#183043;background:#f8fafc}h1{font-size:34px;line-height:1.2}h2{margin-top:38px;padding-top:22px;border-top:1px solid #d0dce3}.scroll{overflow:auto}table{border-collapse:collapse;font-size:13px;width:100%;background:white}th,td{padding:9px 11px;text-align:left;border-bottom:1px solid #dce5e9;white-space:nowrap}th{background:#e4eef4}svg{width:100%;background:white;border:1px solid #d0dce3}svg text{font-size:13px}p{max-width:1100px}@media print{body{margin:8px;font-size:11px}tr{break-inside:avoid}}</style><div class="chart">'+svg+'</div>'+body+'</html>';
}
module.exports={markdown,html,money,pct};
