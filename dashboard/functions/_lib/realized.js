async function sha256Hex(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}

function requirePrivateArchive(env) {
  if (!env?.PRIVATE_ARTIFACTS) throw new Error('Missing private archive binding');
  return env.PRIVATE_ARTIFACTS;
}

const SHA = /^[a-f0-9]{64}$/;
const DECIMAL = /^-?\d{1,24}(?:\.\d{1,24})?$/;
const OWNERS = new Set(['drew', 'michael', 'unallocated']);
export const MAX_INGEST_BYTES = 400_000;

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}

export function validDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
}

// Decimal strings are accumulated exactly. Financial totals never pass through
// Number or SQLite's floating-point SUM(TEXT) conversion.
export function addDecimal(left = '0', right = '0') {
  const parse = value => {
    if (!DECIMAL.test(String(value))) throw new TypeError('Invalid financial decimal');
    const [whole, fraction = ''] = String(value).split('.');
    return { value: BigInt(`${whole}${fraction}`), scale: fraction.length };
  };
  const a = parse(left), b = parse(right), scale = Math.max(a.scale, b.scale);
  const n = a.value * 10n ** BigInt(scale - a.scale) + b.value * 10n ** BigInt(scale - b.scale);
  const sign = n < 0n ? '-' : '', digits = (n < 0n ? -n : n).toString().padStart(scale + 1, '0');
  const result = scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}`.replace(/\.?0+$/, '') : digits;
  return `${sign}${result || '0'}`;
}

export function summarize(rows) {
  const total = { realized_usd: '0', count: 0, missing_usd: 0, inferred_count: 0, native_totals: {} };
  for (const row of rows) {
    total.count += row.count ?? 1;
    if (row.realized_usd == null) total.missing_usd += 1;
    else total.realized_usd = addDecimal(total.realized_usd, row.realized_usd);
    if (row.native_totals) {
      for (const [currency, amount] of Object.entries(row.native_totals)) total.native_totals[currency] = addDecimal(total.native_totals[currency] || '0', amount);
      total.missing_usd += row.missing_usd || 0;
      total.inferred_count += row.inferred_count || 0;
    } else {
      if (row.realized_native != null) total.native_totals[row.currency] = addDecimal(total.native_totals[row.currency] || '0', row.realized_native);
      if (row.confidence === 'legacy_inferred') total.inferred_count += 1;
    }
  }
  return total;
}

export function validateRecord(row, account) {
  if (!row || row.account !== account || !OWNERS.has(row.owner) || !row.record_id || String(row.record_id).length > 180
    || !validDate(row.trade_date) || (row.settlement_date !== null && !validDate(row.settlement_date))
    || !['unknown', 'pending', 'date_reached'].includes(row.settlement_status)
    || !SHA.test(row.report_id || '') || typeof row.contract_label !== 'string' || row.contract_label.length > 300
    || !/^[A-Z]{3}$/.test(row.currency || '') || typeof row.ticker !== 'string' || row.ticker.length > 100) throw new TypeError('Invalid realized record');
  for (const key of ['realized_usd', 'realized_native', 'quantity', 'price', 'cost_basis', 'fx_rate', 'proceeds', 'commission', 'strike', 'multiplier']) {
    if (row[key] != null && !DECIMAL.test(String(row[key]))) throw new TypeError(`Invalid decimal: ${key}`);
  }
  if (JSON.stringify(row).length > 12_000) throw new TypeError('Realized record too large');
  return row;
}

function assertEnvelope(payload) {
  if (payload?.schema_version !== 'sleeve_realized.v1' || !SHA.test(payload.generation_id || '')
      || !/^[A-Za-z0-9_-]{1,64}$/.test(payload.account || '')) throw new TypeError('Invalid realized envelope');
}

export async function storeRealized(env, payload) {
  assertEnvelope(payload);
  const db = env.DB, archive = requirePrivateArchive(env);
  const gen = payload.generation_id, account = payload.account;
  const prefix = `sleeves/realized/${account}/${gen}`;
  if (payload.kind === 'archive-status') {
    if (!SHA.test(payload.report_id || '')) throw new TypeError('Invalid report ID');
    const parts = await db.prepare('SELECT part,content_sha FROM sleeve_realized_archive_parts WHERE account=? AND report_id=? ORDER BY part').bind(account, payload.report_id).all();
    return { parts: parts.results };
  }
  if (payload.kind === 'archive') {
    if (!SHA.test(payload.report_id || '') || !Number.isInteger(payload.part) || payload.part < 0 || payload.part > 2000
        || typeof payload.data !== 'string' || payload.data.length > 300_000) throw new TypeError('Invalid report archive part');
    const bytes = Uint8Array.from(atob(payload.data), c => c.charCodeAt(0));
    if (await sha256Hex(bytes) !== payload.content_sha) throw new TypeError('Archive checksum mismatch');
    const existing = await db.prepare('SELECT content_sha FROM sleeve_realized_archive_parts WHERE account=? AND report_id=? AND part=?').bind(account, payload.report_id, payload.part).first();
    if (existing && existing.content_sha !== payload.content_sha) throw new TypeError('Immutable archive part changed');
    if (existing) return { archived: true, duplicate: true, part: payload.part };
    await archive.put(`sleeves/realized/reports/${account}/${payload.report_id}/${String(payload.part).padStart(5, '0')}`, bytes,
      { customMetadata: { sha256: payload.content_sha, format: 'gzip-part' } });
    await db.prepare('INSERT OR IGNORE INTO sleeve_realized_archive_parts VALUES (?,?,?,?,?)').bind(account, payload.report_id, payload.part, payload.content_sha, bytes.length).run();
    return { archived: true, part: payload.part };
  }
  if (payload.kind === 'begin') {
    const manifest = payload.manifest;
    if (!manifest || !validDate(manifest.through) || !Array.isArray(manifest.batch_hashes)
      || manifest.batch_hashes.length > 2000 || manifest.batch_hashes.some(x => !SHA.test(x))
      || !Number.isSafeInteger(manifest.row_count) || manifest.row_count < 0 || manifest.row_count > 100_000
      || !Array.isArray(manifest.archives) || manifest.archives.length > 1000
      || manifest.archives.some(a => !SHA.test(a.report_id || '') || !Array.isArray(a.part_shas) || a.part_shas.length > 2000 || a.part_shas.some(s => !SHA.test(s)))
      || JSON.stringify(manifest).length > 350_000) throw new TypeError('Invalid history manifest');
    const prior = await db.prepare('SELECT manifest_json FROM sleeve_realized_generations WHERE generation_id=?').bind(gen).first();
    if (prior && canonical(JSON.parse(prior.manifest_json)) !== canonical(manifest)) throw new TypeError('Generation ID reused with different manifest');
    await archive.put(`${prefix}/manifest.json`, canonical(manifest), { httpMetadata: { contentType: 'application/json' } });
    await db.prepare(`INSERT OR IGNORE INTO sleeve_realized_generations(generation_id,account,through_date,state,manifest_json,created_at)
      VALUES (?,?,?,'staging',?,?)`).bind(gen, account, manifest.through, canonical(manifest), new Date().toISOString()).run();
    return { staged: true };
  }
  const generation = await db.prepare('SELECT * FROM sleeve_realized_generations WHERE generation_id=? AND account=?').bind(gen, account).first();
  if (!generation) throw new TypeError('Begin this generation before uploading records');
  const manifest = JSON.parse(generation.manifest_json);
  if (payload.kind === 'batch') {
    if (!Number.isInteger(payload.batch_index) || payload.batch_index < 0 || payload.batch_index >= manifest.batch_hashes.length
      || !Array.isArray(payload.records) || payload.records.length > 100) throw new TypeError('Invalid record batch');
    const sha = await sha256Hex(new TextEncoder().encode(canonical(payload.records)));
    if (sha !== manifest.batch_hashes[payload.batch_index]) throw new TypeError('Record batch checksum mismatch');
    const old = await db.prepare('SELECT content_sha FROM sleeve_realized_batches WHERE generation_id=? AND batch_index=?').bind(gen, payload.batch_index).first();
    if (old) {
      if (old.content_sha !== sha) throw new TypeError('Batch identity conflict');
      return { duplicate: true };
    }
    if (generation.state !== 'staging') throw new TypeError('Completed generations are immutable');
    for (const row of payload.records) validateRecord(row, account);
    await archive.put(`${prefix}/batch-${payload.batch_index}.json`, canonical(payload.records), { httpMetadata: { contentType: 'application/json' } });
    const statements = payload.records.map(row => db.prepare(`INSERT INTO sleeve_realized_records
      (generation_id,record_id,owner,trade_date,settlement_date,settlement_status,ticker,payload_json) VALUES (?,?,?,?,?,?,?,?)`)
      .bind(gen, row.record_id, row.owner, row.trade_date, row.settlement_date, row.settlement_status, row.ticker.toUpperCase(), canonical(row)));
    const grouped = new Map();
    for (const row of payload.records) {
      const key = canonical([row.owner, row.trade_date, row.settlement_date || '', row.settlement_status, row.ticker.toUpperCase()]);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(row);
    }
    for (const [key, rows] of grouped) {
      const [owner, trade, settle, state, ticker] = JSON.parse(key);
      statements.push(db.prepare('INSERT INTO sleeve_realized_daily VALUES (?,?,?,?,?,?,?,?)')
        .bind(gen, owner, trade, settle, state, ticker, canonical(summarize(rows)), payload.batch_index));
    }
    statements.push(db.prepare('INSERT INTO sleeve_realized_batches VALUES (?,?,?,?)').bind(gen, payload.batch_index, sha, payload.records.length));
    await db.batch(statements);
    return { staged: true, records: payload.records.length };
  }
  if (payload.kind !== 'complete') throw new TypeError('Unknown realized operation');
  const batches = await db.prepare('SELECT batch_index,content_sha FROM sleeve_realized_batches WHERE generation_id=? ORDER BY batch_index').bind(gen).all();
  if (batches.results.length !== manifest.batch_hashes.length
    || batches.results.some((b, i) => b.batch_index !== i || b.content_sha !== manifest.batch_hashes[i])) throw new TypeError('Incomplete generation: missing batches');
  if (generation.state === 'complete') return { duplicate: true, complete: true };
  for (const source of manifest.archives) {
    const parts = await db.prepare('SELECT part,content_sha FROM sleeve_realized_archive_parts WHERE account=? AND report_id=? ORDER BY part').bind(account, source.report_id).all();
    if (parts.results.length !== source.part_shas.length || parts.results.some((p, i) => p.part !== i || p.content_sha !== source.part_shas[i])) throw new TypeError('Original source archive is incomplete');
  }
  const count = await db.prepare('SELECT COUNT(*) AS count FROM sleeve_realized_records WHERE generation_id=?').bind(gen).first();
  if (Number(count.count) !== manifest.row_count) throw new TypeError('Published record count does not match manifest');
  // Daily totals were calculated from validated rows inside each atomic batch.
  // Completion never buffers the complete financial history in Worker memory.
  await db.batch([
    db.prepare("UPDATE sleeve_realized_generations SET state='complete',completed_at=CURRENT_TIMESTAMP WHERE generation_id=?").bind(gen),
    db.prepare(`INSERT INTO sleeve_realized_current(account,generation_id,through_date,prepared_at,source_generated) VALUES (?,?,?,?,?)
      ON CONFLICT(account) DO UPDATE SET generation_id=excluded.generation_id,through_date=excluded.through_date,
        prepared_at=excluded.prepared_at,source_generated=excluded.source_generated,published_at=CURRENT_TIMESTAMP
      WHERE excluded.through_date>sleeve_realized_current.through_date OR
        (excluded.through_date=sleeve_realized_current.through_date AND
          (excluded.source_generated>sleeve_realized_current.source_generated OR
           (excluded.source_generated=sleeve_realized_current.source_generated AND excluded.prepared_at>=sleeve_realized_current.prepared_at)))`)
      .bind(account, gen, manifest.through, generation.created_at, manifest.source_generated || `${manifest.through}T00:00:00`),
  ]);
  return { complete: true, records: Number(count.count) };
}

export async function loadRealized(db, params) {
  const owner = params.get('owner') || 'drew';
  if (!['drew', 'michael'].includes(owner)) throw new TypeError('owner must be drew or michael');
  const account = params.get('account');
  const refs = account
    ? await db.prepare('SELECT * FROM sleeve_realized_current WHERE account=?').bind(account).all()
    : await db.prepare('SELECT * FROM sleeve_realized_current ORDER BY account LIMIT 2').all();
  if (!refs.results.length) return { status: 'not_ingested', owner, records: [], summary: null, coverage: null };
  if (refs.results.length > 1) throw new TypeError('Select an account for realized history');
  const ref = refs.results[0], generationId = params.get('generation') || ref.generation_id;
  const generation = await db.prepare("SELECT * FROM sleeve_realized_generations WHERE generation_id=? AND account=? AND state='complete'")
    .bind(generationId, ref.account).first();
  if (!generation) throw new TypeError('History generation is unavailable; refresh the view');
  const manifest = JSON.parse(generation.manifest_json), through = manifest.through;
  const from = params.get('from') || `${through.slice(0, 4)}-01-01`, to = params.get('to') || through;
  if (!validDate(from) || !validDate(to) || from > to) throw new TypeError('Choose a valid date interval');
  const basis = params.get('basis') || 'trade_date';
  if (!['trade_date', 'settlement_date'].includes(basis)) throw new TypeError('Invalid date basis');
  const status = params.get('settlement') || 'all';
  if (!['all', 'pending', 'date_reached', 'unknown'].includes(status)) throw new TypeError('Invalid settlement status');
  const ticker = (params.get('ticker') || '').trim().toUpperCase();
  if (ticker.length > 100) throw new TypeError('Ticker is too long');
  const limit = Math.min(100, Math.max(1, Number.parseInt(params.get('limit') || '50', 10) || 50));
  const filters = { generation: generationId, owner, from, to, basis, status, ticker };
  const where = ['generation_id=?', 'owner=?', `${basis}>=?`, `${basis}<=?`], args = [generationId, owner, from, to];
  if (status !== 'all') { where.push('settlement_status=?'); args.push(status); }
  if (ticker) { where.push('ticker=?'); args.push(ticker); }
  const daily = await db.prepare(`SELECT payload_json FROM sleeve_realized_daily WHERE ${where.join(' AND ')}`).bind(...args).all();
  const summary = summarize(daily.results.map(r => JSON.parse(r.payload_json)));
  const pageWhere = [...where], pageArgs = [...args];
  if (params.get('cursor')) {
    let cursor;
    try { cursor = JSON.parse(atob(params.get('cursor'))); } catch { throw new TypeError('Invalid history cursor'); }
    if (canonical(cursor.filters) !== canonical(filters) || !validDate(cursor.date) || typeof cursor.id !== 'string' || cursor.id.length > 180) throw new TypeError('Cursor does not match the selected history');
    pageWhere.push(`(${basis}<? OR (${basis}=? AND record_id<?))`); pageArgs.push(cursor.date, cursor.date, cursor.id);
  }
  const page = await db.prepare(`SELECT record_id,${basis} AS page_date,payload_json FROM sleeve_realized_records
    WHERE ${pageWhere.join(' AND ')} ORDER BY ${basis} DESC,record_id DESC LIMIT ?`).bind(...pageArgs, limit + 1).all();
  const more = page.results.length > limit, rows = page.results.slice(0, limit), last = rows.at(-1);
  const unresolvedArgs = [...args]; unresolvedArgs[1] = 'unallocated';
  const unresolved = await db.prepare(`SELECT payload_json FROM sleeve_realized_daily WHERE ${where.join(' AND ')}`)
    .bind(...unresolvedArgs).all();
  return { status: 'available', owner, account: ref.account, generation_id: generationId, through,
    from, to, basis, settlement: status, ticker, summary, coverage: manifest.coverage,
    reconciliation: manifest.reconciliation, unresolved: summarize(unresolved.results.map(r => JSON.parse(r.payload_json))),
    records: rows.map(r => JSON.parse(r.payload_json)),
    next_cursor: more ? btoa(JSON.stringify({ filters, date: last.page_date, id: last.record_id })) : null };
}
