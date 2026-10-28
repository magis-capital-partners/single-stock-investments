'use strict';
// Rebuild every feature from source facts at the announcement clock. No old event snapshots.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const F=require('../third_plus_signal/features.cjs'),R=require('../third_plus_reconciliation_engine.cjs'),M=require('../third_plus_fundamental_filters.cjs'),Funding=require('../third_plus_reconciliation_funding.cjs'),A=require('../short_framework/adapters.cjs');
const DAY=86400000,sha=b=>crypto.createHash('sha256').update(b).digest('hex'),read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const SIGNALS={score60:'As-of financial score ≥60',legacy_score60:'Legacy financial score ≥60',S1:'Cash pressure incl. identified financing',S2:'Recent completed equity-linked financing',S3:'Previous split within 180 days',S4:'Share growth ≥25%',S5:'Original weak split-day close · unavailable before split',S6:'Prior 20-session return ≤−20%',S7:'No 50% daily rally',reported_runway:'Reported runway <6 months',burn:'Negative operating cash flow',operating_loss:'Operating loss',revenue15:'Revenue decline ≥15%',margin8:'Operating margin decline ≥8pp',accrual10:'Accrual ratio ≥10%',profit_no_cash:'Profit without operating cash',negative_equity:'Negative equity',debt_distress:'Debt maturity + cash distress',weak_prior_close:'Weak prior completed-session close'};
function arms(){const out=[{id:'all',label:'Every candidate',requires:[]},{id:'rally',label:'No 50% daily rally',requires:['S7']}];
 for(const [key,label]of Object.entries(SIGNALS))if(key!=='S7'){out.push({id:'only_'+key,label,requires:[key]},{id:'rally_'+key,label:'Rally veto + '+label,requires:['S7',key]});}
 for(const a of M.ARMS.filter(a=>a.requires.length>2))out.push({id:a.id,label:a.label,requires:a.requires});
 out.push({id:'burn_weak_prior',label:'Cash burn + weak prior close + rally veto',requires:['S7','burn','weak_prior_close']},{id:'burn_repeat',label:'Cash burn + rapid repeat + rally veto',requires:['S7','burn','S3']},{id:'C1',label:'Cash pressure + recent financing',requires:['S1','S2']},{id:'C2',label:'Cash pressure + financing + rally veto',requires:['S1','S2','S7']},{id:'C3',label:'Original cash/financing/weak split close',requires:['S1','S2','S5','S7']},{id:'C4',label:'Original weak split close + prior weakness',requires:['S5','S6','S7']});
 return out;
}
function loader(root,scores={}){
 const local=path.join(root,'_system/data/reverse_splits/local'),rec=path.join(local,'third_plus_signal_study/reconciliation'),cache=new Map(),receipts={},parsedByCik=new Map(),profiles=new Map();
 const manifestFile=path.join(rec,'filing_manifest.local.json'),manifest=fs.existsSync(manifestFile)?read(manifestFile):[];
 if(fs.existsSync(manifestFile))receipts[path.relative(root,manifestFile).replaceAll('\\','/')]=sha(fs.readFileSync(manifestFile));
 for(const row of manifest.filter(r=>r.status==='ok')){const cik=String(Number(row.cik)),list=parsedByCik.get(cik)||[];list.push(row);parsedByCik.set(cik,list);}
 const reviews=[];for(const name of ['reviewed_financing_claims.local.json','supplemental_financing_reviews.local.json']){const file=path.join(rec,name);if(fs.existsSync(file)){const bytes=fs.readFileSync(file);receipts[path.relative(root,file).replaceAll('\\','/')]=sha(bytes);reviews.push(...read(file).reviews);}}
 const historyCache=new Map();
 function get(cik){cik=String(Number(cik));if(cache.has(cik))return cache.get(cik);
  const file=path.join(local,'raw/companyfacts/CIK'+cik.padStart(10,'0')+'.json');let raw={cik:Number(cik),facts:{}};
  if(fs.existsSync(file)){const bytes=fs.readFileSync(file),original=JSON.parse(bytes);if(Number(original.cik)!==Number(cik))throw Error('Financial source issuer mismatch');const hash=sha(bytes);receipts[path.relative(root,file).replaceAll('\\','/')]=hash;raw.__source_sha256=hash;raw.__source_url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik.padStart(10,'0')+'.json';for(const [ns,tags]of Object.entries(original.facts||{})){raw.facts[ns]={};for(const [tag,value]of Object.entries(tags))if(/Cash|OperatingActivities|SharesOutstanding|SharesIssued|Assets|Liabilities|StockholdersEquity|^Equity$|NetIncomeLoss|ProfitLoss|Revenue|SalesRevenue|OperatingIncome|Debt|Borrowings/.test(tag))raw.facts[ns][tag]=value;}}
  const docs=[];for(const row of parsedByCik.get(cik)||[]){const parsed=path.join(rec,'parsed',row.accession.replaceAll('-','')+'.json');if(!fs.existsSync(parsed))continue;const bytes=fs.readFileSync(parsed),doc=JSON.parse(bytes);if(doc.source_sha256!==row.sha256||Number(doc.cik)!==Number(cik))throw Error('Parsed financial filing receipt mismatch');receipts[path.relative(root,parsed).replaceAll('\\','/')]=sha(bytes);docs.push(doc);
   if(row.file){const source=path.resolve(root,row.file);if(source.startsWith(local+path.sep)&&fs.existsSync(source)){const fd=fs.openSync(source,'r'),buffer=Buffer.alloc(65536);let n;try{n=fs.readSync(fd,buffer,0,buffer.length,0);}finally{fs.closeSync(fd);}const m=buffer.subarray(0,n).toString('utf8').match(/STANDARD INDUSTRIAL CLASSIFICATION:\s*[^\r\n]*?\[(\d{4})\]/i);if(m){const list=profiles.get(cik)||[];list.push({profile:M.profile(Number(m[1])),sic:Number(m[1]),filed_at:row.filed_at,known_at:A.nyClock(A.dateAfter(row.filed_at),'00:00:00'),source_url:row.url,source_sha256:row.sha256});profiles.set(cik,list);}}}
  }
  const value={raw,docs,profiles:profiles.get(cik)||[],reviews:reviews.filter(r=>r.issuer==='cik/'+cik),scores,historyCache};cache.set(cik,value);return value;
 }
 return {get,receipts};
}
function snapshot(ctx,e,at,bundle,past=[]){
 const iso=new Date(at).toISOString(),day=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(at)),raw=bundle?.raw||bundle||{facts:{}},docs=bundle?.docs||[];
 const key=e.issuer+'|'+e.ticker+'|'+iso;let base=bundle?.historyCache?.get(key);
 if(!base){const all=M.rows(raw,docs,iso),financial=R.financial(all,iso),share=R.shares(all,docs,e.ticker,ctx.actions?.get(e.ticker)||new Map(),iso),fresh=financial.status==='source_reconciled';
  const profile=(bundle?.profiles||[]).filter(p=>Date.parse(p.known_at)<=at).sort((a,b)=>b.filed_at.localeCompare(a.filed_at))[0]||null;
  const state=x=>x===null?'unknown':x?'pass':'fail';
  const initial={id:e.id,issuer:e.issuer,ticker:e.ticker,event_date:e.event_date,signals:{reported_runway:{state:fresh?state(financial.cfo.value<0&&financial.reported_runway_years<.5):'unknown'},S4:{state:['source_reconciled','source_reconciled_threshold_bound'].includes(share.status)?state((share.growth??share.growth_lower_bound)>=.25):'unknown'}},reconciliation:{clock:{at:iso,entry_eligible:true},financial}};
  const full=financial.cash.period?M.buildOne(initial,all,profile):{signals:{...Object.fromEntries(Object.keys(SIGNALS).map(k=>[k,{state:'unknown'}])),...initial.signals},profile:profile||{profile:'unknown'}};
  const funding=Funding.caseFunding({id:e.id,issuer:e.issuer,clock:{at:iso},financial},bundle?.reviews||[],[]);
  const fundingUnknown=funding.unresolved_cash_items.length>0,adjusted=funding.reported_cash_plus_identified_components;
  full.signals.S1={state:!fresh||fundingUnknown?'unknown':state(financial.cfo.value<0&&adjusted/-financial.cfo.value<.5),reason:'reported_cash_plus_identified_asof_flows_incomplete_coverage_assumption'};
  // Automated completed-claim diagnostic; never present as independent saleability verification.
  full.signals.S2={state:funding.documented_recent_count>0?'pass':'unknown',reason:'cached_completed_equity_linked_claim_not_independent_saleability_proof'};
  const rating=bundle?.scores?.[e.cik+'|'+day];full.signals.score60={state:rating?.score===null||rating?.score===undefined?'unknown':state(rating.score>=60)};full.signals.legacy_score60={state:rating?.legacy_score===null||rating?.legacy_score===undefined?'unknown':state(rating.legacy_score>=60)};
  base={signals:Object.fromEntries(Object.entries(full.signals).map(([k,v])=>[k,v.state])),financial_status:financial.status,financial_period:financial.cash.period||null,share_status:share.status,profile:full.profile.profile,adjusted_cash_coverage:'identified_cached_flows_only',financing_claims:funding.documented_recent_count,score:rating?.score??null,legacy_score:rating?.legacy_score??null};bundle?.historyCache?.set(key,base);
 }
 const knownDays=ctx.prices.days.filter(d=>(ctx.sessionBounds?.get(d)?.close??Date.parse(A.nyClock(d,'16:00:00')))+60000<=at),last=knownDays.at(-1);
 function adjusted(a,b){const pa=ctx.prices.point(e.ticker,a),pb=ctx.prices.point(e.ticker,b),f=ctx.factor(e.ticker,a,b);return pa&&pb&&f>0?pb.close/f/pa.close-1:null;}
 const five=knownDays.slice(-6),returns=five.slice(1).map((d,j)=>adjusted(five[j],d)),r20=knownDays.length>=21?adjusted(knownDays.at(-21),last):null;
 const prior=past.filter(h=>h.issuer===e.issuer&&h.day<e.event_date&&h.day<day&&Date.parse(h.known)<=at).sort((a,b)=>b.day.localeCompare(a.day))[0],weak=d=>{const p=d&&ctx.prices.point(e.ticker,d);return p&&p.high>p.low?(p.close<p.open&&(p.close-p.low)/(p.high-p.low)<=.25?'pass':'fail'):'unknown';};
 const splitCloseKnown=knownDays.includes(e.event_date);
 return {...base,...base.signals,S7:returns.length===5&&returns.every(Number.isFinite)?(Math.max(...returns)<.5?'pass':'fail'):'unknown',S6:Number.isFinite(r20)&&knownDays.slice(-21).every(d=>ctx.prices.point(e.ticker,d))?(r20<=-.2?'pass':'fail'):'unknown',S3:prior?((at-Date.parse(prior.day+'T12:00:00Z'))/DAY<=180?'pass':'fail'):'unknown',S5:splitCloseKnown?weak(e.event_date):'unknown',weak_prior_close:weak(last),last_completed_price_day:last||null,decision_at:iso,decision_day:day};
}
module.exports={SIGNALS,arms,loader,snapshot};
