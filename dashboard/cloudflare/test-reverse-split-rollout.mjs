import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {consume} from './reverse-split-live/worker.mjs';
import {loadFilingDocuments} from './reverse-split-live/filing-documents.mjs';
function setup(t){const db=new DatabaseSync(':memory:');for(const n of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+n,import.meta.url),'utf8'));t.after(()=>db.close());return {db,env:{DB:localAdapter(db),EVIDENCE:{put:async()=>{}},SEC_USER_AGENT:'qa'}};}

test('an unfinished reconciliation is retried rather than recorded as a completed recovery',async t=>{
 const {db,env}=setup(t);env.deadline=Date.now()-1;db.prepare("INSERT INTO rs_jobs(id,kind,payload,state,token,lease_until,created_at,updated_at) VALUES('reconcile-qa','reconcile','{}','queued','qa',9999999999999,'now','now')").run();
 await consume({messages:[{body:{id:'reconcile-qa',token:'qa'},ack(){}}]},env);assert.equal(db.prepare("SELECT state FROM rs_jobs WHERE id='reconcile-qa'").get().state,'pending');assert.ok(db.prepare("SELECT value FROM rs_state WHERE key='reconciliation_error'").get());
});
test('external filing fallback can read a bounded 32 MiB primary without expanding Worker limits',async()=>{
 const p={cik:'123',accession:'0000000123-26-000001',form:'10-Q',url:'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/0000000123-26-000001.txt'},bytes=new Uint8Array(32*1024*1024),index='<tr><td>1</td><td>Primary</td><td><a href="report.htm">report</a></td><td>10-Q</td></tr>';
 const fetcher=async(url,{maximum=24*1024*1024}={})=>{if(url===p.url)throw new Error('Source exceeds document size limit');if(url.endsWith('-index.html'))return {url,bytes:new TextEncoder().encode(index)};if(bytes.length>maximum)throw new Error('Source exceeds document size limit');return {url,bytes};};
 const result=await loadFilingDocuments({COLLECTOR_MODE:'external_collector'},p,fetcher);assert.equal(result.documents[0].bytes.length,bytes.length);await assert.rejects(loadFilingDocuments({},p,fetcher),/size limit/);
});
