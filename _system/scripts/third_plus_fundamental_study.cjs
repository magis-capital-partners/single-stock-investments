#!/usr/bin/env node
'use strict';
// Registered offline extension; original study and live policies are never written.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const B=require('./reverse_split_repeat_study.cjs'),F=require('./third_plus_fundamental_filters.cjs'),S=require('./third_plus_signal/statistics.cjs'),A=require('./short_framework/adapters.cjs');
const ROOT=path.resolve(__dirname,'../..'),BASE=path.join(ROOT,'_system/data/reverse_splits/third_plus_signal_study'),PRIVATE=path.join(ROOT,'_system/data/reverse_splits/local/third_plus_signal_study'),REC=path.join(PRIVATE,'reconciliation'),WORK=path.join(PRIVATE,'fundamental_filters_v3'),OUT=path.join(BASE,'fundamental_filters_v3');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),digest=x=>crypto.createHash('sha256').update(x).digest('hex'),hash=x=>digest(JSON.stringify(x)),sum=S.sum;
function fileHash(file){const h=crypto.createHash('sha256'),fd=fs.openSync(file,'r'),buf=Buffer.allocUnsafe(1024*1024);try{let n;while((n=fs.readSync(fd,buf,0,buf.length,null))>0)h.update(buf.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');}
function write(f,x){fs.mkdirSync(path.dirname(f),{recursive:true});fs.writeFileSync(f+'.tmp',typeof x==='string'?x:JSON.stringify(x,null,2)+'\n');fs.renameSync(f+'.tmp',f);}
function sources(){return ['third_plus_fundamental_filters.cjs','third_plus_fundamental_filters.test.cjs','third_plus_fundamental_study.cjs','reverse_split_repeat_study.cjs','third_plus_signal/features.cjs','third_plus_signal/statistics.cjs','third_plus_reconciliation_engine.cjs','short_framework/adapters.cjs'].map(n=>path.join(ROOT,'_system/scripts',n)).concat([path.join(ROOT,'dashboard/short-framework-engine.js'),path.join(ROOT,'_system/scripts/build_short_quant_screen.py'),path.join(ROOT,'_system/scripts/reverse_splits/fundamental_data.py')]);}
function datedProfiles(){
 const rows=read(path.join(REC,'terms_source_manifest.local.json')).concat(read(path.join(REC,'filing_manifest.local.json')).filter(r=>r.file?.endsWith('.txt'))),result=new Map();
 for(const r of rows.filter(r=>r.status==='ok')){const text=fs.readFileSync(path.join(ROOT,r.file)).toString('utf8',0,65536),m=text.match(/STANDARD INDUSTRIAL CLASSIFICATION:\s*[^\r\n]*?\[(\d{4})\]/i);if(!m)continue;
 const list=result.get(r.cik)||[];list.push({profile:F.profile(Number(m[1])),sic:Number(m[1]),filed_at:r.filed_at,known_at:A.nyClock(A.dateAfter(r.filed_at),'00:00:00'),source_url:r.url,source_sha256:r.sha256,locator:'SEC-HEADER / STANDARD INDUSTRIAL CLASSIFICATION',quote:m[0]});result.set(r.cik,list);}
 return result;
}
function features(){
 const snapshots=read(path.join(REC,'reconciled_features.local.json')),rawHashes=read(path.join(REC,'companyfacts_hashes.local.json')),parent=read(path.join(BASE,'reconciliation_v2/manifest.json'));
 if(fileHash(path.join(REC,'reconciled_features.local.json'))!==parent.inputs.features_sha256)throw new Error('Reconciled overlay changed');
 const inv=read(path.join(REC,'source_inventory.local.json')).parsedInventories.parsed,parsedHashes=new Map(inv.map(v=>[v.file,v.sha256]));
 const filings=read(path.join(REC,'filing_manifest.local.json')),profiles=datedProfiles(),all=[],sourceHashes={};
 for(const [issuer,ss]of S.grouped(snapshots,s=>s.issuer)){
 const cik=Number(issuer.split('/')[1]),rawFile=path.join(PRIVATE,'../raw/companyfacts','CIK'+String(cik).padStart(10,'0')+'.json'),raw=read(rawFile),rawHash=fileHash(rawFile);
 if(rawHash!==rawHashes[cik]||Number(raw.cik)!==cik)throw new Error('Raw companyfacts identity/hash changed');
 raw.__source_sha256=rawHash;raw.__source_url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json';sourceHashes[rawFile]=rawHash;
 const docs=filings.filter(f=>f.cik===cik&&f.status==='ok').map(f=>{const name=f.accession.replaceAll('-','')+'.json',file=path.join(REC,'parsed',name);if(fileHash(file)!==parsedHashes.get(name))throw new Error('Parsed financial report changed');const d=read(file);if(d.source_sha256!==f.sha256)throw new Error('Parsed source mismatch');return d;});
 for(const s of ss){const at=s.reconciliation.clock.at,rs=F.rows(raw,docs,at),p=(profiles.get(cik)||[]).filter(p=>Date.parse(p.known_at)<=Date.parse(at)).sort((a,b)=>b.filed_at.localeCompare(a.filed_at))[0];all.push(F.buildOne(s,rs,p));}
 }
 all.sort((a,b)=>a.event_date.localeCompare(b.event_date)||a.id.localeCompare(b.id));write(path.join(WORK,'features.local.json'),all);
 const coverage=Object.fromEntries([...new Set(F.ARMS.flatMap(a=>a.requires))].map(k=>[k,Object.fromEntries(['pass','fail','unknown'].map(v=>[v,all.filter(s=>s.signals[k]?.state===v).length]))]));
 return {snapshots:all,coverage,companyfacts_hashes:Object.fromEntries(Object.entries(sourceHashes).map(([f,h])=>[path.relative(ROOT,f).replaceAll('\\','/'),h])),profiles:Object.fromEntries(Object.entries(Object.groupBy(all,s=>s.profile.profile)).map(([p,rs])=>[p,rs.length]))};
}
function trainingPositions(result,embargo){return result.positions.filter(p=>p.units<=1e-9&&p.loan_units<=1e-9&&p.closed&&p.closed<embargo&&p.pending_returns.every(r=>r.day<embargo));}
function selectTraining(primary,embargo){
 const base=primary.find(r=>r.arm==='saved'),ps=trainingPositions(base,embargo),n=new Set(ps.map(p=>p.issuer)).size;
 if(n<30)return {arm:'saved',training_issuers:n,reason:'fewer_than_30_completed_training_issuers',tests:[]};
 const baseMap=new Map([...S.grouped(ps,p=>p.issuer)].map(([id,rs])=>[id,sum(rs.map(p=>p.pnl))]));
 const tests=primary.filter(r=>!['saved','third_plus_only'].includes(r.arm)).map(r=>{
 const rows=trainingPositions(r,embargo),m=new Map([...S.grouped(rows,p=>p.issuer)].map(([id,rs])=>[id,sum(rs.map(p=>p.pnl))])),ids=[...new Set([...baseMap.keys(),...m.keys()])],b=S.bootstrap(ids.map(id=>(m.get(id)||0)-(baseMap.get(id)||0)),{B:2000});
 return {arm:r.arm,issuers:m.size,increment:b.total,p:m.size>=30?b.p_positive:1,interval:b.interval};
 });S.holm(tests);
 const best=tests.filter(r=>r.issuers>=30&&r.increment>0&&r.interval?.[0]>0&&r.holm_p<=.05).sort((a,b)=>b.increment-a.increment||a.arm.localeCompare(b.arm))[0];
 return {arm:best?.arm||'saved',training_issuers:n,reason:best?'prior_completed_labels_pass_training_gate':'no_prior_rule_passed_training_gate',tests};
}
function publicSummary(s){const {issuer_concentration,...rest}=s;return rest;}
function criterion(r,stress){
 const s=r.summary,why=[];if(s.issuers<30)why.push('fewer_than_30_issuers');
 if(r.vs_saved.incremental_net<=0||r.vs_covered.incremental_net<=0)why.push('no_positive_matched_increment');
 if(r.holm_p>.05||!r.vs_saved.issuer_bootstrap_95||r.vs_saved.issuer_bootstrap_95[0]<=0||!r.vs_saved.calendar_block_total_95||r.vs_saved.calendar_block_total_95[0]<=0)why.push('uncertainty_or_multiplicity_gate_failed');
 if(s.max_drawdown_dollars<r.baseline_drawdown)why.push('drawdown_worse_than_saved');
 if(s.pnl_without_best_issuer<=0||s.pnl_without_best5_issuers<=0)why.push('concentration_gate_failed');
 if(s.open_positions>0||s.open_liability>1e-9)why.push('unresolved_short_obligations');
 if(s.risk_breach_sessions>0)why.push('risk_budget_breach');
 if(stress.net_pnl<=0)why.push('nonpositive_stress_profit');
 return {status:why.length?'not_validated':'historical_research_candidate',reasons:why};
}
function markdown(doc){
 const m=x=>Number.isFinite(x)?(x<0?'−$':'$')+Math.abs(x).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
 const table=(headers,rows)=>'| '+headers.join(' | ')+' |\n| '+headers.map(()=> '---').join(' | ')+' |\n'+rows.map(r=>'| '+r.join(' | ')+' |').join('\n')+'\n';
 const primary=doc.primary,rank=primary.filter(r=>r.arm!=='third_plus_only').slice().sort((a,b)=>b.summary.net_pnl-a.summary.net_pnl),labels=new Map(F.ARMS.map(a=>[a.id,a.label]));
 let text='# Recalculated third-plus fundamental-filter study\n\n'+
 'The saved starting rule is third-or-later reverse split plus the prior five-session 50% daily-rally veto. The study tests 19 additions using reconciled data and fixed framework thresholds. These are conditional historical replays; a higher historical number is not an established optimal or live-profitable policy.\n\n'+
 'Primary: 20 sessions, $25,000 target, $1 million reference NAV, unchanged squeeze reserves, three-name maximum, 1% participation and strict SSR skips. Actual positions are usually much smaller than $25,000. Common window '+doc.common_first+' to '+doc.price_asof+'; '+doc.common_months+' calendar months, including idle months. Borrow availability and fills are not verified.\n\n'+
 '## Every primary comparison\n\n'+table(['Addition to saved rule','Candidates','Trades / issuers','Net marked P&L','Change vs saved','Max closing drawdown','Open','Holm p'],primary.map(r=>[labels.get(r.arm),r.coverage.pass,r.summary.entered+' / '+r.summary.issuers,m(r.summary.net_pnl),m(r.vs_saved.incremental_net),m(r.summary.max_drawdown_dollars),r.summary.open_positions,r.holm_p===null?'reference':r.holm_p.toFixed(3)]))+
 '\nThe largest observed primary P&L is '+labels.get(rank[0].arm)+' at '+m(rank[0].summary.net_pnl)+'. This is a descriptive ranking after the registered comparisons. '+doc.finalists.length+' rules meet every declared research-candidate gate.\n\n'+
 '## Filters and coverage\n\n'+table(['Feature','Pass','Fail','Unknown'],Object.entries(doc.coverage).map(([k,v])=>[k,v.pass,v.fail,v.unknown]))+
 '\n'+Object.entries(doc.protocol.feature_rules).map(([k,v])=>'- '+k+': '+v).join('\n')+
 '\n\nReported runway uses reported cash; it is not fully financing-adjusted cash. S1 and S2 remain unavailable for promotion. The strict financing/saleability and six-lens underwriting requirements have not been relaxed. Actual share dilution measures count growth, not immediately saleable supply. Negative equity is not by itself a bankruptcy forecast. Missing data, undefined growth with zero prior revenue, and inapplicable profiles remain unknown.\n\n'+
 'Dated historical profile coverage: '+JSON.stringify(doc.profiles)+'. Unknown historical industry applicability remains a limitation of generic numeric screens. No current SIC was backfilled into past decisions. Accrual and cash-conversion signals share one economic family; cash burn and its runway ratio are also related. Combining them does not create independent confirmation.\n\n'+
 '## Capacity, costs and full-target benchmark\n\n'+table(['Rule','Primary P&L','10-session P&L','Stress P&L','0.1% cap P&L','5% cap P&L','Full $25k strict P&L','Full-target entries / total'],primary.filter(r=>doc.protocol.focus_arms.includes(r.arm)).map(r=>{const get=k=>doc.scenarios.find(s=>s.arm===r.arm&&s.kind===k).summary;return [labels.get(r.arm),m(r.summary.net_pnl),m(get('h10').net_pnl),m(get('stress').net_pnl),m(get('cap_0.001').net_pnl),m(get('cap_0.05').net_pnl),m(get('full_20').net_pnl),get('full_20').full_target_entries+' / '+get('full_20').entered];}))+
 '\nFull-target results remove the account and volume caps while retaining strict SSR. They assume the target can be borrowed, filled and covered. They are not estimates of achievable capacity or funded returns. The separate SSR proxy is an unsupported execution sensitivity. Base APR is 50%; lower-cost and stress APRs are 20% and 150%, with the frozen execution and fee scenarios. Dividends, bespoke locate fees and operational costs need observed records.\n\n'+
 '## Concentration and uncertainty\n\n'+table(['Rule','Without best issuer','Without best five','Issuer increment 95%','Calendar-block increment 95%','Decision'],primary.filter(r=>doc.protocol.focus_arms.includes(r.arm)).map(r=>[labels.get(r.arm),m(r.summary.pnl_without_best_issuer),m(r.summary.pnl_without_best5_issuers),r.vs_saved.issuer_bootstrap_95?.map(m).join(' to ')||'—',r.vs_saved.calendar_block_total_95?.map(m).join(' to ')||'—',r.decision?.reasons.join(', ')||'reference']))+
 '\nConcentration subtraction is retrospective and does not reallocate freed capital. Full issuer-removal replays are separately reported in summary.json for the declared focus arms. Matched covered-universe controls isolate feature selection from feature availability. Confidence intervals are conditional diagnostics; the Holm family covers the 19 current additions, not every prior project experiment.\n\n'+
 '## Chronology and selection\n\n'+table(['Rule','2023 entry-cohort P&L','2024','2025','2026'],primary.filter(r=>doc.protocol.focus_arms.includes(r.arm)).map(r=>[labels.get(r.arm),...['2023','2024','2025','2026'].map(y=>m(r.summary.entry_years.find(v=>v.year===y)?.net_pnl??0))]))+
 '\nEntry-cohort attribution includes each position through its final modeled mark/loan charges; it is not a separate fresh-account calendar return. Fresh-year account replays for focus rules are in summary.json.\n\n'+
 'Quarterly walk-forward uses only fully closed and returned-loan positions before a 20-session embargo. It requires 30 training issuers and corrected positive training evidence, otherwise retains the saved screen. Selected additions: '+doc.walk_forward.decisions.filter(d=>d.arm!=='saved').length+' / '+doc.walk_forward.decisions.length+' quarters. Walk-forward conditional P&L: '+m(doc.walk_forward.summary.net_pnl)+'. Previously explored 2023–2026 history is development data, not an untouched holdout.\n\n'+
 '## Required next tests\n\n'+
 '1. Preserve as-of facts, exact filing clocks, common share units, restricted cash and explicit unknown states.\n'+
 '2. Require positive matched incremental profit with issuer/calendar uncertainty, family correction, acceptable drawdown and issuer-removal stability; fewer than 30 issuers stays descriptive.\n'+
 '3. Pass shorter holding, capacity and cost stresses without relying on unavailable exits, fractional remnants or unreturned loans.\n'+
 '4. Reconcile actual financing cash, security terms and saleable float before testing strict cash-pressure/financing combinations as verified signals.\n'+
 '5. Freeze a prospective rule before new observations. Record all eligible decisions, rejects, locate quantity/APR, partial fills, recalls, covers and actual cash costs. The existing 50-decision/30-issuer checkpoint starts review; it does not prove profitability.\n'+
 '6. Complete the framework earnings-quality, cash/financing, operating impairment, disclosure/control, valuation/payoff and catalyst/path underwriting, including contrary evidence and falsifiers. A numeric screen cannot manufacture these fields.\n\n'+
 '## Reproduction and integrity\n\n'+
 'Implementation correction: the first v3 run accidentally let rally-veto failures into covered controls. The corrected comparisons retain S7 pass and relax only the added filter. Primary strategy ledgers and thresholds were unaffected; the first run is preserved. The source hashes and correction are recorded in implementation_revision.json.\n\n'+
 'Run node _system/scripts/third_plus_fundamental_study.cjs. Protocol, source/code fingerprints, every model definition and aggregate results are archived by version. Full feature evidence and trade/daily ledgers remain in the local study directory. Original frozen study, saved screen, forward policy and SPX executor are untouched.\n\n'+
 'Validation: '+doc.validation.baselines.length+' baseline reproductions, '+doc.validation.unique_replays+' unique replays, zero sealed-holdout files opened, zero new market-data spend, zero Gateway connections. Verified-execution entries remain '+doc.verified_execution.entered+'.\n\n'+
 'Sources: [framework thresholds](../../../../scripts/build_short_quant_screen.py), [backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), [SEC short-sale requirements](https://www.sec.gov/investor/pubs/regsho.htm).\n\nData version: '+doc.data_version+'.\n';
 return text;
}
function html(text){
 const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),lines=text.split('\n'),body=[];let table=false,list=false;
 for(const line of lines){if(line.startsWith('|')){if(!table){body.push('<div class="scroll"><table>');table=true;}if(/^\|[\s|:-]+\|$/.test(line))continue;body.push('<tr>'+line.split('|').slice(1,-1).map(v=>'<td>'+esc(v.trim())+'</td>').join('')+'</tr>');continue;}if(table){body.push('</table></div>');table=false;}if(!line)continue;const h=line.match(/^(#{1,3}) (.*)/);body.push(h?'<h'+h[1].length+'>'+esc(h[2])+'</h'+h[1].length+'>':'<p>'+esc(line)+'</p>');}
 if(table)body.push('</table></div>');return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Third-plus fundamental filter study</title><style>body{font:16px/1.6 system-ui;background:#f5f7fb;color:#172437}main{max-width:1400px;margin:40px auto;padding:0 20px}h1{line-height:1.2}h2{margin-top:36px}table{border-collapse:collapse;background:white;width:100%;font-size:14px}td{padding:9px;border-bottom:1px solid #dde4ec;vertical-align:top}tr:first-child{font-weight:700;background:#e6edf6}.scroll{overflow:auto}p{max-width:1150px;overflow-wrap:anywhere}</style><main>'+body.join('\n')+'</main></html>';
}
function build(){
 const protocol=read(path.join(OUT,'protocol.json'));if(hash(protocol.arms)!==hash(F.ARMS))throw new Error('Code differs from registered arms');
 const parent=read(path.join(BASE,'reconciliation_v2/manifest.json')),prior=read(path.join(BASE,'manifest.json'));
 const inputFiles=[path.join(OUT,'protocol.json'),path.join(BASE,'reconciliation_v2/manifest.json'),path.join(REC,'reconciled_features.local.json'),path.join(REC,'source_inventory.local.json'),...Object.keys(prior.input_hashes).map(f=>path.join(ROOT,f))];
 if(inputFiles.some(f=>/holdout|sealed/i.test(f)))throw new Error('Sealed input forbidden');
 const inputHashes=Object.fromEntries([...new Set(inputFiles)].map(f=>[path.relative(ROOT,f).replaceAll('\\','/'),fileHash(f)])),codeHashes=Object.fromEntries(sources().map(f=>[path.relative(ROOT,f).replaceAll('\\','/'),fileHash(f)]));
 const freeze={schema:'third_plus_fundamental_filters.freeze.v3',registered_at:protocol.registered_at,protocol_sha256:hash(protocol),inputs:inputHashes,code:codeHashes,production_authority:'none'},freezeFile=path.join(OUT,'freeze.json');
 if(fs.existsSync(freezeFile)&&hash(read(freezeFile))!==hash(freeze)){
 const original=read(freezeFile),rev=read(path.join(OUT,'implementation_revision.json'));
 if(hash(original.inputs)!==hash(freeze.inputs)||original.protocol_sha256!==freeze.protocol_sha256)throw new Error('Frozen input/protocol change requires a new study');
 if(Object.entries(codeHashes).some(([file,sha])=>original.code[file]!==sha&&!rev.code_changes.some(c=>c.file===file&&c.original_sha256===original.code[file]&&c.corrected_sha256===sha)))throw new Error('Unaccounted implementation change');
 freeze.implementation_revision_sha256=hash(rev);freeze.original_freeze_sha256=hash(original);
 }else if(!fs.existsSync(freezeFile))write(freezeFile,freeze);
 console.log('Registered protocol and input/code fingerprints locked before replays.');
 const audit=features(),featureIndex=new Map(audit.snapshots.map(s=>[s.id,s])),ctx=B.load(),candidates=ctx.candidates.filter(r=>r.ordinal>=3),first=candidates.filter(r=>r.day).map(r=>r.day).sort()[0];
 if(candidates.length!==210||candidates.some(r=>!featureIndex.has(r.id)))throw new Error('Original 210-event population changed');
 const common={financial:'all',ordinal:'extended',fastStats:true,causalCarry:true,target:25000},opts={...protocol.primary},models=[],cache=new Map(),baselines=[];
 function run(id,options,rs,meta={}){
 const options2={...common,...options},key=hash({options:options2,rows:rs.map(r=>[r.id,r.day,r.i])});let raw=cache.get(key);
 if(!raw){raw=S.normalise(B.replay({...ctx,candidates:rs},options2),first);cache.set(key,raw);write(path.join(WORK,'ledgers',key+'.local.json'),raw);}
 const result={...raw,id,...meta,ledger:key};models.push(result);if(models.length%20===0)console.log(models.length+' model definitions / '+cache.size+' unique replays');return result;
 }
 const selected=(arm,covered=false)=>candidates.filter(r=>F.armState(featureIndex.get(r.id),arm,covered).state==='pass'),primary=[],covered=new Map(),scenarios=[];
 try{
 for(const horizon of [10,20]){const raw=B.replay(ctx,{horizon,cost:'base',cap:null,financial:'all',ordinal:'extended',fastStats:true}),expected=horizon===10?80279.43124008452:685851.8802611388,delta=raw.summary.net_pnl-expected;if(Math.abs(delta)>.01)throw new Error('Original full-size baseline did not reproduce');baselines.push({kind:'original_full',horizon,expected,actual:raw.summary.net_pnl,delta});}
 for(const arm of F.ARMS){primary.push(run('primary_'+arm.id,opts,selected(arm),{kind:'primary',arm:arm.id}));covered.set(arm.id,run('covered_'+arm.id,opts,selected(arm,true),{kind:'covered',arm:arm.id}));}
 const saved=primary.find(r=>r.arm==='saved'),oldSaved=read(path.join(BASE,'summary.json')).primary.find(r=>r.arm==='S7').summary.net_pnl,delta=saved.summary.net_pnl-oldSaved;if(Math.abs(delta)>.01)throw new Error('Saved screen primary did not reproduce');baselines.push({kind:'saved_strict_primary',expected:oldSaved,actual:saved.summary.net_pnl,delta});
 const rows=primary.map(r=>{const arm=F.ARMS.find(a=>a.id===r.arm),vsSaved=S.comparison(r,saved),vsCovered=S.comparison(r,covered.get(r.arm)),counts=Object.fromEntries(['pass','fail','unknown'].map(st=>[st,audit.snapshots.filter(s=>F.armState(s,arm).state===st).length]));return {arm:r.arm,summary:publicSummary(r.summary),vs_saved:vsSaved,vs_covered:vsCovered,p:Math.max(vsSaved.p_conservative,vsCovered.p_conservative),baseline_drawdown:saved.summary.max_drawdown_dollars,coverage:counts};});
 S.holm(rows.filter(r=>!F.ARMS.find(a=>a.id===r.arm).reference));
 for(const arm of F.ARMS){const rs=selected(arm);for(const [kind,options]of [
 ['h10',{...opts,horizon:10}],['stress',{...opts,cost:'stress'}],['lower_cost',{...opts,cost:'lower_cost'}],
 ['cap_0.001',{...opts,cap:.001}],['cap_0.05',{...opts,cap:.05}],
 ['full_20',{horizon:20,cost:'base',cap:null,ssrMode:'strict'}],['full_10',{horizon:10,cost:'base',cap:null,ssrMode:'strict'}],
 ['SSR_proxy',{...opts,ssrMode:'proxy'}]]){const r=run(kind+'_'+arm.id,options,rs,{kind,arm:arm.id});scenarios.push({arm:arm.id,kind,summary:publicSummary(r.summary)});}}
 const removals=[],yearReplays=[];
 for(const arm of F.ARMS.filter(a=>protocol.focus_arms.includes(a.id))){const r=primary.find(r=>r.arm===arm.id),rank=r.summary.issuer_concentration.slice().sort((a,b)=>b.pnl-a.pnl);for(const n of [1,5]){const omitted=rank.slice(0,n).map(x=>x.issuer),z=run('remove_'+n+'_'+arm.id,opts,selected(arm).filter(c=>!omitted.includes(c.issuer)),{kind:'issuer_removal',arm:arm.id});removals.push({arm:arm.id,count:n,omitted_issuer_count:omitted.length,summary:publicSummary(z.summary)});}
 for(const year of ['2023','2024','2025','2026']){const z=run('year_'+year+'_'+arm.id,opts,selected(arm).filter(c=>c.year===year),{kind:'fresh_year_entry_cohort',arm:arm.id});yearReplays.push({arm:arm.id,year,summary:publicSummary(z.summary)});}}
 const quarters=[...new Set(candidates.filter(c=>c.day).map(c=>c.day.slice(0,4)+'Q'+(Math.floor((Number(c.day.slice(5,7))-1)/3)+1)))].sort(),decisions=[],wfRows=[];
 for(const q of quarters){const start=q.slice(0,4)+'-'+String((Number(q.at(-1))-1)*3+1).padStart(2,'0')+'-01',idx=ctx.prices.days.findIndex(d=>d>=start),embargo=ctx.prices.days[Math.max(0,idx-20)],choice=selectTraining(primary,embargo),arm=F.ARMS.find(a=>a.id===choice.arm);decisions.push({quarter:q,selection_at:A.nyClock(start,'00:00:00'),embargo_day:embargo,...choice});wfRows.push(...selected(arm).filter(r=>r.day&&r.day.slice(0,4)+'Q'+(Math.floor((Number(r.day.slice(5,7))-1)/3)+1)===q));}
 const wf=run('walk_forward',opts,wfRows,{kind:'walk_forward'}),verified=run('verified_execution',{...opts,evidence:'verified'},selected(F.ARMS.find(a=>a.id==='saved')),{kind:'verified_execution'});
 for(const r of rows){const arm=F.ARMS.find(a=>a.id===r.arm);r.holm_p=arm.reference?null:r.holm_p;r.decision=arm.reference?{status:'reference',reasons:[]}:criterion(r,scenarios.find(s=>s.arm===r.arm&&s.kind==='stress').summary);}
 const issuerFirst=new Map([...S.grouped(candidates,c=>c.issuer)].map(([id,rs])=>[id,rs.map(r=>r.year).sort()[0]])),issuerChronology=primary.map(r=>({arm:r.arm,cohorts:['first_observed_year','returning_later_year'].map(group=>{const ps=r.positions.filter(p=>(p.year===issuerFirst.get(p.issuer))===(group==='first_observed_year'));return {group,trades:ps.length,issuers:new Set(ps.map(p=>p.issuer)).size,net_pnl:sum(ps.map(p=>p.pnl))};})}));
 for(const [name,h]of Object.entries(inputHashes))if(fileHash(path.join(ROOT,name))!==h)throw new Error('Input changed during study: '+name);
 for(const [name,h]of Object.entries(codeHashes))if(fileHash(path.join(ROOT,name))!==h)throw new Error('Code changed during study');
 const dataVersion=hash({freeze,features:fileHash(path.join(WORK,'features.local.json')),companyfacts:audit.companyfacts_hashes});
 const doc={schema:'third_plus_fundamental_filters.results.v3',built_at:new Date().toISOString(),data_version:dataVersion,protocol,parent_reconciliation:parent.data_version,price_asof:ctx.prices.last,common_first:first,common_months:saved.summary.common_monthly.length,events:candidates.length,coverage:audit.coverage,profiles:audit.profiles,primary:rows,scenarios,issuer_removal_replays:removals,fresh_year_replays:yearReplays,issuer_chronology:issuerChronology,walk_forward:{decisions,summary:publicSummary(wf.summary)},verified_execution:publicSummary(verified.summary),finalists:rows.filter(r=>r.decision.status==='historical_research_candidate').map(r=>r.arm),validation:{baselines,model_definitions:models.length,unique_replays:cache.size,holdout_files_opened:0},production_authority:'none'};
 const manifest={schema:'third_plus_fundamental_filters.manifest.v3',data_version:dataVersion,freeze,companyfacts_hashes:audit.companyfacts_hashes,features_sha256:fileHash(path.join(WORK,'features.local.json')),new_market_data_usd:0,broker_connections:0},report=markdown(doc),register={protocol_sha256:hash(protocol),primary_claims:rows.filter(r=>r.holm_p!==null).map(r=>({arm:r.arm,p:r.p,holm_p:r.holm_p})),models:models.map(r=>({id:r.id,kind:r.kind,arm:r.arm,ledger:r.ledger,options:{horizon:r.summary.horizon,cost:r.summary.cost,cap:r.summary.cap,nav:r.summary.nav??null,ssrMode:r.summary.ssrMode??null},trades:r.summary.entered})),all_experiments_reported:true};
 for(const dest of [OUT,path.join(OUT,'runs',dataVersion)]){write(path.join(dest,'summary.json'),doc);write(path.join(dest,'manifest.json'),manifest);write(path.join(dest,'REPORT.md'),report);write(path.join(dest,'REPORT.html'),html(report));write(path.join(dest,'experiment_register.json'),register);write(path.join(dest,'protocol.json'),protocol);}
 write(path.join(WORK,'freeze.json'),freeze);write(path.join(WORK,'summary.local.json'),doc);write(path.join(OUT,'latest.json'),{data_version:dataVersion,report:'runs/'+dataVersion+'/REPORT.md'});
 console.log(JSON.stringify({data_version:dataVersion,models:models.length,unique_replays:cache.size,finalists:doc.finalists,primary:rows.map(r=>({arm:r.arm,trades:r.summary.entered,issuers:r.summary.issuers,net:r.summary.net_pnl,open:r.summary.open_positions,holm_p:r.holm_p}))},null,2));return doc;
 }finally{ctx.prices.close();}
}
module.exports={trainingPositions,selectTraining,criterion,markdown,html,build};
if(require.main===module)build();
