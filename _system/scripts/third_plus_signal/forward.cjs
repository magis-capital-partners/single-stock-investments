'use strict';
// Manual append-only shadow evidence. No network, broker SDK, scheduler or orders.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
function canonical(x){if(x===null||typeof x==='string'||typeof x==='boolean')return JSON.stringify(x);if(typeof x==='number'&&Number.isFinite(x))return JSON.stringify(x);if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';if(x&&typeof x==='object')return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';throw new Error('Nonfinite or non-JSON evidence');}
const hash=x=>crypto.createHash('sha256').update(canonical(x)).digest('hex');
const aware=s=>typeof s==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(s)&&Number.isFinite(Date.parse(s));
const positive=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
const KINDS=new Set(['enrollment','locate','order_attempt','fill','cashflow','loan_return','closure']);
const FORBIDDEN=new Set(['future_return','realized_return','outcomes','h20_return','next_reverse_split_2y','eventual_failure']);
function noFuture(x){if(!x||typeof x!=='object')return;for(const [k,v]of Object.entries(x)){if(FORBIDDEN.has(k))throw new Error('Outcome field in enrollment inputs: '+k);noFuture(v);}}
function load(file){
 if(!fs.existsSync(file))return [];
 const rows=fs.readFileSync(file,'utf8').split(/\r?\n/).filter(Boolean).map(JSON.parse);let previous=null;
 for(const row of rows){const {sha256,...body}=row;if(body.previous_sha256!==previous||hash(body)!==sha256)throw new Error('Shadow journal hash mismatch');previous=sha256;}return rows;
}
function validate(r,records,now=new Date().toISOString()){
 if(!KINDS.has(r.kind)||!r.event_id||!r.issuer_id||!aware(r.known_at)||Date.parse(r.known_at)>Date.parse(now))throw new Error('Invalid evidence identity, kind or public clock');
 if(!r.source_url?.startsWith('https://')||!r.locator||!/^[a-f0-9]{64}$/.test(r.source_sha256||''))throw new Error('Source/hash/locator required');
 const enrollment=records.find(x=>x.record.kind==='enrollment'&&x.record.event_id===r.event_id)?.record;
 if(r.kind==='enrollment'){
   if(enrollment)throw new Error('Enrollment is immutable');
   if(!aware(r.entry_at)||Date.parse(r.entry_at)<=Date.parse(now))throw new Error('Enrollment must precede future entry');
   if(!r.policy_snapshot||hash(r.policy_snapshot)!==r.policy_sha256||!r.input_snapshot||hash(r.input_snapshot)!==r.input_sha256)throw new Error('Frozen policy/input hash mismatch');
   if(r.policy_snapshot.production_authority!=='none'||r.policy_snapshot.research_only!==true)throw new Error('Only shadow policies permitted');
   if(!['observe','abstain'].includes(r.decision)||r.input_snapshot.event_id!==r.event_id||r.input_snapshot.issuer_id!==r.issuer_id)throw new Error('Bad shadow decision or input identity');
   if(!aware(r.input_snapshot.known_at)||Date.parse(r.input_snapshot.known_at)>Date.parse(r.known_at))throw new Error('Enrollment inputs not yet public');
   if(!(r.input_snapshot.documented_split_ordinal>=3))throw new Error('Enrollment requires documented third-or-later split');
   noFuture(r.input_snapshot);
 }else{
   if(!enrollment||r.issuer_id!==enrollment.issuer_id||r.policy_sha256!==enrollment.policy_sha256)throw new Error('Evidence needs matching frozen enrollment');
   if(!aware(r.observed_at)||Date.parse(r.observed_at)>Date.parse(r.known_at))throw new Error('Observation clock mismatch');
   if(r.kind==='locate'&&(!positive(r.shares)||!(r.apr>=0)||!Number.isFinite(r.apr)||!r.broker_reference||r.status!=='approval'))throw new Error('Locate needs broker-approved positive quantity and APR');
   if(r.kind==='order_attempt'&&(!r.broker_reference||!['entry','cover'].includes(r.phase)||!['submitted','rejected','cancelled','expired'].includes(r.status)||!positive(r.shares)))throw new Error('Invalid observed order attempt');
   if(r.kind==='fill'&&(!positive(r.shares)||!positive(r.price)||!['entry','cover'].includes(r.phase)||!r.broker_reference||r.observed!==true||r.compliance_verified!==true||!r.execution_id))throw new Error('Fill must be observed, compliant and uniquely identified');
   if(r.kind==='fill'&&Date.parse(r.observed_at)<Date.parse(enrollment.entry_at))throw new Error('Fill precedes frozen entry');
   if(r.kind==='loan_return'&&(!positive(r.shares)||!r.broker_reference||!r.loan_reference))throw new Error('Loan return needs broker evidence');
   if(r.kind==='cashflow'&&(!Number.isFinite(r.amount)||!['borrow','dividend','locate','servicing','cash_in_lieu','commission','other'].includes(r.category)))throw new Error('Invalid actual cash flow');
   if(r.kind==='closure'&&!records.some(x=>x.record.event_id===r.event_id&&x.record.kind==='fill'&&x.record.phase==='entry'))throw new Error('Closure requires an observed entry ledger');
   if(r.kind==='closure'&&(r.position_reconciled!==true||r.loan_reconciled!==true||!r.broker_reference))throw new Error('Closure requires position and loan reconciliation');
 }
 canonical(r);return r;
}
function append(file,incoming,now=new Date().toISOString()){
 const records=load(file),pending=records.slice(),ids=new Set(records.map(x=>hash(x.record))),batch=[];
 for(const r of incoming){
   if(ids.has(hash(r)))continue;
   if(r.execution_id&&pending.some(x=>x.record.execution_id===r.execution_id))throw new Error('Conflicting duplicate execution ID');
   validate(r,pending,now);
   const body={record:r,imported_at:now,previous_sha256:pending.at(-1)?.sha256||null},row={...body,sha256:hash(body)};
   pending.push(row);batch.push(row);ids.add(hash(r));
 }
 // Entire batch is checked before writing; exclusive lock prevents lost append races.
 fs.mkdirSync(path.dirname(file),{recursive:true});const lock=file+'.lock';const fd=fs.openSync(lock,'wx');
 try{const live=load(file);if((live.at(-1)?.sha256||null)!==(records.at(-1)?.sha256||null))throw new Error('Concurrent shadow journal change');if(batch.length)fs.appendFileSync(file,batch.map(x=>JSON.stringify(x)).join('\n')+'\n');}
 finally{fs.closeSync(fd);fs.unlinkSync(lock);}
 return {appended:batch.length,total:pending.length,head:pending.at(-1)?.sha256||null};
}
function summary(file){
 const records=load(file),enrolled=records.filter(x=>x.record.kind==='enrollment'),fills=records.filter(x=>x.record.kind==='fill'),issuers=new Set(enrolled.map(x=>x.record.issuer_id));
 return {records:records.length,eligible_decisions:enrolled.length,distinct_issuers:issuers.size,observed_fills:fills.length,locates:records.filter(x=>x.record.kind==='locate').length,
  closed:records.filter(x=>x.record.kind==='closure').length,minimum_review_count_met:enrolled.length>=50&&issuers.size>=30,production_authority:'none',head:records.at(-1)?.sha256||null};
}
module.exports={canonical,hash,aware,load,validate,append,summary};
