
import { privateJson, requirePortfolioViewer } from '../../../_lib/auth.js';
import { readResearchObject } from './data.js';

const SCHEMA = 'stock-summary.v1';

export async function onRequestGet(context) {
  if (!await requirePortfolioViewer(context)) return privateJson({ error: 'Unauthorized.' }, 401);
  const params = new URL(context.request.url).searchParams;
  const coverage = params.get('view') === 'coverage';
  const ticker = (params.get('ticker') || '').toUpperCase();
  if (!coverage && !/^[A-Z0-9^][A-Z0-9.^_-]{0,47}$/.test(ticker)) {
    return privateJson({ error: 'Invalid stock identity.' }, 400);
  }
  const bucket = context.env.PRIVATE_ARTIFACTS;
  if (!bucket) return privateJson({ error: 'Stock summaries are awaiting publication.' }, 503);
  try {
    const object = await bucket.get('stock-summary/v1/current.json');
    if (!object || object.size > 1024 * 1024) return privateJson({ error: 'Stock summaries are awaiting publication.' }, 503);
    const manifest = await object.json();
    if (manifest.schema !== SCHEMA) throw new Error('Unknown stock Summary release');
    const canonical = Object.hasOwn(manifest.aliases, ticker) ? manifest.aliases[ticker] : ticker;
    const location = Object.hasOwn(manifest.locations, canonical) ? manifest.locations[canonical] : null;
    if (!coverage && location === null) return privateJson({ error: 'Stock awaits a Summary coverage review.' }, 404);
    const receipt = coverage ? manifest.coverage : manifest.bundles[location];
    const bundle = JSON.parse(await readResearchObject(bucket, receipt));
    if (bundle.schema !== SCHEMA || bundle.as_of !== manifest.as_of) throw new Error('Inconsistent release');
    if (coverage) return privateJson(bundle);
    const row = bundle.listings?.[canonical];
    if (row?.ticker !== canonical || row.schema !== SCHEMA) throw new Error('Inconsistent stock identity');
    return privateJson({ ...row, as_of: manifest.as_of });
  } catch {
    return privateJson({ error: 'Stock Summary could not be verified.' }, 503);
  }
}
