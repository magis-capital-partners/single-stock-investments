const test = require('node:test');
const assert = require('node:assert/strict');
global.window = global;
require('../../../dashboard/search-match.js');
require('../../../dashboard/insights-viz.js');
const ui = window.InsightsViz;
const escape = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const link = (url, label) => `<a href="${escape(url)}">${escape(label)}</a>`;

const LATEST = { id: 'latest', label: 'Latest quarter', quarters: ['2026Q2'], quarterSet: new Set(['2026Q2']), all: false };
const ALL = { id: 'all', label: 'All history', quarters: [], quarterSet: new Set(), all: true };
const TIME = { quarters: [{ id: '2026Q2' }, { id: '2026Q1' }] };

function row(ticker, { buys = [], sells = [], shorts = [], inBook = true } = {}) {
  const funds = [...buys, ...sells, ...shorts];
  const down = sells.length + shorts.length;
  const sentiment = buys.length > down ? 'accumulating' : down > buys.length ? 'reducing' : funds.length ? 'mixed' : 'discussed';
  return {
    ticker, name: `${ticker} Corp`, in_book: inBook, fund_count: funds.length,
    buy_funds: buys.length, sell_funds: sells.length, short_funds: shorts.length,
    net: buys.length - down, sentiment, funds,
    buy_fund_names: buys, sell_fund_names: sells, short_fund_names: shorts,
  };
}

const crowded = Array.from({ length: 70 }, (_, i) => row(`H${String(i).padStart(2, '0')}`, { buys: [`idea:h${i}`] }));
const current = [
  ...crowded,
  row('FLIP', { sells: ['idea:f1', 'idea:f2'] }),
  row('GAIN', { buys: ['idea:g1', 'idea:g2', 'idea:g3'] }),
  row('QUIET'),
  row('OUTSIDE', { buys: ['idea:o1'], inBook: false }),
];
const prior = [
  ...crowded,
  row('FLIP', { buys: ['idea:f1', 'idea:f2'] }),
  row('GAIN', { buys: ['idea:g1'] }),
  row('QUIET', { sells: ['idea:q1'] }),
  row('DROP', { buys: ['idea:d1', 'idea:d2', 'idea:d3'] }),
];
const CONSENSUS = {
  summary: { fund_count: 12 },
  by_quarter: { '2026Q2': { most_discussed: current }, '2026Q1': { most_discussed: prior }, all: { most_discussed: current } },
};

const letter = (quarter, date, positions) => ({ quarter, letter_date: date, positions, evidence_url: 'https://example.com/l.pdf', evidence_label: 'PDF' });
const profile = (id, fund, letters, ourTickers = ['FLIP']) => ({ fund_id: id, fund, manager: '', our_tickers: ourTickers, letters, latest_quarter: letters[0]?.quarter });
const PROFILES = {
  'alder-value': profile('alder-value', 'Alder Value', [letter('2026Q2', '2026-06-30', [{ ticker: 'FLIP', action: 'exit', commentary: 'Sold the rest.' }])]),
  birch: profile('birch', 'Birch Street', [
    letter('2026Q2', '2026-05-15', [{ ticker: 'FLIP', action: 'add', commentary: 'Bought more.' }, { ticker: 'GAIN', action: 'add' }]),
    letter('2026Q2', '2026-06-30', [{ ticker: 'FLIP', action: 'discussed', commentary: 'Still like it.' }]),
  ]),
  cedar: profile('cedar', 'Cedar <Hill>', [letter('2026Q2', '2026-06-30', [{ ticker: 'FLIP', action: 'discussed' }])]),
  dune: profile('dune', 'Dune', [letter('2026Q1', '2026-03-31', [{ ticker: 'FLIP', action: 'short' }])]),
  greenlight: profile('greenlight', 'Greenlight', [letter('2026Q2', '2026-06-30', [{ ticker: 'FLIP', action: 'trim' }])]),
};

const render = (opts = {}) => ui.renderConsensus(CONSENSUS, escape, link, '', {
  quarter: 'latest', period: LATEST, timeModel: TIME, bookOnly: true, fundProfiles: PROFILES, ...opts,
});
const rows = html => html.split('<article class="consensus-signal-row').slice(1);
const tickers = html => rows(html).map(r => r.match(/data-consensus-ticker="([^"]+)"/)[1]);
const rowFor = (html, ticker) => rows(html).find(r => r.includes(`data-consensus-ticker="${ticker}"`));
const ctx = { fundProfiles: PROFILES, period: LATEST, escapeHtml: escape, linkHtml: link, ghRepo: '' };

