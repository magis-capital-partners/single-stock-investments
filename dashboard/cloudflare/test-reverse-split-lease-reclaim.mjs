import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,rmSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {localAdapter} from './reverse-split-live/checkpoint.mjs';
import {claimCollectorLease,readReclaimOwner,recordOwner} from './reverse-split-live/collector-lease.mjs';
function database(t){const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE rs_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)');t.after(()=>db.close());return db;}
const leaseValue=db=>db.prepare("SELECT value FROM rs_state WHERE key='collector_lease'").get().value;

test('a restarted collector retakes its own predecessor lease without waiting for expiry',async t=>{
  const db=database(t);db.prepare("INSERT INTO rs_state VALUES('collector_lease','999999:dead-predecessor','now')").run();
  let slept=0;const result=await claimCollectorLease(localAdapter(db),{owner:'successor',reclaimOwner:'dead-predecessor',waitMs:600000,clock:()=>1000,sleep:async()=>{slept++;}});
  assert.ok(result);assert.equal(slept,0);assert.equal(result.attempts,0);assert.equal(leaseValue(db),'601000:successor');
});

test('a reclaim id never displaces a different unexpired owner',async t=>{
  const db=database(t);db.prepare("INSERT INTO rs_state VALUES('collector_lease','999999:github-runner','now')").run();
  let now=0;const result=await claimCollectorLease(localAdapter(db),{owner:'box',reclaimOwner:'old-box',waitMs:10000,clock:()=>now,sleep:async ms=>{now+=ms;}});
  assert.equal(result,null);assert.equal(leaseValue(db),'999999:github-runner');
});

test('the displaced predecessor can neither renew nor keep writing',async t=>{
  const db=database(t),remote=localAdapter(db);db.prepare("INSERT INTO rs_state VALUES('collector_lease','999999:old','now')").run();
  await claimCollectorLease(remote,{owner:'new',reclaimOwner:'old',clock:()=>1000});
  const renewed=await remote.prepare("UPDATE rs_state SET value=?,updated_at=? WHERE key='collector_lease' AND value=? RETURNING value").bind('1999999:old','now','999999:old').first();
  assert.equal(renewed,null);assert.match(leaseValue(db),/:new$/);
});

test('malformed, empty or self reclaim ids fall back to the ordinary expiry rule',async t=>{
  for(const reclaimOwner of ["x' OR 1=1 --",'','successor',null,'a:b','z'.repeat(65)]){
    const db=database(t);db.prepare("INSERT INTO rs_state VALUES('collector_lease','999999:other','now')").run();
    const result=await claimCollectorLease(localAdapter(db),{owner:'successor',reclaimOwner,clock:()=>1000});
    assert.equal(result,null,String(reclaimOwner));assert.equal(leaseValue(db),'999999:other');
  }
});

test('an expired lease is still claimable with or without a reclaim id',async t=>{
  const db=database(t);db.prepare("INSERT INTO rs_state VALUES('collector_lease','500:anyone','now')").run();
  assert.ok(await claimCollectorLease(localAdapter(db),{owner:'fresh',reclaimOwner:'unrelated',clock:()=>1000}));assert.match(leaseValue(db),/:fresh$/);
});

test('the owner file round-trips and tolerates a missing or corrupt file',t=>{
  const dir=mkdtempSync(join(tmpdir(),'rs-owner-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));const file=join(dir,'owner');
  assert.equal(readReclaimOwner(undefined),null);assert.equal(readReclaimOwner(file),null);
  assert.equal(recordOwner(file,'6f1c2d3e-0000-4000-8000-000000000001'),true);assert.equal(readReclaimOwner(file),'6f1c2d3e-0000-4000-8000-000000000001');
  assert.equal(recordOwner(file,'bad:owner'),false);assert.equal(readFileSync(file,'utf8').trim(),'6f1c2d3e-0000-4000-8000-000000000001');
  writeFileSync(file,"x' OR 1=1");assert.equal(readReclaimOwner(file),null);
  assert.equal(recordOwner(undefined,'abc'),false);
});
