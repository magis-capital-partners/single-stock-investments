#!/usr/bin/env python3
"""Resolve the ticker text on fund-letter ideas to securities, and tag themes.

An idea's ticker field holds whatever symbols the summarizer kept from the
letter. Counting those strings directly counts finance acronyms (FCF, ROIC),
common words (ALL, KEY) and tickers that a different company uses today (EP was
El Paso in 2012 and is Empire Petroleum now). So each symbol becomes an entity
only on evidence:

* the security master's company name agrees with the idea, or
* the letter prints the symbol as a ticker ($X, NYSE: X, "Company (X)",
  "(5019 JP)") and the security master does not name a different company.

Finance acronyms are dropped unless the security master's company for them is
the one the idea discusses, or the master has no usable name and the letter
prints them with an exchange. Everything else without evidence is kept as
unresolved: shown on the idea, never counted.

The security master and portfolio files are read only. Nothing here changes
the identity inputs of the company-research snapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import letter_matching as lm  # noqa: E402
from ticker_identity import exchange_token_family, nearby_company_phrase, ticker_market_family  # noqa: E402

MASTER_PATH = ROOT / "_system/reference/securities/security_master.json"
COMPOUNDERS_PATH = ROOT / "_system/reference/core_compounders.json"
REGISTRY_PATH = ROOT / "_system/portfolio/registry.json"
SCHEMA = ROOT / "dashboard/cloudflare/migrations/0026_fund_letter_entities.sql"

# Raise when the rules below change; a new value re-resolves every published idea.
RULES = "entities-2"

ACRONYMS = frozenset(
    lm.SYNTACTIC_STOPWORDS | lm.HARVEST_BLOCKLIST | lm.ROLE_COLLISION_CODES | lm.NON_SECURITY_CODES
    | lm.BENCHMARK_CODES | lm.COUNTRY_CODES
    | {
        "ABS", "ADR", "ADS", "AR", "AP", "BV", "BVPS", "CDO", "CDS", "CLO", "CMBS", "CMO", "CRO", "DSO",
        "ECB", "EM", "DM", "FOMC", "FY", "GP", "HY", "IG", "IP", "IR", "IT", "LBO", "LNG", "LTV", "MBS",
        "MMBTU", "NII", "NIM", "OCF", "OPEC", "OPEX", "PEG", "PM", "PPE", "RMBS", "ROTE", "SBC", "SG",
        "SPAC", "TBV", "TIPS", "TTM", "VC", "WTI", "YOY",
    }
)

# Bloomberg exchange codes, as letters write them after a symbol ("5019 JP", "VOD LN").
BLOOMBERG = {
    "US": "", "UN": "", "UW": "", "UQ": "", "UA": "", "UR": "", "UV": "",
    "LN": ".L", "JP": ".T", "JT": ".T", "HK": ".HK", "CN": ".TO", "CT": ".TO", "AU": ".AX", "AT": ".AX",
    "GR": ".DE", "GY": ".DE", "FP": ".PA", "NA": ".AS", "IM": ".MI", "SM": ".MC", "SS": ".ST",
    "SW": ".SW", "VX": ".SW", "NO": ".OL", "DC": ".CO", "FH": ".HE", "BB": ".BR", "SP": ".SI",
    "KS": ".KS", "TT": ".TW", "IN": ".NS", "IB": ".NS", "BZ": ".SA", "MM": ".MX", "CH": ".SZ",
}
# "VIE.FP" is Bloomberg's code joined by a dot. HK, SW, KS, SS, CN and AT are also exchange suffixes
# in their own right (SS is Shanghai there, Stockholm here), so a dot before them is left alone.
DOTTED_BLOOMBERG = frozenset(BLOOMBERG) - {"HK", "SW", "KS", "SS", "CN", "AT"}
SUFFIX_FAMILY = {".TW": "TW", ".KS": "KR", ".SZ": "CN", ".SS": "CN", ".SA": "BR", ".MX": "MX", ".SI": "SG"}
STRONG = {"dollar", "paren_exch", "exch_prefix", "paren_num_exch"}
GENERIC = frozenset(lm.COMMON_WORDS | lm._SINGLE_TOKEN_STOP | {
    "and", "china", "american", "america", "national", "energy", "resources", "systems", "technology",
    "technologies", "industries", "services", "solutions", "pharmaceuticals", "pharmaceutical", "stock",
    "insurance", "bank", "banks", "entertainment", "communications", "products", "brands", "media",
    "petroleum", "oil", "gas", "mining", "minerals", "properties", "realty", "investment", "investments",
    "first", "united", "general", "new", "north", "south", "east", "west", "pacific", "atlantic", "co",
    "etf", "fund", "spdr", "ishares", "index", "performance", "management", "health", "healthcare",
})

THEMES = {"quality": "Quality compounders", "ma": "M&A compounders"}
# Said of the company itself: "a high-quality business", not "we buy high-quality companies".
THEME_TEXT = {
    "quality": re.compile(r"\bcompounder\b|\bcompounding machine|\bwide[- ]moat|\ban? (?:\w+ )?(?:high|exceptional|superior)[- ]quality (?:business|company|franchise)\b", re.I),
    "ma": re.compile(r"\bserial acquir\w*|\broll[- ]?ups?\b|\bacquisition (?:strategy|engine|machine|playbook|platform)|\bbolt[- ]on acquisitions?\b|\bprogrammatic (?:M&A|acquisitions?)|\bM&A (?:strategy|engine|playbook|machine|compounder)", re.I),
}
# Company-level discussions; macro, portfolio and holdings-table notes never carry a theme.
THEMED_TYPES = {"long", "short", "update", "credit", "special_situation", "private", "postmortem"}
# Without a resolved company, only a direct position discussion can carry a theme from its wording.
TEXT_THEME_TYPES = {"long", "short", "special_situation", "private"}


def digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=1)
def master() -> lm.SecurityMaster:
    return lm.SecurityMaster.from_dict(json.loads(MASTER_PATH.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def resolver_version() -> str:
    return f"{RULES}:{digest(MASTER_PATH.read_bytes().decode('utf-8'))}"


# Names a 2011 letter uses for companies the security master knows by a later name.
FORMER_NAMES = {"GOOG": "google", "GOOGL": "google", "META": "facebook", "BKNG": "priceline", "ELV": "wellpoint"}


def stem(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") else word


def words(text: str) -> set[str]:
    return {stem(w) for w in re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’]", "", (text or "").lower())).split()}


def name_tokens(name: str, symbol: str) -> list[str]:
    """Distinctive words of a company name; empty when the master only knows the symbol."""
    tokens = lm._norm_name(re.sub(r"['’]", "", name)).split()
    return [t for t in tokens if len(t) >= 3 and t not in GENERIC and t != symbol.lower().split(".")[0]]


def names_company(name: str, symbol: str, text: str) -> bool | None:
    """True when the text names the company, False when it does not, None when the
    security master has no usable name for the symbol."""
    base = symbol.split(".", 1)[0]
    if FORMER_NAMES.get(symbol) in words(text):
        return True
    tokens = name_tokens(name, symbol)
    if not tokens:
        core = [t for t in lm._norm_name(name).split() if t not in GENERIC]
        plain = " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())
        if core == [base.lower()] and plain != base.lower() and not lm.is_word_collision(base):
            # "CIT Group", "HCA Healthcare": the symbol is the name.
            return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(base) + r"(?![A-Za-z0-9])", text, 0 if len(base) < 4 else re.I))
        whole = lm._norm_name(name)
        if whole and whole != base.lower() and len(whole.split()) >= 2:
            return whole in " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
        return None
    present = words(text)
    tokens = [stem(t) for t in tokens]
    return any(t in present for t in tokens if len(t) >= 5) or all(t in present for t in tokens)


def split_mentions(raw: str) -> list[str]:
    """Symbols in an idea's ticker field. "TW, LN" is one Bloomberg symbol, not two."""
    parts = [p.strip() for p in re.split(r"[,;/]|\band\b", raw or "") if p.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and part.upper() in BLOOMBERG and " " not in merged[-1]:
            merged[-1] = f"{merged[-1]} {part.upper()}"
        else:
            merged.append(part)
    return merged


def normalize(mention: str) -> tuple[str, str | None, str | None]:
    """(symbol, exchange token, exchange suffix) for one mention; symbol '' when it is not one."""
    text = re.sub(r"\s+(?:equity|eq)$", "", mention.strip(), flags=re.I).strip(" ()$")
    match = lm.EXCH_PREFIX_TICKER_RE.fullmatch(text) or re.fullmatch(rf"(?P<exch>{lm.EXCHANGE_NAMES})\s*[:\s]\s*(?P<sym>[A-Za-z0-9.\-]+)", text, re.I)
    if match:
        exch = re.match(rf"{lm.EXCHANGE_NAMES}", text, re.I).group(0)
        return match.groups()[-1].upper(), exch, None
    match = re.fullmatch(r"([A-Za-z0-9.\-]{1,12})\s*[: ]\s*([A-Za-z]{2})", text) or re.fullmatch(r"([A-Za-z0-9\-]{1,12})\.([A-Za-z]{2})", text)
    if match and match.group(2).upper() in (BLOOMBERG if " " in text or ":" in text else DOTTED_BLOOMBERG):
        symbol, code = match.group(1).upper(), match.group(2).upper()
        suffix = BLOOMBERG[code]
        if suffix == ".HK" and symbol.isdigit():
            symbol = symbol.zfill(4)
        return symbol + suffix, None, suffix or "US"
    symbol = text.upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,11}", symbol):
        return "", None, None
    return symbol, None, None