test('every row renders, with no cap on the list', () => {
  const html = render();
  assert.equal(rows(html).length, 74);
  assert.ok(!tickers(html).includes('OUTSIDE'));
  assert.equal(rows(render({ bookOnly: false })).length, 75);
});

test('a holding every fund dropped stays on the list, labeled as trading stopped', () => {
  const drop = rowFor(render(), 'DROP');
  assert.ok(drop, 'DROP is listed');
  assert.match(drop, /No funds trading it this period/);
  assert.match(drop, /trading stopped/);
  assert.match(drop, /3 &rarr; 0 funds/);
});

test('traded names come first; names with no trades sit under their own divider', () => {
  const html = render();
  assert.deepEqual(tickers(html).slice(0, 2), ['FLIP', 'GAIN']);
  assert.deepEqual(tickers(html).slice(-2), ['DROP', 'QUIET']);
  const [traded, quiet] = html.split('consensus-list-divider');
  assert.equal(rows(traded).length, 72);
  assert.match(quiet, /2 names only discussed, or traded before and quiet now/);
  const breadth = tickers(render({ sortMode: 'breadth' }));
  assert.equal(breadth[0], 'GAIN');
  assert.deepEqual(breadth.slice(-2), ['DROP', 'QUIET']);
});

test('the lens tiles filter the list and show a clearable chip', () => {
  for (const lens of ['reducing', 'reversals']) {
    const html = render({ lens });
    assert.deepEqual(tickers(html), ['FLIP']);
    assert.match(html, new RegExp(`data-consensus-lens="${lens}" aria-pressed="true"`));
    assert.match(html, /class="consensus-chip" data-consensus-lens="all"/);
  }
});

