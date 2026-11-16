import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {repairReviewedLargePdf} from './reverse-split-live/worker.mjs';
import {extractAnnouncementText} from './reverse-split-live/announcement-text.mjs';

test('reviewed large PDF retry archives the exact original failure once and leaves other failures alone',async t=>{
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());for(const f of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+f,import.meta.url),'utf8'));
 const id='filing:0001213900-26-119240',error='Announcement PDF requires verified readable text',at='2026-11-13T14:12:54.085Z';
 for(const key of [id,'filing:unreviewed'])db.prepare("INSERT INTO rs_jobs(id,kind,payload,state,priority,attempts,created_at,updated_at,error) VALUES(?,'filing',?,'failed',10,6,?,?,?)").run(key,JSON.stringify({first_seen_at:'2026-11-13T13:39:56.123Z'}),at,at,error);
 const archived=[],env={DB:localAdapter(db),EVIDENCE:{put:async(key,raw)=>{assert.equal(db.prepare('SELECT state FROM rs_jobs WHERE id=?').get(id).state,'failed');archived.push(JSON.parse(new TextDecoder().decode(raw)));}}};
 assert.equal((await repairReviewedLargePdf(env)).retried,1);assert.equal(archived.length,1);assert.equal(archived[0].original_job.attempts,6);assert.equal(archived[0].original_job.error,error);assert.equal(archived[0].original_job.updated_at,at);assert.equal(db.prepare('SELECT state FROM rs_jobs WHERE id=?').get(id).state,'pending');assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='filing:unreviewed'").get().state,'failed');
 assert.equal((await repairReviewedLargePdf(env)).retried,0);assert.equal(archived.length,1);
});

test('native large-report review is archived only with the exact child source and page binding',async()=>{
 const bytes=new TextEncoder().encode('%PDF-fixture'),digest=createHash('sha256').update(bytes).digest('hex');
 async function run({source=digest,pages=513,profile='external_primary_report'}={}){
  const child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();child.kill=()=>{};const reviews=[];
  const task=extractAnnouncementText(bytes,{pdfProfile:profile,spawnProcess:()=>child,onReview:async review=>reviews.push(review)});
  child.stdout.write(JSON.stringify({schema:'announcement_text.v1',text:'All native source pages retained',pages:513,complete:true,reader_review:{schema:'announcement_bounded_source_review.v1',source_sha256:source,pages}}));child.emit('exit',0);return {task,reviews};
 }
 const good=await run();assert.equal(await good.task,'All native source pages retained');assert.equal(good.reviews.length,1);assert.equal(good.reviews[0].source_sha256,digest);
 for(const options of [{source:'wrong'},{pages:514},{profile:'standard'}]){const bad=await run(options);await assert.rejects(bad.task,/identity is invalid/);assert.equal(bad.reviews.length,0);}
});
