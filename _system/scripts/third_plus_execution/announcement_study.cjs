'use strict';
// Announcement-triggered assumption study. Existing post-effective publications remain frozen.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{DatabaseSync}=require('node:sqlite');
const A=require('../short_framework/adapters.cjs'),F=require('../third_plus_signal/features.cjs');
const E=require('./assumed_backtest.cjs'),Identity=require('./identity.cjs'),Archive=require('./venue_archive.cjs'),{loadContext}=require('./venue_study.cjs');
const Features=require('./announcement_features.cjs');
const ROOT=path.resolve(__dirname,'../../..'),REL='_system/data/reverse_splits/third_plus_signal_study/announcement_full_v8';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex'),read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const sum=xs=>xs.reduce((a,b)=>a+b,0),DAY=86400000;
function etDay(at){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(at));}
function bounds(ctx,day){const s=ctx.sessionBounds?.get(day);return s||{open:E.clock(day,9,30),close:E.clock(day,16,0)};}
function arrival(ctx,known,mode='asap',delay=0){
 const available=Date.parse(known)+delay*1000;if(!Number.isFinite(available))throw Error('Invalid public clock');
 for(const day of ctx.prices.days){const b=bounds(ctx,day);if(b.close-15*60000<=available)continue;
  if(mode==='next_open'&&b.open<=available)continue;
  const at=Math.max(b.open+60000,available);if(at>=b.close-15*60000)continue;
  return {day,at,end:Math.min(at+3600000,b.close-15*60000),open:b.open,close:b.close};
 }return null;
}
function history(ctx){
 const m=new Map();
 const original=ctx.events.filter(e=>e.family==='split').map(e=>({issuer:e.issuer,day:e.event_date,known:e.known_at})).concat(ctx.catalogue.filter(e=>['primary_schedule_matched','structured_corporate_action'].includes(e.verification)&&e.issuer?.startsWith('cik/')&&e.ratio>0&&e.ratio<1).map(e=>({issuer:e.issuer,day:e.ex_date,known:e.available_at})));
 const corrected=original.map(e=>{const action=(ctx.announcementActionLedger||[]).find(a=>a.issuer===e.issuer&&[a.declared_date,a.scheduled_date,...(a.superseded_dates||[])].includes(e.day));return action?{...e,day:action.ex_date}:e;});
 for(const e of corrected.concat(ctx.announcementActionHistory||[])){
  if(!e.known||!Number.isFinite(Date.parse(e.known))||ctx.announcementForwardActionKeys?.has(e.issuer+'|'+e.day))continue;const k=e.issuer+'|'+e.day,old=m.get(k);if(!old||Date.parse(e.known)<Date.parse(old.known))m.set(k,e);
 }return [...m.values()];
}
function ordinal(past,issuer,known,eventDate=null){const at=Date.parse(known),day=etDay(at),before=eventDate&&eventDate<day?eventDate:day;return 1+new Set(past.filter(e=>e.issuer===issuer&&e.day<before&&Date.parse(e.known)<=at).map(e=>e.day)).size;}
function definiteClause(audit,scheduled){
 const docs=[audit,...(audit.documents||[])],clauses=docs.flatMap(d=>d.dated_actions||[]).filter(x=>x.date===scheduled).map(x=>x.clause||'');
 return clauses.some(s=>require('./announcement_actions.cjs').operative(s));
}
function loadInputs(sourceRoot,ctx){
 const input=path.join(sourceRoot,'_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z/input.sqlite');
 const db=new DatabaseSync(input,{readOnly:true});
 try{
  // Indexed in memory: wrapping accession columns in SQL REPLACE caused a quadratic join.
  const clocks=new Map();for(const h of db.prepare('SELECT accession,cik,accept_time FROM edgar_hits WHERE accept_time IS NOT NULL').all()){
   if(!h.cik||!Number.isFinite(Date.parse(h.accept_time))||!/(Z|[+-]\d\d:\d\d)$/.test(h.accept_time))continue;
   const k=Number(h.cik)+'/'+h.accession.replace(/-/g,''),old=clocks.get(k);if(!old||Date.parse(h.accept_time)<Date.parse(old))clocks.set(k,h.accept_time);
  }
  const past=history(ctx),rows=db.prepare("SELECT * FROM disclosures WHERE 1=1 AND filed_at<='2026-10-12' ORDER BY filed_at,accession").all();
  const episodes=new Map(),episodeLinks=new Map(),counts={scheduled_rows:rows.filter(r=>r.filed_at>='2023-01-01').length,lookback_rows:rows.filter(r=>r.filed_at<'2023-01-01').length,exact_metadata_rows:0,missing_schedule:0,non_event_report_excluded:0,fund_disclosures_excluded:0,late_historical_disclosure:0,invalid_ratio:0,unknown_ratio_included:0,unbound_or_proposal_clause:0,duplicates:0,revisions_folded:0};
  for(const r of rows){
   if(!r.cik||!r.ticker){counts.missing_schedule++;continue;}if(!require('./announcement_actions.cjs').eventReport(ctx.announcementEventForms?.get(r.accession.replaceAll('-','')))){counts.non_event_report_excluded++;continue;}if(ctx.announcementForwardADS?.has(r.accession))continue;
   if(ctx.announcementExcludedIssuers?.has('cik/'+String(Number(r.cik)))){counts.fund_disclosures_excluded++;continue;}
   const audit=JSON.parse(r.audit_json||'{}'),sourceRecord=ctx.announcementSourceRecords?.get(r.accession),schedule=sourceRecord?.announced_schedule,declared=schedule?.declared_date||r.scheduled,trading=schedule?.day||declared;
   if(!schedule){counts.unbound_or_proposal_clause++;continue;}
   if(!sourceRecord?.declared_factor&&r.ratio!==null&&!(r.ratio>0&&r.ratio<1)){counts.invalid_ratio++;continue;}
   if(r.ratio===null)counts.unknown_ratio_included++;
   const cik=String(Number(r.cik)),exact=clocks.get(cik+'/'+r.accession.replace(/-/g,''));if(exact)counts.exact_metadata_rows++;
   let known=exact||r.available_at,clockBasis=exact?'SEC_acceptance_metadata_publication_proxy':'next_day_conservative_filing_date',featureFreeze=null;const news=sourceRecord?.news_date;if(news){const end=A.nyClock(news.day,'23:59:59');if(Date.parse(end)<Date.parse(known)){known=end;featureFreeze=A.nyClock(news.day,'00:00:00');clockBasis='prior_original_press_release_date_EOD_assumption';}}if(!known||!Number.isFinite(Date.parse(known)))continue;
   if(ctx.announcementForwardActionKeys?.has('cik/'+cik+'|'+trading))continue;if(etDay(known)>trading){counts.late_historical_disclosure++;continue;}
   const issuer='cik/'+cik,n=ordinal(past,issuer,known,trading);
   const physicalAction=(ctx.announcementActionLedger||[]).find(a=>a.issuer===issuer&&[a.ex_date,a.declared_date,a.scheduled_date,...(a.superseded_dates||[])].some(d=>[trading,declared].includes(d))),rawKey=issuer+'|'+(physicalAction?.ex_date||trading),priorKey=(sourceRecord?.superseded_dates||[]).map(d=>issuer+'|'+d).find(k=>episodes.has(k));if(priorKey){episodeLinks.set(rawKey,priorKey);counts.revisions_folded++;continue;}if(physicalAction&&etDay(known)>physicalAction.ex_date){counts.late_historical_disclosure++;continue;}const key=episodeLinks.get(rawKey)||rawKey;
   const symbol=sourceRecord?.symbol;
   const e={id:'announcement/'+cik+'/'+trading,issuer,cik,ticker:symbol?.ticker||r.ticker,original_source_ticker:r.ticker,event_date:declared,announced_trading_day:trading,original_parser_schedule:r.scheduled,known_at:known,ordinal:n,
    source_url:'https://www.sec.gov/Archives/edgar/data/'+cik+'/'+r.accession.replace(/-/g,'')+'/'+r.accession.replace(/^(\d{10})(\d{2})(\d{6})$/,'$1-$2-$3')+'-index.htm',
    clock_basis:clockBasis,sec_accepted_at:exact||null,primary_news_date:news?.day||null,news_date_source_quote:news?.clause||null,feature_freeze_at:featureFreeze,accession:r.accession,
    source_text_sha256:audit.input_text_sha256||null,announcement_ratio:sourceRecord?.declared_factor?.factor?1/sourceRecord.declared_factor.factor:r.ratio,
    scope:'automated_scheduled_action_clause_requires_review',same_security:symbol?.basis||'cached_CIK_ticker_assumption'};
   if(episodes.has(key))counts.duplicates++;
   if(!episodes.has(key)||Date.parse(known)<Date.parse(episodes.get(key).known_at))episodes.set(key,e);
  }
  const all=[...episodes.values()].sort((a,b)=>Date.parse(a.known_at)-Date.parse(b.known_at)||a.id.localeCompare(b.id));
  const full=all.filter(e=>etDay(e.known_at)>='2023-01-01');
  function episodeDates(e){const dates=new Set([e.event_date,e.announced_trading_day,e.original_parser_schedule].filter(Boolean));for(const a of ctx.announcementActionLedger||[])if(a.issuer===e.issuer&&[a.ex_date,a.declared_date,a.scheduled_date,...(a.superseded_dates||[])].some(d=>dates.has(d))){dates.add(a.ex_date);dates.add(a.declared_date);if(a.scheduled_date)dates.add(a.scheduled_date);}return dates;}
  const byKey=new Map();for(const e of all)for(const d of episodeDates(e))if(!byKey.has(e.issuer+'|'+d))byKey.set(e.issuer+'|'+d,e);
  const matched=ctx.candidates.filter(c=>!ctx.announcementExcludedIssuers?.has(c.issuer)).map(c=>{
   if(ctx.announcementForwardActionKeys?.has(c.issuer+'|'+c.event_date))return null;const found=byKey.get(c.issuer+'|'+c.event_date),raw=ctx.events.find(e=>e.id===c.id),acc=(raw?.source_url?.match(/\/data\/\d+\/(\d{18})\//)||[])[1],cik=c.issuer.split('/')[1],exact=acc?clocks.get(cik+'/'+acc):null;
   const provider={...c,cik,known_at:exact||c.known_at,clock_basis:exact?'SEC_acceptance_metadata_publication_proxy':'provider_next_day_filing_clock',source_url:c.source_url,announcement_ratio:1/c.multiple};
   if(!found&&acc&&ctx.announcementEventForms?.has(acc)&&!require('./announcement_actions.cjs').eventReport(ctx.announcementEventForms.get(acc)))return null;if(!found)return null;const e=found;
   return {...e,id:'matched/'+c.id,original_id:c.id,original_day:(()=>{const a=(ctx.announcementActionLedger||[]).find(a=>a.issuer===c.issuer&&episodeDates(e).has(a.ex_date));return a?(ctx.prices.days.find(d=>d>a.ex_date)||c.day):c.day;})(),original_ordinal:c.ordinal,ordinal:ordinal(past,c.issuer,e.known_at,e.announced_trading_day||c.event_date),cohort:'completed_event_matched'};
  }).filter(Boolean);
  const matchedUnique=[...new Map(matched.map(e=>[e.issuer+'|'+e.announced_trading_day,e])).values()];
  const completed=new Set(ctx.candidates.map(c=>c.issuer+'|'+c.event_date));
  for(const e of full)e.completed_cohort_match=[...episodeDates(e)].some(d=>completed.has(e.issuer+'|'+d));
  return {full,matched:matchedUnique,counts,past,input_file:input};
 }finally{db.close();}
}
function signal(ctx,e,decisionAt,facts){
 ctx.announcementSignalCache??=new Map();const key=[e.issuer,e.ticker,e.event_date,e.announced_trading_day||'',decisionAt].join('|');
 if(!ctx.announcementSignalCache.has(key))ctx.announcementSignalCache.set(key,Features.snapshot(ctx,e,decisionAt,facts,ctx.announcementPast||[]));
 return ctx.announcementSignalCache.get(key);
}
function price(ctx,e,clock,session){
 const b=bounds(ctx,clock.day),completed=(session?.bars||[]).filter(x=>x[0]*1000+1000<=clock.at&&clock.at-(x[0]*1000+1000)<=60000).at(-1);
 const quote=(session?.quotes||[]).filter(x=>x[0]*1000<=clock.at&&clock.at-x[0]*1000<=1000&&x[1]>0&&x[2]>=x[1]).at(-1);
 if(quote)return {price:(quote[1]+quote[2])/2,basis:'captured_prearrival_quote',intraday_proxy:false};
 if(completed)return {price:completed[4],basis:'completed_prearrival_venue_bar',intraday_proxy:false};
 const op=ctx.auction(e.ticker,clock.day).open;
 if(op>0&&clock.at>=b.open)return {price:op,basis:clock.at<=b.open+60000?'observed_session_open':'known_open_intraday_proxy',intraday_proxy:clock.at>b.open+60000};
 const prior=ctx.prices.days.filter(d=>d<=clock.day).reverse().find(d=>Features.closeObservation(ctx,e.ticker,d,clock.at));
 if(prior){const f=ctx.factor(e.ticker,prior,clock.day);if(f>0)return {price:Features.closeObservation(ctx,e.ticker,prior,clock.at).price*f,basis:'adjusted_prior_close_proxy',intraday_proxy:true};}
 // Missing all earlier prices: neutralize the unobserved interval with a labeled pricing estimate.
 // This later mark is never admitted to the announcement-time selection snapshot.
 const i=ctx.prices.index?.get(clock.day)??ctx.prices.days.indexOf(clock.day);for(const later of i>=0?ctx.prices.days.slice(i,i+20):[]){const value=ctx.auction(e.ticker,later).close||ctx.prices.point(e.ticker,later)?.close,f=ctx.factor(e.ticker,clock.day,later);if(value>0&&f>0)return {price:value/f,basis:'subsequent_price_back_adjusted_imputation',intraday_proxy:true,imputed:true,imputation_source_day:later};}
 return {price:5,basis:'unpriced_security_5_dollar_proxy',intraday_proxy:true,imputed:true,imputation_source_day:null};
}
function indexSessions(archive){
 const index=new Map();for(const s of archive.sessions.values()){const k=s.issuer+'|'+s.source_ticker+'|'+s.date,list=index.get(k)||[];list.push(s);index.set(k,list);}return index;
}
function sessionAt(index,e,day,start,end,allowPartial=false){
 const ticker=Identity.resolve({...e,day},day).ticker,list=index.get(e.issuer+'|'+ticker+'|'+day)||[];
 const complete=list.find(s=>!s.data_gaps?.length&&(s.capture_start_ms??s.open_ms)<=start&&(s.capture_end_ms??s.close_ms)>=end);if(complete)return complete;if(!allowPartial||!list.length)return null;
 const unique=(rows,key)=>[...new Map(rows.map(x=>[key(x),x])).values()].sort((a,b)=>key(a)-key(b));return {...list[0],bars:unique(list.flatMap(s=>s.bars||[]),x=>x[0]),quotes:unique(list.flatMap(s=>s.quotes||[]),x=>x[0]),statuses:unique(list.flatMap(s=>s.statuses||[]).filter(x=>x.available_ms<=end),x=>x.available_ms),data_gaps:[{kind:'announcement_window_missing'}]};
}
function executeTrade(ctx,index,e,timing,size,scenario,facts,holding='entry20'){
 const delay=timing==='announce_5m'?300:0;
 let clock=arrival(ctx,e.known_at,timing==='next_open'?'next_open':'asap',delay);
 if(timing==='post_effective'){
  const original=e.original_day||ctx.prices.days.find(d=>d>e.event_date&&bounds(ctx,d).open>Date.parse(e.known_at)+300000);
  clock=original?{day:original,at:bounds(ctx,original).open+60000,end:bounds(ctx,original).open+61*60000,...bounds(ctx,original)}:null;
 }
 const decision=clock?(timing==='post_effective'?clock.at-6*60000:Date.parse(e.feature_freeze_at||e.known_at)+(e.feature_freeze_at?0:delay*1000)):Date.parse(e.feature_freeze_at||e.known_at);
 const signals=signal(ctx,e,decision,facts);
 if(!clock||clock.day<'2023-01-01'||Date.parse(e.known_at)>Date.parse('2026-10-13T04:00:00Z'))return {id:e.id,issuer:e.issuer,ticker:e.ticker,day:null,status:'not_yet_eligible',daily:[],entry:null,close_day:null,signals,arrival_ms:null};
 let horizon=20;
 if(holding==='scheduled_split20'){
  const post=e.announced_trading_day?ctx.prices.days.find(d=>d>=e.announced_trading_day):ctx.prices.days.find(d=>d>e.event_date),planned=ctx.prices.index.get(post),i=ctx.prices.index.get(clock.day);
  if(planned!==undefined&&planned+19<i)return {id:e.id,issuer:e.issuer,ticker:e.ticker,day:null,status:'not_yet_eligible',reason:'scheduled_exit_already_passed',daily:[],entry:null,close_day:null,signals,arrival_ms:null};
  horizon=planned===undefined?ctx.prices.days.length-i+20:planned+19-i+1;
 }
 const session=sessionAt(index,e,clock.day,clock.at,clock.end,true),initial=price(ctx,e,clock,session);
 const stressDiscount=initial.intraday_proxy&&scenario==='stress'?.1:0;
 const c={...e,day:clock.day,i:ctx.prices.index.get(clock.day),entry_price:initial.price*(1-stressDiscount),adv_shares:ctx.prices.prior(e.ticker,clock.day).adv||0};
 const entrySession=session?{...session,bars:session.bars,quotes:session.quotes,statuses:session.statuses,open_ms:clock.at-60000,close_ms:clock.close}: {open_ms:clock.at-60000,close_ms:clock.close,bars:[],quotes:[],statuses:[],data_gaps:[{kind:'announcement_window_missing'}]};
 const sessions={get:key=>{
  if(key===c.id)return entrySession;
  const day=key.split('|').at(-1);if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return null;
  const b=bounds(ctx,day);const found=sessionAt(index,c,day,b.close-90*60000,b.close-15*60000,true);return found?{...found,open_ms:b.open,close_ms:b.close}:null;
 }};
 const trade=require('./announcement_accounting.cjs').trade(ctx,sessions,c,{...E.SCENARIOS[scenario],quantity:size==='one_share'?1:null,target_usd:100000,horizon,event_allowance:scenario==='favorable'?0:scenario==='stress'?.05:.01,distribution_actions:(ctx.announcementDistributionActions||[]).filter(a=>a.issuer===e.issuer),cash_return_days:(ctx.announcementCashNeutralActions||[]).filter(a=>a.issuer===e.issuer).map(a=>a.day)});
 const actionGaps=(ctx.announcementActionGaps||[]).filter(g=>g.ticker===e.ticker&&clock.day<=g.day&&g.day<=(trade.close_day||ctx.prices.last));
 return {...trade,initial_basis:initial.basis,signals,arrival_ms:clock.at,entry_end_ms:clock.end,initial_price_basis:initial.basis,intraday_price_proxy:initial.intraday_proxy,entry_price_discount:stressDiscount,price_imputed:!!initial.imputed,imputation_source_day:initial.imputation_source_day||null,holding,ordinal_at_announcement:e.ordinal,clock_basis:e.clock_basis,unresolved_action_gaps:actionGaps};
}
function admit(ctx,trades,capacity='three'){
 const accepted=[],audit=[];
 for(const t of trades.slice().sort((a,b)=>(a.arrival_ms??Infinity)-(b.arrival_ms??Infinity)||a.id.localeCompare(b.id))){
  if(!t.day||t.status==='not_yet_eligible'){audit.push({id:t.id,status:'not_yet_eligible'});continue;}
  const open=accepted.filter(p=>p.entry?.filled_shares&&(!p.close_day||p.close_day>=t.day));
  const pending=accepted.filter(p=>p.day===t.day&&p.entry_end_ms>t.arrival_ms);
  const occupied=new Set([...open,...pending].map(p=>p.issuer));
  const status=capacity==='unlimited'?t.status:occupied.has(t.issuer)?'issuer_open':occupied.size>=3?'name_limit':t.status;
  audit.push({id:t.id,status});if(['issuer_open','name_limit'].includes(status))continue;accepted.push(t);
 }
 const summary=E.portfolio(ctx,accepted,{independent:true,maximum_names:Infinity,first:'2023-01-01'});
 summary.selected=trades.length;summary.name_limit=audit.filter(x=>x.status==='name_limit').length;summary.issuer_open=audit.filter(x=>x.status==='issuer_open').length;summary.not_yet_eligible=audit.filter(x=>x.status==='not_yet_eligible').length;
 delete summary.decisions;
 summary.intraday_proxy_entries=accepted.filter(t=>t.entry?.filled_shares&&t.intraday_price_proxy).length;
 summary.exact_metadata_entries=accepted.filter(t=>t.entry?.filled_shares&&t.clock_basis==='SEC_acceptance_metadata_publication_proxy').length;
 summary.unresolved_action_paths=accepted.filter(t=>t.entry?.filled_shares&&t.unresolved_action_gaps?.length).length;
 summary.daily_range_liability_proxy=summary.peak_intraday_high_liability;delete summary.peak_intraday_high_liability;summary.next_price_imputations=accepted.filter(t=>t.entry?.filled_shares&&t.initial_price_basis==='subsequent_price_back_adjusted_imputation').length;summary.price_imputed_entries=accepted.filter(t=>t.entry?.filled_shares&&t.price_imputed).length;summary.price_imputed_net_pnl=sum(accepted.filter(t=>t.entry?.filled_shares&&t.price_imputed).map(t=>t.net_pnl));summary.pnl_without_price_imputation=summary.net_pnl-summary.price_imputed_net_pnl;for(const k of ['event_allowance','capital_repayment']){summary.costs[k]=sum(accepted.filter(t=>t.entry?.filled_shares).map(t=>t.costs[k]||0));summary.gross_before_costs+=summary.costs[k];}
 summary.mean_hold_sessions=summary.entered?sum(accepted.filter(t=>t.entry?.filled_shares).map(t=>t.daily.filter(d=>d.open).length+1))/summary.entered:0;
 return {summary,accepted,audit};
}
function protocol(){return {schema:'announcement_full_protocol.v8',research_only:true,production_authority:'none',first:'2023-01-01',market_through:'2026-10-12',
 sizes:['usd100k'],target_usd:100000,live_initial_shares:1,scenarios:Object.keys(E.SCENARIOS),capacities:['three','unlimited'],ordinal_groups:['all','first','second','third_plus'],arms:Features.arms(),filters:Object.fromEntries(Features.arms().map(a=>[a.id,a.requires])),
 timing:['announce_now','announce_5m','next_open','post_effective'],holdings:['entry20','scheduled_split20'],
 assumptions:['Every qualifying name is assumed borrowable and accessible. Same base/favorable/stress costs and partial-fill rules as the existing assumption study.',
 'Earlier action-specific original press-release dates in cached event-report exhibits are usable at 23:59:59 New York time, a conservative date-only availability assumption. Their announcement features are frozen at the start of that date to avoid incorporating unknown-hour news reactions. Exact SEC clocks remain the fallback; all three announcement entry variants use the same frozen feature snapshot for date-only releases.',
 'SEC acceptance is a timestamped public-disclosure proxy, not proof of the earliest press release or dissemination instant. Zero and five-minute delays are timing assumptions; missing timestamps use conservative next-day filing availability.',
 'Only regular-session execution: at least 09:31, within a 60-minute entry window ending no later than 15 minutes before the actual close. After-hours news waits for the next regular session.',
 'Every fundamental and price screen is rebuilt at the announcement clock. Original weak split-day close is unknown until that day actually finishes; a separately named weak-prior-close screen uses only completed regular-session data or a labeled completed UTC-day-range proxy.',
 'Scheduled-action disclosures are selected without requiring a later completed split. Authorizations/proposals are a different trigger and are excluded. The legacy completed-event cohort is retained separately as a selected-universe comparison.',
 'Captured pre-arrival quotes/bars, official opens and known prior closes take precedence. If all such prices are missing, the separately labeled later-price imputation below is used only for assumed execution/accounting. Future market data never enter the selection screens. The stress scenario discounts unsupported short-entry prices by 10%; actual announcement jumps remain unknown.',
 'The entry20 horizon counts from actual entry; scheduled_split20 counts the originally announced first split-adjusted trading day as session one, even if the split is later changed or never occurs. Missing first-trading-day wording uses the conservative session after its legal effective date.',
 'Backtests use the full $100,000 per-name order target subject to execution limits. One initial share is solely the future live pilot size. Subsequent reverse splits change owed units; paid whole-share cleanup remains included.',
 'First, second and third-plus refer to documented earlier completed actions known at announcement, a lower bound on lifetime history. A current completed split is never counted as its own predecessor.',
 'An independent primary-source action ledger reads issuer reports and action press releases, excluding warrant agreements, tax annexes and draft certificates. It repairs nominal share units and trading dates across the expanded stock universe, excluding authorization ranges, fund share classes and clock strings as ratios. Exact primary ratios require nominal-path corroboration, or an explicit reported-completed action when no pre-event price anchor exists, or a reviewed exact source conversion paired with a cash repayment or spin-off whose distribution prevents a normal nominal price jump; prices never supply a split factor. Funds, ETFs, ETNs and closed-end investment companies are outside the operating-stock universe.',
 'The announcement cohort re-parses all cached 8-K/6-K event reports, including those previously labeled unresolved. A release dateline, shareholder-vote date, proposed effective date and authorization deadline are not market-effective announcements. Forward ADS splits are unit changes, not reverse-split candidates. Every effective-date phrase must bind to its own date occurrence; an older completed split cannot turn a later warrant update or registration-statement date into a new reverse split. Explicit changed-effective-time language links old and new schedules to the same action. A named synthetic repurchase is eligible before ratio publication only when the source explicitly defines it as including a reverse split. Explicitly superseded dates and ratios cannot overwrite the revised actual action. A captured revision folds into a captured earlier announcement of the same action, retaining its original trigger and planned holding clock.',
 'New action data rebuild prior split history and all announcement-time price/share features. Legal and trading dates of the same action count once; a later source-bound unit ledger may join duplicate descriptions without changing the earliest announcement clock or requiring a completed-action match. Remaining source-associated nominal discontinuities are published and counted on affected positions.',
 'Missing-tape cover attempts use a known official open or adjusted prior close, never the later close as if it were known at the attempt. Bounded residual cleanup still uses the explicitly assumed closing-price closeout premium.',
 'Official regular-session auctions anchor opens, closes and adjusted-close signals where present. UTC-day aggregate candles are not regular-session OHLC: their close/range are usable only after UTC day end. Weak prior close may use a labeled completed-daily-range proxy; original split-day weak close requires captured regular-session range. Missing official entry opens use a known prior close, not an unverified UTC-day open.',
 'All original fundamental arms and prespecified combinations are evaluated individually and with the rally screen. Unknown features do not pass. Recent financing and cash-pressure estimates are conditional on cached source coverage and are not independent saleability/completeness proofs.',
 'Three-slot admissions are chronological, keep pending reservations through their windows, and conservatively hold a covered slot until that session ends. Unlimited cases are independent-opportunity diagnostics.',
 'When entry and all earlier prices are missing, the first observed close within 20 sessions is adjusted back into entry share units. This explicitly assumes no unexplained price movement over the missing interval; it is a pricing imputation, never a signal input. A $5 placeholder is retained only if that also fails. The stress short-entry discount applies to both. Every result reports these positions and profit excluding them without refilling slots.',
 'An extra unreconstructed corporate-action allowance is 1% of entry notional in base, zero in favorable and 5% in stress. This is a model-risk cost assumption, not an observed fee. For reviewed conversions with a source-specified cash repayment per old share, that amount is charged as a distribution liability. Otherwise, for consolidations paired with capital repayment or a spin-off, an unknown distribution is settled as an estimated cash-equivalent liability equal to the mechanical unit reduction at the last pre-action mark. This does not model later distributed-security price movements; actual special cash and stock distributions are not exhaustively reconstructed.',
 'Missing-price paths retain explicit assumed prices and closeout premiums; coverage and concentration are published alongside the numbers. No actual fills, borrow terms or untouched holdout are claimed.']};}
module.exports={ROOT,REL,sha,etDay,bounds,arrival,history,ordinal,definiteClause,loadInputs,signal,price,indexSessions,sessionAt,executeTrade,admit,protocol};

function write(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(value)+'\n');}
function calendar(ctx){
 const script="import sys,json,exchange_calendars as x; c=x.get_calendar('XNYS',start=sys.argv[1],end=sys.argv[2]); print(json.dumps({'version':x.__version__,'sessions':[[s.date().isoformat(),int(c.session_open(s).timestamp()*1000),int(c.session_close(s).timestamp()*1000)] for s in c.sessions]}))";
 const out=JSON.parse(require('node:child_process').execFileSync('python',['-c',script,ctx.prices.first,ctx.prices.last],{encoding:'utf8',maxBuffer:2*1024*1024}));
 ctx.sessionBounds=new Map(out.sessions.map(([d,open,close])=>[d,{open,close}]));
 if(ctx.prices.days.some(d=>!ctx.sessionBounds.has(d)))throw Error('Cached price calendar contains an unverified session');return {version:out.version,sha256:sha(JSON.stringify(out))};
}
function factsLoader(sourceRoot,scores={}){return Features.loader(sourceRoot,scores);}
function fileDigest(file){const h=crypto.createHash('sha256'),fd=fs.openSync(file,'r'),b=Buffer.alloc(1024*1024);try{let n;while((n=fs.readSync(fd,b,0,b.length,null)))h.update(b.subarray(0,n));return h.digest('hex');}finally{fs.closeSync(fd);}}
function register(){const file=path.join(ROOT,REL,'protocol.json'),p=protocol();if(fs.existsSync(file)){const old=read(file);if(JSON.stringify(old.protocol)!==JSON.stringify(p))throw Error('Announcement protocol changed; create a new version');return old;}const doc={registered_at:new Date().toISOString(),protocol:p,sha256:sha(JSON.stringify(p))};write(file,doc);return doc;}
function preflight(sourceRoot){const ctx=loadContext(sourceRoot);try{const c=calendar(ctx),actions=require('./announcement_actions.cjs').prepare(sourceRoot,ctx),x=loadInputs(sourceRoot,ctx);const result={action_count:actions.ledger.length,excluded_funds:actions.excluded_issuers.length,remaining_discontinuities:actions.remaining_nominal_discontinuities,...x.counts,full_events:x.full.length,full_issuers:new Set(x.full.map(e=>e.issuer)).size,full_exact:x.full.filter(e=>e.clock_basis==='SEC_acceptance_metadata_publication_proxy').length,full_not_in_completed_cohort:x.full.filter(e=>!e.completed_cohort_match).length,matched_events:x.matched.length,matched_third_at_announcement:x.matched.filter(e=>e.ordinal>=3).length,calendar:c};console.log(JSON.stringify(result));return result;}finally{ctx.prices.close();}}
function build(sourceRoot){return require('./announcement_full_publish.cjs').run(sourceRoot,module.exports);}
function check(){return require('./announcement_full_publish.cjs').check(module.exports);}
Object.assign(module.exports,{calendar,factsLoader,register,preflight,build,check});
if(require.main===module){const i=process.argv.indexOf('--source-root'),root=i>=0?path.resolve(process.argv[i+1]):null;if(process.argv.includes('--check'))check();else if(process.argv.includes('--register'))register();else if(!root)throw Error('--source-root is required');else if(process.argv.includes('--preflight'))preflight(root);else build(root);}
