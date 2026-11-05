#!/usr/bin/env node
// The same research engine runs on GitHub-hosted runners or an independent machine.
// Cloudflare Free serves the dashboard; it does not parse financial filings.
import {pathToFileURL} from 'node:url';
import {appendFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import {scheduled,dispatch,consume} from './worker.mjs';
import {openCheckpoint} from './checkpoint.mjs';
import {makeMarketData} from './market-data.mjs';
import {makeDatabentoMarket} from './databento-market.mjs';
import {initializeShadow,shadowTick,putState} from './shadow-service.mjs';
import {watchCollector} from './watch.mjs';
import {recoverWatch} from './recovery.mjs';

export function remoteEnvironment({token,account,database,bucket,fetcher=fetch,cadence=300,maxJobs=40}={}){
  if(!token||!account||!database||!bucket)throw new Error('Collector requires configured Cloudflare credentials and isolated research resources');
  const pending=[],usage={rows_read:0,rows_written:0,queries:0},base=`https://api.cloudflare.com/client/v4/accounts/${account}`,headers={authorization:'Bearer '+token};
  async function request(path,options={}){const r=await fetcher(base+path,{...options,headers:{...headers,...options.headers},signal:AbortSignal.timeout(45000)});if(!r.ok){await r.body?.cancel();throw new Error(`Research storage HTTP ${r.status}`);}return r;}
  async function sql(body){const r=await request(`/d1/database/${database}/query`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}),result=await r.json();if(!result.success||result.result?.some(x=>x.success===false))throw new Error('Research database query failed');for(const row of result.result){usage.rows_read+=Number(row.meta?.rows_read||0);usage.rows_written+=Number(row.meta?.rows_written||0);usage.queries++;}return result.result;}
  const prepare=(query,params=[])=>({bind:(...values)=>prepare(query,values),first:async()=>((await sql({sql:query,params}))[0].results||[])[0]||null,all:async()=>({results:(await sql({sql:query,params}))[0].results||[]}),run:async()=>(await sql({sql:query,params}))[0],_query:query,_params:params});
  const DB={prepare,batch:async statements=>sql({batch:statements.map(s=>({sql:s._query,params:s._params}))})};
  const prefix=`/r2/buckets/${encodeURIComponent(bucket)}/objects/`;
  const EVIDENCE={
    async put(key,bytes,options={}){await request(prefix+key.split('/').map(encodeURIComponent).join('/'),{method:'PUT',headers:{'content-type':options.httpMetadata?.contentType||'application/octet-stream'},body:bytes});},
    async get(key){const r=await fetcher(base+prefix+key.split('/').map(encodeURIComponent).join('/'),{headers,signal:AbortSignal.timeout(45000)});if(r.status===404){await r.body?.cancel();return null;}if(!r.ok){await r.body?.cancel();throw new Error(`Evidence storage HTTP ${r.status}`);}return {json:()=>r.json(),text:()=>r.text(),arrayBuffer:()=>r.arrayBuffer()};},
  };
  return {DB,controlDB:DB,EVIDENCE,JOBS:{send:async body=>pending.push(body)},ENABLED:'true',SEC_USER_AGENT:'MagisCapitalResearch/1.0 (reverse-split monitoring; contact: drewgoldman01@gmail.com)',EXPECTED_CADENCE_SECONDS:String(cadence),MAX_DISPATCH:1,COLLECTOR_MODE:'external_collector',SHADOW_ENABLED:'true',pending,maxJobs,usage};
}