def letter_evidence(source: str) -> dict[str, list[dict]]:
    hits: dict[str, list[dict]] = {}
    for hit in lm.extract_explicit_symbols(source or ""):
        hits.setdefault(hit["symbol"].upper(), []).append(hit)
    return hits


def printed(symbol: str, evidence: dict[str, list[dict]], source: str) -> tuple[bool, bool, str | None, int | None]:
    """(strong, parenthetical, exchange token, position) for the letter's own ticker syntax."""
    base = symbol.split(".", 1)[0]
    keys = {symbol, base, base.lstrip("0") or base}
    strong = paren = False
    exchange = position = None
    for key in keys:
        for hit in evidence.get(key, []):
            if hit["rule"] in STRONG or (hit["rule"] == "dotted" and key == symbol):
                strong = True
                exchange = exchange or hit.get("exchange")
                position = hit["span"][0] if position is None else position
            elif hit["rule"] == "paren_company" and lm.parenthetical_is_ticker(source, hit["span"][0], key, 1):
                paren = True
                position = hit["span"][0] if position is None else position
    if not (strong or paren) and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", symbol):
        # "Venoco (VQ, $10.78, ...)": the symbol opens a parenthetical after the name.
        for match in re.finditer(r"\(\s*" + re.escape(symbol) + r"\s*[,;]", source or ""):
            if re.search(r"[A-Z][a-zA-Z&.]+\s*$", source[max(0, match.start() - 40):match.start()]) and lm.parenthetical_is_ticker(source, match.start(), symbol, 1):
                paren, position = True, match.start()
                break
    return strong, paren, exchange, position


