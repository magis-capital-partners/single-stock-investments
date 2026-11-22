import { privateJson, requirePortfolioViewer } from '../../../_lib/auth.js';
import { failure, requestId, requireDatabase } from '../../../_lib/http.js';

const KEYS = new Set(['workspace', 'templates', 'scenarios', 'watchlists', 'screens', 'alerts', 'imports']);
const MAX_BYTES = 524288;

export function validatePreference(key, value) {
  if (!KEYS.has(key) || !value || typeof value !== 'object' || Array.isArray(value)) return false;
  const raw = JSON.stringify(value);
  return new TextEncoder().encode(raw).length <= MAX_BYTES && !Object.keys(value).some(k => ['__proto__', 'constructor', 'prototype'].includes(k));
}

async function viewer(context) {
  const owner = await requirePortfolioViewer(context);
  return owner?.email ? String(owner.email).toLowerCase() : null;
}

export async function onRequestGet(context) {
  const email = await viewer(context);
  if (!email) return privateJson({ error: 'Unauthorized.' }, 401);
  const key = new URL(context.request.url).searchParams.get('key') || 'workspace';
  if (!KEYS.has(key)) return privateJson({ error: 'Unknown preference.' }, 400);
  try {
    const row = await requireDatabase(context.env).prepare('SELECT value_json, revision, updated_at FROM research_preferences WHERE viewer_email = ? AND preference_key = ?').bind(email, key).first();
    const viewer_key = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email)))].map(b=>b.toString(16).padStart(2,'0')).join('');
    return privateJson({ key, viewer_key, value: row ? JSON.parse(row.value_json) : {}, revision: row?.revision || 0, updated_at: row?.updated_at || null });
  } catch (error) { return failure(error, requestId(context.request)); }
}

export async function onRequestPut(context) {
  const email = await viewer(context);
  if (!email) return privateJson({ error: 'Unauthorized.' }, 401);
  // Only same-origin human requests; no machine route or service-token grant.
  const origin = context.request.headers.get('origin');
  if (origin && origin !== new URL(context.request.url).origin) return privateJson({ error: 'Origin is not allowed.' }, 403);
  if (Number(context.request.headers.get('content-length')) > MAX_BYTES + 4096) return privateJson({ error: 'Saved workspace is too large.' }, 413);
  let body;
  try {
    const raw = await context.request.text();
    if (new TextEncoder().encode(raw).length > MAX_BYTES + 4096) return privateJson({ error: 'Saved workspace is too large.' }, 413);
    body = JSON.parse(raw);
  } catch { return privateJson({ error: 'A JSON workspace is required.' }, 400); }
  if (!validatePreference(body.key, body.value) || !Number.isInteger(body.revision) || body.revision < 0) return privateJson({ error: 'Invalid saved workspace.' }, 400);
  try {
    const db = requireDatabase(context.env), raw = JSON.stringify(body.value);
    const result = body.revision === 0
      ? await db.prepare('INSERT INTO research_preferences(viewer_email, preference_key, value_json) VALUES (?, ?, ?) ON CONFLICT(viewer_email, preference_key) DO NOTHING').bind(email, body.key, raw).run()
      : await db.prepare("UPDATE research_preferences SET value_json = ?, revision = revision + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE viewer_email = ? AND preference_key = ? AND revision = ?").bind(raw, email, body.key, body.revision).run();
    if (!result.meta?.changes) return privateJson({ error: 'This workspace changed on another device. Reload before saving again.' }, 409);
    return privateJson({ key: body.key, revision: body.revision + 1, saved: true });
  } catch (error) { return failure(error, requestId(context.request)); }
}
