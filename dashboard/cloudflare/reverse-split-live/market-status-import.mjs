import {createHash} from 'node:crypto';
import {publicMarketEvidence} from './market-status-core.mjs';
import {putState} from './shadow-service.mjs';
const hash=v=>createHash('sha256').update(v).digest('hex');
export async function importMarketStatus(env,now=new Date().toISOString()){
 const healthObject=await env.EVIDENCE.get('market-status/health.json'),producer=healthObject?await healthObject.json():null;
 const object=await env.EVIDENCE.get('market-status/latest.json');if(!object){await putState(env,'public_market_status_health',{status:'not_started',producer,intraday_ssr_clearance:false},now);return;}
 const snapshot=await object.json();if(snapshot.schema!=='reverse_split_public_market_status.v1')throw new Error('Unknown public market-status schema');const {sha256,immutable_key,...signed}=snapshot;if(hash(JSON.stringify(signed))!==sha256)throw new Error('Public market-status snapshot checksum mismatch');
 if(env.listedStatusKey!==snapshot.listing.key){const directory=await env.EVIDENCE.get(snapshot.listing.key);if(!directory)throw new Error('Market listing directory missing');const raw=await directory.text();if(hash(raw)!==snapshot.listing.sha256)throw new Error('Market listing directory checksum mismatch');env.listedStatus=new Set(JSON.parse(raw).symbols);env.listedStatusKey=snapshot.listing.key;}
 const events=(await env.DB.prepare("SELECT payload FROM rs_events WHERE first_seen_at>=? OR id IN (SELECT event_id FROM rs_execution_tracks WHERE state IN ('armed','partial_entry','open','exit_pending')) OR id IN (SELECT event_id FROM rs_shadow_tracks WHERE state IN ('armed','partial_entry','open','exit_pending'))").bind(new Date(Date.parse(now)-24*3600000).toISOString()).all()).results;let imported=0;
 for(const row of events)for(const evidence of publicMarketEvidence({...snapshot,listed:env.listedStatus},JSON.parse(row.payload),now)){const text=JSON.stringify(evidence),id=hash(text);await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(id,evidence.event_id,evidence.kind,evidence.observed_at,JSON.stringify({...evidence,id})).run();imported++;}
 await putState(env,'public_market_status_health',{status:Date.parse(now)-Date.parse(snapshot.halts.observed_at)<=65000?'partial_free_exchange_evidence':'stale',producer,snapshot_at:snapshot.generated_at,feed_as_of:snapshot.halts.as_of,listing_count:env.listedStatus.size,imported,intraday_ssr_clearance:false,broker_allocation:false,immutable_key,source_sha256:sha256},now);
}
