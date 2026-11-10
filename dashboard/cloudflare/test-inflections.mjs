import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const dashboard = new URL('../', import.meta.url);
const context = { window: {}, Date, Intl, Map, Set, console, setTimeout, clearTimeout };
vm.createContext(context);
vm.runInContext(fs.readFileSync(new URL('inflections-viz.js', dashboard), 'utf8'), context);
const api = context.window.InflectionsViz;
const NOW = Date.parse('2026-11-10T12:00:00Z');
const signal = (extra = {}) => ({ id: 'revenue', metric: 'revenues', label: 'Revenue', kind: 'business', domain: 'revenue', source: 'sec_fundamentals', effect: 'improving', support: 'confirmed', support_basis: 'two_quarters', candidate: true, reasons: [], primary: true, max_age_days: 200, period: '2026-09-30', summary: 'Revenue growth improved.', comparison: 'Prior 10%; latest 20%.', members: [], ...extra });
const company = (ticker = 'HELD', extra = {}) => ({ ticker, company: ticker === 'HELD' ? 'Held Company' : 'Tracked Company', signals: [signal()], latest_period: '2026-09-30', data_period: '2026-09-30', max_age_days: 200, signal_count: 1, ...extra });
const overview = (rows = [company(), company('WATCH')]) => ({ schema_version: 'inflections.v1', snapshot_id: 'snapshot', source_generated_at: '2026-11-09T00:00:00Z', max_age_days: 200, signals_ref: 'data/inflection_signals.json', companies: rows });
const tickers = [{ ticker: 'HELD', company: 'Held Company', in_holdings: true }, { ticker: 'WATCH', company: 'Tracked Company', in_holdings: false }];
const select = (data = overview(), state = {}, rows = tickers, index = null) => api.select(data, state, rows, index, NOW);

test('holdings scope excludes a tracked non-holding; tracked scope includes both', () => {
  assert.equal(select().total, 1);
  assert.equal(select().rows[0].ticker, 'HELD');
  assert.equal(select(overview(), { scope: 'tracked' }).total, 2);
});

test('missing holdings metadata fails closed instead of showing all companies as holdings', () => {
  const selected = select(overview(), {}, []);
  assert.equal(selected.total, 0);
  assert.equal(selected.holdingsAvailable, false);
  assert.match(api.render(overview(), {}, { now: NOW }), /Holdings membership is unavailable/);
});

test('current tracking membership excludes cached strays and recognizes explicit aliases', () => {
  const selected = select(overview([company('BRK-B', { aliases: ['BRK.B'] }), company('STRAY')]), { scope: 'tracked' }, [{ ticker: 'BRK.B', in_holdings: true }]);
  assert.equal(selected.total, 1);
  assert.equal(selected.rows[0].ticker, 'BRK-B');
});

test('company-name search, direction and coverage use the same selected universe', () => {
  const selected = select(overview(), { scope: 'tracked', query: 'Held Company', direction: 'improving' });
  assert.equal(selected.total, 1);
  assert.equal(selected.coverage.total, 1);
  assert.equal(selected.coverage.improving, 1);
  const html = api.render(overview(), { scope: 'tracked', query: 'Held Company' }, { tickers, now: NOW });
  assert.doesNotMatch(html, /data-inf-company="WATCH"/);
});

test('opposing business metrics stay Mixed; persistence filtering does not hide disagreement', () => {
  const mixed = company('HELD', { signals: [signal(), signal({ id: 'cash', metric: 'cfo', label: 'Operating cash flow', domain: 'cash_flow', effect: 'weakening', support: 'emerging' })] });
  const selected = select(overview([mixed]), { persistence: 'confirmed' });
  assert.equal(selected.total, 1);
  assert.equal(selected.rows[0].direction, 'mixed');
  assert.match(selected.rows[0].headline, /weakening/);
});

test('a company-history conflict for the same metric is explained as a disagreement', () => {
  const row = company('HELD', { signals: [signal(), signal({ id: 'history', metric: 'revenues', kind: 'history', effect: 'weakening' })] });
  assert.match(api.deriveCompany(row, NOW).headline, /disagree/);
});

