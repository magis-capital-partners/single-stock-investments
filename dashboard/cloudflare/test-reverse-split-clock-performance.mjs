import test from 'node:test';
import assert from 'node:assert/strict';
import {etDay} from './reverse-split-live/core.mjs';
import {at} from './reverse-split-live/shadow-core.mjs';
import {ALL_EXECUTION_POLICIES,BROAD_EXECUTION_POLICIES,matchedThresholdStudy} from './reverse-split-live/execution-core.mjs';

test('Eastern dates retain midnight and daylight-saving boundaries',()=>{
 for(const [clock,day] of [
  ['2026-03-08T04:59:59Z','2026-03-07'],['2026-03-08T05:00:00Z','2026-03-08'],
  ['2026-11-01T03:59:59Z','2026-10-31'],['2026-11-01T04:00:00Z','2026-11-01'],
  ['2026-11-02T04:59:59Z','2026-11-01'],['2026-11-02T05:00:00Z','2026-11-02'],
 ])assert.equal(etDay(clock),day);
 assert.throws(()=>etDay('invalid'),RangeError);
 assert.equal(at('1970-01-01T00:00:00Z'),0);
 assert.equal(at('invalid'),null);
});

test('matched cohort timestamp parsing grows with rows rather than policy comparisons',t=>{
 const start='2026-11-20T14:00:00Z',now='2026-11-20T15:00:00Z';
 const registrations=ALL_EXECUTION_POLICIES.map(p=>({id:p.id,registered_at:start}));
 const tracks=Array.from({length:256},(_,i)=>({id:String(i),policy_id:ALL_EXECUTION_POLICIES[i%ALL_EXECUTION_POLICIES.length].id,first_seen_at:'2026-11-20T14:30:00Z',state:'missed',entry_shares:0,cik:String(i)}));
 const parse=Date.parse;let calls=0;t.mock.method(Date,'parse',value=>{calls++;return parse(value);});
 const study=matchedThresholdStudy(tracks,registrations,now);
 assert.equal(study.length,BROAD_EXECUTION_POLICIES.length);
 assert.ok(calls<=tracks.length*2+registrations.length*4+20,`historical clocks were parsed ${calls} times for ${tracks.length} rows`);
});
