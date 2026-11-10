import {requireHumanViewer,privateJson} from '../../../_lib/auth.js';
// Check the owner here as well as in middleware, including on preview deployments.
export async function onRequestGet(context) {
  const viewer=await requireHumanViewer(context);
  if(!viewer)return privateJson({error:'Sign in through Cloudflare Access.'},401);
  if(viewer.role!=='owner')return privateJson({error:'Owner access required.'},403);
  if(!context.env.REVERSE_SPLITS)return Response.json({error:'Live announcement service is not connected.',status:'unavailable'},{status:503,headers:{'cache-control':'no-store, private'}});
  const incoming=new URL(context.request.url),suffix=incoming.pathname.replace(/^\/api\/v1\/reverse-splits\/?/,'')||'health';
  if(!/^(?:health|events(?:\/[^/]+)?|prepared(?:\/summary|\/\d{1,10})?|fundamentals(?:\/summary|\/\d{1,10}(?:\/source\/[a-f0-9]{64})?)?|shadow(?:\/(?:tracks(?:\/[^/]+)?|borrow|validation|readiness|operations|review-monitor|announcement-quotes\/[a-f0-9]{64}|executable(?:\/tracks(?:\/[^/]+)?)?))?)$/.test(suffix))return new Response('Not found',{status:404});
  const response=await context.env.REVERSE_SPLITS.fetch(new Request('https://reverse-split.internal/'+suffix+incoming.search));
  const headers=new Headers({'content-type':response.headers.get('content-type')||'application/json','cache-control':'no-store, private','x-content-type-options':'nosniff'});
  for(const name of ['content-disposition','content-security-policy'])if(response.headers.has(name))headers.set(name,response.headers.get(name));
  return new Response(response.body,{status:response.status,headers});
}
export async function onRequestPost(context){
  const viewer=await requireHumanViewer(context);if(!viewer)return privateJson({error:'Sign in through Cloudflare Access.'},401);if(viewer.role!=='owner')return privateJson({error:'Owner access required.'},403);
  const url=new URL(context.request.url);if(url.pathname!=='/api/v1/reverse-splits/fundamentals/reviews')return privateJson({error:'Not found'},404);
  if(context.request.headers.get('origin')!==url.origin||!context.request.headers.get('content-type')?.startsWith('application/json'))return privateJson({error:'Submit this review from the signed-in dashboard.'},403);
  if(!context.env.REVERSE_SPLITS)return privateJson({error:'Research service unavailable'},503);
  const response=await context.env.REVERSE_SPLITS.fetch(new Request('https://reverse-split.internal/fundamentals/reviews',{method:'POST',body:context.request.body,duplex:'half',headers:{'content-type':'application/json','x-verified-owner':viewer.email||viewer.subject}}));
  return new Response(response.body,{status:response.status,headers:{'content-type':'application/json','cache-control':'no-store, private','x-content-type-options':'nosniff'}});
}