test('stale, future, unknown and artifact evidence cannot confirm a company', () => {
  for (const extra of [{ period: '2020-01-01' }, { period: '2027-01-01' }, { period: null }, { reasons: ['volatile_base'] }, { reasons: ['source_stale'] }]) {
    const row = company('HELD', { signals: [signal(extra)], data_period: null });
    assert.equal(api.deriveCompany(row, NOW).direction, 'insufficient');
    assert.equal(select(overview([row]), { persistence: 'confirmed' }).total, 0);
  }
});

test('no clear shift is different from insufficient data and is discoverable', () => {
  const quiet = company('HELD', { signals: [] });
  assert.equal(api.deriveCompany(quiet, NOW).direction, 'no_shift');
  assert.equal(select(overview([quiet])).total, 0);
  assert.equal(select(overview([quiet])).coverage.no_shift, 1);
  assert.equal(select(overview([quiet]), { includeQuiet: true }).total, 1);
  assert.equal(select(overview([quiet]), { direction: 'no_shift' }).total, 1);
});

test('composite components are not counted a second time', () => {
  const row = company('HELD', { signals: [signal({ metric: 'core_business', members: ['revenues'] }), signal()] });
  assert.equal(api.deriveCompany(row, NOW).signals.length, 1);
});

test('trailing-year or legacy confirmation never claims two-quarter persistence', () => {
  for (const basis of ['trailing_year', 'unspecified']) {
    const row = company('HELD', { signals: [signal({ support_basis: basis })] });
    assert.equal(select(overview([row]), { persistence: 'two_quarters' }).total, 0);
    assert.equal(select(overview([row]), { persistence: 'confirmed' }).total, 1);
    const html = api.render(overview([row]), {}, { tickers, now: NOW });
    assert.doesNotMatch(html, /class="inf-support">Two-quarter/);
    assert.match(html, basis === 'trailing_year' ? /Trailing-year support/ : /method not supplied/);
  }
});

test('an undated contextual observation is labeled, never presented as confirmed business data', () => {
  const observation = { ticker: 'HELD', ...signal({ candidate: false, kind: 'expectations', support: 'observation', period: null, reasons: ['period_unavailable'] }) };
  const index = { signals: [observation] };
  assert.equal(select(overview(), { view: 'signals' }, tickers, index).total, 1);
  assert.equal(select(overview(), { view: 'signals', persistence: 'confirmed' }, tickers, index).total, 0);
  assert.match(api.render(overview(), { view: 'signals' }, { tickers, signalIndex: index, now: NOW }), /Reporting period unavailable/);
});

test('all companies remain reachable beyond the old 120-row cutoff', () => {
  const rows = Array.from({ length: 130 }, (_, i) => company('C' + String(i).padStart(3, '0')));
  const data = overview(rows);
  const selected = select(data, { scope: 'tracked', page: 5 }, []);
  assert.equal(selected.total, 130);
  assert.equal(selected.pages, 6);
  assert.equal(selected.rows.length, 5);
  assert.equal(selected.rows.at(-1).ticker, 'C129');
  const html = api.render(data, { scope: 'tracked', page: 5 }, { now: NOW });
  assert.match(html, /Showing 126–130 of 130/);
});

test('pagination clamps after a search narrows the result set', () => {
  const selected = select(overview(), { scope: 'tracked', page: 100, query: 'HELD' });
  assert.equal(selected.page, 0);
  assert.equal(selected.rows.length, 1);
});

test('signal explorer filters by source, category and current persistence', () => {
  const index = { signals: [
    { ticker: 'HELD', ...signal() },
    { ticker: 'HELD', ...signal({ id: 'peer', kind: 'peers', candidate: false, source: 'peer_relative', support: 'observation' }) },
    { ticker: 'WATCH', ...signal({ id: 'watch' }) },
  ] };
  assert.equal(select(overview(), { view: 'signals', kind: 'peers' }, tickers, index).total, 1);
  assert.equal(select(overview(), { view: 'signals', source: 'sec_fundamentals', persistence: 'confirmed' }, tickers, index).total, 1);
  assert.equal(select(overview(), { view: 'signals', kind: 'peers', persistence: 'confirmed' }, tickers, index).total, 0);
});

test('suppressed data is explicit and never passes the two-quarter filter', () => {
  const index = { signals: [{ ticker: 'HELD', ...signal({ reasons: ['source_stale'] }) }] };
  assert.equal(select(overview(), { view: 'signals' }, tickers, index).total, 0);
  assert.equal(select(overview(), { view: 'signals', includeSuppressed: true }, tickers, index).total, 1);
  assert.equal(select(overview(), { view: 'signals', includeSuppressed: true, persistence: 'confirmed' }, tickers, index).total, 0);
});

