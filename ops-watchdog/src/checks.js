// ops-watchdog checks: pure logic plus injected I/O, so node:test can drive it.
//
// Why this exists: the repository-health supervisor runs on GitHub Actions, so
// nothing inside GitHub notices when GitHub stops running it (scheduled slots
// here are dropped and delayed by hours). This Worker runs on Cloudflare's
// cron instead and checks three things every 30 minutes:
//   (a) the supervisor's committed state is younger than 8h;
//   (b) today's D1 row usage is under 60% / 80% of the free daily limits;
//   (c) the committed dashboard core.json is younger than 36h.
// It binds no D1 database and never writes to D1.

export const DEFAULTS = {
  REPO: "magis-capital-partners/single-stock-investments",
  BRANCH: "main",
  SUPERVISOR_STATE_PATH: "_system/data/repository_health_supervisor.json",
  CORE_PATH: "dashboard/data/core.json",
  SUPERVISOR_MAX_AGE_HOURS: 8,
  CORE_MAX_AGE_HOURS: 36,
};

// Cloudflare Workers Free plan, per account per UTC day.
export const D1_LIMITS = { rows_read: 5_000_000, rows_written: 100_000 };
export const D1_THRESHOLDS = [60, 80];
// Reminder tiers for a condition that persists: the first alert fires at the
// base threshold, then again once the age crosses each multiple.
const GAP_TIERS = [1, 3, 9];
const KEY_TTL_SECONDS = 8 * 24 * 3600;

const HOUR = 3600 * 1000;

function setting(env, name) {
  const raw = env && env[name] !== undefined && env[name] !== "" ? env[name] : DEFAULTS[name];
  return typeof DEFAULTS[name] === "number" ? Number(raw) : String(raw);
}

export function rawUrl(env, path) {
  return `https://raw.githubusercontent.com/${setting(env, "REPO")}/${setting(env, "BRANCH")}/${path}`;
}

// Read one top-level string field from the first bytes of a large JSON file.
// core.json is ~6 MB and its generated_at is the first key; a Range read keeps
// the Worker inside the free plan's CPU budget.
export async function readHeadField(fetchImpl, url, field, bytes = 2047) {
  let response;
  try {
    response = await fetchImpl(url, {
      headers: { Range: `bytes=0-${bytes}`, "User-Agent": "ops-watchdog" },
    });
  } catch (err) {
    return { ok: false, error: `fetch failed: ${err && err.message ? err.message : err}` };
  }
  if (!response || (response.status !== 200 && response.status !== 206)) {
    return { ok: false, error: `HTTP ${response ? response.status : "no response"}` };
  }
  const text = await response.text();
  const match = new RegExp(`"${field}"\\s*:\\s*"([^"]+)"`).exec(text);
  if (!match) return { ok: false, error: `no ${field} in the first ${bytes + 1} bytes` };
  const stamp = Date.parse(match[1]);
  if (Number.isNaN(stamp)) return { ok: false, error: `unparseable ${field} '${match[1]}'` };
  return { ok: true, value: match[1], at: stamp };
}

export const D1_QUERY = `query D1Usage($accountTag: string!, $start: Date!, $end: Date!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      d1AnalyticsAdaptiveGroups(limit: 10000, filter: {date_geq: $start, date_leq: $end}) {
        sum { rowsRead rowsWritten }
      }
    }
  }
}`;

export function parseD1Usage(payload) {
  if (!payload || typeof payload !== "object") return { ok: false, error: "unparseable response" };
  if (Array.isArray(payload.errors) && payload.errors.length) {
    return { ok: false, error: payload.errors.map((e) => e.message || String(e)).join("; ").slice(0, 200) };
  }
  const accounts = payload.data && payload.data.viewer && payload.data.viewer.accounts;
  if (!Array.isArray(accounts) || !accounts.length) {
    return { ok: false, error: "account not visible to this token" };
  }
  let read = 0;
  let written = 0;
  for (const row of accounts[0].d1AnalyticsAdaptiveGroups || []) {
    read += Number((row.sum || {}).rowsRead || 0);
    written += Number((row.sum || {}).rowsWritten || 0);
  }
  return { ok: true, rows_read: read, rows_written: written };
}

