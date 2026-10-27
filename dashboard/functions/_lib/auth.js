const ACCESS_ASSERTION_HEADER = "cf-access-jwt-assertion";
const CLOCK_SKEW_SECONDS = 60;
// Verified by the owner, 2026-10-23. Names and client supplied headers never grant a role.
export const DASHBOARD_OWNERS = Object.freeze({
  "drew@magiscapitalpartners.com": "drew",
  "mike@magiscapitalpartners.com": "michael",
});

function decodeBase64Url(value) {
  const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function decodeJsonPart(value) {
  return JSON.parse(new TextDecoder().decode(decodeBase64Url(value)));
}

function normalizedTeamDomain(raw) {
  const value = String(raw || "").trim().replace(/\/$/, "");
  if (!value) throw new Error("Missing CF_ACCESS_TEAM_DOMAIN");
  const url = new URL(value.includes("://") ? value : `https://${value}`);
  if (url.protocol !== "https:" || !url.hostname.endsWith(".cloudflareaccess.com")) {
    throw new Error("CF_ACCESS_TEAM_DOMAIN must be an https cloudflareaccess.com domain");
  }
  return url.origin;
}

function audienceIncludes(claim, expected) {
  if (Array.isArray(claim)) return claim.map(String).includes(expected);
  return String(claim || "") === expected;
}

export function validateAccessClaims(payload, env, nowSeconds = Date.now() / 1000) {
  const issuer = normalizedTeamDomain(env?.CF_ACCESS_TEAM_DOMAIN);
  const audience = String(env?.CF_ACCESS_AUD || "").trim();
  if (!audience) throw new Error("Missing CF_ACCESS_AUD");
  if (String(payload?.iss || "").replace(/\/$/, "") !== issuer) {
    throw new Error("Access token issuer mismatch");
  }
  if (!audienceIncludes(payload?.aud, audience)) {
    throw new Error("Access token audience mismatch");
  }
  if (!Number.isFinite(Number(payload?.exp)) || Number(payload.exp) < nowSeconds - CLOCK_SKEW_SECONDS) {
    throw new Error("Access token expired");
  }
  if (payload?.nbf != null && (!Number.isFinite(Number(payload.nbf)) || Number(payload.nbf) > nowSeconds + CLOCK_SKEW_SECONDS)) {
    throw new Error("Access token is not active");
  }
  if (String(payload?.type || "") !== "app") {
    throw new Error("Access token type mismatch");
  }
  return payload;
}

export async function verifyAccessJwt(token, env, fetchImpl = fetch) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) throw new Error("Malformed Access token");
  const header = decodeJsonPart(parts[0]);
  const payload = validateAccessClaims(decodeJsonPart(parts[1]), env);
  if (header?.alg !== "RS256" || !header?.kid) throw new Error("Unsupported Access token algorithm");

  const teamDomain = normalizedTeamDomain(env?.CF_ACCESS_TEAM_DOMAIN);
  const response = await fetchImpl(`${teamDomain}/cdn-cgi/access/certs`, {
    headers: { accept: "application/json" },
  });
  if (!response.ok) throw new Error("Could not load Access signing keys");
  const jwks = await response.json();
  const jwk = (jwks?.keys || []).find((candidate) => candidate?.kid === header.kid);
  if (!jwk) throw new Error("Access signing key not found");
  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    decodeBase64Url(parts[2]),
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!valid) throw new Error("Invalid Access token signature");
  return {
    email: String(payload.email || "").toLowerCase() || null,
    subject: String(payload.sub || "") || null,
    service_token: String(payload.common_name || "") || null,
    claims: payload,
  };
}

function localDevelopmentBypass(request, env) {
  if (String(env?.PORTFOLIO_AUTH_MODE || "") !== "development") return false;
  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1";
}

export function humanRole(viewer, env = {}) {
  if (!viewer?.email || viewer.service_token) return null;
  const email = viewer.email.trim().toLowerCase();
  const revoked = String(env.CF_ACCESS_REVOKED_EMAILS || "").toLowerCase().split(/[\s,;]+/);
  if (revoked.includes(email)) return null;
  return DASHBOARD_OWNERS[email] ? "owner" : "reader";
}

export async function requireHumanViewer(context) {
  if (context.data?.humanViewer) return context.data.humanViewer;
  if (localDevelopmentBypass(context.request, context.env)) {
    // Local access is explicit and cannot be enabled on a deployed hostname.
    return { email: "local-development", subject: "local-development", role: "owner", claims: {} };
  }
  const cookie = context.request.headers.get("cookie") || "";
  const token = context.request.headers.get(ACCESS_ASSERTION_HEADER)
    || cookie.match(/(?:^|;\s*)CF_Authorization=([^;]+)/)?.[1] || "";
  if (!token) return null;
  try {
    const viewer = await verifyAccessJwt(token, context.env);
    const role = humanRole(viewer, context.env);
    return role ? { ...viewer, role } : null;
  } catch (error) {
    console.error(JSON.stringify({
      message: "portfolio Access validation failed",
      error: error instanceof Error ? error.message : String(error),
      path: new URL(context.request.url).pathname,
    }));
    return null;
  }
}

export async function requirePortfolioViewer(context) {
  const viewer = await requireHumanViewer(context);
  return viewer?.role === "owner" ? viewer : null;
}

export function privateJson(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, private",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}
