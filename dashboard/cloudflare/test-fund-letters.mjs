import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { humanRole, requireHumanViewer, viewerFromAccessPayload } from '../functions/_lib/auth.js';
import { accessDecision, onRequest } from '../functions/_middleware.js';
import { parseSearchTokens, readerIdea, readerLetter, sourceSections, validateDraft } from '../functions/_lib/fund-letters.js';
import { onRequestGet, onRequestPost } from '../functions/api/fund-letters.js';

function database() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./migrations/0023_fund_letters.sql',import.meta.url),'utf8'));
  // Exercise production SQL, rather than maintaining query-specific mocked answers.
  const prepare = sql => ({ bind(...args) { return { async all() {return {results:db.prepare(sql).all(...args)};}, async first() {return db.prepare(sql).get(...args)||null;}, async run() {return {meta:{changes:db.prepare(sql).run(...args).changes}};} }; } });
  return { db, prepare, async batch(stmts) {db.exec('BEGIN');try{const rows=[];for(const stmt of stmts)rows.push(await stmt.run());db.exec('COMMIT');return rows;}catch(error){db.exec('ROLLBACK');throw error;}} };
}
const owner = {email:'drew@magiscapitalpartners.com',role:'owner'};
const reader = {email:'reader@example.com',role:'reader'};
const context = (query,viewer=reader,DB=database()) => ({request:new Request('https://test.example/api/fund-letters?'+new URLSearchParams(query)),env:{DB},data:{humanViewer:viewer}});
const source = 'Acme earns subscription income from its customers. Revenue increased 20% this year. Management expects renewals to remain strong. Customer losses are a risk.';
const draft = () => ({overview:'The manager examines an opportunity in recurring customer payments.',ideas:[{id:'acme',title:'Acme subscriptions',ticker:'ACME',idea_type:'long',summary:'The fund argues that customer payments create attractive recurring economics. It reports revenue growth of 20% and identifies customer retention as an uncertainty.',evidence:[{claim:'Economics, growth and risk',section_id:'s1',quote:source}]}],checklist:[{section_id:'s1',idea_ids:['acme'],disposition:'covered',reason:'Acme economics and risks summarized.'}]});

function seed(DB,count=1) {
  DB.db.exec("INSERT INTO fl_funds(id,name) VALUES('fund','Test Fund');");
  for(let i=0;i<count;i++) {
    DB.db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,ingested_at,source_ref,source_url,source_text,published_revision) VALUES(?,?,?,?,?,?,?,?,?,?)').run('l'+i,'fund','hash'+i,'v1','2020Q1','2026-10-23','private/path','https://drive.google.com/SECRET',source,'r'+i);
    DB.db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?)').run('r'+i,'l'+i,'2026-10-23','editor','published',draft().overview,JSON.stringify(draft()),'{}');
    DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,summary,ordinal) VALUES(?,?,?,?,?,?,?,?)').run('acme','r'+i,'l'+i,'Acme subscriptions','ACME','long',draft().ideas[0].summary,0);
  }
}

