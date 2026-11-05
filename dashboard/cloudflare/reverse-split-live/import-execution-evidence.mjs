#!/usr/bin/env node
// Owner-supplied IBKR documents only; this cannot query a broker or send orders.
import {readFileSync} from 'node:fs';
import {remoteEnvironment} from './collector.mjs';
import {digest} from './shadow-service.mjs';
import {at,finite,validateEvidence} from './shadow-core.mjs';
import {completeCosts} from './execution-core.mjs';
export function validateIBKREvidence(r,now){
  if(!r||r.broker!=='IBKR'||r.scope!=='reverse_split')throw new Error('IBKR reverse-split scope required');
  if(r.kind==='trading_status'){
    if(typeof r.event_id!=='string'||!r.event_id||typeof r.halted!=='boolean'||!r.source_url?.startsWith('https://')||typeof r.reference!=='string'||!r.reference||at(r.observed_at)===null||at(r.observed_at)>at(now)||at(r.valid_until)===null||at(r.valid_until)<=at(r.observed_at))throw new Error('Invalid trading-status evidence');
  }else if(r.kind==='cost_reconciliation'){
    if(typeof r.event_id!=='string'||!r.event_id||!r.policy_id?.startsWith('rs_ibkr_')||!r.source_url?.startsWith('https://')||!r.reference||at(r.observed_at)===null||at(r.observed_at)>at(now)||at(r.covers_fills_through)===null||at(r.covers_fills_through)>at(r.observed_at)||!['estimated','documented'].includes(r.basis))throw new Error('Invalid cost reconciliation');
    if(!completeCosts(r.costs))throw new Error('Every cost component, including signed short-proceeds interest, must be explicit and numeric');
  }else validateEvidence(r,now);
  if(['locate','margin'].includes(r.kind)&&(!/^[A-Za-z0-9_.:-]{1,100}$/.test(r.allocation_id||'')))throw new Error('A shared IBKR allocation reference is required to prevent double counting');
  return {...r,approval_basis:'owner_supplied_ibkr_document',broker_execution_verified:false};
}
if(process.argv[1]&&import.meta.url.endsWith('/import-execution-evidence.mjs')&&process.argv[1].replaceAll('\\','/').endsWith('/import-execution-evidence.mjs')){
  const path=process.argv[2];if(!path)throw new Error('Supply an ibkr_reverse_split_evidence.v1 JSON file');
  const raw=readFileSync(path,'utf8');if(Buffer.byteLength(raw)>1000000)throw new Error('Evidence file exceeds limit');
  const input=JSON.parse(raw);if(input.schema!=='ibkr_reverse_split_evidence.v1'||!Array.isArray(input.records)||input.records.length>100)throw new Error('Invalid evidence envelope');
  const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence'});
  const records=input.records.map(r=>validateIBKREvidence(r,new Date().toISOString()));
  for(const r of records){if(!await env.DB.prepare('SELECT id FROM rs_events WHERE id=?').bind(r.event_id).first())throw new Error('Unknown reverse-split event');const id=await digest(JSON.stringify(r));await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(id,r.event_id,r.kind,r.observed_at,JSON.stringify({...r,id})).run();}
  console.log(JSON.stringify({imported:records.length,broker_orders:0}));
}
