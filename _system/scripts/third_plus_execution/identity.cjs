'use strict';
const fs=require('node:fs'),path=require('node:path');
const FILE=path.resolve(__dirname,'../../data/reverse_splits/third_plus_signal_study/ssr_execution_v2/security_lifecycle.v1.json');
const ledger=JSON.parse(fs.readFileSync(FILE,'utf8'));
function validate(d){
 if(d.schema!=='third_plus_security_lifecycle.v1'||!Array.isArray(d.events))throw Error('Invalid security lifecycle');
 const seen=new Set();
 for(const e of d.events){
  const k=[e.issuer,e.ticker,e.effective].join('|');
  if(seen.has(k)||!/^cik\/\d+$/.test(e.issuer)||!/^\d{4}-\d{2}-\d{2}$/.test(e.effective)||!e.source_url?.startsWith('https://www.sec.gov/Archives/'))throw Error('Unsourced or conflicting lifecycle');
  if(!['symbol_change','venue_exit','venue_resume'].includes(e.kind)||e.kind==='symbol_change'&&(!e.successor||e.same_security!==true))throw Error('Unproven security continuity');
  seen.add(k);
 }
 return d;
}
validate(ledger);
function resolve(position,date,data=ledger){
 let ticker=position.ticker,venue='NASDAQ';const sources=[],seen=new Set([ticker]);
 for(const e of data.events.slice().sort((a,b)=>a.effective.localeCompare(b.effective))){
  if(e.issuer!==position.issuer||e.ticker!==ticker||e.effective>date)continue;
  sources.push(e.source_url);
  if(e.kind==='symbol_change'){
   if(seen.has(e.successor))throw Error('Cyclic security lineage');
   ticker=e.successor;seen.add(ticker);
  }else venue=e.kind==='venue_resume'?'NASDAQ':e.destination;
 }
 return {ticker,venue,sources,identity_status:'source_bound'};
}
function factor(ctx,p,date,data=ledger){
 let ticker=resolve(p,p.day,data).ticker,start=p.day,value=1;
 for(const e of data.events.slice().sort((a,b)=>a.effective.localeCompare(b.effective))){
  if(e.kind!=='symbol_change'||e.issuer!==p.issuer||e.ticker!==ticker||e.effective<=start||e.effective>date)continue;
  const f=ctx.factor(ticker,start,e.effective);if(!(f>0))return null;value*=f;ticker=e.successor;start=e.effective;
 }
 const f=ctx.factor(ticker,start,date);return f>0?value*f:null;
}
module.exports={resolve,factor,validate,ledger,FILE};
