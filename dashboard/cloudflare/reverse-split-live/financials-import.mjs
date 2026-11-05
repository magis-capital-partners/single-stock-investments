// External collector only. Warm financial evidence independently of the quote loop.
import {buildFinancialProfile,FINANCIAL_VERSION} from './financials-core.mjs';
import {enqueue,sha} from './worker.mjs';
const read=async(env,key)=>{const o=await env.EVIDENCE.get(key);return o?o.json():null;};
export function installFinancialImport(env){
  env.financialProfiles=new Map();
  env.scoreFinancialProfile=(cik,cutoff)=>{
    const saved=env.financialProfiles.get(cik);if(!saved)return null;
    const p=buildFinancialProfile({cik,companyfacts:saved.raw,facts:saved.facts,sources:saved.profile.sources,as_of:cutoff,instrument:saved.profile.coverage.instrument});
    return {...p.policy_financials,source_profile_version:saved.profile.version,coverage_status:p.coverage.status,source_url:saved.profile.sources[0]?.url,source_sha256:saved.profile.collection.api_source_sha256||saved.profile.sources[0]?.sha256};
  };
  env.onFinancialDisclosure=async disclosure=>{
    // A local signal is included in the next private snapshot. No new D1 writes.
    await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind('financial_need:'+disclosure.cik,JSON.stringify(disclosure),new Date().toISOString()).run();
  };
}
export async function importFinancialProfiles(env,{maximum=3}={}){
  const manifest=await read(env,'financials/manifest-latest.json');if(!manifest||manifest.schema!==FINANCIAL_VERSION)return;
  let count=0;for(const item of manifest.profiles){
    if(count>=maximum)break;
    if(!/^\d{1,10}$/.test(item.cik)||!/^[a-f0-9]{64}$/.test(item.version))continue;
    if(env.financialProfiles.get(item.cik)?.profile.version===item.version)continue;count++;
    const profile=await read(env,`financials/profiles/${item.cik}/${item.version}.json`);if(!profile||profile.cik!==item.cik||profile.schema!==FINANCIAL_VERSION)throw new Error('Financial profile identity mismatch');
    const ledger=await read(env,profile.facts_object_key);if(!ledger||ledger.cik!==item.cik||ledger.source_profile_version!==item.version||!Array.isArray(ledger.facts)||ledger.facts.length>15000||(profile.facts_sha256&&await sha(JSON.stringify(ledger))!==profile.facts_sha256))throw new Error('Financial fact ledger integrity check failed');
    let raw={cik:item.cik,facts:{}};if(profile.collection.api_source_sha256){raw=await read(env,'documents/'+profile.collection.api_source_sha256);if(!raw||String(Number(raw.cik))!==item.cik)throw new Error('Financial API cache identity mismatch');}
    env.financialProfiles.set(item.cik,{profile,raw,facts:ledger.facts});
    // These are new, timestamped decisions. Original decisions/fills remain immutable.
    for(const e of (await env.DB.prepare('SELECT id FROM rs_events WHERE cik=?').bind(item.cik).all()).results)await enqueue(env,'rescore',{id:e.id},9,'financial-profile:'+item.version+':'+e.id);
  }
}
