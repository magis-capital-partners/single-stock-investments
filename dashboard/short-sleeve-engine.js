/* Deterministic historical-month block bootstrap. No normal-return assumption. */
(function (root) {
  'use strict';
  const quantile = (values, p) => {
    const a=values.filter(Number.isFinite).sort((x,y)=>x-y);
    if(!a.length)return null;
    const x=(a.length-1)*p,i=Math.floor(x);return a[i]+(a[Math.ceil(x)]-a[i])*(x-i);
  };
  function random(seed) { let x=seed>>>0;return ()=>{x+=0x6D2B79F5;let t=x;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;}; }
  function monteCarlo(days, models, trials=2000, years=5, seed=19261019) {
    const months=[];
    days.forEach((d,i)=>{if(!i||d.slice(0,7)!==days[i-1].slice(0,7))months.push([]);months.at(-1).push(i);});
    if(!months.length)throw new Error('Historical session blocks are missing.');
    // Boundary months can contain the worst loss. Retain every available
    // session, including partial months, rather than conditioning on omission.
    const blocks=months;
    const rng=random(seed), sessions=Math.round(252*years), selections=[];
    for(let n=0;n<trials;n++){
      const indices=[];
      while(indices.length<sessions)indices.push(...blocks[Math.floor(rng()*blocks.length)]);
      selections.push(indices.slice(0,sessions));
    }
    const result={};
    for(const model of models){
      const delta=new Float64Array(days.length),margin=new Float64Array(days.length),collateral=new Float64Array(days.length);
      model.series.forEach(r=>{delta[r[0]]=r[1];margin[r[0]]=r[2];collateral[r[0]]=r[3];});
      const cagr=[],drawdowns=[],calmar=[],ending=[],peakMargins=[],peakCollateral=[];
      const bands=Array.from({length:Math.ceil(sessions/21)+1},()=>[]);let ruined=0,losses=0;
      for(const indices of selections){
        let value=1,peak=1,dd=0,pm=0,pc=0,ruin=false;bands[0].push(1);
        for(let j=0;j<sessions;j++){
          if(!ruin){value+=delta[indices[j]];peak=Math.max(peak,value);dd=Math.min(dd,value/peak-1);pm=Math.max(pm,margin[indices[j]]);pc=Math.max(pc,collateral[indices[j]]);if(value<=0)ruin=true;}
          if((j+1)%21===0)bands[(j+1)/21].push(value);
        }
        if(sessions%21)bands.at(-1).push(value);
        const growth=value>0&&!ruin ? Math.pow(value,1/years)-1 : null;
        cagr.push(growth);drawdowns.push(-dd);calmar.push(growth!=null&&dd<0?growth/-dd:null);ending.push(value);peakMargins.push(pm);peakCollateral.push(pc);
        ruined+=Number(ruin);losses+=Number(value<1);
      }
      const dist=a=>({p05:quantile(a,.05),p50:quantile(a,.5),p95:quantile(a,.95)});
      // Undefined insolvent CAGRs retain their lower-tail rank; never silently condition growth on survival.
      const growthQuantile=p=>{const a=cagr.map(v=>v==null?-Infinity:v).sort((a,b)=>a-b),x=(a.length-1)*p,i=Math.floor(x),lo=a[i],hi=a[Math.ceil(x)];return Number.isFinite(lo)&&Number.isFinite(hi)?lo+(hi-lo)*(x-i):null;};
      result[model.scenario]={trials,years,seed,cagr:{p05:growthQuantile(.05),p50:growthQuantile(.5),p95:growthQuantile(.95)},max_drawdown:dist(drawdowns),calmar:dist(calmar),ending:dist(ending),
        peak_margin:dist(peakMargins),peak_collateral:dist(peakCollateral),ruin_probability:ruined/trials,loss_probability:losses/trials,
        fan:bands.map((a,i)=>({month:i,p05:quantile(a,.05),p50:quantile(a,.5),p95:quantile(a,.95)}))};
    }
    return result;
  }
  const api={quantile,random,monteCarlo};
  root.ShortSleeveEngine=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
