#!/usr/bin/env node
'use strict';
// Explain frozen results without changing the registered engine or public outcomes.
// Only identities, categorical decisions and modeled sizing dollars are published.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),Module=require('node:module');
const ROOT=path.resolve(__dirname,'../..'),STUDY='_system/data/reverse_splits/third_plus_signal_study',PRIVATE='_system/data/reverse_splits/local/third_plus_signal_study/fundamental_filters_v3';
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),sha=x=>crypto.createHash('sha256').update(x).digest('hex'),round=x=>Math.round(x*100)/100;
function fileSha(file){const h=crypto.createHash('sha256'),fd=fs.openSync(file,'r'),buffer=Buffer.allocUnsafe(1024*1024);try{let n;while((n=fs.readSync(fd,buffer,0,buffer.length,null)))h.update(buffer.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');}
function verifyInputs(sourceRoot,freeze){for(const [f,expected]of Object.entries(freeze.inputs)){if(/sealed|holdout/i.test(f))throw new Error('Sealed input forbidden');if(fileSha(path.join(sourceRoot,f))!==expected)throw new Error('Frozen input changed: '+f);}}
function replaceOnce(text,from,to){if(text.split(from).length!==2)throw new Error('Frozen audit hook changed: '+from);return text.replace(from,to);}
function instrument(source){
 const hooks=[
 ['  const byDay=new Map();',"  const note=(r,status,details={})=>opts.audit?.(r,status,details);\n  const byDay=new Map();"],
 ['{funnel.common_maturity_excluded++;continue;}',"{funnel.common_maturity_excluded++;note(r,'common_maturity_excluded',{reason:r.i===undefined?'missing_original_session':'common_20_session_maturity'});continue;}"],
 ['{funnel.missing_entry++;continue;}',"{funnel.missing_entry++;note(r,'missing_entry');continue;}"],
 ['{funnel.missing_liquidity++;continue;}',"{funnel.missing_liquidity++;note(r,'missing_liquidity');continue;}"],
 ['{funnel.overlap++;continue;}',"{funnel.overlap++;note(r,'overlap');continue;}"],
 ["{funnel.verified_evidence_missing++;continue;}","{funnel.verified_evidence_missing++;note(r,'verified_evidence_missing');continue;}"],
 ["{funnel.ssr_rejected++;continue;}","{funnel.ssr_rejected++;note(r,'ssr_rejected',{reason:ssr?.restricted===1?'restricted':'unknown'});continue;}"],
 ['const target=opts.target||25000;let qty=Math.floor(target/r.entry_price);',"const target=opts.target||25000;let qty=Math.floor(target/r.entry_price);\n      const size={limits:{target:qty},open_events:[]};"],
 ['if(open.length>=(opts.maximumNames||3)){funnel.risk_capacity++;continue;}',"Object.assign(size,{equity,budget,exposure,required,open_names:open.length,open_events:open.map(p=>p.id)});\n        size.limits.per_name=Math.floor(.0025*equity/r.entry_price);size.limits.sleeve=Math.floor(Math.max(0,.01*equity-(opts.otherStressLoss||0)/2-exposure)/r.entry_price);size.limits.margin=Math.floor(Math.max(0,.8*equity-required)/margin(1,r.entry_price));\n        if(open.length>=(opts.maximumNames||3)){funnel.risk_capacity++;note(r,'risk_capacity',{reason:'three_name_limit',size});continue;}"],
 ['if(qty<=0){funnel.risk_capacity++;continue;}',"if(qty<=0){funnel.risk_capacity++;note(r,'risk_capacity',{reason:'no_risk_or_margin_capacity',size});continue;}"],
 ['qty=Math.min(qty,Math.floor(cap*r.adv_shares),Math.floor(cap*point.volume*(ssr?.restricted===0?1:.5)));',"size.limits.adv=Math.floor(cap*r.adv_shares);size.limits.session=Math.floor(cap*point.volume*(ssr?.restricted===0?1:.5));\n        qty=Math.min(qty,Math.floor(cap*r.adv_shares),Math.floor(cap*point.volume*(ssr?.restricted===0?1:.5)));"],
 ['if(qty<1){funnel.zero_capacity++;continue;}',"if(qty<1){funnel.zero_capacity++;note(r,'zero_capacity',{size});continue;}"],
 ['      funnel.entered++;',"      funnel.entered++;note(r,'entered',{size,qty});"]
 ];
 for(const [a,b]of hooks)source=replaceOnce(source,a,b);return source;
}
function compactSize(r,d,index){
 if(!d.size)return null;
 const z=d.size,out={limits:Object.fromEntries(Object.entries(z.limits).map(([k,q])=>[k,round(q*r.entry_price)])),open_events:z.open_events.map(id=>{if(!index.has(id))throw new Error('Unknown open issuer');return index.get(id);})};
 for(const k of ['equity','budget','exposure','required','open_names'])if(z[k]!==undefined)out[k]=round(z[k]);
 if(d.qty!==undefined){out.notional=round(d.qty*r.entry_price);out.target_fraction=d.qty*r.entry_price/25000;out.binding=Object.entries(z.limits).filter(([,q])=>q===d.qty).map(([k])=>k);}
 return out;
}
function build(sourceRoot=ROOT){
 const outDir=path.join(ROOT,STUDY,'fundamental_filters_v3'),manifest=read(path.join(outDir,'manifest.json')),doc=read(path.join(outDir,'summary.json')),register=read(path.join(outDir,'experiment_register.json'));
 verifyInputs(sourceRoot,manifest.freeze);
 const revision=read(path.join(outDir,'implementation_revision.json'));
 for(const [file,expected]of Object.entries(manifest.freeze.code)){const actual=fileSha(path.join(sourceRoot,file));if(actual!==expected&&!revision.code_changes.some(c=>c.file===file&&c.original_sha256===expected&&c.corrected_sha256===actual))throw new Error('Frozen research code changed: '+file);}
 const engineFile=path.join(sourceRoot,'_system/scripts/reverse_split_repeat_study.cjs'),source=fs.readFileSync(engineFile,'utf8'),engineHash=sha(fs.readFileSync(engineFile));
 if(engineHash!==manifest.freeze.code['_system/scripts/reverse_split_repeat_study.cjs'])throw new Error('Engine differs from frozen study');
 const featuresFile=path.join(sourceRoot,PRIVATE,'features.local.json'),featureBytes=fs.readFileSync(featuresFile);
 if(sha(featureBytes)!==manifest.features_sha256)throw new Error('Feature overlay differs from frozen study');
 const features=JSON.parse(featureBytes),F=require(path.join(sourceRoot,'_system/scripts/third_plus_fundamental_filters.cjs'));
 const Fhash=sha(fs.readFileSync(path.join(sourceRoot,'_system/scripts/third_plus_fundamental_filters.cjs'))),rev=read(path.join(outDir,'implementation_revision.json'));
 if(Fhash!==manifest.freeze.code['_system/scripts/third_plus_fundamental_filters.cjs']&&!rev.code_changes.some(c=>c.file==='_system/scripts/third_plus_fundamental_filters.cjs'&&c.corrected_sha256===Fhash))throw new Error('Feature selector changed');
 const mod=new Module(engineFile,module);mod.filename=engineFile;mod.paths=Module._nodeModulePaths(path.dirname(engineFile));mod._compile(instrument(source),engineFile);
 const B=mod.exports,ctx=B.load(),candidates=ctx.candidates.filter(r=>r.ordinal>=3).sort((a,b)=>a.event_date.localeCompare(b.event_date)||a.id.localeCompare(b.id)),index=new Map(candidates.map((c,i)=>[c.id,i])),featureIndex=new Map(features.map(f=>[f.id,f]));
 const events=candidates.map(r=>({id:r.id,ticker:r.ticker,name:r.name,issuer:r.issuer,event_date:r.event_date,entry_day:r.day,ordinal:r.ordinal,source_url:r.source_url,signals:Object.fromEntries(Object.entries(featureIndex.get(r.id).signals).map(([k,s])=>[k,s.state]))})),models={},ledgerHashes={};let replayed=0;
 try{
 for(const model of register.models.filter(m=>['primary','h10','stress','lower_cost','cap_0.001','cap_0.05','full_20','full_10','SSR_proxy'].includes(m.kind))){
  const arm=doc.protocol.arms.find(a=>a.id===model.arm),file=path.join(sourceRoot,PRIVATE,'ledgers',model.ledger+'.local.json'),bytes=fs.readFileSync(file),frozen=JSON.parse(bytes),rows=candidates.filter(r=>F.armState(featureIndex.get(r.id),arm).state==='pass');
  ledgerHashes[model.ledger]=sha(bytes);
  const statuses=candidates.map(r=>{const s=F.armState(featureIndex.get(r.id),arm).state;return s==='pass'?null:'signal_'+s;}),details={};
  const options=Object.fromEntries(['financial','ordinal','fastStats','causalCarry','target','horizon','cost','cap','nav','maximumNames','ssrMode'].filter(k=>frozen.summary[k]!==undefined).map(k=>[k,frozen.summary[k]]));
  const result=B.replay({...ctx,candidates:rows},{...options,audit:(r,status,d)=>{const i=index.get(r.id);if(statuses[i]!==null)throw new Error('Duplicate audit decision');statuses[i]=status;const size=compactSize(r,d,index);if(d.reason||size)details[i]={...(d.reason?{reason:d.reason}:{}),...(size?{size}:{})};}});
  if(JSON.stringify(result.positions)!==JSON.stringify(frozen.positions)||JSON.stringify(result.daily)!==JSON.stringify(frozen.daily))throw new Error('Audit changed frozen outcomes: '+model.id);
  for(const p of frozen.positions)details[index.get(p.id)].position={planned_exit:p.planned_exit,closed:p.closed||null,open:p.units>1e-9,identity_unresolved:!!p.identity_unresolved,ever_overdue:!!p.overdue,fractional:p.units>0&&p.units/p.factor<1};
  if(statuses.some(s=>!s))throw new Error('Incomplete candidate audit');
  for(const [k,v]of Object.entries(frozen.summary.funnel))if(k!=='selected'&&statuses.filter(s=>s===k).length!==v)throw new Error('Funnel mismatch: '+model.id+' / '+k);
  if(statuses.filter(s=>!s.startsWith('signal_')).length!==frozen.summary.funnel.selected)throw new Error('Selected count mismatch');
  models[model.kind]??={};models[model.kind][model.arm]={ledger:model.ledger,statuses,details};replayed++;
  if(replayed%21===0)console.log('Reconciled '+replayed+' audit replays against frozen positions and daily P&L');
 }
 }finally{ctx.prices.close();}
 verifyInputs(sourceRoot,manifest.freeze);
 if(events.length!==210||replayed!==189)throw new Error('Incomplete event audit');
 return {schema:'third_plus_decision_audit.v1',data_version:doc.data_version,events,models,verification:{models:replayed,frozen_inputs_checked:Object.keys(manifest.freeze.inputs).length,frozen_code_files_checked:Object.keys(manifest.freeze.code).length,frozen_manifest_sha256:sha(fs.readFileSync(path.join(outDir,'manifest.json'))),positions_and_daily_paths_exact:true,engine_sha256:engineHash,features_sha256:sha(featureBytes),experiment_register_sha256:sha(fs.readFileSync(path.join(outDir,'experiment_register.json'))),ledger_hashes:ledgerHashes},publication:'Historical issuer identities, categorical decisions and derived modeled sizing dollars only; no raw prices, volumes, quantities, per-event returns or broker data.'};
}
function publish(sourceRoot){const output=build(sourceRoot),dest=path.join(ROOT,STUDY,'fundamental_filters_v3/decision_audit.json');fs.writeFileSync(dest,JSON.stringify(output)+'\n');console.log('Published event audit: '+fs.statSync(dest).size+' bytes');}
module.exports={instrument,compactSize,replaceOnce,build};
if(require.main===module){const at=process.argv.indexOf('--source-root');publish(at>=0?path.resolve(process.argv[at+1]):ROOT);}
