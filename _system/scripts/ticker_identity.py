#!/usr/bin/env python3
"""Cross-exchange ticker identity guards.

Same bare symbols trade on different venues (US ``MSB`` Mesabi Trust vs
``ASX: MSB`` Mesoblast). Matching pipelines must reject evidence that names a
foreign exchange or a conflicting company when attaching content to a book
ticker.
"""
from __future__ import annotations

import re
from typing import Iterable

# Venue families used for compatibility checks (not MIC codes).
FAMILY_US = "US"
FAMILY_AU = "AU"
FAMILY_CA = "CA"
FAMILY_UK = "UK"
FAMILY_HK = "HK"
FAMILY_JP = "JP"
FAMILY_SE = "SE"
FAMILY_EU = "EU"
FAMILY_IN = "IN"
FAMILY_SG = "SG"
FAMILY_OTHER = "OTHER"

_SUFFIX_FAMILY: dict[str, str] = {
    "AX": FAMILY_AU,
    "ASX": FAMILY_AU,
    "TO": FAMILY_CA,
    "V": FAMILY_CA,
    "CN": FAMILY_CA,
    "L": FAMILY_UK,
    "LN": FAMILY_UK,
    "HK": FAMILY_HK,
    "T": FAMILY_JP,
    "TYO": FAMILY_JP,
    "ST": FAMILY_SE,
    "STO": FAMILY_SE,
    "HE": FAMILY_EU,
    "PA": FAMILY_EU,
    "FP": FAMILY_EU,
    "DE": FAMILY_EU,
    "F": FAMILY_EU,
    "AS": FAMILY_EU,
    "MI": FAMILY_EU,
    "BR": FAMILY_EU,
    "SW": FAMILY_EU,
    "OL": FAMILY_EU,
    "CO": FAMILY_EU,
    "NS": FAMILY_IN,
    "BO": FAMILY_IN,
    "SI": FAMILY_SG,
    "NZ": FAMILY_AU,
}

_TOKEN_FAMILY: dict[str, str] = {
    "NASDAQ": FAMILY_US,
    "NYSE": FAMILY_US,
    "NYSEARCA": FAMILY_US,
    "ARCA": FAMILY_US,
    "AMEX": FAMILY_US,
    "OTC": FAMILY_US,
    "OTCQX": FAMILY_US,
    "OTCQB": FAMILY_US,
    "CBOE": FAMILY_US,
    "ASX": FAMILY_AU,
    "TSX": FAMILY_CA,
    "TSXV": FAMILY_CA,
    "CSE": FAMILY_CA,
    "LSE": FAMILY_UK,
    "AIM": FAMILY_UK,
    "HKEX": FAMILY_HK,
    "SEHK": FAMILY_HK,
    "HK": FAMILY_HK,
    "TSE": FAMILY_JP,
    "JPX": FAMILY_JP,
    "JP": FAMILY_JP,
    "STO": FAMILY_SE,
    "OMX": FAMILY_SE,
    "EURONEXT": FAMILY_EU,
    "XETRA": FAMILY_EU,
    "FWB": FAMILY_EU,
    "EPA": FAMILY_EU,
    "BIT": FAMILY_EU,
    "MIL": FAMILY_EU,
    "B3": FAMILY_OTHER,
    "BMV": FAMILY_OTHER,
    "GPW": FAMILY_EU,
    "SGX": FAMILY_SG,
    "NSE": FAMILY_IN,
    "BSE": FAMILY_IN,
    "ATHEX": FAMILY_EU,
    "PSE": FAMILY_OTHER,
    "TASE": FAMILY_OTHER,
    "BYMA": FAMILY_OTHER,
}

_MARKET_FAMILY: dict[str, str] = {
    "US": FAMILY_US,
    "OTC": FAMILY_US,
    "AU": FAMILY_AU,
    "CA": FAMILY_CA,
    "UK": FAMILY_UK,
    "HK": FAMILY_HK,
    "JP": FAMILY_JP,
    "SE": FAMILY_SE,
    "EU": FAMILY_EU,
    "IN": FAMILY_IN,
    "SG": FAMILY_SG,
}

_EXCHANGE_NAME_RE = (
    r"NASDAQ|NYSE\s*ARCA|NYSE|ARCA|AMEX|TSX|TSXV|CSE|OTCQX|OTCQB|OTC|CBOE|LSE|"
    r"AIM|ASX|HKEX|SEHK|TSE|JPX|SGX|B3|BMV|GPW|FWB|XETRA|EURONEXT|EPA|BIT|MIL|"
    r"STO|OMX|ATHEX|PSE|TASE|BYMA|NSE|BSE"
)

EXPLICIT_EXCHANGE_TICKER_RE = re.compile(
    rf"(?P<exch>{_EXCHANGE_NAME_RE})(?:\s*Exchange)?\s*:\s*"
    rf"(?P<sym>[A-Za-z0-9][A-Za-z0-9.\-]{{0,11}})\b",
    re.I,
)

_COMPANY_STOP = frozenset(
    {
        "inc", "incorporated", "corp", "corporation", "company", "co", "ltd",
        "limited", "plc", "lp", "llc", "group", "holdings", "holding", "the",
        "and", "of", "sa", "nv", "ag", "ab", "trust", "class", "ordinary",
        "common", "shares", "share",
    }
)


def _norm_exchange_token(token: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (token or "").upper())


