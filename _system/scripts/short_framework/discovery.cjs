'use strict';
// Bounded public SEC discovery only. No broker, subscription, or Gateway path.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { hash, write } = require('./store.cjs');
const { nyClock, dateAfter, read, loadEvents } = require('./adapters.cjs');
async function discover({ root, work, store, maximum = 20, since, fetcher = fetch, delay = 250 }) {
  if (!Number.isInteger(maximum) || maximum < 1 || maximum > 200) throw new TypeError('SEC request budget must be 1..200');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(since)) throw new TypeError('Discovery start date required');
  const config = fs.readFileSync(path.join(root, '_system/data/reverse_splits/config.toml'), 'utf8');
  const userAgent = config.match(/^user_agent\s*=\s*"([^"]+)"/m)?.[1];
  if (!userAgent) throw new TypeError('Existing SEC research User-Agent is required');
  const progressFile = path.join(work, 'discovery-progress.local.json');
  const progress = fs.existsSync(progressFile) ? read(progressFile) : { first_seen: {}, completed: {} };
  const universe = store.records().filter(r => r.kind === 'universe');
  const issuerRows = universe.length ? universe : loadEvents(root).events;
  const ciks = [...new Set(issuerRows.map(e => String(e.cik || e.issuer_id || e.issuer || '').replace(/^cik\//, '')).filter(s => /^\d+$/.test(s)))].sort((a, b) => hash(a).localeCompare(hash(b)));
  const incoming = [], failures = []; let requests = 0, blocked = false;
  async function get(url) {
    const u = new URL(url);
    if (u.protocol !== 'https:' || !['www.sec.gov', 'data.sec.gov'].includes(u.hostname)) throw new TypeError('SEC HTTPS allowlist only');
    if (requests >= maximum) throw new TypeError('Request budget exhausted');
    if (requests && delay) await new Promise(resolve => setTimeout(resolve, delay));
    requests++;
    const response = await fetcher(url, { headers: { 'User-Agent': userAgent, Accept: 'application/json,text/html' },
      redirect: 'error', signal: AbortSignal.timeout(8000) });
    if ([401, 403, 429].includes(response.status)) { blocked = true; throw new TypeError('SEC access denied or rate limited; collection stopped'); }
    if (!response.ok) throw new TypeError('SEC HTTP ' + response.status);
    const bytes = Buffer.from(await response.arrayBuffer());
    const digest = crypto.createHash('sha256').update(bytes).digest('hex');
    const dir = path.join(work, 'public-sec-cache'); fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, hash(url) + '.raw'); fs.writeFileSync(file, bytes);
    return { bytes, digest };
  }
  for (const cik of ciks) {
    if (requests >= maximum || blocked) break;
    try {
      const submission = await get('https://data.sec.gov/submissions/CIK' + cik.padStart(10, '0') + '.json');
      const doc = JSON.parse(submission.bytes.toString('utf8'));
      if (Number(doc.cik) !== Number(cik)) throw new TypeError('Submission issuer mismatch');
      const recent = doc.filings?.recent || {};
      for (let i = 0; i < (recent.accessionNumber || []).length; i++) {
        if (requests >= maximum || blocked) break;
        const accession = recent.accessionNumber[i], form = recent.form[i], filed = recent.filingDate[i];
        if (filed < since || progress.completed[accession] || !['8-K', '6-K', '424B4', '424B5', 'S-1', 'S-3', 'F-1', 'F-3'].includes(form)) continue;
        const primary = recent.primaryDocument[i];
        if (!/^[\w.-]+$/.test(primary) || !/^\d{10}-\d{2}-\d{6}$/.test(accession)) continue;
        const url = 'https://www.sec.gov/Archives/edgar/data/' + Number(cik) + '/' + accession.replaceAll('-', '') + '/' + primary;
        const filing = await get(url), text = filing.bytes.toString('utf8'), now = new Date().toISOString();
        const parsed = text.match(/reverse[\s-]+(?:stock[\s-]+)?split|registered direct offering|private placement|at.the.market|convertible (?:note|preferred)|notice of (?:delisting|non.compliance)/i);
        progress.first_seen[accession] ||= now;
        if (parsed) {
          const family = /reverse/i.test(parsed[0]) ? 'split' : /notice of/i.test(parsed[0]) ? 'deficiency' : 'financing';
          const acceptance = recent.acceptanceDateTime?.[i];
          const known = acceptance && /(Z|[+-]\d\d:\d\d)$/.test(acceptance) ? acceptance : nyClock(dateAfter(filed), '00:00:00');
          incoming.push({ id: 'discovery/' + family + '/' + cik + '/' + accession, kind: 'event', family,
            cik, issuer_id: 'cik/' + Number(cik), ticker: (doc.tickers || [])[0] || '',
            known_at: known, first_seen_at: progress.first_seen[accession], event_date: filed,
            source_url: url, source_sha256: filing.digest, locator: 'raw_source[' + parsed.index + ':' + (parsed.index + parsed[0].length) + ']',
            source_locator: 'raw_source[' + parsed.index + ':' + (parsed.index + parsed[0].length) + ']',
            event_status: 'phrase_lead_requires_source_review', identity_verified: false,
            discovery_basis: universe.length ? 'selected_independent_universe_SEC_submissions' : 'selected_prior_research_issuers_SEC_submissions',
            economic_terms_verified: false });
        }
        progress.completed[accession] = filing.digest;
        write(progressFile, progress);
      }
    } catch (error) { failures.push({ cik, error: error.message }); }
  }
  if (incoming.length) store.import(incoming);
  write(progressFile, progress);
  return { requests, new_leads: incoming.length, failures, blocked, coverage_complete: false,
    scope: universe.length ? 'Selected imported-universe issuers; recent submissions only' : 'Selected prior research issuers; selection bias retained',
    paid_downloads_usd: 0, source_review_required: true, production_authority: 'none' };
}
module.exports = { discover };
