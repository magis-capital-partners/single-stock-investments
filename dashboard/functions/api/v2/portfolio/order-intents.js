// Order command channel, edge half.
//
// GET  - the owner's recent tickets, for rendering the order desk.
// POST - record a *request* for an order. This never reaches IBKR. The hub on
//        the Ubuntu box polls, previews against the live book, and is the only
//        process that can transmit.
//
// The signed hub-facing routes (claim / publish preview / report status) live in
// ingest.js alongside the other HMAC endpoints, so this file has no path that a
// browser session could use to move a ticket toward the broker.

import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { portfolioOrderOwner } from "../../../_lib/paper-orders.js";
import { validateOrderRequest, frameworkRequestCore } from "../../../_lib/order-requests.js";
import { expireStalePreviewsStatement, isStalePreview } from "../../../_lib/command-channel.js";

const PUBLIC_COLUMNS = `request_id,owner,strategy,conid,symbol,sec_type,action,quantity_decimal,
  limit_price_decimal,currency,tif,outside_rth,mode,rationale,state,intent_uuid,contract_fingerprint,
  preview_json,preview_as_of,approval_expires_at,reject_reason,approved_at,approved_by,
  broker_status,order_ref,client_id,order_id,perm_id,created_at,updated_at,
  expiry,strike_decimal,right_code,multiplier_decimal,trading_class,exchange,local_symbol`;

const privateHeaders = () => ({ "cache-control": "private, no-store" });

function uuid() {
  return crypto.randomUUID();
}

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    const db = requireDatabase(context.env);
    const list = () => db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_order_requests
          WHERE owner=? ORDER BY created_at DESC LIMIT 100`).bind(owner).all();
    let rows = owner ? await list() : { results: [] };
    // Expire this owner's long-dead previews, so a ticket the bridge will never
    // advance (bridge down, or a human walked away) cannot keep the desk's
    // ticket poll running -- but only when a listed row actually is one. This
    // route is polled (1s, then 5s) while a ticket is open; an UPDATE on every
    // poll would be a read of the owner's previews each time for nothing. And a
    // refused write (the daily D1 quota) must never fail the read or stop the
    // poll: the list is served as it stands. See expireStalePreviewsStatement
    // for why no approval or transmit guard is weakened.
    const now = new Date();
    if (owner && (rows.results || []).some((row) => isStalePreview(row, now))) {
      try {
        const expired = await expireStalePreviewsStatement(db, { owner, now }).run();
        if (Number(expired?.meta?.changes || 0) > 0) rows = await list();
      } catch (error) {
        console.error(JSON.stringify({
          message: "stale preview expiry failed; serving the ticket list unchanged",
          request_id: id, error: error instanceof Error ? error.message : String(error),
        }));
      }
    }
    return json({
      schema_version: "portfolio_order_requests.v1",
      command_plane: "python_private_only",
      viewer: { email: viewer?.email || null, order_owner: owner, can_request_orders: Boolean(owner) },
      // Live transmission also requires the hub's own interlock; the edge never
      // knows or controls that, and must not imply otherwise in the UI.
      requests: rows.results || [],
      request_id: id,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    const body = await context.request.json().catch(() => null);
    if (!body) return json({ error: "A JSON body is required.", request_id: id }, 400, privateHeaders());

    let ticket;
    try {
      ticket = validateOrderRequest(body, owner);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 400, privateHeaders());
    }
    if (ticket.strategy === "short_framework") {
      const core = JSON.stringify(frameworkRequestCore(ticket));
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(core))))
        .map(value => value.toString(16).padStart(2, "0")).join("");
      if (digest !== ticket.framework_request_sha256) return json({ error: "Reviewed framework request contents changed.", request_id: id }, 400, privateHeaders());
    }

    const db = requireDatabase(context.env);
    const run = await db.prepare(`SELECT account_alias FROM portfolio_source_runs
      WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1`).first();
    if (!run) {
      // Without a complete snapshot there is no book to price or size against.
      return json({ error: "No complete broker snapshot; order entry is closed.", request_id: id }, 409, privateHeaders());
    }

    const now = new Date().toISOString();
    const requestKey = ticket.strategy === "short_framework" ? `sf-${ticket.framework_request_sha256}` : uuid();
    if (ticket.strategy === "short_framework") {
      const prior = await db.prepare("SELECT request_id,owner,state FROM portfolio_order_requests WHERE request_id=?").bind(requestKey).first();
      if (prior) {
        if (prior.owner !== owner) return json({ error: "Request binding is already in use.", request_id: id }, 409, privateHeaders());
        return json({ schema_version: "portfolio_order_requests.v1", request_id_created: prior.request_id,
          state: prior.state, idempotent: true, request_id: id }, 200, privateHeaders());
      }
    }
    // The option identity rides with the request so the ticket can be *read*.
    // It is not the source of truth for what gets sent: the hub re-qualifies the
    // conId at preview and builds the fingerprint from what IBKR returns, so a
    // browser that lied about the strike would produce a fingerprint that does
    // not match what it displayed, and the approval would not bind.
    const insertion = ticket.strategy === "short_framework" ? "INSERT OR IGNORE" : "INSERT";
    const inserted = await db.prepare(`${insertion} INTO portfolio_order_requests
      (request_id,account_alias,owner,strategy,conid,symbol,sec_type,action,quantity_decimal,
       limit_price_decimal,currency,tif,outside_rth,mode,rationale,expiry,strike_decimal,right_code,
       multiplier_decimal,trading_class,exchange,local_symbol,state,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'requested',?,?)`).bind(
      requestKey, run.account_alias, ticket.owner, ticket.strategy, ticket.conid, ticket.symbol,
      ticket.sec_type, ticket.action, ticket.quantity, ticket.limit_price, ticket.currency,
      ticket.tif, ticket.outside_rth ? 1 : 0, ticket.mode, ticket.rationale,
      ticket.expiry, ticket.strike, ticket.right, ticket.multiplier,
      ticket.trading_class, ticket.exchange, ticket.local_symbol, now, now,
    ).run();
    if (ticket.strategy === "short_framework" && Number(inserted?.meta?.changes) === 0) {
      const prior = await db.prepare("SELECT request_id,owner,state FROM portfolio_order_requests WHERE request_id=?").bind(requestKey).first();
      if (!prior || prior.owner !== owner) return json({ error: "Request binding conflict.", request_id: id }, 409, privateHeaders());
      return json({ schema_version: "portfolio_order_requests.v1", request_id_created: prior.request_id,
        state: prior.state, idempotent: true, request_id: id }, 200, privateHeaders());
    }

    return json({
      schema_version: "portfolio_order_requests.v1",
      request_id_created: requestKey,
      state: "requested",
      transmitted: false,
      note: "Recorded for the private hub. Nothing has been sent to the broker.",
      request_id: id,
    }, 201, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}
