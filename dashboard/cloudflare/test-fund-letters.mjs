import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { humanRole, requireHumanViewer, viewerFromAccessPayload } from '../functions/_lib/auth.js';
import { accessDecision, onRequest } from '../functions/_middleware.js';
import { nearDuplicate, parseSearchTokens, readerExtras, readerIdea, readerLetter, sourceSections, validateDraft } from '../functions/_lib/fund-letters.js';
import { onRequestGet, onRequestPost } from '../functions/api/fund-letters.js';

function database() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./migrations/0023_fund_letters.sql',import.meta.url),'utf8'));
  db.exec(readFileSync(new URL('./migrations/0026_fund_letter_entities.sql',import.meta.url),'utf8'));
  // Exercise production SQL, rather than maintaining query-specific mocked answers.
  const prepare = sql => ({ bind(...args) { return { async all() {return {results:db.prepare(sql).all(...args)};}, async first() {return db.prepare(sql).get(...args)||null;}, async run() {return {meta:{changes:db.prepare(sql).run(...args).changes}};} }; } });
  return { db, prepare, async batch(stmts) {db.exec('BEGIN');try{const rows=[];for(const stmt of stmts)rows.push(await stmt.run());db.exec('COMMIT');return rows;}catch(error){db.exec('ROLLBACK');throw error;}} };
}
const owner = {email:'drew@magiscapitalpartners.com',role:'owner'};
const reader = {email:'reader@example.com',role:'reader'};
const context = (query,viewer=reader,DB=database()) => ({request:new Request('https://test.example/api/fund-letters?'+new URLSearchParams(query)),env:{DB},data:{humanViewer:viewer}});
const source = 'Acme earns subscription income from its customers. Revenue increased 20% this year. Management expects renewals to remain strong. Customer losses are a risk.';
const draft = () => ({overview:'The manager examines an opportunity in recurring customer payments.',ideas:[{id:'acme',title:'Acme subscriptions',ticker:'ACME',idea_type:'long',summary:'The fund argues that customer payments create attractive recurring economics. It reports revenue growth of 20% and identifies customer retention as an uncertainty.',evidence:[{claim:'Economics, growth and risk',section_id:'s1',quote:source}]}],checklist:[{section_id:'s1',idea_ids:['acme'],disposition:'covered',reason:'Acme economics and risks summarized.'}]});

// The pipeline's resolver reduced to fixtures: each mention in an idea's ticker text is one resolved security
// unless the test marks it 'unresolved' or 'dropped'. Rows sit under resolver 'test-1', which fl_settings names.
function resolveTickers(DB, status = {}) {
  DB.db.exec("INSERT OR IGNORE INTO fl_settings(key,value) VALUES('entity_resolver','test-1'),('idea_themes','test-1')");
  const insert = DB.db.prepare("INSERT OR IGNORE INTO fl_idea_entities(resolver,revision_id,idea_id,ordinal,mention,ticker,status) VALUES('test-1',?,?,?,?,?,?)");
  for (const row of DB.db.prepare("SELECT revision_id,id,ticker FROM fl_ideas WHERE TRIM(COALESCE(ticker,''))!=''").all()) {
    row.ticker.split(',').map(part => part.trim()).forEach((mention, ordinal) => {
      const state = status[`${row.id}:${mention}`] ?? status[mention] ?? 'resolved';
      if (state !== 'dropped') insert.run(row.revision_id, row.id, ordinal, mention, state === 'resolved' ? mention : null, state);
    });
  }
}