test('only the two verified identities become owners; service tokens and revoked users cannot read',()=>{
  assert.equal(humanRole({email:'DREW@magiscapitalpartners.com'}),'owner');
  assert.equal(humanRole({email:'mike@magiscapitalpartners.com'}),'owner');
  assert.equal(humanRole({email:'drew@example.com'}),'reader');
  assert.equal(viewerFromAccessPayload({email:'drew@magiscapitalpartners.com',common_name:'Drew'}).service_token,null);
  assert.equal(humanRole(viewerFromAccessPayload({email:'drew@magiscapitalpartners.com',common_name:'Drew'})),'owner');
  assert.equal(humanRole(viewerFromAccessPayload({common_name:'ingest-token'})),null);
  assert.equal(humanRole({email:'reader@example.com',service_token:'machine'}),null);
  assert.equal(humanRole(reader,{CF_ACCESS_REVOKED_EMAILS:'reader@example.com'}),null);
  assert.equal(humanRole({email:'Drew.Access@example.com'},{PORTFOLIO_DREW_ACCESS_EMAILS:'drew.access@example.com'}),'owner');
  assert.equal(humanRole({email:'mike.access@example.com'},{PORTFOLIO_MICHAEL_ACCESS_EMAILS:'Mike.Access@example.com, other@example.com'}),'owner');
  assert.equal(humanRole({email:'other@example.com'},{PORTFOLIO_DREW_ACCESS_EMAILS:'drew.access@example.com'}),'reader');
  assert.equal(humanRole({email:'both@example.com'},{PORTFOLIO_DREW_ACCESS_EMAILS:'both@example.com',PORTFOLIO_MICHAEL_ACCESS_EMAILS:'both@example.com'}),'reader');
  assert.equal(humanRole(viewerFromAccessPayload({email:'Drew Goldman <drew@magiscapitalpartners.com>'})),'owner');
  assert.equal(humanRole(viewerFromAccessPayload({email:'personal@example.com',common_name:'drew@magiscapitalpartners.com'})),'owner');
  assert.equal(humanRole(viewerFromAccessPayload({common_name:'drew@magiscapitalpartners.com'})),'owner');
  assert.equal(humanRole(viewerFromAccessPayload({email:'drew@magiscapitalpartners.com',common_name:'Drew',service_token_id:'machine'})),null);
  assert.equal(humanRole({email:'drew.access@example.com'},{PORTFOLIO_DREW_ACCESS_EMAILS:'drew.access@example.com',CF_ACCESS_REVOKED_EMAILS:'drew.access@example.com'}),null);
});
test('signed owners and readers, revocation, forged/expired tokens and cookie authentication exercise the actual boundary',async()=>{
  const env={CF_ACCESS_TEAM_DOMAIN:'https://test.cloudflareaccess.com',CF_ACCESS_AUD:'reader-audience'};
  const pair=await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
  const jwk=await crypto.subtle.exportKey('jwk',pair.publicKey);jwk.kid='signing-key';
  const encode=obj=>Buffer.from(JSON.stringify(obj)).toString('base64url');
  async function token(email,extra={}){const message=encode({alg:'RS256',kid:jwk.kid})+'.'+encode({email,iss:env.CF_ACCESS_TEAM_DOMAIN,aud:[env.CF_ACCESS_AUD],exp:Date.now()/1000+600,type:'app',...extra});return message+'.'+Buffer.from(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,new TextEncoder().encode(message))).toString('base64url');}
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async()=>new Response(JSON.stringify({keys:[jwk]}));
  try{
    for(const [email,role] of [['drew@magiscapitalpartners.com','owner'],['mike@magiscapitalpartners.com','owner'],['reader@example.com','reader']]){
      const signed=await token(email);
      const ctx={request:new Request('https://preview.pages.dev/fund-letters/',{headers:{'cf-access-jwt-assertion':signed}}),env,data:{},next:async()=>new Response('allowed')};
      assert.equal((await requireHumanViewer(ctx)).role,role);
      ctx.data={};
      const response=await onRequest(ctx);
      if(role==='owner'){assert.equal(response.status,302);assert.equal(response.headers.get('location'),'/');}
      else assert.equal(response.status,200);
      ctx.request=new Request('https://preview.pages.dev/data/core.json',{headers:{'cf-access-jwt-assertion':signed}});ctx.data={};
      assert.equal((await onRequest(ctx)).status,role==='owner'?200:403);
    }
    const signed=await token('reader@example.com');
    assert.equal((await requireHumanViewer({request:new Request('https://test.example/',{headers:{cookie:'CF_Authorization='+signed}}),env})).role,'reader');
    for(const invalid of [await token('reader@example.com',{exp:Date.now()/1000-600}),await token('reader@example.com',{aud:['wrong']}),await token('reader@example.com',{iss:'https://evil.cloudflareaccess.com'}),signed.split('.').slice(0,2).join('.')+'.AAAA']){
      const ctx={request:new Request('https://test.example/data/core.json',{headers:{'cf-access-jwt-assertion':invalid}}),env,data:{},next:()=>{throw new Error('Must deny before asset access');}};
      assert.equal((await onRequest(ctx)).status,401);
    }
    assert.equal(await requireHumanViewer({request:new Request('https://test.example/',{headers:{'cf-access-jwt-assertion':signed}}),env:{...env,CF_ACCESS_REVOKED_EMAILS:'reader@example.com'}}),null);
    assert.equal(await requireHumanViewer({request:new Request('https://preview.pages.dev/'),env:{PORTFOLIO_AUTH_MODE:'development'}}),null);
    assert.equal(await requireHumanViewer({request:new Request('https://test.example/',{headers:{'cf-access-jwt-assertion':signed}}),env:{}}),null);
  }finally{globalThis.fetch=originalFetch;}
});
test('direct dashboard requests, private data, guessed files and source APIs are denied to readers',()=>{
  for(const path of ['/data/core.json','/index-viz.js','/data/insights/letters.json','/data/company-research/companies/CME.json','/data/company-research/documents/original.json','/data/company-research/search/CME.json','/api/v2/portfolio/book','/original.pdf','/fund-letters/../../data/core.json','/cloudflare-artifact-manifest.json']) assert.equal(accessDecision(path,'GET',reader),'forbidden',path);
  for(const path of ['/data/company-research/manifest.json','/data/company-research/documents/original.json']) {
    assert.equal(accessDecision(path,'GET',null),'unauthenticated');
    assert.equal(accessDecision(path,'GET',{role:'owner'}),'allow');
  }
  assert.equal(accessDecision('/fund-letters/','GET',reader),'allow');
  assert.equal(accessDecision('/api/fund-letters','GET',reader),'allow');
  assert.equal(accessDecision('/','GET',reader),'reader-home');
  assert.equal(accessDecision('/fund-letters/','GET',null),'unauthenticated');
  assert.equal(accessDecision('/api/v2/portfolio/ingest','GET',null),'unauthenticated');
  assert.equal(accessDecision('/api/v2/portfolio/ingest','POST',null),'machine');
  assert.equal(accessDecision('/api/v2/portfolio/ingest/guessed','POST',null),'unauthenticated');
});
test('middleware denies before reading and prevents role-dependent cache reuse',async()=>{
  let calls=0;
  const base={request:new Request('https://preview.pages.dev/data/core.json'),env:{},data:{humanViewer:reader},next:async()=>{calls++;return new Response('private body',{headers:{'cache-control':'public,max-age=3600'}});}};
  assert.equal((await onRequest(base)).status,403);assert.equal(calls,0);
  base.data.humanViewer=owner;
  const response=await onRequest(base);assert.equal(await response.text(),'private body');assert.equal(response.headers.get('cache-control'),'no-store, private');assert.equal(response.headers.get('cdn-cache-control'),'no-store');
  base.data.humanViewer=reader;
  assert.equal((await onRequest(base)).status,403);assert.equal(calls,1);
});
test('reader serializers strip unknown private fields without truncating summaries',()=>{
  const body='An original argument. '.repeat(1000);
  const value=readerLetter({id:'l',fund:'Fund',overview:body,source_url:'SECRET',raw_extract:'SECRET',evidence:'SECRET',drive_id:'SECRET'},[{id:'a',title:'Idea',summary:body,source_ref:'SECRET'}]);
  assert.equal(value.overview,body);assert.equal(value.ideas[0].summary,body);assert.equal(JSON.stringify(value).includes('SECRET'),false);
  assert.equal(readerIdea({summary:'https://drive.google.com/SECRET'}).summary,'');
});
test('the whole archive is reachable beyond eighty letters; search pins any dated idea',async()=>{
  const DB=database();seed(DB,105);let offset=0,total=0;
  do {const data=await (await onRequestGet(context({action:'letters',fund:'fund',offset:String(offset)},reader,DB))).json();total+=data.letters.length;offset=data.next_offset;}while(offset!==null);
  assert.equal(total,105);
  const result=await(await onRequestGet(context({action:'search',q:'ACME'},reader,DB))).json();assert.equal(result.results.length,20);assert.equal(result.next_offset,20);assert.equal(JSON.stringify(result).includes('SECRET'),false);
  const pinned=await(await onRequestGet(context({action:'letters',fund:'fund',letter:'l104'},reader,DB))).json();assert.equal(pinned.letters[0].id,'l104');
  const archive=await(await onRequestGet(context({action:'archive',fund:'fund'},reader,DB))).json();assert.equal(archive.letters.length,105);
});
test('drafts never enter reader search or fund counts; source/evidence/review require ownership',async()=>{
  const DB=database();seed(DB);DB.db.exec("UPDATE fl_letters SET published_revision=NULL");
  for(const action of ['source','document','original','draft','revisions','review']) assert.equal((await onRequestGet(context({action,letter:'l0'},reader,DB))).status,403);
  assert.deepEqual((await(await onRequestGet(context({action:'funds'},reader,DB))).json()).funds,[]);
  assert.deepEqual((await(await onRequestGet(context({action:'search',q:'Acme'},reader,DB))).json()).results,[]);
  const owned=await(await onRequestGet(context({action:'source',letter:'l0'},owner,DB))).json();assert.equal(owned.source.source_url,'https://drive.google.com/SECRET');
});

