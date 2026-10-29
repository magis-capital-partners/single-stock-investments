#!/usr/bin/env node
'use strict';
// Offline descriptive research. No broker, network, production policy, or sealed holdout access.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const A = require('./short_framework/adapters.cjs');
const ROOT = path.resolve(__dirname, '../..'), DATA = path.join(ROOT, '_system/data/reverse_splits');
const CACHE = path.join(DATA, 'local/profit_program/20261022_v1');
const RUN = path.join(DATA, 'local/expansion/expansion_v2/runs/20261013T224003582762Z');
const OUT = path.join(DATA, 'repeat_magnitude_study');
const PRIVATE = path.join(DATA, 'local/repeat_magnitude_20261023');
const read = f => JSON.parse(fs.readFileSync(f, 'utf8'));
const hash = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const json = (f,x) => fs.writeFileSync(f,JSON.stringify(x,null,2)+'\n');
const DAY = 86400000;
const sum = xs => xs.reduce((a,b)=>a+b,0);
const mean = xs => xs.length ? sum(xs)/xs.length : null;
function quant(xs,p){ if(!xs.length)return null;const a=xs.slice().sort((a,b)=>a-b),i=(a.length-1)*p;return a[Math.floor(i)]+(a[Math.ceil(i)]-a[Math.floor(i)])*(i%1); }
function groups(rows,key){const m=new Map();for(const r of rows){const k=key(r),v=m.get(k)||[];v.push(r);m.set(k,v);}return m;}
function dist(xs){return {n:xs.length,mean:mean(xs),median:quant(xs,.5),p05:quant(xs,.05),p95:quant(xs,.95),min:xs.length?Math.min(...xs):null,max:xs.length?Math.max(...xs):null,win_rate:mean(xs.map(x=>+(x>0)))};}
function bin(x){return x<5?'>1–<5':x<10?'5–<10':x<20?'10–<20':x<50?'20–<50':x<100?'50–<100':'100+';}
function rng(seed=20261023){let s=seed>>>0;return()=>{s=(1664525*s+1013904223)>>>0;return s/4294967296;};}
function clusterCI(rows,value='ret',B=2000){
  const clusters=[...groups(rows,r=>r.issuer).values()],random=rng();
  if(clusters.length<2)return null;
  const draws=[];
  for(let b=0;b<B;b++){let total=0,n=0;for(let i=0;i<clusters.length;i++){const c=clusters[Math.floor(random()*clusters.length)];for(const r of c){total+=r[value];n++;}}draws.push(total/n);}
  return [quant(draws,.025),quant(draws,.975)];
}
function stats(rows,key='ret'){return {...dist(rows.map(r=>r[key])),issuers:new Set(rows.map(r=>r.issuer)).size,issuer_bootstrap_95:clusterCI(rows,key)};}
function invert(a){
  const n=a.length,m=a.map((r,i)=>[...r,...Array.from({length:n},(_,j)=>+(i===j))]);
  for(let i=0;i<n;i++){let k=i;for(let j=i+1;j<n;j++)if(Math.abs(m[j][i])>Math.abs(m[k][i]))k=j;
    if(Math.abs(m[k][i])<1e-10)return null;[m[i],m[k]]=[m[k],m[i]];
    const d=m[i][i];for(let j=0;j<2*n;j++)m[i][j]/=d;
    for(let r=0;r<n;r++)if(r!==i){const f=m[r][i];for(let j=0;j<2*n;j++)m[r][j]-=f*m[i][j];}
  }return m.map(r=>r.slice(n));
}
function regression(rows,financial=false){
  rows=rows.filter(r=>r.adv_dollars>0&&r.entry_price>0&&(!financial||r.scored));
  const years=[...new Set(rows.map(r=>r.year))].sort(),names=['intercept','log2_ratio','third_plus','log_entry_price','log_prior_ADV',...(financial?['financial_score']:[]),...years.slice(1).map(y=>'year_'+y)];
  const xs=rows.map(r=>[1,Math.log2(r.multiple),+(r.ordinal>=3),Math.log(r.entry_price),Math.log(r.adv_dollars),...(financial?[r.score]:[]),...years.slice(1).map(y=>+(r.year===y))]),p=names.length;
  if(rows.length<=p+2)return {n:rows.length,status:'insufficient_sample'};
  const xx=Array.from({length:p},()=>Array(p).fill(0)),xy=Array(p).fill(0);
  xs.forEach((x,i)=>{for(let j=0;j<p;j++){xy[j]+=x[j]*rows[i].ret;for(let k=0;k<p;k++)xx[j][k]+=x[j]*x[k];}});
  const inv=invert(xx);if(!inv)return {n:rows.length,status:'singular'};
  const beta=inv.map(v=>sum(v.map((z,i)=>z*xy[i]))),scores=new Map();
  xs.forEach((x,i)=>{const u=rows[i].ret-sum(x.map((z,j)=>z*beta[j])),sc=scores.get(rows[i].issuer)||Array(p).fill(0);x.forEach((z,j)=>sc[j]+=z*u);scores.set(rows[i].issuer,sc);});
  const G=scores.size,adjust=G>1?G/(G-1)*(rows.length-1)/(rows.length-p):1;
  const meat=Array.from({length:p},()=>Array(p).fill(0));for(const s of scores.values())for(let j=0;j<p;j++)for(let k=0;k<p;k++)meat[j][k]+=s[j]*s[k];
  const se=inv.map((v,j)=>Math.sqrt(Math.max(0,adjust*sum(v.map((a,k)=>sum(inv[j].map((b,l)=>a*meat[k][l]*b)))))));
  return {n:rows.length,issuers:G,status:'exploratory_cluster_robust_OLS',coefficients:Object.fromEntries(names.map((n,i)=>[n,{beta:beta[i],se:se[i],normal_95:[beta[i]-1.96*se[i],beta[i]+1.96*se[i]]}]))};
}
const CASES={
  ideal:{execution:0,apr:0,fees:false},
  friction_only:{execution:0,apr:.5,fees:true},
  lower_cost:{execution:.01,apr:.2,fees:true},
  base:{execution:.0172,apr:.5,fees:true},
  depth_base:{execution:null,apr:.5,fees:true},
  stress:{execution:.0425,apr:1.5,fees:true},
};
const SEC=[['2020-02-18',22.1],['2021-02-25',5.1],['2022-05-14',22.9],['2023-02-27',8],['2024-05-22',27.8],['2025-05-14',0],['2026-04-04',20.6]];
function fee(q,p,day,sell,settle=day){
  const value=q*p,comm=Math.min(Math.max(.005*q,1),.01*value),allowance=q*.000003;
  let cost=comm+allowance;
  if(sell){const sec=SEC.filter(([d])=>d<=settle).at(-1)?.[1]??22.1;
    const [taf,cap]=day>='2026-10-01'&&day<='2026-12-31'?[0,0]:day>='2026-01-01'?[.000195,9.79]:day>='2024-01-01'?[.000166,8.3]:day>='2023-01-01'?[.000145,7.27]:day>='2022-01-01'?[.000130,6.49]:[.000119,5.95];
    cost+=value*sec/1e6+Math.min(q*taf,cap);}
  return Math.ceil(cost*100-1e-10)/100;
}
function execution(c,n){return c.execution===null?Math.min(.8,.0172+.0423*Math.sqrt(n/25000)):c.execution;}
const collateral=(q,p)=>Math.abs(q)*Math.ceil(1.02*p);
const margin=(q,p)=>Math.abs(q)*Math.max(p,p<5?Math.max(2.5,p):Math.max(5,.3*p));
function load(){
  const events=read(path.join(CACHE,'effective_events.local.json'));
  const manifest=read(path.join(RUN,'event_outcomes.parts.json'));
  const catalogue=manifest.files.flatMap(f=>{
    const filename=path.join(RUN,f.path);
    if(hash(filename)!==f.sha256)throw new Error('Catalogue checksum mismatch');
    return fs.readFileSync(filename,'utf8').trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
  });
  const prices=new A.Prices(ROOT,events);
  const actions=new Map(),actionFlags=[];
  function add(t,d,f,priority,basis){
    if(!(f>0))return;
    const ds=actions.get(t)||new Map(),prev=ds.get(d);
    if(!prev||priority>prev.priority)ds.set(d,{factor:f,priority,basis});
    else if(priority===prev.priority&&Math.abs(prev.factor/f-1)>.001)ds.set(d,{factor:null,priority,basis:'conflict'});
    actions.set(t,ds);
  }
  // Same precedence as profit_prices: vendor < provider < primary repairs < verified catalogue.
  for(const r of prices.db.prepare('SELECT ticker,ex_date,split_from,split_to FROM reverse_splits').all())if(r.split_from>0&&r.split_to>0)add(r.ticker,r.ex_date,r.split_from/r.split_to,0,'legacy_database');
  for(const e of catalogue)if(e.verification==='vendor_action_only'&&e.ratio>0)add(e.ticker,e.ex_date,1/e.ratio,1,'vendor');
  for(const e of events)if(e.family==='split'&&e.features.ratio>1)add(e.ticker,e.event_date,e.features.ratio,2,'provider');
  for(const r of read(path.join(CACHE,'corporate_action_repairs.json')))add(r.ticker,r.ex_date,r.price_factor,3,'automated_primary_repair');
  for(const e of catalogue)if(['primary_schedule_matched','structured_corporate_action'].includes(e.verification)&&e.ratio>0&&e.ratio!==1)add(e.ticker,e.ex_date,1/e.ratio,4,e.verification);
  prices.actions=new Map([...actions].map(([t,ds])=>[t,new Map([...ds].map(([d,a])=>[d,a.factor===null?null:1/a.factor]))]));
  prices.priorCache.clear();
  const factor=(t,a,b)=>{let f=1;for(const [d,x] of actions.get(t)||[])if(a<d&&d<=b){if(x.factor===null)return null;f*=x.factor;}return f;};
  const history=catalogue.filter(e=>['primary_schedule_matched','structured_corporate_action'].includes(e.verification)&&e.issuer?.startsWith('cik/')&&e.ratio>0&&e.ratio<1);
  const split=events.filter(e=>e.family==='split');
  const sources=split.map(e=>({issuer:e.issuer,day:e.event_date,known:e.known_at,provider:true})).concat(history.map(e=>({issuer:e.issuer,day:e.ex_date,known:e.available_at,provider:false})));
  const query=prices.db.prepare('SELECT point,price,dataset FROM official_auction_prices WHERE ticker=? AND date=?');
  const auctions=new Map();
  const auction=(t,d)=>{const k=t+'/'+d;if(!auctions.has(k))auctions.set(k,Object.fromEntries(query.all(t,d).filter(x=>Number.isFinite(x.price)&&x.price>0).map(x=>[x.point,x.price])));return auctions.get(k);};
  const candidates=split.map(e=>{
    const day=prices.entryDay(e),i=prices.index.get(day),at=day?Date.parse(A.nyClock(day)):Date.parse(e.event_date+'T23:59:59Z');
    const count=provider=>1+new Set(sources.filter(s=>s.issuer===e.issuer&&s.day<e.event_date&&s.known&&Date.parse(s.known)<=at&&(!provider||s.provider)).map(s=>s.day)).size;
    const f=e.financials||{},factClock=(f.evidence||[]).every(x=>x.filed&&Date.parse(A.nyClock(A.dateAfter(x.filed),'00:00:00'))<=at);
    const age=f.period&&day?(Date.parse(day)-Date.parse(f.period))/DAY:null;
    const scored=f.status==='scored'&&Number.isFinite(f.score)&&f.evidence?.length>0&&factClock&&age>=0&&age<=200;
    const matched=catalogue.filter(x=>x.issuer===e.issuer&&x.ex_date===e.event_date&&['primary_schedule_matched','structured_corporate_action'].includes(x.verification)&&x.ratio>0&&x.ratio<1);
    const magnitudes=[...new Set(matched.map(x=>+(1/x.ratio).toFixed(8)))];
    const multiple=magnitudes.length===1?magnitudes[0]:e.features.ratio;
    if(Math.abs(multiple/e.features.ratio-1)>.001)actionFlags.push({id:e.id,provider:e.features.ratio,corroborated:multiple});
    const p=day?prices.point(e.ticker,day):null,pr=day?prices.prior(e.ticker,day):null;
    return {id:e.id,issuer:e.issuer,ticker:e.ticker,name:e.name,event_date:e.event_date,known_at:e.known_at,day,i,
      ordinal:count(false),provider_ordinal:count(true),multiple,provider_multiple:e.features.ratio,bin:bin(multiple),
      source_url:e.source_url,score:f.score??null,scored,fact_clock:factClock,fact_age:age,financial_status:f.status,
      entry_price:day?auction(e.ticker,day).open||null:null,adv_dollars:pr?.complete&&p?pr.adv*p.open:null,
      liquidity_complete:pr?.complete||false,adv_shares:pr?.adv||0,year:day?.slice(0,4)||e.event_date.slice(0,4)};
  });
  const settlement=(d)=>{const i=prices.index.get(d),lag=d<'2024-05-28'?2:1;if(i!==undefined&&prices.days[i+lag])return prices.days[i+lag];let n=0,x=d;while(n<lag){x=A.dateAfter(x);if(![0,6].includes(new Date(x+'T12:00:00Z').getUTCDay()))n++;}return x;};
  return {events,catalogue,prices,candidates,factor,auction,settlement,actionFlags,actions};
}
function label(ctx,r,h){
  if(r.i===undefined||r.i+h-1>=ctx.prices.days.length)return {status:'immature'};
  const end=ctx.prices.days[r.i+h-1],exit=ctx.auction(r.ticker,end).close,f=ctx.factor(r.ticker,r.day,end);
  if(!r.entry_price)return {status:'missing_entry'};
  if(!exit)return {status:'missing_exit'};
  if(!f)return {status:'action_conflict'};
  return {...r,h,exit_day:end,exit_price:exit,factor:f,ret:1-exit/f/r.entry_price,status:'observed'};
}