function seed(DB,count=1) {
  DB.db.exec("INSERT INTO fl_funds(id,name) VALUES('fund','Test Fund');");
  for(let i=0;i<count;i++) {
    DB.db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,ingested_at,source_ref,source_url,source_text,published_revision) VALUES(?,?,?,?,?,?,?,?,?,?)').run('l'+i,'fund','hash'+i,'v1','2020Q1','2026-10-23','private/path','https://drive.google.com/SECRET',source,'r'+i);
    DB.db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?)').run('r'+i,'l'+i,'2026-10-23','editor','published',draft().overview,JSON.stringify(draft()),'{}');
    DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,summary,ordinal) VALUES(?,?,?,?,?,?,?,?)').run('acme','r'+i,'l'+i,'Acme subscriptions','ACME','long',draft().ideas[0].summary,0);
  }
  resolveTickers(DB);
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
test('a transcribed table is gated on its source and reaches readers without its quote',()=>{
  const quote='Fund results Q3 2011 YTD Net Performance \u2010 3.83% 1.14% Benchmark 2.10% 4.00%';
  const letterText=source+' '+quote;
  const parts=sourceSections(letterText);
  const tabled=()=>({...draft(),tables:[{idea_id:null,section_id:'s1',quote,title:'Fund results',columns:['Q3 2011','YTD'],rows:[{label:'Net Performance',values:['-3.83%','1.14%']},{label:'Benchmark',values:['2.10%','4.00%']}]}]});
  assert.deepEqual(validateDraft(tabled(),parts),[]);
  const sign=tabled();sign.tables[0].rows[1].values[0]='-2.10%';
  assert.ok(validateDraft(sign,parts).some(e=>e.includes('shown as negative but is not printed so')));
  const invented=tabled();invented.tables[0].rows[0].values[1]='11.14%';
  assert.ok(validateDraft(invented,parts).some(e=>e.includes('Table numerical claim 11.14% lacks cited evidence')));
  const short=tabled();short.tables[0].rows[0].values.pop();
  assert.ok(validateDraft(short,parts).some(e=>e.includes('one value under every heading')));
  const moved=tabled();moved.tables[0].quote='Fund results Q3 2011 YTD Net Performance 9.99%';
  assert.ok(validateDraft(moved,parts).some(e=>e.includes('Table evidence must match its source passage exactly')));
  const orphan=tabled();orphan.tables[0].idea_id='no-such-idea';
  assert.ok(validateDraft(orphan,parts).length);
  // A figure in the overview may rest on a table the letter prints.
  const cited=tabled();cited.overview+=' The benchmark returned 4.00% for the year to date.';
  assert.deepEqual(validateDraft(cited,parts),[]);

  const stored={...tabled(),coverage:{sections:1,sections_cited:1,topics:1,statements:2,tables:1,tables_omitted:2,figures:4,source_words:40,summary_words:30,secret:'SECRET'}};
  stored.ideas[0].cites=['s1','s1'];
  stored.tables[0].source_url='SECRET';stored.tables.push({columns:['Only one'],rows:[{label:'x',values:['1']}]});
  const row={id:'l0',fund_id:'fund',fund:'Fund',reporting_period:'2011Q3',letter_date:null,publication_date:null,published_at:'x',created_at:'y',revision_id:'r1',overview:'Overview'};
  const letter=readerLetter(row,[{id:'acme',title:'Acme',ticker:null,idea_type:'long',activity:'new',summary:'One.\nTwo.',evolution:null,compared_letter_id:null}],null,'Headline',readerExtras(stored));
  assert.deepEqual(letter.tables,[{index:0,idea_id:null,passage:1,title:'Fund results',columns:['Q3 2011','YTD'],rows:[{label:'Net Performance',values:['-3.83%','1.14%']},{label:'Benchmark',values:['2.10%','4.00%']}]}]);
  assert.deepEqual(letter.coverage,{sections:1,sections_cited:1,topics:1,statements:2,tables:1,tables_omitted:2,figures:4,source_words:40,summary_words:30});
  assert.deepEqual(letter.ideas[0].cites,[1,1]);
  assert.equal(JSON.stringify(letter).includes('SECRET'),false);
  assert.equal(JSON.stringify(letter).includes('Net Performance \u2010'),false);
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
  resolveTickers(DB);

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

// The reader's shared workspace state, run from the shipped file so the URL contract is the one users get.
function readerState() {
  const sandbox = { URLSearchParams, document: { getElementById: () => null } };
  sandbox.window = sandbox;
  vm.runInNewContext(readFileSync(new URL('../fund-letters/reader.js', import.meta.url), 'utf8'), sandbox);
  return sandbox.FundLettersReader.state;
}
test('workspace state round-trips through the URL, keeps links stable and upgrades older links', () => {
  const { readState, writeState, statements, emptiedReason } = readerState();
  const state = readState('view=ideas&period=2012q1&q=rambus&f=first,new,bogus&fund=tiger&ticker=rmbs&type=long');
  assert.equal(state.view, 'ideas');
  assert.equal(state.period, '2012Q1');
  assert.deepEqual([...state.chips], ['new', 'first']);
  assert.equal(state.ticker, 'RMBS');
  const link = writeState(state);
  assert.equal(link, 'view=ideas&period=2012Q1&q=rambus&f=new%2Cfirst&fund=tiger&ticker=RMBS&type=long');
  assert.deepEqual(JSON.parse(JSON.stringify(readState(link))), JSON.parse(JSON.stringify(state)));
  // Defaults stay out of links, so the latest quarter and the By fund view are implied.
  assert.equal(writeState(readState('')), '');
  assert.equal(writeState(readState('view=funds&period=all')), 'period=all');
  assert.equal(readState('period=2012Q5').period, '');
  assert.equal(readState('ticker=GLUU, TMRK').ticker, '');
  assert.deepEqual([readState('view=ticker&ticker=beta').view, writeState(readState('view=ticker&ticker=beta'))], ['ticker', 'view=ticker&ticker=BETA']);
  // Links written before the workspace still open the same filters.
  const legacy = readState('view=letters&activity=trim,cover&scope=book&tickers=AAPL,MSFT');
  assert.equal(legacy.view, 'funds');
  assert.deepEqual([...legacy.chips], ['trim', 'exit', 'book']);
  assert.equal(legacy.ticker, 'AAPL');
  assert.deepEqual([...statements('One line.\nSecond line.\n\nThird line.')], ['One line.', 'Second line.', 'Third line.']);
  assert.deepEqual([...statements('The fund bought Acme. It trimmed Beta (BETA). 3.5% of NAV.')], ['The fund bought Acme.', 'It trimmed Beta (BETA).', '3.5% of NAV.']);
  assert.equal(emptiedReason([{ key: 'period', label: 'Quarter 2020Q2', count: 5 }, { key: 'first', label: 'First mentioned this quarter', count: 0 }]).key, 'first');
  assert.equal(emptiedReason([{ key: 'period', label: 'Quarter 2020Q2', count: 5 }, { key: 'first', label: 'First mentioned this quarter', count: 0 }]).before, 5);
  assert.equal(emptiedReason([{ key: 'period', count: 5 }]), null);
});

// Fund A writes in 2020Q1 and 2020Q2; fund B's first letter is 2020Q2.
function workspaceArchive() {
  const DB = database();
  DB.db.exec("INSERT INTO fl_funds(id,name) VALUES('a','Alpha Fund'),('b','Beta Fund');");
  const letter = (id, fund, period, date) => {
    DB.db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,letter_date,ingested_at,source_ref,source_url,source_text,published_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?)')
      .run(id, fund, 'h-' + id, 'v1', period, date, '2026-10-23', 'private/path', 'https://drive.google.com/SECRET', source, 'r-' + id);
    DB.db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?)')
      .run('r-' + id, id, '2026-10-23', 'editor', 'published', 'Overview of ' + id, '{}', '{}');
  };
  const idea = (letterId, id, ticker, type, activity, ordinal) => DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)')
    .run(id, 'r-' + letterId, letterId, `${ticker} thesis`, ticker, type, activity, `The fund discusses ${ticker} in ${letterId}.\nA second statement.`, ordinal);
  letter('a1', 'a', '2020Q1', '2020-04-15');
  idea('a1', 'acme', 'ACME', 'long', 'hold', 0);
  idea('a1', 'delta-table', 'DELTA', 'factual_note', 'hold', 1);
  letter('a2', 'a', '2020Q2', null);
  idea('a2', 'acme', 'ACME', 'long', 'add', 0);
  idea('a2', 'beta', 'BETA', 'long', 'new', 1);
  idea('a2', 'gamma', 'GAMMA', 'update', 'hold', 2);
  idea('a2', 'delta', 'DELTA', 'long', 'new', 3);
  letter('b2', 'b', '2020Q2', '2020-07-20');
  idea('b2', 'beta-short', 'BETA', 'short', 'short', 0);
  resolveTickers(DB);
  return DB;
}
const ids = body => body.results.map(r => `${r.fund_id}:${r.ticker}`).sort();

