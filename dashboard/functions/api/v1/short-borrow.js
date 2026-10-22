import { json, requestId, requireDatabase } from '../../_lib/http.js';
import { withEdgeCache } from '../../_lib/edge-cache.js';
export function parseSymbol(value) {
 const s=String(value||'').trim().toUpperCase();
 return /^[A-Z0-9][A-Z0-9.\-/]{0,24}$/.test(s)?s:null;
}
async function produce(context) {
 const id=requestId(context.request),url=new URL(context.request.url);
 const symbol=parseSymbol(url.searchParams.get('symbol'));
 if(!symbol)return json({error:'Choose one valid ticker.',request_id:id},400);
 const days=Math.max(1,Math.min(365,Number.parseInt(url.searchParams.get('days')||'90',10)||90));
 try {
  const db=requireDatabase(context.env);
  const source=await db.prepare("SELECT id,as_of,captured_at,source_sha256,source_rows,checksum_verified,time_basis FROM short_borrow_sources WHERE source='ibkr_public_ftp' ORDER BY as_of DESC LIMIT 1").first();
  if(!source)return json({schema_version:'short_borrow_api.v1',symbol,status:'no_capture_yet',source:null,history:[],locate_approved:false});
  const latest=await db.prepare('SELECT symbol,as_of,fee_apr,available_shares,available_at_least,quality FROM short_borrow_observations WHERE source_id=? AND symbol=?').bind(source.id,symbol).first();
  const since=new Date(Date.now()-days*86400000).toISOString();
  const result=await db.prepare("SELECT o.as_of,o.fee_apr,o.available_shares,o.available_at_least,o.quality FROM short_borrow_observations o JOIN short_borrow_sources s ON s.id=o.source_id WHERE o.symbol=? AND o.as_of>=? AND o.quality='public_indication' AND s.source='ibkr_public_ftp' ORDER BY o.as_of DESC LIMIT 500").bind(symbol,since).all();
  const age=Math.max(0,(Date.now()-Date.parse(source.as_of))/1000);
  return json({schema_version:'short_borrow_api.v1',research_only:true,symbol,source,latest:latest||null,status:latest?'indication':'not_listed',age_seconds:age,stale:!Number.isFinite(age)||age>10800,history:(result.results||[]).reverse(),history_retention_days:90,locate_approved:false,request_id:id});
 } catch {return json({error:'Borrow database unavailable. The dated dashboard snapshot remains available.',request_id:id},503,{'cache-control':'no-store'});}
}
export async function onRequestGet(context){return withEdgeCache(context,120,()=>produce(context));}