function replay(ctx, opts){
  const {prices,auction,factor,settlement}=ctx,c=CASES[opts.cost],cap=opts.cap??null,h=opts.horizon;
  const filter=r=>opts.ordinal==='provider'?r.provider_ordinal>=3:opts.ordinal==='all'?true:r.ordinal>=3;
  const cutoff=prices.days.length-(opts.maturitySessions||Math.max(20,h));
  if(!c||!Number.isInteger(h)||h<1||h>60||cap!==null&&(!(cap>0)||cap>1)||opts.nav!==undefined&&(!(opts.nav>0)||!Number.isFinite(opts.nav)))throw new Error('Invalid replay options');
  const universe=ctx.candidates.filter(filter).filter(r=>opts.financial==='all'||opts.financial==='scored'&&r.scored||opts.financial==='score60'&&r.scored&&r.score>=60);
  const funnel={selected:universe.length,common_maturity_excluded:0,missing_entry:0,missing_liquidity:0,overlap:0,zero_capacity:0,entered:0,ssr_rejected:0,risk_capacity:0,verified_evidence_missing:0};
  const byDay=new Map();
  for(const r of universe){
    if(r.i===undefined||(r.maturity_index??r.i)>cutoff){funnel.common_maturity_excluded++;continue;}
    if(!r.entry_price||!prices.point(r.ticker,r.day)){funnel.missing_entry++;continue;}
    if(cap!==null&&!r.liquidity_complete){funnel.missing_liquidity++;continue;}
    const a=byDay.get(r.day)||[];a.push(r);byDay.set(r.day,a);
  }
  const positions=[],daily=[];let cash=0,peak=0,maxDD=0,previous=0;
  const allDays=prices.days,dayIndex=prices.index;
  let day=allDays[0],peakExposure=0,peakMargin=0,peakNames=0,staleSessions=0,loanTail=0,riskBreachSessions=0;
  function applyCash(p,category,value){cash+=value;p[category]=(p[category]||0)+value;}
  function mark(p,ds){
    const f=factor(p.ticker,p.day,ds);
    if(f===null){p.action_conflict=true;return;}
    const old=p.factor;p.factor=f;
    p.mark*=f/old;p.open_mark=p.mark;
    if(opts.stopCloseFraction&&p.units>1e-9&&p.open_mark/p.factor>=p.entry_price*(1+opts.stopCloseFraction))p.stop_due=ds;
    if((Date.parse(ds)-Date.parse(p.last_mark))/DAY>7)p.identity_unresolved=true;
    if(p.identity_unresolved)return;
    const point=prices.point(p.ticker,ds),a=auction(p.ticker,ds);
    if(point){p.mark=a.close||point.close;p.last_mark=ds;if(p.units>1e-9)p.max_adverse_price_return=Math.max(p.max_adverse_price_return||0,point.high/p.factor/p.entry_price-1);}
  }
  for(;day<=prices.last;day=A.dateAfter(day)){
    const idx=dayIndex.get(day),session=idx!==undefined;
    // Mark and accrue loans on every calendar day, including weekends.
    for(const p of positions){
      if(p.units>1e-9||p.loan_units>1e-9)mark(p,day);
      if(p.loan_start===day)p.loan_units+=p.entry_units;
      for(const ret of p.pending_returns)if(ret.day===day)p.loan_units=Math.max(0,p.loan_units-ret.units);
      let billed=p.loan_units;
      if(day===p.loan_start&&billed<=1e-9&&p.borrow_days===0)billed=p.entry_units;
      if(billed>1e-9&&day>=p.loan_start){
        const charge=collateral(billed/p.factor,opts.causalCarry?p.open_mark:p.mark)*c.apr/360;
        applyCash(p,'borrow',-charge);p.borrow_days++;
      }
    }
    if(!session)continue;
    for(const r of (byDay.get(day)||[]).sort((a,b)=>a.id.localeCompare(b.id))){
      if(positions.some(p=>p.issuer===r.issuer&&p.units>1e-9)){funnel.overlap++;continue;}
      const point=prices.point(r.ticker,day),ssr=prices.ssrQuery.get(r.ticker,day);
      if(opts.evidence==='verified'){funnel.verified_evidence_missing++;continue;}
      if(opts.ssrMode==='strict'&&ssr?.restricted!==0){funnel.ssr_rejected++;continue;}
      const target=opts.target||25000;let qty=Math.floor(target/r.entry_price);
      if(opts.nav){
        const open=positions.filter(p=>p.units>1e-9),exposure=sum(open.map(p=>p.units/p.factor*(p.open_mark||p.mark))),required=sum(open.map(p=>margin(p.units/p.factor,p.open_mark||p.mark)));
        const equity=opts.nav+cash-exposure,budget=Math.min(.0025*equity,Math.max(0,.01*equity-(opts.otherStressLoss||0)/2-exposure));
        if(open.length>=(opts.maximumNames||3)){funnel.risk_capacity++;continue;}
        qty=Math.min(qty,Math.floor(budget/r.entry_price),Math.floor(Math.max(0,.8*equity-required)/margin(1,r.entry_price)));
        if(qty<=0){funnel.risk_capacity++;continue;}
      }
      if(cap!==null){
        qty=Math.min(qty,Math.floor(cap*r.adv_shares),Math.floor(cap*point.volume*(ssr?.restricted===0?1:.5)));
      }
      if(qty<1){funnel.zero_capacity++;continue;}
      const spread=execution(c,qty*r.entry_price)/2,fill=r.entry_price*(1-spread);
      const p={...r,horizon:h,entry_units:qty,units:qty,loan_units:0,factor:1,mark:auction(r.ticker,day).close||point.close,last_mark:day,
        open_mark:r.entry_price,max_adverse_price_return:Math.max(0,point.high/r.entry_price-1),
        entry_reference_notional:qty*r.entry_price,entry_proceeds:qty*fill,entry_fill:fill,deadline:r.exit_index_override??idx+h-1,
        planned_exit:allDays[r.exit_index_override??idx+h-1],loan_start:settlement(day),pending_returns:[],borrow:0,borrow_days:0,fees:0,
        covers:0,execution_cost:qty*(r.entry_price-fill),stale_sessions:0,cover_children:0,filled_fraction:qty*r.entry_price/target};
      positions.push(p);cash+=p.entry_proceeds;
      if(c.fees)applyCash(p,'fees',-fee(qty,fill,day,true,p.loan_start));
      funnel.entered++;
    }
    // Close at the session close; for h1 the entry session is also the exit session.
    for(const p of positions){
      if(p.units<=1e-9||idx<p.deadline&&!p.stop_due)continue;
      if(p.identity_unresolved||p.action_conflict){p.overdue=true;continue;}
      const point=prices.point(p.ticker,day),close=p.stop_due?auction(p.ticker,day).open:auction(p.ticker,day).close;
      if(p.stop_due)p.exit_price_basis='next_session_open_after_prior_close_threshold';
      if(!point||!close){p.overdue=true;continue;}
      let q=p.units/p.factor;
      if(cap!==null)q=Math.min(Math.floor(q+1e-10),Math.floor(cap*point.volume));
      if(q<=0){p.overdue=true;continue;}
      const units=Math.min(p.units,q*p.factor),spread=execution(c,q*close)/2,fill=close*(1+spread);
      applyCash(p,'covers',-q*fill);
      if(c.fees)applyCash(p,'fees',-fee(q,fill,day,false));
      p.execution_cost+=q*(fill-close);p.units=Math.max(0,p.units-units);
      p.pending_returns.push({day:settlement(day),units,nominal:close});
      p.cover_children++;p.last_cover=day;
      if(p.units<=1e-9)p.closed=day;else p.overdue=true;
    }
    let liability=0,exposure=0,required=0,names=0,stale=0;
    for(const p of positions)if(p.units>1e-9){
      const v=p.units/p.factor*p.mark;liability+=v;exposure+=v;required+=margin(p.units/p.factor,p.mark);names++;
      if(p.last_mark!==day){p.stale_sessions++;stale+=v;}
    }
    const pnl=cash-liability;if(opts.nav&&(2*exposure+(opts.otherStressLoss||0)>.02*(opts.nav+pnl)||required>.8*(opts.nav+pnl)))riskBreachSessions++;peak=Math.max(peak,pnl);maxDD=Math.min(maxDD,pnl-peak);
    peakExposure=Math.max(peakExposure,exposure);peakMargin=Math.max(peakMargin,required);peakNames=Math.max(peakNames,names);staleSessions+=+(stale>0);
    daily.push({date:day,pnl,change:pnl-previous,liability,exposure,margin:required,names,stale});previous=pnl;
  }
  // Known modeled covers still owe carry until modeled loan return. Accrue that
  // finite tail at the last mark; unresolved open shorts are not called settled.
  for(const p of positions)if(p.units<=1e-9&&p.loan_units>1e-9){
    for(let d=A.dateAfter(prices.last);p.loan_units>1e-9;d=A.dateAfter(d)){
      for(const ret of p.pending_returns)if(ret.day===d)p.loan_units=Math.max(0,p.loan_units-ret.units);
      if(p.loan_units>1e-9){const z=collateral(p.loan_units/p.factor,p.mark)*c.apr/360;applyCash(p,'borrow',-z);loanTail+=z;}
      if((Date.parse(d)-Date.parse(prices.last))/DAY>10)throw new Error('Settlement tail did not resolve');
    }
  }
  if(daily.length){daily.at(-1).pnl-=loanTail;daily.at(-1).change-=loanTail;}
  for(const p of positions){
    p.open_liability=p.units/p.factor*p.mark;
    p.pnl=p.entry_proceeds+p.covers+p.fees+p.borrow-p.open_liability;
    p.net_return=p.pnl/p.entry_reference_notional;
    p.gross_pnl=p.pnl-p.fees-p.borrow+p.execution_cost;
  }
  const net=sum(positions.map(p=>p.pnl));
  if(Math.abs(net-(cash-sum(positions.map(p=>p.open_liability))))>.01)throw new Error('Cash/position accounting mismatch');
  let runningPeak=0,drawdown=0;for(const d of daily){runningPeak=Math.max(runningPeak,d.pnl);drawdown=Math.min(drawdown,d.pnl-runningPeak);}
  const active=positions.length?daily.filter(d=>d.date>=positions[0].day):[];
  const monthly=[...groups(active,d=>d.date.slice(0,7))].map(([month,ds])=>({month,pnl:sum(ds.map(d=>d.change)),entries:positions.filter(p=>p.day.startsWith(month)).length}));
  const yearly=[...groups(active,d=>d.date.slice(0,4))].map(([year,ds])=>({year,pnl:sum(ds.map(d=>d.change)),entries:positions.filter(p=>p.day.startsWith(year)).length}));
  const closed=positions.filter(p=>p.units<=1e-9),issuerPnls=[...groups(positions,p=>p.issuer)].map(([issuer,ps])=>({issuer,pnl:sum(ps.map(p=>p.pnl)),n:ps.length}));
  const first=positions[0]?.day,years=first?(Date.parse(prices.last)-Date.parse(first))/DAY/365.25:0;
  const returns=positions.map(p=>({...p,ret:p.net_return}));
  const summary={...opts,price_asof:prices.last,funnel,first_entry:first,last_entry:positions.at(-1)?.day,
    entered:positions.length,issuers:new Set(positions.map(p=>p.issuer)).size,closed:closed.length,
    net_pnl:net,gross_pnl:sum(positions.map(p=>p.gross_pnl)),borrow_cost:-sum(positions.map(p=>p.borrow)),
    commissions_and_fees:-sum(positions.map(p=>p.fees)),execution_cost:sum(positions.map(p=>p.execution_cost)),settlement_tail_accrual:loanTail,
    mean_position:mean(positions.map(p=>p.entry_reference_notional)),median_position:quant(positions.map(p=>p.entry_reference_notional),.5),
    mean_net_return:mean(positions.map(p=>p.net_return)),median_net_return:quant(positions.map(p=>p.net_return),.5),
    win_rate_closed:mean(closed.map(p=>+(p.pnl>0))),profit_factor_closed:sum(closed.filter(p=>p.pnl>0).map(p=>p.pnl))/-sum(closed.filter(p=>p.pnl<0).map(p=>p.pnl)),
    max_drawdown_dollars:drawdown,worst_day:Math.min(...daily.map(d=>d.change)),best_day:Math.max(...daily.map(d=>d.change)),
    worst_trade:positions.length?Math.min(...positions.map(p=>p.pnl)):null,best_trade:positions.length?Math.max(...positions.map(p=>p.pnl)):null,
    risk_breach_sessions:riskBreachSessions,peak_exposure:peakExposure,peak_margin:peakMargin,peak_open_names:peakNames,
    nav_for_200pct_squeeze_at_2pct_loss_budget:2*peakExposure/.02,
    open_positions:positions.filter(p=>p.units>1e-9).length,open_liability:sum(positions.map(p=>p.open_liability)),stale_sessions:staleSessions,
    overdue_positions:positions.filter(p=>p.overdue).length,fractional_residuals:positions.filter(p=>p.units>0&&p.units/p.factor<1).length,
    action_conflicts:positions.filter(p=>p.action_conflict).length,identity_unresolved:positions.filter(p=>p.identity_unresolved).length,
    mean_monthly_since_first_entry:mean(monthly.map(x=>x.pnl)),median_month:quant(monthly.map(x=>x.pnl),.5),
    positive_months:monthly.filter(x=>x.pnl>0).length,total_months:monthly.length,best_month:monthly.length?Math.max(...monthly.map(x=>x.pnl)):null,
    worst_month:monthly.length?Math.min(...monthly.map(x=>x.pnl)):null,annualized_pnl:years?net/years:null,trades_per_year:years?positions.length/years:null,
    pooled_net_return:sum(positions.map(p=>p.entry_reference_notional))?net/sum(positions.map(p=>p.entry_reference_notional)):null,
    issuer_bootstrap_mean_trade_return_95:opts.fastStats?null:clusterCI(returns),
    top5_issuer_profit_share:net?sum(issuerPnls.slice().sort((a,b)=>b.pnl-a.pnl).slice(0,5).map(x=>x.pnl))/net:null,
    pnl_without_best_issuer:net-(issuerPnls.length?Math.max(...issuerPnls.map(x=>x.pnl)):0),
    pnl_without_best5_issuers:net-sum(issuerPnls.slice().sort((a,b)=>b.pnl-a.pnl).slice(0,5).map(x=>x.pnl)),
    monthly,yearly,broker_verified_entries:0,borrow_availability_verified:false,account_capital_limit_applied:!!opts.nav,
    negative_marked_trades:positions.filter(p=>p.pnl<0).length};
  return enrichSummary({summary,daily,positions});
}
function tests(){
  const assert=require('node:assert/strict');
  assert.equal(25000*(1-8/10),4999.999999999999);
  assert.equal(1-80/10/10,.2-Number.EPSILON/4); // split: 10 old shares become one.
  assert.equal(collateral(100,5),600);
  assert.equal(collateral(100,5)*.5/360,5/6);
  assert.equal(margin(100,1),250);
  assert.equal(bin(5),'5–<10');assert.equal(bin(20),'20–<50');assert.equal(bin(100),'100+');
  // A partial cover must leave a liability, not a zero-price windfall.
  assert.equal(25000-1000*8-1500*8,5000);
  assert.equal(25000-1000*8-1500*12,-1000);
  const inv=invert([[2,0],[0,4]]);assert.deepEqual(inv,[[.5,0],[0,.25]]);
  return {hand_accounting_checks:11,passed:true};
}