test('position activity and first mention are separate filters: OR within a group, AND across groups', async () => {
  const DB = workspaceArchive();
  const get = async query => (await onRequestGet(context(query, reader, DB))).json();
  const workspace = await get({ action: 'workspace' });
  assert.equal(workspace.period, '2020Q2');
  assert.deepEqual(workspace.periods, [{ period: '2020Q2', count: 2 }, { period: '2020Q1', count: 1 }]);
  // Holdings-table mentions are not discussions.
  assert.deepEqual(workspace.funds.map(f => [f.id, f.discussions, f.letter_date]), [['a', 4, null], ['b', 1, '2020-07-20']]);
  assert.deepEqual(workspace.totals, { funds: 2, letters: 2, discussions: 5, unresolved: 0 });

  // New position: what the fund opened, whether or not it named the company before.
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'new' })), ['a:BETA', 'a:DELTA']);
  // First mentioned: never named in an earlier quarter of the same fund, whatever the activity. DELTA was in a
  // holdings table, and fund B has no earlier letter to compare against.
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'first' })), ['a:BETA', 'a:GAMMA']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'new,first' })), ['a:BETA']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'new,add' })), ['a:ACME', 'a:BETA', 'a:DELTA']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'short' })), ['b:BETA']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'new', q: 'delta' })), ['a:DELTA']);
  const flagged = await get({ action: 'ideas', period: '2020Q2' });
  assert.deepEqual(flagged.results.filter(r => r.first_mentioned).map(r => r.ticker).sort(), ['BETA', 'GAMMA']);

  // Each fund counts once on the overlap strip, with its direction.
  assert.deepEqual(workspace.overlap, [{ ticker: 'BETA', name: null, funds: 2, letters: 2, managers: 2, long: 1, short: 1 }]);
  const narrowed = await get({ action: 'workspace', f: 'new' });
  assert.deepEqual(narrowed.funds.map(f => [f.id, f.discussions]), [['a', 2]]);
  assert.deepEqual(narrowed.overlap, []);
});

