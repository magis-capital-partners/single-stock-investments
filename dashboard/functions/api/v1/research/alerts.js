import { privateJson, requirePortfolioViewer } from '../../../_lib/auth.js';
import { failure, requestId, requireDatabase } from '../../../_lib/http.js';

export async function onRequestGet(context) {
  const viewer=await requirePortfolioViewer(context);
  if(!viewer?.email)return privateJson({error:'Unauthorized.'},401);
  try {
    const rows=await requireDatabase(context.env).prepare('SELECT event_key, rule_id, ticker, metric, observed_value, unit, period, filed, note, release_sha256, triggered_at, read_at FROM research_alert_events WHERE viewer_email = ? ORDER BY triggered_at DESC LIMIT 100').bind(String(viewer.email).toLowerCase()).all();
    return privateJson({events:rows.results||[]});
  }catch(error){return failure(error,requestId(context.request));}
}
export async function onRequestPut(context) {
  const viewer=await requirePortfolioViewer(context);
  if(!viewer?.email)return privateJson({error:'Unauthorized.'},401);
  const origin=context.request.headers.get('origin');
  if(origin&&origin!==new URL(context.request.url).origin)return privateJson({error:'Origin is not allowed.'},403);
  try {
    await requireDatabase(context.env).prepare("UPDATE research_alert_events SET read_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE viewer_email = ? AND read_at IS NULL").bind(String(viewer.email).toLowerCase()).run();
    return privateJson({read:true});
  }catch(error){return failure(error,requestId(context.request));}
}