export async function fetchD1Usage(fetchImpl, env, day) {
  if (!env.CF_API_TOKEN || !env.CF_ACCOUNT_ID) return { ok: false, error: "not configured" };
  let response;
  try {
    response = await fetchImpl("https://api.cloudflare.com/client/v4/graphql", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        query: D1_QUERY,
        variables: { accountTag: env.CF_ACCOUNT_ID, start: day, end: day },
      }),
    });
  } catch (err) {
    return { ok: false, error: `fetch failed: ${err && err.message ? err.message : err}` };
  }
  if (!response.ok) {
    return { ok: false, error: `HTTP ${response.status} (the token may lack Account Analytics read)` };
  }
  try {
    return parseD1Usage(await response.json());
  } catch (_err) {
    return { ok: false, error: "unparseable response" };
  }
}

// ---------------------------------------------------------------------------
// dedupe stores: KV (exact) -> Cache API (exact where it works; it is a no-op
// on *.workers.dev) -> fixed slots (stateless; at most four alerts a day for a
// condition that persists, never a message every 30 minutes).
// ---------------------------------------------------------------------------

export function kvStore(kv) {
  return {
    kind: "kv",
    async has(key) { return (await kv.get(key)) !== null; },
    async get(key) { return kv.get(key); },
    async put(key, value) { await kv.put(key, String(value), { expirationTtl: KEY_TTL_SECONDS }); },
    async delete(key) { await kv.delete(key); },
  };
}

export function cacheStore(cache) {
  const req = (key) => new Request(`https://ops-watchdog.dedupe/${encodeURIComponent(key)}`);
  return {
    kind: "cache",
    async has(key) { return (await cache.match(req(key))) !== undefined; },
    async get(key) {
      const hit = await cache.match(req(key));
      return hit ? hit.text() : null;
    },
    async put(key, value) {
      await cache.put(req(key), new Response(String(value), {
        headers: { "Cache-Control": `max-age=${KEY_TTL_SECONDS}` },
      }));
    },
    async delete(key) { await cache.delete(req(key)); },
  };
}

export function slotStore(now) {
  const inSlot = now.getUTCHours() % 6 === 0 && now.getUTCMinutes() < 30;
  return {
    kind: "slots",
    async has(_key) { return !inSlot; },
    async get(_key) { return null; },
    async put(_key, _value) {},
    async delete(_key) {},
  };
}

export async function chooseStore(env, now, cache) {
  if (env && env.DEDUPE && typeof env.DEDUPE.get === "function") return kvStore(env.DEDUPE);
  if (cache) {
    const store = cacheStore(cache);
    try {
      const probe = `probe:${now.getTime()}`;
      await store.put(probe, "1");
      if (await store.has(probe)) {
        await store.delete(probe);
        return store;
      }
    } catch (_err) {
      // fall through to the stateless store
    }
  }
  return slotStore(now);
}

// ---------------------------------------------------------------------------
// the run
// ---------------------------------------------------------------------------

function hoursSince(now, at) {
  return (now.getTime() - at) / HOUR;
}

function tierFor(ageHours, base) {
  let tier = 0;
  for (const multiple of GAP_TIERS) if (ageHours > base * multiple) tier = multiple;
  return tier;
}