def exchange_token_family(token: str | None) -> str | None:
    """Map an exchange token from prose (``ASX``, ``NYSE``) to a venue family."""
    if not token:
        return None
    return _TOKEN_FAMILY.get(_norm_exchange_token(token))


def ticker_market_family(
    ticker: str,
    *,
    market: str | None = None,
    exchange: str | None = None,
) -> str:
    """Infer the venue family for a book ticker."""
    t = (ticker or "").strip().upper()
    if "." in t:
        suffix = t.rsplit(".", 1)[-1]
        if suffix in _SUFFIX_FAMILY:
            return _SUFFIX_FAMILY[suffix]
    exch = (exchange or "").strip().upper()
    if exch:
        fam = _TOKEN_FAMILY.get(_norm_exchange_token(exch)) or _SUFFIX_FAMILY.get(exch)
        if fam:
            return fam
    mkt = (market or "").strip().upper()
    if mkt in _MARKET_FAMILY:
        return _MARKET_FAMILY[mkt]
    # Bare US-listed symbols are the default book shape.
    return FAMILY_US


def families_compatible(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return left == right


def explicit_exchange_mentions(text: str, ticker: str) -> list[str]:
    """Return exchange tokens explicitly paired with ``ticker`` in ``text``."""
    if not text or not ticker:
        return []
    base = ticker.split(".", 1)[0].upper()
    dotted = ticker.upper()
    out: list[str] = []
    for match in EXPLICIT_EXCHANGE_TICKER_RE.finditer(text):
        sym = match.group("sym").upper().replace("-", ".")
        if sym in {base, dotted}:
            out.append(match.group("exch"))
    return out


def text_has_incompatible_exchange(
    text: str,
    ticker: str,
    *,
    market: str | None = None,
    exchange: str | None = None,
) -> bool:
    """True when prose pairs the symbol with a foreign exchange."""
    book_family = ticker_market_family(ticker, market=market, exchange=exchange)
    for token in explicit_exchange_mentions(text, ticker):
        mention_family = exchange_token_family(token)
        if mention_family and not families_compatible(book_family, mention_family):
            return True
    return False


def _norm_company(name: str) -> str:
    clean = re.sub(r"\([^)]*\)", " ", name or "")
    clean = clean.replace("&", " and ")
    clean = re.sub(r"[^A-Za-z0-9 ]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    tokens = [t for t in clean.split() if t not in _COMPANY_STOP and len(t) >= 3]
    return " ".join(tokens)


def _company_tokens(name: str) -> set[str]:
    norm = _norm_company(name)
    return {t for t in norm.split() if t}


def nearby_company_phrase(text: str, pos: int) -> str:
    """Capitalized phrase immediately before a ticker span."""
    pre = re.sub(r"\s+", " ", (text or "")[max(0, pos - 90) : pos]).rstrip()
    # Strip a trailing ``(EXCH:`` / ``EXCH:`` wrapper so we read the issuer name.
    pre = re.sub(
        rf"(?:\(|\s)(?:{_EXCHANGE_NAME_RE})(?:\s*Exchange)?\s*:\s*$",
        " ",
        pre,
        flags=re.I,
    ).rstrip()
    match = re.search(
        r"((?:[A-Z][A-Za-z0-9&.\-]*\s+){0,5}[A-Z][A-Za-z0-9&.\-]*)\s*(?:\(|:)?\s*$",
        pre,
    )
    if not match:
        return ""
    phrase = match.group(1).strip()
    # Ignore bare exchange tokens mistaken for company names.
    if exchange_token_family(phrase) or _norm_exchange_token(phrase) in _TOKEN_FAMILY:
        return ""
    return phrase


def company_names_conflict(
    evidence_name: str,
    book_company: str,
    aliases: Iterable[str] | None = None,
) -> bool:
    """True when evidence names a different issuer than the book company."""
    evidence_tokens = _company_tokens(evidence_name)
    if not evidence_tokens:
        return False
    book_names = [book_company, *(aliases or [])]
    book_token_sets = [_company_tokens(name) for name in book_names if name]
    book_token_sets = [tokens for tokens in book_token_sets if tokens]
    if not book_token_sets:
        return False
    for tokens in book_token_sets:
        if evidence_tokens & tokens:
            return False
        evidence_norm = " ".join(sorted(evidence_tokens))
        book_norm = " ".join(sorted(tokens))
        if evidence_norm in book_norm or book_norm in evidence_norm:
            return False
    return True


def text_has_company_conflict(
    text: str,
    ticker: str,
    company: str,
    aliases: Iterable[str] | None = None,
) -> bool:
    """True when a nearby issuer name conflicts with the book company."""
    if not text or not ticker or not company:
        return False
    base = re.escape(ticker.split(".", 1)[0])
    for match in re.finditer(rf"(?<![A-Z0-9.\-]){base}(?![A-Z0-9.\-])", text, re.I):
        phrase = nearby_company_phrase(text, match.start())
        if phrase and company_names_conflict(phrase, company, aliases):
            return True
    return False


def identity_match_ok(
    text: str,
    ticker: str,
    *,
    company: str | None = None,
    market: str | None = None,
    exchange: str | None = None,
    aliases: Iterable[str] | None = None,
) -> bool:
    """Return False when text is clearly about a different exchange listing/issuer."""
    if text_has_incompatible_exchange(text, ticker, market=market, exchange=exchange):
        return False
    if company and text_has_company_conflict(text, ticker, company, aliases):
        return False
    return True
