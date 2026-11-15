import { privateJson, requireHumanViewer } from "../_lib/auth.js";
import { requireDatabase } from "../_lib/http.js";
import { EDITORIAL_CHECKS, FIRST_MENTIONED_SQL, IDEA_IDENTITY_SQL, LETTER_SORT_SQL, LONG_SQL, OPPOSING_SQL, QUARTER, companyQuarters, independentCount, readerCompanyQuarter, letterSortSql, letterWhere, pageArgs, periodKeySql, readerArchiveEntry, readerExtras, readerFund, readerLetter, readerName, readerOverlap, readerPeriod, readerPrior, readerSearchResult, readerTickerSignal, readerWorkspaceFund, readerWorkspaceIdea, searchWhere, sourceSections, validateDraft, workspaceScope } from "../_lib/fund-letters.js";

const all = async (db, sql, args = []) => (await db.prepare(sql).bind(...args).all()).results || [];
const first = (db, sql, args = []) => db.prepare(sql).bind(...args).first();
const run = (db, sql, args = []) => db.prepare(sql).bind(...args).run();
const ORIGINAL_TEXT_BYTES = 20_000_000;
const IDEA_FROM = `FROM fl_ideas i JOIN fl_letters l ON l.id=i.letter_id AND l.published_revision=i.revision_id
  JOIN fl_funds f ON f.id=l.fund_id JOIN fl_revisions r ON r.id=l.published_revision`;
const TICKER_SHAPE = /^[A-Z0-9._-]{1,16}$/;
// Per company: funds discussing it, letters, and funds long or short-or-selling it.
const COMPANY_COUNTS = `t.ticker,MAX(t.name) name,COUNT(DISTINCT l.fund_id) fund_count,COUNT(DISTINCT l.id) letter_count,
  COUNT(DISTINCT CASE WHEN ${LONG_SQL} AND NOT ${OPPOSING_SQL} THEN l.fund_id END) long_count,COUNT(DISTINCT CASE WHEN ${OPPOSING_SQL} THEN l.fund_id END) short_count`;
const byManagers = (a, b) => b.managers - a.managers || b.letters - a.letters || a.ticker.localeCompare(b.ticker);

const tickersOf = (row) => {
  try {
    const tickers = JSON.parse(row.tickers || "[]");
    return Array.isArray(tickers) ? tickers.filter(ticker => typeof ticker === "string" && ticker) : [];
  } catch {
    return [];
  }
};

// For each idea naming a security, the same fund's latest discussion of any of its securities in an earlier quarter.
async function priorDiscussions(db, ideas) {
  const wanted = ideas.map(idea => [idea.fund_id, tickersOf(idea), idea.period_key || ""]);
  if (!wanted.some(([, tickers, key]) => tickers.length && key)) return new Map();
  const rows = await all(db, `WITH wanted AS (SELECT CAST(w.key AS INTEGER) k,json_extract(w.value,'$[0]') fund_id,json_extract(w.value,'$[2]') period_key,t.value ticker
      FROM json_each(?) w,json_each(json_extract(w.value,'$[1]')) t)
    SELECT w.k,p.id letter_id,p.reporting_period,p.letter_date,pi.title,pi.idea_type,pi.activity,pi.summary,pi.ordinal,${periodKeySql("p")} pk,${letterSortSql("p")} sk
    FROM wanted w JOIN fl_idea_tickers pt ON pt.ticker=w.ticker
    JOIN fl_ideas pi ON pi.revision_id=pt.revision_id AND pi.id=pt.idea_id AND pi.idea_type!='factual_note'
    JOIN fl_letters p ON p.id=pi.letter_id AND p.published_revision=pi.revision_id AND p.fund_id=w.fund_id
    WHERE w.period_key!='' AND ${periodKeySql("p")}!='' AND ${periodKeySql("p")}<w.period_key`, [JSON.stringify(wanted)]);
  const latest = new Map();
  for (const row of rows) {
    const best = latest.get(row.k);
    if (!best || row.pk > best.pk || (row.pk === best.pk && (row.sk > best.sk || (row.sk === best.sk && row.ordinal < best.ordinal)))) latest.set(row.k, row);
  }
  return latest;
}