TITLE_STOPWORDS = frozenset({"the", "a", "an", "short", "long", "new", "exit", "exited", "sold", "bought", "added", "trimmed", "position", "update", "thesis", "investment", "on", "in", "of"})


def fuller_label(label: str, title: str) -> str:
    """Extracted PDF text breaks names apart ("Gr een Mountain Coffee Roasters"), and the phrase before a ticker
    stops at a digit ("Level 3"), so a label can be a name's tail. The idea's title usually prints the whole name."""
    at = title.lower().find(label.lower()) if label else -1
    prefix = title[:at].split() if at > 0 else []
    if prefix and len(prefix) <= 4 and all(re.fullmatch(r"[A-Z0-9][A-Za-z0-9&.'\-]*", w) and w.lower() not in TITLE_STOPWORDS for w in prefix):
        return title[: at + len(label)].strip()
    return label


def resolve_mention(mention: str, idea_text: str, source: str, evidence: dict | None = None) -> dict:
    sm = master()
    evidence = letter_evidence(source) if evidence is None else evidence
    symbol, exch_token, bloomberg = normalize(mention)
    row = {"mention": mention.strip()[:80], "ticker": None, "exchange": None, "name": None}
    if not symbol:
        return {**row, "status": "unresolved", "reason": "not_a_symbol"}
    base = symbol.split(".", 1)[0]
    acronym = base in lm.SYNTACTIC_STOPWORDS or base in ACRONYMS
    ticker = sm.resolve_symbol(symbol, exch_token)
    if not ticker and re.fullmatch(r"[A-Z]{1,5}\.[A-Z]", symbol):
        ticker = next((t for t in (f"{base}.{c}" for c in "ABCDK") if t in sm.by_ticker), None)
    strong, paren, token, position = printed(symbol, evidence, source)
    verbatim = re.search(r"(?<![A-Za-z0-9])" + re.escape(mention.strip()) + r"(?![A-Za-z0-9])", source or "") if bloomberg else None
    if verbatim:
        strong = True
        position = verbatim.start() if position is None else position
    nearby = nearby_company_phrase(source, position) if position is not None else ""
    # Shown only as a label, so "Ltd" or "Inc" alone is no name at all.
    label = nearby if any(len(w) >= 4 and w not in GENERIC for w in words(nearby)) else ""
    label = fuller_label(label, (idea_text or "").split("\n", 1)[0])
    word = lm.is_word_collision(symbol)
    if ticker:
        meta = sm.by_ticker[ticker]
        named = names_company(str(meta.get("name") or ""), ticker, f"{idea_text} {nearby or ''}")
        family = ticker_market_family(ticker, exchange=str(meta.get("exchange") or "") or None)
        name = str(meta.get("name") or "")
        resolved = {**row, "ticker": ticker, "exchange": family, "name": (label if name.upper() in {ticker, base} else name)[:120] or None}
        if named:
            return {**resolved, "status": "resolved", "reason": "name"}
        if named is None and (strong or (paren and not acronym and not word and not sm.collision(ticker))):
            return {**resolved, "status": "resolved", "reason": "printed"}
        if acronym:
            return {**row, "status": "dropped", "reason": "acronym"}
        return {**row, "status": "unresolved", "reason": "different_company" if named is False and (strong or paren) else "unverified"}
    if acronym:
        return {**row, "status": "dropped", "reason": "acronym"}
    if symbol.split(".", 1)[0].isdigit() or word:
        ticker_syntax = strong
    else:
        ticker_syntax = (strong or paren) and lm.plausible_harvest_symbol(symbol)
    if ticker_syntax:
        suffix = "." + symbol.rsplit(".", 1)[1] if "." in symbol else ""
        family = exchange_token_family(token) or SUFFIX_FAMILY.get(suffix) or ticker_market_family(symbol)
        return {**row, "ticker": symbol, "exchange": family, "name": label[:120] or None, "status": "resolved", "reason": "printed"}
    return {**row, "status": "unresolved", "reason": "unknown"}


