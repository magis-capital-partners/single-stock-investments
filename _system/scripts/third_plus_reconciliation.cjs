#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const B=require('./reverse_split_repeat_study.cjs'),E=require('./third_plus_reconciliation_engine.cjs'),F=require('./third_plus_reconciliation_funding.cjs');
const ROOT=path.resolve(__dirname,'../..'),LOCAL=path.join(ROOT,'_system/data/reverse_splits/local'),WORK=path.join(LOCAL,'third_plus_signal_study/reconciliation'),OUT=path.join(ROOT,'_system/data/reverse_splits/third_plus_signal_study/reconciliation_v2');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),write=(f,x)=>{fs.mkdirSync(path.dirname(f),{recursive:true});fs.writeFileSync(f,JSON.stringify(x,null,2)+'\n');};
function build(){
 const population=read(path.join(WORK,'population.local.json')),manifest=read(path.join(WORK,'filing_manifest.local.json')),parsed=new Map();
 for(const f of manifest.filter(x=>x.status==='ok')){const file=path.join(WORK,'parsed',f.accession.replaceAll('-','')+'.json');if(!fs.existsSync(file))continue;const d=read(file);if(d.source_sha256!==f.sha256)throw new Error('Parsed source hash mismatch');const list=parsed.get(d.cik)||[];list.push(d);parsed.set(d.cik,list);}
 const actionDocs=new Map(),financeSourceIndex=new Map();const financeManifestFile=path.join(WORK,'financing_source_manifest.local.json');
 if(fs.existsSync(financeManifestFile))for(const source of read(financeManifestFile).filter(f=>f.status==='ok')){const file=path.join(WORK,'financing_parsed',source.accession.replaceAll('-','')+'.json');if(!fs.existsSync(file))continue;const d=read(file);financeSourceIndex.set(d.accession,d);const list=actionDocs.get(d.cik)||[];for(const part of d.parts)list.push({accession:d.accession,filed_at:d.filed_at,source_url:part.url,source_sha256:part.source_sha256,paragraphs:part.paragraphs,text:part.paragraphs.join(' ')});actionDocs.set(d.cik,list);}
 const contractIndex=new Map();const contractFolder=path.join(WORK,'terms_parsed');if(fs.existsSync(contractFolder))for(const name of fs.readdirSync(contractFolder).filter(n=>n.endsWith('.json'))){const doc=read(path.join(contractFolder,name));contractIndex.set(doc.accession,doc);}
 const reviewFiles=['reviewed_financing_claims.local.json','supplemental_financing_reviews.local.json'].map(f=>path.join(WORK,f)).filter(fs.existsSync);
 const reviews=reviewFiles.flatMap(f=>read(f).reviews);F.validateReviews(reviews,financeSourceIndex,contractIndex);
 const financeManifest=fs.existsSync(financeManifestFile)?read(financeManifestFile):[];
 const ctx=B.load(),raws=new Map(),result=[],rawHashes={};
 try{for(const event of population){const cik=Number(event.issuer.split('/')[1]);if(!raws.has(cik)){const file=path.join(LOCAL,'raw/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json'),bytes=fs.readFileSync(file),raw=JSON.parse(bytes);raw.__source_sha256=crypto.createHash('sha256').update(bytes).digest('hex');raw.__source_url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json';rawHashes[cik]=raw.__source_sha256;raws.set(cik,raw);}
 const clock=E.clock(event),docs=parsed.get(cik)||[],facts=E.publicRows(raws.get(cik),docs,clock.at);
 result.push({...event,clock,financial:E.financial(facts,clock.at),shares:E.shares(facts,[...docs,...(actionDocs.get(cik)||[])],event.ticker,ctx.actions.get(event.ticker),clock.at)});
 }}finally{ctx.prices.close();}
 for(const event of result)event.financing=F.caseFunding(event,reviews,financeManifest);
 write(path.join(WORK,'reconciled_events.local.json'),result);
 const original=read(path.join(WORK,'../features.local.json')),byId=new Map(original.map(s=>[s.id,s]));
 const features=result.map(event=>{
  const old=byId.get(event.id);if(!old)throw new Error('Missing original feature snapshot');const output=JSON.parse(JSON.stringify(old));
  output.reconciliation=event;output.reconciliation_version='v2';output.signals_v1=output.signals;output.signals={...output.signals};
  const active=event.clock.entry_eligible,fin=event.financial,share=event.shares;
  output.signals.reported_runway=!active?{state:'unknown',reason:'no_original_entry_session'}:fin.status==='source_reconciled'?{state:fin.cfo.value<0&&fin.reported_runway_years<.5?'pass':'fail',reason:'reconciled_reported_cash_runway',value:fin.reported_runway_years,source_evidence:fin}:{state:'unknown',reason:fin.status,source_evidence:fin};
  output.signals.S4=!active?{state:'unknown',reason:'no_original_entry_session'}:share.status==='source_reconciled'?{state:share.growth>=.25?'pass':'fail',reason:'source_reconciled_common_share_growth',value:share.growth,source_evidence:share}:share.status==='source_reconciled_threshold_bound'?{state:'pass',reason:'issued_share_upper_bound_proves_25pct_dilution',value:null,growth_lower_bound:share.growth_lower_bound,source_evidence:share}:{state:'unknown',reason:share.status,source_evidence:share};
  output.signals.S1={state:active&&fin.status==='source_reconciled'&&fin.cfo.value>=0?'fail':'unknown',reason:!active?'no_original_entry_session':fin.status!=='source_reconciled'?fin.status:fin.cfo.value>=0?'nonnegative_reconciled_TTM_CFO':'adjusted_cash_completeness_not_verified',reported_only:output.signals.reported_runway};
  output.signals.S2={state:'unknown',reason:'independent_transaction_and_saleability_review_not_complete',documented_recent_financings:event.financing.documented_recent_completed_financings};
  return output;
 });
 write(path.join(WORK,'reconciled_features.local.json'),features);write(path.join(WORK,'companyfacts_hashes.local.json'),rawHashes);
 const count=fn=>Object.fromEntries(Object.entries(Object.groupBy(result,fn)).map(([k,v])=>[k,v.length]));
 const summary={schema:'third_plus_reconciliation.results.v2',built_at:new Date().toISOString(),events:result.length,financial_reports_recovered:manifest.filter(x=>x.status==='ok').length,financial_reports_parsed:[...parsed.values()].reduce((a,v)=>a+v.length,0),
 cash_status:count(x=>x.financial.cash.status),cashflow_status:count(x=>x.financial.cfo.status),financial_status:count(x=>x.financial.status),shares_status:count(x=>x.shares.status),
 cash_numeric:result.filter(x=>Number.isFinite(x.financial.cash.value)).length,ttm_cfo_numeric:result.filter(x=>Number.isFinite(x.financial.cfo.value)).length,share_growth_numeric:result.filter(x=>Number.isFinite(x.shares.growth)).length,share_threshold_resolved:result.filter(x=>Number.isFinite(x.shares.growth)||x.shares.status==='source_reconciled_threshold_bound').length,
 unresolved:result.filter(x=>x.financial.status!=='source_reconciled'||x.shares.status!=='source_reconciled').map(x=>({id:x.id,ticker:x.ticker,event_date:x.event_date,financial_status:x.financial.status,cfo_status:x.financial.cfo.status,shares_status:x.shares.status})),
 financing_status:'all_current_reports_scanned_source_claims_classified',financing_reports:financeManifest.filter(r=>r.status==='ok').length,financing_claim_reviews:reviews.length,full_transaction_reports:contractIndex.size,financing_economic_groups:F.dealsAsOf(reviews,new Date().toISOString()).length,
 feature_coverage:Object.fromEntries(['reported_runway','S1','S2','S4','S7'].map(id=>[id,Object.fromEntries(['pass','fail','unknown'].map(state=>[state,features.filter(s=>s.signals[id].state===state).length]))])),independent_review_attestation:false,production_authority:'none',completion_status:'in_progress'};
 write(path.join(OUT,'progress.json'),summary);const finalized=require('./third_plus_reconciliation_report.cjs').finalize();console.log(JSON.stringify(finalized,null,2));return result;
}
module.exports={build};if(require.main===module)build();
