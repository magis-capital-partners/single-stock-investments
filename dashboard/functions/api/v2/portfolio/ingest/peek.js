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
// Skipping the nonce is only safe if a peek request can be replayed as a peek
// and as nothing else. An earlier version of this route got that wrong: it was
// signed exactly like a claim, with a byte-identical body, and never used up its
// nonce -- so a captured peek was a valid, unused claim signature for its whole
// 300s window, and replaying it to a claim route leased the desk's tickets away
// from the real bridge. Two independent locks now close that:
//
//   * Signing domain. The peek is verified over "peek\n<ts>\n<nonce>\n<body>";
//     every other route verifies "<ts>\n<nonce>\n<body>". The timestamp must be
//     ten digits and the domain starts with a letter, so the two messages can
//     never coincide: a peek signature fails every other route's check (401)
//     and a claim or ingest signature fails here, whatever body is attached.
//   * Purpose. The signed body says {"purpose":"peek"} and this route requires
//     it; both claim routes refuse any body whose purpose is not "claim" (a
//     missing purpose is still a claim, which is what the deployed bridge
//     sends), and do so before reserving a nonce.
//
// With those, replaying a captured peek can only repeat the peek: two COUNTs
// over open rows, no lease, no state change, no row written. What it discloses
// is two integers -- how many order tickets and contract lookups are claimable
// for the account in the signed body -- for up to 300s after capture.

import { failure, json, requestId, requireDatabase } from "../../../../_lib/http.js";
import { verifyPortfolioHmac } from "../../../../_lib/portfolio.js";
import {
  LOOKUP_CLAIMABLE_STATES, LOOKUP_LEASE_SECONDS, ORDER_LEASE_SECONDS, ORDER_OPEN_STATES,
  PEEK_PURPOSE, PEEK_SIGNATURE_DOMAIN, leaseFloor, placeholders,
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
    // Only a peek-domain signature is accepted here, and a peek-domain
    // signature is accepted nowhere else (see the header).
    const authorization = await verifyPortfolioHmac(context.request, context.env, bytes, { domain: PEEK_SIGNATURE_DOMAIN });
    if (!authorization) return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, noStore());
    // Deliberately no reserveNonce(): see the header. This route must stay
    // read-only for that to remain true -- anything that writes belongs in a
    // claim route, behind a nonce.

    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes) || "{}"); }
    catch (_) { return json({ error: "Invalid JSON.", request_id: id }, 400, noStore()); }
    if (payload?.purpose !== PEEK_PURPOSE) {
      return json({ error: "A peek body must say purpose: peek.", request_id: id }, 422, noStore());
    }

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
