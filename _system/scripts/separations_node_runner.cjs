// Node runner for the separations UI (dashboard/separations-viz.js and the
// split-off detail row in dashboard/special-situations-viz.js). Driven by
// test_separations_ui.py; prints one JSON object per action.
global.window = global;
require('../../dashboard/separations-viz.js');
require('../../dashboard/special-situations-viz.js');

const ATTACH = {
  roles: [{
    separation_id: 'sep:jnj-kvue-2023', role: 'parent', kind: 'split_off', status: 'offer_open',
    counterparty: 'KVUE', ends: '2023-08-23', ends_label: 'Settlement 2023-08-23',
    flow: { pct_of_float_base: -3.4, pct_of_adv_days: 1.8, window_end: '2023-09-08', confidence: 'estimate' },
  }],
  odd_lot: { eligible_owners: ['drew'], expiration: '2023-08-18' },
};

const FLOW_BLOCK = {
  side: 'spinco', ticker: 'KVUE', run_date: '2026-10-11', status: 'ok', float_flag: 'float_adj',
  pct_of_float_low: -2.1, pct_of_float_base: -3.4, pct_of_float_high: -4.9, pct_of_adv_days: 1.8,
  window_start: '2023-08-23', window_end: '2023-09-08',
  legs: [
    { leg: 'arb_unwind_sale', direction: 'sell', shares_base: -51000000, pct_of_float_base: -3.4,
      window_start: '2023-08-23', window_end: '2023-09-08', confidence: 'estimate',
      source: 'parent_shares_accepted x final_ratio x arb_share', reason: null },
    { leg: 'mandate_mismatch_sale', direction: 'sell', shares_base: null, pct_of_float_base: null,
      confidence: 'n_a', reason: 'no passive share per name until 13F classification lands' },
  ],
};

const SPREAD = {
  basis: 'filing_formula', as_of: '2026-10-11', parent_price: 170.0, spinco_price: 23.0,
  implied_ratio: 7.9412, upper_limit_binding: false, realized_discount_pct: 7.0,
  days_to_settlement: 12, annualized_spread_pct: 212.9,
  odd_lot_payoff_per_99: { gain_usd: 1177.0, gain_pct: 7.0 },
  proration: { low: 0.15, base: 0.25, high: 0.40, basis: 'reference_set' },
  holder_expected_gain_pct: { low: 1.0, base: 1.75, high: 2.8 },
};

const PAYLOAD = {
  schema_version: 'special_situations.v1', generated_at: '2026-10-11T12:00:00Z',
  definition: 'The situation ends.',
  caption: 'Forced selling is a research trigger and a timing input.',
  lanes: [
    { id: 'spinoffs', label: 'Spinoffs', source: 'Greenblatt' },
    { id: 'split_offs', label: 'Split-offs and exchange offers', source: 'Greenblatt' },
    { id: 'mergers', label: 'Merger securities', source: 'Greenblatt' },
  ],
  counts: { ranked: { split_offs: 1 } },
  rows: [{
    id: 'ss:split-1', lane: 'split_offs', lanes: ['split_offs'], book: 'ranked', ticker: 'JNJ', company: 'Johnson & Johnson',
    what: 'Exchange offer: JNJ for KVUE', ends: '2023-08-23', ends_label: 'Settlement 2023-08-23',
    annualized_spread: '212.9% (7.0% over 12 days)', evidence_url: 'https://www.sec.gov/x', evidence_label: 'SC TO-I',
    evidence_kind: 'filing', next: 'Tender the odd lot before 2023-08-18.',
    separation_id: 'sep:jnj-kvue-2023', spread: SPREAD,
    flow: { pct_of_float_base: -3.4, pct_of_adv_days: 1.8, window_start: '2023-08-23', window_end: '2023-09-08', confidence: 'estimate' },
    terms_summary: 'Exchange at a 7% discount, upper limit 8.0525, odd-lot priority, three-session valuation period.',
  }, {
    id: 'ss:merger-1', lane: 'mergers', lanes: ['mergers'], book: 'ranked', ticker: 'ABC', company: 'ABC',
    what: 'Plain merger row <script>alert(1)</script>', ends_label: 'Not stated', annualized_spread: null, next: '',
  }],
  discovery: [], history: [],
};

const XSS = '<img src=x onerror=alert(1)>';

const action = process.argv[2] || '';
const out = (obj) => process.stdout.write(JSON.stringify(obj));
const V = window.SeparationsViz;
const S = window.SpecialSituationsViz;

if (action === 'card') {
  out({ html: V.renderTickerCard(ATTACH) });
} else if (action === 'card-empty') {
  out({ none: V.renderTickerCard(null), empty: V.renderTickerCard({}), noroles: V.renderTickerCard({ roles: [], odd_lot: { eligible_owners: ['drew'] } }) });
} else if (action === 'badge') {
  out({
    eligible: V.renderOddLotBadge(ATTACH),
    none: V.renderOddLotBadge({ odd_lot: { eligible_owners: [], expiration: '2023-08-18' } }),
    missing: V.renderOddLotBadge(null),
    no_expiry: V.renderOddLotBadge({ odd_lot: { eligible_owners: ['michael'] } }),
  });
} else if (action === 'legs') {
  out({
    full: V.renderFlowLegs(FLOW_BLOCK),
    na: V.renderFlowLegs({ status: 'n_a', reason: 'no float' }),
    empty: V.renderFlowLegs({ legs: [] }),
    missing: V.renderFlowLegs(null),
  });
} else if (action === 'escape') {
  const attach = {
    roles: [{ role: 'parent', kind: XSS, status: XSS, counterparty: XSS, ends_label: XSS, separation_id: XSS,
      flow: { pct_of_float_base: -1, confidence: XSS, window_end: XSS,
        legs: [{ leg: XSS, direction: XSS, confidence: XSS, reason: XSS, window_start: XSS }] } }],
    odd_lot: { eligible_owners: [XSS], expiration: XSS },
  };
  out({ card: V.renderTickerCard(attach), badge: V.renderOddLotBadge(attach) });
} else if (action === 'desk') {
  // The desk renders the split-offs lane with the detail row open on the JNJ row.
  const closed = S.render(PAYLOAD, { lane: 'split_offs' });
  // open the row through the same state the click handler drives
  const container = {
    querySelectorAll: (sel) => (sel === '[data-situation-open]'
      ? [{ dataset: { situationOpen: 'ss:split-1' }, addEventListener: (_, fn) => fn() }]
      : []),
    querySelector: () => null,
  };
  S.attach(container, PAYLOAD, { onChange() {} });
  const open = S.render(PAYLOAD, { lane: 'split_offs' });
  const mergers = S.render(PAYLOAD, { lane: 'mergers' });
  out({ closed, open, mergers });
} else if (action === 'desk-empty') {
  out({ html: S.render({ rows: [], discovery: [], history: [], lanes: [], error: 'Special situations data 404' }, { lane: 'split_offs' }) });
} else {
  process.stderr.write(`unknown action: ${action}`);
  process.exit(2);
}
