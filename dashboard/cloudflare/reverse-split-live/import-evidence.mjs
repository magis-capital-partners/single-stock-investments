#!/usr/bin/env node
// Append dated, owner-supplied evidence. This never requests a stock loan or sends an order.
import {readFileSync} from 'node:fs';
import {remoteEnvironment} from './collector.mjs';
import {validateEvidence} from './shadow-core.mjs';
import {digest} from './shadow-service.mjs';
const path=process.argv[2];if(!path)throw new Error('Supply a local reverse_split_shadow_evidence.v1 JSON file');
const raw=readFileSync(path,'utf8');if(Buffer.byteLength(raw)>1000000)throw new Error('Evidence file exceeds limit');
const input=JSON.parse(raw);if(input.schema!=='reverse_split_shadow_evidence.v1'||!Array.isArray(input.records)||input.records.length>100)throw new Error('Invalid evidence envelope');
const env=remoteEnvironment({token:process.env.CLOUDFLARE_API_TOKEN,account:process.env.CLOUDFLARE_ACCOUNT_ID||'e1cac493b315c8fd7398500dd1bfd687',database:'de0ec6d5-9619-48be-b02e-d007456517ee',bucket:'single-stock-reverse-splits-evidence'});
const records=[];for(const rawRecord of input.records){const record=validateEvidence(rawRecord,new Date().toISOString()),id=await digest(JSON.stringify(record));records.push({...record,id});}
for(const r of records){const event=await env.DB.prepare('SELECT id FROM rs_events WHERE id=?').bind(r.event_id).first();if(!event)throw new Error('Evidence refers to an unknown announcement');await env.DB.prepare('INSERT OR IGNORE INTO rs_shadow_evidence VALUES(?,?,?,?,?)').bind(r.id,r.event_id,r.kind,r.observed_at,JSON.stringify(r)).run();}
console.log(JSON.stringify({imported:records.length,broker_orders:0}));
