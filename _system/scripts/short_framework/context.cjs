'use strict';
// Current execution context comes from local ledgers and an attributed Flex
// export. Reading it never opens a Gateway or market-data session.
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const E = require('../../../dashboard/short-framework-engine.js');
const O = require('./operations.cjs');

function hubReservations(filename, work, records, excludeIntent = null) {
  if (!filename || !fs.existsSync(filename)) throw new TypeError('Current private hub ledger required');
  const db = new DatabaseSync(filename, { readOnly: true });
  try {
    const orders = db.prepare("SELECT * FROM order_intents WHERE strategy='short_framework'").all();
    const result = [];
    for (const order of orders) {
      if (order.intent_uuid === excludeIntent || order.mode === 'dry_run') continue;
      const filled = db.prepare('SELECT quantity_decimal FROM executions WHERE intent_uuid=?').all(order.intent_uuid)
        .reduce((sum, row) => sum + Number(row.quantity_decimal), 0);
      const imported = records.filter(r => ['entry_fill', 'cover_fill'].includes(r.kind) && r.hub_intent_uuid === order.intent_uuid)
        .reduce((sum, row) => sum + row.shares, 0);
      const active = !['Filled', 'Cancelled', 'Rejected', 'Expired'].includes(order.state);
      const shares = Math.max(0, filled - imported) + (active ? Math.max(0, Number(order.quantity_decimal) - filled) : 0);
      if (!(shares > 1e-9)) continue;
      const created = db.prepare("SELECT payload_json FROM order_events WHERE intent_uuid=? AND event_type='intent_created' ORDER BY created_at LIMIT 1").get(order.intent_uuid);
      const match = /^SF1:[a-f0-9]{64}:([a-f0-9]{64})$/.exec(JSON.parse(created?.payload_json || '{}').framework_binding || '');
      if (!match) throw new TypeError('An outstanding framework order has no private binding');
      const saved = JSON.parse(fs.readFileSync(path.join(work, 'handoffs', match[1] + '.json'), 'utf8'));
      const e = saved.envelope.snapshot.event;
      if (saved.envelope.account.account_reference !== order.account_alias) throw new TypeError('Outstanding framework order account mismatch');
      result.push({ order_id: order.intent_uuid, instrument_id: e.instrument_id, issuer_id: e.issuer_id,
        action: order.action, shares, mark: Number(order.limit_price_decimal) });
    }
    return result.sort((a, b) => a.order_id.localeCompare(b.order_id));
  } finally { db.close(); }
}

function assertAccount(envelope, projection, broker, reservations, now) {
  const account = envelope.account, actual = projection.account, metrics = projection.metrics;
  const reconciliation = O.reconcile(actual, broker, now);
  if (!reconciliation.reconciled || !account.account_reference || broker.account_reference !== account.account_reference)
    throw new TypeError('Current attributed account and Flex reconciliation required');
  if (account.basis !== 'observed_account' || account.reconciled !== true
    || Math.abs(account.equity - metrics.equity) > .02
    || account.other_stress_loss !== broker.other_stress_loss || account.other_stressed_margin !== broker.other_stressed_margin)
    throw new TypeError('Reviewed account differs from the private journal or account-wide risk');
  const normalize = rows => rows.filter(r => r.shares > 1e-9 || r.loan_shares > 1e-9).map(r => ({
    instrument_id: r.instrument_id, issuer_id: r.issuer_id, shares: r.shares, loan_shares: r.loan_shares,
    mark: r.mark,
  })).sort((a, b) => a.instrument_id.localeCompare(b.instrument_id));
  if (E.canonical(normalize(account.positions || [])) !== E.canonical(normalize(Object.values(actual.positions))))
    throw new TypeError('Reviewed positions differ from the current private journal');
  const reserve = rows => rows.map(r => ({ order_id: r.order_id, instrument_id: r.instrument_id,
    issuer_id: r.issuer_id, action: r.action, shares: r.shares, mark: r.mark })).sort((a, b) => a.order_id.localeCompare(b.order_id));
  if (E.canonical(reserve(account.reservations || [])) !== E.canonical(reserve(reservations)))
    throw new TypeError('Pending orders changed; refresh the reviewed account reservations');
  return reconciliation;
}
module.exports = { hubReservations, assertAccount };
