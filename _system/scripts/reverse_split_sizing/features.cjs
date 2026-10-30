'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const A=require('../short_framework/adapters.cjs'),R=require('../third_plus_reconciliation_engine.cjs'),F=require('../third_plus_fundamental_filters.cjs');
const DAY=86400000,read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const digest=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
function rally(ctx,r){const rs=[];for(let i=r.i-5;i<r.i;i++){if(i<1)return null;const a=ctx.prices.days[i-1],b=ctx.prices.days[i],x=ctx.prices.point(r.ticker,a),y=ctx.prices.point(r.ticker,b),f=ctx.factor(r.ticker,a,b);if(!x||!y||!f)return null;rs.push(y.close/f/x.close-1);}return Math.max(...rs)<.5;}
function makeCandidate(ctx,r,day,history,e){
 const i=ctx.prices.index.get(day),at=day?A.nyClock(day,'09:25:00'):null;
 const ordinal=1+new Set(history.filter(s=>s.issuer===r.issuer&&s.day<r.event_date&&s.day<day&&s.known&&Date.parse(s.known)<=Date.parse(at)).map(s=>s.day)).size;
 const prior=day?ctx.prices.prior(r.ticker,day):null,p=day?ctx.prices.point(r.ticker,day):null,f=e.financials||{};
 const fresh=f.period&&day&&(Date.parse(day)-Date.parse(f.period))/DAY>=0&&(Date.parse(day)-Date.parse(f.period))/DAY<=200;
 const scored=f.status==='scored'&&Number.isFinite(f.score)&&f.evidence?.length>0&&fresh&&f.evidence.every(x=>x.filed&&Date.parse(A.nyClock(A.dateAfter(x.filed),'00:00:00'))<=Date.parse(at));
 const z={...r,maturity_index:r.i,day,i,ordinal,decision_at:at,entry_price:day?ctx.auction(r.ticker,day).open||null:null,adv_shares:prior?.adv||0,liquidity_complete:prior?.complete||false,adv_dollars:prior?.complete&&p?prior.adv*p.open:null,year:day?.slice(0,4),scored,score:scored?f.score:null};
 z.signals={rally:rally(ctx,z),score60:scored?f.score>=60:null};return z;
}
function build(ctx,root,work){
 const local=path.join(root,'_system/data/reverse_splits/local'),rec=path.join(local,'third_plus_signal_study/reconciliation');
 const files=new Map(),track=f=>{if(/holdout|sealed/i.test(f))throw new Error('Forbidden source');files.set(path.relative(root,f).replaceAll('\\','/'),digest(f));return read(f);};
 const manifest=track(path.join(rec,'filing_manifest.local.json')),inventory=track(path.join(rec,'source_inventory.local.json')),actionDocs=new Map();
 const parsedHashes=new Map(inventory.parsedInventories.parsed.map(x=>[x.file,x.sha256])),docsBy=new Map(),profiles=new Map();
 for(const f of manifest.filter(x=>x.status==='ok')){const name=f.accession.replaceAll('-','')+'.json',file=path.join(rec,'parsed',name);if(digest(file)!==parsedHashes.get(name))throw new Error('Parsed document changed');const d=track(file);if(d.source_sha256!==f.sha256)throw new Error('Parsed source mismatch');const a=docsBy.get(Number(f.cik))||[];a.push(d);docsBy.set(Number(f.cik),a);}
 const financingManifest=track(path.join(rec,'financing_source_manifest.local.json'));
 for(const source of financingManifest.filter(f=>f.status==='ok')){const file=path.join(rec,'financing_parsed',source.accession.replaceAll('-','')+'.json');if(!fs.existsSync(file))continue;const d=track(file),list=actionDocs.get(Number(d.cik))||[];for(const part of d.parts)list.push({accession:d.accession,filed_at:d.filed_at,source_url:part.url,source_sha256:part.source_sha256,paragraphs:part.paragraphs,text:part.paragraphs.join(' ')});actionDocs.set(Number(d.cik),list);}
 const terms=track(path.join(rec,'terms_source_manifest.local.json'));
 for(const f of terms.concat(manifest.filter(r=>r.file?.endsWith('.txt'))).filter(r=>r.status==='ok')){const file=path.join(root,f.file);if(!fs.existsSync(file))continue;const txt=fs.readFileSync(file).toString('utf8',0,65536),m=txt.match(/STANDARD INDUSTRIAL CLASSIFICATION:\s*[^\r\n]*?\[(\d{4})\]/i);if(!m)continue;files.set(path.relative(root,file).replaceAll('\\','/'),digest(file));const a=profiles.get(Number(f.cik))||[];a.push({profile:F.profile(Number(m[1])),filed_at:f.filed_at,known_at:A.nyClock(A.dateAfter(f.filed_at),'00:00:00')});profiles.set(Number(f.cik),a);}
 const history=ctx.events.filter(e=>e.family==='split').map(e=>({issuer:e.issuer,day:e.event_date,known:e.known_at})).concat(ctx.catalogue.filter(e=>['primary_schedule_matched','structured_corporate_action'].includes(e.verification)&&e.issuer?.startsWith('cik/')&&e.ratio>0&&e.ratio<1).map(e=>({issuer:e.issuer,day:e.ex_date,known:e.available_at})));
 const events=new Map(ctx.events.map(e=>[e.id,e])),rows=[],raws=new Map(),featureCache=new Map(),coverage={events:0,late_disclosure:0,missing_effective_session:0};
 const cashFeature=(e,z)=>{
  const cik=Number(e.cik);if(!raws.has(cik)){const file=path.join(local,'raw/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json');if(!fs.existsSync(file)){raws.set(cik,null);}else{const raw=track(file);if(Number(raw.cik)!==cik)throw new Error('Issuer mismatch');for(const[ns,tags]of Object.entries(raw.facts||{}))for(const tag of Object.keys(tags))if(!/Cash|OperatingActivities|CommonStockSharesOutstanding|EntityCommonStockSharesOutstanding|^(Assets|Liabilities|StockholdersEquity|NetIncomeLoss|Revenues|RevenueFromContractWithCustomerExcludingAssessedTax)$/.test(tag))delete tags[tag];raw.__source_sha256=digest(file);raw.__source_url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json';raws.set(cik,raw);}}
  const raw=raws.get(cik);if(!raw||!z.day)return {burn:null,runway:null,dilution:null};
  const key=e.issuer+'/'+e.ticker+'/'+z.day;if(featureCache.has(key))return featureCache.get(key);
  const at=z.decision_at,docs=docsBy.get(cik)||[],publicRows=R.publicRows(raw,docs,at),fin=R.financial(publicRows,at),profile=(profiles.get(cik)||[]).filter(p=>p.known_at<=at&&(Date.parse(z.day)-Date.parse(p.filed_at))/DAY<=550).sort((a,b)=>b.filed_at.localeCompare(a.filed_at))[0];
  const applicable=!profile||!['financial','lender','fund_or_trust'].includes(profile.profile),valid=applicable&&fin.status==='source_reconciled';
  const share=R.shares(publicRows,[...docs,...(actionDocs.get(cik)||[])],e.ticker,ctx.actions.get(e.ticker)||new Map(),at);
  const result={burn:valid?fin.cfo.value<0:null,runway:valid?fin.cfo.value<0&&fin.reported_runway_years<.5:null,dilution:share.status==='source_reconciled'?share.growth>=.25:share.status==='source_reconciled_threshold_bound'?true:null,financial_status:fin.status,cash_period:fin.cash.period||null,runway_years:fin.reported_runway_years,profile:profile?.profile||'unknown',share_status:share.status};
  featureCache.set(key,result);return result;
 };
 for(const r of ctx.candidates){const e=events.get(r.id);if(r.event_date<'2023-01-01')continue;coverage.events++;
  const annDay=ctx.prices.entryDay(e,'announcement'),splitDay=ctx.prices.index.has(r.event_date)?r.event_date:null;
  const days={announcement:annDay&&annDay<r.event_date?annDay:null,split_day:splitDay&&Date.parse(A.nyClock(splitDay))>Date.parse(e.known_at)+300000?splitDay:null,post_split:r.day};
  if(!days.announcement)coverage.late_disclosure++;if(!splitDay)coverage.missing_effective_session++;if(coverage.events%100===0)console.log('Prepared timing features for '+coverage.events+' source events');
  const matched=Object.values(days).every(Boolean);
  for(const[timing,day]of Object.entries(days)){if(!day)continue;const z=makeCandidate(ctx,r,day,history,e);if(z.ordinal<2)continue;z.timing=timing;z.matched_timing=matched;z.signals={...z.signals,...cashFeature(e,z)};rows.push(z);}
 }
 fs.mkdirSync(work,{recursive:true});fs.writeFileSync(path.join(work,'features.local.json'),JSON.stringify(rows)+'\n');
 return {rows,coverage,input_hashes:Object.fromEntries(files),clock_basis:'filing_date_plus_one_ET_day; exact press-release timestamps unavailable'};
}
function select(rows,rule,{covered=false}={}){
 return rows.filter(r=>r.ordinal>=rule.ordinal&&(!rule.rally||r.signals.rally===true)&&(!rule.cash||r.signals[rule.cash]!==null&&(covered||r.signals[rule.cash]===true))&&(!rule.dilution||r.signals.dilution!==null&&(covered||r.signals.dilution===true))&&(rule.score!=='gate'||r.signals.score60!==null&&(covered||r.signals.score60===true))).map(r=>({...r,raw_target:25000*(covered?1:rule.score==='boost125'&&r.signals.score60===true?1.25:rule.score==='boost150'&&r.signals.score60===true?1.5:1)}));
}
module.exports={build,rally,makeCandidate,select};