// Independent managers per company in a view, and the latest quarter it was discussed, for the companies more than
// one fund discussed: each fund's newest discussion stands for it, and funds making a near-identical argument count once.
async function independentManagers(db, scope) {
  const rows = await all(db, `WITH named AS MATERIALIZED (SELECT t.ticker,l.fund_id,i.revision_id,i.id,i.summary,i.ordinal,l.id letter_id,
        ${periodKeySql("l")} period_key,${LETTER_SORT_SQL} sort_key ${IDEA_FROM}
        JOIN fl_idea_tickers t ON t.revision_id=i.revision_id AND t.idea_id=i.id WHERE ${scope.sql}),
      shared AS (SELECT ticker FROM named GROUP BY ticker HAVING COUNT(DISTINCT fund_id)>1)
    SELECT n.ticker,n.fund_id,n.summary,n.period_key,(SELECT e.claims_json FROM fl_evidence e WHERE e.revision_id=n.revision_id AND e.idea_id=n.id) claims
    FROM named n JOIN shared s ON s.ticker=n.ticker ORDER BY n.ticker,n.period_key DESC,n.sort_key DESC,n.letter_id,n.ordinal`, scope.args);
  const byTicker = new Map();
  for (const row of rows) {
    if (!byTicker.has(row.ticker)) byTicker.set(row.ticker, []);
    byTicker.get(row.ticker).push(row);
  }
  return new Map([...byTicker].map(([ticker, list]) => [ticker, { managers: independentCount(list), latest: list[0].period_key || "" }]));
}

// The quarter a workspace view shows: the one asked for, else the latest with published letters.
async function quarterOf(db, params) {
  const periodRows = await all(db, `SELECT reporting_period,COUNT(id) letter_count FROM fl_letters WHERE published_revision IS NOT NULL AND reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' GROUP BY reporting_period ORDER BY reporting_period DESC`);
  const requested = String(params.get("period") || "").trim().toUpperCase();
  return { periodRows, period: requested === "ALL" || QUARTER.test(requested) ? requested : periodRows[0]?.reporting_period || "ALL" };
}

// Applies the scope's groups one at a time and reports how many discussions survive each, so an empty
// view can name the filter that emptied it.
async function emptiedBy(db, scope) {
  const steps = [];
  for (let n = 1; n <= scope.groups.length; n += 1) {
    const kept = new Set(scope.groups.slice(0, n));
    const part = scope.pick(group => kept.has(group));
    const row = await first(db, `SELECT COUNT(*) n ${IDEA_FROM} WHERE ${part.sql}`, part.args);
    steps.push({ key: scope.groups[n - 1].key, label: scope.groups[n - 1].label, count: Number(row?.n || 0) });
    if (!row?.n) break;
  }
  return steps;
}
function httpsLink(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
async function boundedBody(request, maximum = 2_000_000) {
  const reader = request.body?.getReader();
  if (!reader) return "";
  const chunks = [];
  let size = 0;
  const decoder = new TextDecoder();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maximum) { await reader.cancel(); return null; }
    chunks.push(decoder.decode(value, { stream: true }));
  }
  chunks.push(decoder.decode());
  return chunks.join("");
}

