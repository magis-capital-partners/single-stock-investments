export const EDITORIAL_CHECKS = ["complete_document", "idea_coverage", "claim_accuracy", "numerical_accuracy", "original_writing", "historical_dates"];
export const IDEA_TYPES = new Set(["long", "short", "update", "postmortem", "special_situation", "credit", "private", "unnamed", "sector", "macro", "portfolio", "factual_note"]);
// A period endpoint is an internal ordering fallback only, never a verified displayed date.
export const LETTER_SORT_SQL = "COALESCE(l.letter_date,l.publication_date,CASE WHEN l.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN substr(l.reporting_period,1,4)||CASE substr(l.reporting_period,6,1) WHEN '1' THEN '-03-31' WHEN '2' THEN '-06-30' WHEN '3' THEN '-09-30' ELSE '-12-31' END ELSE l.reporting_period END,'')";

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
export function readerIdea(row) {
  return { id: safe(row.id), title: safe(row.title), ticker: safe(row.ticker), idea_type: safe(row.idea_type),
    activity: safe(row.activity), summary: safe(row.summary), evolution: safe(row.evolution), compared_letter_id: safe(row.compared_letter_id) };
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
export function readerLetter(row, ideas, stance = null, headline = null) {
  const focus = safe(stance?.focus || row?.focus);
  return { id: safe(row.id), fund_id: safe(row.fund_id), fund: safe(row.fund), reporting_period: safe(row.reporting_period),
    letter_date: safe(row.letter_date) || null, publication_date: safe(row.publication_date) || null,
    summary_published_at: safe(row.published_at), summary_revised_at: safe(row.created_at),
    revision_id: safe(row.revision_id), headline: safe(headline ?? row.headline) || null,
    focus: ["micro", "macro", "mixed"].includes(focus) ? focus : null,
    overview: safe(row.overview), stance: readerStance(stance), ideas: ideas.map(readerIdea) };
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
export function readerArchiveEntry(row) {
  return { id: safe(row.id), reporting_period: safe(row.reporting_period), letter_date: safe(row.letter_date) || null };
}
export function readerSearchResult(row) {
  return { ...readerIdea(row), fund_id: safe(row.fund_id), fund: safe(row.fund), letter_id: safe(row.letter_id), reporting_period: safe(row.reporting_period), letter_date: safe(row.letter_date) || null };
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
  }
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
  const prose = [draft.overview, ...draft.ideas.flatMap(i => [i?.title, i?.summary, i?.evolution, i?.activity]), ...stanceText].filter(Boolean).join(" ");
  const allQuotes = [...draft.ideas.flatMap(i => (i?.evidence || []).map(e => e?.quote || "")), ...stanceQuotes].join(" ");
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
  ].filter(Boolean);
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
    clauses.push(`UPPER(TRIM(COALESCE(i.ticker,''))) IN (${tickers.map(() => "?").join(",")})`);
    args.push(...tickers);
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
    clauses.push(`EXISTS(SELECT 1 FROM fl_ideas i WHERE i.letter_id=l.id AND i.revision_id=l.published_revision AND UPPER(TRIM(COALESCE(i.ticker,''))) IN (${tickers.map(() => "?").join(",")}))`);
    args.push(...tickers);
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