function protocol(){
  return {schema:'repeat_magnitude_study.v1',declared_date:'2026-10-23',research_only:true,production_authority:'none',
    universe:'1,183 existing MicrocapLedger completed-action records, 2021 onward; issuer/effective-date deduplication.',
    history:'Count only distinct earlier effective dates linked to the same SEC CIK and publicly available by entry. Supplement provider records with primary_schedule_matched / structured corporate actions. Third means at least two documented prior actions, a lower bound on lifetime count.',
    entry:'First exchange-session official opening price after effective-day close and known_at + 5 minutes. Hypothetical auction fills.',
    horizons:[1,5,10,20,60],primary_horizon:10,
    maturity:'Same last-20-session entry exclusion for primary 1/5/10/20 comparisons, independent of exit availability. 60 sessions uses its own exclusion.',
    target:25000,portfolio:'One open short per SEC issuer; integer entry shares, fixed initial reference dollars, no compounding, NAV cap, stop or take-profit.',
    sizing:'Full-fill ceiling; separate 0.1%, 1%, 5% caps on prior 20-session split-adjusted share ADV and same-day three-venue volume. Restricted/unknown SSR gets 50% entry capture. Historical borrow quantity is unknown.',
    covers:'Official close after h sessions including entry. Delayed and partial covers persist. No future exit availability selects entry. Missing continuity after seven calendar days freezes identity and retains the liability. Fractional remnants persist in capacity models.',
    accounting:'Nominal prices and mechanical action share adjustments. Vendor < provider < automated primary repair < verified catalogue. ACT/360 rounded collateral borrow from settlement through modeled return, minimum one billed day; dated commissions and SEC/TAF schedule reused from profit_prices.',
    omissions:'No proceeds interest, dividends, locate charges, forced buy-ins, corporate-action servicing fees, taxes or overhead.',
    costs:CASES,financial:'Existing as-filed numeric score, at least three independent signals, every filing public by entry, period age <=200 days. Higher score means greater distress. Show all, financially scored subset and score>=60 separately.',
    magnitude:'Old/new price multiple. Corroborated same-issuer same-date catalogue ratio supersedes provider ratio. Bins: >1–<5, 5–<10, 10–<20, 20–<50, 50–<100, >=100.',
    statistics:'Event-weighted arithmetic short returns; 2,000 issuer-cluster bootstrap mean intervals. Exploratory OLS with issuer-cluster standard errors, year, repeat status, log price and log prior ADV; finance-covered fit adds score. No multiple-testing adjustment or untouched historical holdout.',
    exclusions:'No sealed holdout files, Gateway/broker access, or new paid market data. Previously explored history is development evidence.'};
}
function magnitudeStudy(ctx){
  const tables=[],regressions=[],repeatTables=[],coverage=[];
  const common=ctx.candidates.filter(r=>r.i!==undefined&&r.i<=ctx.prices.days.length-20);
  for(const h of [1,5,10,20,60]){
    const rows=(h>20?ctx.candidates.filter(r=>r.i!==undefined&&r.i<=ctx.prices.days.length-h):common).map(r=>label(ctx,r,h));
    coverage.push({h,eligible:rows.length,statuses:Object.fromEntries([...groups(rows,r=>r.status)].map(([k,v])=>[k,v.length]))});
    const valid=rows.filter(r=>r.status==='observed');
    for(const cohort of ['all','scored','score60','third_plus']){
      const eligible=valid.filter(r=>cohort==='all'||cohort==='scored'&&r.scored||cohort==='score60'&&r.scored&&r.score>=60||cohort==='third_plus'&&r.ordinal>=3);
      for(const b of ['>1–<5','5–<10','10–<20','20–<50','50–<100','100+','ALL']){
        tables.push({h,cohort,bin:b,...stats(b==='ALL'?eligible:eligible.filter(r=>r.bin===b))});
      }
    }
    for(const cohort of ['first','second','third_plus']){
      const sample=valid.filter(r=>cohort==='first'?r.ordinal===1:cohort==='second'?r.ordinal===2:r.ordinal>=3);
      repeatTables.push({h,cohort,...stats(sample)});
    }
    if(h<=20){
      regressions.push({h,cohort:'all',...regression(valid)});
      regressions.push({h,cohort:'financially_scored',...regression(valid,true)});
      const lo=quant(valid.map(r=>r.ret),.01),hi=quant(valid.map(r=>r.ret),.99);
      regressions.push({h,cohort:'winsorized_1_99_diagnostic',...regression(valid.map(r=>({...r,ret:Math.min(hi,Math.max(lo,r.ret))})))});
    }
  }
  return {coverage,tables,repeatTables,regressions};
}
function oracle(ctx){
  const checks=[];
  for(const h of [1,5,10,20]){
    let n=0,same=0,max=0,changed=[];
    for(const r of ctx.candidates){
      const old=ctx.catalogue.find(o=>o.issuer===r.issuer&&o.ex_date===r.event_date&&o.ticker===r.ticker)?.outcomes?.find(x=>x.cohort==='ex_plus_1_h'+h);
      const fresh=label(ctx,r,h);
      if(old?.status==='observed_price_path'&&fresh.status==='observed'&&old.entry_date===r.day&&old.exit_date===fresh.exit_day){
        n++;const diff=Math.abs(old.gross_short_return-fresh.ret);max=Math.max(max,diff);if(diff<1e-8)same++;else changed.push({ticker:r.ticker,date:r.event_date,old:old.gross_short_return,new:fresh.ret});
      }
    }checks.push({h,compared:n,matched:same,maximum_difference:max,changed});
  }return checks;
}
function makeReport(doc){
  const money=x=>x==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x);
  const pct=x=>x==null?'—':(x*100).toFixed(2)+'%';
  const model=(h,cost='base',cap=null,financial='all',ordinal='extended')=>doc.models.find(r=>r.horizon===h&&r.cost===cost&&r.cap===cap&&r.financial===financial&&r.ordinal===ordinal);
  const ci=x=>x?'['+x.map(pct).join(', ')+']':'—';
  const table=(headers,rows)=>'| '+headers.join(' | ')+' |\n| '+headers.map(()=>'---').join(' | ')+' |\n'+rows.map(r=>'| '+r.join(' | ')+' |').join('\n')+'\n';
  let s='# Third-and-later reverse splits and split magnitude\n\nBuilt '+doc.built_at+'. Price observations end **'+doc.price_asof+'**. Research-only conditional simulations; no live authority or verified fills.\n\n';
  s+='## Scope and counting\n\n'+doc.protocol.universe+'\n\n'+doc.protocol.history+'\n\n';
  s+=table(['Definition','Third+ candidates','Issuers'],doc.counting.map(r=>[r.definition,r.n,r.issuers]));
  s+='\nSupplemented same-CIK history is primary; provider-only counting is a sensitivity. Lifetime history, historical share-class/ADS identity and automated action repairs remain incomplete. No ticker-based history stitching is used. Missing older history produces false negatives.\n\n';
  s+='Entry is the first official session open after effective-day close and public filing clock plus five minutes. Horizons include entry day. All primary horizons share the same 20-session maturity cutoff. P&L is short proceeds minus mechanically adjusted cover liability and costs. A 1-for-100 action itself creates no gain.\n\n';
  s+='## Equal $25,000 full-fill benchmark\n\n';
  s+=table(['Sessions','Entries / issuers','Gross P&L','Zero slippage + carry / fees','Base net','Depth-cost net','Base max drawdown','Base open positions / liability'],[1,5,10,20].map(h=>{const ideal=model(h,'ideal'),f=model(h,'friction_only'),b=model(h),d=model(h,'depth_base');return[h,b.entered+' / '+b.issuers,money(ideal.net_pnl),money(f.net_pnl),money(b.net_pnl),money(d.net_pnl),money(b.max_drawdown_dollars),b.open_positions+' / '+money(b.open_liability)];}));
  s+='\nBase assumes 1.72% roundtrip execution and 50% APR carry. Entry shares are rounded down from $25,000 without reinvestment. Full-fill ignores locate quantity, queues, capital admission and actual auction availability. These are conditional dollar results, not an executable forecast.\n\n';
  s+='## Capacity and financing, ten-session comparison\n\n';
  const main=model(10);
  s+=table(['Sizing / case','Entries','Mean position','Net P&L','Mean monthly since first entry','Max drawdown','Open positions'],[
    ['Full fill; no friction',model(10,'ideal')],['Full fill; zero slippage + carry / fees',model(10,'friction_only')],['Full fill; lower cost',model(10,'lower_cost')],['Full fill; base',main],['Full fill; depth base',model(10,'depth_base')],['Full fill; stress',model(10,'stress')],['5% ADV/volume; base',model(10,'base',.05)],['5% ADV/volume; depth',model(10,'depth_base',.05)],['1% ADV/volume; base',model(10,'base',.01)],['0.1% ADV/volume; base',model(10,'base',.001)],
  ].map(([label,r])=>[label,r.entered,money(r.mean_position),money(r.net_pnl),money(r.mean_monthly_since_first_entry),money(r.max_drawdown_dollars),r.open_positions]));
  s+='\nLower cost: 1% execution / 20% APR. Stress: 4.25% / 150% APR. Depth base: 1.72% + 4.23% × sqrt(order value / $25,000), capped at 80%, plus 50% APR. The depth curve transfer is uncalibrated. Monthly mean includes zero months from first entry and the October 2026 partial month. It is not a monthly income commitment. Volume is a three-venue subset; SSR capture and cover capacity are assumptions. Verified historical borrow quantities and broker fills are zero.\n\n';
  s+='## Base ten-session details\n\n';
  s+=table(['Metric','Value'],[
    ['First / last entry',main.first_entry+' / '+main.last_entry],['Gross price P&L',money(main.gross_pnl)],['Execution debit',money(main.execution_cost)],['Commissions and regulatory fees',money(main.commissions_and_fees)],['Borrow carry',money(main.borrow_cost)],['Net marked P&L',money(main.net_pnl)],['Mean / median trade return',pct(main.mean_net_return)+' / '+pct(main.median_net_return)],['Issuer-bootstrap mean-return 95%',ci(main.issuer_bootstrap_mean_trade_return_95)],['Win rate, closed trades',pct(main.win_rate_closed)],['Profit factor, closed trades',main.profit_factor_closed?.toFixed(2)||'—'],['Best / worst trade',money(main.best_trade)+' / '+money(main.worst_trade)],['Worst day',money(main.worst_day)],['Best / worst month',money(main.best_month)+' / '+money(main.worst_month)],['Positive / total months',main.positive_months+' / '+main.total_months],['Peak closing open names',main.peak_open_names],['Peak closing exposure',money(main.peak_exposure)],['Peak modeled margin',money(main.peak_margin)],['Illustrative NAV, 200% squeeze at 2% loss budget',money(main.nav_for_200pct_squeeze_at_2pct_loss_budget)],['Net without best issuer',money(main.pnl_without_best_issuer)],['Net without best five issuers',money(main.pnl_without_best5_issuers)],['Unresolved / stale sessions',main.identity_unresolved+' / '+main.stale_sessions],
  ]);
  s+='\nExposure/margin use closing marks; intraday peaks, broker house requirements and other strategies can be higher. The NAV illustration is a declared stress budget, not a minimum deposit or guarantee. There is no initial equity assumption, hence no CAGR claim.\n\n';
  s+='### Calendar years\n\n'+table(['Year','Entries','Marked P&L'],main.yearly.map(r=>[r.year,r.entries,money(r.pnl)]));
  s+='\n### Calendar months\n\n'+table(['Month','Entries','Marked P&L'],main.monthly.map(r=>[r.month,r.entries,money(r.pnl)]));
  s+='\n## Fundamentals and repeat-count sensitivity\n\n';
  s+=table(['Ten-session full-fill base cohort','Entries','Mean position','Net P&L','Closed win rate','Max drawdown','Open liability'],[
    ['All third+',main],['Financially scored third+',model(10,'base',null,'scored')],['Score >=60 third+',model(10,'base',null,'score60')],['Provider-only third+',model(10,'base',null,'all','provider')],
  ].map(([label,r])=>[label,r.entered,money(r.mean_position),money(r.net_pnl),pct(r.win_rate_closed),money(r.max_drawdown_dollars),money(r.open_liability)]));
  s+='\n'+doc.protocol.financial+' Compare score>=60 against the scored subset to separate financial selection from filing coverage. Fewer trades/exposure can reduce dollar profit even if average return improves.\n\n';
  s+='## Split-magnitude event study\n\nAll split candidates, rather than only third-plus. Gross complete-path open-to-close returns, without costs or portfolio overlap restrictions. Missing exits are not assumed winners; portfolio replays above retain their liabilities.\n\n';
  s+=table(['Sessions','Mature eligible','Observed paths','Missing entry','Missing exit','Action conflict'],doc.magnitude.coverage.map(r=>[r.h,r.eligible,r.statuses.observed||0,r.statuses.missing_entry||0,r.statuses.missing_exit||0,r.statuses.action_conflict||0]));
  for(const h of [1,5,10,20,60]){
    s+='\n### '+h+' sessions: gross short returns\n\n';
    s+=table(['Old per new share','All n','All mean / median','Scored n / mean','Score>=60 n / mean','Third+ n / mean','All mean 95%'],['>1–<5','5–<10','10–<20','20–<50','50–<100','100+','ALL'].map(b=>{
      const get=cohort=>doc.magnitude.tables.find(r=>r.h===h&&r.bin===b&&r.cohort===cohort),a=get('all'),f=get('scored'),g=get('score60'),t=get('third_plus');
      return [b,a.n,pct(a.mean)+' / '+pct(a.median),f.n+' / '+pct(f.mean),g.n+' / '+pct(g.mean),t.n+' / '+pct(t.mean),ci(a.issuer_bootstrap_95)];
    }));
  }
  s+='\n### Magnitude after controls\n\n';
  s+=table(['Sessions','Sample','n / issuers','Return change per ratio doubling','Cluster 95%'],doc.magnitude.regressions.map(r=>[r.h,r.cohort,r.n+' / '+(r.issuers||0),pct(r.coefficients?.log2_ratio?.beta),ci(r.coefficients?.log2_ratio?.normal_95)]));
  s+='\nControls: year, third-plus indicator, log entry price and log prior ADV valued at entry open. Financial fit adds distress score. Post-split price control asks about magnitude at a similar trading price. Associations are not causal. Winsorization is a disclosed diagnostic, never the primary P&L.\n\n';
  s+='### Recorded repeat count\n\n'+table(['Sessions','Ordinal','n / issuers','Mean','Median','Win rate'],doc.magnitude.repeatTables.map(r=>[r.h,r.cohort,r.n+' / '+r.issuers,pct(r.mean),pct(r.median),pct(r.win_rate)]));
  s+='\n## Missing paths and execution limits\n\n';
  s+=table(['Ten-session model','Selected','Maturity','Missing entry','Missing liquidity','Overlap','Zero capacity','Entered'],doc.models.filter(r=>r.horizon===10&&r.financial==='all'&&r.ordinal==='extended'&&['ideal','base','depth_base'].includes(r.cost)).map(r=>[r.cost+' / '+(r.cap??'full'),r.funnel.selected,r.funnel.common_maturity_excluded,r.funnel.missing_entry,r.funnel.missing_liquidity,r.funnel.overlap,r.funnel.zero_capacity,r.entered]));
  s+='\nHistorical PIT security identity, loan recall/return, locates and executable child fills are unverified. '+doc.protocol.omissions+' Stale marks can understate liabilities. Named residuals and extreme trades remain in the local audit and are not silently dropped.\n\n';
  s+='To validate prospectively: freeze eligibility and timing, resolve two prior actions and security class, log timestamped locate quantity/APR and all attempted orders including failures, reconcile fills and loan returns, and compare observed quantity/cost against assumptions. Use a fixed shadow ledger first. This study changes no executor or broker settings.\n\n';
  s+='## Reproduction and validation\n\nRun node _system/scripts/reverse_split_repeat_study.cjs. Aggregate outputs are here; candidate/position/daily ledgers and named residuals are in the ignored local/repeat_magnitude_20261023 directory.\n\n';
  s+='Accounting checks: '+JSON.stringify(doc.validation.tests)+'. Frozen-price oracle: '+JSON.stringify(doc.validation.oracle.map(r=>({h:r.h,n:r.compared,matched:r.matched,max_difference:r.maximum_difference})))+'. Different clocks/actions are reported, not forced to match.\n\n';
  s+='Corroborated ratio overrides: '+doc.data_quality.ratio_overrides+'. Provider events, class identities and automatic action repairs remain provisional. '+doc.protocol.statistics+'\n\n';
  s+='A favorable conditional result does not establish that larger ratios always improve short returns, that $25,000 is borrowable, or that historical monthly P&L will recur.\n';
  return s;
}
function htmlReport(doc,md,baseLedger){
  const esc=x=>String(x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const pts=baseLedger.daily.filter(d=>d.date>=baseLedger.summary.first_entry),vals=pts.map(d=>d.pnl),min=Math.min(0,...vals),max=Math.max(0,...vals);
  const xy=pts.map((d,i)=>(65+i/Math.max(1,pts.length-1)*950).toFixed(1)+','+(20+(max-d.pnl)/Math.max(1,max-min)*220).toFixed(1)).join(' ');
  const zero=20+max/Math.max(1,max-min)*220;
  const svg='<svg viewBox="0 0 1040 280" role="img" aria-label="Ten-session full-fill base cumulative marked profit"><line x1="65" y1="'+zero+'" x2="1015" y2="'+zero+'" stroke="#aaa"/><polyline fill="none" stroke="#176f88" stroke-width="2" points="'+xy+'"/><text x="0" y="20">$'+Math.round(max).toLocaleString()+'</text><text x="0" y="240">$'+Math.round(min).toLocaleString()+'</text><text x="65" y="275">'+esc(pts[0]?.date)+'</text><text x="920" y="275">'+esc(pts.at(-1)?.date)+'</text></svg>';
  let body='',tableOpen=false;
  for(const line of md.split('\n')){
    if(line.startsWith('| ')){
      if(/^\| (---\s*\|)+$/.test(line))continue;
      if(!tableOpen){body+='<div class="scroll"><table>';tableOpen=true;}
      body+='<tr>'+line.slice(2,-2).split(' | ').map(x=>'<td>'+esc(x)+'</td>').join('')+'</tr>';continue;
    }
    if(tableOpen){body+='</table></div>';tableOpen=false;}
    if(line.startsWith('# '))body+='<h1>'+esc(line.slice(2))+'</h1>'+svg;
    else if(line.startsWith('### '))body+='<h3>'+esc(line.slice(4))+'</h3>';
    else if(line.startsWith('## '))body+='<h2>'+esc(line.slice(3))+'</h2>';
    else if(line.trim())body+='<p>'+esc(line)+'</p>';
  }
  return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reverse-split repeat and magnitude study</title><style>body{font:16px/1.55 system-ui,sans-serif;margin:40px auto;padding:0 24px;max-width:1200px;color:#182a3b;background:#f8fafc}h1{font-size:34px;line-height:1.2}h2{margin-top:38px;border-top:1px solid #cdd8df;padding-top:22px}h3{margin-top:28px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;background:white;margin:12px 0 22px}td{padding:9px 10px;border-bottom:1px solid #dae2e8;white-space:nowrap}tr:first-child{font-weight:700;background:#e7f0f4}svg{width:100%;background:white;border:1px solid #dae2e8;margin:15px 0}svg text{font-size:12px;fill:#415567}p{max-width:1050px}@media print{body{font-size:11px;margin:10px}h2{break-after:avoid}tr{break-inside:avoid}}</style>'+body+'</html>';
}
async function main(){
  fs.mkdirSync(OUT,{recursive:true});fs.mkdirSync(PRIVATE,{recursive:true});
  const declared=protocol();json(path.join(OUT,'protocol.json'),declared);
  const test={...tests(),portfolio:extendedTests()},ctx=load(),models=[],ledgers=[];
  function run(horizon,cost='base',cap=null,financial='all',ordinal='extended'){
    const o={horizon,cost,cap,financial,ordinal},r=replay(ctx,o);models.push(r.summary);ledgers.push(r);
    const id=[ordinal,financial,'h'+horizon,cost,cap===null?'full':'cap'+cap].join('__');
    json(path.join(PRIVATE,id+'.local.json'),r);
    process.stdout.write('Completed '+id+': '+r.summary.entered+' entries; net '+r.summary.net_pnl.toFixed(2)+'\n');
    return r;
  }
  for(const h of [1,5,10,20]){
    for(const c of Object.keys(CASES))run(h,c);
    for(const cap of [.05,.01,.001])run(h,'base',cap);
    run(h,'depth_base',.05);run(h,'base',null,'scored');run(h,'base',null,'score60');run(h,'base',null,'all','provider');
  }
  run(60,'ideal');run(60,'base');
  const magnitude=magnitudeStudy(ctx),validation={tests:test,oracle:oracle(ctx)},diagnostic=diagnostics(ctx,ledgers);
  const counting=[{definition:'Provider catalogue only',rows:ctx.candidates.filter(r=>r.provider_ordinal>=3)},{definition:'Supplemented same-CIK history',rows:ctx.candidates.filter(r=>r.ordinal>=3)}].map(x=>({definition:x.definition,n:x.rows.length,issuers:new Set(x.rows.map(r=>r.issuer)).size}));
  const base=ledgers.find(r=>r.summary.horizon===10&&r.summary.cost==='base'&&r.summary.cap===null&&r.summary.financial==='all'&&r.summary.ordinal==='extended');
  const qa={ratio_overrides:ctx.actionFlags.length,financial_statuses:Object.fromEntries([...groups(ctx.candidates,r=>r.financial_status)].map(([k,v])=>[k,v.length])),candidates:ctx.candidates.length,candidate_issuers:new Set(ctx.candidates.map(r=>r.issuer)).size,complete_lifetime_history:false,new_market_data_spend:0};
  const doc={schema:'repeat_magnitude_study.v1',built_at:new Date().toISOString(),price_asof:ctx.prices.last,protocol:declared,counting,models,magnitude,diagnostic,validation,data_quality:qa,
    inputs:[path.join(CACHE,'effective_events.local.json'),path.join(CACHE,'corporate_action_repairs.json'),path.join(RUN,'event_outcomes.parts.json'),path.join(RUN,'prices.sqlite'),__filename].map(f=>({file:path.relative(ROOT,f).replace(/\\/g,'/'),sha256:hash(f)}))};
  json(path.join(OUT,'summary.json'),doc);json(path.join(PRIVATE,'candidates.local.json'),ctx.candidates);
  json(path.join(PRIVATE,'audit.local.json'),{ratio_overrides:ctx.actionFlags,oracle:validation.oracle,
    residuals:ledgers.map(r=>({options:{h:r.summary.horizon,cost:r.summary.cost,cap:r.summary.cap,financial:r.summary.financial,ordinal:r.summary.ordinal},positions:r.positions.filter(p=>p.units>1e-9).map(p=>({id:p.id,ticker:p.ticker,issuer:p.issuer,entry:p.day,planned_exit:p.planned_exit,liability:p.open_liability,units:p.units,identity_unresolved:p.identity_unresolved,action_conflict:p.action_conflict}))})),
    outliers:base.positions.slice().sort((a,b)=>a.pnl-b.pnl).filter((p,i,a)=>i<10||i>=a.length-10)});
  const md=makeReport(doc)+additionalReport(doc);fs.writeFileSync(path.join(OUT,'REPORT.md'),md);
  fs.writeFileSync(path.join(OUT,'REPORT.html'),htmlReport(doc,md,base));
  ctx.prices.close();console.log(JSON.stringify({saved:OUT,models:models.length,counting,base:base.summary},null,2));
}
module.exports={load,label,replay,tests,extendedTests,diagnostics,protocol,regression,stats,magnitudeStudy,makeReport,htmlReport,enrichSummary,additionalReport};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});


