// Hub-facing: "would a claim find anything?" -- asked without writing a row.
//
// Why this exists. The bridge polls every 15s. Each claim route is a signed
// POST that reserves a nonce before doing anything else, and the bridge called
// both on every tick, so an idle desk wrote two portfolio_ingest_nonces rows
// every 15 seconds: 11,323 inserts a day at ~3 billed row writes each (table +
// primary-key index + received_at index), plus ~10k more when retention deleted
// them. That was ~44k of the 100k free-tier daily write allowance spent saying
// "nothing to do". The bridge now peeks first and claims only the queue that has
// work, so an idle tick writes nothing at all.
//
// Why a replayed peek is harmless, which is what lets it skip the nonce:
//
//   * It is read-only. Two COUNTs; no lease, no state change, no nonce row. A
//     replay cannot claim a ticket, move one, or deny one to the real bridge --
//     the thing the claim routes' nonce actually protects against.
//   * It is still signed. The HMAC covers the timestamp and the body, and the
//     timestamp must be within 300s (verifyPortfolioHmac), so only a request the
//     hub itself signed recently is answered at all.
//   * It discloses two integers: how many order tickets and contract lookups are
//     claimable for the account named in the signed body. Replaying a captured
//     peek inside its 300s window tells the replayer whether the desk has work,
//     nothing about what the work is.
//   * Its cost is bounded by index seeks over open rows, so replaying it is no
//     more useful for burning quota than any public read route.

import { failure, json, requestId, requireDatabase } from "../../../../_lib/http.js";
import { verifyPortfolioHmac } from "../../../../_lib/portfolio.js";
import {
  LOOKUP_CLAIMABLE_STATES, LOOKUP_LEASE_SECONDS, ORDER_LEASE_SECONDS, ORDER_OPEN_STATES,
  leaseFloor, placeholders,
} from "../../../../_lib/command-channel.js";

const MAX_BODY_BYTES = 16_384;
const noStore = () => ({ "cache-control": "no-store" });

// Both statements lead with `state IN (...)`, so they seek idx_order_requests_state
// and idx_contract_lookups_state (state, created_at) and read only open rows.
export const PEEK_ORDER_REQUESTS_SQL = `SELECT COUNT(*) AS claimable FROM portfolio_order_requests
  WHERE state IN (${placeholders(ORDER_OPEN_STATES)}) AND account_alias=?
    AND (claimed_at IS NULL OR claimed_at < ?)`;
export const PEEK_CONTRACT_LOOKUPS_SQL = `SELECT COUNT(*) AS claimable FROM portfolio_contract_lookups
  WHERE state IN (${placeholders(LOOKUP_CLAIMABLE_STATES)}) AND account_alias=?
    AND (claimed_at IS NULL OR claimed_at < ?)`;

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const bytes = await context.request.arrayBuffer();
    if (bytes.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413, noStore());
    }
    const authorization = await verifyPortfolioHmac(context.request, context.env, bytes);
    if (!authorization) return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, noStore());
    // Deliberately no reserveNonce(): see the header. This route must stay
    // read-only for that to remain true -- anything that writes belongs in a
    // claim route, behind a nonce.

    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes) || "{}"); }
    catch (_) { return json({ error: "Invalid JSON.", request_id: id }, 400, noStore()); }

    const accountAlias = String(payload?.account_alias || "").trim();
    if (!accountAlias) return json({ error: "account_alias is required.", request_id: id }, 422, noStore());

    const now = new Date();
    const db = requireDatabase(context.env);
    const [orders, lookups] = await db.batch([
      db.prepare(PEEK_ORDER_REQUESTS_SQL)
        .bind(...ORDER_OPEN_STATES, accountAlias, leaseFloor(now, ORDER_LEASE_SECONDS)),
      db.prepare(PEEK_CONTRACT_LOOKUPS_SQL)
        .bind(...LOOKUP_CLAIMABLE_STATES, accountAlias, leaseFloor(now, LOOKUP_LEASE_SECONDS)),
    ]);
    const count = (result) => Number(result?.results?.[0]?.claimable || 0);

    return json({
      schema_version: "portfolio_command_peek.v1",
      account_alias: accountAlias,
      claimable: { order_requests: count(orders), contract_lookups: count(lookups) },
      request_id: id,
    }, 200, noStore());
  } catch (error) {
    return failure(error, id);
  }
}