test('source snapshot and reporting dates remain separate', () => {
  const html = api.render(overview(), {}, { tickers, now: NOW });
  assert.match(html, /Source snapshot Nov 9, 2026/);
  assert.match(html, /Sep 30, 2026/);
  assert.match(html, /Period end/);
});

test('change badges expire and do not turn old observations into new ones', () => {
  const recent = company('HELD', { change: { kind: 'changed', observed_at: '2026-11-09' } });
  const old = company('HELD', { change: { kind: 'new', observed_at: '2026-10-01' } });
  assert.match(api.render(overview([recent]), {}, { tickers, now: NOW }), /Changed · observed/);
  assert.doesNotMatch(api.render(overview([old]), {}, { tickers, now: NOW }), /New · observed/);
});

test('HTML, query text and source links are escaped', () => {
  const row = company('HELD', { company: '<img src=x onerror=alert(1)>', signals: [signal({ summary: '<script>bad</script>' })] });
  const html = api.render(overview([row]), { scope: 'tracked', query: '"<script>' }, { now: NOW });
  assert.doesNotMatch(html, /<script>|onerror=/);
  const detail = api.renderEvidence(row, [{ ...signal(), raw: { source_url: 'javascript:alert(1)', evidence_ref: '../bad' } }], NOW);
  assert.doesNotMatch(detail, /href="javascript:|href=.*\.\.\/bad/);
});

test('reported levels are labeled and QDEL research is closed until requested', () => {
  const detail = api.renderEvidence(company('QDEL'), [{ ...signal(), raw: { metric: 'revenues', points: [{ period: '2026-09-30', value: 200 }] } }], NOW);
  assert.match(detail, /Reported levels/);
  assert.match(detail, /filing units; not growth rates/);
  assert.match(detail, /data-inf-model>/);
  assert.doesNotMatch(detail, /data-inf-model open|resp-legend/);
});

test('calendar-quarter and monthly periods are parsed accurately', () => {
  assert.equal(new Date(api.periodTime('2026-Q1')).toISOString().slice(0, 10), '2026-03-31');
  assert.equal(new Date(api.periodTime('2026-02')).toISOString().slice(0, 10), '2026-02-28');
  assert.equal(api.periodTime('2026-02-31'), null);
  assert.equal(api.periodTime('2026-Q5'), null);
});

test('SPA loads the compact overview and mounts independent Inflections controls', () => {
  const html = fs.readFileSync(new URL('index.html', dashboard), 'utf8');
  assert.match(html, /src="inflections-viz\.js/);
  assert.match(html, /inflections: \['inflection_overview'\]/);
  assert.doesNotMatch(html, /inflections: \['kpi_trends'/);
  assert.match(html, /InflectionsViz\.mount\(inflectionsRoot/);
  assert.match(html, /onResearch: ticker =>/);
  assert.doesNotMatch(html, /data-inflection-tier/);
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) if (!/\bsrc=/.test(match[1])) new vm.Script(match[2]);
});

test('generated projection is compact, consistent and contains only the tracked universe', () => {
  const file = new URL('data/inflection_overview.json', dashboard);
  if (!fs.existsSync(file)) return;
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.equal(data.schema_version, 'inflections.v1');
  assert.ok(data.companies.length > 100);
  assert.ok(fs.statSync(file).size < 2_000_000);
  assert.equal(new Set(data.companies.map(c => c.ticker)).size, data.companies.length);
  assert.ok(data.companies.every(c => !('in_holdings' in c)));
  const index = JSON.parse(fs.readFileSync(new URL(data.signals_ref, dashboard), 'utf8'));
  assert.equal(data.snapshot_id, index.snapshot_id);
  for (const c of data.companies) {
    assert.ok(c.signals.every(s => s.candidate && s.reasons.length === 0));
    const evidence = JSON.parse(fs.readFileSync(new URL(c.evidence_ref, dashboard), 'utf8'));
    assert.equal(evidence.snapshot_id, data.snapshot_id);
    assert.ok(Array.isArray(evidence.by_ticker[c.ticker]));
  }
});
