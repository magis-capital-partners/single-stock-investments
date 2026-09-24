// Edge caching for the public, read-only GET routes.
//
// Pages Functions responses are never stored by Cloudflare's CDN on the
// strength of a Cache-Control header, so the `public, max-age=30` these routes
// have always sent only ever helped the one browser that asked. Every page load
// by every visitor ran the queries again: six public D1 routes on each SPA
// boot, several of them aggregates over whole tables. This stores each 200 in
// the colo's Workers cache (caches.default) for a short TTL, keyed by the full
// URL, so a burst of page loads costs one set of D1 reads per colo per TTL.
//
// Only routes that are public and identical for every caller may use this. A
// route behind Access, anything that reads the viewer, and anything that writes
// must never be wrapped -- portfolio, sleeves, orders and every ingest route are
// deliberately absent (test-edge-cache.mjs pins that).
//
// A cached body is byte-for-byte the response that was stored, including its
// request_id; `x-edge-cache: HIT` says so. The browser-facing Cache-Control is
// restored on a hit, so clients see the same caching directives as before.

// Market-risk data moves with the live monitor (60s publish cadence) and the
// 22:15 UTC components run; research data moves with a deploy seed, a few
// times a day.
export const MARKET_RISK_TTL_SECONDS = 60;
export const RESEARCH_TTL_SECONDS = 300;

const CLIENT_CACHE_HEADER = "x-client-cache-control";

function edgeCache() {
  try {
    return globalThis.caches?.default || null;
  } catch (_) {
    return null;
  }
}

function withHeaders(response, headers) {
  const copy = new Response(response.body, response);
  for (const [name, value] of Object.entries(headers)) {
    if (value == null) copy.headers.delete(name);
    else copy.headers.set(name, value);
  }
  return copy;
}

/**
 * Serve `produce()` through the edge cache for `ttlSeconds`.
 *
 * Fails open in every direction: no Cache API (tests, local dev), a cache that
 * throws, or a non-200 answer all fall through to the live handler, so caching
 * can make a route cheaper but never make it fail.
 */
export async function withEdgeCache(context, ttlSeconds, produce) {
  const request = context.request;
  const cache = edgeCache();
  if (!cache || request.method !== "GET") return produce();

  // Full URL, query string included; nothing from the request's headers.
  const key = new Request(new URL(request.url).toString(), { method: "GET" });
  let hit = null;
  try { hit = await cache.match(key); } catch (_) { hit = null; }
  if (hit) {
    return withHeaders(hit, {
      "cache-control": hit.headers.get(CLIENT_CACHE_HEADER) || hit.headers.get("cache-control"),
      [CLIENT_CACHE_HEADER]: null,
      "x-edge-cache": "HIT",
    });
  }

  const response = await produce();
  if (response.status !== 200) return withHeaders(response, { "x-edge-cache": "BYPASS" });

  const clientCacheControl = response.headers.get("cache-control");
  const stored = withHeaders(response.clone(), {
    // What the edge cache honours when storing: how long this copy may serve.
    "cache-control": `public, max-age=${ttlSeconds}`,
    [CLIENT_CACHE_HEADER]: clientCacheControl,
    "x-edge-cache": null,
  });
  const put = Promise.resolve().then(() => cache.put(key, stored)).catch(() => {});
  if (typeof context.waitUntil === "function") context.waitUntil(put);
  else await put;
  return withHeaders(response, { "x-edge-cache": "MISS" });
}