test('the workspace explains empty results, compares with the fund\'s last discussion and highlights matches in the letter', async () => {
  const DB = workspaceArchive();
  const get = async (query, viewer = reader) => (await onRequestGet(context(query, viewer, DB))).json();
  const empty = await get({ action: 'workspace', q: 'zzz' });
  assert.deepEqual(empty.emptied_by, [{ key: 'period', label: 'Quarter 2020Q2', count: 5 }, { key: 'search', label: 'Search "zzz"', count: 0 }]);
  const book = await get({ action: 'ideas', period: '2020Q2', f: 'book,first' });
  assert.deepEqual(book.results, []);
  assert.equal(book.emptied_by.find(step => !step.count).key, 'book');
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'book', book: 'GAMMA,ZZZZ' }, owner)), ['a:GAMMA']);

  const all = await get({ action: 'ideas', period: '2020Q2' });
  const acme = all.results.find(r => r.ticker === 'ACME');
  assert.deepEqual(acme.prior, { letter_id: 'a1', reporting_period: '2020Q1', letter_date: '2020-04-15', title: 'ACME thesis', idea_type: 'long', activity: 'hold', summary: 'The fund discusses ACME in a1.\nA second statement.' });
  assert.equal(all.results.find(r => r.ticker === 'DELTA').prior, null);
  assert.deepEqual(Object.keys(acme).sort(), ['activity', 'compared_letter_id', 'evolution', 'first_mentioned', 'fund', 'fund_id', 'id', 'idea_type', 'letter_date', 'letter_id', 'managers', 'prior', 'reporting_period', 'summary', 'themes', 'ticker', 'tickers', 'title', 'unresolved']);
  assert.equal(JSON.stringify(all).includes('SECRET'), false);
  assert.equal(JSON.stringify(all).includes('private/path'), false);

  const pane = await get({ action: 'letters', fund: 'a', period: '2020Q2', f: 'new' });
  assert.deepEqual(pane.letters.map(l => l.id), ['a2']);
  assert.deepEqual(pane.letters[0].ideas.map(i => [i.ticker, i.matches, i.first_mentioned, i.prior?.reporting_period || null]),
    [['ACME', false, false, '2020Q1'], ['BETA', true, true, null], ['GAMMA', false, true, null], ['DELTA', true, false, null]]);
  const unfiltered = await get({ action: 'letters', fund: 'a', period: '2020Q2' });
  assert.equal(unfiltered.letters[0].ideas.some(i => 'matches' in i), false);
  assert.deepEqual((await get({ action: 'letters', fund: 'a', period: 'all' })).letters.map(l => l.id), ['a2', 'a1']);
  const archive = await get({ action: 'archive', fund: 'a' });
  assert.equal(archive.fund_name, 'Alpha Fund');
});

