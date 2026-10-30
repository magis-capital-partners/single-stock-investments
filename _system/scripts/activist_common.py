"""Shared utilities for activist report ingestion and indexing."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
PORTFOLIO_REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
US_TICKER_CONFIG = Path(__file__).resolve().parent / "us_ticker_config.json"
GLOBAL_SCAN_PATH = ROOT / "_system" / "data" / "activist_scan_latest.json"
SCAN_LOG_PATH = ROOT / "_system" / "data" / "activist_scan_log.json"
# EDGAR renamed the beneficial-ownership submission types when Schedules 13D/G
# moved to structured XML on 2024-12-18: data.sec.gov now reports "SCHEDULE 13D"
# where it used to report "SC 13D". Both spellings must pass the form filter —
# the filter runs on the raw EDGAR label, before normalization — and
# sec_filer_parse.normalize_form() collapses them to the canonical left-hand
# name for everything downstream.
FORM_ALIASES = {
    "SCHEDULE 13D": "SC 13D",
    "SCHEDULE 13D/A": "SC 13D/A",
    "SCHEDULE 13G": "SC 13G",
    "SCHEDULE 13G/A": "SC 13G/A",
    "SCHEDULE13D": "SC 13D",
    "SCHEDULE13G": "SC 13G",
}

ACTIVIST_FORMS = frozenset(
    {
        # Beneficial ownership (both the legacy and post-2024 EDGAR spellings)
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
        *FORM_ALIASES,
        # Contested proxy solicitations (management-side numbering)
        "DEFC14A",
        "PREC14A",
        "DFAN14A",
        # Non-management proxy statements — the dissident's own solicitation.
        # DEFC/PREC only cover contests the registrant files under; a dissident
        # running its own slate files DEFN14A/PREN14A and was invisible before.
        "DEFN14A",
        "PREN14A",
        # Notice of exempt solicitation (Rule 14a-6(g)) — the low-cost lever
        # activists and shareholder proponents use instead of a full contest.
        "PX14A6G",
        # The company's answer. Without it a campaign reads as a one-sided claim.
        "DEFA14A",
        # Hostile tender offer and the board's response. Rare per issuer.
        "SC TO-T",
        "SC TO-C",
        "SC 14D9",
        # Rule 14a-11 proxy access nominations. Rarer still.
        "SC 14N",
        "SC 14N-S",
    }
)

# Forms too voluminous to pull unconditionally. An 8-K names a campaign outcome
# only under Item 5.02, and every issuer files many for unrelated reasons, so
# these are fetched only for a ticker that already has a live campaign.
CONDITIONAL_FORMS = frozenset({"8-K"})
CONDITIONAL_FORM_CAP = 25

# Publisher / wire rows share the same body-verification + false-positive gates.
PUBLISHER_SOURCES = frozenset({"publisher_site", "local", "press_wire"})
OPEN_LETTER_CLASSES = frozenset(
    {"open_letter", "campaign_presentation", "press_campaign", "publisher_report"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default if default is not None else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_firm_registry() -> dict:
    return load_json(REGISTRY_PATH, {"firms": []})


def active_firms(*, side: str | None = None) -> list[dict]:
    firms = load_firm_registry().get("firms") or []
    out = [f for f in firms if f.get("active", True)]
    if side:
        out = [f for f in out if f.get("side") in (side, "both")]
    return out


def firm_ingest_methods(firm: dict | None) -> list[str]:
    """Return normalized ingest methods; supports legacy ingest_method string."""
    if not firm:
        return []
    methods = firm.get("ingest_methods")
    if isinstance(methods, list) and methods:
        return [str(m).strip() for m in methods if str(m).strip()]
    legacy = firm.get("ingest_method")
    if legacy:
        return [str(legacy).strip()]
    return []


def firm_has_ingest(firm: dict | None, method: str) -> bool:
    return method in firm_ingest_methods(firm)


def firms_for_ingest(method: str, *, side: str | None = None) -> list[dict]:
    out = [f for f in active_firms(side=side) if firm_has_ingest(f, method)]
    return out


def _boundary_pattern(term: str) -> re.Pattern[str]:
    """Compile a firm term so it only matches on word boundaries.

    Without \\b an alias like "amber" matches inside "chamber" and "tci" inside
    unrelated prose. Only anchor the side that starts/ends alphanumeric, so a
    term such as "3d investment partners" or "l.p." still matches.
    """
    body = re.escape(term)
    left = r"\b" if term[:1].isalnum() else ""
    right = r"\b" if term[-1:].isalnum() else ""
    return re.compile(f"{left}{body}{right}", re.I)


@lru_cache(maxsize=1)
def _firm_terms_cached(registry_stamp: tuple) -> tuple[tuple[str, str], ...]:
    """(firm_id, lowercase term) pairs, most specific term first."""
    terms_by_firm: list[tuple[str, str]] = []
    seen: set[str] = set()
    for firm in load_firm_registry().get("firms") or []:
        fid = firm.get("id") or ""
        terms = [firm.get("name", "")]
        terms.extend(firm.get("aliases") or [])
        terms.extend(firm.get("sec_filer_patterns") or [])
        for term in terms:
            key = str(term or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            terms_by_firm.append((fid, key))
    # Longest term first: a filing naming both "Engine Capital Management" and a
    # shorter generic alias should resolve to the most specific firm, not to
    # whichever happens to sit earlier in the registry file.
    terms_by_firm.sort(key=lambda pair: (-len(pair[1]), pair[0]))
    return tuple(terms_by_firm)


@lru_cache(maxsize=1)
def _firm_matchers_cached(registry_stamp: tuple) -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (fid, _boundary_pattern(term)) for fid, term in _firm_terms_cached(registry_stamp)
    )


@lru_cache(maxsize=1)
def _combined_firm_matcher(registry_stamp: tuple) -> tuple[re.Pattern[str], dict[str, str]]:
    """One alternation over every firm term, plus a term -> firm_id lookup.

    Scanning 325 separate patterns across a 250KB filing took ~2 seconds, and
    the pipeline calls this up to three times per filing — a full reindex of
    the 15.5k local filings would have taken about a day. The terms are literal
    strings, so a single alternation finds them all in one pass and the matched
    text maps straight back to its firm.
    """
    terms = _firm_terms_cached(registry_stamp)
    lookup = {term: fid for fid, term in terms}
    if not terms:
        # Never matches; keeps callers branch-free.
        return re.compile(r"(?!x)x"), lookup
    alternation = "|".join(
        f"{r'\b' if term[:1].isalnum() else ''}{re.escape(term)}"
        f"{r'\b' if term[-1:].isalnum() else ''}"
        for _fid, term in terms
    )
    return re.compile(alternation, re.I), lookup


def _registry_stamp() -> tuple:
    try:
        stat = REGISTRY_PATH.stat()
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


def firm_matchers() -> list[tuple[str, re.Pattern[str]]]:
    return list(_firm_matchers_cached(_registry_stamp()))


def match_firm_id(text: str) -> str | None:
    """Resolve text to a registry firm, preferring the most specific term found.

    One pass over the whole text collecting every term that appears, then the
    longest wins — so "Engine Capital Management" beats a shorter alias no
    matter where each sits in the document.
    """
    if not text:
        return None
    pattern, lookup = _combined_firm_matcher(_registry_stamp())
    best_term = ""
    best_fid = None
    for match in pattern.finditer(text):
        term = match.group(0).lower()
        if len(term) <= len(best_term):
            continue
        fid = lookup.get(term)
        if fid:
            best_term, best_fid = term, fid
    return best_fid


def portfolio_tickers() -> list[str]:
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holdings = reg.get("holdings") or {}
    if holdings:
        return sorted(holdings.keys())
    tickers = []
    skip = {"_system", "dashboard", ".git", ".github", ".cursor", "_external"}
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in skip and not p.name.startswith((".", "_")):
            tickers.append(p.name)
    return sorted(tickers)


GENERIC_COMPANY_TOKENS = frozenset(
    {
        "digital",
        "group",
        "holdings",
        "capital",
        "partners",
        "management",
        "investments",
        "inc",
        "corp",
        "corporation",
        "company",
        "companies",
        "international",
        "global",
        "services",
        "technologies",
        "technology",
        "resources",
        "energy",
        "financial",
        "trust",
        "fund",
        "limited",
        "ltd",
        "plc",
        "the",
        "and",
        # Industry words shared across many issuers — matching on these alone
        # produced false positives (e.g. Charter *Communications* <- Zoom
        # *Communications*, Dorchester *Minerals* <- Nova *Minerals*).
        "communications",
        "minerals",
        "mining",
        "metals",
        "uranium",
        "networks",
        "systems",
        "sciences",
        "pharmaceuticals",
        "pharma",
        "therapeutics",
        "semiconductor",
        "industries",
        "industrial",
        "materials",
        "properties",
        "realty",
        "royalty",
        "royalties",
        "petroleum",
        "exploration",
        "enterprises",
        "solutions",
        "brands",
        "labs",
        "media",
        "markets",
        "exchange",
        "bancorp",
        "bank",
        "insurance",
        "power",
        "electric",
        "motors",
        "airlines",
        "foods",
        "software",
        "platforms",
        # Ordinary English words that lead real issuer names. Each one put a
        # report about a different company into a holding's index: Spruce
        # Point's American Battery Metals report under AEP/AIG/AMT/AWK/AXP,
        # Healthcare Trust of America under BAC/GEHC/HCA, Hims & Hers *Health*
        # under CVS, e.l.f. *Beauty* under ULTA, LuxUrban *Hotels* under HST,
        # every bleeckerstreetresearch.com/*research*/ URL under LRCX, a
        # Grizzly post on *public* companies under PEG/PSA, Trian's General
        # Catalyst releases under GD/GIS/GM, Morgan *Stanley* under SWK.
        "american",
        "america",
        "general",
        "public",
        "health",
        "healthcare",
        "beauty",
        "hotels",
        "research",
        "storage",
        "service",
        "water",
        "works",
        "express",
        "tower",
        "stanley",
    }
)

# Leading issuer-name tokens that are dictionary words, place names or common
# personal names. Unlike GENERIC_COMPANY_TOKENS they are not industry nouns, but
# they are just as unsafe as single-token evidence: "Target", "Oracle",
# "Progressive" and "Southern" all occur in prose about other companies. They
# may still lead a two-word brand phrase ("morgan stanley", "general dynamics").
# There is no dictionary on the box, so this list is curated from the first
# tokens of the portfolio registry's company names (2026-10-12).
COMMON_ENGLISH_BRAND_TOKENS = frozenset(
    {
        "abacus", "advanced", "aerospace", "alphabet", "amazon", "analog", "apollo",
        "applied", "archer", "arthur", "associates", "automatic", "beaver", "booking",
        "boston", "brasil", "bristol", "builders", "bullish", "cadence", "cardinal",
        "caribbean", "carnival", "carrier", "castle", "cattle", "central", "charles",
        "charter", "church", "cincinnati", "circle", "citizens", "coherent", "comfort",
        "connectivity", "consensus", "consolidated", "constellation", "construction",
        "cooper", "credit", "deutsche", "diagnostics", "dollar", "dominion", "dynamics",
        "edison", "edwards", "electronic", "electronics", "emerson", "enterprise",
        "equity", "everest", "evolution", "evolve", "exchanges", "expand", "federal",
        "fidelity", "franklin", "freight", "galaxy", "garden", "generation", "genuine",
        "gladstone", "hanover", "hartford", "hawaiian", "heritage", "horizon", "hughes",
        "huntington", "illinois", "income", "indemnity", "indian", "indiana",
        "inflection", "instruments", "interactive", "intercontinental", "intuitive",
        "invitation", "jacobs", "johnson", "kinder", "laboratories", "lauren",
        "liberty", "london", "malaysia", "marathon", "martin", "mechanics", "mellon",
        "merger", "metallurgical", "monster", "morgan", "mosaic", "mountain", "nation",
        "national", "natural", "northern", "norwegian", "occidental", "offshore",
        "oncology", "oracle", "pacific", "packaging", "paramount", "parker",
        "payments", "pharmaceutical", "philip", "philippine", "phillips", "pinnacle",
        "polska", "prevail", "principal", "products", "progressive", "property",
        "prudential", "raymond", "regency", "regions", "republic", "reserve",
        "resorts", "robinson", "snowflake", "southern", "southwest", "stores",
        "street", "summit", "target", "travelers", "trinity", "triple", "united",
        "universal", "vertex", "vulcan", "warner", "warrior", "warsaw", "waters",
        "western", "williams", "willis", "worldwide",
    }
)

# Tickers that are English words. A bare token is never evidence for these —
# "Open Letter", "fast-growing", "One-Trick Pony", "slide deck" — even in
# upper case (PDF covers and card headings are often all caps). They need
# explicit notation: $OPEN, (OPEN), (Nasdaq: OPEN). Union of the 2026-10-12
# activist audit list and the 4+ letter words in letter_matching.COMMON_WORDS.
COMMON_WORD_TICKERS = frozenset(
    {
        "OPEN", "FAST", "PONY", "DECK", "PLUG", "REAL", "LOVE", "CASH", "SAFE", "BEST",
        "LIFE", "HOME", "PLAY", "WELL", "GOLD", "MAIN", "LAND", "ROAD", "SNAP", "CARE",
        "FORM", "TRUE", "EDIT", "BOOM", "NICE",
        "META", "SNOW", "GOOD", "CORE", "PEAK", "EDGE", "FLOW", "GROW", "HOPE", "PURE",
        "RISE", "STAR", "WAVE", "WISE", "WORK", "FUND", "GAIN", "RATE", "RISK", "TERM",
        "DATA", "TECH", "BANK", "DEBT", "COST", "SAGA", "ALSO", "PLUS",
        # Word tickers in the portfolio registry (2026-10-12).
        "BALL", "BULL", "CART", "COIN", "COLD", "DASH", "DELL", "ECHO", "ERIE",
        "FANG", "FLEX", "FLUX", "GILD", "GRAB", "HOOD", "KEEL", "KEYS", "LITE", "LULU",
        "ONTO", "OUST", "POET", "POST", "PURR", "RIOT", "SHOP", "SPOT", "VALE", "VELO",
        "WEST", "ZETA",
    }
)

LEGAL_ENTITY_SUFFIX_TOKENS = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "lp",
        "ltd",
        "plc",
    }
)


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _matches_company_phrase(text: str, company: str) -> bool:
    """Match a normalized full/core issuer name across URL punctuation and legal suffixes."""
    company_words = _normalized_words(company)
    if not company_words:
        return False
    if len(company_words) == 1 and is_weak_brand_token(company_words[0]):
        # A one-word registry name that is an ordinary word ("Target") is no
        # more specific than the word itself.
        return False
    words = _normalized_words(text)
    hay = f" {' '.join(words)} "
    phrases = [" ".join(company_words)]
    core_words = list(company_words)
    while core_words and core_words[-1] in LEGAL_ENTITY_SUFFIX_TOKENS:
        core_words.pop()
    if len(core_words) >= 2:
        phrases.append(" ".join(core_words))
    if any(f" {phrase} " in hay for phrase in phrases):
        return True
    # A one-word registry name written as two words: "Supermicro" vs
    # Hindenburg's "Super Micro Computer Inc.".
    if len(core_words) == 1 and len(core_words[0]) >= 8:
        target = core_words[0]
        return any(a + b == target for a, b in zip(words, words[1:]))
    return False


def is_weak_brand_token(token: str) -> bool:
    """True for a name token that is never sufficient evidence on its own."""
    token = (token or "").lower()
    return token in GENERIC_COMPANY_TOKENS or token in COMMON_ENGLISH_BRAND_TOKENS


_PHRASE_FILLER_TOKENS = frozenset({"the", "of", "and", "a", "an", "de", "du", "la", "le"})


def _company_has_name(meta: dict) -> bool:
    """False when the registry stores no real name: company == ticker ("OPEN", "PONY").

    Case-sensitive on purpose: "Uber" is a name, "UBER" would be the symbol.
    """
    company = (meta.get("company") or "").strip()
    ticker = (meta.get("ticker") or "").strip()
    if not company:
        return False
    return company not in {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}


def company_brand_phrase(company: str) -> str | None:
    """The issuer's first two significant name words as a normalized phrase.

    "American Electric Power" -> "american electric", "Lam Research" ->
    "lam research", "Host Hotels & Resorts" -> "host hotels", "Bank of
    America" -> "bank of america". None when the name has fewer than two
    significant words before its legal suffix, or the phrase is too short to
    be distinctive ("e.l.f." -> "e l").
    """
    words = _normalized_words(company)
    while words and words[0] == "the":
        words.pop(0)
    out: list[str] = []
    significant = 0
    for word in words:
        if word in LEGAL_ENTITY_SUFFIX_TOKENS:
            break
        out.append(word)
        if word not in _PHRASE_FILLER_TOKENS:
            significant += 1
        if significant == 2:
            break
    if significant < 2:
        return None
    phrase = " ".join(out)
    if len(phrase.replace(" ", "")) < 6:
        return None
    return phrase


def company_brand_token(company: str) -> str | None:
    """A single leading name token distinctive enough to stand alone.

    Only the FIRST significant word qualifies (the old rule skipped ahead to
    any 6+ letter word, which turned "M&F Bancorp Optus merger" into
    "merger"), and only when it is not an ordinary word: "costar",
    "solventum", "fastenal" qualify; "american", "target", "research" do not.
    """
    words = _normalized_words(company)
    while words and words[0] in _PHRASE_FILLER_TOKENS:
        words.pop(0)
    if not words:
        return None
    token = words[0]
    if len(token) < 6 or token in LEGAL_ENTITY_SUFFIX_TOKENS or is_weak_brand_token(token):
        return None
    return token


def _contains_phrase(text: str, phrase: str) -> bool:
    hay = f" {' '.join(_normalized_words(text))} "
    return f" {phrase} " in hay


_EXCHANGE_PREFIX = (
    r"(?i:nyse(?:\s+american|\s+arca|\s+mkt)?|nasdaq(?:gs|gm|cm)?|amex|"
    r"otc(?:qx|qb|mkts|\s+markets|\s+pink)?|tsxv?|cse|lse|asx|hkex|sgx)"
)


def _ticker_regex_body(ticker: str) -> str:
    """Escaped ticker, case-sensitive upper case for word tickers, else (?i:)."""
    escaped = re.escape(ticker.upper())
    if ticker.upper() in COMMON_WORD_TICKERS:
        return escaped
    return f"(?i:{escaped})"


def ticker_explicit_match(text: str, ticker: str) -> bool:
    """Ticker written in market notation: $OPEN, (Nasdaq: OPEN), symbol: OPEN, (OPEN).

    Case-insensitive for ordinary tickers; upper case only for COMMON_WORD_TICKERS,
    so "nasdaq - open to ..." prose cannot pass as notation. The bare
    parenthesised form "(LRCX)" is accepted only for 4+ character tickers: "(ED)",
    "(ICE)" and "(SEC)" are acronym definitions in ordinary prose.
    """
    if not text or not ticker:
        return False
    body = _ticker_regex_body(ticker)
    end = r"(?![A-Za-z0-9])"
    patterns = [
        rf"(?<![A-Za-z0-9])\${body}{end}",
        rf"\b{_EXCHANGE_PREFIX}\s*[:\-]\s*{body}{end}",
        rf"\b(?i:ticker|symbol)\s*[:\-]\s*{body}{end}",
    ]
    if len(re.sub(r"[^A-Za-z0-9]", "", ticker)) >= 4:
        patterns.append(rf"\(\s*{re.escape(ticker.upper())}\s*\)")
    return any(re.search(pattern, text) for pattern in patterns)


_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


def ticker_token_match(text: str, ticker: str) -> bool:
    """Bare ticker evidence: an UPPER-CASE token in the original text, or a URL path token.

    Lower-case prose never counts ("open", "fast-growing", "deck"), and word
    tickers (COMMON_WORD_TICKERS) never count bare at all — even all-caps
    headings say "OPEN LETTER". Tickers under 4 characters need notation.
    """
    if not text or not ticker:
        return False
    upper = ticker.upper()
    compact = re.sub(r"[.\-]", "", upper)
    if len(compact) < 4 or upper in COMMON_WORD_TICKERS or compact in COMMON_WORD_TICKERS:
        return False
    for candidate in {upper, compact}:
        if re.search(rf"(?<![A-Za-z0-9$]){re.escape(candidate)}(?![A-Za-z0-9])", text):
            return True
    # URL slugs are lower-cased by convention ("/research/smci-short/"); an
    # exact path token equal to the ticker is still a deliberate reference.
    lowered = {upper.lower(), compact.lower()}
    for url in _URL_RE.findall(text):
        path = _url_path(url)
        tokens = set(re.split(r"[^a-z0-9]+", path.lower()))
        if tokens & lowered:
            return True
    return False


def _url_path(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).path or ""
    except ValueError:
        return ""


def _distinctive_aliases(company: str, ticker: str) -> set[str]:
    aliases = {ticker.upper(), company}
    for token in re.split(r"[\s,./]+", company):
        token = token.strip()
        if len(token) >= 5 and token.lower() not in GENERIC_COMPANY_TOKENS:
            aliases.add(token)
    return aliases


@lru_cache(maxsize=4096)
def _ticker_meta_cached(ticker: str, registry_stamp: tuple) -> dict:
    return _build_ticker_meta(ticker)


def ticker_meta(ticker: str) -> dict:
    """Cached: this re-read and re-parsed two JSON files on every call, and
    the reindex calls it once per filing across 15k filings."""
    return _ticker_meta_cached(ticker.upper(), _registry_stamp())


def _cik_key(value: str | None) -> str:
    return str(value or "").strip().lstrip("0")


def subject_cik_matches_ticker(
    issuer_cik: str | None,
    ticker: str,
    *,
    external_cik_to_ticker: dict | None = None,
) -> bool:
    """True when the filing's subject CIK is this holding's registry CIK.

    The filer's CIK is not the subject. ``external_cik_to_ticker`` is accepted
    and ignored: SEC company_tickers lists the symbol SATS under Strive, Inc.,
    and the registry's SATS row is a different CIK. A ticker-to-CIK table must
    not place that filing on SATS.
    """
    _ = external_cik_to_ticker
    want = _cik_key(issuer_cik)
    have = _cik_key((ticker_meta(ticker) or {}).get("cik"))
    return bool(want and have and want == have)


def portfolio_ticker_for_subject_cik(
    issuer_cik: str | None,
    *,
    external_cik_to_ticker: dict | None = None,
) -> str | None:
    """Portfolio ticker for a subject issuer CIK, or None when we do not hold it.

    One registry CIK shared by two tickers (ECHO and SATS both carry EchoStar)
    is ambiguous and returns None. An external CIK-to-ticker map is not read.
    """
    _ = external_cik_to_ticker
    want = _cik_key(issuer_cik)
    if not want:
        return None
    hits = [
        ticker
        for ticker in portfolio_tickers()
        if _cik_key((ticker_meta(ticker) or {}).get("cik")) == want
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _build_ticker_meta(ticker: str) -> dict:
    ticker = ticker.upper()
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holding = (reg.get("holdings") or {}).get(ticker) or {}
    us_cfg = load_json(US_TICKER_CONFIG, {})
    download = holding.get("download") or {}
    cik = download.get("cik")
    if not cik:
        cik = (us_cfg.get(ticker) or {}).get("cik")
    company = holding.get("company") or ticker
    return {
        "ticker": ticker,
        "company": company,
        "cik": str(cik).strip() if cik else None,
        "aliases": sorted(_distinctive_aliases(company, ticker), key=len, reverse=True),
    }


CANONICAL_REPORTS_DIR = ROOT / "_system" / "reference" / "activist-reports"


def activist_reports_dir(ticker: str, side: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports" / side


def canonical_report_path(firm_id: str, dest_name: str) -> Path:
    return CANONICAL_REPORTS_DIR / firm_id / dest_name


def activist_index_path(ticker: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"


def load_ticker_index(ticker: str) -> dict:
    path = activist_index_path(ticker)
    data = load_json(path, {"ticker": ticker.upper(), "reports": []})
    data.setdefault("ticker", ticker.upper())
    data.setdefault("reports", [])
    return data


def save_ticker_index(ticker: str, index: dict) -> Path:
    path = activist_index_path(ticker)
    index["updated_at"] = now_iso()
    write_json(path, index)
    return path


# Rows from these sources are one document per URL. Keying them on the file
# name too meant a re-fetch under a new (fetch-dated) name was a new row.
URL_KEYED_SOURCES = frozenset({"publisher_site", "press_wire"})


def _normalized_source_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def report_key(entry: dict) -> str:
    if entry.get("source") in URL_KEYED_SOURCES and entry.get("source_url"):
        return "|".join(
            ["url", entry.get("firm_id") or "", _normalized_source_url(entry["source_url"])]
        )
    return "|".join(
        [
            entry.get("firm_id") or "",
            entry.get("report_date") or "",
            entry.get("source_url") or "",
            entry.get("canonical_file") or "",
            entry.get("local_pdf") or "",
            entry.get("local_file") or "",
            entry.get("accession") or "",
        ]
    )


def resolve_report_file(report: dict) -> tuple[str | None, bool, bool]:
    """Return (repo-relative path, is_pdf, exists on disk)."""
    candidates: list[tuple[str, bool]] = []
    if report.get("canonical_file"):
        ref = str(report["canonical_file"]).replace("\\", "/")
        candidates.append((ref, ref.lower().endswith(".pdf")))
    if report.get("local_pdf"):
        ref = str(report["local_pdf"]).replace("\\", "/")
        candidates.append((ref, True))
    if report.get("local_file"):
        ref = str(report["local_file"]).replace("\\", "/")
        candidates.append((ref, ref.lower().endswith(".pdf")))
    for ref, is_pdf in candidates:
        path = ROOT / ref
        if path.exists() and path.stat().st_size > 0:
            return ref, is_pdf, True
    if candidates:
        ref, is_pdf = candidates[0]
        return ref, is_pdf, False
    return None, False, False


def publisher_match_blob(report: dict) -> str:
    """Text used to match publisher/local/wire reports to a ticker (excludes repo paths).

    Including local_file makes every ``{TICKER}/third-party-analyses/...`` path
    match its folder ticker regardless of document content.
    """
    parts = [
        report.get("title") or "",
        report.get("source_url") or "",
        report.get("document_url") or "",
        report.get("firm_name") or "",
    ]
    return " ".join(p for p in parts if p)


NON_REPORT_SLUGS = frozenset(
    {
        "about",
        "authors",
        "careers",
        "contact",
        "items",
        "legal",
        "legal-disclaimer",
        "lostpassword",
        "news",
        "newsroom",
        "podcast",
        "privacy",
        "privacy-policy",
        "products",
        "publications",
        "research",
        "single-project",
        "social-media-disclaimer",
        "team",
        "terms",
        "terms-of-use",
    }
)


def classify_publisher_page(url: str, title: str = "") -> tuple[bool, str]:
    """Reject publisher navigation/policy pages before ticker matching."""
    from urllib.parse import urlparse

    parsed = urlparse(url or "")
    path = parsed.path.strip("/")
    slug = path.split("/")[-1].lower() if path else ""
    normalized_title = re.sub(r"\s+", " ", title or "").strip().lower()
    if not slug:
        return False, "publisher_homepage"
    if slug in NON_REPORT_SLUGS:
        return False, f"non_report_slug:{slug}"
    if any(
        phrase in normalized_title
        for phrase in (
            "legal disclaimer",
            "privacy policy",
            "social media disclaimer",
            "all rights reserved",
            "page not found",
        )
    ):
        return False, "non_report_title"
    return True, "report_candidate"


def publisher_match_allowed(url: str, title: str, blob: str, meta: dict) -> tuple[bool, float, str]:
    is_report, page_reason = classify_publisher_page(url, title)
    if not is_report:
        return False, 0.0, page_reason
    if url_target_mismatch(url, title, meta):
        return False, 0.0, "url_mismatch"
    matched, confidence, reason = match_report_to_ticker(blob, meta)
    if not matched or confidence < 0.9:
        return False, confidence, reason
    if reason.startswith("alias:"):
        return False, confidence, reason
    return True, confidence, reason


def prune_ghost_index_entries(ticker: str, *, dry_run: bool = False) -> int:
    """Drop index rows whose local file is missing and no publisher URL remains."""
    index = load_ticker_index(ticker)
    kept: list[dict] = []
    removed = 0
    meta = ticker_meta(ticker)
    for report in index.get("reports") or []:
        _ref, _is_pdf, exists = resolve_report_file(report)
        source_url = report.get("source_url")
        title = report.get("title") or ""
        url = source_url or report.get("local_file") or ""
        if not exists and not source_url:
            removed += 1
            continue
        if report.get("source") in PUBLISHER_SOURCES and url:
            if url_target_mismatch(url, title, meta) and not exists:
                removed += 1
                continue
        kept.append(report)
    if removed and not dry_run:
        index["reports"] = kept
        save_ticker_index(ticker, index)
    return removed


def upsert_report(index: dict, entry: dict) -> bool:
    key = report_key(entry)
    reports = index.setdefault("reports", [])
    local_file = entry.get("local_file")
    if local_file and entry.get("source") == "local":
        for i, existing in enumerate(reports):
            if existing.get("local_file") == local_file:
                merged = {**existing, **entry}
                if merged != existing:
                    reports[i] = merged
                    return True
                return False
    for i, existing in enumerate(reports):
        if report_key(existing) == key:
            if entry.get("source") in URL_KEYED_SOURCES:
                # A re-fetch that learned less (no date this time) must not
                # erase what an earlier run recorded.
                incoming = {k: v for k, v in entry.items() if v is not None or k not in existing}
            else:
                incoming = entry
            merged = {**existing, **incoming}
            if merged != existing:
                reports[i] = merged
                return True
            return False
    reports.append(entry)
    return True


def side_for_firm(firm_id: str, default: str = "long") -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("side") if firm.get("side") != "both" else default
    return default


def firm_name(firm_id: str) -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("name") or firm_id
    return firm_id


def match_report_to_ticker(text: str, meta: dict, *, min_confidence: float = 0.0) -> tuple[bool, float, str]:
    raw = text or ""
    hay = raw.lower()
    ticker = meta["ticker"].upper()
    # A registry row whose "company" is just the ticker (OPEN, PONY) has no
    # name to match; only ticker notation can place a report there.
    company = (meta.get("company") or "").lower() if _company_has_name(meta) else ""

    # Resolve the issuer name before ticker symbols.  Short symbols such as A,
    # T, ON, IT, ED, and MAR are ordinary prose/month tokens and are never
    # sufficient without explicit market notation.
    if company and len(company) >= 6 and _matches_company_phrase(hay, company):
        return True, 0.98, "company_name"

    # Brand evidence short of the full name: the first two significant name
    # words as a phrase ("lam research", "host hotels", "general dynamics"), or
    # a single leading token that is not an ordinary word ("costar" from
    # "CoStar Group"), so open letters titled "...Letter to CoStar Board"
    # survive publisher_match_allowed. A lone dictionary word ("american",
    # "research", "public") never does.
    if company:
        phrase = company_brand_phrase(company)
        if phrase and _contains_phrase(hay, phrase):
            return True, 0.95, "company_brand"
        token = company_brand_token(company)
        if token and re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", hay):
            return True, 0.95, "company_brand"

    if ticker_explicit_match(raw, ticker):
        return True, 0.99, "ticker_explicit"

    # Bare symbols are matched on the ORIGINAL text, upper case only; the old
    # case-insensitive \bopen\b put Viceroy's Abaxx report ("Open Interest")
    # under OPEN and its sibling ("fast-growing") under FAST.
    if ticker_token_match(raw, ticker):
        compact = re.sub(r"[.\-]", "", ticker)
        if compact != ticker and not re.search(
            rf"(?<![A-Za-z0-9$]){re.escape(ticker)}(?![A-Za-z0-9])", raw
        ):
            return True, 0.98, "ticker_compact"
        return True, 0.94, "ticker_symbol"

    for alias in meta.get("aliases") or []:
        alias_l = str(alias).strip().lower()
        if len(alias_l) < 6 or alias_l in GENERIC_COMPANY_TOKENS:
            continue
        if alias_l in hay:
            return True, 0.82, f"alias:{alias_l}"

    return False, 0.0, "no_match"


def text_matches_ticker(text: str, meta: dict) -> bool:
    matched, confidence, _reason = match_report_to_ticker(text, meta)
    return matched and confidence >= 0.9


_PAGE_EXTENSIONS_RE = re.compile(r"\.(?:pdf|html?|aspx?|php|jsp)$", re.I)


def _slug_tokens(url: str) -> set[str]:
    """Last URL path segment as tokens: extension dropped, digits-only tokens dropped.

    Two-letter tokens are kept: Bleecker Street's NextNav and LL Flooring
    reports live at /research/nn and /research/ll, and WD-40's at
    /research/wd-40. Dropping tokens under 3 characters left those slugs
    empty, and an empty slug was read as "no mismatch".
    """
    slug = _url_path(url).strip("/").split("/")[-1].lower()
    slug = _PAGE_EXTENSIONS_RE.sub("", slug)
    return {t for t in re.split(r"[^a-z0-9]+", slug) if len(t) >= 2 and not t.isdigit()}


def url_target_mismatch(url: str, title: str, meta: dict) -> bool:
    """True when URL/title clearly names a different company (site false-positive guard)."""
    raw_blob = f"{url} {title}"
    blob = raw_blob.lower()
    ticker = meta["ticker"].upper()
    company = (meta.get("company") or "").lower() if _company_has_name(meta) else ""
    # Same evidence rules as match_report_to_ticker: an upper-case or
    # notated ticker, the issuer's name, or its two-word brand phrase.
    if ticker_explicit_match(raw_blob, ticker) or ticker_token_match(raw_blob, ticker):
        return False
    if company and len(company) >= 6 and _matches_company_phrase(blob, company):
        return False
    phrase = company_brand_phrase(company) if company else None
    if phrase and _contains_phrase(blob, phrase):
        return False

    slug = _url_path(url or "").strip("/").split("/")[-1].lower()
    if not slug or re.fullmatch(r"[\d-]+", slug):
        return False
    slug_tokens = _slug_tokens(url or "")
    if not slug_tokens:
        return False
    ticker_token = re.sub(r"[.\-]", "", ticker).lower()
    ours: set[str] = set()
    if ticker not in COMMON_WORD_TICKERS:
        ours.add(ticker_token)
    if company:
        ours.update(
            t
            for t in _normalized_words(company)
            if len(t) >= 4 and t not in LEGAL_ENTITY_SUFFIX_TOKENS and not is_weak_brand_token(t)
        )
    # "QS1.pdf" is Scorpion's QuantumScape report: a symbol with a sequence
    # number still names the symbol.
    candidates = slug_tokens | {re.sub(r"\d+$", "", t) for t in slug_tokens}
    if candidates & ours:
        return False
    return True


def safe_report_filename(firm_id: str, report_date: str, suffix: str, ext: str = ".pdf") -> str:
    # No date means "undated", never today's date: a fetch-dated name changes
    # every run and duplicates the file and its index row.
    date_part = (report_date or "undated")[:10]
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", f"{firm_id}_{date_part}_{suffix}").strip("-")
    return f"{stem}{ext}"


def load_global_scan() -> dict:
    return load_json(GLOBAL_SCAN_PATH, {"reports": [], "generated_at": None})


def save_global_scan(payload: dict) -> None:
    write_json(GLOBAL_SCAN_PATH, payload)


def append_scan_log(entry: dict) -> None:
    log = load_json(SCAN_LOG_PATH, {"entries": []})
    log.setdefault("entries", []).append({**entry, "at": now_iso()})
    log["entries"] = log["entries"][-500:]
    write_json(SCAN_LOG_PATH, log)
