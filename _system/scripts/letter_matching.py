#!/usr/bin/env python3
"""Evidence-tiered letter -> ticker matching.

Shared by build_superinvestor_insights.py (full pipeline),
build_security_master.py (Tier-A symbol harvest), and
calibrate_letter_matching.py (precision/recall harness).

Confidence tiers
----------------
- Tier A (high): explicit ticker syntax. ``$AAPL``, ``(NASDAQ: AAPL)``,
  ``NASDAQ: AAPL``, ``(AAPL)`` next to a capitalized company word, or a
  numeric exchange ticker with explicit exchange context (``HKEX: 388``,
  ``(3905 JP)``). Numeric bases are valid ONLY in Tier A.
- Tier B (medium): verified company name. The full multi-word company name
  (>= 2 significant tokens) matched case-sensitively, OR a distinctive single
  token, appearing >= 2 times OR inside a position/holdings context.
- Tier C (weak, excluded from consensus): a single bare-symbol word or a
  single one-word alias mention; word-collision tickers that only matched as a
  lowercase word.

Only Tier A and Tier B mentions are emitted by default; Tier C is retained but
flagged so recall can be inspected without polluting consensus counts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Exchange vocabulary + explicit-syntax regexes (Tier A)
# ---------------------------------------------------------------------------
EXCHANGE_NAMES = (
    r"NASDAQ|NYSE|NYSE\s*ARCA|ARCA|AMEX|TSX|TSXV|CSE|OTCQX|OTCQB|OTC|LSE|AIM|ASX|"
    r"HKEX|SEHK|HK|TSE|JPX|JP|SGX|B3|BMV|GPW|FWB|XETRA|EURONEXT|EPA|BIT|MIL|STO|OMX|"
    r"KLSE|KRX|NSE|BSE|TWSE|SET|IDX|BVMF|BCBA"
)
_EXCH_RE = re.compile(rf"\b(?:{EXCHANGE_NAMES})\b", re.I)

# $TICKER
DOLLAR_TICKER_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9.\-]{0,11})\b")
# (EXCH: TICKER) or (EXCH:TICKER) with optional "Exchange"
PAREN_EXCH_TICKER_RE = re.compile(
    rf"\(\s*(?:{EXCHANGE_NAMES})(?:\s*Exchange)?\s*[:\s]\s*([A-Za-z0-9][A-Za-z0-9.\-]{{0,11}})\s*\)",
    re.I,
)
# EXCH: TICKER (bare, not in parens)
EXCH_PREFIX_TICKER_RE = re.compile(
    rf"\b(?:{EXCHANGE_NAMES})(?:\s*Exchange)?\s*:\s*([A-Za-z0-9][A-Za-z0-9.\-]{{0,11}})\b",
    re.I,
)
# (TICKER) bare parenthetical — only trusted next to a capitalized company word
PAREN_BARE_RE = re.compile(r"\(\s*([A-Z][A-Z0-9.\-]{0,11})\s*\)")
# (388 HK) / (3905 JP) style — number then exchange inside parens
PAREN_NUM_EXCH_RE = re.compile(
    rf"\(\s*([0-9]{{2,6}})\s*[:\s]\s*(?:{EXCHANGE_NAMES})\s*\)",
    re.I,
)
# Dotted exchange ticker e.g. 0388.HK, 3905.T, ALS.TO
DOTTED_TICKER_RE = re.compile(r"\b([A-Z0-9]{1,6}\.[A-Z]{1,3})\b")

# Action / position language
ACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("new", re.compile(r"\b(initiated|new position|established|started a position|opened)\b", re.I)),
    ("add", re.compile(r"\b(added|increased|accumulat\w*|bought more|topped up|built up)\b", re.I)),
    ("trim", re.compile(r"\b(trimmed|reduced|pared|lightened|sold down|took profits)\b", re.I)),
    ("exit", re.compile(r"\b(exited|eliminated|closed|sold out|fully sold|divested)\b", re.I)),
    ("short", re.compile(r"\b(short(?:ed|ing)?|put position|bearish bet)\b", re.I)),
    ("buy", re.compile(r"\b(purchased|bought|acquired)\b", re.I)),
]
HOLDINGS_HEADING_RE = re.compile(
    r"\b(top (?:ten |10 |five |5 )?(?:holdings|positions)|portfolio holdings|"
    r"largest (?:holdings|positions)|position(?:s)? summary|holdings? as of|"
    r"top contributors|portfolio composition)\b",
    re.I,
)
TABLE_CHANGE_TOKEN_RE = re.compile(
    r"\b(new|added|add|increased|buy|trimmed|trim|reduced|sold|exit|closed|hold|unchanged|short)\b",
    re.I,
)
TABLE_ROW_TICKER_RE = re.compile(
    r"(?:\(([A-Z][A-Z0-9.\-]{0,11})\)|\$([A-Z][A-Z0-9.\-]{0,11})|"
    r"\b([A-Z0-9]{1,6}\.[A-Z]{1,3})\b|"
    r"\b([A-Z][A-Z0-9.\-]{1,5})\b)",
)
TABLE_CHANGE_MAP = {
    "new": "new",
    "added": "add",
    "add": "add",
    "increased": "add",
    "buy": "add",
    "trimmed": "trim",
    "trim": "trim",
    "reduced": "trim",
    "sold": "exit",
    "exit": "exit",
    "closed": "exit",
    "hold": "hold",
    "unchanged": "hold",
    "short": "short",
}
CONVICTION_HIGH_RE = re.compile(
    r"\b(high(?:est)? conviction|largest position|top position|core (?:holding|position)|"
    r"significant position|concentrated)\b",
    re.I,
)

# Compact common-word set for ticker collision detection (short English words /
# units that frequently appear as bare tokens in prose). Used to flag tickers
# that must rely on Tier A explicit syntax.
COMMON_WORDS: frozenset[str] = frozenset(
    w.lower()
    for w in (
        "ALL", "AND", "ANY", "ARE", "ARM", "ART", "BIG", "BIT", "BUY", "CAN", "CAP",
        "CAR", "CEO", "CFO", "DAY", "EAT", "END", "EPS", "EVR", "FAR", "FED", "FEW",
        "FIT", "FOR", "FUN", "GET", "GOT", "HAS", "HE", "HIT", "HOT", "HOW", "ICE",
        "ITS", "JOB", "KEY", "LAB", "LAND", "LAW", "LB", "LBS", "LET", "LOW", "MAN",
        "MAP", "MAX", "MAY", "MEN", "META", "MID", "NET", "NEW", "NOT", "NOW", "OAK",
        "OFF", "OIL", "OLD", "ON", "ONE", "OR", "OUR", "OUT", "OWN", "PAY", "PER",
        "PSE", "PUT", "RAW", "RED", "RUN", "SAW", "SEA", "SET", "SIT", "SIX", "SKY",
        "SNOW", "SO", "SUN", "TAX", "TEN", "THE", "TIP", "TOP", "TRY", "TWO", "USE",
        "VS", "WAR", "WAS", "WAY", "WIN", "WON", "YES", "YET", "YOU", "REAL", "GOOD",
        "BEST", "MAIN", "CORE", "PEAK", "EDGE", "FLOW", "GROW", "HOPE", "LIFE", "LOVE",
        "OPEN", "PLAY", "PURE", "RISE", "SAFE", "STAR", "TRUE", "WAVE", "WISE", "WELL",
        "WORK", "FUND", "GAIN", "RATE", "RISK", "TERM", "DATA", "TECH", "BANK", "GOLD",
        "CASH", "DEBT", "COST", "SAGA", "ALSO", "PLUS", "FORM",
    )
)


def is_word_collision(ticker: str) -> bool:
    """A purely-alphabetic short ticker that collides with a common word."""
    base = ticker.split(".", 1)[0].replace("-", "")
    return base.isalpha() and base.lower() in COMMON_WORDS


# Single-token company names that collide with exchanges/benchmarks/generic
# finance nouns cited in nearly every letter. These must never match on the
# bare token (e.g. "Nasdaq" the benchmark vs NDAQ the company).
_SINGLE_TOKEN_STOP: frozenset[str] = frozenset(
    {
        "nasdaq", "euronext", "exchange", "exchanges", "index", "group", "capital",
        "partners", "holdings", "global", "international", "financial", "markets",
        "fund", "trust", "company", "corporation", "growth", "value", "income",
        "russell", "treasury", "benchmark", "beyond", "focus", "summit", "vista",
        "peak", "edge", "select", "advantage", "frontier",
    }
)


# ---------------------------------------------------------------------------
# Security master access
# ---------------------------------------------------------------------------
@dataclass
class SecurityMaster:
    """Lookup tables + precompiled combined regexes from security_master.json."""

    by_ticker: dict[str, dict]
    symbol_to_ticker: dict[str, str] = field(default_factory=dict)
    numeric_to_ticker: dict[str, str] = field(default_factory=dict)
    name_alias_to_ticker: dict[str, str] = field(default_factory=dict)
    single_token_to_ticker: dict[str, str] = field(default_factory=dict)
    # combined regexes compiled once for speed (one finditer per letter)
    bare_symbol_re: re.Pattern[str] | None = None
    bare_symbol_map: dict[str, str] = field(default_factory=dict)
    name_re: re.Pattern[str] | None = None
    single_token_re: re.Pattern[str] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityMaster":
        by_ticker = {str(k).upper(): dict(v or {}) for k, v in (data or {}).items()}
        symbol_to_ticker: dict[str, str] = {}
        numeric_to_ticker: dict[str, str] = {}
        name_alias_counts: dict[str, set[str]] = {}
        single_token_counts: dict[str, set[str]] = {}
        bare_symbols: dict[str, str] = {}

        for ticker, meta in by_ticker.items():
            symbol = ticker.split(".", 1)[0]
            symbol_to_ticker.setdefault(symbol.upper(), ticker)
            symbol_to_ticker.setdefault(ticker.upper(), ticker)
            num = meta.get("numeric_base")
            if num:
                numeric_to_ticker.setdefault(str(num), ticker)
            if symbol.isdigit():
                numeric_to_ticker.setdefault(symbol.lstrip("0") or symbol, ticker)
                numeric_to_ticker.setdefault(symbol, ticker)
            # bare uppercase symbol: alpha, len>=3, non-collision only
            collision = bool(meta["is_word_collision"]) if "is_word_collision" in meta else is_word_collision(ticker)
            if symbol.isalpha() and len(symbol) >= 3 and not collision:
                bare_symbols.setdefault(symbol.upper(), ticker)
            # Only trusted names feed the name/alias matchers. Harvested company
            # names are unreliable (DIS->"Software", CRM->"AgentForce") and would
            # match the generic word everywhere, so harvested securities match
            # by explicit symbol only.
            trusted = bool(meta.get("in_book")) or meta.get("source") in ("book", "manual")
            names = set(meta.get("aliases") or [])  # curated aliases always trusted
            if trusted and meta.get("name"):
                names.add(meta["name"])
            for name in names:
                norm = _norm_name(name)
                if not norm:
                    continue
                tokens = norm.split()
                if len(tokens) >= 2:
                    name_alias_counts.setdefault(norm, set()).add(ticker)
                elif (
                    len(tokens) == 1
                    and len(tokens[0]) >= 5
                    and tokens[0] not in COMMON_WORDS
                    and tokens[0] not in _SINGLE_TOKEN_STOP
                ):
                    single_token_counts.setdefault(tokens[0], set()).add(ticker)

        name_alias_to_ticker = {a: next(iter(t)) for a, t in name_alias_counts.items() if len(t) == 1}
        single_token_to_ticker = {a: next(iter(t)) for a, t in single_token_counts.items() if len(t) == 1}

        # combined bare-symbol regex (case-sensitive, longest first)
        bare_symbol_re = None
        if bare_symbols:
            alt = "|".join(re.escape(s) for s in sorted(bare_symbols, key=len, reverse=True))
            bare_symbol_re = re.compile(rf"(?<![A-Za-z0-9.])(?:{alt})(?![A-Za-z0-9.])")

        # combined name regex (case-insensitive, longest first); map back via normalization
        name_re = None
        if name_alias_to_ticker:
            parts = []
            for norm in sorted(name_alias_to_ticker, key=len, reverse=True):
                toks = norm.split()
                parts.append(r"[\s\-]+".join(re.escape(t) for t in toks))
            name_re = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])", re.I)

        single_token_re = None
        if single_token_to_ticker:
            alt = "|".join(re.escape(t) for t in sorted(single_token_to_ticker, key=len, reverse=True))
            single_token_re = re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])", re.I)

        return cls(
            by_ticker=by_ticker,
            symbol_to_ticker=symbol_to_ticker,
            numeric_to_ticker=numeric_to_ticker,
            name_alias_to_ticker=name_alias_to_ticker,
            single_token_to_ticker=single_token_to_ticker,
            bare_symbol_re=bare_symbol_re,
            bare_symbol_map=bare_symbols,
            name_re=name_re,
            single_token_re=single_token_re,
        )

    def resolve_symbol(self, sym: str) -> str | None:
        if not sym:
            return None
        s = sym.strip().upper().replace("-", ".")
        if s in self.by_ticker:
            return s
        bare = s.split(".", 1)[0]
        return self.symbol_to_ticker.get(s) or self.symbol_to_ticker.get(bare)

    def resolve_numeric(self, num: str) -> str | None:
        n = str(num).strip()
        return self.numeric_to_ticker.get(n) or self.numeric_to_ticker.get(n.lstrip("0") or n)

    def in_book(self, ticker: str) -> bool:
        return bool(self.by_ticker.get(ticker, {}).get("in_book"))

    def collision(self, ticker: str) -> bool:
        meta = self.by_ticker.get(ticker, {})
        if "is_word_collision" in meta:
            return bool(meta["is_word_collision"])
        return is_word_collision(ticker)


def _norm_name(name: str) -> str:
    clean = re.sub(r"\([^)]*\)", " ", name or "")
    clean = clean.replace("&", " and ")
    clean = re.sub(r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|lp|llc|"
                   r"holdings?|group|trust|class|ordinary|common|shares|sa|nv|ag|ab|berhad|the)\b\.?",
                   " ", clean, flags=re.I)
    clean = re.sub(r"[^A-Za-z0-9 ]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return clean


# ---------------------------------------------------------------------------
# Tier A: explicit symbol extraction (also used by the harvester)
# ---------------------------------------------------------------------------
NON_TICKER_DOTTED = {"U.S", "U.K", "E.U", "B.A", "M.A", "A.M", "P.M", "D.C", "Q.E", "P.E"}
SYNTACTIC_STOPWORDS = {
    "PDF", "USD", "EPS", "CEO", "CFO", "USA", "ETF", "IPO", "AUM", "FCF", "EBIT",
    "EBITDA", "ROIC", "NAV", "CAGR", "YTD", "GAAP", "SEC", "IRS", "LTM", "NTM",
    "TAM", "GDP", "CPI", "PCE", "FED", "NYSE", "NASDAQ", "REIT", "ESG", "WACC",
    "DCF", "IRR", "ROI", "ROE", "ROA", "COGS", "CAPEX", "AFFO", "FFO", "NOI",
    "IFRS", "SOFR", "LIBOR", "EMEA", "APAC", "LATAM", "Q1", "Q2", "Q3", "Q4",
}


def _looks_symbol(sym: str) -> bool:
    s = sym.upper()
    if s in SYNTACTIC_STOPWORDS or s in NON_TICKER_DOTTED:
        return False
    if not re.match(r"^[A-Z0-9](?:[A-Z0-9.\-]{0,11})?$", s):
        return False
    return True


# Finance acronyms / benchmark tickers / prose words that get written in
# parentheses like a ticker but are NOT companies. Used to keep the harvester
# from minting junk securities (the biggest universe-expansion FP source).
HARVEST_BLOCKLIST: frozenset[str] = frozenset(
    {
        # finance acronyms
        "MTM", "AIV", "NAV", "MOIC", "TSR", "BPS", "YOY", "QOQ", "MOM", "WACC",
        "DCF", "IRR", "MOIC", "EBIT", "EBITDA", "ROIC", "ROE", "ROA", "ROI",
        "FCF", "AFFO", "FFO", "NOI", "CAGR", "YTD", "NTM", "LTM", "TAM", "SAM",
        "GDP", "CPI", "PCE", "PPI", "AUM", "GAV", "GMV", "ARR", "MRR", "ARPU",
        "EV", "PE", "PB", "PS", "FX", "QE", "QT", "ZIRP", "DPI", "RVPI",
        # benchmark / index tickers
        "SPX", "RUT", "RUJ", "RUO", "RUI", "RUA", "NDX", "DJIA", "VIX", "XBI",
        "IBB", "SPY", "QQQ", "IWM", "VTI", "ACWI", "EFA", "EEM", "TLT", "HYG",
        "AGG", "GSPC",
        # prose words that masquerade as tickers in (X) form
        "BILLION", "MILLION", "TRILLION", "DRIVEN", "INDEX", "FIRST", "SECOND",
        "THIRD", "RETURN", "RETURNS", "ALPHA", "BETA", "VALUE", "GROWTH", "YIELD",
        "TOTAL", "GROSS", "NET", "REAL", "AI", "ESG", "USD", "EUR", "GBP", "JPY",
        "CNY", "HKD", "CAD", "AUD", "CHF", "SPTR", "MXWO", "MXEF", "NKY", "SX5E",
        "UKX", "CCMP", "INDU",
        # professional credentials / titles written like "Name, CFA"
        "CFA", "CPA", "CAIA", "CMT", "FRM", "MBA", "PHD", "CTO", "COO", "CIO",
        "SVP", "EVP", "JD", "MD", "ESQ",
    }
)


COUNTRY_CODES: frozenset[str] = frozenset(
    {"US", "UK", "EU", "JP", "CN", "HK", "DE", "FR", "CA", "AU", "CH", "NL", "SE",
     "IT", "ES", "IN", "KR", "TW", "BR", "MX", "SG", "NO", "DK", "FI", "IE", "PT",
     "AT", "BE", "PL", "ZA", "NZ", "RU", "SA", "AE", "IL", "TH", "ID", "MY", "PH",
     "USA", "UAE"}
)
_BENCHMARK_WORDS = re.compile(
    r"\b(index|benchmark|average|composite|world|eafe|acwi|ratio|aggregate|treasury|"
    r"sharpe|sofr|libor|barclays|bloomberg|russell|nasdaq|\d{3,4})\b",
    re.I,
)

# Index / benchmark / rate tickers that masquerade as companies in return tables.
# Excluded from harvest and emission unless the ticker is actually in our book.
BENCHMARK_CODES: frozenset[str] = frozenset(
    {
        "MSCI", "MEAA", "EDOF", "RFR", "MXWO", "MXEF", "MXWD", "M1WD", "MXAP",
        "SPX", "SPTR", "NDX", "CCMP", "RTY", "RUT", "RUI", "RUA", "RUJ", "RUO",
        "INDU", "DJIA", "SX5E", "SXXP", "UKX", "NKY", "TPX", "HSI", "DAX", "CAC",
        "VIX", "TNX", "GSPC", "GDDUWI", "NDDUWI", "HFR", "HFRI", "BBgAgg",
    }
)


def is_benchmark(ticker: str) -> bool:
    return ticker.split(".", 1)[0].upper() in BENCHMARK_CODES


def parenthetical_is_ticker(text: str, span_start: int, symbol: str, min_words: int) -> bool:
    """True when ``Company Name (TICKER)`` is a genuine ticker parenthetical and
    not a prose acronym definition, a country tag, or a benchmark index.

    Only the *contiguous* run of capitalized words immediately before the paren
    is treated as the company name, so an unrelated earlier word in the sentence
    (e.g. "SOFR futures, Kyndryl Holdings (KD)") does not poison the decision.
    """
    if symbol.upper() in COUNTRY_CODES:
        return False
    pre = re.sub(r"\s+", " ", text[max(0, span_start - 70):span_start]).rstrip()
    m = re.search(r"((?:[A-Z][A-Za-z0-9&.\-]*\s+){0,4}[A-Z][A-Za-z0-9&.\-]*)\s*$", pre)
    if not m:
        return False
    phrase = m.group(1)
    words = phrase.split()
    if len(words) < min_words:
        return False
    if _BENCHMARK_WORDS.search(phrase):
        return False  # "MSCI World", "Sharpe Ratio", "... Total Return Index"
    tail = words[-5:]
    for n in range(2, len(tail) + 1):
        if "".join(w[0] for w in tail[-n:]).upper() == symbol.upper():
            return False  # acronym definition, not a ticker
    return True


def plausible_harvest_symbol(sym: str) -> bool:
    """Stricter than _looks_symbol: gate which symbols may MINT a new security.

    Rejects finance acronyms, benchmark tickers, prose words, over-long bare
    alpha symbols, and consonant-only gibberish from OCR'd tables.
    """
    s = sym.upper()
    if not _looks_symbol(s):
        return False
    base = s.split(".", 1)[0]
    if base in HARVEST_BLOCKLIST or base.lower() in COMMON_WORDS:
        return False
    if base in _EXCHANGE_TOKENS:
        return False  # exchange codes (MIL, BIT, HK, JP, ...) are not tickers
    if base.isalpha():
        if len(base) < 2:
            return False  # single letters: footnote markers / "$B" billions shorthand
        if "." not in s and len(base) > 5:
            return False  # real bare US tickers are <= 5 chars; longer = table junk
        if len(base) >= 5 and not re.search(r"[AEIOUY]", base):
            return False  # consonant-only gibberish (MVSMHTR)
    return True


_EXCHANGE_TOKENS: frozenset[str] = frozenset(
    t.replace("\\s*", "").upper() for t in re.split(r"\|", EXCHANGE_NAMES) if t.strip()
)


def extract_explicit_symbols(text: str) -> list[dict]:
    """Return raw Tier-A symbol candidates with the rule that fired.

    Each item: {"symbol": str, "numeric": bool, "rule": str, "span": (s, e)}.
    Used by the harvester to seed the security master and by the matcher.
    """
    out: list[dict] = []

    def add(sym: str, rule: str, m: re.Match, numeric: bool = False) -> None:
        if not numeric and sym.upper() in COUNTRY_CODES:
            return
        if numeric or _looks_symbol(sym):
            out.append({"symbol": sym.upper(), "numeric": numeric, "rule": rule, "span": m.span()})

    for m in DOLLAR_TICKER_RE.finditer(text):
        add(m.group(1), "dollar", m)
    for m in PAREN_EXCH_TICKER_RE.finditer(text):
        sym = m.group(1)
        add(sym, "paren_exch", m, numeric=sym.isdigit())
    for m in EXCH_PREFIX_TICKER_RE.finditer(text):
        sym = m.group(1)
        add(sym, "exch_prefix", m, numeric=sym.isdigit())
    for m in PAREN_NUM_EXCH_RE.finditer(text):
        add(m.group(1), "paren_num_exch", m, numeric=True)
    for m in DOTTED_TICKER_RE.finditer(text):
        if m.group(1) not in NON_TICKER_DOTTED:
            add(m.group(1), "dotted", m)
    # bare (TICKER) only when preceded by a capitalized company word
    for m in PAREN_BARE_RE.finditer(text):
        sym = m.group(1)
        pre = text[max(0, m.start() - 40):m.start()]
        if re.search(r"[A-Z][a-zA-Z&.]+\s*$", pre):
            add(sym, "paren_company", m)
    return out


# ---------------------------------------------------------------------------
# Full matcher
# ---------------------------------------------------------------------------
TIER_RANK = {"A": 3, "B": 2, "C": 1}


def _sentences(text: str) -> list[tuple[int, str]]:
    spans: list[tuple[int, str]] = []
    for m in re.finditer(r"[^.!?\n]{15,400}[.!?\n]", text):
        spans.append((m.start(), m.group(0).strip()))
    return spans


def _window(text: str, pos: int, radius: int = 130) -> str:
    return text[max(0, pos - radius):min(len(text), pos + radius)]


def _classify_action(window: str) -> str | None:
    for action, pat in ACTION_PATTERNS:
        if pat.search(window):
            return {"buy": "add"}.get(action, action)
    return None


def _table_action_from_cell(cell: str) -> str | None:
    m = TABLE_CHANGE_TOKEN_RE.search(cell or "")
    if not m:
        return None
    return TABLE_CHANGE_MAP.get(m.group(1).lower())


def _holdings_table_block(text: str) -> str:
    m = HOLDINGS_HEADING_RE.search(text)
    if not m:
        return ""
    start = m.end()
    tail = text[start : start + 6000]
    lines = tail.splitlines()
    block: list[str] = []
    blank = 0
    for line in lines[:80]:
        stripped = line.strip()
        if not stripped:
            blank += 1
            if blank >= 2 and block:
                break
            continue
        blank = 0
        if block and re.match(r"^[A-Z][A-Za-z0-9 /&\-]{3,40}$", stripped) and "|" not in stripped and "\t" not in stripped:
            if not TABLE_ROW_TICKER_RE.search(stripped):
                break
        block.append(stripped)
    return "\n".join(block)


def parse_holdings_table_rows(text: str, master: SecurityMaster) -> list[dict]:
    """Parse structured holdings tables into tier-A/B mentions with actions."""
    block = _holdings_table_block(text)
    if not block:
        return []
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in block.splitlines():
        if len(line) < 4:
            continue
        parts = [p.strip() for p in re.split(r"\||\t", line) if p.strip()] if ("|" in line or "\t" in line) else [line]
        if len(parts) < 1:
            continue
        action = None
        for part in reversed(parts):
            action = _table_action_from_cell(part)
            if action:
                break
        if len(parts) < 2 and not action:
            continue
        blob = " ".join(parts)
        ticker = None
        for m in TABLE_ROW_TICKER_RE.finditer(blob):
            sym = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if not sym:
                continue
            resolved = master.resolve_symbol(sym) or master.resolve_numeric(sym)
            if resolved and not is_benchmark(resolved):
                ticker = resolved
                break
        if not ticker:
            continue
        key = (ticker, action or "hold")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "ticker": ticker,
                "tier": "A",
                "rules": ["holdings_table"],
                "mention_count": 1,
                "in_holdings_table": True,
                "action": action or "hold",
                "conviction": "high" if action in {"new", "add", "trim", "exit", "short"} else "med",
                "evidence": re.sub(r"\s+", " ", line.strip())[:300],
                "in_book": master.in_book(ticker),
                "score": 8.0 + (3.0 if action in {"new", "add", "trim", "exit", "short"} else 0),
            }
        )
    return rows


def match_letter(text: str, master: SecurityMaster) -> list[dict]:
    """Return structured, tiered mentions for one letter."""
    holdings_zone = bool(HOLDINGS_HEADING_RE.search(text))
    # candidate ticker -> aggregation bucket
    cand: dict[str, dict] = {}

    def bucket(ticker: str) -> dict:
        return cand.setdefault(
            ticker,
            {
                "ticker": ticker,
                "tier": "C",
                "rules": set(),
                "mention_count": 0,
                "spans": [],
                "in_holdings_table": False,
                "in_book": master.in_book(ticker),
            },
        )

    # --- Tier A: explicit syntax ---
    for hit in extract_explicit_symbols(text):
        if hit["numeric"]:
            ticker = master.resolve_numeric(hit["symbol"])
        else:
            ticker = master.resolve_symbol(hit["symbol"])
        if not ticker:
            continue
        symbol = ticker.split(".", 1)[0]
        short = symbol.isalpha() and len(symbol) <= 2
        # short symbols are ambiguous: footnote "(B)"/"(a)", "$M" millions.
        # Trust them when in the book, or when written as "Company Name (KD)"
        # (guarded), but never as a bare footnote marker.
        if short:
            if hit["rule"] == "paren_company":
                if not parenthetical_is_ticker(text, hit["span"][0], symbol, min_words=1):
                    continue
            elif not master.in_book(ticker):
                continue
        b = bucket(ticker)
        b["tier"] = "A"
        b["rules"].add(hit["rule"])
        b["mention_count"] += 1
        b["spans"].append(hit["span"][0])

    # --- Bare uppercase symbol tokens (non-collision -> B; collision excluded) ---
    if master.bare_symbol_re is not None:
        sym_hits: dict[str, list[int]] = {}
        for m in master.bare_symbol_re.finditer(text):
            sym = m.group(0)
            ticker = master.bare_symbol_map.get(sym)
            if ticker:
                sym_hits.setdefault(ticker, []).append(m.start())
        for ticker, positions in sym_hits.items():
            b = bucket(ticker)
            b["rules"].add("bare_symbol")
            b["mention_count"] += len(positions)
            b["spans"].extend(positions)
            if b["tier"] == "C":
                b["tier"] = "B" if len(positions) >= 2 else "C"

    # --- Company-name matches (combined regex, mapped back via normalization) ---
    if master.name_re is not None:
        name_hits: dict[str, list[int]] = {}
        for m in master.name_re.finditer(text):
            norm = re.sub(r"[\s\-]+", " ", m.group(0)).strip().lower()
            ticker = master.name_alias_to_ticker.get(norm)
            if ticker:
                name_hits.setdefault(ticker, []).append(m.start())
        for ticker, positions in name_hits.items():
            b = bucket(ticker)
            b["rules"].add("company_name")
            b["mention_count"] += len(positions)
            b["spans"].extend(positions)
            near_action = any(_classify_action(_window(text, p)) for p in positions[:6])
            if b["tier"] == "C":
                b["tier"] = "B" if (len(positions) >= 2 or near_action or holdings_zone) else "C"

    # --- distinctive single-token names (e.g. "Google") ---
    if master.single_token_re is not None:
        tok_hits: dict[str, list[int]] = {}
        for m in master.single_token_re.finditer(text):
            ticker = master.single_token_to_ticker.get(m.group(0).lower())
            if ticker:
                tok_hits.setdefault(ticker, []).append(m.start())
        for ticker, positions in tok_hits.items():
            b = bucket(ticker)
            b["rules"].add("single_token_name")
            b["mention_count"] += len(positions)
            b["spans"].extend(positions)
            # single-token brand mentions ("Google", "Amazon") are only promoted
            # to Tier B with explicit position/action context; bare repetition
            # (e.g. a name cited as a comparison) stays Tier C.
            near_action = any(_classify_action(_window(text, p)) for p in positions[:8])
            if b["tier"] == "C":
                b["tier"] = "B" if near_action else "C"

    # --- holdings table rows (explicit ticker + change column) ---
    for row in parse_holdings_table_rows(text, master):
        ticker = row["ticker"]
        b = bucket(ticker)
        b["rules"].add("holdings_table")
        b["mention_count"] += 1
        b["in_holdings_table"] = True
        if TIER_RANK.get(row["tier"], 0) > TIER_RANK.get(b["tier"], 0):
            b["tier"] = row["tier"]
        if row.get("action") and row["action"] != "discuss":
            b["table_action"] = row["action"]

    # --- finalize each candidate ---
    mentions: list[dict] = []
    for ticker, b in cand.items():
        if is_benchmark(ticker) and not master.in_book(ticker):
            continue  # benchmark/index codes are not investable positions
        spans = sorted(set(b["spans"]))
        windows = [_window(text, p) for p in spans[:6]]
        action = b.get("table_action")
        if not action:
            for w in windows:
                action = _classify_action(w)
                if action:
                    break
        in_table = holdings_zone and any(
            HOLDINGS_HEADING_RE.search(text[max(0, p - 600):p]) for p in spans[:4]
        )
        conviction = "low"
        if in_table or any(CONVICTION_HIGH_RE.search(w) for w in windows):
            conviction = "high"
        elif b["mention_count"] >= 3 or action in {"new", "add", "trim", "exit"}:
            conviction = "med"
        if in_table and b["tier"] != "A":
            b["tier"] = "B"
        evidence = _best_evidence(text, spans, ticker)
        mentions.append(
            {
                "ticker": ticker,
                "tier": b["tier"],
                "rules": sorted(b["rules"]),
                "mention_count": b["mention_count"],
                "in_holdings_table": in_table,
                "action": action or "discuss",
                "conviction": conviction,
                "evidence": evidence,
                "in_book": b["in_book"],
                "score": _score(b, action, in_table),
            }
        )
    mentions.sort(key=lambda r: (TIER_RANK.get(r["tier"], 0), r["score"]), reverse=True)
    return mentions


def bucket_tier(cand: dict[str, dict], ticker: str) -> str:
    return cand.get(ticker, {}).get("tier", "C")


def _name_positions(text: str, norm: str) -> list[int]:
    tokens = norm.split()
    if not tokens:
        return []
    pat = r"(?<![A-Za-z0-9])" + r"[\s\-]+".join(re.escape(t) for t in tokens) + r"(?![A-Za-z0-9])"
    return [m.start() for m in re.finditer(pat, text, re.I)]


def _best_evidence(text: str, spans: list[int], ticker: str) -> str:
    if not spans:
        return ""
    pos = spans[0]
    raw = _window(text, pos, 150)
    return re.sub(r"\s+", " ", raw).strip()[:300]


def _score(b: dict, action: str | None, in_table: bool) -> float:
    score = float(b["mention_count"])
    if in_table:
        score += 5
    if action in {"new", "add", "trim", "exit", "short"}:
        score += 3
    if "dollar" in b["rules"] or "paren_exch" in b["rules"]:
        score += 4
    return score


def emitted_mentions(mentions: Iterable[dict], min_tier: str = "B") -> list[dict]:
    floor = TIER_RANK.get(min_tier, 2)
    return [m for m in mentions if TIER_RANK.get(m["tier"], 0) >= floor]
