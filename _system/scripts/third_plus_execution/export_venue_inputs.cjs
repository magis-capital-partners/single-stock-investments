'use strict';
// Only local source caches are read. No network or broker capability.
const path=require('node:path'),fs=require('node:fs');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
const ctx=require('./venue_study.cjs').loadContext(root);
try{
 const candidates=ctx.candidates.filter(c=>c.ordinal>=3);
 const sessions=[];
 for(const c of candidates){
  if(c.i===undefined)continue;
  const requests=[{date:c.day,kind:'entry'}];
  for(let i=c.i+19;i<Math.min(c.i+25,ctx.prices.days.length);i++)requests.push({date:ctx.prices.days[i],kind:'cover'});
  for(const s of requests)sessions.push({...s,id:c.id,ticker:c.ticker,issuer:c.issuer,restricted:ctx.prices.ssrQuery.get(c.ticker,s.date)?.restricted??null});
 }
 fs.writeFileSync(out,JSON.stringify({schema:'third_plus_venue_inputs.v2',days:ctx.prices.days,candidates,sessions}));
}finally{ctx.prices.close();}
