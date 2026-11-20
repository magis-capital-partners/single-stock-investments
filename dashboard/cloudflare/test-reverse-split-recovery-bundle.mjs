import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {limitedFetch} from './reverse-split-live/worker.mjs';
import {openRecoveryBundle,installRecoveryBundle,reconcileUnavailableFiling} from './reverse-split-live/recovery-bundle.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const archive='https://www.prnewswire.com/news-releases/news-releases-list/?page=1&pagesize=100',article='https://www.prnewswire.com/news-releases/ordinary-302900002.html',at='2026-11-20T16:00:00Z';
function setup(t,{missingBody=false}={}){
 const dir=mkdtempSync(join(tmpdir(),'rs-repair-test-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));const documents=[];
 const add=(url,name,body)=>{writeFileSync(join(dir,name),body);const d={url,path:name,bytes:Buffer.byteLength(body),sha256:hash(body),content_type:'text/html',retrieved_at:at};documents.push(d);return d;};
 const row=(time,id)=>`<a class="newsreleaseconsolidatelink" href="/news-releases/ordinary-${id}.html"><h3>Ordinary release</h3><small>November 20, 2026, ${time} ET</small></a>`;
 const page=add(archive,'page.html',row('09:30','302900001')+row('09:15','302900002')+row('09:00','302900003'));
 if(!missingBody)add(article,'body.html',`<meta property="og:url" content="${article}"><script>{"datePublished":"2026-11-20T14:15:00Z"}</script><section class="release-body">Ordinary report</section>`);
 const manifest={schema:'reverse_split_recovery_bundle.v1',documents,publisher:{source:'prnewswire',pages:[{page:1,url:page.url}],gaps:[{id:'gap',source_id:'prnewswire',start_at:'2026-11-20T14:10:00Z',end_at:'2026-11-20T14:20:00Z'}]}};
 const bytes=JSON.stringify(manifest),file=join(dir,'manifest.json');writeFileSync(file,bytes);const bundle=openRecoveryBundle(file,{expectedSha256:hash(bytes)});
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());for(const n of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+n,import.meta.url),'utf8'));
 db.prepare('INSERT INTO rs_source_gaps(id,source_id,start_at,end_at,created_at) VALUES(?,?,?,?,?)').run('gap','prnewswire','2026-11-20T14:10:00Z','2026-11-20T14:20:00Z',at);
 const objects=new Map(),env={DB:localAdapter(db),assertCollectorLease(){},EVIDENCE:{put:async(k,b)=>objects.set(k,b)}};return {dir,file,bundle,db,env,objects};
}
test('recovery bundle preserves late discovery clocks and cannot close a gap by inventory alone',async t=>{
 const {bundle,db,env,objects}=setup(t);await installRecoveryBundle(env,bundle,{now:at});
 const state=JSON.parse(db.prepare("SELECT value FROM rs_state WHERE key='publisher_recovery:gap'").get().value),job=db.prepare('SELECT * FROM rs_jobs').get(),payload=JSON.parse(job.payload);
 assert.equal(state.inventory_complete,true);assert.equal(state.coverage_complete,false);assert.equal(db.prepare('SELECT resolved_at FROM rs_source_gaps').get().resolved_at,null);
 assert.equal(job.state,'pending');assert.equal(job.priority,9);assert.equal(payload.first_seen_at,at);assert.equal(payload.published_at,'2026-11-20T14:15:00.000Z');assert.equal(payload.url,article);assert.ok(objects.size>=2);
 assert.equal((await installRecoveryBundle(env,bundle,{now:at})).already_installed,true);
});
test('a repair capture never freezes mutable publisher pages or current SEC metadata',async t=>{
 const {bundle}=setup(t);assert.equal(await bundle.fetchDocument(archive),null);assert.ok(await bundle.fetchDocument(article));
});
test('ordinary source checks always fetch current bytes; captured bytes require a matching repair job context',async t=>{
 const previous=globalThis.fetch;t.after(()=>globalThis.fetch=previous);let calls=0;globalThis.fetch=async()=>{calls++;return new Response('live bytes');};const env={recoveryBundle:{sha256:'a'.repeat(64)},recoveryDocument:async()=>({bytes:Buffer.from('capture')})};
 assert.equal(new TextDecoder().decode((await limitedFetch(env,article)).bytes),'live bytes');assert.equal(new TextDecoder().decode((await limitedFetch({...env,recoveryCapture:'a'.repeat(64)},article)).bytes),'capture');assert.equal(new TextDecoder().decode((await limitedFetch({...env,recoveryCapture:'b'.repeat(64)},article)).bytes),'live bytes');assert.equal(calls,2);
});
test('missing article bytes leave coverage untouched; document hashes and manifest pin fail closed',async t=>{
 const {bundle,db,env}=setup(t,{missingBody:true});await assert.rejects(installRecoveryBundle(env,bundle,{now:at}),/article.*missing/i);assert.equal(db.prepare('SELECT count(*) n FROM rs_jobs').get().n,0);
 const good=setup(t);writeFileSync(join(good.dir,'body.html'),'tampered');await assert.rejects(installRecoveryBundle(good.env,good.bundle,{now:at}),/hash|identity/);assert.throws(()=>openRecoveryBundle(good.file,{expectedSha256:'0'.repeat(64)}),/manifest/);
});
test('a retired SEC reference requires official same-day inventory and an already archived completed canonical job',async t=>{
 const {db,env,objects}=setup(t),original={cik:'896493',accession:'0001214659-24-016464',published_at:'2024-09-18T04:00:00.000Z',url:'https://www.sec.gov/Archives/edgar/data/896493/000121465924016464/0001214659-24-016464.txt'},canonical={...original,accession:'0001214659-24-016539',url:'https://www.sec.gov/Archives/edgar/data/896493/000121465924016539/0001214659-24-016539.txt'};
 for(const [p,state,error] of [[original,'failed','Source returned HTTP 404'],[canonical,'pending',null]])db.prepare('INSERT INTO rs_jobs(id,kind,payload,state,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?)').run('history-filing:'+p.accession,'history_filing',JSON.stringify(p),state,error,at,at);
 const metadata={cik:'0000896493',filings:{recent:{accessionNumber:['new','0001214659-24-016539','old'],filingDate:['2026-11-19','2024-09-17','2021-07-16'],form:['8-K','8-K/A','8-K'],primaryDocument:['new.htm','o9172438ka2.htm','old.htm']}}},bytes=Buffer.from(JSON.stringify(metadata)),bundle={manifest:{reconcile_unavailable_filing:true},read:()=>({url:'https://data.sec.gov/submissions/CIK0000896493.json',bytes,sha256:hash(bytes),retrieved_at:at,content_type:'application/json'})};
 await assert.rejects(reconcileUnavailableFiling(env,bundle,{now:at}),/completed canonical/);db.prepare("UPDATE rs_jobs SET state='complete' WHERE id=?").run('history-filing:'+canonical.accession);await assert.rejects(reconcileUnavailableFiling(env,bundle,{now:at}),/no archived primary/);
 db.prepare('INSERT INTO rs_documents VALUES(?,?,?,?,?,?)').run('c'.repeat(64),canonical.url,'documents/'+'c'.repeat(64),at,100,'text/plain');assert.equal((await reconcileUnavailableFiling(env,bundle,{now:at})).reconciled,1);
 const row=db.prepare('SELECT * FROM rs_jobs WHERE id=?').get('history-filing:'+original.accession);assert.equal(row.state,'superseded');assert.equal(row.payload,JSON.stringify(original));assert.match(row.error,/Unavailable reference retained/);
 const proof=[...objects.entries()].filter(([key])=>key.startsWith('review/repairs/')).map(([,b])=>JSON.parse(new TextDecoder().decode(b)))[0];assert.equal(proof.original_job.error,'Source returned HTTP 404');assert.ok(proof.limitations.some(v=>v.includes('not recovered')));assert.equal((await reconcileUnavailableFiling(env,bundle,{now:at})).reconciled,0);
});
