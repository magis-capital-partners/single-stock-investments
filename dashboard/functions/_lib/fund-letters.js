export const EDITORIAL_CHECKS = ["complete_document", "idea_coverage", "claim_accuracy", "numerical_accuracy", "original_writing", "historical_dates"];
export const IDEA_TYPES = new Set(["long", "short", "update", "postmortem", "special_situation", "credit", "private", "unnamed", "sector", "macro", "portfolio", "factual_note"]);
// A period endpoint is an internal ordering fallback only, never a verified displayed date.
export const letterSortSql = (a) => `COALESCE(${a}.letter_date,${a}.publication_date,CASE WHEN ${a}.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN substr(${a}.reporting_period,1,4)||CASE substr(${a}.reporting_period,6,1) WHEN '1' THEN '-03-31' WHEN '2' THEN '-06-30' WHEN '3' THEN '-09-30' ELSE '-12-31' END ELSE ${a}.reporting_period END,'')`;
export const LETTER_SORT_SQL = letterSortSql("l");
// The reporting quarter, else the quarter of a known letter date; '' when neither is known, so an
// undated letter is never treated as earlier than another.
export const periodKeySql = (a) => `COALESCE(CASE WHEN ${a}.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN ${a}.reporting_period END,`
  + `CASE WHEN COALESCE(${a}.letter_date,${a}.publication_date) GLOB '[0-9][0-9][0-9][0-9]-[01][0-9]*' THEN substr(COALESCE(${a}.letter_date,${a}.publication_date),1,4)||'Q'||((CAST(substr(COALESCE(${a}.letter_date,${a}.publication_date),6,2) AS INTEGER)+2)/3) END,'')`;
export const tickerKeySql = (a) => `UPPER(TRIM(COALESCE(${a}.ticker,'')))`;

export const MULTI_FUND_TICKERS_SQL = `SELECT UPPER(TRIM(i2.ticker)) FROM fl_ideas i2
  JOIN fl_letters l2 ON l2.id=i2.letter_id AND l2.published_revision=i2.revision_id
  WHERE i2.ticker IS NOT NULL AND TRIM(i2.ticker)!=''
  GROUP BY UPPER(TRIM(i2.ticker))
  HAVING COUNT(DISTINCT l2.fund_id) >= 2`;

export const BATTLEGROUND_TICKERS_SQL = `SELECT UPPER(TRIM(i2.ticker)) FROM fl_ideas i2
  JOIN fl_letters l2 ON l2.id=i2.letter_id AND l2.published_revision=i2.revision_id
  WHERE i2.ticker IS NOT NULL AND TRIM(i2.ticker)!=''
  GROUP BY UPPER(TRIM(i2.ticker))
  HAVING SUM(CASE WHEN i2.idea_type='long' OR LOWER(COALESCE(i2.activity,'')) IN ('new','add') THEN 1 ELSE 0 END) > 0
     AND SUM(CASE WHEN i2.idea_type='short' OR LOWER(COALESCE(i2.activity,'')) IN ('short','trim','exit') THEN 1 ELSE 0 END) > 0`;

