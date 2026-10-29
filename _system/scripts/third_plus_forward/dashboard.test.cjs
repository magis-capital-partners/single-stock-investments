'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const V=require('../../../dashboard/third-plus-forward.js'),ROOT=path.resolve(__dirname,'../../..');
const original=JSON.parse(fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_forward.json'),'utf8'));
const state=()=>({policy:original.policies[0].id,decision:'',query:''});
test('committed publication checksum covers the exact served bytes on Windows and Linux',()=>{
  const body=fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_forward.json'));
  const manifest=JSON.parse(fs.readFileSync(path.join(ROOT,'dashboard/data/third_plus_forward_manifest.json'),'utf8'));
  assert.equal(crypto.createHash('sha256').update(body).digest('hex'),manifest.sha256);
});
test('the publication preserves two frozen 20-session books without trading authority',()=>{
  const d=V.validate(original);assert.equal(d.all_names_assumed_tradable,true);assert.equal(d.policies.length,2);
  assert.deepEqual(d.policies.map(p=>p.requires),[['S7','burn','S5'],['S7','burn']]);
  assert.ok(d.policies.every(p=>p.hold_sessions===20&&p.slots===3&&!p.results.review_ready));
});
test('missing actual fills display unknown profit and never manufactured zero returns',()=>{
  const d=structuredClone(original);for(const p of d.policies){p.results.entered=0;p.results.closed=0;p.results.net_closed_pnl=null;}
  const html=V.view(d,state());assert.match(html,/Awaiting evidence/);assert.match(html,/orders disabled/);assert.match(html,/Only sourced paper fills/);
});
test('candidate screen supports signal, company and decision inspection with escaped inputs',()=>{
  const d=structuredClone(original);const candidate={event_id:'event/X',issuer_id:'cik/X',ticker:'X',company:'<img src=x onerror=alert(1)>',policy_id:state().policy,effective_day:'2026-10-27',ordinal:3,signals:{S7:'pass',burn:'pass',S5:'unknown'},decision:'abstain',reason:'Required signal remains unknown',target_usd:0,input_sha256:'a'.repeat(64)};
  d.candidates=[candidate];const s=state();assert.match(V.table(d,s),/&lt;img/);assert.ok(!V.table(d,s).includes('<img'));s.query='onerror';assert.equal(V.rows(d,s).length,1);s.query='missing';assert.equal(V.rows(d,s).length,0);s.query='';s.decision='observe';assert.equal(V.rows(d,s).length,0);
});
test('CSV is quoted, filtered and neutralizes formula prefixes',()=>{
  const d=structuredClone(original);d.candidates=[{policy_id:state().policy,ticker:'=SUM(1)',decision:'observe',reason:'a,"b"'}];const csv=V.csv(d,state());assert.ok(csv.includes("'=SUM(1)"));assert.ok(csv.includes('a,""b""'));
});
test('untrusted documentation links cannot execute script URLs',()=>{
  const d=structuredClone(original);d.links.runbook='javascript:alert(1)';assert.ok(!V.view(d,state()).includes('javascript:'));
});
test('loader checks exact manifest bytes and publication version',async()=>{
  const body=JSON.stringify(original),manifest={schema:'third_plus_forward_manifest.v1',payload:'third_plus_forward.json',data_version:original.data_version,sha256:crypto.createHash('sha256').update(body).digest('hex')};
  const fetcher=async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body};
  assert.equal((await V.load(fetcher,crypto.webcrypto)).data_version,original.data_version);
  manifest.sha256='0'.repeat(64);await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/different publications/);
  manifest.sha256=crypto.createHash('sha256').update(body).digest('hex');manifest.data_version='bad';await assert.rejects(()=>V.load(fetcher,crypto.webcrypto),/Mixed forward/);
});
test('dashboard route, source assets and research workflow are connected',()=>{
  const html=fs.readFileSync(path.join(ROOT,'dashboard/index.html'),'utf8'),workflow=fs.readFileSync(path.join(ROOT,'.github/workflows/reverse-split-borrow-history.yml'),'utf8');
  assert.match(html,/short-alpha\\\/forward/);assert.match(html,/third-plus-forward\.js/);assert.match(html,/ThirdPlusForward\.attach\(content\)/);
  assert.match(workflow,/third_plus_forward monitor --max-requests 30/);assert.match(workflow,/third_plus_forward check/);assert.match(workflow,/git add _system\/data\/reverse_splits\/third_plus_forward_v1/);
});