export async function runChecks(env, now, deps) {
  const fetchImpl = deps.fetch;
  const store = deps.store || (await chooseStore(env, now, deps.cache));
  const lines = [];
  const marks = [];
  const report = { store: store.kind };
  const day = now.toISOString().slice(0, 10);

  async function once(key, text, value = "1") {
    if (await store.has(key)) return;
    lines.push(text);
    marks.push([key, value]);
  }

  // (a) supervisor heartbeat
  const maxGap = setting(env, "SUPERVISOR_MAX_AGE_HOURS");
  const state = await readHeadField(fetchImpl, rawUrl(env, setting(env, "SUPERVISOR_STATE_PATH")),
    "checked_at");
  report.supervisor = state;
  if (!state.ok) {
    await once(`supervisor-unreadable:${day}`,
      `[ops-watchdog] Cannot read the supervisor state from GitHub (${state.error}).`);
  } else {
    const age = hoursSince(now, state.at);
    report.supervisor.age_hours = Math.round(age * 10) / 10;
    const tier = tierFor(age, maxGap);
    if (tier) {
      await once(`supervisor-gap:${state.value}:${tier}`,
        `[ops-watchdog] [GAP] The repository-health supervisor has not run for ${age.toFixed(1)}h`
        + ` (last run ${state.value}). Lane, feed and D1 checks inside GitHub are blind;`
        + " scheduled workflows may not be starting.");
      marks.push(["supervisor-gap-open", state.value]);
    } else if (await store.get("supervisor-gap-open")) {
      lines.push(`[ops-watchdog] [RECOVERED] The supervisor ran again at ${state.value}.`);
      marks.push(["supervisor-gap-open", null]);
    }
  }

  // (b) D1 free-plan usage today
  const usage = await fetchD1Usage(fetchImpl, env, day);
  report.d1 = usage;
  if (usage.ok) {
    for (const [metric, limit] of Object.entries(D1_LIMITS)) {
      const pct = (100 * usage[metric]) / limit;
      const crossed = D1_THRESHOLDS.filter((t) => pct >= t);
      if (!crossed.length) continue;
      const top = Math.max(...crossed);
      const key = `d1:${day}:${metric}:${top}`;
      if (await store.has(key)) continue;
      const label = metric === "rows_read" ? "rows read" : "rows written";
      lines.push(`[ops-watchdog] [D1 ${top}%] D1 ${label} today: ${usage[metric].toLocaleString("en-US")}`
        + ` of the free ${limit.toLocaleString("en-US")}/day (${pct.toFixed(0)}%). At 100% D1 stops`
        + ` serving ${metric === "rows_read" ? "reads" : "writes"} until 00:00 UTC.`);
      for (const t of crossed) marks.push([`d1:${day}:${metric}:${t}`, "1"]);
    }
  } else {
    // Unauthorized or unconfigured: degrade quietly; the supervisor's digest
    // reports the same status once a day.
    console.log(`ops-watchdog: D1 usage unavailable: ${usage.error}`);
  }

  // (c) dashboard payload freshness. The Pages site is behind Cloudflare
  // Access, so this reads the committed core.json the deploy serves.
  const maxCore = setting(env, "CORE_MAX_AGE_HOURS");
  const core = await readHeadField(fetchImpl, rawUrl(env, setting(env, "CORE_PATH")), "generated_at", 511);
  report.core = core;
  if (core.ok) {
    const age = hoursSince(now, core.at);
    report.core.age_hours = Math.round(age * 10) / 10;
    const tier = tierFor(age, maxCore);
    if (tier) {
      await once(`core-stale:${core.value}:${tier}`,
        `[ops-watchdog] [STALE DASHBOARD] dashboard/data/core.json on main was generated`
        + ` ${age.toFixed(0)}h ago (${core.value}); the dashboard is serving data older than`
        + ` ${maxCore}h.`);
    }
  } else {
    await once(`core-unreadable:${day}`,
      `[ops-watchdog] Cannot read dashboard/data/core.json from GitHub (${core.error}).`);
  }

  report.alerts = lines;
  report.sent = false;
  if (lines.length) {
    report.sent = await sendSlack(fetchImpl, env, lines.join("\n"));
    if (report.sent) {
      for (const [key, value] of marks) {
        if (value === null) await store.delete(key);
        else await store.put(key, value);
      }
    }
  }
  return report;
}

export async function sendSlack(fetchImpl, env, text) {
  if (!env.SLACK_WEBHOOK_URL) {
    console.log(`ops-watchdog: SLACK_WEBHOOK_URL not set; would have sent:\n${text}`);
    return false;
  }
  try {
    const response = await fetchImpl(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    return response.ok;
  } catch (err) {
    console.log(`ops-watchdog: Slack send failed: ${err && err.message ? err.message : err}`);
    return false;
  }
}