test('long ticker lists stay within the D1 bound-parameter limit', async () => {
  const DB = workspaceArchive();
  let most = 0;
  const counting = { ...DB, prepare: sql => { const statement = DB.prepare(sql); return { bind: (...args) => { most = Math.max(most, args.length); return statement.bind(...args); } }; } };
  const many = Array.from({ length: 250 }, (_, n) => `T${n}`).join(',');
  for (const query of [{ action: 'workspace', f: 'book', book: many + ',BETA' }, { action: 'ideas', f: 'book', book: many }, { action: 'letters', tickers: many }, { action: 'search', tickers: many + ',BETA' }]) {
    const response = await onRequestGet(context(query, owner, counting));
    assert.equal(response.status, 200, JSON.stringify(query).slice(0, 40));
  }
  assert.ok(most > 0 && most < 100, `largest bind was ${most} parameters`);
});

test('only resolved securities are matched or counted; unresolved mentions show on the card and in a separate count', async () => {
  const DB = workspaceArchive();
  const get = async (query, viewer = reader) => (await onRequestGet(context(query, viewer, DB))).json();
  const add = (letterId, id, ticker, type, activity, ordinal) => DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)')
    .run(id, 'r-' + letterId, letterId, `${id} thesis`, ticker, type, activity, `The fund discusses ${id}.`, ordinal);
  // Both funds write FCF, which the resolver drops as an acronym. Fund B's "ACME" is a different company.
  add('a2', 'cash', 'FCF', 'long', 'hold', 4);
  add('b2', 'cash-b', 'FCF', 'long', 'hold', 1);
  add('b2', 'acme-other', 'ACME', 'long', 'new', 2);
  add('a2', 'pair', 'ACME, ZETA', 'long', 'new', 5);
  resolveTickers(DB, { FCF: 'dropped', 'acme-other:ACME': 'unresolved' });
  // An older resolver that did count FCF no longer matters once the pointer has moved on.
  DB.db.exec("INSERT INTO fl_idea_entities(resolver,revision_id,idea_id,ordinal,mention,ticker,status) VALUES('test-0','r-a2','cash',0,'FCF','FCF','resolved'),('test-0','r-b2','cash-b',0,'FCF','FCF','resolved')");

  const workspace = await get({ action: 'workspace' });
  assert.deepEqual(workspace.overlap.map(row => row.ticker), ['BETA']);
  assert.equal(workspace.totals.unresolved, 1);
  assert.deepEqual(await get({ action: 'ideas', period: '2020Q2', ticker: 'FCF' }).then(body => body.results), []);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', ticker: 'ACME' })), ['a:ACME', 'a:ACME, ZETA']);
  const card = (await get({ action: 'ideas', period: '2020Q2' })).results.find(row => row.id === 'acme-other');
  assert.deepEqual([card.ticker, card.tickers, card.unresolved], ['', [], ['ACME']]);
  const catalog = await get({ action: 'funds' });
  assert.equal(catalog.tickers.some(row => row.ticker === 'FCF'), false);
  assert.equal(catalog.tickers.find(row => row.ticker === 'ACME').fund_count, 1);
  // A first mention is any resolved security the fund has not named before: ZETA, alongside the familiar ACME.
  const pair = (await get({ action: 'ideas', period: '2020Q2', f: 'first' })).results.map(row => row.id).sort();
  assert.deepEqual(pair, ['beta', 'gamma', 'pair']);
});