// Deliberate field allowlists. Never spread database rows into reader responses.
const safe = (value) => {
  const text = String(value ?? "");
  return /https?:\/\/|drive\.google|_system[\\/]|[a-z]:[\\/]/i.test(text) ? "" : text;
};
// A citation reaches readers only as a passage number. The quoted source words stay private.
const passageNumber = (id) => (typeof id === "string" && /^s\d{1,5}$/.test(id) ? Number(id.slice(1)) : null);
export function readerIdea(row, cites = null) {
  const idea = { id: safe(row.id), title: safe(row.title), ticker: safe(row.ticker), idea_type: safe(row.idea_type),
    activity: safe(row.activity), summary: safe(row.summary), evolution: safe(row.evolution), compared_letter_id: safe(row.compared_letter_id) };
  // One passage number for each line of the summary, or nothing at all.
  const passages = Array.isArray(cites) && cites.length <= 2000 ? cites.map(passageNumber) : [];
  if (passages.length && passages.every(Boolean) && passages.length === idea.summary.split("\n").filter(line => line.trim()).length) idea.cites = passages;
  return idea;
}
// A table transcribed from the letter: its title, column headings and rows of values, with the passage
// it came from. `index` is its place in the stored draft, which is how an owner asks for its quote.
function readerTables(items, ideaIds) {
  const cell = (value) => (typeof value === "string" ? safe(value).trim().slice(0, 160) : "");
  const tables = [];
  (Array.isArray(items) ? items : []).slice(0, 12).forEach((item, index) => {
    if (!item || typeof item !== "object" || !Array.isArray(item.columns) || !Array.isArray(item.rows)) return;
    const columns = item.columns.slice(0, 12).map(cell);
    const rows = item.rows.slice(0, 40)
      .filter(row => row && typeof row === "object" && Array.isArray(row.values) && row.values.length === columns.length)
      .map(row => ({ label: cell(row.label), values: row.values.map(cell) }));
    if (columns.length < 2 || columns.some(column => !column) || !rows.length || rows.some(row => !row.label || row.values.some(value => !value))) return;
    tables.push({ index, idea_id: typeof item.idea_id === "string" && ideaIds.has(item.idea_id) ? item.idea_id : null,
      passage: passageNumber(item.section_id), title: cell(item.title), columns, rows });
  });
  return tables;
}
const COVERAGE_KEYS = ["sections", "sections_cited", "topics", "statements", "tables", "tables_omitted", "figures", "source_words", "summary_words"];
function readerCoverage(coverage) {
  if (!coverage || typeof coverage !== "object" || Array.isArray(coverage)) return null;
  const result = {};
  for (const key of COVERAGE_KEYS) if (Number.isSafeInteger(coverage[key]) && coverage[key] >= 0) result[key] = coverage[key];
  return result.sections ? result : null;
}
// The reader-safe parts of a stored draft beyond its ideas: transcribed tables, coverage counts and per-line citations.
export function readerExtras(content) {
  const draft = content && typeof content === "object" ? content : {};
  const cites = new Map();
  for (const idea of Array.isArray(draft.ideas) ? draft.ideas : []) if (idea && typeof idea.id === "string" && Array.isArray(idea.cites)) cites.set(idea.id, idea.cites);
  return { tables: draft.tables, coverage: draft.coverage, cites };
}
function readerStance(stance) {
  if (!stance || typeof stance !== "object") return null;
  const lean = (items) => (Array.isArray(items) ? items : [])
    .filter(item => item && typeof item === "object" && safe(item.subject) && safe(item.why))
    .map(item => ({ subject: safe(item.subject), why: safe(item.why) }));
  const focus = safe(stance.focus);
  const result = { focus: ["micro", "macro", "mixed"].includes(focus) ? focus : "micro", leaning_in: lean(stance.leaning_in), leaning_out: lean(stance.leaning_out) };
  return result.leaning_in.length || result.leaning_out.length ? result : null;
}
export function readerLetter(row, ideas, stance = null, headline = null, extras = null) {
  const focus = safe(stance?.focus || row?.focus);
  const tables = readerTables(extras?.tables, new Set(ideas.map(idea => idea.id)));
  const coverage = readerCoverage(extras?.coverage);
  const cites = extras?.cites instanceof Map ? extras.cites : new Map();
  return { id: safe(row.id), fund_id: safe(row.fund_id), fund: safe(row.fund), reporting_period: safe(row.reporting_period),
    letter_date: safe(row.letter_date) || null, publication_date: safe(row.publication_date) || null,
    summary_published_at: safe(row.published_at), summary_revised_at: safe(row.created_at),
    revision_id: safe(row.revision_id), headline: safe(headline ?? row.headline) || null,
    focus: ["micro", "macro", "mixed"].includes(focus) ? focus : null,
    overview: safe(row.overview), stance: readerStance(stance), ideas: ideas.map(idea => readerIdea(idea, cites.get(idea.id))),
    ...(tables.length ? { tables } : {}), ...(coverage ? { coverage } : {}) };
}
export function readerFund(row) {
  return { id: safe(row.id), name: safe(row.name), manager: safe(row.manager), strategy: safe(row.strategy), letter_count: Number(row.letter_count), latest: safe(row.latest) };
}
export function readerPeriod(row) {
  return { period: safe(row.reporting_period), count: Number(row.letter_count || 0) };
}
export function readerTickerSignal(row) {
  const ticker = safe(row.ticker).trim().toUpperCase();
  const fund_count = Number(row.fund_count || 0);
  const letter_count = Number(row.letter_count || 0);
  const bull_count = Number(row.bull_count || 0);
  const bear_count = Number(row.bear_count || 0);
  return {
    ticker,
    fund_count,
    letter_count,
    bull_count,
    bear_count,
    multi_fund: fund_count >= 2,
    battleground: bull_count > 0 && bear_count > 0,
  };
}
export const readerName = (value) => safe(value) || null;
export function readerArchiveEntry(row) {
  return { id: safe(row.id), reporting_period: safe(row.reporting_period), letter_date: safe(row.letter_date) || null };
}
export function readerSearchResult(row) {
  return { ...readerIdea(row), fund_id: safe(row.fund_id), fund: safe(row.fund), letter_id: safe(row.letter_id), reporting_period: safe(row.reporting_period), letter_date: safe(row.letter_date) || null };
}
// The same fund's most recent earlier discussion of a company, shown as "What changed".
export function readerPrior(row) {
  if (!row) return null;
  return { letter_id: safe(row.letter_id), reporting_period: safe(row.reporting_period), letter_date: safe(row.letter_date) || null,
    title: safe(row.title), idea_type: safe(row.idea_type), activity: safe(row.activity), summary: safe(row.summary) };
}
export function readerWorkspaceIdea(row, prior = null) {
  return { ...readerSearchResult(row), first_mentioned: Boolean(row.first_mentioned), prior: readerPrior(prior) };
}
export function readerWorkspaceFund(row) {
  return { id: safe(row.id), name: safe(row.name), letters: Number(row.letter_count || 0), discussions: Number(row.discussions || 0),
    reporting_period: safe(row.reporting_period) || null, letter_date: safe(row.letter_date) || null };
}
export function readerOverlap(row) {
  return { ticker: safe(row.ticker).trim().toUpperCase(), funds: Number(row.fund_count || 0), letters: Number(row.letter_count || 0),
    long: Number(row.long_count || 0), short: Number(row.short_count || 0) };
}

