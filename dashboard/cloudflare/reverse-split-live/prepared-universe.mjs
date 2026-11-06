// Shared, bounded readers for the broad SEC preparation snapshot.
import {etDay,DAY} from './core.mjs';
export const PREPARED_SCHEMA='reverse_split_prepared.v1';
export const PREPARED_BUCKETS=512;
const read=async(env,key,signal,urgent=false)=>{const o=await env.EVIDENCE.get(key,{signal,urgent});return o?o.json():null;};
const digest=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(x=>x.toString(16).padStart(2,'0')).join('');
export async function preparedManifest(env,{signal,refresh=false,urgent=false}={}){
  const old=env.preparedManifest;if(!refresh&&old&&Date.now()-old.loaded_at<60000)return old.value;
  const value=await read(env,'prepared/manifest-latest.json',signal,urgent);if(value&&value.schema!==PREPARED_SCHEMA)throw new Error('Prepared universe schema mismatch');env.preparedManifest={value,loaded_at:Date.now()};return value;
}
export async function preparedCompany(env,cik,{signal,urgent=false}={}){
  if(!/^\d{1,10}$/.test(String(cik)))return null;const manifest=await preparedManifest(env,{signal,urgent});if(!manifest)return null;
  const parts=manifest.shards?.[String(Number(cik)%PREPARED_BUCKETS)]||[],part=parts.find(p=>Number(cik)>=p.minimum_cik&&Number(cik)<=p.maximum_cik);if(!part)return null;
  if(!/^prepared\/shards\/[a-f0-9]{64}\.json$/.test(part.key)||part.bytes>512000)throw new Error('Prepared shard exceeds its bounded contract');
  env.preparedShardCache ||= new Map();let shard=env.preparedShardCache.get(part.key);
  if(!shard){shard=await read(env,part.key,signal,urgent);if(!shard||await digest(JSON.stringify(shard))!==part.sha256||shard.schema!==PREPARED_SCHEMA)throw new Error('Prepared shard integrity failure');env.preparedShardCache.set(part.key,shard);while(env.preparedShardCache.size>16)env.preparedShardCache.delete(env.preparedShardCache.keys().next().value);}
  const p=shard.profiles[cik];if(!p)return null;if(p.cik!==cik||p.schema!==PREPARED_SCHEMA)throw new Error('Prepared company identity failure');return p;
}
export async function loadPreparedFinancial(env,cik,{signal,cutoff=new Date().toISOString()}={}){
  const p=await preparedCompany(env,cik,{signal,urgent:true});if(!p)return null;
  if(Date.parse(p.prepared_at)>Date.parse(cutoff)||Date.parse(cutoff)-Date.parse(p.prepared_at)>36*3600000)return null;
  // New dated reports cannot silently enter a different scoring day through an old snapshot.
  if(p.as_of_day!==etDay(cutoff))return null;
  const score={...p.financials,cutoff,prepared_at:p.prepared_at,source_profile_version:p.version,evidence_layer:PREPARED_SCHEMA,security_identity_required:true};
  const age=score.period?(Date.parse(etDay(cutoff))-Date.parse(score.period))/DAY:Infinity;
  if(age<0||age>200)return {...score,score:null,status:'stale_or_missing_period'};return score;
}
export async function preparedAPI(request,env){
  const u=new URL(request.url);if(!u.pathname.startsWith('/prepared'))return null;if(request.method!=='GET')return Response.json({error:'Method not allowed'},{status:405});
  const manifest=await preparedManifest(env);if(!manifest)return Response.json({status:'not_prepared',summary:null,companies:[]},{status:202});
  const headers={'cache-control':'no-store, private','x-content-type-options':'nosniff'};
  if(u.pathname==='/prepared/summary')return Response.json(manifest.summary,{headers});
  if(u.pathname==='/prepared'){
    const page=Number(u.searchParams.get('page')||0);if(!Number.isInteger(page)||page<0||page>=Math.max(1,manifest.pages.length))return Response.json({error:'Invalid page'},{status:400,headers});
    const data=manifest.pages[page]?await read(env,manifest.pages[page]):{companies:[]};return Response.json({...data,summary:manifest.summary,next_page:page+1<manifest.pages.length?page+1:null},{headers});
  }
  const m=/^\/prepared\/(\d{1,10})$/.exec(u.pathname);if(!m)return Response.json({error:'Not found'},{status:404,headers});const company=await preparedCompany(env,String(Number(m[1])));return Response.json(company||{error:'Company not in prepared universe'},{status:company?200:404,headers});
}