export async function runOnce(env,{maximumMs=210000,reconcile=false}={}){
  const now=Date.now(),token=crypto.randomUUID(),lease=String(now+Math.max(600000,maximumMs+180000))+':'+token,remote=env.controlDB;
  env.deadline=now+maximumMs;
  env.DB=remote;Object.assign(env.usage,{rows_read:0,rows_written:0,queries:0});
  await env.DB.prepare("INSERT OR IGNORE INTO rs_state(key,value,updated_at) VALUES('collector_lease','0',?)").bind(new Date().toISOString()).run();
  const acquired=await env.DB.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND CAST(value AS INTEGER)<=? RETURNING value").bind(lease,new Date().toISOString(),now).first();
  if(!acquired)return {skipped:true,reason:'Another collector owns the bounded lease'};
  const usageKey='collector_usage:'+new Date(now).toISOString().slice(0,10),priorUsage=JSON.parse((await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(usageKey).first())?.value||'{}');
  const withinBudget=()=>Number(priorUsage.rows_read||0)+(env.usage?.rows_read||0)<500000&&Number(priorUsage.rows_written||0)+(env.usage?.rows_written||0)<50000;
  const counts={jobs:0,started_at:new Date(now).toISOString(),mode:'external_collector'};let checkpoint,lastSave=counts.started_at;
  try{
    if(!withinBudget())return {skipped:true,reason:'Research daily database budget reached; preserving headroom for the existing dashboard'};
    checkpoint=await openCheckpoint(env);
    if(env.SHADOW_ENABLED==='true'){await initializeShadow(env);env.market ||= makeMarketData({key:process.env.MASSIVE_API_KEY||process.env.POLYGON_API_KEY});env.onShadowDecision=async event=>{await shadowTick(env,{event});};await shadowTick(env);}
    await scheduled({cron:reconcile?'17 8 * * *':'external'},env);
    await checkpoint.save();
    while(Date.now()-now<maximumMs&&counts.jobs<env.maxJobs&&withinBudget()){
      if(!env.pending.length)await dispatch(env);
      const body=env.pending.shift();if(!body)break;
      await consume({messages:[{body,ack(){}}]},env);counts.jobs++;
      if(counts.jobs%8===0||checkpoint.changedSince(lastSave)){await checkpoint.save();lastSave=new Date().toISOString();}
    }
    counts.finished_at=new Date().toISOString();
    await env.DB.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('last_collector_run',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").bind(JSON.stringify(counts),counts.finished_at).run();
    return counts;
  }finally{
    // A runner ending before its work budget never strands its locally dispatched messages.
    for(const p of env.pending.splice(0))await env.DB.prepare("UPDATE rs_jobs SET state='pending',token=NULL WHERE id=? AND token=? AND state='queued'").bind(p.id,p.token).run();
    try{if(checkpoint)await checkpoint.save();}finally{
      checkpoint?.close();env.DB=remote;
      const total={rows_read:Number(priorUsage.rows_read||0)+(env.usage?.rows_read||0),rows_written:Number(priorUsage.rows_written||0)+(env.usage?.rows_written||0)};
      await remote.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(usageKey,JSON.stringify(total),new Date().toISOString()).run();
      await remote.prepare("UPDATE rs_state SET value='0',updated_at=? WHERE key='collector_lease' AND value=?").bind(new Date().toISOString(),lease).run();
    }
  }
}

async function main(){
  const {values}=parseArgs({options:{watch:{type:'boolean',default:false},interval:{type:'string',default:'15'},'run-minutes':{type:'string',default:'300'},'max-jobs':{type:'string',default:'40'},reconcile:{type:'boolean',default:false}}});
  const cadence=Math.max(15,Number(values.interval)||15),env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:process.env.CLOUDFLARE_ACCOUNT_ID||'e1cac493b315c8fd7398500dd1bfd687',database:process.env.REVERSE_SPLIT_DATABASE_ID||'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:process.env.REVERSE_SPLIT_EVIDENCE_BUCKET||'single-stock-reverse-splits-evidence',cadence:values.watch?cadence:300,maxJobs:Math.min(150,Math.max(1,Number(values['max-jobs'])||40))});
  const reference=makeMarketData({key:process.env.MASSIVE_API_KEY||process.env.POLYGON_API_KEY});
  env.market=process.env.DATABENTO_API_KEY?makeDatabentoMarket({key:process.env.DATABENTO_API_KEY,reference}):reference;
  let stopRequested=false;const stop=()=>{stopRequested=true;};
  if(values.watch){process.once('SIGINT',stop);process.once('SIGTERM',stop);}
  try{
    if(values.watch){const maximumMs=Number(values['run-minutes'])===0?Infinity:Math.min(310,Math.max(1,Number(values['run-minutes'])||300))*60000,result=await recoverWatch(remaining=>watchCollector(env,{interval:cadence,maximumMs:remaining}),{maximumMs,shouldStop:()=>stopRequested});if(process.env.GITHUB_OUTPUT)appendFileSync(process.env.GITHUB_OUTPUT,'continue='+(!result.skipped)+'\n');console.log(JSON.stringify(result));}
    else console.log(JSON.stringify(await runOnce(env,{reconcile:values.reconcile})));
  }catch(e){console.error(JSON.stringify({event:'collector_failed',error:e.message}));process.exitCode=1;}
  finally{process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);env.market.close?.();}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main();
