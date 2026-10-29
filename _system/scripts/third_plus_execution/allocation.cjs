'use strict';
// Causal research allocation. Tradability and execution assumptions stay in assumed_backtest.
const Engine=require('./assumed_backtest.cjs'),Identity=require('./identity.cjs');
const sum=a=>a.reduce((s,x)=>s+x,0),pass=(e,k)=>e.signals[k]==='pass';
const FAMILIES={distress:['burn','reported_runway','operating_loss','revenue15','margin8','negative_equity','accrual10'],issuance:['S3','S4'],price:['S5','S6']};
function registry(){
 const policies=[],add=(id,label,requires,extra={})=>policies.push({id,label,requires,target:100000,rank:'id',size:'fixed',risk:false,...extra});
 add('all_100','All candidates · $100k',[]);add('saved_100','Rally veto · $100k',['S7']);add('dilution_100','Dilution · $100k',['S7','S4']);add('burn_100','Cash burn · $100k',['S7','burn']);
 add('repeat_100','Rapid repeat · $100k',['S7','S3']);add('weak_100','Weak close · $100k',['S7','S5']);
 for(const target of [25000,50000])add('burn_'+target/1000,'Cash burn · $'+target/1000+'k',['S7','burn'],{target});
 const overlays={S3:'rapid repeat',S5:'weak close',S4:'dilution',reported_runway:'short runway',operating_loss:'operating loss',revenue15:'revenue decline',margin8:'margin decline',S6:'prior price weakness',negative_equity:'negative equity',accrual10:'accruals',score60:'legacy score'};
 for(const [key,label]of Object.entries(overlays))add('gate_'+key,'Cash burn + '+label,['S7','burn',key]);
 add('gate_both','Cash burn + repeat + weak close',['S7','burn','S3','S5']);
 add('size_repeat','Repeat increases target',['S7','burn'],{size:'repeat'});add('size_weak','Weak close increases target',['S7','burn'],{size:'weak'});
 add('size_core','Repeat / weak-close tiers',['S7','burn'],{size:'core'});add('rank_core','Rank repeat / weak close only',['S7','burn'],{rank:'core'});
 add('both_core','Rank and size repeat / weak close',['S7','burn'],{rank:'core',size:'core'});
 add('shrunk_core','Rank and size · past-issuer shrinkage',['S7','burn'],{rank:'core',size:'core',shrink:true});
 add('daily_uniform','Matched daily budget · uniform',['S7','burn'],{daily:true,target:50000});
 add('daily_rank','Matched daily budget · rank only',['S7','burn'],{daily:true,target:50000,rank:'core'});
 add('daily_size','Matched daily budget · size only',['S7','burn'],{daily:true,target:50000,size:'core'});
 add('daily_both','Matched daily budget · rank and size',['S7','burn'],{daily:true,target:50000,rank:'core',size:'core'});
 add('naive_count','Uncapped correlated signal count',['S7'],{size:'naive',diagnostic_only:true});
 add('group_size','Grouped signals · size only',['S7'],{size:'groups'});add('group_rank','Grouped signals · rank only',['S7'],{rank:'groups'});
 add('group_both','Grouped signals · rank and size',['S7'],{rank:'groups',size:'groups'});add('group_shrunk','Grouped signals · past-issuer shrinkage',['S7'],{rank:'groups',size:'groups',shrink:true});
 add('burn_risk','Cash burn · squeeze-adjusted cap',['S7','burn'],{risk:true});
 add('core_risk','Repeat / weak close · squeeze-adjusted',['S7','burn'],{rank:'core',size:'core',risk:true});
 add('group_risk','Grouped signals · squeeze-adjusted',['S7'],{rank:'groups',size:'groups',risk:true});
 return policies;
}
function scores(e){
 const core=+pass(e,'S3')+ +pass(e,'S5'),groups=Object.values(FAMILIES).map(keys=>+keys.some(k=>pass(e,k)));
 return {core,groups:sum(groups),signature:groups.join(''),core_signature:['S3','S5'].map(k=>e.signals[k]).join('|'),naive:sum([...new Set(Object.values(FAMILIES).flat())].map(k=>+pass(e,k)))};
}
function support(events,e,p){
 const signature=p.size==='groups'?scores(e).signature:scores(e).core_signature;
 return new Set(events.filter(x=>x.i+23<e.i&&p.requires.every(k=>pass(x,k))&&(p.size==='groups'?scores(x).signature:scores(x).core_signature)===signature).map(x=>x.issuer)).size;
}
function desired(events,e,p){
 const s=scores(e);let target=p.target;
 if(p.size==='repeat')target=pass(e,'S3')?100000:25000;
 if(p.size==='weak')target=pass(e,'S5')?100000:25000;
 if(p.size==='core')target=[25000,50000,100000][s.core];
 if(p.size==='groups')target=[25000,25000,50000,100000][s.groups];
 if(p.size==='naive')target=s.naive>=3?100000:s.naive>=2?50000:25000;
 const n=p.shrink?support(events,e,p):null;
 if(p.shrink)target=25000+(target-25000)*Math.min(1,n/20);
 return {target,score:p.rank==='core'?s.core:p.rank==='groups'?s.groups:0,support:n};
}
function risk(ctx,c){
 const i=ctx.prices.index.get(c.day);if(i===undefined)return {shock:2,observations:0};
 let maximum=0,observations=0;
 for(let j=Math.max(1,i-20);j<i;j++){
  const d=ctx.prices.days[j],prev=ctx.prices.days[j-1],t=Identity.resolve(c,d).ticker,pt=ctx.prices.point(t,d),before=ctx.prices.point(Identity.resolve(c,prev).ticker,prev),factor=ctx.factor(t,prev,d);
  if(!pt||!before||!(factor>0))continue;
  maximum=Math.max(maximum,pt.high/(before.close*factor)-1);observations++;
 }
 return {shock:Math.max(2,2*maximum),observations};
}
function waterfill(weights,total,cap=100000){
 const out=weights.map(()=>0),active=new Set(weights.map((_,i)=>i));let remaining=Math.min(total,weights.length*cap);
 while(active.size&&remaining>1e-8){const scale=sum([...active].map(i=>weights[i])),hit=[...active].filter(i=>remaining*weights[i]/scale>=cap);
  if(!hit.length){for(const i of active)out[i]=remaining*weights[i]/scale;break;}
  for(const i of hit){out[i]=cap;remaining-=cap;active.delete(i);}
 }
 return out;
}
function prepareProfile(ctx,c,t,budget){
 const out={...t,budget,shock:c.shock,ready_day:t.close_day?(t.returns||[]).reduce((a,r)=>r.day>a?r.day:a,ctx.settlement(t.day)):null};
 out.entry=t.entry?Object.fromEntries(Object.entries(t.entry).filter(([k])=>!['fills'].includes(k))):null;
 let mark=t.entry?.arrival_mid||1,factor=1;
 out.daily=t.daily.map(row=>{const f=Identity.factor(ctx,c,row.day)||factor;mark*=f/factor;factor=f;const ticker=Identity.resolve(c,row.day).ticker;mark=ctx.auction(ticker,row.day).close||ctx.prices.point(ticker,row.day)?.close||mark;return {...row,mark,factor};});
 delete out.returns;return out;
}
function morning(ctx,t,d){
 // Only yesterday's inventory and today's known opening price can fund admission.
 let row=null;for(const r of t.daily){if(r.day>=d)break;row=r;}
 if(!row?.open)return {open:false,liability:0};
 const ticker=Identity.resolve(t,d).ticker,op=ctx.auction(ticker,d).open||ctx.prices.point(ticker,d)?.open,f=Identity.factor(ctx,t,d)||row.factor;
 return {open:true,liability:op>0?row.liability/row.mark*row.factor/f*op:row.liability};
}
function simulate(ctx,events,policy,getProfile,options={}){
 const o={capacity:'three',budget:'matched',scenario:'base',omit:new Set(),...options},positions=[],audit=[],byDay=new Map();
 const usable=events.filter(e=>!o.omit.has(e.issuer));
 for(const e of usable){const list=byDay.get(e.day)||[];list.push(e);byDay.set(e.day,list);}
 for(const d of [...byDay.keys()].sort((a,b)=>(a||'9999').localeCompare(b||'9999'))){
  const p=typeof policy==='function'?policy(d):policy;if(!p)throw Error('Missing allocation policy');
  const eligible=[];
  for(const e of byDay.get(d)){if(!p.requires.every(k=>pass(e,k))){audit.push({id:e.id,status:'outside_signal',policy:p.id});continue;}if(!e.day||e.i===undefined){audit.push({id:e.id,status:'not_yet_eligible',policy:p.id});continue;}eligible.push({...e,allocation:desired(usable,e,p)});}
  eligible.sort((a,b)=>b.allocation.score-a.allocation.score||a.id.localeCompare(b.id));
  const open=positions.map(t=>({t,...morning(ctx,t,d)})).filter(x=>x.open),issuers=new Set(open.map(x=>x.t.issuer));
  let gross=sum(open.map(x=>x.liability)),squeeze=sum(open.map(x=>x.liability*x.t.allocation_shock));
  const pending=[];
  for(const e of eligible){
   if(o.capacity==='three'&&issuers.has(e.issuer)){audit.push({id:e.id,status:'issuer_open',policy:p.id});continue;}
   if(o.capacity==='three'&&issuers.size>=3){audit.push({id:e.id,status:'name_limit',policy:p.id});continue;}
   pending.push(e);if(o.capacity==='three')issuers.add(e.issuer);
  }
  const daily=p.daily?waterfill(pending.map(e=>e.allocation.target),Math.min(pending.length*50000,o.budget==='matched'?Math.max(0,300000-gross):Infinity)):null;
  for(const [i,e]of pending.entries()){
   const shock=p.risk?e.shock:2,wanted=daily?daily[i]:e.allocation.target;
   const available=o.budget==='matched'?Math.min(Math.max(0,300000-gross),Math.max(0,600000-squeeze)/shock):Infinity;
   const budget=Math.floor(Math.min(100000,wanted,p.risk?200000/shock:Infinity,available)/100)*100;
   if(budget<100){audit.push({id:e.id,status:'budget_limit',policy:p.id,target_usd:0,score:e.allocation.score});continue;}
   const trade=getProfile(e,o.scenario,budget);positions.push({...trade,allocation_policy:p.id,allocation_shock:shock});
   // Reserve requested dollars, even when a later fill would be tiny or absent.
   gross+=budget;squeeze+=budget*shock;
   audit.push({id:e.id,status:trade.status,policy:p.id,target_usd:budget,score:e.allocation.score,support:e.allocation.support,imputed_risk:e.risk_observations<20});
  }
 }
 return {positions,audit};
}
function aggregate(ctx,run,options={}){
 const first=options.first||'2023-01-19',last=options.last||ctx.prices.last,all=run.positions,positions=all.filter(t=>t.entry?.filled_shares),byDay=new Map(),issuerPnls=new Map(),monthly=new Map();
 for(const t of positions){let final=0;for(const r of t.daily){if(r.day>last)break;if(r.day<first){final=r.pnl;continue;}const x=byDay.get(r.day)||{change:0,liability:0,margin:0,peak:0,open:0};x.change+=r.change;x.liability+=r.liability;x.margin+=r.margin||0;x.peak+=r.peak_liability;x.open+=+(r.peak_liability>0);byDay.set(r.day,x);final=r.pnl;}issuerPnls.set(t.issuer,(issuerPnls.get(t.issuer)||0)+final);}
 let pnl=0,peak=0,dd=0,gross=0,margin=0,concurrent=0,high=0,breaches=0;const daily=[];
 for(const d of ctx.prices.days){if(d<first||d>last)continue;const r=byDay.get(d)||{change:0,liability:0,margin:0,open:0,peak:0};pnl+=r.change;peak=Math.max(peak,pnl);dd=Math.min(dd,pnl-peak);gross=Math.max(gross,r.liability);margin=Math.max(margin,r.margin);concurrent=Math.max(concurrent,r.open);high=Math.max(high,r.peak);breaches+=+(r.liability>300000+1e-8);monthly.set(d.slice(0,7),(monthly.get(d.slice(0,7))||0)+r.change);daily.push([d,pnl,r.liability]);}
 const costs={};for(const k of ['borrow','fees','locate','impact'])costs[k]=sum(positions.map(t=>t.costs[k]));
 const winners=[...issuerPnls.entries()].sort((a,b)=>b[1]-a[1]),lastRows=positions.map(t=>t.daily.filter(r=>r.day<=last).at(-1)),status=k=>run.audit.filter(x=>x.status===k).length;
 const summary={net_pnl:pnl,max_drawdown_dollars:dd,selected:run.audit.filter(a=>a.status!=='outside_signal').length,attempted:all.length,entered:positions.length,issuers:issuerPnls.size,entry_dollars:sum(positions.map(t=>t.entry.notional)),requested_dollars:sum(run.audit.map(a=>a.target_usd||0)),mean_position:positions.length?sum(positions.map(t=>t.entry.notional))/positions.length:0,no_fill:status('no_fill'),name_limit:status('name_limit'),issuer_open:status('issuer_open'),budget_limit:status('budget_limit'),outside_signal:status('outside_signal'),not_yet_eligible:status('not_yet_eligible'),open_positions:lastRows.filter(r=>r?.open).length,open_liability:sum(lastRows.map(r=>r?.liability||0)),costs,peak_gross:gross,peak_margin:margin,peak_concurrent:concurrent,peak_intraday_high_liability:high,closing_budget_breach_sessions:breaches,pnl_without_best_issuer:pnl-(winners[0]?.[1]||0),pnl_without_best5_issuers:pnl-sum(winners.slice(0,5).map(x=>x[1])),monthly:[...monthly],proxy_entry:positions.filter(t=>t.entry.proxy).length,proxy_exit:positions.filter(t=>t.proxy_exit).length,estimated_quote_entries:positions.filter(t=>t.entry.estimatedQuotes).length};
 return {summary,daily,winners};
}
function completed(run,cutoff){return {positions:run.positions.filter(t=>t.ready_day&&t.ready_day<cutoff),audit:run.audit};}
function choose(training,policies,minIssuers=20){
 const viable=policies.filter(p=>!p.diagnostic_only).map(p=>{const x=training[p.id];if(!x||x.base.issuers<minIssuers||x.stress.issuers<minIssuers)return null;const pnl=Math.min(x.base.net_pnl,x.stress.net_pnl),dd=Math.max(1000,Math.abs(x.base.max_drawdown_dollars),Math.abs(x.stress.max_drawdown_dollars));return {id:p.id,score:pnl/dd,base_pnl:x.base.net_pnl,stress_pnl:x.stress.net_pnl,issuers:Math.min(x.base.issuers,x.stress.issuers)};}).filter(x=>x&&x.score>0).sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
 return {selected:viable[0]?.id||'burn_100',fallback:!viable.length,eligible_policies:viable.length,ranking:viable};
}
module.exports={FAMILIES,registry,scores,support,desired,risk,waterfill,prepareProfile,morning,simulate,aggregate,completed,choose};
