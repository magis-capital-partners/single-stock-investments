// Pure, replayable research rules. No brokerage, market-data seat, or order dependencies.
export const POLICY = Object.freeze({id:'reverse_split_live.v1',score_method:'as_filed_annual_or_matched_fiscal_ytd.v3',minimum_ordinal:2,minimum_score:60,minimum_signals:3,max_period_age_days:200,holding_sessions:5,timing:'observed_announcement_time',research_only:true,authority:'none'});
export const DAY=86400000;
export const finite=x=>typeof x==='number'&&Number.isFinite(x);
export const etDay=x=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(x));
export const days=(a,b)=>(Date.parse(b)-Date.parse(a))/DAY;
export function iso(value){const t=Date.parse(value);return Number.isFinite(t)?new Date(t).toISOString():null;}
export function easternTime(day,time='00:00:00') {const guess=new Date(day+'T'+time+'Z'),zone=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',timeZoneName:'shortOffset'}).formatToParts(guess).find(p=>p.type==='timeZoneName').value,match=/GMT([+-])(\d+)(?::(\d+))?/.exec(zone),offset=match?(match[1]==='-'?-1:1)*(Number(match[2])*60+Number(match[3]||0))*60000:0;return new Date(guess.getTime()-offset).toISOString();}
export const dateOnlyAvailable=day=>easternTime(new Date(Date.parse(day+'T12:00:00Z')+DAY).toISOString().slice(0,10));
export function decode(value){return String(value||'').replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g,'$1').replace(/&#(x[\da-f]+|\d+);/gi,(_,n)=>{const c=n[0].toLowerCase()==='x'?parseInt(n.slice(1),16):Number(n);return c>0&&c<=0x10ffff?String.fromCodePoint(c):'';}).replace(/&(amp|lt|gt|quot|apos|nbsp);/g,(_,k)=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '}[k]));}
export function plain(raw){return decode(String(raw).replace(/<(script|style|ix:header)\b[\s\S]*?<\/\1>/gi,' ').replace(/<\/(?:p|div|tr|h\d|li)>|<br\s*\/?\s*>/gi,'\n').replace(/<[^>]+>/g,' ')).replace(/[\t\r ]+/g,' ').replace(/\n\s*\n+/g,'\n').trim();}
const field=(text,name)=>decode(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`,'i').exec(text)?.[1]||'').trim();
export function parseFeed(xml,source){
  if(!/<(?:feed|rss|rdf:RDF)\b/i.test(xml))throw new Error('Source did not return an RSS or Atom feed');
  return [...xml.matchAll(/<(entry|item)\b[^>]*>([\s\S]*?)<\/\1>/gi)].map(([, ,body])=>{
    const url=/<link\b[^>]*href=["']([^"']+)["']/i.exec(body)?.[1]||field(body,'link');
    const cik=/\bCIK=(\d+)/i.exec(url)?.[1]||/\/edgar\/data\/(\d+)\//i.exec(url)?.[1]||/CIK[:= ]+(\d+)/i.exec(body)?.[1];
    const accession=/\b(\d{10}-\d{2}-\d{6})\b/.exec(body)?.[1];
    const title=plain(field(body,'title'));
    return {source,url:decode(url),title,published_at:iso(field(body,'published')||field(body,'updated')||field(body,'pubDate')),cik:cik?String(Number(cik)):null,accession,form:/^(8-K(?:\/A)?|6-K(?:\/A)?|10-[KQ](?:\/A)?|20-F(?:\/A)?|40-F(?:\/A)?|DEF\s?14[AC]|PRE\s?14[AC])\s*-/i.exec(title)?.[1]?.replace(/\s/g,'')||null};
  }).filter(x=>/^https:\/\//.test(x.url));
}
const SPLIT=/reverse[\s-]+(?:stock[\s-]+|share[\s-]+)?split|share consolidation|consolidation of.{0,30}shares/i;
const MONTH='January|February|March|April|May|June|July|August|September|October|November|December';
function dates(text){return [...text.matchAll(new RegExp(`(?:${MONTH})\\s+\\d{1,2}(?:st|nd|rd|th)?[,]?\\s+20\\d{2}|20\\d{2}-\\d{2}-\\d{2}`,'gi'))].map(m=>iso(m[0].replace(/(\d)(?:st|nd|rd|th)\b/,'$1'))?.slice(0,10)).filter(Boolean);}
export function classifyAnnouncement(raw,{published_at,form}={}){
  const text=plain(raw),all=text.split(/\n/).filter(p=>SPLIT.test(p));
  const passages=all.length?all:[...text.matchAll(new RegExp(SPLIT.source,'gi'))].map(m=>text.slice(Math.max(0,m.index-220),m.index+1800));
  if(!passages.length)return null;
  const action=passages.filter(p=>/will (?:effect|implement|become|begin)|announces?.{0,140}(?:reverse|consolidation)|has (?:determined|approved)|effective|begin trading/i.test(p));
  const candidates=action.length?action:passages,ratios=new Set(),effective=new Set();
  const words={two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,twelve:12,fifteen:15,twenty:20,thirty:30,forty:40,fifty:50,hundred:100};
  for(const p of candidates){
    for(const m of p.matchAll(/(?:\b1|\bone)[\s-]*(?:for|to|:)[\s-]*(\d[\d,]*(?:\.\d+)?|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|forty|fifty|hundred)\b/gi)){const n=words[m[1].toLowerCase()]||Number(m[1].replaceAll(',',''));if(n>1)ratios.add(n);}
    for(const m of p.matchAll(/(?:effective|begin(?:s)? trading|commence(?:s)? trading|trading.{0,35}(?:begin|commence))[^\n]{0,230}/gi))for(const d of dates(m[0]))effective.add(d);
  }
  const day=published_at?etDay(published_at):null;
  const future=[...effective].filter(d=>!day||d>=day),past=effective.size&&future.length===0;
  const cancelled=candidates.some(p=>/(?:cancel(?:led|ed)?|abandon\w*|will not proceed|not to proceed).{0,140}(?:reverse|consolidation)|(?:reverse|consolidation).{0,140}(?:cancel(?:led|ed)?|abandon\w*)/i.test(p));
  const proposal=/14[AC]/i.test(form||'')||candidates.every(p=>/propos|seek.{0,35}approval|range of|between.{0,60}and|authorize/i.test(p)&&!/will (?:effect|implement|become)|has (?:selected|determined)/i.test(p));
  const conflict=ratios.size!==1||future.length>1;
  const status=cancelled?'cancelled':past?'historical':proposal?'authorization':conflict?'needs_review':!future.length?'needs_review':'scheduled';
  return {status,ratio:ratios.size===1?[...ratios][0]:null,effective_date:future.length===1?future[0]:null,ratio_candidates:[...ratios],date_candidates:[...effective],evidence:candidates.slice(0,4).map(p=>p.slice(0,2800)),reason:cancelled?'Announcement cancelled':past?'References a previously effective split':proposal?'Authorization or proposal; implementation not established':conflict?'Conflicting or missing split terms':!future.length?'Effective date requires source verification':'Ratio and upcoming effective date extracted'};
}
export const ALIASES={revenues:['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax','Revenue'],net_income:['NetIncomeLoss','ProfitLoss','NetIncomeLossAvailableToCommonStockholdersBasic'],operating_income:['OperatingIncomeLoss','ProfitLossFromOperatingActivities'],cfo:['NetCashProvidedByUsedInOperatingActivities','NetCashFlowsFromUsedInOperatingActivities'],cash:['CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents'],total_assets:['Assets'],stockholders_equity:['StockholdersEquity','EquityAttributableToOwnersOfParent','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest','Equity'],long_term_debt:['LongTermDebtNoncurrent','NoncurrentBorrowings','LongTermDebt'],current_debt:['LongTermDebtCurrent','CurrentPortionOfNoncurrentBorrowings']};
const FLOWS=new Set(['revenues','net_income','operating_income','cfo']);
const FORMS=new Set(['10-Q','10-K','10-Q/A','10-K/A','20-F','20-F/A','40-F','40-F/A','6-K','6-K/A']);
export function monetaryFacts(raw,cutoff){
  const candidates=Object.fromEntries(Object.keys(ALIASES).map(k=>[k,[]])),day=etDay(cutoff),currencies={};
  for(const ns of ['us-gaap','ifrs-full','dei'])for(const [metric,aliases] of Object.entries(ALIASES))for(const [rank,tag] of aliases.entries())for(const [unit,rows] of Object.entries(raw.facts?.[ns]?.[tag]?.units||{})){
    if(!/^[A-Z]{3}$/.test(unit))continue;
    for(const r of rows)if(FORMS.has(r.form)&&r.filed&&r.filed.slice(0,10)<day&&r.end&&r.end<=day&&finite(r.val)&&(FLOWS.has(metric)?Boolean(r.start):!r.start))candidates[metric].push({...r,unit,tag:ns+':'+tag,rank,known_at:r.filed.slice(0,10),source:'sec_companyfacts'});
  }
  for(const rows of Object.values(candidates)){if(!rows.length)continue;const latest=rows.map(r=>r.end).sort().at(-1);for(const unit of new Set(rows.filter(r=>r.end===latest).map(r=>r.unit)))currencies[unit]=(currencies[unit]||0)+1;}
  const currency=Object.keys(currencies).sort((a,b)=>currencies[b]-currencies[a]||a.localeCompare(b))[0]||null,metrics={};
  for(const [k,rs] of Object.entries(candidates)){const unique=new Map();for(const r of rs.sort((a,b)=>a.filed.localeCompare(b.filed)||b.rank-a.rank))if(r.unit===currency)unique.set((r.start||'')+'/'+r.end,r);metrics[k]=[...unique.values()];}
  return {metrics,currency,currency_candidates:Object.keys(currencies)};
}
export function trailingYear(rows,end){
  const direct=rows.filter(r=>r.end===end&&days(r.start,end)>=340&&days(r.start,end)<=380).sort((a,b)=>b.filed.localeCompare(a.filed));
  if(direct.length)return {value:direct[0].val,evidence:[direct[0]],method:'reported_annual'};
  const current=rows.filter(r=>r.end===end&&days(r.start,end)>=60&&days(r.start,end)<310).sort((a,b)=>days(b.start,b.end)-days(a.start,a.end));
  for(const cur of current)for(const annual of rows.filter(r=>days(r.start,r.end)>=340&&days(r.start,r.end)<=380&&days(r.end,cur.start)>=0&&days(r.end,cur.start)<=3).sort((a,b)=>b.end.localeCompare(a.end))){const old=rows.filter(r=>r.start===annual.start&&days(r.end,cur.end)>=350&&days(r.end,cur.end)<=380&&Math.abs(days(r.start,r.end)-days(cur.start,cur.end))<=15).sort((a,b)=>b.filed.localeCompare(a.filed))[0];if(old)return {value:cur.val+annual.val-old.val,evidence:[cur,annual,old],method:'matched_fiscal_ytd'};}
  const window=rows.filter(r=>days(r.start,r.end)>=70&&days(r.start,r.end)<=105&&r.end<=end).sort((a,b)=>a.end.localeCompare(b.end)).slice(-4);
  if(window.length===4&&window.at(-1).end===end&&window.slice(1).every((r,i)=>days(window[i].end,r.start)>=0&&days(window[i].end,r.start)<=3)&&days(window[0].start,end)>=340&&days(window[0].start,end)<=380)return {value:window.reduce((a,r)=>a+r.val,0),evidence:window,method:'four_reported_quarters'};
  return null;
}
export function scoreFundamentals(raw,cutoff,expectedCik){
  if(!raw||String(Number(raw.cik))!==String(Number(expectedCik)))return {status:'identity_mismatch_or_missing',score:null,signals:{},evidence:[]};
  const {metrics,currency,currency_candidates}=monetaryFacts(raw,cutoff),flowEnds=[...FLOWS].flatMap(k=>metrics[k].map(r=>r.end)),anchor=(flowEnds.length?flowEnds:Object.values(metrics).flatMap(rs=>rs.map(r=>r.end))).sort().at(-1)||null;
  if(!anchor||days(anchor,etDay(cutoff))<0||days(anchor,etDay(cutoff))>200)return {status:'stale_or_missing_period',score:null,period:anchor,currency,signals:{},evidence:[]};
  const flows={},prior={},balances={},evidence=[];
  for(const k of FLOWS){const cur=trailingYear(metrics[k],anchor);if(cur){flows[k]=cur.value;evidence.push(...cur.evidence);}for(const end of [...new Set(metrics[k].filter(r=>days(r.end,anchor)>=350&&days(r.end,anchor)<=380).map(r=>r.end))].sort().reverse()){const old=trailingYear(metrics[k],end);if(old){prior[k]=old.value;evidence.push(...old.evidence);break;}}}
  for(const k of Object.keys(ALIASES).filter(k=>!FLOWS.has(k))){const r=metrics[k].filter(r=>days(r.end,anchor)>=0&&days(r.end,anchor)<=105).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed))[0];if(r){balances[k]=r.val;evidence.push(r);}}
  const signals={},add=(k,value,zero,full,weight)=>{signals[k]={value,score:Math.max(0,Math.min(1,(value-zero)/(full-zero))),weight};};
  const ni=flows.net_income,cfo=flows.cfo,assets=balances.total_assets,cash=balances.cash,debt=balances.long_term_debt,rev=flows.revenues,oldrev=prior.revenues,oi=flows.operating_income,oldoi=prior.operating_income;
  if(finite(ni)&&finite(cfo)&&assets>0){add('accrual_ratio',(ni-cfo)/assets,0,.1,1);if(ni>0)add('profit_without_cash',1-cfo/ni,0,1,.8);}
  if(finite(cfo)&&cfo<0&&finite(cash)&&cash>=0)add('cash_burn',cash/-cfo,4,1,1.2);
  if(finite(debt)&&assets>0){const total=debt+(balances.current_debt||0);add('leverage',total/assets,.2,.5,1);if((oi||0)<0&&total>0)signals.leverage.score=Math.min(1,signals.leverage.score+.5);if(finite(balances.stockholders_equity)&&balances.stockholders_equity<0)signals.leverage.score=1;}
  if(finite(rev)&&oldrev>0)add('revenue_turn',rev/oldrev-1,0,-.15,.8);
  if(rev>0&&oldrev>0&&finite(oi)&&finite(oldoi))add('margin_trend',oi/rev-oldoi/oldrev,0,-.08,1);
  const values=Object.values(signals),weight=values.reduce((a,r)=>a+r.weight,0),score=values.length>=3&&weight?Math.round(1000*values.reduce((a,r)=>a+r.weight*r.score,0)/weight)/10:null;
  const unique=new Map(evidence.map(r=>[[r.accn,r.tag,r.start,r.end,r.val].join('/'),r]));
  return {status:score===null?'fewer_than_three_independent_signals':'scored',score,period:anchor,currency,currency_candidates,signals,signal_count:values.length,flows,balances,evidence:[...unique.values()],current_debt_reported:finite(balances.current_debt),method:POLICY.score_method,cutoff,limitations:['Date-only financial facts become available on the next Eastern day.','Inherited score has no industry-specific underwriting adjustment.','Unreported current debt is zero in the inherited score and is separately disclosed.']};
}
export function screen(event,financials,prior,now){
  const history=prior.filter(p=>p.cik===event.cik&&p.effective_date<etDay(event.published_at||event.first_seen_at)&&p.known_at<=event.first_seen_at&&p.verified),ordinal=1+new Set(history.map(p=>p.effective_date)).size;
  const checks={announcement:{state:event.status==='scheduled'?'pass':['cancelled','historical','authorization'].includes(event.status)?'fail':'unknown',reason:event.reason},repeat:{state:ordinal>=2?'pass':'unknown',reason:ordinal>=2?'At least one prior completed split is documented':'No prior completed split verified yet',ordinal_min:ordinal},fundamentals:{state:financials.score===null?'unknown':financials.score>=60?'pass':'fail',reason:financials.status,score:financials.score},timing:{state:event.effective_date&&event.effective_date<=etDay(now)?'fail':event.effective_date?'pass':'unknown',reason:'Research must precede the effective split date'}};
  const states=Object.values(checks).map(r=>r.state),result=states.includes('fail')?'fails_screen':states.includes('unknown')?'needs_review':'passes_screen';
  return {result,checks,ordinal_min:ordinal,prior_splits:history,policy:POLICY,decision_at:now,execution_ready:false};
}