function extendedTests(){
  const assert=require('node:assert/strict'),days=[];
  for(let d='2025-01-02';days.length<45;d=A.dateAfter(d))if(![0,6].includes(new Date(d+'T12:00:00Z').getUTCDay()))days.push(d);
  function fixture({action=false,missing=false,capacity=false}={}){
    const index=new Map(days.map((d,i)=>[d,i]));
    const row={id:'fixture',issuer:'cik/1',ticker:'TEST',day:days[0],i:0,ordinal:3,provider_ordinal:3,entry_price:10,liquidity_complete:true,adv_shares:1000,scored:true,score:70};
    const point=(t,d)=>({open:10,high:10,low:8,close:action&&d>days[0]?80:8,volume:capacity&&index.get(d)<2?0:100000});
    const prices={days,index,last:days.at(-1),point,ssrQuery:{get:()=>({restricted:0})}};
    return {candidates:[row],prices,auction:(t,d)=>({open:10,close:missing?null:action&&d>days[0]?80:8}),
      factor:(t,a,b)=>action&&a<b?10:1,settlement:d=>days[index.get(d)+1]||A.dateAfter(d)};
  }
  let r=replay(fixture(),{horizon:1,cost:'ideal',cap:null,financial:'all',ordinal:'extended'});
  assert.equal(r.summary.net_pnl,5000);assert.equal(r.summary.closed,1);
  r=replay(fixture({action:true}),{horizon:5,cost:'ideal',cap:null,financial:'all',ordinal:'extended'});
  assert.equal(r.summary.net_pnl,5000);assert.equal(r.positions[0].factor,10);
  r=replay(fixture({missing:true}),{horizon:5,cost:'ideal',cap:null,financial:'all',ordinal:'extended'});
  assert.equal(r.summary.closed,0);assert.equal(r.summary.open_positions,1);assert.equal(r.summary.open_liability,20000);assert.equal(r.summary.net_pnl,5000);
  const f=fixture();f.prices.point=(t,d)=>({open:10,high:10,low:8,close:8,volume:d===days[1]?100:100000});
  r=replay(f,{horizon:2,cost:'ideal',cap:.05,financial:'all',ordinal:'extended'});
  assert.equal(r.summary.entered,1);assert.equal(r.positions[0].entry_units,50);
  assert.equal(r.positions[0].cover_children,2);assert.equal(r.summary.net_pnl,100);
  return {synthetic_portfolio_assertions:12,passed:true,cases:['fixed-dollar gain','intervening 1-for-10 action','missing exit retains full liability','liquidity-constrained partial covers']};
}
function diagnostics(ctx,ledgers){
  const primary=ledgers.filter(r=>r.summary.horizon<=20&&r.summary.ordinal==='extended'&&r.summary.financial==='all'&&r.summary.cost==='base');
  const chronological=primary.flatMap(r=>['2023-2024','2025','2026'].map(period=>{
    const ps=r.positions.filter(p=>period==='2023-2024'?p.day<'2025-01-01':p.day.startsWith(period));
    return {h:r.summary.horizon,cap:r.summary.cap,entry_period:period,trades:ps.length,issuers:new Set(ps.map(p=>p.issuer)).size,marked_pnl:sum(ps.map(p=>p.pnl)),net_per_entry_dollar:sum(ps.map(p=>p.entry_reference_notional))?sum(ps.map(p=>p.pnl))/sum(ps.map(p=>p.entry_reference_notional)):null,unresolved:ps.filter(p=>p.units>0).length};
  }));
  const exact=[];
  for(const h of [1,5,10,20])for(const multiple of [5,10,20,50,100])for(const cohort of ['all','scored','score60','third_plus']){
    const rows=ctx.candidates.filter(r=>r.i!==undefined&&r.i<=ctx.prices.days.length-20&&Math.abs(r.multiple-multiple)<1e-7)
      .map(r=>label(ctx,r,h)).filter(r=>r.status==='observed'&&(cohort==='all'||cohort==='scored'&&r.scored||cohort==='score60'&&r.scored&&r.score>=60||cohort==='third_plus'&&r.ordinal>=3));
    exact.push({h,multiple,cohort,...stats(rows)});
  }
  const full20=ledgers.find(r=>r.summary.horizon===20&&r.summary.cost==='base'&&r.summary.cap===null&&r.summary.financial==='all'&&r.summary.ordinal==='extended');
  const cap20=ledgers.find(r=>r.summary.horizon===20&&r.summary.cost==='base'&&r.summary.cap===.05&&r.summary.financial==='all'&&r.summary.ordinal==='extended');
  const capacityPairs=full20.positions.filter(p=>p.closed).map(p=>{const other=cap20.positions.find(q=>q.id===p.id);return other?{id:p.id,full:p.pnl,capped:other.pnl,full_exit:p.closed,capped_exit:other.closed||null,capped_open:other.units>0,entry_fraction:other.entry_reference_notional/p.entry_reference_notional}:null;}).filter(Boolean);
  return {chronological,exact,capacity_comparison:{paired_positions:capacityPairs.length,delayed_or_open_covers:capacityPairs.filter(p=>p.capped_exit!==p.full_exit).length,mean_entry_fraction:mean(capacityPairs.map(p=>p.entry_fraction))},
    limitations:['No sealed holdout touched','Chronological diagnostics reuse explored history and have no retraining','Historical loan capacity and recall paths unobserved']};
}