export async function onRequestGet(context) {
  const viewer = await requireHumanViewer(context);
  if (!viewer) return privateJson({ error: "Sign in through Cloudflare Access." }, 401);
  const params = new URL(context.request.url).searchParams;
  const action = params.get("action") || "funds";
  if (action === "session") {
    let book_tickers = [];
    if (viewer.role === "owner" && context.env?.DB) {
      try {
        const rows = await all(context.env.DB, "SELECT DISTINCT symbol FROM portfolio_positions WHERE position != 0 AND symbol IS NOT NULL AND TRIM(symbol)!='' LIMIT 300");
        book_tickers = rows.map(r => String(r.symbol || "").trim().toUpperCase()).filter(Boolean);
      } catch {
        book_tickers = [];
      }
    }
    return privateJson({ role: viewer.role, email: viewer.email || null, ...(viewer.role === "owner" ? { book_tickers } : {}) });
  }
  if (["review", "source", "document", "original", "revisions", "draft"].includes(action) && viewer.role !== "owner") return privateJson({ error: "Owner access required." }, 403);
  try {
    const db = requireDatabase(context.env);
    const { offset, limit } = pageArgs(params);
    if (action === "funds") {
      const [rows, periodRows, tickerRows] = await Promise.all([
        all(db, `SELECT f.id,f.name,f.manager,f.strategy,COUNT(l.id) letter_count,
          (SELECT COALESCE(NULLIF(l.reporting_period,''),l.letter_date) FROM fl_letters l WHERE l.fund_id=f.id AND l.published_revision IS NOT NULL ORDER BY ${LETTER_SORT_SQL} DESC,l.id LIMIT 1) latest
          FROM fl_funds f JOIN fl_letters l ON l.fund_id=f.id AND l.published_revision IS NOT NULL GROUP BY f.id ORDER BY f.name,f.id`),
        all(db, `SELECT reporting_period,COUNT(id) letter_count FROM fl_letters WHERE published_revision IS NOT NULL AND reporting_period IS NOT NULL AND reporting_period!='' GROUP BY reporting_period ORDER BY reporting_period DESC`),
        all(db, `SELECT t.ticker,COUNT(DISTINCT l.fund_id) fund_count,COUNT(DISTINCT l.id) letter_count,
          SUM(CASE WHEN i.idea_type='long' OR LOWER(COALESCE(i.activity,'')) IN ('new','add') THEN 1 ELSE 0 END) bull_count,
          SUM(CASE WHEN i.idea_type='short' OR LOWER(COALESCE(i.activity,'')) IN ('short','trim','exit') THEN 1 ELSE 0 END) bear_count
          FROM fl_idea_tickers t JOIN fl_ideas i ON i.revision_id=t.revision_id AND i.id=t.idea_id
          JOIN fl_letters l ON l.id=i.letter_id AND l.published_revision=i.revision_id
          GROUP BY t.ticker
          ORDER BY fund_count DESC,letter_count DESC,t.ticker ASC LIMIT 120`),
      ]);
      return privateJson({
        funds: rows.map(readerFund),
        periods: periodRows.map(readerPeriod).filter(p => p.period),
        tickers: tickerRows.map(readerTickerSignal).filter(t => t.ticker),
      });
    }
    if (action === "workspace") {
      const { periodRows, period } = await quarterOf(db, params);
      const scoped = new URLSearchParams(params);
      scoped.set("period", period);
      scoped.delete("fund");
      const scope = workspaceScope(scoped);
      const letterLevel = scope.groups.filter(group => group.key === "period");
      const filtered = scope.groups.some(group => group.key !== "period");
      const ideaPart = scope.pick(group => group.key !== "period");
      const letterSql = letterLevel.map(group => group.sql).join(" AND ") || "1";
      const [fundRows, overlapRows, unresolvedRow, managers] = await Promise.all([
        all(db, `SELECT f.id,f.name,COUNT(DISTINCT l.id) letter_count,COUNT(i.id) discussions,MAX(l.reporting_period) reporting_period,
          MAX(l.letter_date) letter_date FROM fl_letters l JOIN fl_funds f ON f.id=l.fund_id JOIN fl_revisions r ON r.id=l.published_revision
          LEFT JOIN fl_ideas i ON i.letter_id=l.id AND i.revision_id=l.published_revision AND ${ideaPart.sql}
          WHERE ${letterSql} GROUP BY f.id ${filtered ? "HAVING COUNT(i.id)>0" : ""} ORDER BY f.name,f.id`,
          [...ideaPart.args, ...letterLevel.flatMap(group => group.args)]),
        all(db, `SELECT ${COMPANY_COUNTS} ${IDEA_FROM} JOIN fl_idea_tickers t ON t.revision_id=i.revision_id AND t.idea_id=i.id
          WHERE ${scope.sql} GROUP BY t.ticker HAVING COUNT(DISTINCT l.fund_id)>=2
          ORDER BY fund_count DESC,letter_count DESC,t.ticker LIMIT 60`, scope.args),
        // Mentions not matched to a security are listed on their cards but never counted.
        first(db, `SELECT COUNT(*) n ${IDEA_FROM} JOIN fl_idea_entities e ON e.revision_id=i.revision_id AND e.idea_id=i.id AND e.status='unresolved'
          AND e.resolver=(SELECT value FROM fl_settings WHERE key='entity_resolver') WHERE ${scope.sql}`, scope.args),
        independentManagers(db, scope),
      ]);
      const funds = fundRows.map(readerWorkspaceFund);
      const totals = { funds: funds.length, letters: funds.reduce((n, fund) => n + fund.letters, 0), discussions: funds.reduce((n, fund) => n + fund.discussions, 0),
        unresolved: Number(unresolvedRow?.n || 0) };
      return privateJson({
        period,
        periods: periodRows.map(readerPeriod).filter(p => p.period),
        funds,
        totals,
        overlap: overlapRows.map(row => readerOverlap({ ...row, managers: managers.get(row.ticker)?.managers }))
          .filter(row => TICKER_SHAPE.test(row.ticker) && row.managers >= 2).sort(byManagers).slice(0, 24),
        ...(filtered && !totals.discussions ? { emptied_by: await emptiedBy(db, scope) } : {}),
      });
    }
    if (action === "ideas") {
      const scope = workspaceScope(params);
      // Companies that more independent managers discussed in this view come first, the most recently discussed
      // first among equals, each company's ideas together; ideas on no shared company follow, newest first.
      const companies = [...await independentManagers(db, scope)]
        .sort(([a, x], [b, y]) => y.managers - x.managers || (y.latest > x.latest) - (y.latest < x.latest) || a.localeCompare(b))
        .map(([ticker, row], rank) => [ticker, row.managers, rank]);
      const rows = await all(db, `WITH counts AS MATERIALIZED (SELECT json_extract(value,'$[0]') ticker,json_extract(value,'$[1]') n,json_extract(value,'$[2]') rank FROM json_each(?)),
          ranked AS MATERIALIZED (SELECT t.revision_id,t.idea_id,MAX(c.n) n,MIN(c.rank) rank FROM counts c JOIN fl_idea_tickers t ON t.ticker=c.ticker GROUP BY t.revision_id,t.idea_id)
        SELECT i.id,i.title,${IDEA_IDENTITY_SQL("i")},i.idea_type,i.activity,i.summary,i.evolution,i.compared_letter_id,i.letter_id,
        l.fund_id,l.reporting_period,l.letter_date,f.name fund,${periodKeySql("l")} period_key,(${FIRST_MENTIONED_SQL}) first_mentioned,
        COALESCE(rk.n,1) managers
        ${IDEA_FROM} LEFT JOIN ranked rk ON rk.revision_id=i.revision_id AND rk.idea_id=i.id WHERE ${scope.sql}
        ORDER BY managers DESC,COALESCE(rk.rank,1e9),period_key DESC,${LETTER_SORT_SQL} DESC,f.name,l.id,i.ordinal LIMIT ? OFFSET ?`, [JSON.stringify(companies), ...scope.args, limit+1, offset]);
      const page = rows.slice(0, limit);
      const priors = await priorDiscussions(db, page);
      return privateJson({
        results: page.map((row, index) => readerWorkspaceIdea(row, priors.get(index))),
        next_offset: rows.length > limit ? offset+limit : null,
        ...(!page.length && scope.groups.length ? { emptied_by: await emptiedBy(db, scope) } : {}),
      });
    }
    if (action === "ticker") {
      const { periodRows, period } = await quarterOf(db, params);
      const scoped = new URLSearchParams(params);
      scoped.set("period", period);
      scoped.delete("fund");
      const scope = workspaceScope(scoped);
      const ticker = String(params.get("ticker") || "").trim().toUpperCase();
      const periods = periodRows.map(readerPeriod).filter(p => p.period);
      if (!TICKER_SHAPE.test(ticker)) {
        const [rows, managers] = await Promise.all([
          all(db, `SELECT ${COMPANY_COUNTS} ${IDEA_FROM} JOIN fl_idea_tickers t ON t.revision_id=i.revision_id AND t.idea_id=i.id
            WHERE ${scope.sql} GROUP BY t.ticker ORDER BY fund_count DESC,letter_count DESC,t.ticker LIMIT 150`, scope.args),
          independentManagers(db, scope),
        ]);
        return privateJson({ period, periods, companies: rows.map(row => readerOverlap({ ...row, managers: managers.get(row.ticker)?.managers })).sort(byManagers),
          ...(!rows.length && scope.groups.length ? { emptied_by: await emptiedBy(db, scope) } : {}) });
      }
      const select = `SELECT i.id,i.title,${IDEA_IDENTITY_SQL("i")},i.idea_type,i.activity,i.summary,i.evolution,i.compared_letter_id,i.letter_id,
        l.fund_id,l.reporting_period,l.letter_date,f.name fund,${periodKeySql("l")} period_key,(${FIRST_MENTIONED_SQL}) first_mentioned,
        (SELECT e.claims_json FROM fl_evidence e WHERE e.revision_id=i.revision_id AND e.idea_id=i.id) claims ${IDEA_FROM}`;
      const order = `ORDER BY period_key DESC,${LETTER_SORT_SQL} DESC,l.id,i.ordinal`;
      // The chosen quarter under every filter, then the company's earlier quarters in full, for context.
      const history = workspaceScope(new URLSearchParams({ ticker, period: "ALL" }));
      const [current, earlier, named] = await Promise.all([
        all(db, `${select} WHERE ${scope.sql} ${order} LIMIT 400`, scope.args),
        period === "ALL" ? [] : all(db, `${select} WHERE ${history.sql} AND ${periodKeySql("l")}!='' AND ${periodKeySql("l")}<? ${order} LIMIT 200`, [...history.args, period]),
        first(db, "SELECT name FROM fl_idea_tickers WHERE ticker=? AND COALESCE(name,'')!='' GROUP BY name ORDER BY COUNT(*) DESC,name LIMIT 1", [ticker]),
      ]);
      const quarters = [...companyQuarters(current), ...companyQuarters(earlier)].slice(0, 12);
      return privateJson({ ticker, name: readerName(named?.name), period, periods, managers: independentCount(current), quarters: quarters.map(readerCompanyQuarter),
        current: current.length ? quarters[0].period : null,
        ...(!current.length ? { emptied_by: await emptiedBy(db, scope) } : {}) });
    }
    if (action === "archive") {
      const [letters, fund] = await Promise.all([
        all(db, `SELECT id,reporting_period,letter_date FROM fl_letters l WHERE fund_id=? AND published_revision IS NOT NULL ORDER BY ${LETTER_SORT_SQL} DESC,id`, [params.get("fund")]),
        first(db, "SELECT name FROM fl_funds WHERE id=?", [params.get("fund")]),
      ]);
      return privateJson({ letters: letters.map(readerArchiveEntry), fund_name: readerName(fund?.name) });
    }
    if (action === "letters") {
      const where = letterWhere(params);
      const rows = await all(db, `SELECT l.id,l.fund_id,f.name fund,l.reporting_period,l.letter_date,l.publication_date,${periodKeySql("l")} period_key,
        r.id revision_id,r.overview,r.created_at,r.published_at,r.content_json FROM fl_letters l JOIN fl_funds f ON f.id=l.fund_id
        JOIN fl_revisions r ON r.id=l.published_revision WHERE ${where.sql}
        ORDER BY ${LETTER_SORT_SQL} DESC,l.id LIMIT ? OFFSET ?`, [...where.args, limit+1, offset]);
      const page = rows.slice(0, limit);
      const letterScope = workspaceScope(params);
      const matching = letterScope.pick(group => !["period", "fund"].includes(group.key));
      const narrowed = letterScope.groups.some(group => !["period", "fund"].includes(group.key));
      const letters = await Promise.all(page.map(async row => {
        let stance = null, headline = null, extras = null;
        try {
          const parsed = JSON.parse(row.content_json || "{}");
          stance = parsed.stance || null;
          headline = parsed.headline || null;
          extras = readerExtras(parsed);
        } catch {
          stance = null;
          headline = null;
          extras = null;
        }
        const ideas = await all(db, `SELECT i.*,${IDEA_IDENTITY_SQL("i")},(${FIRST_MENTIONED_SQL}) first_mentioned FROM fl_ideas i JOIN fl_letters l ON l.id=i.letter_id
          WHERE i.letter_id=? AND i.revision_id=? ORDER BY i.ordinal`, [row.id, row.revision_id]);
        const [priors, matched] = await Promise.all([
          priorDiscussions(db, ideas.map(idea => ({ fund_id: row.fund_id, tickers: idea.tickers, period_key: row.period_key }))),
          narrowed ? all(db, `SELECT i.id ${IDEA_FROM} WHERE l.id=? AND ${matching.sql}`, [row.id, ...matching.args]) : null,
        ]);
        const letter = readerLetter(row, ideas, stance, headline, extras);
        const matchedIds = matched ? new Set(matched.map(match => match.id)) : null;
        letter.ideas.forEach((idea, index) => {
          idea.first_mentioned = Boolean(ideas[index].first_mentioned);
          idea.prior = readerPrior(priors.get(index));
          if (matchedIds) idea.matches = matchedIds.has(ideas[index].id);
        });
        return letter;
      }));
      return privateJson({ letters, next_offset: rows.length > limit ? offset+limit : null });
    }
    if (action === "search") {
      const where = searchWhere(params);
      const rows = await all(db, `SELECT i.*,${IDEA_IDENTITY_SQL("i")},l.fund_id,l.reporting_period,l.letter_date,f.name fund FROM fl_ideas i
        JOIN fl_letters l ON l.id=i.letter_id AND l.published_revision=i.revision_id JOIN fl_funds f ON f.id=l.fund_id
        JOIN fl_revisions r ON r.id=l.published_revision
        WHERE ${where.sql} ORDER BY ${LETTER_SORT_SQL} DESC,l.id,i.ordinal LIMIT ? OFFSET ?`, [...where.args, limit+1, offset]);
      return privateJson({ results: rows.slice(0,limit).map(readerSearchResult), next_offset: rows.length > limit ? offset+limit : null });
    }
    if (action === "review") {
      const clauses = ["q.status='open'"];
      const args = [];
      if (params.get("review_q")) {
        const match = `%${params.get("review_q").replace(/[\\%_]/g, "\\$&")}%`;
        clauses.push("(f.name LIKE ? ESCAPE '\\' OR q.detail LIKE ? ESCAPE '\\' OR l.id LIKE ? ESCAPE '\\')");
        args.push(match, match, match);
      }
      if (params.get("letter")) { clauses.push("l.id=?"); args.push(params.get("letter")); }
      const reviews = await all(db, `SELECT q.*,f.name fund,l.reporting_period,l.letter_date FROM fl_reviews q JOIN fl_letters l ON l.id=q.letter_id JOIN fl_funds f ON f.id=l.fund_id WHERE ${clauses.join(' AND ')} ORDER BY q.kind,f.name,l.reporting_period DESC,l.id LIMIT ? OFFSET ?`, [...args, limit+1, offset]);
      const coverage = await first(db, "SELECT COUNT(*) letters,SUM(published_revision IS NOT NULL) published FROM fl_letters");
      return privateJson({ reviews: reviews.slice(0,limit), coverage, next_offset: reviews.length > limit ? offset+limit : null });
    }
    if (action === "document") {
      const letter = await first(db, "SELECT id,content_hash,source_text FROM fl_letters WHERE id=?", [params.get("letter")]);
      if (!letter) return privateJson({ error: "Letter not found." }, 404);
      const object = letter.source_text ? null : await context.env.PRIVATE_ARTIFACTS?.get(`fund-letters/source/${letter.content_hash}.txt`);
      if (!letter.source_text && !object) return privateJson({ error: "Original text is unavailable; resolve the extraction issue first." }, 404);
      return new Response(letter.source_text || object.body, { headers: {
        "content-type": "text/plain; charset=utf-8", "cache-control": "no-store, private", "cdn-cache-control": "no-store",
        "content-disposition": `inline; filename="${String(letter.id).replace(/[^a-zA-Z0-9_-]/g,'')}.txt"`,
        "content-security-policy": "sandbox; default-src 'none'", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
      }});
    }
    if (action === "original") {
      const letter = await first(db, `SELECT l.id,l.content_hash,l.source_text,l.source_url,l.reporting_period,l.letter_date,f.name fund
        FROM fl_letters l JOIN fl_funds f ON f.id=l.fund_id WHERE l.id=?`, [params.get("letter")]);
      if (!letter) return privateJson({ error: "Letter not found." }, 404);
      let text = letter.source_text || "";
      if (!text) {
        const object = await context.env.PRIVATE_ARTIFACTS?.get(`fund-letters/source/${letter.content_hash}.txt`);
        if (object && !(object.size > ORIGINAL_TEXT_BYTES)) text = await object.text();
      }
      const original_url = httpsLink(letter.source_url);
      const driveFile = original_url && new URL(original_url).hostname === "drive.google.com"
        ? (original_url.match(/^(.+\/file\/d\/[A-Za-z0-9_-]{10,})/) || [])[1] : null;
      return privateJson({
        letter: { id: letter.id, fund: letter.fund, reporting_period: letter.reporting_period, letter_date: letter.letter_date },
        text, original_url, in_drive: Boolean(driveFile),
        preview_url: driveFile ? `${driveFile}/preview` : null,
      });
    }
    if (["source", "revisions", "draft"].includes(action)) {
      const letterId = params.get("letter");
      if (action === "revisions") return privateJson({ revisions: await all(db, "SELECT id,created_at,published_at,author,status,previous_revision,checks_json FROM fl_revisions WHERE letter_id=? ORDER BY created_at DESC,id", [letterId]), publications: await all(db, "SELECT revision_id,previous_revision,author,created_at,action FROM fl_publication_events WHERE letter_id=? ORDER BY created_at DESC,id", [letterId]) });
      if (action === "draft") {
        const revision = params.get("revision");
        const row = await first(db, `SELECT * FROM fl_revisions WHERE letter_id=? ${revision ? "AND id=?" : ""} ORDER BY created_at DESC,id DESC LIMIT 1`, revision ? [letterId, revision] : [letterId]);
        return privateJson({ draft: row ? { ...row, content: JSON.parse(row.content_json) } : null });
      }
      const letter = await first(db, "SELECT id,fund_id,reporting_period,letter_date,source_ref,source_url,alternate_sources_json,published_revision FROM fl_letters WHERE id=?", [letterId]);
      if (!letter) return privateJson({ error: "Letter not found." }, 404);
      const revisionId = params.get("revision") || letter.published_revision;
      const evidence = await all(db, "SELECT idea_id,claims_json FROM fl_evidence WHERE revision_id=?", [revisionId]);
      // Owners also get the quoted source text behind each transcribed table, in stored order,
      // so a table can be opened in the original.
      let tables = [];
      try {
        const stored = await first(db, "SELECT content_json FROM fl_revisions WHERE id=? AND letter_id=?", [revisionId, letterId]);
        const parsed = JSON.parse(stored?.content_json || "{}").tables;
        if (Array.isArray(parsed)) tables = parsed.map(table => ({ section_id: String(table?.section_id || ""), quote: String(table?.quote || "") }));
      } catch {
        tables = [];
      }
      return privateJson({ source: letter, evidence, tables });
    }
    return privateJson({ error: "Unknown archive action." }, 400);
  } catch (error) {
    console.error(JSON.stringify({ message: "Fund Letters read failed", error: error.message }));
    return privateJson({ error: error instanceof TypeError ? error.message : "The archive is unavailable. Try again shortly." }, error instanceof TypeError ? 400 : 503);
  }
}

