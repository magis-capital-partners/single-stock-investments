const test = require('node:test');
const assert = require('node:assert/strict');
global.window = global;
require('../../../dashboard/search-match.js');
require('../../../dashboard/insights-viz.js');
const ui = window.InsightsViz;
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const event = { id: 'len-buy', ticker: 'LEN', title: 'Berkshire purchase in LEN', summary: 'A purchase',
  actor_name: 'Berkshire <script>', issuer_ticker: 'LEN', relationship: 'direct',
  economic_channel: 'ownership', tier: 'signal', direction: 'bullish', feed_eligible: true,
  observed_at: '2026-09-21', published_at: '2026-09-21', processed_at: '2026-10-20', in_holdings: true };

test('card separates actor, target and driver and escapes source content', () => {
  const html = ui.renderDecisionEventCard(event, escape, () => '', '', {});
  assert.match(html, /Actor: Berkshire &lt;script&gt;/);
  assert.match(html, /Target: LEN/);
  assert.match(html, /Driver: ownership/);
  assert.doesNotMatch(html, /<script>/);
});
test('review flags remove misleading signals without mutating source events', () => {
  for (const reason of ['wrong_company', 'wrong_interpretation', 'already_known']) {
    const result = ui.applyEventFeedback(event, { reason });
    assert.notEqual(result.tier, 'signal');
    assert.equal(result.direction, 'neutral');
  }
  assert.equal(event.tier, 'signal');
  assert.equal(ui.applyEventFeedback(event, undefined), event);
});
test('workflow feedback affects real feed filtering', () => {
  const options = { eventRange: 'all', eventScope: 'all', eventKind: 'all', eventReview: 'all', eventTier: 'signal',
    reviewState: { feedback: { 'len-buy': { reason: 'wrong_interpretation' } } } };
  assert.equal(ui.filterEvents([event], options).length, 0);
  assert.equal(ui.filterEvents([event], { ...options, eventTier: 'context' }).length, 1);
});
test('detail includes correction controls and the distinct dates', () => {
  const html = ui.renderEventDetailBody(event, escape, () => '', '', {});
  for (const text of ['Wrong company', 'Wrong interpretation', 'Already known', 'Export flags', 'Published 2026-09-21', 'Processed 2026-10-20']) assert.ok(html.includes(text));
});
