export function makeWarmDispatcher({token,repository,fetcher=fetch}={}){
 if(!token||repository!=='magis-capital-partners/single-stock-investments')return null;
 return async()=>{const r=await fetcher('https://api.github.com/repos/'+repository+'/dispatches',{method:'POST',headers:{authorization:'Bearer '+token,accept:'application/vnd.github+json','content-type':'application/json','user-agent':'MagisReverseSplitShadow'},body:JSON.stringify({event_type:'reverse-split-shadow-warm',client_payload:{research_only:true,reason:'Prepare dependencies before the bounded collector lease handoff'}}),redirect:'error',signal:AbortSignal.timeout(10000)});if(r.status!==204){await r.body?.cancel();throw new Error('Warm successor dispatch HTTP '+r.status);}return {queued_at:new Date().toISOString()};};
}
