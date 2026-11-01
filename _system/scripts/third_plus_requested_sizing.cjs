#!/usr/bin/env node
'use strict';
// Requested sizing sensitivity; no broker access, downloads or live authority.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const B=require('./reverse_split_repeat_study.cjs'),E=require('./third_plus_sizing_engine.cjs'),S=require('./third_plus_signal/statistics.cjs'),Audit=require('./build_third_plus_decision_audit.cjs');
const ROOT=path.resolve(__dirname,'../..'),STUDY='_system/data/reverse_splits/third_plus_signal_study',OUT=path.join(ROOT,STUDY,'requested_sizing_v1');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),sha=x=>crypto.createHash('sha256').update(x).digest('hex'),write=(f,x)=>fs.writeFileSync(f,JSON.stringify(x,null,2)+'\n');
function fileSha(f){const h=crypto.createHash('sha256'),fd=fs.openSync(f,'r'),b=Buffer.allocUnsafe(1024*1024);try{let n;while((n=fs.readSync(fd,b,0,b.length,null)))h.update(b.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');}
const CASES=[
{id:'requested_100k',label:'Requested · $100k cap / $10m account',requested:true,note:'$100,000 position cap; $10m reference NAV; 10% prior ADV and final-day volume; three-name limit; no margin/sleeve cap or maturity exclusion. Opening fills remain hypothetical.'},
{id:'requested_prior_only',label:'Requested · prior-volume entry sizing',requested:true,note:'Same $100k cap / $10m reference and three names; entry quantity uses only 10% prior ADV. Exit cap remains 10% daily volume. Opening fills and borrowing are unverified.'},
{id:'requested_SSR_proxy',label:'Requested · SSR capture sensitivity',requested:true,hypothetical:true,note:'Requested sizing with unsupported restricted/unknown SSR capture at 50% of the entry-volume allowance. This does not prove compliant fills or borrow availability.'}
];
function protocol(){return {schema:'third_plus_requested_sizing.protocol.v1',requested_parameters:{nav:10000000,target:100000,cap:.1,maximumNames:3,riskLimits:false,minimumMaturitySessions:0,horizon:20,cost:'base',ssrMode:'strict',causalCarry:true},unchanged:['Original 210-event population and as-of signals','Three simultaneous open positions','20-session planned time exit, with unresolved obligations retained','Frozen base fees, 50% borrow APR and execution debit'],changes:['Dollar cap replaces 0.25%-of-equity name reserve','Remove margin-capacity and sleeve-reserve admission limits','10x original 1% volume caps to 10%','Remove common maturity exclusion; unfinished recent positions stay open and marked'],cases:CASES,limitations:['No observed locates, fills or sliced execution','Final-day entry-volume case uses hindsight information','Reference NAV is an accounting denominator, not a verified funding or margin simulation','All historical data were explored; no new significance or optimal-filter claim'],production_authority:'none'};}
function build(sourceRoot=ROOT){
 fs.mkdirSync(OUT,{recursive:true});const p=protocol(),pf=path.join(OUT,'protocol.json');if(fs.existsSync(pf)&&JSON.stringify(read(pf))!==JSON.stringify(p))throw new Error('Registered scenario parameters changed');if(!fs.existsSync(pf))write(pf,p);
 const parent=read(path.join(ROOT,STUDY,'fundamental_filters_v3/manifest.json')),base=read(path.join(ROOT,STUDY,'fundamental_filters_v3/summary.json')),reg=read(path.join(ROOT,STUDY,'fundamental_filters_v3/experiment_register.json')),oldAudit=read(path.join(ROOT,STUDY,'fundamental_filters_v3/decision_audit.json'));
 for(const [f,h]of Object.entries(parent.freeze.inputs)){if(/sealed|holdout/i.test(f))throw new Error('Sealed input forbidden');if(fileSha(path.join(sourceRoot,f))!==h)throw new Error('Frozen input changed: '+f);}
 const F=require(path.join(sourceRoot,'_system/scripts/third_plus_fundamental_filters.cjs')),loader=require(path.join(sourceRoot,'_system/scripts/reverse_split_repeat_study.cjs')),featuresFile=path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/fundamental_filters_v3/features.local.json');
 if(fileSha(featuresFile)!==parent.features_sha256)throw new Error('Frozen features changed');
 const snapshots=read(featuresFile),features=new Map(snapshots.map(s=>[s.id,s])),ctx=loader.load(),events=oldAudit.events,index=new Map(events.map((e,i)=>[e.id,i])),candidates=ctx.candidates.filter(c=>c.ordinal>=3),models={},validation={baseline_models_matched:0,new_models:0,broker_verified_entries:0,holdout_files_opened:0};
 if(candidates.length!==210||candidates.some(c=>!index.has(c.id)))throw new Error('Changed cohort');
 const local=path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/requested_sizing_v1');fs.mkdirSync(path.join(local,'ledgers'),{recursive:true});
 const first=base.common_first;
 try{
 for(const arm of base.protocol.arms){
 const selected=candidates.filter(c=>F.armState(features.get(c.id),arm).state==='pass');
 const frozenModel=reg.models.find(m=>m.kind==='primary'&&m.arm===arm.id),frozen=read(path.join(sourceRoot,'_system/data/reverse_splits/local/third_plus_signal_study/fundamental_filters_v3/ledgers',frozenModel.ledger+'.local.json'));
 const legacy=E.replay({...ctx,candidates:selected},{financial:'all',ordinal:'extended',fastStats:true,...base.protocol.primary});
 if(JSON.stringify(legacy.positions)!==JSON.stringify(frozen.positions)||JSON.stringify(legacy.daily)!==JSON.stringify(frozen.daily))throw new Error('Scenario fork failed frozen primary replication: '+arm.id);validation.baseline_models_matched++;
 for(const scenario of CASES){
  const options={financial:'all',ordinal:'extended',fastStats:true,...p.requested_parameters,...(scenario.id==='requested_prior_only'?{entryVolumeMode:'prior_only'}:{}),...(scenario.id==='requested_SSR_proxy'?{ssrMode:'proxy'}:{})};
  const statuses=events.map(e=>{const s=F.armState(features.get(e.id),arm).state;return s==='pass'?null:'signal_'+s;}),details={};
  const result=S.normalise(E.replay({...ctx,candidates:selected},{...options,audit:(r,status,d)=>{const i=index.get(r.id);if(statuses[i]!==null)throw new Error('Duplicate decision');statuses[i]=status;const size=Audit.compactSize(r,d,index);if(size&&d.qty!==undefined)size.target_fraction=d.qty*r.entry_price/options.target;if(size&&options.riskLimits===false)delete size.required;if(d.reason||size)details[i]={...(d.reason?{reason:d.reason}:{}),...(size?{size}:{})};}}),first);
  for(const pos of result.positions)details[index.get(pos.id)].position={planned_exit:pos.planned_exit||null,closed:pos.closed||null,open:pos.units>1e-9,identity_unresolved:!!pos.identity_unresolved,ever_overdue:!!pos.overdue,fractional:pos.units>0&&pos.units/pos.factor<1,immature:pos.deadline>=ctx.prices.days.length};
  const s=result.summary;delete s.audit;for(const [k,n]of Object.entries(s.funnel))if(k!=='selected'&&statuses.filter(x=>x===k).length!==n)throw new Error('Unreconciled decisions');if(statuses.some(x=>!x))throw new Error('Unclassified event');
  const key=sha(JSON.stringify({version:'requested_sizing_v1',options,selected:selected.map(r=>r.id)}));write(path.join(local,'ledgers',key+'.local.json'),result);
  const publicSummary={...s};delete publicSummary.issuer_concentration;publicSummary.peak_margin=null;publicSummary.risk_breach_sessions=null;publicSummary.nav_for_200pct_squeeze_at_2pct_loss_budget=null;
  models[scenario.id]??={};models[scenario.id][arm.id]={summary:publicSummary,audit:{ledger:key,statuses,details}};validation.new_models++;
 }
 console.log('Replayed requested sizing: '+arm.id);
 }
 }finally{ctx.prices.close();}
 const sources={parent_manifest:fileSha(path.join(ROOT,STUDY,'fundamental_filters_v3/manifest.json')),protocol:fileSha(pf),engine:fileSha(path.join(ROOT,'_system/scripts/third_plus_sizing_engine.cjs')),builder:fileSha(__filename),features:parent.features_sha256},version=sha(JSON.stringify(sources));
 const doc={schema:'third_plus_requested_sizing.results.v1',data_version:version,parent_study:base.data_version,market_through:base.price_asof,first,months:base.common_months,protocol:p,cases:CASES,models,validation,sources,production_authority:'none'};
 fs.writeFileSync(path.join(OUT,'summary.json'),JSON.stringify(doc)+'\n');write(path.join(OUT,'manifest.json'),{schema:'third_plus_requested_sizing.manifest.v1',data_version:version,sources,summary_sha256:fileSha(path.join(OUT,'summary.json')),new_market_data_usd:0,broker_connections:0});
 console.log(JSON.stringify({version,validation,default:models.requested_100k.dilution.summary},null,2));return doc;
}
module.exports={build,protocol,CASES};
if(require.main===module){const i=process.argv.indexOf('--source-root');build(i>=0?path.resolve(process.argv[i+1]):ROOT);}
