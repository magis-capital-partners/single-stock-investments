import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {readSnapshotAPI} from './reverse-split-live/read-snapshot.mjs';
import {SHADOW_POLICIES} from './reverse-split-live/shadow-core.mjs';

// Mirrors the Nov 6 shape: every event enrolls a retrospective track under each policy.
function setup(t){
  const db=new DatabaseSync(':memory:');t.after(()=>db.close());
  for(const name of readdirSync(new URL('./reverse-split-live/migrations/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort())db.exec(readFileSync(new URL('./reverse-split-live/migrations/'+name,import.meta.url),'utf8'));
  const insert=db.prepare('INSERT INTO rs_shadow_tracks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'),tracks=[];
  for(let e=0;e<120;e++)for(const {id:policy} of SHADOW_POLICIES){
    // Paired events share an enrollment clock so the id tie-breaker is exercised across page boundaries.
    const enrolled_at=new Date(Date.UTC(2026,9,1)+Math.floor(e/2)*3600e3).toISOString(),track={id:policy+':event-'+e,event_id:'event-'+e,policy_id:policy,cik:String(1000+e),ticker:'T'+e,state:'retrospective',enrolled_at};
    insert.run(track.id,track.event_id,policy,track.cik,track.ticker,enrolled_at,null,null,'retrospective','r',enrolled_at,JSON.stringify(track));tracks.push(track);
  }
  const statements=[],DB={prepare(sql){const make=args=>({bind:(...v)=>make(v),all:async()=>{statements.push({sql,args});return {results:db.prepare(sql).all(...args)};}});return make([]);}};
  return {db,tracks,statements,env:{DB,EVIDENCE:{get:async()=>null}}};
}
async function pages(env,query){const ids=[];let cursor=null;do{const url=new URL('https://internal/shadow/tracks?'+query);if(cursor)url.searchParams.set('before',cursor);const body=await(await readSnapshotAPI(url,env)).json();ids.push(...body.tracks.map(t=>t.id));cursor=body.next_cursor;}while(cursor);return ids;}

test('retrospective track pages seek the policy index instead of sorting every retrospective track',async t=>{
  const {db,statements,env}=setup(t),policy=SHADOW_POLICIES[0].id;
  await pages(env,'policy='+encodeURIComponent(policy)+'&limit=50');
  assert.ok(statements.length>=3);
  for(const {sql,args} of statements){
    const plan=db.prepare('EXPLAIN QUERY PLAN '+sql).all(...args).map(r=>r.detail).join(' | ');
    assert.match(plan,/USING (?:COVERING )?INDEX rs_shadow_retrospective_page \(state=\? AND policy_id=\? AND enrolled_at<\?\)/,plan);
    assert.doesNotMatch(plan,/TEMP B-TREE/,plan);
  }
});

test('indexed retrospective paging returns exactly the policy tracks in enrollment order',async t=>{
  const {tracks,env}=setup(t),policy=SHADOW_POLICIES[3].id;
  const expected=tracks.filter(r=>r.policy_id===policy).sort((a,b)=>a.enrolled_at===b.enrolled_at?(a.id<b.id?-1:1):a.enrolled_at>b.enrolled_at?-1:1).map(r=>r.id);
  for(const limit of [1,7,50,100])assert.deepEqual(await pages(env,'policy='+encodeURIComponent(policy)+'&limit='+limit),expected,'limit '+limit);
  assert.deepEqual(await pages(env,'policy='+encodeURIComponent(policy)+'&q=T1&limit=9'),expected.filter(id=>/:event-1/.test(id)));
});