export function sourceSections(text) {
  const chars = Array.from(text);
  const parts = [];
  let start = 0;
  while (start < chars.length) {
    let end = Math.min(start + 6000, chars.length);
    if (end < chars.length) {
      const piece = chars.slice(start, end).join("");
      const newline = piece.lastIndexOf("\n");
      if (newline >= 3000) end = start + Array.from(piece.slice(0, newline + 1)).length;
    }
    parts.push({ id: `s${parts.length + 1}`, text: chars.slice(start, end).join("") });
    start = end;
  }
  return parts;
}
const words = (text) => String(text || "").toLowerCase().match(/[\p{L}\p{N}_]+/gu) || [];
// A minus sign as letters print it, directly before a figure: "-3.8%", "‐ 3.8%", "-$40".
const MINUS_BEFORE = "[-\u2010\u2011\u2012\u2013\u2212]\\s?[$€£¥]?";
// Calendar years and labels such as QE2 are dates or names, not numerical
// claims; the historical_dates attestation covers those.
const numbers = text => (String(text || "").replace(/\b[A-Za-z]+[0-9]+\b/g, " ").match(/\d+(?:[,.]\d+)*(?:%|[xX])?/g) || [])
  .filter(number => !/^(?:19|20)\d{2}$/.test(number));
export function validateDraft(draft, parts) {
  const errors = [];
  if (typeof draft?.overview !== "string" || !draft.overview.trim() || !Array.isArray(draft.ideas) || !Array.isArray(draft.checklist)) return ["Overview, ideas and completeness checklist are required."];
  const ids = draft.ideas.map(i => i?.id);
  if (ids.some(id => typeof id !== "string" || !/^[a-zA-Z0-9_-]+$/.test(id)) || new Set(ids).size !== ids.length) errors.push("Idea IDs must be unique and alphanumeric.");
  const sections = new Map(parts.map(p => [p.id, p.text]));
  const covered = new Set();
  for (const idea of draft.ideas) {
    if (!idea?.title || typeof idea.summary !== "string" || !idea.summary.trim() || !IDEA_TYPES.has(idea.idea_type)) { errors.push("Every idea needs a title, type and full summary."); continue; }
    if (idea.evolution && !idea.compared_letter_id) errors.push("Evolution requires the earlier letter ID.");
    if (!Array.isArray(idea.evidence) || !idea.evidence.length) errors.push("Every idea needs private claim evidence.");
    let quotes = "";
    for (const evidence of idea.evidence || []) {
      const quote = String(evidence?.quote || "").replace(/\s+/g," ").trim();
      const passage = String(sections.get(evidence?.section_id) || "").replace(/\s+/g," ").trim();
      if (!evidence?.claim || !quote || !passage.includes(quote)) errors.push("Evidence must match the cited source passage exactly.");
      quotes += ` ${evidence?.quote || ""}`;
    }
    for (const n of numbers(idea.summary)) if (!quotes.includes(n)) errors.push(`Numerical claim ${n} lacks cited evidence.`);
    // Optional per-statement citations: one source section for each line of the summary,
    // and the idea must hold private evidence in that section.
    if (idea.cites !== undefined && idea.cites !== null) {
      const lines = idea.summary.split("\n").filter(line => line.trim());
      const held = new Set((idea.evidence || []).map(e => e?.section_id));
      if (!Array.isArray(idea.cites) || idea.cites.length !== lines.length || idea.cites.some(cite => !sections.has(cite) || !held.has(cite))) errors.push("Statement citations and evidence must match the summary line by line.");
    }
  }
  // Optional tables transcribed from the letter. Readers see each row label with every value under its
  // column heading; the quoted table text stays private. Every figure shown must be printed in that
  // quote, and a value shown with a minus must be printed with one.
  const tables = draft.tables || [];
  if (!Array.isArray(tables)) errors.push("Table evidence must match: tables is not a list.");
  const figureText = [], figureQuotes = [];
  const figuresIn = (text) => String(text || "").match(/\d+(?:[,.]\d+)*(?:%|[xX])?/g) || [];
  for (const table of Array.isArray(tables) ? tables : []) {
    const quote = String(table?.quote || "").replace(/\s+/g, " ").trim();
    const passage = String(sections.get(table?.section_id) || "").replace(/\s+/g, " ").trim();
    const title = typeof table?.title === "string" ? table.title : "";
    const columns = table?.columns, rows = table?.rows;
    const shaped = Array.isArray(columns) && columns.length >= 2 && columns.every(c => typeof c === "string" && c.trim())
      && Array.isArray(rows) && rows.length > 0 && rows.every(row => row && typeof row === "object" && typeof row.label === "string" && row.label.trim()
        && Array.isArray(row.values) && row.values.length === columns.length && row.values.every(v => typeof v === "string" && figuresIn(v).length));
    if (!shaped || !quote || !passage.includes(quote) || (table.idea_id !== null && table.idea_id !== undefined && !ids.includes(table.idea_id))) {
      errors.push("Table evidence must match its source passage exactly, with one value under every heading.");
      continue;
    }
    for (const row of rows) for (const value of row.values) for (const n of figuresIn(value)) {
      if (!quote.includes(n)) errors.push(`Table numerical claim ${n} lacks cited evidence.`);
      else if (value.trim().startsWith("-") && !new RegExp(MINUS_BEFORE + n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(quote)) errors.push(`Table numerical claim ${n} is shown as negative but is not printed so.`);
    }
    for (const n of numbers([title, ...columns, ...rows.map(row => row.label)].join(" "))) if (!quote.includes(n)) errors.push(`Table numerical claim ${n} lacks cited evidence.`);
    figureText.push([title, ...rows.map(row => [row.label, ...columns.map((column, i) => `${column} ${row.values[i]}`)].join(" "))].join(" "));
    figureQuotes.push(quote);
  }
  if (draft.coverage !== undefined && draft.coverage !== null && (typeof draft.coverage !== "object" || Array.isArray(draft.coverage) || Object.values(draft.coverage).some(v => !Number.isInteger(v) || v < 0))) errors.push("Coverage counts must be whole numbers.");
  const visited = [];
  for (const item of draft.checklist) {
    visited.push(item?.section_id);
    if (!item?.reason || !["covered", "non_substantive"].includes(item.disposition)) errors.push("Each passage needs a disposition and reason.");
    const targets = item?.idea_ids || [];
    if (!Array.isArray(targets) || targets.some(id => !ids.includes(id)) || (item.disposition === "covered" && !targets.length)) errors.push("Checklist must refer to existing ideas.");
    for (const id of targets) covered.add(id);
  }
  if (!parts.length || visited.length !== parts.length || new Set(visited).size !== parts.length || visited.some(id => !sections.has(id))) errors.push("Reconcile every source passage exactly once.");
  if (ids.some(id => !covered.has(id))) errors.push("Every idea must appear in the completeness checklist.");
  const stanceText = [draft.stance?.leaning_in, draft.stance?.leaning_out].flatMap(items => (Array.isArray(items) ? items : []).flatMap(i => [i?.subject, i?.why]));
  const stanceQuotes = [draft.stance?.leaning_in, draft.stance?.leaning_out].flatMap(items => (Array.isArray(items) ? items : []).flatMap(i => [i?.quote || "", ...(Array.isArray(i?.quotes) ? i.quotes : [])]));
  const sourceWords = words(parts.map(p => p.text).join(" "));
  const grams = new Set(sourceWords.slice(0, -11).map((_, i) => sourceWords.slice(i, i + 12).join(" ")));
  const prose = [draft.overview, ...draft.ideas.flatMap(i => [i?.title, i?.summary, i?.evolution, i?.activity]), ...stanceText, ...figureText].filter(Boolean).join(" ");
  const allQuotes = [...draft.ideas.flatMap(i => (i?.evidence || []).map(e => e?.quote || "")), ...stanceQuotes, ...figureQuotes].join(" ");
  for (const n of numbers(prose)) if (!allQuotes.includes(n)) errors.push(`Published numerical claim ${n} lacks cited evidence.`);
  if (safe(prose) !== prose || (draft.headline && safe(draft.headline) !== String(draft.headline))) errors.push("Reader prose contains a source link or private reference.");
  const tokens = words(prose);
  if (tokens.slice(0, -11).some((_, i) => grams.has(tokens.slice(i, i + 12).join(" ")))) errors.push("At least twelve consecutive source words copied; rewrite original prose.");
  return [...new Set(errors)];
}

export function pageArgs(params) {
  const offset = Number(params.get("offset") || 0);
  if (!Number.isSafeInteger(offset) || offset < 0) throw new TypeError("Invalid archive page.");
  return { offset, limit: Math.min(50, Math.max(1, Number.parseInt(params.get("limit") || "20", 10) || 20)) };
}

export function parseSearchTokens(rawQuery) {
  const out = {
    tickers: [],
    types: [],
    activities: [],
    focuses: [],
    periods: [],
    funds: [],
    signals: [],
    freeText: "",
  };
  const rest = [];
  const raw = String(rawQuery || "").trim();
  if (!raw) return out;
  for (const part of raw.split(/\s+/)) {
    const m = part.match(/^([a-zA-Z_]+):(.+)$/);
    if (!m) {
      rest.push(part);
      continue;
    }
    const key = m[1].toLowerCase();
    const val = m[2].trim();
    if (!val) continue;
    const list = val.split(",").map(s => s.trim()).filter(Boolean);
    if (key === "ticker" || key === "tickers" || key === "sym") {
      out.tickers.push(...list.map(s => s.toUpperCase()));
    } else if (key === "type" || key === "category") {
      out.types.push(...list.map(s => s.toLowerCase()));
    } else if (key === "action" || key === "activity") {
      out.activities.push(...list.map(s => s.toLowerCase()));
    } else if (key === "focus") {
      out.focuses.push(...list.map(s => s.toLowerCase()).filter(s => ["micro", "macro", "mixed"].includes(s)));
    } else if (key === "period" || key === "quarter" || key === "year") {
      out.periods.push(...list);
    } else if (key === "fund") {
      out.funds.push(...list.map(s => s.toLowerCase()));
    } else if (key === "is" || key === "signal" || key === "has") {
      for (const item of list.map(s => s.toLowerCase())) {
        if (item === "multi" || item === "multifund" || item === "consensus" || item === "overlap") out.signals.push("multi");
        else if (item === "battleground" || item === "contested" || item === "disputed") out.signals.push("battleground");
        else if (item === "evolution" || item === "changed") out.signals.push("evolution");
      }
    } else {
      rest.push(part);
    }
  }
  out.freeText = rest.join(" ").trim();
  return out;
}

function normalizeTickerList(rawTickers, tokenTickers = []) {
  const combined = [
    ...String(rawTickers || "").split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
    ...tokenTickers,
  ];
  return [...new Set(combined.filter(t => /^[A-Z0-9._-]{1,16}$/.test(t)))].slice(0, 300);
}

function appendPeriodAndDateFilters(params, tokenPeriods, clauses, args) {
  const periods = [
    ...(params.get("period") ? [params.get("period").trim()] : []),
    ...(tokenPeriods || []),
  ].filter(period => period && period.toLowerCase() !== "all");
  for (const period of periods) {
    if (/^\d{4}Q[1-4]$/i.test(period)) {
      clauses.push("UPPER(l.reporting_period)=?");
      args.push(period.toUpperCase());
    } else if (/^\d{4}$/.test(period)) {
      clauses.push("(l.reporting_period LIKE ? OR COALESCE(l.letter_date,l.publication_date,'') LIKE ?)");
      args.push(`${period}%`, `${period}%`);
    } else {
      throw new TypeError("Use a YYYY or YYYYQn period.");
    }
  }
  // Date filters use known dates, falling back to the reporting quarter for discovery only.
  const periodDate = "COALESCE(l.letter_date,l.publication_date,CASE WHEN l.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN substr(l.reporting_period,1,4)||CASE substr(l.reporting_period,6,1) WHEN '1' THEN '-01-01' WHEN '2' THEN '-04-01' WHEN '3' THEN '-07-01' ELSE '-10-01' END END)";
  for (const [key, comparison] of [["from", ">="], ["to", "<="]]) {
    if (params.get(key)) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(params.get(key))) throw new TypeError("Use an ISO date.");
      clauses.push(`${key === 'from' ? LETTER_SORT_SQL : periodDate}${comparison}?`);
      args.push(params.get(key));
    }
  }
}

