import {requireHumanViewer,privateJson} from '../../../_lib/auth.js';
// Check the owner here as well as in middleware, including on preview deployments.
export async function onRequestGet(context) {
  const viewer=await requireHumanViewer(context);
  if(!viewer)return privateJson({error:'Sign in through Cloudflare Access.'},401);
  if(viewer.role!=='owner')return privateJson({error:'Owner access required.'},403);
  if(!context.env.REVERSE_SPLITS)return Response.json({error:'Live announcement service is not connected.',status:'unavailable'},{status:503,headers:{'cache-control':'no-store, private'}});
  const incoming=new URL(context.request.url),suffix=incoming.pathname.replace(/^\/api\/v1\/reverse-splits\/?/,'')||'health';
  if(!/^(?:health|events(?:\/[^/]+)?)$/.test(suffix))return new Response('Not found',{status:404});
  const response=await context.env.REVERSE_SPLITS.fetch(new Request('https://reverse-split.internal/'+suffix+incoming.search));
  return new Response(response.body,{status:response.status,headers:{'content-type':'application/json','cache-control':'no-store, private','x-content-type-options':'nosniff'}});
}
