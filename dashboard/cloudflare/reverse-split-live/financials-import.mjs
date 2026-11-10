// External collector only. Verified scores survive handoffs; urgent lookups bypass batch warming.
import {buildFinancialProfile,FINANCIAL_VERSION} from './financials-core.mjs';
import {etDay,DAY} from './core.mjs';
import {enqueue,sha} from './worker.mjs';
import {loadPreparedFinancial} from './prepared-universe.mjs';
const read=async(env,key,signal,urgent=false)=>{const o=await env.EVIDENCE.get(key,{signal,urgent});return o?o.json():null;};
const validCik=cik=>/^\d{1,10}$/.test(String(cik));
const cacheKey=cik=>'financial_score_cache:'+cik;
export const FINANCIAL_EVIDENCE_REVISION='primary_source_reconciliation.2026-11-10.v1';
export const MAX_RETAINED_FINANCIAL_PROFILES=24;
export function retainFinancialProfile(env,cik,saved){
  env.financialProfiles.delete(cik);env.financialProfiles.set(cik,saved);
  while(env.financialProfiles.size>MAX_RETAINED_FINANCIAL_PROFILES)env.financialProfiles.delete(env.financialProfiles.keys().next().value);
}
function usableCache(saved,cutoff){
  if(!saved||saved.calculation_revision!==FINANCIAL_EVIDENCE_REVISION||saved.schema!==FINANCIAL_VERSION||!validCik(saved.cik)||!saved.computed_at||Date.parse(saved.computed_at)>Date.parse(cutoff)||etDay(saved.computed_at)!==etDay(cutoff))return null;
  const score={...saved.score,cutoff},age=score.period?(Date.parse(etDay(cutoff))-Date.parse(score.period))/DAY:Infinity;
  if(age<0||age>200)return {...score,score:null,status:'stale_or_missing_period'};
  return score;
}
async function rememberScore(env,cik,score,computed_at){
  const saved={schema:FINANCIAL_VERSION,calculation_revision:FINANCIAL_EVIDENCE_REVISION,cik,computed_at,score};env.financialScoreCache.set(cik,saved);
  await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(cacheKey(cik),JSON.stringify(saved),computed_at).run();
}
function calculate(saved,cik,cutoff){
  const p=buildFinancialProfile({cik,companyfacts:saved.raw,facts:saved.facts,sources:saved.profile.sources,as_of:cutoff,instrument:saved.profile.coverage.instrument});
  return {...p.policy_financials,evidence_revision:FINANCIAL_EVIDENCE_REVISION,issuer_financials:p.issuer_financials,source_profile_version:saved.profile.version,coverage_status:p.coverage.status,source_url:saved.profile.sources[0]?.url,source_sha256:saved.profile.collection.api_source_sha256||saved.profile.sources[0]?.sha256};
}
async function loadEnhanced(env,cik,{version,signal,rescore=false,urgent=false}={}){
  const profile=await read(env,`financials/profiles/${cik}/${version||'latest'}.json`,signal,urgent);if(!profile)return false;
  if(profile.cik!==cik||profile.schema!==FINANCIAL_VERSION||!/^[a-f0-9]{64}$/.test(profile.version||'')||(version&&profile.version!==version))throw new Error('Financial profile identity mismatch');
  if(env.financialProfiles.get(cik)?.profile.version===profile.version)return true;
  if(profile.facts_object_key!==`financials/facts/${cik}/${profile.version}.json`)throw new Error('Unexpected financial ledger path');
  const [ledger,rawDoc]=await Promise.all([read(env,profile.facts_object_key,signal,urgent),profile.collection.api_source_sha256?read(env,'documents/'+profile.collection.api_source_sha256,signal,urgent):null]);
  if(!ledger||ledger.schema!==FINANCIAL_VERSION||ledger.cik!==cik||ledger.source_profile_version!==profile.version||!Array.isArray(ledger.facts)||ledger.facts.length>15000||!profile.facts_sha256||await sha(JSON.stringify(ledger))!==profile.facts_sha256)throw new Error('Financial fact ledger integrity check failed');
  const raw=rawDoc||{cik,facts:{}};if(String(Number(raw.cik))!==cik||(profile.collection.api_source_sha256&&!rawDoc))throw new Error('Financial API cache identity mismatch');
  if(signal?.aborted)throw signal.reason;
  const saved={profile,raw,facts:ledger.facts},at=new Date().toISOString(),score=calculate(saved,cik,at);retainFinancialProfile(env,cik,saved);await rememberScore(env,cik,score,at);env.financialProfileVersions.set(cik,profile.version);
  if(rescore)for(const e of (await env.DB.prepare('SELECT id FROM rs_events WHERE cik=?').bind(cik).all()).results)await enqueue(env,'rescore',{id:e.id},14,'financial-profile:'+profile.version+':'+e.id);
  return true;
}
export function installFinancialImport(env){
  env.financialProfiles=new Map();env.financialScoreCache=new Map();env.financialLoads=new Map();env.financialProfileVersions=new Map();
  env.restoreFinancialScores=async()=>{
    const rows=(await env.DB.prepare("SELECT value FROM rs_state WHERE key>='financial_score_cache:' AND key<'financial_score_cache;' LIMIT 20000").all()).results;
    for(const row of rows)try{const saved=JSON.parse(row.value);if(saved.schema===FINANCIAL_VERSION&&validCik(saved.cik)){env.financialScoreCache.set(saved.cik,saved);if(saved.calculation_revision===FINANCIAL_EVIDENCE_REVISION&&/^[a-f0-9]{64}$/.test(saved.score?.source_profile_version||''))env.financialProfileVersions.set(saved.cik,saved.score.source_profile_version);}}catch{}
    return env.financialScoreCache.size;
  };
  env.scoreFinancialProfile=(cik,cutoff)=>{
    const warm=usableCache(env.financialScoreCache.get(cik),cutoff);if(warm)return warm;
    const saved=env.financialProfiles.get(cik);return saved?calculate(saved,cik,cutoff):null;
  };
  env.ensureFinancialProfile=async(cik,{maximumMs=4000}={})=>{
    cik=String(Number(cik));if(!validCik(cik))return false;
    if(env.scoreFinancialProfile(cik,new Date().toISOString()))return true;
    if(env.financialLoads.has(cik)){let timer;try{return await Promise.race([env.financialLoads.get(cik),new Promise(resolve=>{timer=setTimeout(()=>resolve(false),maximumMs);})]);}finally{clearTimeout(timer);}}
    const signal=AbortSignal.timeout(maximumMs),task=(async()=>{
      if(await loadEnhanced(env,cik,{signal,urgent:true}))return true;
      const prepared=await loadPreparedFinancial(env,cik,{signal});if(!prepared)return false;
      await rememberScore(env,cik,prepared,new Date().toISOString());return true;
    })().finally(()=>env.financialLoads.delete(cik));env.financialLoads.set(cik,task);return task;
  };
  env.onFinancialDisclosure=async disclosure=>{
    await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind('financial_need:'+disclosure.cik,JSON.stringify(disclosure),new Date().toISOString()).run();
  };
}
export async function importFinancialProfiles(env,{maximum=12}={}){
  const manifest=await read(env,'financials/manifest-latest.json');if(!manifest||manifest.schema!==FINANCIAL_VERSION)return;
  let count=0;for(const item of manifest.profiles){
    if(count>=maximum)break;if(!validCik(item.cik)||!/^[a-f0-9]{64}$/.test(item.version))continue;
    if(env.financialProfileVersions.get(item.cik)===item.version&&usableCache(env.financialScoreCache.get(item.cik),new Date().toISOString())||env.financialLoads.has(item.cik))continue;count++;
    const task=loadEnhanced(env,item.cik,{version:item.version,rescore:true}).finally(()=>env.financialLoads.delete(item.cik));env.financialLoads.set(item.cik,task);await task;
  }
}