export function searchWhere(params) {
  const clauses = ["l.published_revision IS NOT NULL"];
  const args = [];
  const parsed = parseSearchTokens(params.get("q") || "");

  if (params.get("fund")) {
    clauses.push("l.fund_id=?");
    args.push(params.get("fund"));
  }
  for (const fundToken of parsed.funds) {
    const match = `%${fundToken.replace(/[\\%_]/g, "\\$&")}%`;
    clauses.push("(LOWER(l.fund_id)=? OR LOWER(f.name) LIKE ? ESCAPE '\\')");
    args.push(fundToken, match);
  }

  const types = [
    ...String(params.get("type") || "").split(",").map(s => s.trim()).filter(Boolean),
    ...parsed.types,
  ];
  if (types.length === 1) {
    clauses.push("i.idea_type=?");
    args.push(types[0]);
  } else if (types.length > 1) {
    clauses.push(`i.idea_type IN (${types.map(() => "?").join(",")})`);
    args.push(...types);
  }

  const activities = [
    ...String(params.get("activity") || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
    ...parsed.activities,
  ];
  if (activities.length === 1) {
    clauses.push("LOWER(COALESCE(i.activity,''))=?");
    args.push(activities[0]);
  } else if (activities.length > 1) {
    clauses.push(`LOWER(COALESCE(i.activity,'')) IN (${activities.map(() => "?").join(",")})`);
    args.push(...activities);
  }

  const tickers = normalizeTickerList(params.get("tickers"), parsed.tickers);
  if (tickers.length === 1) {
    clauses.push("UPPER(TRIM(COALESCE(i.ticker,'')))=?");
    args.push(tickers[0]);
  } else if (tickers.length > 1) {
    clauses.push("UPPER(TRIM(COALESCE(i.ticker,''))) IN (SELECT value FROM json_each(?))");
    args.push(JSON.stringify(tickers));
  }

  const focuses = [
    ...String(params.get("focus") || "").split(",").map(s => s.trim().toLowerCase()).filter(s => ["micro", "macro", "mixed"].includes(s)),
    ...parsed.focuses,
  ];
  if (focuses.length) {
    clauses.push(`LOWER(COALESCE(json_extract(r.content_json,'$.stance.focus'),json_extract(r.content_json,'$.letter_focus'),'micro')) IN (${focuses.map(() => "?").join(",")})`);
    args.push(...focuses);
  }

  const signals = new Set([
    ...String(params.get("signal") || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
    ...parsed.signals,
  ]);
  if (signals.has("multi")) {
    clauses.push(`UPPER(TRIM(COALESCE(i.ticker,''))) IN (${MULTI_FUND_TICKERS_SQL})`);
  }
  if (signals.has("battleground")) {
    clauses.push(`UPPER(TRIM(COALESCE(i.ticker,''))) IN (${BATTLEGROUND_TICKERS_SQL})`);
  }
  if (signals.has("evolution")) {
    clauses.push("i.evolution IS NOT NULL AND TRIM(i.evolution)!=''");
  }

  if (parsed.freeText) {
    const match = `%${parsed.freeText.replace(/[\\%_]/g, "\\$&")}%`;
    clauses.push("(i.title LIKE ? ESCAPE '\\' OR i.ticker LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\' OR f.name LIKE ? ESCAPE '\\')");
    args.push(match, match, match, match);
  }
  appendPeriodAndDateFilters(params, parsed.periods, clauses, args);
  return { sql: clauses.join(" AND "), args };
}

export function letterWhere(params) {
  const clauses = ["l.published_revision IS NOT NULL"];
  const args = [];
  const parsed = parseSearchTokens(params.get("q") || "");

  if (params.get("fund")) {
    clauses.push("l.fund_id=?");
    args.push(params.get("fund"));
  }
  for (const fundToken of parsed.funds) {
    const match = `%${fundToken.replace(/[\\%_]/g, "\\$&")}%`;
    clauses.push("(LOWER(l.fund_id)=? OR LOWER(f.name) LIKE ? ESCAPE '\\')");
    args.push(fundToken, match);
  }
  if (params.get("letter")) {
    clauses.push("l.id=?");
    args.push(params.get("letter"));
  }

  const types = [
    ...String(params.get("type") || "").split(",").map(s => s.trim()).filter(Boolean),
    ...parsed.types,
  ];
  if (types.length) {
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND i.idea_type IN (${types.map(() => "?").join(",")}))`);
    args.push(...types);
  }

  const activities = [
    ...String(params.get("activity") || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
    ...parsed.activities,
  ];
  if (activities.length) {
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND LOWER(COALESCE(i.activity,'')) IN (${activities.map(() => "?").join(",")}))`);
    args.push(...activities);
  }

  const tickers = normalizeTickerList(params.get("tickers"), parsed.tickers);
  if (tickers.length) {
    clauses.push("EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND UPPER(TRIM(COALESCE(i.ticker,''))) IN (SELECT value FROM json_each(?)))");
    args.push(JSON.stringify(tickers));
  }
  const chips = workspaceScope(params, { only: ["ticker", "activity", "first", "book"] });
  if (chips.groups.length) {
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND ${chips.sql})`);
    args.push(...chips.args);
  }

  const focuses = [
    ...String(params.get("focus") || "").split(",").map(s => s.trim().toLowerCase()).filter(s => ["micro", "macro", "mixed"].includes(s)),
    ...parsed.focuses,
  ];
  if (focuses.length) {
    clauses.push(`LOWER(COALESCE(json_extract(r.content_json,'$.stance.focus'),json_extract(r.content_json,'$.letter_focus'),'micro')) IN (${focuses.map(() => "?").join(",")})`);
    args.push(...focuses);
  }

  const signals = new Set([
    ...String(params.get("signal") || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
    ...parsed.signals,
  ]);
  if (signals.has("multi")) {
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND UPPER(TRIM(COALESCE(i.ticker,''))) IN (${MULTI_FUND_TICKERS_SQL}))`);
  }
  if (signals.has("battleground")) {
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND UPPER(TRIM(COALESCE(i.ticker,''))) IN (${BATTLEGROUND_TICKERS_SQL}))`);
  }
  if (signals.has("evolution")) {
    clauses.push("EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND i.evolution IS NOT NULL AND TRIM(i.evolution)!='')");
  }

  if (parsed.freeText) {
    const match = `%${parsed.freeText.replace(/[\\%_]/g, "\\$&")}%`;
    clauses.push("(f.name LIKE ? ESCAPE '\\' OR f.manager LIKE ? ESCAPE '\\' OR COALESCE(l.reporting_period,'') LIKE ? ESCAPE '\\' OR r.overview LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND (i.title LIKE ? ESCAPE '\\' OR i.ticker LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\')))");
    args.push(match, match, match, match, match, match, match);
  }
  appendPeriodAndDateFilters(params, parsed.periods, clauses, args);
  return { sql: clauses.join(" AND "), args };
}

// One filter definition for the workspace fund list, idea feed, letter pane and overlap strip. Each filter is a
// labelled group in the order the reader applies it, so an empty result can name the group that emptied it.
export const QUARTER = /^\d{4}Q[1-4]$/;
export const FILTER_CHIPS = ["new", "add", "trim", "exit", "short", "first", "book"];
export const LONG_SQL = "(i.idea_type='long' OR LOWER(COALESCE(i.activity,'')) IN ('new','add'))";
export const SHORT_SQL = "(i.idea_type='short' OR LOWER(COALESCE(i.activity,''))='short')";
const ACTIVITY_CHIPS = {
  new: ["New position", "LOWER(COALESCE(i.activity,''))='new'"],
  add: ["Added", "LOWER(COALESCE(i.activity,''))='add'"],
  trim: ["Reduced", "LOWER(COALESCE(i.activity,''))='trim'"],
  exit: ["Exited", "LOWER(COALESCE(i.activity,'')) IN ('exit','cover')"],
  short: ["Short", SHORT_SQL],
};
// A company the fund has not named in any earlier quarter we hold. Without an earlier letter there is no
// history to compare against, so nothing in a fund's first archived letter counts as first mentioned.
export const FIRST_MENTIONED_SQL = `(${tickerKeySql("i")}!='' AND ${periodKeySql("l")}!=''
  AND EXISTS(SELECT 1 FROM fl_letters p WHERE p.fund_id=l.fund_id AND p.published_revision IS NOT NULL AND ${periodKeySql("p")}!='' AND ${periodKeySql("p")}<${periodKeySql("l")})
  AND NOT EXISTS(SELECT 1 FROM fl_letters p JOIN fl_ideas pi ON pi.letter_id=p.id AND pi.revision_id=p.published_revision
    WHERE p.fund_id=l.fund_id AND ${periodKeySql("p")}!='' AND ${periodKeySql("p")}<${periodKeySql("l")} AND ${tickerKeySql("pi")}=${tickerKeySql("i")}))`;

export function parseChips(raw) {
  return [...new Set(String(raw || "").split(",").map(s => s.trim().toLowerCase()).filter(chip => FILTER_CHIPS.includes(chip)))];
}

const FOCUS_SQL = "LOWER(COALESCE(json_extract(r.content_json,'$.stance.focus'),json_extract(r.content_json,'$.letter_focus'),'micro'))";
const likeArg = (text) => `%${text.replace(/[\\%_]/g, "\\$&")}%`;
const jsonList = (values) => JSON.stringify(values);

// Queries using the scope join fl_ideas i, fl_letters l (on the published revision), fl_funds f and fl_revisions r.
export function workspaceScope(params, { only = null } = {}) {
  const parsed = parseSearchTokens(params.get("q") || "");
  const groups = [];
  const group = (key, label, clauses, args = []) => {
    if ((!only || only.includes(key)) && clauses.length) groups.push({ key, label, sql: clauses.join(" AND "), args });
  };

  const periods = [String(params.get("period") || "").trim().toUpperCase(), ...parsed.periods.map(p => p.toUpperCase())].filter(p => p && p !== "ALL");
  const periodClauses = [], periodArgs = [];
  for (const period of periods) {
    if (QUARTER.test(period)) { periodClauses.push("l.reporting_period=?"); periodArgs.push(period); }
    else if (/^\d{4}$/.test(period)) { periodClauses.push("(l.reporting_period LIKE ? OR COALESCE(l.letter_date,l.publication_date,'') LIKE ?)"); periodArgs.push(`${period}%`, `${period}%`); }
    else throw new TypeError("Use a YYYY or YYYYQn period.");
  }
  group("period", periods.length === 1 ? `Quarter ${periods[0]}` : "Quarter", periodClauses, periodArgs);

  const search = [], searchArgs = [];
  for (const token of parsed.funds) { search.push("(LOWER(l.fund_id)=? OR LOWER(f.name) LIKE ? ESCAPE '\\')"); searchArgs.push(token, likeArg(token)); }
  const tokenTickers = normalizeTickerList("", parsed.tickers);
  if (tokenTickers.length) { search.push(`${tickerKeySql("i")} IN (SELECT value FROM json_each(?))`); searchArgs.push(jsonList(tokenTickers)); }
  if (parsed.types.length) { search.push("i.idea_type IN (SELECT value FROM json_each(?))"); searchArgs.push(jsonList(parsed.types)); }
  if (parsed.activities.length) { search.push("LOWER(COALESCE(i.activity,'')) IN (SELECT value FROM json_each(?))"); searchArgs.push(jsonList(parsed.activities)); }
  if (parsed.focuses.length) { search.push(`${FOCUS_SQL} IN (SELECT value FROM json_each(?))`); searchArgs.push(jsonList(parsed.focuses)); }
  if (parsed.signals.includes("multi")) search.push(`${tickerKeySql("i")} IN (${MULTI_FUND_TICKERS_SQL})`);
  if (parsed.signals.includes("battleground")) search.push(`${tickerKeySql("i")} IN (${BATTLEGROUND_TICKERS_SQL})`);
  if (parsed.signals.includes("evolution")) search.push("i.evolution IS NOT NULL AND TRIM(i.evolution)!=''");
  if (parsed.freeText) {
    const match = likeArg(parsed.freeText);
    search.push("(i.title LIKE ? ESCAPE '\\' OR i.ticker LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\' OR f.name LIKE ? ESCAPE '\\')");
    searchArgs.push(match, match, match, match);
  }
  group("search", `Search "${String(params.get("q") || "").trim()}"`, search, searchArgs);

  const fund = String(params.get("fund") || "").trim();
  if (fund) group("fund", "Selected fund", ["l.fund_id=?"], [fund]);
  const ticker = normalizeTickerList(params.get("ticker"))[0];
  if (ticker) group("ticker", `Company ${ticker}`, [`${tickerKeySql("i")}=?`], [ticker]);

  const chips = parseChips(params.get("f"));
  const activity = chips.filter(chip => ACTIVITY_CHIPS[chip]);
  if (activity.length) group("activity", `Position activity: ${activity.map(chip => ACTIVITY_CHIPS[chip][0]).join(" or ")}`, [`(${activity.map(chip => ACTIVITY_CHIPS[chip][1]).join(" OR ")})`]);
  if (chips.includes("first")) group("first", "First mentioned this quarter", [FIRST_MENTIONED_SQL]);
  if (chips.includes("book")) {
    const book = normalizeTickerList(params.get("book"));
    group("book", "Our book", book.length ? [`${tickerKeySql("i")} IN (SELECT value FROM json_each(?))`] : ["0"], book.length ? [jsonList(book)] : []);
  }

  const types = String(params.get("type") || "").split(",").map(s => s.trim().toLowerCase()).filter(type => IDEA_TYPES.has(type));
  if (types.length) group("type", "Category", ["i.idea_type IN (SELECT value FROM json_each(?))"], [jsonList(types)]);
  const focuses = String(params.get("focus") || "").split(",").map(s => s.trim().toLowerCase()).filter(s => ["micro", "macro", "mixed"].includes(s));
  if (focuses.length) group("focus", "Letter focus", [`${FOCUS_SQL} IN (SELECT value FROM json_each(?))`], [jsonList(focuses)]);

  // Holdings-table mentions are listed in the letter but are not discussions, unless asked for by category.
  const base = [...types, ...parsed.types].includes("factual_note") ? [] : ["i.idea_type!='factual_note'"];
  const pick = (keep = () => true) => {
    const chosen = groups.filter(keep);
    return { sql: [...base, ...chosen.map(g => g.sql)].join(" AND ") || "1", args: chosen.flatMap(g => g.args) };
  };
  return { groups, pick, ...pick() };
}
