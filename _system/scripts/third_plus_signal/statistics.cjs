'use strict';
const sum=x=>x.reduce((a,b)=>a+b,0),mean=x=>x.length?sum(x)/x.length:null;
function quant(xs,p){if(!xs.length)return null;const a=xs.slice().sort((a,b)=>a-b),i=(a.length-1)*p;return a[Math.floor(i)]+(a[Math.ceil(i)]-a[Math.floor(i)])*(i%1);}
function rng(seed=881711){let s=seed>>>0;return()=>{s=(1664525*s+1013904223)>>>0;return s/4294967296;};}
function grouped(rows,fn){const m=new Map();for(const r of rows){const k=fn(r),a=m.get(k)||[];a.push(r);m.set(k,a);}return m;}
function months(daily,first){
 const rows=daily.filter(d=>d.date>=first);
 return [...grouped(rows,r=>r.date.slice(0,7))].map(([month,ds])=>({month,pnl:sum(ds.map(d=>d.change))}));
}
function normalise(result,first){
 const s=result.summary;
 s.common_monthly=months(result.daily,first);s.common_mean_monthly=mean(s.common_monthly.map(m=>m.pnl));
 s.common_window_first=first;s.worst_adverse_price_return=result.positions.length?Math.max(...result.positions.map(p=>p.max_adverse_price_return||0)):null;
 s.issuer_concentration=[...grouped(result.positions,p=>p.issuer)].map(([issuer,ps])=>({issuer,pnl:sum(ps.map(p=>p.pnl))}));
 const all=grouped(result.positions,p=>p.year);
 s.entry_years=[...all].map(([year,ps])=>({year,n:ps.length,issuers:new Set(ps.map(p=>p.issuer)).size,net_pnl:sum(ps.map(p=>p.pnl)),open:ps.filter(p=>p.units>1e-9).length}));
 return result;
}
function bootstrap(values,{block=1,B=4000,seed=881711}={}){
 const n=values.length;
 if(n<2)return {n,total:sum(values),interval:null,p_positive:1};
 const random=rng(seed),observed=mean(values),totals=[];let beyond=0;
 for(let b=0;b<B;b++){let total=0,k=0;while(k<n){const i=Math.floor(random()*n);for(let j=0;j<block&&k<n;j++,k++)total+=values[(i+j)%n];}totals.push(total);if(total/n-observed>=observed-1e-12)beyond++;}
 return {n,total:sum(values),interval:[quant(totals,.025),quant(totals,.975)],p_positive:(beyond+1)/(B+1)};
}
function comparison(result,baseline,{B=4000}={}){
 const a=new Map(result.summary.issuer_concentration.map(x=>[x.issuer,x.pnl])),b=new Map(baseline.summary.issuer_concentration.map(x=>[x.issuer,x.pnl]));
 const ids=[...new Set([...a.keys(),...b.keys()])],issuer=bootstrap(ids.map(k=>(a.get(k)||0)-(b.get(k)||0)),{B});
 const ma=new Map(result.summary.common_monthly.map(x=>[x.month,x.pnl])),mb=new Map(baseline.summary.common_monthly.map(x=>[x.month,x.pnl]));
 const monthIds=[...new Set([...ma.keys(),...mb.keys()])].sort(),calendar=bootstrap(monthIds.map(k=>(ma.get(k)||0)-(mb.get(k)||0)),{block:6,B});
 return {incremental_net:result.summary.net_pnl-baseline.summary.net_pnl,
   issuer_bootstrap_95:issuer.interval,calendar_block_total_95:calendar.interval,
   p_issuer:issuer.p_positive,p_calendar:calendar.p_positive,p_conservative:Math.max(issuer.p_positive,calendar.p_positive),
   baseline_entered:baseline.summary.entered,baseline_issuers:baseline.summary.issuers,
   monthly_increment:monthIds.map(k=>({month:k,delta:(ma.get(k)||0)-(mb.get(k)||0)}))};
}
function holm(rows){
 const ordered=rows.map((r,i)=>({i,p:r.p??1})).sort((a,b)=>a.p-b.p);let last=0;
 for(let j=0;j<ordered.length;j++){const r=ordered[j];last=Math.max(last,Math.min(1,r.p*(ordered.length-j)));rows[r.i].holm_p=last;}return rows;
}
function invert(a){
 const n=a.length,m=a.map((r,i)=>[...r,...Array.from({length:n},(_,j)=>+(i===j))]);
 for(let i=0;i<n;i++){let k=i;for(let j=i+1;j<n;j++)if(Math.abs(m[j][i])>Math.abs(m[k][i]))k=j;if(Math.abs(m[k][i])<1e-9)return null;[m[i],m[k]]=[m[k],m[i]];const d=m[i][i];for(let j=0;j<2*n;j++)m[i][j]/=d;for(let r=0;r<n;r++)if(r!==i){const f=m[r][i];for(let j=0;j<2*n;j++)m[r][j]-=f*m[i][j];}}
 return m.map(r=>r.slice(n));
}
function controlledSignal(rows){
 rows=rows.filter(r=>Number.isFinite(r.y)&&r.adv>0&&r.price>0&&r.ratio>0&&typeof r.pass==='boolean');
 const years=[...new Set(rows.map(r=>r.year))].sort(),names=['intercept','signal_pass','log2_ratio','ordinal_4_plus','log_price','log_ADV',...years.slice(1).map(y=>'year_'+y)];
 const p=names.length,n=rows.length,G=new Set(rows.map(r=>r.issuer)).size;
 if(n<p+5||G<10||new Set(rows.map(r=>r.pass)).size<2)return {n,issuers:G,status:'insufficient_support'};
 const X=rows.map(r=>[1,+r.pass,Math.log2(r.ratio),+(r.ordinal>=4),Math.log(r.price),Math.log(r.adv),...years.slice(1).map(y=>+(r.year===y))]);
 const xx=Array.from({length:p},()=>Array(p).fill(0)),xy=Array(p).fill(0);
 X.forEach((x,i)=>{for(let j=0;j<p;j++){xy[j]+=x[j]*rows[i].y;for(let k=0;k<p;k++)xx[j][k]+=x[j]*x[k];}});
 const inv=invert(xx);if(!inv)return {n,issuers:G,status:'singular'};
 const beta=inv.map(v=>sum(v.map((z,i)=>z*xy[i]))),scores=new Map();
 X.forEach((x,i)=>{const u=rows[i].y-sum(x.map((z,j)=>z*beta[j])),s=scores.get(rows[i].issuer)||Array(p).fill(0);x.forEach((v,j)=>s[j]+=v*u);scores.set(rows[i].issuer,s);});
 const meat=Array.from({length:p},()=>Array(p).fill(0));for(const s of scores.values())for(let j=0;j<p;j++)for(let k=0;k<p;k++)meat[j][k]+=s[j]*s[k];
 const scale=G/(G-1)*(n-1)/(n-p),j=1;
 const variance=scale*sum(inv[j].map((a,k)=>sum(inv[j].map((b,l)=>a*b*meat[k][l])))),se=Math.sqrt(Math.max(0,variance));
 return {n,issuers:G,status:'exploratory_issuer_cluster_OLS',coefficient:beta[j],normal_95:[beta[j]-1.96*se,beta[j]+1.96*se],controls:names.slice(2)};
}
function eligibleForPromotion(result,all,covered,holmP){
 const s=result.summary,why=[];
 if(s.issuers<30)why.push('fewer_than_30_issuers');
 if(all.incremental_net<=0)why.push('no_incremental_full_universe_profit');
 if(covered.incremental_net<=0)why.push('no_incremental_covered_universe_profit');
 if(!all.issuer_bootstrap_95||all.issuer_bootstrap_95[0]<=0||!all.calendar_block_total_95||all.calendar_block_total_95[0]<=0)why.push('increment_uncertain');
 if(holmP>.05)why.push('family_adjusted_evidence_insufficient');
 if(s.max_drawdown_dollars<all.baseline_drawdown)why.push('worse_drawdown');
 if(s.pnl_without_best_issuer<=0||s.pnl_without_best5_issuers<=0)why.push('concentrated_or_nonpositive_profit');
 if(s.open_positions>0)why.push('unresolved_obligations');
 return {status:why.length?(s.issuers<30?'insufficient_evidence':'rejected'):'research_candidate',reasons:why};
}
module.exports={sum,mean,quant,rng,grouped,months,normalise,bootstrap,comparison,holm,controlledSignal,eligibleForPromotion};
