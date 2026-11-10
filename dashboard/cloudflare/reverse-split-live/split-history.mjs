// Primary-source completion evidence and narrow reviewed action aliases.
// Original history rows are never edited. Reviews apply to new decisions only.
export const HISTORY_REVIEW_VERSION='completed_split_history.2026-11-10.v1';
const MONTH='(?:January|February|March|April|May|June|July|August|September|October|November|December)',DATE=MONTH+'\\s+\\d{1,2},?\\s+20\\d{2}',SPLIT='(?:reverse(?:[ -]+(?:stock|share))?[ -]+split|share[ -]+consolidation)';
export function completedSplitEvidence(text,{published_at,now=new Date().toISOString()}={}){
 const s=String(text).replace(/\s+/g,' '),found=[];
 const patterns=[
  // The completion verb must describe the split, not a shareholder meeting.
  [SPLIT+'(?:\\s+(?:that|which))?\\s+(?:was\\s+(?:effected|implemented|completed|effective)|effected|implemented|completed|became effective|took effect)[^.;]{0,75}?('+DATE+')',1],
  ['(?:effected|implemented|completed)\\s+(?:(?:a|an|the|its)\\s+)?(?:[0-9]+(?:-for-|:)[0-9]+\\s+)?'+SPLIT+'[^.;]{0,100}?('+DATE+')',1],
  ['('+DATE+')[, ]{0,5}(?:the\\s+)?(?:company|we|[A-Z][A-Za-z]+)\\s+(?:had\\s+)?(?:effected|implemented|completed)\\s+(?:(?:a|an|the|its)\\s+)?(?:[0-9]+(?:-for-|:)[0-9]+\\s+)?'+SPLIT,1],
  ['(?:began|commenced|started)\\s+trading[^.;]{0,110}?(?:'+SPLIT+'[ -]+adjusted\\s+basis|adjusted\\s+basis[^.;]{0,65}?'+SPLIT+')[^.;]{0,45}?('+DATE+')',1],
 ];
 for(const [pattern,group]of patterns)for(const m of s.matchAll(new RegExp(pattern,'gi'))){
  const ms=Date.parse(m[group]);if(Number.isFinite(ms)&&new Date(ms).getUTCDate()!==Number(/\s(\d{1,2})/.exec(m[group])?.[1]))continue;const day=Number.isFinite(ms)?new Date(ms).toISOString().slice(0,10):null;
  if(!day||!published_at||day>published_at.slice(0,10)||day>=now.slice(0,10))continue;
  const prefix=s.slice(Math.max(0,m.index-45),m.index);if(/(?:not|never|may|might|will|would|could|should|plans? to|intends? to|expects? to|expected to)\s*(?:(?:have|be|have been)\s+)?$/i.test(prefix))continue;
  if(!found.some(r=>r.date===day&&r.clause===m[0]))found.push({date:day,clause:m[0],basis:'completed_split_bound_clause'});
 }
 return found;
}
export const REVIEWED_SPLIT_HISTORY=Object.freeze({
 schema:'primary_split_history_review.v1',version:HISTORY_REVIEW_VERSION,reviewed_at:'2026-11-10T17:24:06Z',reviewer:'Codex review of checksum-verified original primary submissions',cik:'2022416',complete_history:false,documented_count_is_lower_bound:true,
 actions:[
  {effective_date:'2024-11-27',trading_date:'2024-11-29',ratio:9,source_sha256:['05ff43bed5e62e81323ae33d71e504de998063ec6323105b636e392b31fc654b','54d5fcc746e9f98c053a8d291a858054276b722fd556a27c7e9dcb199d466707'],basis:'One 1-for-9 action: effective after November 27 close, reflected at November 29 trading.'},
  {effective_date:'2025-07-28',trading_date:'2025-07-29',ratio:15,source_sha256:['6016664840dd9386e28df61cfa6941a4ff7f1c053a8998a58d9f323193179e0e','0c7a9eb85bdf660743a7a508bb878a4e8a5bd6c355f8b698b580830632c5dacb'],basis:'One 1-for-15 action: effective after July 28 close, adjusted trading July 29.'},
 ],
 excluded:[{effective_date:'2025-07-14',source_sha256:'59be7bb859f5f049620c89a8882cb5378c4cd99fe4c4e38e5eec9ea98285d521',basis:'July 14 is the completed shareholder meeting; this July 22 source says the split will be effective July 28.'}],
 preserved_completed:[{effective_date:'2026-05-28',ratio:10,source_sha256:'e572b762e0b67107bc280d8b916b34788aebc7182a4ad41928508824d3a470ac'}],
 scope:'Only the named issuer, dates and exact primary-source hashes. No date-window heuristic; no original history row, decision or fill is rewritten.'
});
export function reviewedPriorHistory(rows,now=new Date().toISOString()){
 const review=REVIEWED_SPLIT_HISTORY;if(Date.parse(now)<Date.parse(review.reviewed_at))return rows;
 return rows.map(r=>{
  if(String(r.cik)!==review.cik)return r;
  const rejected=review.excluded.find(x=>x.effective_date===r.effective_date&&x.source_sha256===r.source_sha256);
  if(rejected)return {...r,verified:false,original_verified:r.verified,history_review:{version:review.version,reviewed_at:review.reviewed_at,disposition:'not_a_completed_split',reason:rejected.basis}};
  const action=review.actions.find(x=>[x.effective_date,x.trading_date].includes(r.effective_date)&&x.source_sha256.includes(r.source_sha256));
  return action?{...r,source_effective_date:r.effective_date,effective_date:action.effective_date,first_adjusted_trading_date:action.trading_date,ratio:action.ratio,history_review:{version:review.version,reviewed_at:review.reviewed_at,disposition:'same_split_action',reason:action.basis}}:r;
 });
}
export async function queueReviewedHistoryRepair(env,{hash,enqueue}){
 const marker='repair:'+HISTORY_REVIEW_VERSION;if(await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(marker).first())return;
 const original=(await env.DB.prepare('SELECT * FROM rs_history WHERE cik=? ORDER BY effective_date').bind(REVIEWED_SPLIT_HISTORY.cik).all()).results;
 const raw=JSON.stringify({schema:'split_history_repair_receipt.v1',review:REVIEWED_SPLIT_HISTORY,recorded_at:new Date().toISOString(),original_history_rows:original,original_rows_unchanged:true,not_original_clock_fills:true}),key='review/repairs/'+await hash(raw)+'.json';
 await env.EVIDENCE.put(key,new TextEncoder().encode(raw),{httpMetadata:{contentType:'application/json'}});
 const accession='0001185185-26-001520',payload={cik:'1876766',accession,published_at:'2026-04-29T04:00:00.000Z',url:'https://www.sec.gov/Archives/edgar/data/1876766/000118518526001520/0001185185-26-001520.txt',expected_sha256:'b9bab50f402ebdb3e8bee8f8fa16b6a3df6f9af6e438469c11e5f34e6490618e',repair_version:HISTORY_REVIEW_VERSION};
 await enqueue('history_filing',payload,14,'history-filing-review:'+HISTORY_REVIEW_VERSION+':'+accession);
 for(const r of (await env.DB.prepare('SELECT id FROM rs_events WHERE cik=?').bind(REVIEWED_SPLIT_HISTORY.cik).all()).results)await enqueue('rescore',{id:r.id},14,'history-review-rescore:'+HISTORY_REVIEW_VERSION+':'+r.id);
 await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind(marker,JSON.stringify({at:new Date().toISOString(),original_object_key:key,target_cik:'1876766',history_view_cik:REVIEWED_SPLIT_HISTORY.cik,historical_decisions_unchanged:true}),new Date().toISOString()).run();
}
