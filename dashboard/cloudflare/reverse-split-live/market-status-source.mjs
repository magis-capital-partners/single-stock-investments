// Public HTTPS only. No Databento connection, account login, broker or order API.
import {pathToFileURL} from 'node:url';
import {appendFileSync} from 'node:fs';
import {remoteEnvironment} from './collector.mjs';
import {boundedBody,sha} from './worker.mjs';
import {etDay,easternTime} from './core.mjs';
import {sessionAt} from './shadow-core.mjs';
import {parseHaltFeed,parseCarryRestrictions,HALT_URL} from './market-status-core.mjs';
import {recoverWatch} from './recovery.mjs';
const ROOT='https://www.nasdaqtrader.com',LISTS=['nasdaqlisted','otherlisted'];
const provenance=env=>({pipeline_version:'public_status_recovery.2026-11-09.v2',pipeline_commit:/^[a-f0-9]{40}$/.test(env.PUBLIC_STATUS_COMMIT||'')?env.PUBLIC_STATUS_COMMIT:null});
export function parseListedFile(text,name,now){
 if(!LISTS.includes(name)||text.length>5*1024*1024)throw new Error('Invalid listing directory');
 const lines=text.trim().split(/\r?\n/),head=lines[0].split('|'),footer=/^File Creation Time: (\d{2})(\d{2})(\d{4})(\d{2}):(\d{2})\|/.exec(lines.at(-1));
 if(!footer||head[0]!== (name==='nasdaqlisted'?'Symbol':'ACT Symbol')||!head.includes('Test Issue'))throw new Error('Listing directory header or footer invalid');
 const as_of=easternTime(footer[3]+'-'+footer[1]+'-'+footer[2],footer[4]+':'+footer[5]+':00'),age=Date.parse(now)-Date.parse(as_of);if(age< -2000||age>36*3600000)throw new Error('Listing directory stale or future');
 const symbols=new Set(),test=head.indexOf('Test Issue');for(const line of lines.slice(1,-1)){const cells=line.split('|');if(cells.length!==head.length)throw new Error('Truncated listing directory');if(cells[test]==='Y')continue;for(const index of name==='nasdaqlisted'?[0]:[0,3,7])if(/^[A-Z][A-Z0-9.-]{0,15}$/.test(cells[index]||''))symbols.add(cells[index]);}
 if(symbols.size<1000)throw new Error('Incomplete listing universe');return {as_of,symbols:[...symbols].sort()};
}
export async function publishMarketSnapshot(env,{fetcher=fetch,clock=()=>new Date().toISOString()}={}){
 const now=clock(),get=async url=>{const u=new URL(url);if(u.origin!==ROOT)throw new Error('Unapproved market-status host');const response=await fetcher(url,{redirect:'error',headers:{'user-agent':env.SEC_USER_AGENT,accept:'text/plain, application/rss+xml, text/xml'},signal:AbortSignal.timeout(12000)});if(!response.ok){await response.body?.cancel();throw new Error('Exchange source HTTP '+response.status);}const bytes=await boundedBody(response,5*1024*1024);return {url,bytes,text:new TextDecoder().decode(bytes),sha256:await sha(bytes),observed_at:clock()};};
 const archive=async doc=>{const key='market-status/documents/'+doc.sha256;await env.EVIDENCE.put(key,doc.bytes,{httpMetadata:{contentType:'text/plain'}});return key;};
 const day=etDay(now),oldObject=await env.EVIDENCE.get('market-status/latest.json'),old=oldObject?await oldObject.json():null;let listing=old?.listing;
 if(listing?.day!==day){const symbols=new Set(),proofs=[];for(const name of LISTS){const doc=await get(ROOT+'/dynamic/SymDir/'+name+'.txt'),parsed=parseListedFile(doc.text,name,now);parsed.symbols.forEach(s=>symbols.add(s));proofs.push({url:doc.url,sha256:doc.sha256,key:await archive(doc),as_of:parsed.as_of});}const text=JSON.stringify({day,symbols:[...symbols].sort(),sources:proofs}),digest=await sha(text),key='market-status/listings/'+digest+'.json';await env.EVIDENCE.put(key,new TextEncoder().encode(text),{httpMetadata:{contentType:'application/json'}});listing={day,key,sha256:digest,count:symbols.size};}
 const doc=await get(HALT_URL),halts={...parseHaltFeed(doc.text,doc.observed_at),observed_at:doc.observed_at,source_sha256:doc.sha256,source_url:doc.url,object_key:await archive(doc)};let carry=old?.carry;
 if(carry?.day!==day||!carry.complete){try{const source=await get(ROOT+'/dynamic/symdir/shorthalts/shorthalts'+day.replaceAll('-','')+'.txt');carry={...parseCarryRestrictions(source.text,day,source.observed_at),observed_at:source.observed_at,source_sha256:source.sha256,object_key:await archive(source)};}catch(error){carry={day,status:'unavailable',error:error.message,intraday_clearance:false,complete:false};}}
 const snapshot={schema:'reverse_split_public_market_status.v1',...provenance(env),generated_at:clock(),status:'partial_free_exchange_evidence',listing,halts,carry,coverage:{halts:'official_public_minute_snapshot',intraday_ssr_clearance:false,IBKR_allocation:false,maximum_halt_evidence_seconds:65},research_only:true,authority:'none',broker_connections:0,orders:0},raw=JSON.stringify(snapshot),digest=await sha(raw),key='market-status/snapshots/'+digest+'.json';
 await env.assertStatusLease?.();await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});await env.EVIDENCE.put('market-status/latest.json',new TextEncoder().encode(JSON.stringify({...snapshot,immutable_key:key,sha256:digest})),{httpMetadata:{contentType:'application/json'}});return snapshot;
}
export async function watchMarketStatus(env,{maximumMs=270*60000,acquireWaitMs=0,clock=Date.now,fetcher=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),shouldStop=()=>false}={}){
 const started=clock(),owner=crypto.randomUUID(),key='exchange_status_lease',stamp=()=>new Date(clock()).toISOString();let lease=String(clock()+180000)+':'+owner,ticks=0;
 await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind(key,'0',stamp()).run();const acquireDeadline=Math.min(started+maximumMs,clock()+acquireWaitMs);
 for(;;){if(shouldStop()||clock()>=started+maximumMs)return {skipped:true};lease=String(clock()+180000)+':'+owner;if(await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND CAST(value AS INTEGER)<=? RETURNING key').bind(lease,stamp(),key,clock()).first())break;if(clock()>=acquireDeadline)return {skipped:true};await sleep(Math.min(5000,acquireDeadline-clock()));}
 env.assertStatusLease=async()=>{const row=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first();if(row?.value!==lease||Number(lease.split(':')[0])<=clock())throw new Error('Market-status lease lost');};
 try{while(clock()-started<maximumMs&&!shouldStop()){
  const cycle=clock(),next=String(clock()+180000)+':'+owner;if(!await env.DB.prepare('UPDATE rs_state SET value=?,updated_at=? WHERE key=? AND value=? RETURNING key').bind(next,stamp(),key,lease).first())throw new Error('Market-status lease lost');lease=next;
  const prior=Number((await env.DB.prepare("SELECT value FROM rs_state WHERE key='exchange_status_poll_at'").first())?.value||0);let health={...provenance(env),generated_at:stamp(),status:sessionAt(stamp())?'waiting_for_minute_boundary':'market_closed',broker_connections:0,orders:0};
  if(sessionAt(stamp())&&clock()-prior<60000){const remaining=started+maximumMs-clock();if(remaining>0)await sleep(Math.min(remaining,Math.max(1000,prior+60000-clock())));continue;}
  if(sessionAt(stamp())&&clock()-prior>=60000){await env.DB.prepare("INSERT INTO rs_state VALUES('exchange_status_poll_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").bind(String(clock()),stamp()).run();try{const result=await publishMarketSnapshot(env,{fetcher,clock:()=>new Date(clock()).toISOString()});health={...health,status:result.status,feed_as_of:result.halts.as_of,listing_count:result.listing.count,intraday_ssr_clearance:false};}catch(error){health={...health,status:'degraded',error:error.message};}}
  await env.assertStatusLease();await env.EVIDENCE.put('market-status/health.json',new TextEncoder().encode(JSON.stringify(health)),{httpMetadata:{contentType:'application/json'}});ticks++;const remaining=started+maximumMs-clock();if(remaining>0)await sleep(Math.min(remaining,Math.max(1000,60000-(clock()-cycle))));
 }return {ticks};}finally{delete env.assertStatusLease;await env.DB.prepare("UPDATE rs_state SET value='0',updated_at=? WHERE key=? AND value=?").bind(stamp(),key,lease).run();}
}
export async function recoverMarketStatus(env,{maximumMs=270*60000,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms)),shouldStop=()=>false,report=event=>console.error(JSON.stringify({...event,event:'market_status_restart',observed_at:new Date(clock()).toISOString()})),...options}={}){
 let runs=0;
 // A timed-out release/renewal may have committed remotely. A retry waits for the
 // ordinary bounded lease to expire; it never forces ownership or extends the job.
 return recoverWatch(remaining=>watchMarketStatus(env,{...options,maximumMs:remaining,acquireWaitMs:runs++?Math.min(200000,remaining):0,clock,sleep,shouldStop}),{maximumMs,clock,pause:sleep,shouldStop,report});
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence'});env.PUBLIC_STATUS_COMMIT=process.env.RS_STATUS_COMMIT;let stop=false;process.once('SIGTERM',()=>{stop=true;});process.once('SIGINT',()=>{stop=true;});try{const result=await recoverMarketStatus(env,{shouldStop:()=>stop});if(process.env.GITHUB_OUTPUT)appendFileSync(process.env.GITHUB_OUTPUT,'continue='+(!result.skipped)+'\n');console.log(JSON.stringify(result));}catch(error){console.error(JSON.stringify({event:'market_status_source_failed',error:error.message}));process.exitCode=1;}}
