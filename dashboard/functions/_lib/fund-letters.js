export const EDITORIAL_CHECKS = ["complete_document", "idea_coverage", "claim_accuracy", "numerical_accuracy", "original_writing", "historical_dates"];
export const IDEA_TYPES = new Set(["long", "short", "update", "postmortem", "special_situation", "credit", "private", "unnamed", "sector", "macro", "portfolio", "factual_note"]);
// A period endpoint is an internal ordering fallback only, never a verified displayed date.
export const LETTER_SORT_SQL = "COALESCE(l.letter_date,l.publication_date,CASE WHEN l.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN substr(l.reporting_period,1,4)||CASE substr(l.reporting_period,6,1) WHEN '1' THEN '-03-31' WHEN '2' THEN '-06-30' WHEN '3' THEN '-09-30' ELSE '-12-31' END ELSE l.reporting_period END,'')";

// Deliberate field allowlists. Never spread database rows into reader responses.
const safe = (value) => {
  const text = String(value ?? "");
  return /https?:\/\/|drive\.google|_system[\\/]|[a-z]:[\\/]/i.test(text) ? "" : text;
};
export function readerIdea(row) {
  return { id: safe(row.id), title: safe(row.title), ticker: safe(row.ticker), idea_type: safe(row.idea_type),
    activity: safe(row.activity), summary: safe(row.summary), evolution: safe(row.evolution), compared_letter_id: safe(row.compared_letter_id) };
}
export function readerLetter(row, ideas) {
  return { id: safe(row.id), fund_id: safe(row.fund_id), fund: safe(row.fund), reporting_period: safe(row.reporting_period),
    letter_date: safe(row.letter_date) || null, publication_date: safe(row.publication_date) || null,
    summary_published_at: safe(row.published_at), summary_revised_at: safe(row.created_at),
    revision_id: safe(row.revision_id), overview: safe(row.overview), ideas: ideas.map(readerIdea) };
}
export function readerFund(row) {
  return { id: safe(row.id), name: safe(row.name), manager: safe(row.manager), strategy: safe(row.strategy), letter_count: Number(row.letter_count), latest: safe(row.latest) };
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
const numbers = text => String(text || "").match(/\d+(?:[,.]\d+)*(?:%|[xX])?/g) || [];
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
  const sourceWords = words(parts.map(p => p.text).join(" "));
  const grams = new Set(sourceWords.slice(0, -11).map((_, i) => sourceWords.slice(i, i + 12).join(" ")));
  const prose = [draft.overview, ...draft.ideas.flatMap(i => [i?.title, i?.summary, i?.evolution, i?.activity])].filter(Boolean).join(" ");
  const allQuotes = draft.ideas.flatMap(i => (i?.evidence || []).map(e => e?.quote || "")).join(" ");
  for (const n of numbers(prose)) if (!allQuotes.includes(n)) errors.push(`Published numerical claim ${n} lacks cited evidence.`);
  if (safe(prose) !== prose) errors.push("Reader prose contains a source link or private reference.");
  const tokens = words(prose);
  if (tokens.slice(0, -11).some((_, i) => grams.has(tokens.slice(i, i + 12).join(" ")))) errors.push("At least twelve consecutive source words copied; rewrite original prose.");
  return [...new Set(errors)];
}

export function pageArgs(params) {
  const offset = Number(params.get("offset") || 0);
  if (!Number.isSafeInteger(offset) || offset < 0) throw new TypeError("Invalid archive page.");
  return { offset, limit: Math.min(50, Math.max(1, Number.parseInt(params.get("limit") || "20", 10) || 20)) };
}

export function searchWhere(params) {
  const clauses = ["l.published_revision IS NOT NULL"];
  const args = [];
  for (const [key, column] of [["fund", "l.fund_id"], ["type", "i.idea_type"]]) {
    if (params.get(key)) { clauses.push(`${column}=?`); args.push(params.get(key)); }
  }
  const q = (params.get("q") || "").trim();
  if (q) {
    const match = `%${q.replace(/[\\%_]/g, "\\$&")}%`;
    clauses.push("(i.title LIKE ? ESCAPE '\\' OR i.ticker LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\' OR f.name LIKE ? ESCAPE '\\')");
    args.push(match, match, match, match);
  }
  // Date filters use known dates, falling back to the reporting quarter for discovery only.
  const periodDate = "COALESCE(l.letter_date,l.publication_date,CASE WHEN l.reporting_period GLOB '[0-9][0-9][0-9][0-9]Q[1-4]' THEN substr(l.reporting_period,1,4)||CASE substr(l.reporting_period,6,1) WHEN '1' THEN '-01-01' WHEN '2' THEN '-04-01' WHEN '3' THEN '-07-01' ELSE '-10-01' END END)";
  for (const [key, comparison] of [["from", ">="], ["to", "<="]]) {
    if (params.get(key)) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(params.get(key))) throw new TypeError("Use an ISO date.");
      clauses.push(`${key === 'from' ? LETTER_SORT_SQL : periodDate}${comparison}?`); args.push(params.get(key));
    }
  }
  return { sql: clauses.join(" AND "), args };
}
