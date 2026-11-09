import test from 'node:test';
import assert from 'node:assert/strict';
import {historySearchURL,historySearchPage,queueHistorySearch,recoverHistorySearch} from './reverse-split-live/history-search.mjs';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {enqueue,sha} from './reverse-split-live/worker.mjs';
function setup(t){const db=new DatabaseSync(':memory:');for(const n of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+n,import.meta.url),'utf8'));t.after(()=>db.close());return db;}
test('SEC prior-split searches use a ten-digit company ID and include foreign share-split terminology',()=>{
 const url=new URL(historySearchURL('2022416',{start:'2016-11-09',end:'2026-11-09'}));assert.equal(url.searchParams.get('ciks'),'0002022416');assert.match(url.searchParams.get('q'),/"reverse share split"/);assert.equal(url.searchParams.get('size'),'100');
});
test('the actual padded Silexion response contains 37 distinct filing accessions',()=>{
 const raw=JSON.parse(readFileSync(new URL('./reverse-split-live/fixtures/sec-history-silexion-20261109.json',import.meta.url),'utf8')),page=historySearchPage(raw,'2022416',{end:'2026-11-09'});assert.equal(page.total,65);assert.equal(page.filings.length,37);assert.equal(page.complete,true);
});
test('new announcements promote pending history work without resetting completed jobs',async t=>{
 const db=setup(t),env={DB:localAdapter(db)},at='2026-11-09T15:00:00Z',put=(...args)=>enqueue(env,...args);
 await put('history',{cik:'2022416'},3,'history:v2:2022416:2026-11-09:0');await put('history_filing',{cik:'2022416'},2,'history-filing:pending');await put('history_filing',{cik:'2022416'},2,'history-filing:complete');db.prepare("UPDATE rs_jobs SET state='complete' WHERE id='history-filing:complete'").run();
 await queueHistorySearch(env,{cik:'2022416',first_seen_at:at},put,at);assert.equal(db.prepare("SELECT priority FROM rs_jobs WHERE id='history:v2:2022416:2026-11-09:0'").get().priority,12);assert.equal(db.prepare("SELECT priority FROM rs_jobs WHERE id='history-filing:pending'").get().priority,11);assert.equal(db.prepare("SELECT priority FROM rs_jobs WHERE id='history-filing:complete'").get().priority,2);
});
test('history job identity follows the Eastern trading day after UTC midnight',async t=>{const db=setup(t),env={DB:localAdapter(db)},at='2026-11-10T00:30:00Z';await queueHistorySearch(env,{cik:'2022416',first_seen_at:at},(...args)=>enqueue(env,...args),at);assert.ok(db.prepare("SELECT id FROM rs_jobs WHERE id='history:v2:2022416:2026-11-09:0'").get());});
test('history repair archives original false-complete searches before one versioned retry',async t=>{
 const db=setup(t),objects=new Map(),env={DB:localAdapter(db),EVIDENCE:{put:async(k,v)=>objects.set(k,v)}},at='2026-11-09T15:00:00Z',put=(...args)=>enqueue(env,...args);
 db.prepare("INSERT INTO rs_issuers(cik,history_status) VALUES('2022416','search_complete')").run();db.prepare("INSERT INTO rs_events(id,cik,first_seen_at,payload) VALUES('event','2022416',?,'{}')").run(at);await put('history',{cik:'2022416'},3,'history:2022416:2026-11-09');db.prepare("UPDATE rs_jobs SET state='complete' WHERE id='history:2022416:2026-11-09'").run();
 assert.equal((await recoverHistorySearch(env,{enqueue:put,hash:sha,now:at})).queued,1);const original=JSON.parse(new TextDecoder().decode([...objects.values()][0]));assert.equal(original.original_jobs[0].state,'complete');assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='history:2022416:2026-11-09'").get().state,'complete');assert.equal((await recoverHistorySearch(env,{enqueue:put,hash:sha,now:at})).queued,0);assert.equal(objects.size,1);
});
test('history inventory deduplicates exhibits, paginates and refuses incomplete or foreign-issuer hits',()=>{
 const hit={_source:{ciks:['0002022416'],adsh:'0001178913-26-002988',file_date:'2026-05-29'}},page=historySearchPage({hits:{total:{value:101,relation:'eq'},hits:Array.from({length:100},()=>hit)}},'2022416',{offset:0,end:'2026-11-09'});assert.equal(page.filings.length,1);assert.equal(page.next,100);assert.equal(page.complete,false);
 assert.equal(historySearchPage({hits:{total:{value:101,relation:'eq'},hits:[hit]}},'2022416',{offset:100,end:'2026-11-09'}).complete,true);
 assert.throws(()=>historySearchPage({hits:{total:{value:1,relation:'eq'},hits:[]}},'2022416',{end:'2026-11-09'}),/Incomplete/);assert.throws(()=>historySearchPage({hits:{total:{value:1,relation:'eq'},hits:[hit]}},'999',{end:'2026-11-09'}),/issuer/);
});
