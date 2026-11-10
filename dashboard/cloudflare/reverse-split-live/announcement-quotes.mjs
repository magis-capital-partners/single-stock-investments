// Independent observation, including rejected/unscored signals. Never creates fills.
import {digest,putState} from './shadow-service.mjs';
import {at,finite} from './shadow-core.mjs';
const DAY=86400000;
export async function registerAnnouncement(env,event,now=new Date().toISOString()){
 const old=await env.DB.prepare('SELECT payload FROM rs_announcement_watches WHERE event_id=?').bind(event.id).first();
 const saved=old?JSON.parse(old.payload):null;
 const until=new Date(Math.max(at(event.first_seen_at)||at(now),at(event.effective_date)||0)+10*DAY).toISOString();
 const row={...saved,event_id:event.id,ticker:event.ticker||saved?.ticker||null,cik:event.cik||null,company:event.company||null,announcement_status:event.status,first_seen_at:event.first_seen_at,registered_at:saved?.registered_at||now,watch_until:until,late_registration:at(now)-at(event.first_seen_at)>15000,status:saved?.status||'awaiting_quote',samples:saved?.samples||0,authority:'none'};
 await env.DB.prepare('INSERT INTO rs_announcement_watches VALUES(?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET ticker=excluded.ticker,watch_until=excluded.watch_until,payload=excluded.payload').bind(row.event_id,row.ticker,row.first_seen_at,row.registered_at,row.watch_until,JSON.stringify(row)).run();
 if(at(until)>at(now))env.market?.warm?.(row.ticker);
 return row;
}
export async function initializeAnnouncementQuotes(env,now=new Date().toISOString()){
 const events=(await env.DB.prepare('SELECT payload FROM rs_events WHERE first_seen_at>=?').bind(new Date(at(now)-2*DAY).toISOString()).all()).results;
 for(const r of events)await registerAnnouncement(env,JSON.parse(r.payload),now);
 env.onAnnouncementDetection=event=>registerAnnouncement(env,event);
}
export async function announcementQuoteTick(env,now=new Date().toISOString()){
 if(at(now)<(env.nextAnnouncementQuotes||0))return;
 env.nextAnnouncementQuotes=at(now)+5000;
 const rows=(await env.DB.prepare('SELECT payload FROM rs_announcement_watches WHERE watch_until>=? ORDER BY first_seen_at DESC').bind(now).all()).results.map(r=>JSON.parse(r.payload));
 const names=[...new Set(rows.map(r=>r.ticker).filter(t=>/^[A-Z][A-Z0-9.]{0,11}$/.test(t||'')))];env.announcementQuoteSymbols=names;
 const errors=new Map(),quotes=new Map();let identityRequests=0;
 // Read the existing shared subscription. No additional market-data session.
 for(const ticker of names){try{
  const q=env.market.peek?env.market.peek(ticker):await env.market.observe(ticker);
  if(!env.market.identityKnown?.(ticker)&&identityRequests<2&&env.market.verifyIdentity){identityRequests++;env.market.verifyIdentity(ticker).catch(()=>{});}
  if(!q&&env.market.health?.symbol_budget_remaining===0&&!env.market.health.per_symbol?.some(r=>r.ticker===ticker))throw new Error('Databento symbol budget exhausted; observation missing');
  if(!q||q.dataset!=='EQUS.MINI'||q.size_units!=='shares'||![q.bid,q.ask,q.bid_size,q.ask_size].every(finite)||q.bid<=0||q.ask<q.bid||q.bid_size<=0||q.ask_size<=0||at(q.quote_at)===null||at(q.observed_at)===null||at(now)-at(q.quote_at)>15000||at(q.quote_at)>at(now)+2000||at(q.observed_at)>at(now)+2000)throw new Error('Fresh identified two-sided displayed quote required');
  if(at(q.observed_at)===null||at(now)-at(q.observed_at)>15000)throw new Error('Fresh quote receipt required');
  const sample={...q,identity_verified:q.identity_verified===true,recorded_at:now,spread_bps:10000*(q.ask-q.bid)/((q.ask+q.bid)/2),event_ids:rows.filter(r=>r.ticker===ticker&&at(q.observed_at)>=at(r.registered_at)).map(r=>r.event_id),research_only:true,broker_execution_verified:false};
  if(!sample.event_ids.length)throw new Error('Quote predates observation registration');
  const id=await digest(JSON.stringify([ticker,q.quote_at,q.observed_at,q.bid,q.ask,q.bid_size,q.ask_size]));sample.id=id;
  await env.DB.prepare('INSERT OR IGNORE INTO rs_announcement_quote_samples VALUES(?,?,?,?)').bind(id,ticker,q.observed_at,JSON.stringify(sample)).run();quotes.set(ticker,sample);
 }catch(e){errors.set(ticker,e.message);}}
 for(const row of rows){const q=quotes.get(row.ticker);if(q&&q.event_ids.includes(row.event_id)){
   row.status=!q.identity_verified?'observed_identity_pending':q.cik&&String(Number(q.cik))===String(Number(row.cik))?'observed':'identity_mismatch';
   if(row.latest?.id!==q.id)row.samples++;
   row.first_quote ||= q;row.latest=q;row.error=null;
  }else{row.status=row.ticker?'awaiting_fresh_quote':'identity_unresolved';row.error=errors.get(row.ticker)||'Ticker unresolved';}
  row.last_attempt=now;await env.DB.prepare('UPDATE rs_announcement_watches SET payload=? WHERE event_id=?').bind(JSON.stringify(row),row.event_id).run();
 }
 // Immutable archive first; only remove buffered samples after storage acknowledges.
 if(at(now)>=(env.nextAnnouncementArchive||0)){
  const pending=(await env.DB.prepare('SELECT id,payload FROM rs_announcement_quote_samples ORDER BY observed_at,id LIMIT 2000').all()).results;
  if(pending.length){const samples=pending.map(r=>JSON.parse(r.payload)),raw=JSON.stringify({schema:'reverse_split_announcement_quotes.v1',samples}),sha=await digest(raw),key='announcement-quotes/'+sha+'.json';
   await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
   await env.DB.prepare('INSERT OR IGNORE INTO rs_announcement_quote_archives VALUES(?,?,?)').bind(sha,now,JSON.stringify({key,sha256:sha,count:samples.length,first_at:samples[0].observed_at,last_at:samples.at(-1).observed_at})).run();
   for(const r of pending)await env.DB.prepare('DELETE FROM rs_announcement_quote_samples WHERE id=?').bind(r.id).run();
  }env.nextAnnouncementArchive=at(now)+60000;
 }
 const archives=(await env.DB.prepare('SELECT payload FROM rs_announcement_quote_archives ORDER BY recorded_at DESC LIMIT 1000').all()).results.map(r=>JSON.parse(r.payload));
 await putState(env,'announcement_quote_summary',{schema:'reverse_split_announcement_quote_summary.v1',generated_at:now,cadence_seconds:5,coverage:'selected_venues_not_sip_nbbo',events:rows,archives,archive_index_truncated:archives.length===1000,authority:'none',orders:0,broker_connections:0,limits:['Five-second observed-book samples, not a complete tick history or guaranteed execution. Restores may repeat physical quote IDs across archives; deduplicate IDs and retain original recorded/identity-verification clocks.','Late registration never reconstructs announcement-time quotes.','Unknown identity, subscription-budget exhaustion, stale quotes and missing bids/sizes remain explicit gaps.','Observation is independent of scoring and never approves a locate, halt/SSR clearance or a simulated fill.']},now);
}