test('theme chips use the current theme set only, OR within the group and AND with the others', async () => {
  const DB = workspaceArchive();
  const get = async query => (await onRequestGet(context(query, reader, DB))).json();
  DB.db.exec("INSERT INTO fl_idea_themes(theme_set,revision_id,idea_id,theme) VALUES('test-1','r-a2','acme','quality'),('test-1','r-a2','delta','ma'),('test-0','r-a2','beta','ma')");
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'quality' })), ['a:ACME']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'ma' })), ['a:DELTA']);
  assert.deepEqual(ids(await get({ action: 'ideas', period: '2020Q2', f: 'quality,ma' })), ['a:ACME', 'a:DELTA']);
  const empty = await get({ action: 'ideas', period: '2020Q2', f: 'quality,new' });
  assert.deepEqual(empty.results, []);
  assert.equal(empty.emptied_by.find(step => !step.count).key, 'theme');
  const acme = (await get({ action: 'ideas', period: '2020Q2' })).results.find(row => row.id === 'acme');
  assert.deepEqual(acme.themes, ['quality']);
  const pane = await get({ action: 'letters', fund: 'a', period: '2020Q2', f: 'ma' });
  assert.deepEqual(pane.letters[0].ideas.filter(idea => idea.matches).map(idea => idea.id), ['delta']);
});

// BETA in 2020Q2: fund A long twice, B short, C long, D publishing C's letter in other words, E selling out;
// and fund A watching it in 2020Q1.
function companyArchive() {
  const DB = workspaceArchive();
  DB.db.exec("INSERT INTO fl_funds(id,name) VALUES('c','Gamma Partners'),('d','Gamma Feeder'),('e','Echo Capital');");
  const letter = (id, fund, period, date) => {
    DB.db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,letter_date,ingested_at,source_ref,source_url,source_text,published_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?)')
      .run(id, fund, 'h-' + id, 'v1', period, date, '2026-10-23', 'private/path', 'https://drive.google.com/SECRET', source, 'r-' + id);
    DB.db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?)')
      .run('r-' + id, id, '2026-10-23', 'editor', 'published', 'Overview of ' + id, '{}', '{}');
  };
  const idea = (letterId, id, type, activity, ordinal, summary, quotes = []) => {
    DB.db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)')
      .run(id, 'r-' + letterId, letterId, 'Beta Corp', 'BETA', type, activity, summary, ordinal);
    if (quotes.length) DB.db.prepare('INSERT INTO fl_evidence(revision_id,idea_id,claims_json) VALUES(?,?,?)')
      .run('r-' + letterId, id, JSON.stringify(quotes.map(quote => ({ claim: 'Beta', quote, section_id: 's1' }))));
  };
  const shared = ['Beta raised prices four times without losing a single large customer this year.', 'We think margins at Beta can double over the next three years as contracts reprice.'];
  idea('a2', 'beta-again', 'long', 'hold', 4, 'The fund also discusses Beta management changes.\nA new chief executive started in June.');
  letter('c2', 'c', '2020Q2', '2020-07-10');
  idea('c2', 'beta-c', 'long', 'new', 0, 'The fund bought Beta for its pricing power.\nIt expects margins to double as contracts reprice.', shared);
  letter('d2', 'd', '2020Q2', '2020-07-11');
  idea('d2', 'beta-d', 'long', 'new', 0, 'Beta was purchased because of pricing power with large customers.\nThe manager sees margins doubling over three years.', [...shared, 'The feeder fund invests alongside the master fund.']);
  letter('e2', 'e', '2020Q2', '2020-07-12');
  idea('e2', 'beta-e', 'long', 'exit', 0, 'The fund sold its Beta position after the stock doubled.\nValuation no longer left a margin of safety.');
  idea('a1', 'beta-early', 'sector', 'watch', 2, 'The fund is watching Beta as competitors cut prices.');
  resolveTickers(DB);
  return DB;
}

test('near-identical arguments are told apart from independent ones by shared quotes or wording', () => {
  const quotes = text => JSON.stringify([{ quote: text }]);
  const passage = 'Beta raised prices four times without losing a single large customer this year.';
  assert.equal(nearDuplicate({ summary: 'Beta has pricing power.', claims: quotes(passage) }, { summary: 'Pricing power at Beta is strong.', claims: quotes(passage) }), true);
  assert.equal(nearDuplicate({ summary: 'Beta has pricing power.', claims: quotes(passage) }, { summary: 'Pricing power at Beta is strong.', claims: quotes('Beta fell 20% after the company reported weaker orders in Europe.') }), false);
  const argument = 'The fund bought Beta because its pricing power lets it raise prices every year while customers keep renewing their contracts at higher rates.';
  assert.equal(nearDuplicate({ summary: argument }, { summary: argument.replace('The fund bought', 'The manager purchased') }), true);
  assert.equal(nearDuplicate({ summary: argument }, { summary: 'The fund is short Beta because customers are leaving for cheaper rivals and the balance sheet carries too much debt to compete.' }), false);
  // Short quotes and summaries carry too little to call two managers one.
  assert.equal(nearDuplicate({ summary: 'Beta.', claims: quotes('Beta rose.') }, { summary: 'Beta.', claims: quotes('Beta rose.') }), false);
});