def resolve_idea(ticker_text: str, idea_text: str, source: str, evidence: dict | None = None) -> list[dict]:
    evidence = letter_evidence(source) if evidence is None else evidence
    rows, seen = [], set()
    for mention in split_mentions(ticker_text):
        row = resolve_mention(mention, idea_text, source, evidence)
        key = row["ticker"] or row["mention"].upper()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def keep_symbol(symbol: str, idea_text: str, source: str) -> bool:
    """False for a finance acronym the resolver would drop; the summarizer keeps the rest."""
    return resolve_mention(symbol, idea_text, source)["status"] != "dropped"


@lru_cache(maxsize=1)
def theme_tickers() -> dict[str, frozenset[str]]:
    compounders = json.loads(COMPOUNDERS_PATH.read_text(encoding="utf-8")) if COMPOUNDERS_PATH.is_file() else {}
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8")) if REGISTRY_PATH.is_file() else {}
    quality = {str(t).upper() for t in compounders.get("tickers") or []}
    acquirers = {str(t).upper() for t, row in (compounders.get("issuers") or {}).items() if (row or {}).get("watchlist_group") == "acquirers"}
    serial_path = COMPOUNDERS_PATH.with_name('serial_acquirers.json')
    if serial_path.is_file():
        serial = json.loads(serial_path.read_text(encoding='utf-8'))
        acquirers.update(row['ticker'].upper() for row in serial.get('companies') or [])
    for bucket in ("holdings", "watchlist"):
        for ticker, row in (registry.get(bucket) or {}).items():
            archetype = ((row or {}).get("classification") or {}).get("archetype") if isinstance((row or {}).get("classification"), dict) else (row or {}).get("archetype")
            if archetype == "compounder":
                quality.add(str(ticker).upper())
            if archetype == "serial_acquirer":
                acquirers.add(str(ticker).upper())
    return {"quality": frozenset(quality), "ma": frozenset(acquirers)}


