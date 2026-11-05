// Local scan database, atomically committed into one of two private R2 slots.
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,readFileSync,writeFileSync,readdirSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname,basename} from 'node:path';
import {sha} from './worker.mjs';
function cleanup(dir){const target=realpathSync(dir),parent=realpathSync(tmpdir()),equal=(a,b)=>process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b;if(!equal(dirname(target),parent)||!basename(target).startsWith('reverse-split-'))throw new Error('Unsafe collector temporary directory');rmSync(target,{recursive:true,force:true});}

export function localAdapter(db){const make=(sql,args=[])=>({bind:(...values)=>make(sql,values),first:async()=>db.prepare(sql).get(...args)||null,all:async()=>({results:db.prepare(sql).all(...args)}),run:async()=>({meta:{changes:Number(db.prepare(sql).run(...args).changes)}})});return {prepare:sql=>make(sql),batch:async statements=>{db.exec('BEGIN');try{const rows=[];for(const s of statements)rows.push(await s.run());db.exec('COMMIT');return rows;}catch(e){db.exec('ROLLBACK');throw e;}}};}

export async function openCheckpoint(env){
  const remote=env.controlDB,dir=mkdtempSync(join(tmpdir(),'reverse-split-')),file=join(dir,'research.sqlite');let db,receipt;
  try{
    receipt=JSON.parse((await remote.prepare("SELECT value FROM rs_state WHERE key='collector_checkpoint'").first())?.value||'null');
    if(receipt){const object=await env.EVIDENCE.get(`collector-state/slot${receipt.slot}.sqlite`);if(!object)throw new Error('Committed collector checkpoint is unavailable');const bytes=new Uint8Array(await object.arrayBuffer());if(await sha(bytes)!==receipt.sha256)throw new Error('Collector checkpoint checksum mismatch; original evidence preserved');writeFileSync(file,bytes);}
    db=new DatabaseSync(file);db.exec('PRAGMA journal_mode=DELETE');for(const name of readdirSync(new URL('./migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./migrations/'+name,import.meta.url),'utf8'));
    env.DB=localAdapter(db);
    const bootstrap=readFileSync(new URL('./bootstrap.json',import.meta.url)),bootstrapHash=await sha(bootstrap);
    if(!db.prepare("SELECT value FROM rs_state WHERE key='prior_history_bootstrap'").get()||db.prepare("SELECT value FROM rs_state WHERE key='prior_history_bootstrap'").get().value!==bootstrapHash){
      const data=JSON.parse(bootstrap);if(data.schema!=='reverse_split_prior_history.v1')throw new Error('Unexpected historical action seed');
      db.exec('BEGIN');try{for(const r of data.records){if(!r.verified||!r.cik||!r.effective_date||!r.known_at||!r.source_url?.startsWith('https://'))throw new Error('Unbound historical action');db.prepare('INSERT OR IGNORE INTO rs_history(id,cik,effective_date,known_at,verified,payload) VALUES(?,?,?,?,1,?)').run(r.cik+':'+r.effective_date,r.cik,r.effective_date,r.known_at,JSON.stringify(r));}db.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('prior_history_bootstrap',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(bootstrapHash,new Date().toISOString());db.exec('COMMIT');}catch(e){db.exec('ROLLBACK');throw e;}
    }
  }catch(e){db?.close();cleanup(dir);throw e;}
  return {
    async save(){
      for(const p of env.pending.splice(0))await env.DB.prepare("UPDATE rs_jobs SET state='pending',token=NULL WHERE id=? AND token=? AND state='queued'").bind(p.id,p.token).run();
      const at=new Date().toISOString(),jobs=db.prepare('SELECT state,count(*) AS count,min(created_at) AS oldest FROM rs_jobs GROUP BY state').all();
      db.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('collector_job_counts',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(JSON.stringify(jobs),at);
      const publications=[];
      const backgroundDue=Date.now()-Number(db.prepare("SELECT value FROM rs_state WHERE key='source_publication_at'").get()?.value||0)>=300000;
      async function changed(kind,id,payload,statement){if(kind==='source'&&!backgroundDue)return;const hash=await sha(payload),key='published:'+kind+':'+id,old=db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value;if(old!==hash)publications.push({key,hash,statement});}
      for(const r of db.prepare('SELECT * FROM rs_sources').all())await changed('source',r.id,JSON.stringify(r),remote.prepare('INSERT INTO rs_sources(id,kind,url,last_attempt,last_success,watermark,status,error,failures,next_attempt,coverage_gap,items) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=excluded.last_success,watermark=excluded.watermark,status=excluded.status,error=excluded.error,failures=excluded.failures,next_attempt=excluded.next_attempt,coverage_gap=excluded.coverage_gap,items=excluded.items').bind(...['id','kind','url','last_attempt','last_success','watermark','status','error','failures','next_attempt','coverage_gap','items'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_events').all())await changed('event',r.id,r.payload,remote.prepare('INSERT INTO rs_events(id,cik,ticker,company,effective_date,published_at,first_seen_at,analyzed_at,result,score,ordinal_min,revision,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,company=excluded.company,effective_date=excluded.effective_date,published_at=excluded.published_at,analyzed_at=excluded.analyzed_at,result=excluded.result,score=excluded.score,ordinal_min=excluded.ordinal_min,revision=excluded.revision,payload=json_set(excluded.payload,\'$.first_seen_at\',rs_events.first_seen_at) WHERE rs_events.payload<>excluded.payload').bind(...['id','cik','ticker','company','effective_date','published_at','first_seen_at','analyzed_at','result','score','ordinal_min','revision','payload'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_decisions').all())await changed('decision',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_decisions(id,event_id,recorded_at,policy,payload) VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.recorded_at,r.policy,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_alerts').all())await changed('alert',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_alerts(id,event_id,created_at,kind,payload) VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.created_at,r.kind,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_policies').all())await changed('shadow-policy',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_policies VALUES(?,?,?)').bind(r.id,r.registered_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_tracks').all())await changed('shadow-track',r.id,r.payload,remote.prepare('INSERT INTO rs_shadow_tracks(id,event_id,policy_id,cik,ticker,enrolled_at,signal_at,due_at,state,reason,updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,signal_at=excluded.signal_at,due_at=excluded.due_at,state=excluded.state,reason=excluded.reason,updated_at=excluded.updated_at,payload=excluded.payload').bind(...['id','event_id','policy_id','cik','ticker','enrolled_at','signal_at','due_at','state','reason','updated_at','payload'].map(k=>r[k])));
      for(const r of db.prepare('SELECT * FROM rs_shadow_records').all())await changed('shadow-record',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_records VALUES(?,?,?,?,?,?)').bind(r.id,r.track_id,r.event_id,r.kind,r.recorded_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_quotes').all())await changed('shadow-quote',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_quotes VALUES(?,?,?,?,?)').bind(r.id,r.ticker,r.quote_at,r.observed_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_evidence').all())await changed('shadow-evidence',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.kind,r.observed_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_shadow_daily').all())await changed('shadow-day',r.id,r.payload,remote.prepare('INSERT INTO rs_shadow_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(r.id,r.policy_id,r.day,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_policies').all())await changed('execution-policy',r.id,r.payload,remote.prepare('INSERT OR IGNORE INTO rs_execution_policies VALUES(?,?,?)').bind(r.id,r.registered_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_tracks').all())await changed('execution-track',r.id,r.payload,remote.prepare('INSERT INTO rs_execution_tracks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ticker=excluded.ticker,state=excluded.state,updated_at=excluded.updated_at,payload=excluded.payload').bind(r.id,r.event_id,r.policy_id,r.ticker,r.state,r.updated_at,r.payload));
      for(const r of db.prepare('SELECT * FROM rs_execution_daily').all())await changed('execution-day',r.id,r.payload,remote.prepare('INSERT INTO rs_execution_daily VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload').bind(r.id,r.policy_id,r.day,r.payload));
      const cursors=[];
      for(const [table,fields] of [['rs_execution_records',['id','track_id','recorded_at','kind','payload']],['rs_borrow_observations',['id','ticker','day','kind','as_of','observed_at','payload']]]){
        const key='publication_cursor:'+table,last=Number(db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value||0),rows=db.prepare(`SELECT rowid AS sequence,* FROM ${table} WHERE rowid>? ORDER BY rowid`).all(last);
        for(const r of rows)publications.push({statement:remote.prepare(`INSERT OR IGNORE INTO ${table} VALUES(${fields.map(()=>'?').join(',')})`).bind(...fields.map(k=>r[k]))});
        if(rows.length)cursors.push({key,value:String(rows.at(-1).sequence)});
      }
      const keys=['last_tick','last_completed_tick','service_mode','last_reconciliation','reconciliation_error','collector_job_counts','last_collector_run','shadow_started_at','shadow_summary','execution_summary','validation_plan','validation_summary','shadow_borrow_health','flex_borrow_health'];
      const routineKeys=['last_tick','last_completed_tick','collector_job_counts'];
      const stateRows=db.prepare('SELECT * FROM rs_state').all().filter(r=>keys.includes(r.key)&&(backgroundDue||!routineKeys.includes(r.key))),states=[];
      for(const r of stateRows){const key='published:state:'+r.key,hash=await sha(JSON.stringify([r.value,r.updated_at]));if(db.prepare('SELECT value FROM rs_state WHERE key=?').get(key)?.value!==hash)states.push({r,key,hash});}
      // Write the inactive slot before committing its pointer. A killed runner leaves the active slot intact.
      const slot=receipt?.slot===0?1:0,bytes=readFileSync(file),next={slot,sha256:await sha(bytes),bytes:bytes.length,at};
      await env.EVIDENCE.put(`collector-state/slot${slot}.sqlite`,bytes,{httpMetadata:{contentType:'application/vnd.sqlite3'}});
      await remote.prepare("INSERT INTO rs_state(key,value,updated_at) VALUES('collector_checkpoint',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").bind(JSON.stringify(next),at).run();receipt=next;
      // The committed checkpoint is authoritative before any dashboard publication.
      // A failed publication retries from that checkpoint and cannot erase a simulated fill.
      for(let i=0;i<publications.length;i+=60){const group=publications.slice(i,i+60);await remote.batch(group.map(p=>p.statement));for(const p of group)if(p.key)db.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(p.key,p.hash,at);}
      for(const {key,value} of cursors)db.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(key,value,at);
      if(backgroundDue)db.prepare("INSERT INTO rs_state VALUES('source_publication_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at").run(String(Date.now()),at);
      if(states.length){await remote.batch(states.map(({r})=>remote.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind(r.key,r.value,r.updated_at)));for(const {key,hash} of states)db.prepare('INSERT INTO rs_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').run(key,hash,at);}
      return next;
    },
    changedSince(at){return Boolean(db.prepare('SELECT id FROM rs_events WHERE analyzed_at>? LIMIT 1').get(at));},
    close(){db.close();cleanup(dir);},
  };
}
