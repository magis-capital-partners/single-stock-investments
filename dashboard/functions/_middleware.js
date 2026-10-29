import { privateJson, requireHumanViewer } from "./_lib/auth.js";

// These routes perform their own cryptographic machine authentication before storage access.
// No wildcard exemption: adding an ingestion route requires an explicit security review.
export const MACHINE_ROUTES = new Set([
  "/api/v1/market-risk/ingest", "/api/v1/quotes/ingest", "/api/v1/sleeves/ingest",
  "/api/v1/sleeves/realized-ingest",
  "/api/v2/portfolio/ingest", "/api/v2/portfolio/ingest/peek",
  "/api/v2/portfolio/ingest/contract-lookups/claim", "/api/v2/portfolio/ingest/contract-lookups/publish",
  "/api/v2/portfolio/ingest/order-requests/claim", "/api/v2/portfolio/ingest/order-requests/publish",
]);
export const READER_PATHS = new Set([
  "/fund-letters", "/fund-letters/", "/fund-letters/index.html",
  "/fund-letters/reader.js", "/fund-letters/reader.css", "/api/fund-letters",
]);
const OWNER_READER_ENTRY = new Set(["/fund-letters", "/fund-letters/", "/fund-letters/index.html"]);

export function accessDecision(path, method, viewer) {
  if (method === "POST" && MACHINE_ROUTES.has(path)) return "machine";
  if (!viewer) return "unauthenticated";
  if (viewer.role === "owner" && OWNER_READER_ENTRY.has(path)) return "owner-home";
  if (viewer.role === "owner" || READER_PATHS.has(path)) return "allow";
  return path === "/" || path === "/index.html" ? "reader-home" : "forbidden";
}

export async function onRequest(context) {
  let path;
  try { path = decodeURIComponent(new URL(context.request.url).pathname); }
  catch { return privateJson({ error: "Invalid path." }, 400); }
  const machine = context.request.method === "POST" && MACHINE_ROUTES.has(path);
  const viewer = machine ? null : await requireHumanViewer(context);
  const decision = accessDecision(path, context.request.method, viewer);
  if (decision === "unauthenticated") return privateJson({ error: "Sign in through Cloudflare Access." }, 401);
  if (decision === "forbidden") return privateJson({ error: "Owner access required." }, 403);
  if (decision === "reader-home") return new Response(null, { status: 302, headers: { location: "/fund-letters/", "cache-control": "no-store, private" } });
  if (decision === "owner-home") return new Response(null, { status: 302, headers: { location: "/", "cache-control": "no-store, private" } });
  if (viewer) context.data.humanViewer = viewer;
  const upstream = await context.next();
  const response = new Response(upstream.body, upstream);
  response.headers.set("cache-control", "no-store, private");
  response.headers.set("cdn-cache-control", "no-store");
  response.headers.set("vary", "Cookie, cf-access-jwt-assertion");
  response.headers.set("referrer-policy", "no-referrer");
  response.headers.set("x-content-type-options", "nosniff");
  return response;
}