function movingBlockCI(monthly,B=2000,block=6){
  if(monthly.length<block)return null;const random=rng(77123),draws=[];
  for(let b=0;b<B;b++){const values=[];while(values.length<monthly.length){const start=Math.floor(random()*monthly.length);for(let j=0;j<block&&values.length<monthly.length;j++)values.push(monthly[(start+j)%monthly.length].pnl);}draws.push(mean(values));}
  return [quant(draws,.025),quant(draws,.975)];
}
function additionalReport(doc){
  const money=x=>x==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x);
  const pct=x=>x==null?'—':(100*x).toFixed(2)+'%';
  const table=(h,rows)=>'| '+h.join(' | ')+' |\n| '+h.map(()=>'---').join(' | ')+' |\n'+rows.map(r=>'| '+r.join(' | ')+' |').join('\n')+'\n';
  const get=(h,cap=null)=>doc.models.find(r=>r.horizon===h&&r.cap===cap&&r.cost==='base'&&r.financial==='all'&&r.ordinal==='extended');
  let s='\n## Additional robustness and accounting\n\n### Volume limits across all horizons\n\n';
  s+=table(['Sessions','Sizing','Entries','Mean position','Net P&L','Monthly mean','Max drawdown','Open liability'],[1,5,10,20].flatMap(h=>[null,.05,.01,.001].map(cap=>{const r=get(h,cap);return[h,cap===null?'Full-fill':100*cap+'% ADV/volume',r.entered,money(r.mean_position),money(r.net_pnl),money(r.mean_monthly_since_first_entry),money(r.max_drawdown_dollars),money(r.open_liability)];})));
  s+='\nVolume limits change allocation and cover timing. Smaller capacity is not the full-fill result multiplied by a constant.\n\n### Open versus closed P&L and monthly uncertainty\n\n';
  s+=table(['Model','Closed-trade P&L','Open marked P&L','Monthly mean','6-month-block 95% interval','At least 95% target entries','Break-even APR'],[10,20].flatMap(h=>[null,.05].map(cap=>{const r=get(h,cap);return[h+' sessions / '+(cap===null?'full':'5%'),money(r.closed_trade_pnl),money(r.open_trade_marked_pnl),money(r.mean_monthly_since_first_entry),r.monthly_block_bootstrap_95?.map(money).join(' to '),r.full_target_entries+' / '+r.entered,pct(r.break_even_borrow_apr)];})));
  s+='\nIntervals resample six-month blocks of the same explored monthly history, including zeros; these are sensitivity intervals, not forward guarantees. Break-even APR holds historical marks, covers and base execution fixed. Open marked P&L is not completed profit.\n\n### Entry-year cohorts\n\n';
  s+=table(['Horizon / sizing','Entry period','Trades / issuers','Marked P&L','Return per entry dollar','Unresolved'],doc.diagnostic.chronological.map(r=>[r.h+' / '+(r.cap===null?'full':100*r.cap+'%'),r.entry_period,r.trades+' / '+r.issuers,money(r.marked_pnl),pct(r.net_per_entry_dollar),r.unresolved]));
  s+='\nEntry-year P&L includes later carry and marks through the cutoff, unlike calendar-year changes. All periods were already explored.\n\n### Exact ratio comparison, ten-session gross returns\n\n';
  s+=table(['Exact ratio','All n / mean','Scored n / mean','Score>=60 n / mean','Third+ n / mean'],[5,10,20,50,100].map(m=>{const get=c=>doc.diagnostic.exact.find(r=>r.h===10&&r.multiple===m&&r.cohort===c);return['1-for-'+m,...['all','scored','score60','third_plus'].map(c=>{const r=get(c);return r.n+' / '+pct(r.mean);})];}));
  s+='\nThe >1–<5 bucket includes supplied 1-for-1.5 and 1-for-1.99 actions. Exact ratios avoid mixing 1-for-100 with larger actions. In the twenty-session comparison, '+doc.diagnostic.capacity_comparison.delayed_or_open_covers+' of '+doc.diagnostic.capacity_comparison.paired_positions+' paired full-fill closed positions have a delayed or still-open cover in the 5% model.\n\n### Twenty-session calendar years and months\n\n';
  const full=get(20),cap=get(20,.05);
  s+=table(['Year','Full-fill P&L','5% volume P&L'],full.yearly.map(r=>[r.year,money(r.pnl),money(cap.yearly.find(x=>x.year===r.year)?.pnl)]));
  s+='\n'+table(['Month','Full-fill P&L','5% volume P&L'],full.monthly.map(r=>[r.month,money(r.pnl),money(cap.monthly.find(x=>x.month===r.month)?.pnl)]));
  s+='\nCost references: https://www.interactivebrokers.com/en/pricing/short-sale-cost.php and https://www.interactivebrokers.com/en/trading/short-securities-availability.php . Rates and availability vary; these pages do not supply historical locates. The frozen fee table is a scenario, not a broker invoice.\n';
  return s;
}

function enrichSummary(result){
  const {summary:r,positions:p, daily}=result,closed=p.filter(x=>x.units<=1e-9);
  r.closed_trade_pnl=sum(closed.map(x=>x.pnl));
  r.open_trade_marked_pnl=sum(p.filter(x=>x.units>1e-9).map(x=>x.pnl));
  r.full_target_entries=p.filter(x=>x.filled_fraction>=.95).length;
  r.monthly_block_bootstrap_95=r.fastStats?null:movingBlockCI(r.monthly);
  r.break_even_borrow_apr=r.borrow_cost>0&&CASES[r.cost].apr>0?CASES[r.cost].apr*(r.gross_pnl-r.execution_cost-r.commissions_and_fees)/r.borrow_cost:null;
  return result;
}
