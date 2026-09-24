// What "claimable" means on the command channel, in one place.
//
// Three routes have to agree on it: the two claim routes, which lease work to
// the bridge, and the peek, which only asks whether a claim would find
// anything. If the peek's idea of claimable drifted from the claim's, the bridge
// would either skip work it should have taken or go back to claiming (and so
// writing a nonce row) on every idle tick -- which is the cost the peek exists
// to remove.

// States where a human or the broker still owes the desk something. Mirrors
// OPEN_STATES in command_poller.py.
export const ORDER_OPEN_STATES = ["requested", "drafting", "previewed", "approved", "submitting"];

// Long enough that a slow preview (live NBBO + whatIf, inside the hub's own
// 10s quote freshness budget) never loses its lease mid-flight; short enough
// that a bridge killed between claim and preview frees the ticket well within
// the 120s approval TTL.
export const ORDER_LEASE_SECONDS = 90;

export const LOOKUP_CLAIMABLE_STATES = ["requested", "resolving"];
export const LOOKUP_LEASE_SECONDS = 60;
// reqContractDetails / reqSecDefOptParams are paced by IBKR; a handful per tick
// keeps the bridge inside its pacing budget.
export const LOOKUP_BATCH = 5;

// A `previewed` ticket nobody approved is dead once its approval window has
// closed: validateApproval() refuses it and the hub's own token has expired. It
// is kept visible for this long past the window so the person who walked away
// still sees "the approval window closed" on the ticket, then it is marked
// `expired` so it can no longer hold the browser's ticket poll or be re-leased
// to the bridge every 90 seconds forever. The approval TTL is 120s; this is
// deliberately many multiples of it.
export const PREVIEW_EXPIRY_GRACE_SECONDS = 15 * 60;

// The peek is signed under its own domain and names itself in the body.
// Mirrors PEEK_SIGNATURE_DOMAIN / PEEK_PURPOSE / CLAIM_PURPOSE in command_poller.py.
export const PEEK_SIGNATURE_DOMAIN = "peek";
export const PEEK_PURPOSE = "peek";
export const CLAIM_PURPOSE = "claim";

/**
 * Why this body may not be used as a claim, or null if it may.
 *
 * A body with no `purpose` is a claim: that is what every bridge sent before
 * purposes existed, and the one deployed on NY4 still does. A body that names
 * any other purpose -- above all "peek", which reserves no nonce -- is refused
 * before anything is written. The peek's signing domain already stops a peek
 * signature from verifying on a claim route; this is the second, independent
 * lock, and it holds even for a body signed the claim way.
 */
export function claimPurposeError(payload) {
  const purpose = payload?.purpose;
  if (purpose === undefined || purpose === null || purpose === CLAIM_PURPOSE) return null;
  return `A '${String(purpose).slice(0, 32)}' body is not a claim.`;
}

export function leaseFloor(now, seconds) {
  return new Date(now.getTime() - seconds * 1000).toISOString();
}

export const placeholders = (values) => values.map(() => "?").join(",");

/**
 * Mark long-dead previews `expired`.
 *
 * Only `previewed` moves, and only once its approval window (or, for a row
 * that never recorded one, its last update) is PREVIEW_EXPIRY_GRACE_SECONDS in
 * the past. By then nothing can approve it: the approve route requires an open
 * window and the hub re-checks its own HMAC token, which expired with the
 * window. So this closes no path that was still open -- it only stops a corpse
 * from looking like live work.
 *
 * `approved` and `submitting` are never touched: those belong to the hub, and a
 * submitting ticket may already be at the broker.
 *
 * Seeks on idx_order_requests_state (state, created_at) and writes nothing when
 * there is nothing to expire.
 */
export function expireStalePreviewsStatement(db, { accountAlias = null, owner = null, now = new Date() } = {}) {
  const cutoff = leaseFloor(now, PREVIEW_EXPIRY_GRACE_SECONDS);
  const stamp = now.toISOString();
  const scope = accountAlias != null ? "AND account_alias=?" : owner != null ? "AND owner=?" : "";
  const binds = [stamp, "approval_expired", "previewed", cutoff];
  if (accountAlias != null) binds.push(accountAlias);
  else if (owner != null) binds.push(owner);
  // datetime() on both sides: the hub writes approval_expires_at with Python's
  // isoformat() ("...+00:00") while the edge writes "...Z", and an unparseable
  // stamp becomes NULL, which never compares true -- so a malformed row stays
  // put rather than being expired early.
  return db.prepare(`UPDATE portfolio_order_requests
    SET state='expired', updated_at=?, reject_reason=COALESCE(reject_reason, ?),
        claimed_at=NULL, claimed_by=NULL
    WHERE state=? AND datetime(COALESCE(approval_expires_at, updated_at)) < datetime(?) ${scope}`).bind(...binds);
}
