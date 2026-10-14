// Node runner for the desk briefs block (dashboard/desk-briefs-viz.js). Driven by
// _system/scripts/tests/test_desk_briefs.py; prints one JSON object per action.
global.window = global;
require('../../dashboard/desk-briefs-viz.js');

const XSS = '<img src=x onerror=alert(1)>';

const ITEM = {
  ticker: 'MDT',
  headline: 'MiniMed exchange offer expired 2026-10-09 with the upper limit in effect.',
  one_number: 'final exchange ratio 4.5939',
  lane: 'split_offs',
  evidence: [
    { kind: 'filing', ref: 'SC TO-I/A 0001628280-26-065406', url: 'https://www.sec.gov/Archives/edgar/data/1613103/000162828026065406/mdt-amendedno2scheduleissu.htm' },
    { kind: 'dashboard', ref: 'dashboard/data/separations.json row sep:mdt-mmed-2026', url: null },
  ],
  confidence: 'filing',
  next: 'Read the final-results 8-K.',
  handoff: null,
};

const DOC = {
  schema_version: 'desk_briefs.v1',
  generated_at: '2026-10-12T12:00:00Z',
  caption: 'Ranked output from the Magis desk bots. Research only.',
  desks: [
    {
      desk: 'special_situations', desk_label: 'Special Situations', owner: 'drew', author: 'claude-drew-special-situations',
      as_of: '2026-10-12', age_hours: 12.0, stale: false, path: '_system/data/desk_briefs/special_situations/2026-10-12.json',
      items: [ITEM, { ...ITEM, ticker: 'unresolved', lane: 'forced_sellers', handoff: 'tape_index', confidence: 'provider',
        headline: 'MiniMed (MMED): modelled selling of 27.7% of float.', one_number: '-27.7% of float (estimate)' }],
      inputs_read: [
        { path: 'dashboard/data/separations.json', generated_at: '2026-10-12T00:04:30Z', age_hours_at_read: 23.9, exists: true },
        { path: 'dashboard/data/missing.json', generated_at: null, age_hours_at_read: null, exists: false },
      ],
      screens_empty: ['odd_lot_alerts', 'rights_offering'],
      notes: 'Seed brief.',
    },
    {
      desk: 'activism', desk_label: 'Activism', owner: 'michael', author: 'grok-michael-activism',
      as_of: '2026-10-01', age_hours: 276.0, stale: true, path: '_system/data/desk_briefs/activism/2026-10-01.json',
      items: [{ ...ITEM, ticker: 'FOX', lane: '13d', headline: 'LGC Holdco 13D/A: stake unchanged, purpose amended.', one_number: 'stake 7.1%' }],
      inputs_read: [{ path: 'dashboard/data/activist_feed.json', generated_at: '2026-09-30T14:08:48Z', age_hours_at_read: 33.9, exists: true }],
      screens_empty: [],
      notes: null,
    },
  ],
  items_flat: [],
  desks_without_brief: ['fundamentals', 'nol_tax_assets', 'tape_index', 'stahl', 'short_selling'],
  desk_labels: { special_situations: 'Special Situations', activism: 'Activism', fundamentals: 'Fundamentals', nol_tax_assets: 'NOL and Tax Assets', tape_index: 'Index, forced flow and tape', stahl: 'Murray Stahl', short_selling: 'Short Selling' },
  counts: { briefs: 2, items: 3, files: 2, by_desk: { special_situations: 2, activism: 1 }, by_owner: { drew: 2, michael: 1 } },
  health: { status: 'degraded', structural_errors: [], problems: ['activism brief is 12 days old (2026-10-01)'], warnings: [], stale_days: 7, checked_at: '2026-10-12T12:00:00Z' },
  research_only: true, in_base_irr: false, authority: 'none',
};

const action = process.argv[2] || '';
const out = (obj) => process.stdout.write(JSON.stringify(obj));
const V = window.DeskBriefsViz;

function clickers(attr, value) {
  // Minimal container: attach() wires the one chip we want to "click".
  return {
    querySelectorAll: (sel) => (sel === `[${attr}]`
      ? [{ dataset: attr === 'data-desk-brief-owner' ? { deskBriefOwner: value } : { deskBriefDesk: value }, addEventListener: (_, fn) => fn() }]
      : []),
    querySelector: () => null,
  };
}

if (action === 'render') {
  out({ html: V.render(DOC, { owner: 'all', desk: 'all' }) });
} else if (action === 'filter') {
  const all = V.render(DOC, { owner: 'all', desk: 'all' });
  let changed = 0;
  V.attach(clickers('data-desk-brief-owner', 'michael'), DOC, { onChange() { changed += 1; } });
  const michael = V.render(DOC);
  V.attach(clickers('data-desk-brief-desk', 'special_situations'), DOC, { onChange() { changed += 1; } });
  const none = V.render(DOC); // owner michael + desk special_situations -> nothing matches
  const reset = V.render(DOC, { owner: 'all', desk: 'all' });
  out({ all, michael, none, reset, changed });
} else if (action === 'empty') {
  out({
    missing: V.render(null, { owner: 'all', desk: 'all' }),
    error: V.render({ desks: [], desks_without_brief: [], error: 'Desk briefs data 404' }, { owner: 'all', desk: 'all' }),
    nodesks: V.render({ desks: [] }, { owner: 'all', desk: 'all' }),
  });
} else if (action === 'escape') {
  const nasty = JSON.parse(JSON.stringify(DOC));
  const d = nasty.desks[0];
  d.author = XSS; d.owner = XSS; d.desk = XSS; d.as_of = XSS; d.path = XSS; d.notes = XSS; d.screens_empty = [XSS];
  d.items[0] = { ticker: XSS, headline: XSS, one_number: XSS, lane: XSS, confidence: XSS, next: XSS, handoff: XSS,
    evidence: [{ kind: XSS, ref: XSS, url: 'javascript:alert(1)' }, { kind: 'news', ref: XSS, url: `https://example.com/${XSS}` }] };
  d.inputs_read = [{ path: XSS, generated_at: XSS, age_hours_at_read: 'x', exists: false }];
  nasty.caption = XSS; nasty.generated_at = XSS; nasty.desks_without_brief = [XSS];
  nasty.health = { status: XSS, structural_errors: [XSS], problems: [XSS] };
  nasty.desk_labels = { [XSS]: XSS };
  out({ html: V.render(nasty, { owner: 'all', desk: 'all' }) });
} else {
  process.stderr.write(`unknown action: ${action}`);
  process.exit(2);
}
