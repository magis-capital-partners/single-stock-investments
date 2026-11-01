#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),zlib=require('node:zlib');
const {DatabaseSync}=require('node:sqlite');
const ROOT=path.resolve(__dirname,'../..'),DATA=path.join(ROOT,'_system/data/reverse_splits/local'),WORK=path.join(DATA,'third_plus_signal_study/reconciliation');
const DB=path.join(DATA,'expansion/expansion_v2/runs/20261013T224003582762Z/input.sqlite');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8')),write=(p,x)=>{fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,JSON.stringify(x,null,2)+'\n');};
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const UA='Magis Capital Research drew@magiscapitalpartners.com';
const population=read(path.join(WORK,'population.local.json'));
const db=new DatabaseSync(DB,{readOnly:true});
const sources=db.prepare('SELECT url,file,status FROM collection_sources').all(),sourceIndex=new Map(sources.map(x=>[x.url,x]));
async function get(url,file){
 if(fs.existsSync(file))return fs.readFileSync(file);
 const old=sourceIndex.get(url);if(old&&fs.existsSync(path.join(ROOT,old.file)))return zlib.gunzipSync(fs.readFileSync(path.join(ROOT,old.file)));
 let last;
 for(let i=0;i<3;i++){try{const response=await fetch(url,{headers:{'User-Agent':UA},signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw new Error('HTTP '+response.status+' '+url);const bytes=Buffer.from(await response.arrayBuffer());fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,bytes);return bytes;
 }catch(e){last=e;if(i<2)await sleep(1500*2**i);}}
 throw last;
}
function rows(data){const r=data.filings?.recent||data;return (r.accessionNumber||[]).map((a,i)=>({accession:a,cik:Number(data.cik),form:r.form[i],filed_at:r.filingDate[i],accepted_at:r.acceptanceDateTime?.[i],report_date:r.reportDate?.[i],primary:r.primaryDocument?.[i]}));}
async function metadata(){
 const ciks=[...new Set(population.map(x=>Number(x.issuer.split('/')[1])))],failures=[],index=[];
 for(let i=0;i<ciks.length;i++){
 const cik=ciks[i],file=path.join(WORK,'submissions',cik+'.json');try{
 const sub=JSON.parse(await get('https://data.sec.gov/submissions/CIK'+String(cik).padStart(10,'0')+'.json',file));fs.mkdirSync(path.dirname(file),{recursive:true});if(!fs.existsSync(file))write(file,sub);
 index.push(...rows(sub).map(r=>({...r,cik})));
 const first=population.filter(x=>x.issuer==='cik/'+cik).map(x=>x.event_date).sort()[0];
 for(const old of sub.filings?.files||[]){if(old.filingTo<first.slice(0,4)-3+'-01-01'||old.filingFrom>population.filter(x=>x.issuer==='cik/'+cik).map(x=>x.event_date).sort().at(-1))continue;
 const f=path.join(WORK,'submissions',old.name),body=JSON.parse(await get('https://data.sec.gov/submissions/'+old.name,f));index.push(...rows(body).map(r=>({...r,cik})));await sleep(350);}
 }catch(e){failures.push({cik,error:e.message});}
 if((i+1)%20===0)console.log('Submission indexes '+(i+1)+'/'+ciks.length);await sleep(350);
 }
 const dedup=[...new Map(index.map(r=>[r.accession,r])).values()];write(path.join(WORK,'filing_index.local.json'),dedup);write(path.join(WORK,'metadata_failures.local.json'),failures);
 console.log(JSON.stringify({stage:'metadata',issuers:ciks.length,filings:dedup.length,failures}));return dedup;
}
async function filings(){
 const index=read(path.join(WORK,'filing_index.local.json')),lookup=new Map(index.map(r=>[r.accession,r]));
 const wanted=new Map();
 for(const e of population){
 const cik=Number(e.issuer.split('/')[1]),raw=read(path.join(DATA,'raw/companyfacts/CIK'+String(cik).padStart(10,'0')+'.json'));
 const cutoff=e.decision_at?.slice(0,10)||e.event_date;
 const tags=[['us-gaap','Cash'],['us-gaap','CashAndCashEquivalentsAtCarryingValue'],['us-gaap','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],['us-gaap','CommonStockSharesOutstanding'],['dei','EntityCommonStockSharesOutstanding'],['us-gaap','NetCashProvidedByUsedInOperatingActivities'],['us-gaap','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],['us-gaap','CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations']];
 for(const [ns,tag]of tags){const points=Object.values(raw.facts?.[ns]?.[tag]?.units||{}).flat().filter(r=>r.filed<cutoff&&r.end<cutoff).sort((a,b)=>b.end.localeCompare(a.end)||b.filed.localeCompare(a.filed));
 const recent=points.filter(r=>(Date.parse(cutoff)-Date.parse(r.end))/86400000<=600);
 const selected=recent.slice(0,1); const last=recent[0]; if(last){const older=recent.find(r=>{const age=(Date.parse(last.end)-Date.parse(r.end))/86400000;return age>=150&&age<=240;});if(older)selected.push(older);} for(const r of selected)if(r.accn)wanted.set(r.accn,{cik,accession:r.accn,...lookup.get(r.accn)});
 }
 // Include the last two annual/interim reports and nearby earnings disclosures.
 const reports=index.filter(r=>r.cik===cik&&r.filed_at<cutoff&&/^(10-[QK]|20-F|40-F)/.test(r.form)).sort((a,b)=>b.filed_at.localeCompare(a.filed_at));
 for(const r of reports.slice(0,3))wanted.set(r.accession,r); const lastReport=reports[0]; if(lastReport?.report_date){const older=reports.find(r=>{const age=(Date.parse(lastReport.report_date)-Date.parse(r.report_date))/86400000;return age>=150&&age<=240;});if(older)wanted.set(older.accession,older);}
 }
 if(fs.existsSync(path.join(WORK,'additional_filings.local.json')))for(const r of read(path.join(WORK,'additional_filings.local.json')))wanted.set(r.accession,r);
 write(path.join(WORK,'requested_filings.local.json'),[...wanted.values()]);
 const prior=fs.existsSync(path.join(WORK,'filing_manifest.local.json'))?read(path.join(WORK,'filing_manifest.local.json')):[],done=new Map(prior.filter(x=>x.status==='ok').map(x=>[x.accession,x])),failures=[];
 const jobs=[...wanted.values()];let cursor=0,finished=0;
 async function worker(){while(cursor<jobs.length){const r=jobs[cursor++];try{if(!done.has(r.accession)||r.force_full_submission&&done.get(r.accession)?.source_kind!=='complete_submission'){
 const no=r.accession.replaceAll('-',''),url='https://www.sec.gov/Archives/edgar/data/'+r.cik+'/'+no+'/'+(!r.force_full_submission&&r.primary?r.primary:r.accession+'.txt'),file=path.join(WORK,'sources',no+(!r.force_full_submission&&r.primary?'.html':'.txt'));
 const bytes=await get(url,file);if(!fs.existsSync(file))fs.writeFileSync(file,bytes);done.set(r.accession,{...r,url,file:path.relative(ROOT,file).replaceAll('\\','/'),sha256:hash(bytes),bytes:bytes.length,status:'ok',source_kind:r.force_full_submission?'complete_submission':'primary_document'});
 }}catch(e){failures.push({...r,status:'failed',error:e.message});}
 finished++;if(finished%10===0){write(path.join(WORK,'filing_manifest.local.json'),[...done.values(),...failures]);console.log('Original financial filings '+finished+'/'+jobs.length+'; recovered '+done.size+'; failed '+failures.length);}if(!done.has(r.accession)||r.force_full_submission)await sleep(600);}}
 await Promise.all([worker(),worker()]);write(path.join(WORK,'filing_manifest.local.json'),[...done.values(),...failures]);console.log(JSON.stringify({stage:'filings',requested:jobs.length,recovered:done.size,failed:failures.length}));
}
async function financing(){
 const jobs=read(path.join(WORK,'financing_filings_requested.local.json'));
 const manifestFile=path.join(WORK,'financing_source_manifest.local.json'),prior=fs.existsSync(manifestFile)?read(manifestFile):[],done=new Map(prior.filter(r=>r.status==='ok').map(r=>[r.accession,r])),errors=[];
 let cursor=0,finished=0;
 async function worker(){while(cursor<jobs.length){const r=jobs[cursor++];try{if(!done.has(r.accession)){
 if(r.source_cached){const bytes=zlib.gunzipSync(fs.readFileSync(path.join(ROOT,r.cache_file)));done.set(r.accession,{...r,status:'ok',sources:[{url:r.url,file:r.cache_file,compression:'gzip',sha256:hash(bytes),kind:'cached_complete_submission'}]});}
 else {const no=r.accession.replaceAll('-',''),base='https://www.sec.gov/Archives/edgar/data/'+r.cik+'/'+no+'/',url=base+r.primary,file=path.join(WORK,'finance_sources',no+'.html');
 const bytes=await get(url,file),source=[{url,file:path.relative(ROOT,file).replaceAll('\\','/'),compression:null,sha256:hash(bytes),kind:'primary_document'}];
 const links=new Set();for(const row of bytes.toString('utf8').matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)){if(!/99\.[\d]+|press release/i.test(row[0]))continue;for(const hit of row[0].matchAll(/href=["']([^"'#]+)["']/gi)){let link;try{link=new URL(hit[1].replaceAll('&amp;','&'),base);}catch{continue;}if(link.origin==='https://www.sec.gov'&&link.pathname.startsWith(new URL(base).pathname)&&/\.html?$/i.test(link.pathname))links.add(link.href);}}
 for(const link of links){if(link===url)continue;const exfile=path.join(WORK,'finance_sources',no+'_'+path.basename(new URL(link).pathname)),ex=await get(link,exfile);source.push({url:link,file:path.relative(ROOT,exfile).replaceAll('\\','/'),compression:null,sha256:hash(ex),kind:'referenced_press_release_or_99_exhibit'});await sleep(500);}
 done.set(r.accession,{...r,status:'ok',sources:source});}
 }}catch(e){errors.push({...r,status:'failed',error:e.message});}
 finished++;if(finished%20===0){write(manifestFile,[...done.values(),...errors]);console.log('Financing reports '+finished+'/'+jobs.length+'; recovered '+done.size+'; failed '+errors.length);}await sleep(500);}}
 await Promise.all([worker(),worker()]);write(manifestFile,[...done.values(),...errors]);console.log(JSON.stringify({stage:'financing',requested:jobs.length,recovered:done.size,failed:errors.length}));
}

