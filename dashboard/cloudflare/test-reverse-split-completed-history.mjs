import test from 'node:test';
import assert from 'node:assert/strict';
import {completedSplitEvidence,reviewedPriorHistory,REVIEWED_SPLIT_HISTORY} from './reverse-split-live/split-history.mjs';
import {screen} from './reverse-split-live/core.mjs';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {queueReviewedHistoryRepair} from './reverse-split-live/split-history.mjs';
import {sha} from './reverse-split-live/worker.mjs';
const clock={published_at:'2026-04-29T04:00:00Z',now:'2026-11-10T17:00:00Z'};
test('completed split-adjusted trading is positive prior evidence, not merely approval',()=>{
 const text='Our Class A Ordinary Shares began trading on an adjusted basis, reflecting the Reverse Share Split, on March 3, 2025, under the existing ticker symbol LICN.';
 assert.deepEqual(completedSplitEvidence(text,clock).map(r=>r.date),['2025-03-03']);
 for(const text of ['The company effected a 1-for-15 reverse share split on July 29, 2025.','On July 29, 2025, the Company effected a 1-for-15 reverse share split.','The Reverse Share Split became effective after the close of business on July 28, 2025.'])assert.equal(completedSplitEvidence(text,{...clock,published_at:'2026-08-15T04:00:00Z'}).length,1);
});
test('review queues new bounded work only after archiving originals and never edits existing history',async t=>{
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT); CREATE TABLE rs_history(id TEXT PRIMARY KEY,cik TEXT,effective_date TEXT,payload TEXT); CREATE TABLE rs_events(id TEXT PRIMARY KEY,cik TEXT)');
 db.prepare('INSERT INTO rs_history VALUES(?,?,?,?)').run('original','2022416','2025-07-14','original evidence');db.prepare('INSERT INTO rs_events VALUES(?,?)').run('slxn-event','2022416');const original=db.prepare('SELECT * FROM rs_history').get(),queued=[],objects=new Map(),env={DB:localAdapter(db),EVIDENCE:{put:async()=>{throw new Error('Archive temporarily unavailable');}}},options={hash:sha,enqueue:async(...args)=>queued.push(args)};
 await assert.rejects(queueReviewedHistoryRepair(env,options),/Archive/);assert.equal(queued.length,0);assert.equal(db.prepare('SELECT count(*) AS n FROM rs_state').get().n,0);
 env.EVIDENCE.put=async(k,v)=>objects.set(k,JSON.parse(new TextDecoder().decode(v)));await queueReviewedHistoryRepair(env,options);assert.equal(queued.length,2);assert.equal(queued[0][1].expected_sha256,'b9bab50f402ebdb3e8bee8f8fa16b6a3df6f9af6e438469c11e5f34e6490618e');assert.equal(queued[0][1].published_at,'2026-04-29T04:00:00.000Z');assert.deepEqual(db.prepare('SELECT * FROM rs_history').get(),original);assert.equal(objects.values().next().value.original_history_rows[0].payload,'original evidence');await queueReviewedHistoryRepair(env,options);assert.equal(queued.length,2);
});
test('a completed meeting cannot establish a split, and future or negated implementation stays unknown',()=>{
 const texts=['The reverse share split was approved by shareholders at the annual general meeting that was completed on July 14, 2025. As announced July 16, the effective time will be after the close July 28, 2025.','The Company will have effected a reverse share split on July 29, 2025.','The Company never effected a reverse share split on July 29, 2025.','A proposed reverse share split effective July 29, 2025.','The reverse share split was approved on July 14, 2025.'];
 for(const text of texts)assert.deepEqual(completedSplitEvidence(text,{...clock,published_at:'2026-08-15T04:00:00Z'}),[],text);
 assert.deepEqual(completedSplitEvidence('The company effected a reverse share split on July 29, 2025.',{...clock,published_at:'2025-07-22T04:00:00Z'}),[]);
});
test('reviewed legal and trading dates count as one action without editing source rows or other issuers',()=>{
 const r=REVIEWED_SPLIT_HISTORY,rows=r.actions.flatMap(a=>[a.effective_date,a.trading_date].map((effective_date,i)=>({cik:r.cik,effective_date,known_at:'2026-09-01T00:00:00Z',verified:true,source_sha256:a.source_sha256[i]}))).concat(r.excluded.map(x=>({...x,cik:r.cik,known_at:'2026-09-01T00:00:00Z',verified:true})),r.preserved_completed.map(x=>({...x,cik:r.cik,known_at:'2026-09-01T00:00:00Z',verified:true}))),original=structuredClone(rows),view=reviewedPriorHistory(rows,'2026-11-10T17:30:00Z');
 assert.equal(new Set(view.filter(x=>x.verified).map(x=>x.effective_date)).size,3);assert.deepEqual(rows,original);
 const event={cik:r.cik,status:'scheduled',published_at:'2026-11-09T12:00:00Z',first_seen_at:'2026-11-09T12:03:33Z',effective_date:'2026-11-11'};
 const decision=screen(event,{score:56.5,status:'scored'},rows,'2026-11-10T17:30:00Z');assert.equal(decision.ordinal_min,4);assert.equal(screen(event,{score:56.5,status:'scored'},rows,'2026-11-09T20:00:00Z').ordinal_min,7);assert.equal(decision.checks.repeat.state,'pass');assert.equal(decision.checks.fundamentals.state,'fail');
 const foreign=rows.map(x=>({...x,cik:'123'}));assert.deepEqual(reviewedPriorHistory(foreign),foreign);
 const wrong=rows.map(x=>({...x,source_sha256:'f'.repeat(64)}));assert.deepEqual(reviewedPriorHistory(wrong),wrong);
});