export async function onRequestPost(context) {
  const viewer = await requireHumanViewer(context);
  if (!viewer) return privateJson({ error: "Authentication required." }, 401);
  if (viewer.role !== "owner") return privateJson({ error: "Owner access required." }, 403);
  if (context.request.headers.get("origin") !== new URL(context.request.url).origin || !context.request.headers.get("content-type")?.startsWith("application/json")) return privateJson({ error: "Use this application's review controls." }, 403);
  try {
    const body = await boundedBody(context.request);
    if (body === null) return privateJson({ error: "Draft too large." }, 413);
    const payload = JSON.parse(body);
    const db = requireDatabase(context.env);
    const stamp = new Date().toISOString();
    const letter = await first(db, "SELECT * FROM fl_letters WHERE id=?", [payload.letter_id]);
    if (!letter) return privateJson({ error: "Letter not found." }, 404);
    if (payload.action === "resolve") {
      if (!payload.reason?.trim()) throw new TypeError("Record the review decision.");
      await run(db, "UPDATE fl_reviews SET status='resolved',detail=? WHERE letter_id=? AND kind=?", [`${viewer.email} · ${stamp}: ${payload.reason}`, letter.id, payload.kind]);
      return privateJson({ ok: true });
    }
    if (payload.action === "date") {
      if (payload.letter_date !== null && (!/^\d{4}-\d{2}-\d{2}$/.test(payload.letter_date) || !Number.isFinite(Date.parse(payload.letter_date)) || new Date(payload.letter_date).toISOString().slice(0,10) !== payload.letter_date || payload.letter_date > stamp.slice(0,10))) throw new TypeError("Use a verified historical letter date or null.");
      if (!payload.reason?.trim()) throw new TypeError("Record the date evidence.");
      await db.batch([
        db.prepare("UPDATE fl_letters SET letter_date=?,date_source='owner_verified' WHERE id=?").bind(payload.letter_date, letter.id),
        db.prepare("UPDATE fl_reviews SET status='resolved',detail=? WHERE letter_id=? AND kind='date'").bind(`${viewer.email}: ${payload.reason}`, letter.id),
      ]);
      return privateJson({ ok: true });
    }
    let revision;
    if (["publish", "rollback"].includes(payload.action)) {
      revision = await first(db, "SELECT * FROM fl_revisions WHERE id=? AND letter_id=?", [payload.revision_id, letter.id]);
      if (!revision) throw new TypeError("Choose an existing revision of this letter.");
    }
    const draft = payload.action === "draft" ? payload.draft : revision ? JSON.parse(revision.content_json) : null;
    if (!draft) throw new TypeError("Unknown review action.");
    const object = letter.source_text ? null : await context.env.PRIVATE_ARTIFACTS?.get(`fund-letters/source/${letter.content_hash}.txt`);
    if (object?.size > 20_000_000) return privateJson({ error: "Review this large source through the offline pipeline." }, 413);
    const original = letter.source_text || await object?.text();
    if (!original) return privateJson({ error: "Original document unavailable; publication is blocked." }, 409);
    const errors = validateDraft(draft, sourceSections(original));
    for (const idea of draft.ideas || []) {
      if (idea.compared_letter_id) {
        const earlier = await first(db, `SELECT l.id FROM fl_letters l WHERE l.id=? AND l.fund_id=? AND l.published_revision IS NOT NULL AND ${LETTER_SORT_SQL}<(SELECT ${LETTER_SORT_SQL} FROM fl_letters l WHERE l.id=?)`, [idea.compared_letter_id, letter.fund_id, letter.id]);
        if (!earlier) errors.push("Evolution must reference an earlier letter of the same fund.");
      }
    }
    if (payload.action === "draft") {
      if (!Array.isArray(draft.ideas) || draft.ideas.some(i => !i?.id || !i.title || typeof i.summary !== "string" || !i.idea_type)) return privateJson({ error: "Draft structure is incomplete.", errors }, 422);
      const id = `rev-${crypto.randomUUID()}`;
      const statements = [db.prepare("INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json,previous_revision) VALUES(?,?,?,?,?,?,?,?,?)").bind(id, letter.id, stamp, viewer.email, errors.length ? "failed" : "needs_review", draft.overview || "", JSON.stringify(draft), JSON.stringify({ errors }), letter.published_revision)];
      // JSON table insertion keeps a letter with hundreds of ideas within the request query budget.
      const ideas = JSON.stringify(draft.ideas);
      statements.push(db.prepare(`INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,evolution,compared_letter_id,ordinal)
        SELECT json_extract(value,'$.id'),?,?,json_extract(value,'$.title'),json_extract(value,'$.ticker'),json_extract(value,'$.idea_type'),json_extract(value,'$.activity'),json_extract(value,'$.summary'),json_extract(value,'$.evolution'),json_extract(value,'$.compared_letter_id'),CAST(key AS INTEGER) FROM json_each(?)`).bind(id, letter.id, ideas));
      statements.push(db.prepare("INSERT INTO fl_evidence SELECT ?,json_extract(value,'$.id'),COALESCE(json_extract(value,'$.evidence'),'[]') FROM json_each(?)").bind(id, ideas));
      await db.batch(statements);
      return privateJson({ revision_id: id, errors }, 201);
    }
    if (!EDITORIAL_CHECKS.every(key => payload.attestations?.[key] === true)) errors.push("Explicitly complete all six editorial checks.");
    if (await first(db, "SELECT 1 found FROM fl_reviews WHERE letter_id=? AND status='open' AND kind IN ('identity','extraction','duplicate_sources') LIMIT 1", [letter.id])) errors.push("Resolve identity, extraction and alternate-source reviews first.");
    if (errors.length) return privateJson({ error: "Publication blocked.", errors }, 422);
    // Optimistic concurrency: a second editor cannot silently replace a newly published revision.
    if ((payload.expected_revision || null) !== (letter.published_revision || null)) return privateJson({ error: "Published revision changed. Reload before publishing." }, 409);
    const checks = JSON.stringify({ editorial: payload.attestations, reviewed_by: viewer.email, reviewed_at: stamp, errors: [] });
    const results = await db.batch([
      db.prepare("UPDATE fl_letters SET published_revision=?,status='published' WHERE id=? AND published_revision IS ?").bind(revision.id, letter.id, letter.published_revision),
      db.prepare("UPDATE fl_revisions SET status='published',published_at=COALESCE(published_at,?),checks_json=? WHERE id=? AND EXISTS(SELECT 1 FROM fl_letters WHERE id=? AND published_revision=?)").bind(stamp, checks, revision.id, letter.id, revision.id),
      db.prepare("UPDATE fl_reviews SET status='resolved' WHERE letter_id=? AND kind='summary' AND EXISTS(SELECT 1 FROM fl_letters WHERE id=? AND published_revision=?)").bind(letter.id, letter.id, revision.id),
      db.prepare("INSERT INTO fl_publication_events SELECT ?,?,?,?,?,?,? WHERE EXISTS(SELECT 1 FROM fl_letters WHERE id=? AND published_revision=?)").bind(crypto.randomUUID(), letter.id, revision.id, letter.published_revision, viewer.email, stamp, payload.action, letter.id, revision.id),
    ]);
    if (!results[0].meta?.changes) return privateJson({ error: "Published revision changed. Reload before publishing." }, 409);
    return privateJson({ ok: true, revision_id: revision.id });
  } catch (error) {
    console.error(JSON.stringify({ message: "Fund Letters write failed", error: error.message }));
    return privateJson({ error: error instanceof TypeError || error instanceof SyntaxError ? error.message : "Review could not be saved." }, error instanceof TypeError || error instanceof SyntaxError ? 400 : 503);
  }
}
