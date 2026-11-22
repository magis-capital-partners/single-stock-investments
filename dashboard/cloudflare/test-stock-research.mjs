import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash, webcrypto } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { onRequestGet as getPreferences, onRequestPut, validatePreference } from '../functions/api/v1/research/preferences.js';
import { onRequestGet as getData, readResearchObject } from '../functions/api/v1/research/data.js';
import { onRequestGet as getAlerts, onRequestPut as readAlerts } from '../functions/api/v1/research/alerts.js';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const sha = b => createHash('sha256').update(b).digest('hex');
const migration=readFileSync(new URL('./migrations/0027_research_preferences.sql',import.meta.url),'utf8');
function database(){
 const path=join(mkdtempSync(join(tmpdir(),'stock-research-')),'preferences.sqlite');
 const script=`import json,sqlite3,sys\nx=json.load(sys.stdin)\nc=sqlite3.connect(x['path']);c.row_factory=sqlite3.Row\nwith c:\n if 'schema' in x:c.executescript(x['schema']);print('{}')\n else:\n  q=c.execute(x['sql'],x['args']);print(json.dumps({'results':[dict(r) for r in q.fetchall()] if q.description else [],'meta':{'changes':max(q.rowcount,0)}}))`;
 function call(payload){const r=spawnSync(process.platform==='win32'?'python':'python3',['-c',script],{input:JSON.stringify({path,...payload}),encoding:'utf8'});if(r.status)throw Error(r.stderr);return JSON.parse(r.stdout);}
 call({schema:migration});return {prepare(sql){const statement=args=>({bind(...args){return statement(args);},async first(){return call({sql,args}).results[0]||null;},async all(){return call({sql,args});},async run(){return call({sql,args});}});return statement([]);}};
}
function context(email='drew@example.com',body,DB){return {data:{humanViewer:{email,role:'owner'}},env:{DB},request:new Request('https://dashboard.example/api/v1/research/preferences',{method:body?'PUT':'GET',headers:body?{'content-type':'application/json','origin':'https://dashboard.example'}:{},...(body?{body:JSON.stringify(body)}:{})})};}
test('preferences are scoped to the verified viewer and use optimistic revisions',async()=>{
 const DB=database(),value={templates:{growth:{name:'Growth',view:{metrics:['revenue']}}}};
 assert.equal((await onRequestPut(context('drew@example.com',{key:'workspace',value,revision:0},DB))).status,200);
 const own=await (await getPreferences(context('drew@example.com',null,DB))).json();assert.deepEqual(own.value,value);assert.equal(own.revision,1);
 const other=await (await getPreferences(context('michael@example.com',null,DB))).json();assert.deepEqual(other.value,{});
 assert.equal((await onRequestPut(context('drew@example.com',{key:'workspace',value:{},revision:0},DB))).status,409);
 assert.equal((await onRequestPut(context('drew@example.com',{key:'workspace',value:{},revision:1},DB))).status,200);
 assert.deepEqual((await (await getPreferences(context('michael@example.com',null,DB))).json()).value,{});
});
test('saved workspace rejects unrecognized keys, over-size values, cross-origin writes and readers',async()=>{
 assert.equal(validatePreference('unknown',{}),false);assert.equal(validatePreference('workspace',{text:'a'.repeat(524288)}),false);
 const c=context();c.data.humanViewer.role='reader';assert.equal((await getPreferences(c)).status,401);
 const x=context('drew@example.com',{key:'workspace',value:{},revision:0});x.request=new Request(x.request,{headers:{origin:'https://attacker.example'}});assert.equal((await onRequestPut(x)).status,403);
});
test('private financial shards verify compressed and raw hashes, sizes and company identity',async()=>{
 const raw=Buffer.from(JSON.stringify({schema_version:'stock-research-explorer.v1',ticker:'TEST'})),stored=gzipSync(raw);
 const chunk={sha256:sha(raw),bytes:raw.length,stored_sha256:sha(stored),stored_bytes:stored.length,encoding:'gzip'},record={sha256:sha(raw),bytes:raw.length,chunks:[chunk]};
 const pointer={schema_version:'stock-research-live.v1',as_of:'2026-11-21',companies:{TEST:record}};
 const bucket={async get(key){if(key==='research-explorer/v1/current.json')return {size:500,json:async()=>pointer};return {size:stored.length,arrayBuffer:async()=>stored.buffer.slice(stored.byteOffset,stored.byteOffset+stored.length)};}};
 assert.equal(await readResearchObject(bucket,record),raw.toString());
 await assert.rejects(readResearchObject(bucket,{...record,sha256:'0'.repeat(64)}));
 await assert.rejects(readResearchObject(bucket,{...record,bytes:21*1024*1024}));
 const c=context();c.env.PRIVATE_ARTIFACTS=bucket;c.request=new Request('https://dashboard.example/api/v1/research/data?ticker=TEST');assert.equal((await getData(c)).status,200);
 c.request=new Request('https://dashboard.example/api/v1/research/data?ticker=OTHER');assert.equal((await getData(c)).status,404);
 c.request=new Request('https://dashboard.example/api/v1/research/data?ticker=..%2FTEST');assert.equal((await getData(c)).status,400);
 c.data.humanViewer.role='reader';assert.equal((await getData(c)).status,401);
});
test('persistent alert inbox and read status cannot cross verified owners',async()=>{
 const DB=database();
 for(const [email,key]of [['drew@example.com','drew-event'],['michael@example.com','michael-event']])await DB.prepare('INSERT INTO research_alert_events(viewer_email,event_key,rule_id,ticker,metric,observed_value,period,release_sha256) VALUES (?,?,?,?,?,?,?,?)').bind(email,key,'rule','TEST','pe',10,'2026-11-18','a'.repeat(64)).run();
 const c=context('drew@example.com',null,DB),own=await(await getAlerts(c)).json();assert.deepEqual(own.events.map(r=>r.event_key),['drew-event']);
 assert.equal((await readAlerts(c)).status,200);
 const other=await(await getAlerts(context('michael@example.com',null,DB))).json();assert.equal(other.events[0].read_at,null);
 const after=await(await getAlerts(c)).json();assert.ok(after.events[0].read_at);
});
