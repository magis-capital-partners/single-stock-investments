// Hub-facing: hand the bridge the tickets it still owes an answer on.
//
// command_poller.py has called this path since the command channel was written
// and it did not exist -- ingest.js answers four schema_versions and 422s
// everything else -- so every ticket a browser submitted sat in `requested`
// forever while the UI polled a row that could never move. This is that half.
//
// The direction of trust is the whole point: the edge never calls the hub. The
// hub calls in, signed with a token that lives only on the trusted machine, and
// takes work. A stolen session cookie or a compromised Worker can create a
// request row; it cannot reach this route, and could not transmit if it did.

import { failure, json, requestId, requireDatabase } from "../../../../../_lib/http.js";
import { reserveNonce, verifyPortfolioHmac } from "../../../../../_lib/portfolio.js";
import { ORDER_LEASE_SECONDS, ORDER_OPEN_STATES, claimPurposeError, expireStalePreviewsStatement, leaseFloor } from "../../../../../_lib/command-channel.js";

// States where a human or the broker still owes us something, and the lease.
// Shared with the peek route (_lib/command-channel.js) so "claimable" cannot
// mean one thing to the peek and another here. The hub acts on `requested` and
// `approved` and uses the rest to decide whether the desk is busy enough to
// poll fast.
const OPEN_STATES = ORDER_OPEN_STATES;
const LEASE_SECONDS = ORDER_LEASE_SECONDS;

const MAX_BODY_BYTES = 16_384;
const noStore = () => ({ "cache-control": "no-store" });

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const bytes = await context.request.arrayBuffer();
    if (bytes.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413, noStore());
    }
    const authorization = await verifyPortfolioHmac(context.request, context.env, bytes);
    if (!authorization) return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, noStore());

    // Read the body before reserving the nonce, so a body that is not a claim is
    // refused without writing anything (see claimPurposeError).
    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes) || "{}"); }
    catch (_) { return json({ error: "Invalid JSON.", request_id: id }, 400, noStore()); }
    const notClaim = claimPurposeError(payload);
    if (notClaim) return json({ error: notClaim, request_id: id }, 422, noStore());

    const db = requireDatabase(context.env);
    if (!await reserveNonce(db, authorization.nonce)) {
      return json({ error: "Replay rejected.", request_id: id }, 409, noStore());
    }

    const accountAlias = String(payload?.account_alias || "").trim();
    if (!accountAlias) return json({ error: "account_alias is required.", request_id: id }, 422, noStore());
    const claimant = String(payload?.claimed_by || "portfolio-hub-bridge").trim().slice(0, 64);

    const now = new Date();
    const stamp = now.toISOString();
    const floor = leaseFloor(now, LEASE_SECONDS);
    const placeholders = OPEN_STATES.map(() => "?").join(",");

    // Take the lease in SQL, not in JS. Reading then writing would let two
    // bridges each believe they own the same ticket; this way the second one
    // updates zero rows and simply sees less work.
    //
    // Re-claiming an expired lease is safe on purpose. `drafting` is before any
    // transmission, and for `approved` the hub ledger is the real serialisation
    // point -- GuardedOrderService.submit() refuses an intent that is no longer
    // Approved, so a duplicated claim produces a refusal, never a second order.
    //
    // Long-dead previews are expired first. Nothing advances a `previewed`
    // ticket except a human approval inside its window, so one that was never
    // approved used to stay open forever: re-leased here every 90s (a nonce and
    // a lease write each time) and holding the browser's ticket poll. It can no
    // longer be approved by then -- the window and the hub's token are both
    // long gone -- so marking it `expired` closes nothing that was open.
    //
    // Housekeeping, so it runs on its own and may fail on its own: a refused
    // expiry must never cost the bridge its claim.
    try {
      await expireStalePreviewsStatement(db, { accountAlias, now }).run();
    } catch (error) {
      console.error(JSON.stringify({
        message: "stale preview expiry failed; claiming anyway",
        request_id: id, error: error instanceof Error ? error.message : String(error),
      }));
    }
    await db.prepare(`UPDATE portfolio_order_requests
      SET claimed_at=?, claimed_by=?, updated_at=?
      WHERE account_alias=? AND state IN (${placeholders})
        AND (claimed_at IS NULL OR claimed_at < ?)`).bind(
      stamp, claimant, stamp, accountAlias, ...OPEN_STATES, floor,
    ).run();

    const rows = await db.prepare(`SELECT * FROM portfolio_order_requests
      WHERE account_alias=? AND state IN (${placeholders}) AND claimed_by=? AND claimed_at=?
      ORDER BY created_at LIMIT 50`).bind(accountAlias, ...OPEN_STATES, claimant, stamp).all();

    return json({
      schema_version: "portfolio_order_requests.v1",
      account_alias: accountAlias,
      lease_seconds: LEASE_SECONDS,
      requests: rows.results || [],
      request_id: id,
    }, 200, noStore());
  } catch (error) {
    return failure(error, id);
  }
}