async function terms(){
 const jobs=read(path.join(WORK,'terms_filings_requested.local.json'));if(jobs.length>200)throw new Error('Terms request budget exceeds 200 filings');
 const file=path.join(WORK,'terms_source_manifest.local.json'),prior=fs.existsSync(file)?read(file):[],done=new Map(prior.filter(r=>r.status==='ok').map(r=>[r.accession,r])),failed=[];let cursor=0,finished=0;
 async function worker(){while(cursor<jobs.length){const r=jobs[cursor++];if(done.has(r.accession)){finished++;continue;}
 try{const no=r.accession.replaceAll('-',''),url='https://www.sec.gov/Archives/edgar/data/'+r.cik+'/'+no+'/'+r.accession+'.txt',target=path.join(WORK,'terms_sources',no+'.txt');const data=await get(url,target);if(!fs.existsSync(target)){fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,data);}done.set(r.accession,{...r,url,file:path.relative(ROOT,target).replaceAll('\\','/'),sha256:hash(data),bytes:data.length,status:'ok'});}catch(e){failed.push({...r,status:'failed',error:e.message});}
 finished++;write(file,[...done.values(),...failed]);if(finished%10===0)console.log('Full transaction filings '+finished+'/'+jobs.length+'; recovered '+done.size+'; failed '+failed.length);await sleep(700);}}
 await Promise.all([worker(),worker()]);write(file,[...done.values(),...failed]);console.log(JSON.stringify({stage:'terms',requested:jobs.length,recovered:done.size,failed:failed.length}));
}

async function main(){fs.mkdirSync(path.join(WORK,'sources'),{recursive:true});if(process.argv[2]==='metadata')await metadata();else if(process.argv[2]==='filings')await filings();else if(process.argv[2]==='financing')await financing();else if(process.argv[2]==='terms')await terms();else throw new Error('Use metadata, filings, financing or terms');db.close();}
if(require.main===module)main().catch(e=>{console.error(e.stack);process.exitCode=1;});
