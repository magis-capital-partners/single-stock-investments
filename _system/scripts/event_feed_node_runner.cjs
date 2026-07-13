global.window = global;
require('../../dashboard/search-match.js');
require('../../dashboard/insights-viz.js');

const common = {
  eventRange: 'all', eventScope: 'all', eventKind: 'all', eventSource: 'all',
  eventAxis: 'all', eventDirection: 'all', eventConfidence: 'all', eventReview: 'all',
  reviewState: {}, knownTickers: ['ICE', 'GOOGL'], eventTier: 'all',
};

const events = [];
for (let i = 0; i < 30; i += 1) {
  events.push({
    id: `repeat-${i}`, ticker: `T${i}`, title: 'Leadership / governance on watch',
    template_id: 'governance-watch', tier: 'signal', feed_eligible: true,
    decision_priority: 90 - i, observed_at: '2026-07-12', event_kind: 'observed',
    in_holdings: i % 2 === 0, in_watchlist: i % 2 === 1,
  });
}
for (let i = 0; i < 20; i += 1) {
  events.push({
    id: `distinct-${i}`, ticker: `D${i}`, title: `Distinct event ${i}`,
    template_id: `distinct-${i}`, tier: i < 5 ? 'signal' : 'context', feed_eligible: true,
    decision_priority: 80 - i, observed_at: '2026-07-11', event_kind: 'observed',
    in_holdings: true, in_watchlist: false,
  });
}

const action = process.argv[2] || 'diversify';
if (action === 'diversify') {
  const ranked = window.InsightsViz.diversifyEvents(events);
  const head = ranked.slice(0, 20);
  const counts = {};
  for (const event of head) counts[event.template_id] = (counts[event.template_id] || 0) + 1;
  process.stdout.write(JSON.stringify({ max_template: Math.max(...Object.values(counts)), head_count: head.length }));
} else if (action === 'scope') {
  const holdings = window.InsightsViz.baseFilterEvents(events, { ...common, eventScope: 'holdings' });
  const watchlist = window.InsightsViz.baseFilterEvents(events, { ...common, eventScope: 'watchlist' });
  process.stdout.write(JSON.stringify({ holdings: holdings.length, watchlist: watchlist.length }));
} else if (action === 'tier') {
  const signals = window.InsightsViz.filterEvents(events, { ...common, eventTier: 'signal' });
  const context = window.InsightsViz.filterEvents(events, { ...common, eventTier: 'context' });
  process.stdout.write(JSON.stringify({ signals: signals.length, context: context.length }));
} else {
  process.stderr.write(`unknown action: ${action}`);
  process.exit(2);
}
