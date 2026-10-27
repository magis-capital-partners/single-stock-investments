import { privateJson, requireHumanViewer } from "../_lib/auth.js";
import { requireDatabase } from "../_lib/http.js";
import { EDITORIAL_CHECKS, LETTER_SORT_SQL, letterWhere, pageArgs, readerArchiveEntry, readerFund, readerLetter, readerPeriod, readerSearchResult, readerTickerSignal, searchWhere, sourceSections, validateDraft } from "../_lib/fund-letters.js";

const all = async (db, sql, args = []) => (await db.prepare(sql).bind(...args).all()).results || [];
const first = (db, sql, args = []) => db.prepare(sql).bind(...args).first();
const run = (db, sql, args = []) => db.prepare(sql).bind(...args).run();
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
  if (["review", "source", "document", "revisions", "draft"].includes(action) && viewer.role !== "owner") return privateJson({ error: "Owner access required." }, 403);
  try {
    const db = requireDatabase(context.env);
    const { offset, limit } = pageArgs(params);
    if (action === "funds") {
      const [rows, periodRows, tickerRows] = await Promise.all([
        all(db, `SELECT f.id,f.name,f.manager,f.strategy,COUNT(l.id) letter_count,
          (SELECT COALESCE(NULLIF(l.reporting_period,''),l.letter_date) FROM fl_letters l WHERE l.fund_id=f.id AND l.published_revision IS NOT NULL ORDER BY ${LETTER_SORT_SQL} DESC,l.id LIMIT 1) latest
          FROM fl_funds f JOIN fl_letters l ON l.fund_id=f.id AND l.published_revision IS NOT NULL GROUP BY f.id ORDER BY f.name,f.id`),
        all(db, `SELECT reporting_period,COUNT(id) letter_count FROM fl_letters WHERE published_revision IS NOT NULL AND reporting_period IS NOT NULL AND reporting_period!='' GROUP BY reporting_period ORDER BY reporting_period DESC`),
        all(db, `SELECT UPPER(TRIM(i.ticker)) ticker,COUNT(DISTINCT l.fund_id) fund_count,COUNT(DISTINCT l.id) letter_count,
          SUM(CASE WHEN i.idea_type='long' OR LOWER(COALESCE(i.activity,'')) IN ('new','add') THEN 1 ELSE 0 END) bull_count,
          SUM(CASE WHEN i.idea_type='short' OR LOWER(COALESCE(i.activity,'')) IN ('short','trim','exit') THEN 1 ELSE 0 END) bear_count
          FROM fl_ideas i JOIN fl_letters l ON l.id=i.letter_id AND l.published_revision=i.revision_id
          WHERE i.ticker IS NOT NULL AND TRIM(i.ticker)!=''
          GROUP BY UPPER(TRIM(i.ticker))
          ORDER BY fund_count DESC,letter_count DESC,ticker ASC LIMIT 120`),
      ]);
      return privateJson({
        funds: rows.map(readerFund),
        periods: periodRows.map(readerPeriod).filter(p => p.period),
        tickers: tickerRows.map(readerTickerSignal).filter(t => t.ticker),
      });
    }
    if (action === "archive") {
      const letters = await all(db, `SELECT id,reporting_period,letter_date FROM fl_letters l WHERE fund_id=? AND published_revision IS NOT NULL ORDER BY ${LETTER_SORT_SQL} DESC,id`, [params.get("fund")]);
      return privateJson({ letters: letters.map(readerArchiveEntry) });
    }
    if (action === "letters") {
      const where = letterWhere(params);
      const rows = await all(db, `SELECT l.id,l.fund_id,f.name fund,l.reporting_period,l.letter_date,l.publication_date,
        r.id revision_id,r.overview,r.created_at,r.published_at,r.content_json FROM fl_letters l JOIN fl_funds f ON f.id=l.fund_id
        JOIN fl_revisions r ON r.id=l.published_revision WHERE ${where.sql}
        ORDER BY ${LETTER_SORT_SQL} DESC,l.id LIMIT ? OFFSET ?`, [...where.args, limit+1, offset]);
      const page = rows.slice(0, limit);
      const letters = await Promise.all(page.map(async row => {
        let stance = null, headline = null;
        try {
          const parsed = JSON.parse(row.content_json || "{}");
          stance = parsed.stance || null;
          headline = parsed.headline || null;
        } catch {
          stance = null;
          headline = null;
        }
        return readerLetter(row, await all(db, "SELECT * FROM fl_ideas WHERE letter_id=? AND revision_id=? ORDER BY ordinal", [row.id, row.revision_id]), stance, headline);
      }));
      return privateJson({ letters, next_offset: rows.length > limit ? offset+limit : null });
    }
    if (action === "search") {
      const where = searchWhere(params);
      const rows = await all(db, `SELECT i.*,l.fund_id,l.reporting_period,l.letter_date,f.name fund FROM fl_ideas i
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
      const evidence = await all(db, "SELECT idea_id,claims_json FROM fl_evidence WHERE revision_id=?", [params.get("revision") || letter.published_revision]);
      return privateJson({ source: letter, evidence });
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