def idea_themes(idea_type: str, idea_text: str, tickers: list[str]) -> list[str]:
    if idea_type not in THEMED_TYPES:
        return []
    lists = theme_tickers()
    worded = bool(tickers) or idea_type in TEXT_THEME_TYPES
    return [theme for theme in THEMES if set(tickers) & lists[theme] or (worded and THEME_TEXT[theme].search(idea_text or ""))]


@lru_cache(maxsize=1)
def theme_version() -> str:
    lists = {k: sorted(v) for k, v in theme_tickers().items()}
    patterns = {k: v.pattern for k, v in THEME_TEXT.items()}
    return f"{RULES}:{digest(json.dumps(lists), json.dumps(patterns), json.dumps(sorted(THEMED_TYPES)), resolver_version())}"


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    # Local bookkeeping only: which published revisions the current rules have read.
    db.execute("CREATE TABLE IF NOT EXISTS fl_entity_runs (resolver TEXT NOT NULL, revision_id TEXT NOT NULL, PRIMARY KEY(resolver, revision_id))")


def refresh(db: sqlite3.Connection) -> dict:
    """Resolve every published idea not yet resolved under the current rules and master."""
    ensure_schema(db)
    resolver, themes = resolver_version(), theme_version()
    pending = db.execute(
        """SELECT DISTINCT l.id letter_id, l.published_revision revision_id FROM fl_letters l
           JOIN fl_ideas i ON i.letter_id=l.id AND i.revision_id=l.published_revision
           WHERE l.published_revision IS NOT NULL
             AND NOT EXISTS(SELECT 1 FROM fl_entity_runs r WHERE r.resolver=? AND r.revision_id=l.published_revision)""",
        (themes,),
    ).fetchall()
    counts = {"revisions": 0, "resolved": 0, "unresolved": 0, "dropped": 0, "themed": 0}
    for letter_id, revision_id in pending:
        source = (db.execute("SELECT source_text FROM fl_letters WHERE id=?", (letter_id,)).fetchone() or [""])[0] or ""
        evidence = letter_evidence(source)
        ideas = db.execute("SELECT id,title,ticker,idea_type,summary FROM fl_ideas WHERE revision_id=? ORDER BY ordinal", (revision_id,)).fetchall()
        for idea_id, title, ticker_text, idea_type, summary in ideas:
            text = f"{title or ''}\n{summary or ''}"
            rows = resolve_idea(ticker_text or "", text, source, evidence) if (ticker_text or "").strip() else []
            for ordinal, row in enumerate(rows):
                db.execute(
                    "INSERT OR IGNORE INTO fl_idea_entities(resolver,revision_id,idea_id,ordinal,mention,ticker,exchange,name,status,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (resolver, revision_id, idea_id, ordinal, row["mention"], row["ticker"], row["exchange"], row["name"], row["status"], row["reason"]),
                )
                counts[row["status"]] += 1
            resolved = [row["ticker"] for row in rows if row["status"] == "resolved"]
            for theme in idea_themes(idea_type or "", text, resolved):
                db.execute("INSERT OR IGNORE INTO fl_idea_themes(theme_set,revision_id,idea_id,theme) VALUES(?,?,?,?)", (themes, revision_id, idea_id, theme))
                counts["themed"] += 1
        db.execute("INSERT OR IGNORE INTO fl_entity_runs(resolver,revision_id) VALUES(?,?)", (themes, revision_id))
        counts["revisions"] += 1
    for key, value in (("entity_resolver", resolver), ("idea_themes", themes)):
        db.execute("INSERT INTO fl_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()
    return {"resolver": resolver, "theme_set": themes, **counts}


def release_statements(db: sqlite3.Connection, quote) -> list[str]:
    """Entity and theme rows for published revisions, then the pointers that make them current.

    Rows are keyed by rule version, so an accepted row never needs replacing and the
    sync ledger sends each one once. The pointers move last, after every row is in."""
    refresh(db)
    resolver, themes = resolver_version(), theme_version()
    sql = []
    for row in db.execute(
        """SELECT e.resolver,e.revision_id,e.idea_id,e.ordinal,e.mention,e.ticker,e.exchange,e.name,e.status,e.reason
           FROM fl_idea_entities e JOIN fl_letters l ON l.published_revision=e.revision_id
           WHERE e.resolver=? AND e.status!='dropped' ORDER BY e.revision_id,e.idea_id,e.ordinal""", (resolver,)):
        sql.append("INSERT OR IGNORE INTO fl_idea_entities (resolver,revision_id,idea_id,ordinal,mention,ticker,exchange,name,status,reason) VALUES ("
                   + ",".join(quote(v) for v in tuple(row)) + ");")
    for row in db.execute(
        """SELECT t.theme_set,t.revision_id,t.idea_id,t.theme FROM fl_idea_themes t JOIN fl_letters l ON l.published_revision=t.revision_id
           WHERE t.theme_set=? ORDER BY t.revision_id,t.idea_id,t.theme""", (themes,)):
        sql.append("INSERT OR IGNORE INTO fl_idea_themes (theme_set,revision_id,idea_id,theme) VALUES (" + ",".join(quote(v) for v in tuple(row)) + ");")
    for key, value in (("entity_resolver", resolver), ("idea_themes", themes)):
        sql.append(f"INSERT OR IGNORE INTO fl_settings (key,value) VALUES ({quote(key)},'');")
        sql.append(f"UPDATE fl_settings SET value={quote(value)} WHERE key={quote(key)} AND value!={quote(value)};")
    return sql


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=ROOT / "_private/fund_letters/archive.sqlite")
    parser.add_argument("--report", action="store_true", help="Print unresolved and dropped mentions for review")
    args = parser.parse_args()
    db = sqlite3.connect(args.db)
    print(json.dumps(refresh(db)))
    if args.report:
        for row in db.execute("SELECT status,reason,mention,COUNT(*) FROM fl_idea_entities WHERE resolver=? AND status!='resolved' GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 80", (resolver_version(),)):
            print("\t".join(str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
