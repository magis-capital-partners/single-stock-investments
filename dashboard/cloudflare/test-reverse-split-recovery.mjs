import test from 'node:test';
import assert from 'node:assert/strict';
import {recoverWatch} from './reverse-split-live/recovery.mjs';

test('a temporary startup failure retries within the original job deadline',async()=>{
  let now=0;const budgets=[],events=[];
  const result=await recoverWatch(async remaining=>{budgets.push(remaining);if(budgets.length===1){now+=45000;throw new Error('The operation was aborted due to timeout');}return {ticks:1};},{maximumMs:100000,clock:()=>now,pause:async ms=>{now+=ms;},report:e=>events.push(e)});
  assert.deepEqual(budgets,[100000,40000]);assert.equal(result.ticks,1);assert.equal(events[0].reason,'temporary_network_failure');
});
test('recovery is capped at three attempts and does not retry policy or credential failures',async()=>{
  let calls=0,now=0;
  await assert.rejects(recoverWatch(async()=>{calls++;throw new Error('Research storage HTTP 503');},{maximumMs:100000,clock:()=>now,pause:async ms=>{now+=ms;},report:()=>{}}),/503/);
  assert.equal(calls,3);assert.equal(now,45000);
  for(const message of ['Registered shadow policy changed; create a new version','Research storage HTTP 401']){calls=0;await assert.rejects(recoverWatch(async()=>{calls++;throw new Error(message);},{maximumMs:100000,pause:async()=>{},report:()=>{}}));assert.equal(calls,1);}
});
test('a late failure cannot reset the run budget and a competing lease is yielded',async()=>{
  let now=0,calls=0;
  await assert.rejects(recoverWatch(async()=>{calls++;now=95000;throw new Error('fetch failed');},{maximumMs:100000,clock:()=>now,pause:async()=>assert.fail('No time left for recovery'),report:()=>{}}));assert.equal(calls,1);
  const result=await recoverWatch(async()=>({skipped:true,reason:'Another collector owns the bounded lease'}),{maximumMs:1000,pause:async()=>assert.fail('Do not contend with a lease')});assert.equal(result.skipped,true);
});
test('a stop request during backoff prevents a new collector from starting',async()=>{
  let stop=false,calls=0;
  await assert.rejects(recoverWatch(async()=>{calls++;throw new Error('fetch failed');},{maximumMs:100000,shouldStop:()=>stop,pause:async()=>{stop=true;},report:()=>{}}),/stop requested/);assert.equal(calls,1);
});
