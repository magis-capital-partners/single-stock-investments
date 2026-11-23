import { privateJson, requirePortfolioViewer } from '../../../_lib/auth.js';

const HEX = /^[a-f0-9]{64}$/;
const MAX_BYTES = 20 * 1024 * 1024;

async function hash(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
}

export async function readResearchObject(bucket, record) {
  if (!record || !HEX.test(record.sha256 || '') || !Number.isInteger(record.bytes) || record.bytes < 0 || record.bytes > MAX_BYTES
    || !Array.isArray(record.chunks) || record.chunks.length !== 1) throw new Error('Invalid research object receipt');
  const chunk = record.chunks[0];
  if (!HEX.test(chunk.stored_sha256 || '') || chunk.bytes !== record.bytes || chunk.sha256 !== record.sha256
    || !Number.isInteger(chunk.stored_bytes) || chunk.stored_bytes > MAX_BYTES || !['raw', 'gzip'].includes(chunk.encoding)) throw new Error('Invalid research chunk receipt');
  const object = await bucket.get(`research-archive/v1/objects/${chunk.stored_sha256.slice(0, 2)}/${chunk.stored_sha256}`);
  if (!object || object.size !== chunk.stored_bytes) throw new Error('Research object is not available');
  const stored = await object.arrayBuffer();
  if (await hash(stored) !== chunk.stored_sha256) throw new Error('Research object failed integrity verification');
  const bytes = chunk.encoding === 'gzip'
    ? await new Response(new Blob([stored]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer() : stored;
  if (bytes.byteLength !== record.bytes || await hash(bytes) !== record.sha256) throw new Error('Research document failed integrity verification');
  return new TextDecoder().decode(bytes);
}

export async function onRequestGet(context) {
  if (!await requirePortfolioViewer(context)) return privateJson({ error: 'Unauthorized.' }, 401);
  const ticker = new URL(context.request.url).searchParams.get('ticker') || 'index';
  const changes = new URL(context.request.url).searchParams.get('view') === 'changes';
  if (ticker !== 'index' && !/^[A-Za-z0-9^][A-Za-z0-9.^_-]{0,47}$/.test(ticker)) return privateJson({ error: 'Invalid stock identity.' }, 400);
  try {
    const bucket = context.env.PRIVATE_ARTIFACTS;
    if (!bucket) return privateJson({ error: 'Live research is not configured; use the publication snapshot.' }, 404);
    const pointer = await bucket.get('research-explorer/v1/current.json');
    if (!pointer || pointer.size > 1024 * 1024) return privateJson({ error: 'Use the publication snapshot.' }, 404);
    const manifest = await pointer.json();
    if (manifest.schema_version !== 'stock-research-live.v1') throw new Error('Unknown research release');
    const record = changes ? manifest.changes : ticker === 'index' ? manifest.index : manifest.companies?.[ticker];
    if (!record) return privateJson({ error: 'Company is awaiting the next research refresh.' }, 404);
    const raw = await readResearchObject(bucket, record), document = JSON.parse(raw);
    if (changes ? document.version !== 1 || !document.rows || !document.profiles || !Array.isArray(document.registered) || document.as_of !== manifest.as_of : ticker === 'index' ? document.schema_version !== 'stock-research-index.v1' : document.ticker !== ticker || document.schema_version !== 'stock-research-explorer.v1') throw new Error('Research identity mismatch');
    return new Response(raw, { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store, private', 'x-content-type-options': 'nosniff', 'x-research-as-of': manifest.as_of } });
  } catch {
    // A failed or incomplete live release does not replace the checked Pages
    // snapshot. The client explicitly falls back, never to unauthenticated data.
    return privateJson({ error: 'Live research could not be verified; use the publication snapshot.' }, 503);
  }
}
