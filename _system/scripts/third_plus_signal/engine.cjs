'use strict';
const A=require('../short_framework/adapters.cjs');
const F=require('./features.cjs'),S=require('./statistics.cjs');
function shiftCandidate(ctx,r,shift,exitAnchor=false){
 const i=r.i===undefined?undefined:r.i+shift,day=i===undefined?null:ctx.prices.days[i];
 if(!day)return {...r,day:null,i:undefined,entry_price:null};
 const p=ctx.prices.point(r.ticker,day),prior=ctx.prices.prior(r.ticker,day);
 return {...r,i,day,entry_price:ctx.auction(r.ticker,day).open||null,adv_shares:prior.adv,liquidity_complete:prior.complete,
  adv_dollars:prior.complete&&p?prior.adv*p.open:null,year:day.slice(0,4),original_entry:r.original_entry||r.day,maturity_index:r.maturity_index??r.i,
  ...(exitAnchor?{exit_index_override:r.i+19}:{})};
}
function delayConfirmation(ctx,candidates){
 const rows=[],audit=[];
 for(const r of candidates){
   if(r.i===undefined){audit.push({id:r.id,status:'missing_original_entry'});continue;}
   let bounced=false,trigger=null,unknown=false;
   for(let k=0;k<3;k++){
     const i=r.i+k,day=ctx.prices.days[i],prev=ctx.prices.days[i-1],p=day?ctx.prices.point(r.ticker,day):null,q=prev?ctx.prices.point(r.ticker,prev):null;
     const factor=day&&prev?ctx.factor(r.ticker,prev,day):null;
     if(!p||!q||!factor){unknown=true;break;}
     if(bounced&&p.close/factor<q.low){trigger=k+1;break;}
     if(p.close/factor>q.close)bounced=true;
   }
   if(trigger!==null){rows.push(shiftCandidate(ctx,r,trigger));audit.push({id:r.id,status:'triggered',lag:trigger});}
   else audit.push({id:r.id,status:unknown?'unknown_price_path':'no_completed_failed_bounce'});
 }
 return {rows,audit};
}
function trainingRecords(result,embargoDay){
 return result.positions.filter(p=>p.closed&&p.closed<embargoDay&&p.pending_returns.every(x=>x.day<embargoDay)&&p.units<=1e-9);
}
function quarter(date){return date.slice(0,4)+'Q'+(Math.floor((Number(date.slice(5,7))-1)/3)+1);}
function walkForward(ctx,results,featureIndex,run){
 const firsts=ctx.candidates.filter(r=>r.ordinal>=3&&r.day),quarters=[...new Set(firsts.map(r=>quarter(r.day)))].sort(),decisions=[],chosen=[];
 const primary=results.filter(r=>r.arm!=='score60'),baseline=primary.find(r=>r.arm==='baseline');
 for(const q of quarters){
   const year=Number(q.slice(0,4)),part=Number(q.slice(-1)),start=year+'-'+String((part-1)*3+1).padStart(2,'0')+'-01';
   const session=ctx.prices.days.findIndex(d=>d>=start),embargo=ctx.prices.days[Math.max(0,session-20)];
   const pool=trainingRecords(baseline,embargo),poolIssuers=new Set(pool.map(p=>p.issuer)).size,candidates=[];
   if(year>=2025&&poolIssuers>=30){
     for(const r of primary.filter(r=>r.arm!=='baseline')){
       const ps=trainingRecords(r,embargo),n=new Set(ps.map(p=>p.issuer)).size;
       if(n<30)continue;
       const a=new Map([...S.grouped(ps,p=>p.issuer)].map(([id,v])=>[id,S.sum(v.map(p=>p.pnl))]));
       const b=new Map([...S.grouped(pool,p=>p.issuer)].map(([id,v])=>[id,S.sum(v.map(p=>p.pnl))]));
       const ids=[...new Set([...a.keys(),...b.keys()])],values=ids.map(id=>(a.get(id)||0)-(b.get(id)||0));
       const uncertainty=S.bootstrap(values,{B:2000});
       candidates.push({arm:r.arm,n,increment:S.sum(values),p:uncertainty.p_positive});
     }
     const tested=F.ARMS.filter(a=>!['baseline','score60'].includes(a.id)).map(a=>candidates.find(c=>c.arm===a.id)||{arm:a.id,n:0,increment:0,p:1});
     S.holm(tested);
     candidates.splice(0,candidates.length,...tested.filter(c=>c.n>=30&&c.increment>0&&c.holm_p<=.05).sort((a,b)=>b.increment-a.increment||a.arm.localeCompare(b.arm)));
   }
   const selected=candidates[0]?.arm||'baseline';
   decisions.push({quarter:q,selection_at:A.nyClock(start,'00:00:00'),embargo_day:embargo,training_issuers:poolIssuers,
     arm:selected,reason:selected==='baseline'?'insufficient_prior_completed_evidence':'prior_completed_issuer_Holm_selection',
     training_cutoff_rule:'closed position and modeled loan returns strictly before 20-session embargo'});
   for(const r of firsts.filter(r=>quarter(r.day)===q))if(selected==='baseline'||F.armState(featureIndex.get(r.id),selected).state==='pass')chosen.push(r);
 }
 return {decisions,result:run('walk_forward',{horizon:20,cost:'base',cap:.01,ssrMode:'strict',causalCarry:true,...(baseline.summary.nav?{nav:baseline.summary.nav,maximumNames:baseline.summary.maximumNames||3}:{})},chosen,{kind:'walk_forward',arm:'walk_forward'})};
}
module.exports={shiftCandidate,delayConfirmation,trainingRecords,quarter,walkForward};