test('going quiet is not a lean reversal', () => {
  const html = render();
  assert.match(html, /<span>Lean reversals<\/span><strong>1<\/strong>/);
  const quiet = rowFor(html, 'QUIET');
  assert.doesNotMatch(quiet, /&rarr; <span class="badge/);
  assert.match(quiet, /trading stopped/);
});

test('all history has no prior period, so change tiles, column and sort are hidden', () => {
  const html = render({ quarter: 'all', period: ALL, lens: 'reversals' });
  assert.doesNotMatch(html, /Lean reversals|Largest deterioration|consensus-signal-change|data-consensus-sort/);
  assert.match(html, /consensus-signal-list no-change/);
  assert.equal(rows(html).length, 73);
});

test('fund trades use readable names, the latest trade, and only the selected period', () => {
  const funds = ui.consensusFundTrades('FLIP', PROFILES, LATEST);
  const byName = Object.fromEntries(funds.map(f => [f.fund, f.latest.group]));
  assert.deepEqual(byName, { 'Alder Value': 'reducing', 'Birch Street': 'adding', 'Cedar <Hill>': 'discussed', Greenlight: 'reducing' });
  assert.equal(funds.find(f => f.fund === 'Birch Street').letters, 2);
});

test('the disclosure groups funds by stance and escapes names before 13F loads', () => {
  const body = ui.renderConsensusFundsBody('FLIP', ctx);
  assert.match(body, /Loading 13F/);
  assert.match(body, /badge-ok">Adding<\/span><span>1 fund</);
  assert.match(body, /badge-bad">Reducing<\/span><span>2 funds</);
  assert.match(body, /Cedar &lt;Hill&gt;/);
  assert.doesNotMatch(body, /idea:|<Hill>/);
});

test('13F join is by whole-word name, so BAMCO does not match Bam', () => {
  const holders = [{ manager_id: 'bamco', name: 'BAMCO' }, { manager_id: 'greenlight-capital', name: 'Greenlight Capital' }];
  const funds = [{ fund_id: 'bam', fund: 'Bam' }, { fund_id: 'greenlight', fund: 'Greenlight' }];
  const unmatched = ui.consensusAttachHolders(funds, holders);
  assert.equal(funds[0].holder, null);
  assert.equal(funds[1].holder.name, 'Greenlight Capital');
  assert.deepEqual(unmatched.map(h => h.name), ['BAMCO']);
});

test('13F size shows book weight, value and share change, plus the ten largest filing-only holders', async () => {
  const fetched = [];
  const filers = Array.from({ length: 12 }, (_, i) => ({ manager_id: `filer-${i}`, name: `Filer ${i}`, weight_pct: i / 10, value_usd: 5e6, change_type: null, shares_delta_pct: null }));
  global.fetch = async url => {
    fetched.push(url);
    return { ok: true, json: async () => ({ period_end: '2026-06-30', holders: [
      { manager_id: 'greenlight-capital', name: 'Greenlight Capital', weight_pct: 2.46, value_usd: 1.2e9, change_type: 'trim', shares_delta_pct: -25.85, filed_at: '2026-08-12' },
      ...filers,
    ] }) };
  };
  await ui.loadConsensusHolderFile('FLIP');
  assert.deepEqual(fetched, ['data/holdings/by_ticker/FLIP.json']);
  const body = ui.renderConsensusFundsBody('FLIP', ctx);
  const greenlight = body.split('<tr>').find(r => r.includes('>Greenlight<'));
  assert.match(greenlight, /2\.5%/);
  assert.match(greenlight, /\$1\.2B/);
  assert.match(greenlight, /&minus;26%/);
  assert.match(body.split('<tr>').find(r => r.includes('>Alder Value<')), /No 13F size on file/);
  assert.match(body, /13F only/);
  assert.equal((body.match(/>Filer \d+</g) || []).length, 10);
  assert.ok(!body.includes('>Filer 0<') && !body.includes('>Filer 1<'), 'smallest filers are cut');
  assert.match(body, /quarter ending 2026-06-30, filed 2026-08-12/);
  assert.match(body, /no share-of-float figure/);
});

test('with no 13F file for a ticker, the size columns are dropped and the note says why', async () => {
  global.fetch = async () => ({ ok: false, json: async () => null });
  await ui.loadConsensusHolderFile('GAIN');
  const body = ui.renderConsensusFundsBody('GAIN', ctx);
  assert.match(body, />Birch Street</);
  assert.doesNotMatch(body, /Share of their 13F book|No 13F size on file/);
  assert.match(body, /No 13F holdings file covers GAIN/);
  assert.match(body, /<th colspan="2">/);
});

test('with no 13F file for a ticker, the size columns are dropped and the note says why', async () => {
  global.fetch = async () => ({ ok: false, json: async () => null });
  await ui.loadConsensusHolderFile('GAIN');
  const body = ui.renderConsensusFundsBody('GAIN', ctx);
  assert.match(body, />Birch Street</);
  assert.doesNotMatch(body, /Share of their 13F book|No 13F size on file/);
  assert.match(body, /No 13F holdings file covers GAIN/);
  assert.match(body, /<th colspan="2">/);
});

test('the fund rail pages 25 at a time, searches, and filters the list to one fund', () => {
  const filler = Object.fromEntries(Array.from({ length: 60 }, (_, i) => {
    const id = `fund-${String(i).padStart(2, '0')}`;
    return [id, profile(id, `Fund ${String(i).padStart(2, '0')}`, [letter('2026Q2', '2026-06-30', [{ ticker: 'H01', action: 'add' }])], [])];
  }));
  const fundProfiles = { ...PROFILES, ...filler };
  const railFunds = html => (html.match(/class="consensus-rail-fund/g) || []).length;
  const first = render({ fundProfiles, bookOnly: false });
  assert.equal(railFunds(first), 25);
  assert.match(first, /<span>1 of 3<\/span>/);
  assert.match(first, /data-consensus-fund-page="0" disabled/);
  assert.equal(railFunds(render({ fundProfiles, bookOnly: false, fundPage: 2 })), 14);
  assert.equal(railFunds(render({ fundProfiles, bookOnly: false, fundQuery: 'birch' })), 1);
  const one = render({ fundProfiles, selectedFundId: 'alder-value' });
  assert.deepEqual(tickers(one), ['FLIP']);
  assert.match(one, /Selected fund/);
  assert.match(one, /Named by Alder Value/);
  assert.match(one, /Its letters name 1 security in this period; 1 is in this list\./);
});