test('complete source text is owner-only and private R2 streams stay private',async()=>{
  const DB=database();seed(DB);
  const response=await onRequestGet(context({action:'document',letter:'l0'},owner,DB));
  assert.equal(await response.text(),source);assert.match(response.headers.get('cache-control'),/no-store/);assert.equal(response.headers.get('content-type'),'text/plain; charset=utf-8');
  DB.db.exec("UPDATE fl_letters SET source_text=''");
  const ctx=context({action:'document',letter:'l0'},owner,DB);let reads=0;
  ctx.env.PRIVATE_ARTIFACTS={async get(){reads++;return {body:new Response('full private R2 source').body};}};
  assert.equal(await(await onRequestGet(ctx)).text(),'full private R2 source');assert.equal(reads,1);
  ctx.data.humanViewer=reader;assert.equal((await onRequestGet(ctx)).status,403);assert.equal(reads,1);
  DB.db.exec("UPDATE fl_letters SET reporting_period='https://drive.google.com/SECRET'");
  assert.equal(JSON.stringify(await(await onRequestGet(context({action:'archive',fund:'fund'},reader,DB))).json()).includes('SECRET'),false);
});
test('owners read the original in-site, with a Drive link and preview; readers cannot',async()=>{
  const DB=database();seed(DB);
  DB.db.exec("UPDATE fl_letters SET source_url='https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp_q-r/view'");
  const data=await(await onRequestGet(context({action:'original',letter:'l0'},owner,DB))).json();
  assert.equal(data.text,source);assert.equal(data.letter.fund,'Test Fund');assert.equal(data.in_drive,true);
  assert.equal(data.original_url,'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp_q-r/view');
  assert.equal(data.preview_url,'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp_q-r/preview');
  assert.equal('content_hash' in data.letter||'source_ref' in data.letter,false);
  DB.db.exec("UPDATE fl_letters SET source_text='',source_url='javascript:alert(1)'");
  const ctx=context({action:'original',letter:'l0'},owner,DB);let reads=0;
  ctx.env.PRIVATE_ARTIFACTS={async get(key){reads++;assert.equal(key,'fund-letters/source/hash0.txt');return {size:24,async text(){return 'full private R2 source';}};}};
  const fallback=await(await onRequestGet(ctx)).json();
  assert.equal(fallback.text,'full private R2 source');assert.equal(fallback.original_url,null);assert.equal(fallback.preview_url,null);assert.equal(reads,1);
  ctx.env.PRIVATE_ARTIFACTS={async get(){return {size:30_000_000,async text(){throw new Error('must not load an oversized source');}};}};
  DB.db.exec("UPDATE fl_letters SET source_url='https://example.com/letter.pdf'");
  const linkOnly=await(await onRequestGet(ctx)).json();
  assert.equal(linkOnly.text,'');assert.equal(linkOnly.original_url,'https://example.com/letter.pdf');assert.equal(linkOnly.in_drive,false);
  ctx.data.humanViewer=reader;assert.equal((await onRequestGet(ctx)).status,403);
  assert.equal((await onRequestGet(context({action:'original',letter:'missing'},owner,DB))).status,404);
});
test('full text coverage, exact evidence, originality, numeric support and historical evolution are gated',()=>{
  assert.deepEqual(validateDraft(draft(),sourceSections(source)),[]);
  const missing=draft();missing.checklist=[];assert.ok(validateDraft(missing,sourceSections(source)).length);
  const copy=draft();copy.ideas[0].summary=source;assert.ok(validateDraft(copy,sourceSections(source)).some(e=>e.includes('copied')));
  const bad=draft();bad.ideas[0].summary+=' Target is 900.';assert.ok(validateDraft(bad,sourceSections(source)).some(e=>e.includes('900')));
  const long=source.repeat(100);assert.equal(sourceSections(long).map(p=>p.text).join(''),long);
});
test('years and labels are not numerical claims, and stance reaches readers without quotes',()=>{
  const dated=draft();dated.overview+=' Written in 2011 after QE2 ended.';
  assert.deepEqual(validateDraft(dated,sourceSections(source)),[]);
  const row={id:'l0',fund_id:'fund',fund:'Fund',reporting_period:'2011Q1',letter_date:null,publication_date:null,published_at:'x',created_at:'y',revision_id:'r1',overview:'Overview'};
  const letter=readerLetter(row,[{id:'i1',title:'Acme',ticker:null,idea_type:'long',activity:'new',summary:'Summary',evolution:null,compared_letter_id:null}],{focus:'macro',leaning_in:[{subject:'Equities',why:'Cash yields are low.',quote:'PRIVATE QUOTE'}],leaning_out:[{subject:'Cash',why:'Yields are low.',quote:'PRIVATE QUOTE 2'}]},'Macro tilt towards equities.');
  assert.equal(letter.stance.focus,'macro');
  assert.equal(letter.focus,'macro');
  assert.equal(letter.headline,'Macro tilt towards equities.');
  assert.equal(readerLetter(row,[],null,'https://drive.google.com/SECRET').headline,null);
  assert.deepEqual(letter.stance.leaning_in,[{subject:'Equities',why:'Cash yields are low.'}]);
  assert.equal(JSON.stringify(letter).includes('PRIVATE QUOTE'),false);
});
test('cross-fund letters feed, period catalog, and category/activity filters return allowlisted summaries',async()=>{
  const DB=database();seed(DB,3);
  DB.db.exec("UPDATE fl_revisions SET content_json='{\"headline\":\"Headline for l0\",\"stance\":{\"focus\":\"micro\"}}' WHERE id='r0'");
  DB.db.exec("UPDATE fl_ideas SET activity='new' WHERE revision_id='r0'");
  const catalog=await(await onRequestGet(context({action:'funds'},reader,DB))).json();
  assert.deepEqual(catalog.periods,[{period:'2020Q1',count:3}]);
  const allLetters=await(await onRequestGet(context({action:'letters'},reader,DB))).json();
  assert.equal(allLetters.letters.length,3);
  assert.equal(allLetters.letters[0].headline,'Headline for l0');
  assert.equal(allLetters.letters[0].focus,'micro');
  assert.equal(JSON.stringify(allLetters).includes('SECRET'),false);
  const byAct=await(await onRequestGet(context({action:'letters',activity:'new,add',period:'2020',type:'long,short'},reader,DB))).json();
  assert.equal(byAct.letters.length,1);
  assert.equal(byAct.letters[0].id,'l0');
  const searchByAct=await(await onRequestGet(context({action:'search',activity:'new,add',period:'2020Q1',type:'long,short'},reader,DB))).json();
  assert.equal(searchByAct.results.length,1);
});
test('smart search tokens, multi-fund overlap, battleground signals, and owner portfolio scope work without leaking to readers',async()=>{
  const DB=database();seed(DB,2);
  DB.db.exec("INSERT INTO fl_funds(id,name) VALUES('bear-fund','Bear Fund');");
  DB.db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,ingested_at,source_ref,source_url,source_text,published_revision) VALUES(?,?,?,?,?,?,?,?,?,?)').run('lbear','bear-fund','hbear','v1','2020Q2','2026-10-23','private/path','https://drive.google.com/SECRET',source,'rbear');
  DB.db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?)').run('rbear','lbear','2026-10-23','editor','published','Bearish view on Acme.','{"stance":{"focus":"macro"}}','{}');
  DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)').run('acme-short','rbear','lbear','Acme short thesis','ACME','short','short','Acme faces competitive pressure.',0);

  const parsed = parseSearchTokens('ticker:ACME,MSFT type:short action:new focus:macro is:battleground recurring');
  assert.deepEqual(parsed.tickers, ['ACME', 'MSFT']);
  assert.deepEqual(parsed.types, ['short']);
  assert.deepEqual(parsed.activities, ['new']);
  assert.deepEqual(parsed.focuses, ['macro']);
  assert.deepEqual(parsed.signals, ['battleground']);
  assert.equal(parsed.freeText, 'recurring');

  const catalog = await (await onRequestGet(context({action:'funds'},reader,DB))).json();
  assert.equal(catalog.tickers.length, 1);
  assert.equal(catalog.tickers[0].ticker, 'ACME');
  assert.equal(catalog.tickers[0].fund_count, 2);
  assert.equal(catalog.tickers[0].multi_fund, true);
  assert.equal(catalog.tickers[0].battleground, true);

  const battleIdeas = await (await onRequestGet(context({action:'search',signal:'battleground'},reader,DB))).json();
  assert.equal(battleIdeas.results.length, 3);
  const macroLetters = await (await onRequestGet(context({action:'letters',q:'focus:macro is:multi ticker:ACME'},reader,DB))).json();
  assert.equal(macroLetters.letters.length, 1);
  assert.equal(macroLetters.letters[0].id, 'lbear');

  DB.db.exec("CREATE TABLE portfolio_positions (symbol TEXT, position REAL); INSERT INTO portfolio_positions VALUES ('ACME', 100);");
  const readerSession = await (await onRequestGet(context({action:'session'},reader,DB))).json();
  assert.equal('book_tickers' in readerSession, false);
  const ownerSession = await (await onRequestGet(context({action:'session'},owner,DB))).json();
  assert.deepEqual(ownerSession.book_tickers, ['ACME']);
});
test('owner edits create revisions and publication requires six explicit attestations',async()=>{
  const DB=database();seed(DB);
  async function post(payload,viewer=owner,origin='https://test.example') {
    const ctx=context({},viewer,DB);ctx.request=new Request(ctx.request.url,{method:'POST',headers:{'content-type':'application/json',origin},body:JSON.stringify(payload)});return onRequestPost(ctx);
  }
  assert.equal((await post({action:'draft',letter_id:'l0',draft:draft()},reader)).status,403);
  assert.equal((await post({action:'draft',letter_id:'l0',draft:draft()},owner,'https://evil.example')).status,403);
  const saved=await(await post({action:'draft',letter_id:'l0',draft:draft()})).json();assert.equal(saved.errors.length,0);
  assert.equal(DB.db.prepare('SELECT count(*) n FROM fl_revisions').get().n,2);
  assert.equal((await post({action:'publish',letter_id:'l0',revision_id:saved.revision_id,expected_revision:'r0'})).status,422);
  const attestations=Object.fromEntries(Object.keys({complete_document:1,idea_coverage:1,claim_accuracy:1,numerical_accuracy:1,original_writing:1,historical_dates:1}).map(k=>[k,true]));
  assert.equal((await post({action:'publish',letter_id:'l0',revision_id:saved.revision_id,expected_revision:'stale',attestations})).status,409);
  assert.equal((await post({action:'publish',letter_id:'l0',revision_id:saved.revision_id,expected_revision:'r0',attestations})).status,200);
  assert.equal(DB.db.prepare('SELECT published_revision FROM fl_letters').get().published_revision,saved.revision_id);
  assert.equal(DB.db.prepare('SELECT count(*) n FROM fl_revisions').get().n,2);
});
