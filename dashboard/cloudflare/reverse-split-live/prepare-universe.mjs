#!/usr/bin/env node
// Nightly public SEC preparation. Heavy work stays off the quote collector.
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtemp,writeFile,rm,rmdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {ALIASES,etDay} from './core.mjs';
import {buildFinancialProfile} from './financials-core.mjs';
import {remoteEnvironment} from './collector.mjs';
import {PREPARED_SCHEMA,PREPARED_BUCKETS} from './prepared-universe.mjs';
import {hash} from './financials-io.mjs';
const now=()=>new Date().toISOString();
export function prepareCompany(row,source,at){
  const cik=row.issuer.cik,raw=row.raw||{cik,facts:{}},p=buildFinancialProfile({cik,company:row.issuer.company,companyfacts:raw,as_of:at});
  const {evidence,...financials}=p.policy_financials;
  const profile={schema:PREPARED_SCHEMA,cik,company:row.issuer.company,tickers:row.issuer.tickers,exchanges:row.issuer.exchanges,security_type:row.issuer.security_type,prepared_at:at,as_of_day:etDay(at),financials:{...financials,source_url:source.url,source_sha256:source.sha256},coverage:p.coverage,source:{url:source.url,archive_sha256:source.sha256,member_sha256:row.member_sha256||null,storage_basis:'Normalized relevant financial inputs; original complete archive is not retained'},error:row.error||null};
  profile.version=hash(JSON.stringify(profile));return profile;
}
export async function publishPreparedUniverse(env,rows,source,at){
  if(rows.length!==source.universe.length||rows.length<1000)throw new Error('Incomplete broad preparation; previous snapshot preserved');
  const counts={},buckets=new Map(),cards=[];
  for(const p of rows){counts[p.coverage.status]=(counts[p.coverage.status]||0)+1;const bucket=Number(p.cik)%PREPARED_BUCKETS;if(!buckets.has(bucket))buckets.set(bucket,[]);buckets.get(bucket).push(p);cards.push({cik:p.cik,tickers:p.tickers,company:p.company,status:p.coverage.status,score:p.financials.score,period:p.coverage.period,signal_count:p.coverage.signal_count,security_type:p.security_type,error:p.error});}
  const put=async(key,value)=>{await env.assertPreparationLease?.();await env.EVIDENCE.put(key,new TextEncoder().encode(JSON.stringify(value)),{httpMetadata:{contentType:'application/json'}});};
  const shards={};
  for(const [bucket,profiles] of buckets){
    profiles.sort((a,b)=>Number(a.cik)-Number(b.cik));shards[bucket]=[];let group=[];
    async function flush(){if(!group.length)return;const shard={schema:PREPARED_SCHEMA,prepared_at:at,profiles:Object.fromEntries(group.map(p=>[p.cik,p]))},text=JSON.stringify(shard),sha256=hash(text),key='prepared/shards/'+sha256+'.json';if(Buffer.byteLength(text)>512000)throw new Error('A prepared company exceeds the shard limit');await put(key,shard);shards[bucket].push({key,sha256,bytes:Buffer.byteLength(text),minimum_cik:Number(group[0].cik),maximum_cik:Number(group.at(-1).cik)});group=[];}
    for(const p of profiles){if(group.length&&Buffer.byteLength(JSON.stringify([...group,p]))>450000)await flush();group.push(p);}await flush();
  }
  const pages=[];cards.sort((a,b)=>Number(a.cik)-Number(b.cik));for(let i=0;i<cards.length;i+=100){const page={schema:PREPARED_SCHEMA,companies:cards.slice(i,i+100)},key='prepared/pages/'+hash(JSON.stringify(page))+'.json';await put(key,page);pages.push(key);}
  const summary={schema:PREPARED_SCHEMA,generated_at:at,as_of_day:etDay(at),issuers:rows.length,securities:source.universe.reduce((n,r)=>n+r.tickers.length,0),status_counts:counts,source_url:source.url,source_archive_sha256:source.sha256,scope:'SEC-listed exchange candidates; final common-share identity and prior-split verification remain mandatory at entry',complete_for_declared_universe:true,automatic_trade_authority:false,broker_connections:0,orders:0};
  const manifest={schema:PREPARED_SCHEMA,generated_at:at,summary,shards,pages};await put('prepared/manifests/'+hash(JSON.stringify(manifest))+'.json',manifest);await put('prepared/manifest-latest.json',manifest);return summary;
}
export async function runPreparation(env){
  const owner=crypto.randomUUID(),key='universe_preparation_lease',at=now();let lease=String(Date.now()+600000)+':'+owner,error,renewing=Promise.resolve();
  await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind(key,'0',at).run();if(!await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND CAST(value AS INTEGER)<=? RETURNING value').bind(lease,at,key,Date.now()).first())return {skipped:true};
  const timer=setInterval(()=>{renewing=renewing.then(async()=>{const next=String(Date.now()+600000)+':'+owner;if(!await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND value=? RETURNING value').bind(next,now(),key,lease).first())throw new Error('Preparation lease lost');lease=next;}).catch(e=>{error=e;});},120000);
  env.assertPreparationLease=async()=>{await renewing;if(error)throw error;const r=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first();if(r?.value?.split(':').at(-1)!==owner||Number(r.value.split(':')[0])<=Date.now())throw new Error('Preparation owner changed');};
  const directory=await mkdtemp(join(tmpdir(),'reverse-split-preparation-'));let child;
  try{
    const aliases=join(directory,'aliases.json');await writeFile(aliases,JSON.stringify([...new Set(Object.values(ALIASES).flat())]));
    child=spawn(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./prepare_sec_bulk.py',import.meta.url)),'--aliases',aliases],{stdio:['ignore','pipe','pipe'],windowsHide:true,env:{...Object.fromEntries(Object.entries(process.env).filter(([k])=>['PATH','Path','SYSTEMROOT','SystemRoot','WINDIR','HOME','USERPROFILE','TMP','TEMP','LANG'].includes(k))),PYTHONIOENCODING:'utf-8'}});
    const done=new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(new Error('SEC bulk reader failed')));});done.catch(()=>{});child.stderr.on('data',chunk=>process.stderr.write(chunk));
    let source,complete=false;const rows=[];for await(const line of createInterface({input:child.stdout,crlfDelay:Infinity})){if(Buffer.byteLength(line)>64*1024*1024)throw new Error('SEC member output limit');const row=JSON.parse(line);if(row.kind==='source')source=row;else if(row.kind==='company'){if(!source)throw new Error('SEC preparation lacks source provenance');rows.push(prepareCompany(row,source,at));if(rows.length%500===0)console.log(JSON.stringify({event:'universe_preparation_progress',companies:rows.length}));}else if(row.kind==='complete'){complete=row.issuers===rows.length;}}
    await done;if(!complete||!source)throw new Error('SEC bulk stream did not complete');await env.assertPreparationLease();return await publishPreparedUniverse(env,rows,source,at);
  }finally{child?.kill();clearInterval(timer);await renewing;try{await rm(join(directory,'aliases.json'),{force:true});await rmdir(directory);}finally{await env.DB.prepare("UPDATE rs_state SET value='0',updated_at=? WHERE key=? AND value=?").bind(now(),key,lease).run();delete env.assertPreparationLease;}}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence',evidenceInterval:1500});try{console.log(JSON.stringify(await runPreparation(env)));}catch(e){console.error(JSON.stringify({event:'universe_preparation_failed',error:e.message}));process.exitCode=1;}}