test('the ticker view counts independent managers, collapses repeats and near-duplicates, and puts longs apart from shorts and sellers', async () => {
  const DB = companyArchive();
  const get = async query => (await onRequestGet(context(query, reader, DB))).json();
  const body = await get({ action: 'ticker', ticker: 'beta', period: '2020Q2' });
  assert.equal(body.ticker, 'BETA');
  assert.equal(body.current, '2020Q2');
  // Five funds wrote about BETA; Gamma Feeder republished Gamma Partners' argument, so four managers.
  assert.equal(body.managers, 4);
  const [quarter, earlier] = body.quarters;
  assert.equal(quarter.managers, 4);
  const side = key => quarter[key].map(entry => entry.idea.fund_id).sort();
  assert.deepEqual([side('long'), side('opposing'), side('other')], [['a', 'c'], ['b', 'e'], []]);
  assert.deepEqual(quarter.opposing.map(entry => entry.stance).sort(), ['sell', 'short']);
  const alpha = quarter.long.find(entry => entry.idea.fund_id === 'a');
  assert.deepEqual([alpha.idea.id, alpha.more.map(idea => idea.id)], ['beta', ['beta-again']]);
  const gamma = quarter.long.find(entry => entry.idea.fund_id === 'c');
  assert.deepEqual(gamma.also, [{ fund_id: 'd', fund: 'Gamma Feeder', letter_id: 'd2' }]);
  // Earlier quarters follow for context.
  assert.equal(earlier.period, '2020Q1');
  assert.deepEqual(earlier.other.map(entry => entry.idea.id), ['beta-early']);
  // Evidence quotes decide the collapse but never reach a reader.
  assert.equal(/claims|quote|Beta raised prices/.test(JSON.stringify(body)), false);

  // Filters narrow the chosen quarter; earlier quarters stay whole.
  const shorts = await get({ action: 'ticker', ticker: 'BETA', period: '2020Q2', f: 'short' });
  assert.equal(shorts.managers, 1);
  assert.deepEqual(shorts.quarters.map(q => [q.period, q.managers]), [['2020Q2', 1], ['2020Q1', 1]]);
  const none = await get({ action: 'ticker', ticker: 'BETA', period: '2020Q2', f: 'quality' });
  assert.equal(none.current, null);
  assert.equal(none.emptied_by.find(step => !step.count).key, 'theme');
  assert.deepEqual(none.quarters.map(q => q.period), ['2020Q1']);

  // The overview and the overlap strip use the same count.
  const overview = await get({ action: 'ticker', period: '2020Q2' });
  assert.deepEqual(overview.companies[0], { ticker: 'BETA', name: null, funds: 5, letters: 5, managers: 4, long: 3, short: 2 });
  const workspace = await get({ action: 'workspace', period: '2020Q2' });
  assert.deepEqual(workspace.overlap.map(row => [row.ticker, row.managers, row.funds]), [['BETA', 4, 5]]);
});

test('the ideas feed puts companies more independent managers discussed first, each company together, then the most recent', async () => {
  const DB = companyArchive();
  DB.db.exec("INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES('acme-b','r-b2','b2','Acme','ACME','long','new','Fund B buys Acme.',1)");
  resolveTickers(DB);
  const get = async query => (await onRequestGet(context(query, reader, DB))).json();
  const first = await get({ action: 'ideas', period: '2020Q2', limit: '5' });
  const second = await get({ action: 'ideas', period: '2020Q2', limit: '5', offset: String(first.next_offset) });
  const rows = [...first.results, ...second.results];
  assert.deepEqual(rows.map(row => [row.ticker, row.managers]).slice(0, 9), [
    ['BETA', 4], ['BETA', 4], ['BETA', 4], ['BETA', 4], ['BETA', 4], ['BETA', 4], ['ACME', 2], ['ACME', 2], ['GAMMA', 1],
  ]);
});

