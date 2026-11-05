// Private service binding. Owner identity is supplied only by the authenticated Pages proxy.
import {FINANCIAL_VERSION,validateReviewedFacts} from './financials-core.mjs';
const json=(v,status=200)=>Response.json(v,{status,headers:{'cache-control':'no-store, private','x-content-type-options':'nosniff'}});
const read=async(env,key)=>{const o=await env.EVIDENCE.get(key);return o?o.json():null;};
const digest=async v=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(v)))].map(x=>x.toString(16).padStart(2,'0')).join('');
export async function financialAPI(request,env){
  const url=new URL(request.url),path=url.pathname;
  if(request.method==='POST'&&path==='/fundamentals/reviews'){
    if(!request.headers.get('x-verified-owner'))return json({error:'Verified owner required'},403);
    if(Number(request.headers.get('content-length'))>65536)return json({error:'Review is too large'},413);
    const reader=request.body?.getReader(),decoder=new TextDecoder();let text='',length=0;
    if(!reader)return json({error:'Review required'},400);
    for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>65536){await reader.cancel();return json({error:'Review is too large'},413);}text+=decoder.decode(value,{stream:true});}text+=decoder.decode();
    let input;try{input=JSON.parse(text);}catch{return json({error:'Invalid review'},400);}
    const cik=String(Number(input?.cik));if(!/^\d{1,10}$/.test(cik))return json({error:'Invalid company'},400);
    const profile=await read(env,`financials/profiles/${cik}/latest.json`);if(!profile)return json({error:'Financial profile not found'},404);
    if(input.profile_version!==profile.version)return json({error:'New evidence arrived. Reload the company before reviewing.'},409);
    let facts;const at=new Date().toISOString();try{facts=validateReviewedFacts(input,profile.sources,at);}catch(e){return json({error:e.message},400);}
    const owner=request.headers.get('x-verified-owner'),id=await digest(JSON.stringify({owner,input})),object_key=`financials/reviews/${cik}/${id}.json`;
    const existing=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(`financial_review:${cik}:${id}`).first();if(existing)return json({status:'already_saved',id});
    const review={schema:FINANCIAL_VERSION,id,cik,reviewed_at:at,reviewer:owner,reason:input.reason,source_profile_version:profile.version,facts};
    await env.EVIDENCE.put(object_key,JSON.stringify(review),{httpMetadata:{contentType:'application/json'}});
    await env.DB.prepare('INSERT OR IGNORE INTO rs_state VALUES(?,?,?)').bind(`financial_review:${cik}:${id}`,JSON.stringify({object_key,id}),at).run();
    await env.DB.prepare('INSERT INTO rs_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at').bind('financial_need:'+cik,JSON.stringify({cik,review_id:id,at}),at).run();
    return json({status:'saved_pending_recalculation',id,reviewed_at:at,affects_past_fills:false});
  }
  if(request.method!=='GET')return json({error:'Method not allowed'},405);
  if(path==='/fundamentals'||path==='/fundamentals/summary'){
    const manifest=await read(env,'financials/manifest-latest.json');if(!manifest)return json({status:'warming',profiles:[],summary:{processed:0}},202);
    const {profiles,pages,cards:allCards,...summary}=manifest;if(path.endsWith('/summary'))return json(summary);
    const offset=Number(url.searchParams.get('after')||0);if(!Number.isInteger(offset)||offset<0||offset>100000)return json({error:'Invalid page'},400);
    const q=(url.searchParams.get('q')||'').toUpperCase().slice(0,100),status=url.searchParams.get('status')||'',cards=manifest.cards||profiles;
    const filtered=cards.filter(r=>(!q||[r.cik,r.ticker,r.company].some(v=>String(v||'').toUpperCase().includes(q)))&&(!status||r.status===status));
    return json({schema:FINANCIAL_VERSION,summary,profiles:filtered.slice(offset,offset+50),next_cursor:filtered.length>offset+50?String(offset+50):null});
  }
  const match=/^\/fundamentals\/(\d{1,10})(?:\/(source)\/([a-f0-9]{64}))?$/.exec(path);if(!match)return json({error:'Not found'},404);
  const profile=await read(env,`financials/profiles/${Number(match[1])}/latest.json`);if(!profile)return json({error:'Financial profile not found'},404);
  if(!match[2])return json(profile);
  const source=profile.sources.find(s=>s.sha256===match[3]);if(!source)return json({error:'Source is not attached to this company'},404);
  const object=await env.EVIDENCE.get('documents/'+match[3]);if(!object)return json({error:'Source unavailable'},404);
  // Never render filing HTML on the dashboard origin. Download raw captured evidence.
  return new Response(object.body,{headers:{'content-type':'application/octet-stream','content-disposition':`attachment; filename="filing-${match[3].slice(0,16)}.txt"`,'content-security-policy':"sandbox; default-src 'none'",'x-content-type-options':'nosniff','cache-control':'no-store, private'}});
}
