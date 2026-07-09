#!/usr/bin/env python3
"""Subject-gated index add/delete extraction from news titles (precision-first)."""
from __future__ import annotations

import re
from typing import Any

INDEX_ALIASES: dict[str, str] = {
    "s&p 500": "sp500",
    "s&p500": "sp500",
    "sp 500": "sp500",
    "s&p midcap 400": "sp400",
    "s&p midcap": "sp400",
    "s&p 400": "sp400",
    "s&p smallcap 600": "sp600",
    "s&p smallcap": "sp600",
    "s&p 600": "sp600",
    "russell 3000e": "russell_2000",  # growth/value subsets still map to R2000 family for watch
    "russell 3000": "russell_1000",
    "russell 1000": "russell_1000",
    "russell1000": "russell_1000",
    "russell 2000": "russell_2000",
    "russell2000": "russell_2000",
    "russell 2500": "russell_2000",  # mid+small; small-cap adds watch R2000
    "russell2500": "russell_2000",
    "russell midcap": "russell_1000",
    "russell defensive": "russell_2000",
    "russell top 50": "russell_1000",  # mega-cap subset; treat as R1000-family reclass
    "russell growth": "russell_1000",
    "russell value": "russell_1000",
    "russell": "russell_1000",  # bare "Russell reclassification" → R1000 family watch
    "nasdaq-100": "nasdaq_100",
    "nasdaq 100": "nasdaq_100",
    "nasdaq100": "nasdaq_100",
    "msci usa": "msci_usa",
    "msci acwi": "msci_acwi",
    "msci": "msci_acwi",
    "s&p/tsx composite": "tsx_composite",
    "s&p/tsx": "tsx_composite",
    "tsx composite": "tsx_composite",
    "dow jones industrial average": "djia",
    "dow jones": "djia",
    "djia": "djia",
    "the dow": "djia",
    "dow": "djia",
    "topix": "topix",
    "ftse 100": "ftse_100",
    "ftse 250": "ftse_250",
    "stoxx europe 600": "stoxx_europe_600",
    "stoxx 600": "stoxx_europe_600",
    "asx 200": "asx_200",
    "nzx 50": "nzx_50",
    "hang seng": "hang_seng",
    "nifty 500": "nifty_500",
}

# Longest aliases first for regex alternation
_INDEX_ALT = "|".join(
    re.escape(a) for a in sorted(INDEX_ALIASES.keys(), key=len, reverse=True)
)

_ADD_VERBS = (
    r"(?:joins?|joined|joining|added\s+to|to\s+be\s+added\s+to|will\s+be\s+added\s+to|"
    r"set\s+to\s+join|inclusion\s+in)"
)
_DEL_VERBS = (
    r"(?:removed\s+from|deleted\s+from|dropped\s+from|to\s+be\s+removed\s+from|"
    r"deletion\s+from|exclusion\s+from|exit(?:s|ed|ing)?\s+from)"
)
_INDEX_ADDS = r"(?:adds?|will\s+add|to\s+add|adding)"

# Subject: ticker in parens, bare ticker, or multi-word company name
_SUBJECT = (
    r"(?P<subject>"
    r"[A-Za-z][A-Za-z0-9.\-]{0,14}"  # ticker-like
    r"|(?:[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){0,6})"  # Company Name
    r")"
)

_SUBJECT_TICKER_PAREN = re.compile(
    r"(?P<name>[A-Za-z][^()]{1,80}?)\s*\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\)",
    re.I,
)

_PAT_SUBJECT_JOINS = re.compile(
    rf"(?P<sub>(?:[A-Za-z][A-Za-z0-9.\-]{{0,14}}|"
    rf"[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){{0,6}}|"
    rf"[A-Za-z][^()]{{1,60}}?\([^)]+\)))"
    rf"\s+(?:is\s+|was\s+|has\s+|have\s+)?"
    rf"(?P<verb>{_ADD_VERBS}|{_DEL_VERBS})"
    rf"\s+(?:the\s+)?(?P<index>{_INDEX_ALT})\b",
    re.I,
)

_PAT_INDEX_ADDS_SUBJECT = re.compile(
    rf"(?:the\s+)?(?P<index>{_INDEX_ALT})\b"
    rf"\s+(?P<verb>{_INDEX_ADDS})"
    rf"\s+(?P<sub>(?:[A-Za-z][A-Za-z0-9.\-]{{0,14}}|"
    rf"[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){{0,6}}))",
    re.I,
)

_PAT_ADDED_TO_INDEX = re.compile(
    rf"(?P<sub>(?:[A-Za-z][A-Za-z0-9.\-]{{1,14}}|"
    rf"[A-Za-z][^()]{{1,60}}?\([^)]+\)))"
    rf"\s+added\s+to\s+(?:the\s+)?(?P<index>{_INDEX_ALT})\b",
    re.I,
)

# "SpaceX has been added to the Russell 1000"
_PAT_HAS_BEEN_ADDED = re.compile(
    rf"(?P<sub>[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){{0,4}})"
    rf"\s+has\s+been\s+(?P<verb>added\s+to|removed\s+from|deleted\s+from|dropped\s+from)"
    rf"\s+(?:the\s+)?(?P<index>{_INDEX_ALT})\b",
    re.I,
)

# "Company (TICKER) ... joins INDEX" with intervening words (valuation blurbs, etc.)
_PAT_TICKER_THEN_JOINS = re.compile(
    rf"\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\)"
    rf".{{0,80}}?"
    rf"(?P<verb>{_ADD_VERBS}|{_DEL_VERBS})"
    rf"\s+(?:the\s+)?(?P<index>{_INDEX_ALT})\b",
    re.I | re.S,
)

# Reclassification / style-box moves (Copart Russell reclassification, index shift)
_RECLASS_PHRASE = (
    r"(?:index\s+reclassification|russell\s+reclassification|russell\s+reshuffle|"
    r"russell\s+index\s+reshuffle|joins?\s+russell\s+top\s+50|"
    r"index\s+reclass(?:ification)?|index\s+reshuffle|"
    r"index\s+shift|index\s+moves?|index\s+change|style\s+reclassification|"
    r"reclassification|reclassified|reshuffle)"
)

# "After Nasdaq-100 Exit" / "exits the Nasdaq-100"
_PAT_INDEX_EXIT = re.compile(
    rf"(?P<sub>[A-Za-z][^()]{{0,60}}?\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\))"
    rf".{{0,80}}?(?:nasdaq[-\s]?100|s&p\s*500|russell\s+\d+)\s+exit"
    rf"|(?:after|following)\s+(?P<index>{_INDEX_ALT})\s+exit",
    re.I | re.S,
)
_PAT_EXIT_SHORT = re.compile(
    rf"\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\)"
    rf".{{0,60}}?(?P<index>nasdaq[-\s]?100|s&p\s*500|russell\s+1000|russell\s+2000)\s+exit",
    re.I | re.S,
)

# "Alphabet Just Replaced Verizon in the Dow"
_PAT_DOW_REPLACE = re.compile(
    rf"(?P<sub>[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){{0,3}}?)"
    rf"(?:\s+(?:just|has|have|had))?\s+replac(?:ed|es|ing)\b"
    rf".{{0,50}}?\b(?:in\s+)?(?:the\s+)?(?P<index>dow|djia|dow\s+jones)\b",
    re.I | re.S,
)
_PAT_RECLASS_TICKER_PAREN = re.compile(
    rf"(?P<sub>[A-Za-z][^()]{{0,60}}?\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\))"
    rf".{{0,100}}?{_RECLASS_PHRASE}"
    rf"(?:.{{0,40}}?(?P<index>{_INDEX_ALT}))?",
    re.I | re.S,
)
_PAT_RECLASS_THEN_TICKER = re.compile(
    rf"(?:(?P<index>{_INDEX_ALT})\s+)?{_RECLASS_PHRASE}"
    rf".{{0,100}}?"
    rf"(?P<sub>[A-Za-z][^()]{{0,60}}?\((?P<exch>[A-Za-z]+:\s*)?(?P<ticker>[A-Za-z0-9.\-]+)\))",
    re.I | re.S,
)
_PAT_RECLASS_COMPANY = re.compile(
    rf"(?P<sub>[A-Z][A-Za-z0-9&'.\-]+(?:\s+[A-Z][A-Za-z0-9&'.\-]+){{0,4}})"
    rf".{{0,60}}?{_RECLASS_PHRASE}"
    rf"(?:.{{0,40}}?(?P<index>{_INDEX_ALT}))?",
    re.I | re.S,
)


def resolve_index_alias(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if key in INDEX_ALIASES:
        return INDEX_ALIASES[key]
    for alias, idx in sorted(INDEX_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in key:
            return idx
    return None


def _normalize_ticker_token(token: str) -> str:
    t = (token or "").strip().upper()
    # Strip exchange prefixes like NASDAQGS: ECHO
    if ":" in t:
        t = t.split(":")[-1].strip()
    return t


def _subject_to_ticker(
    subject_raw: str,
    candidate_tickers: list[str],
    company_names: dict[str, str] | None = None,
) -> str | None:
    """Map a subject phrase to one of candidate_tickers, or None."""
    candidates = [str(t) for t in (candidate_tickers or []) if t]
    if not candidates:
        return None
    cand_upper = {c.upper(): c for c in candidates}
    company_names = company_names or {}
    ENGLISH_STOP = {
        "A", "AN", "THE", "OR", "AND", "TO", "OF", "IN", "ON", "FOR", "AS", "IT", "IS",
        "BE", "BY", "AT", "IF", "SO", "NO", "YES", "ALL", "ANY", "NOT", "BUT", "HAS",
        "HAVE", "HAD", "WAS", "WERE", "BEEN", "BEING", "WILL", "CAN", "MAY", "ITS",
    }

    # Prefer explicit (TICKER) in subject
    m = _SUBJECT_TICKER_PAREN.search(subject_raw or "")
    if m:
        tk = _normalize_ticker_token(m.group("ticker"))
        if tk in cand_upper:
            return cand_upper[tk]
        bare = tk.split(".")[0]
        for cu, orig in cand_upper.items():
            if cu == tk or cu.split(".")[0] == bare:
                return orig

    sub = (subject_raw or "").strip()
    sub_up = sub.upper()
    # Exact ticker (whole subject is the ticker)
    if sub_up in cand_upper and sub_up not in ENGLISH_STOP:
        return cand_upper[sub_up]

    # Reject tiny / stop-word subjects (e.g. "be" from "will be added to" matching Alphabet)
    if len(sub) < 3 or sub_up in ENGLISH_STOP:
        return None

    # Short tickers (len <= 3): only accept exact subject or (TICKER) form — never substring
    # in a long phrase (avoids OR matching English "or", HE matching "the", etc.)
    for cu, orig in cand_upper.items():
        if len(cu.split(".")[0]) <= 3:
            continue
        if re.search(rf"\b{re.escape(cu)}\b", sub_up):
            return orig

    # Company name containment (longest first) — require subject length >= 4
    if len(sub) < 4:
        return None
    name_pairs = []
    for t in candidates:
        name = (company_names.get(t) or "").strip()
        if name and len(name) >= 4:
            name_pairs.append((t, name))
    name_pairs.sort(key=lambda x: -len(x[1]))
    sub_low = sub.lower()
    for t, name in name_pairs:
        nlow = name.lower()
        # Prefer whole-word / substantial overlap; never let 2-letter crumbs match
        if len(sub_low) >= 4 and (nlow in sub_low or sub_low in nlow):
            return t
        parts = [
            p
            for p in re.split(r"\s+", name)
            if p.lower()
            not in {"inc", "inc.", "corp", "corp.", "ltd", "ltd.", "plc", "the", "co", "co.", "group"}
        ]
        if len(parts) >= 1:
            head = " ".join(parts[:2]).lower()
            if len(head) >= 4 and head in sub_low:
                return t
    return None


def _verb_to_action(verb: str) -> str | None:
    v = (verb or "").lower()
    if re.search(r"remov|delet|dropp|exclusion|exit", v):
        return "delete"
    if re.search(
        r"reclass|reshuffl|index\s+shift|index\s+moves?|index\s+change|style\s+reclass|"
        r"top\s+50|replac",
        v,
    ):
        return "reclassify"
    if re.search(r"join|add|inclusion", v):
        return "add"
    return None


def _default_index_from_text(text: str) -> str | None:
    """When reclass headlines omit 1000/2000 (or say only 'index shift')."""
    low = (text or "").lower()
    if "russell" in low:
        return "russell_1000"
    if "nasdaq" in low:
        return "nasdaq_100"
    if "s&p" in low or "s and p" in low:
        return "sp500"
    if "msci" in low:
        return "msci_usa"
    # Bare index reclass / shift / moves (Copart simplywall titles) → Russell family watch
    if re.search(
        r"\b(?:index\s+reclass|index\s+shift|index\s+moves?|index\s+change|"
        r"style\s+reclass|reclassification|reshuffl)",
        low,
    ):
        return "russell_1000"
    return None


def extract_index_events(
    title: str,
    summary: str = "",
    candidate_tickers: list[str] | None = None,
    company_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Extract index add/delete/reclassify events where a portfolio ticker is the subject.

    Returns list of {ticker, index, action}. Empty if no subject-gated match.
    Precision over recall: co-mentions of mega-caps in SpaceX/CoreWeave stories return [].
    """
    text = f"{title or ''} {summary or ''}".strip()
    if not text:
        return []
    candidates = [str(t) for t in (candidate_tickers or []) if t]
    if not candidates:
        return []

    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(sub_raw: str, index_raw: str, verb: str, *, default_index: str | None = None) -> None:
        index_id = resolve_index_alias(index_raw) if index_raw else None
        if not index_id:
            index_id = default_index
        action = _verb_to_action(verb)
        if not index_id or not action:
            return
        ticker = _subject_to_ticker(sub_raw, candidates, company_names)
        if not ticker:
            return
        key = (ticker, index_id, action)
        if key in seen:
            return
        seen.add(key)
        found.append({"ticker": ticker, "index": index_id, "action": action})

    for pat in (_PAT_SUBJECT_JOINS, _PAT_ADDED_TO_INDEX, _PAT_HAS_BEEN_ADDED):
        for m in pat.finditer(text):
            gd = m.groupdict()
            verb = gd.get("verb") or "added to"
            _push(gd.get("sub") or "", gd.get("index") or "", verb)

    for m in _PAT_INDEX_ADDS_SUBJECT.finditer(text):
        gd = m.groupdict()
        _push(gd.get("sub") or "", gd.get("index") or "", gd.get("verb") or "adds")

    for m in _PAT_TICKER_THEN_JOINS.finditer(text):
        gd = m.groupdict()
        tk = _normalize_ticker_token(gd.get("ticker") or "")
        if tk:
            _push(tk, gd.get("index") or "", gd.get("verb") or "joins")

    # Reclassification / index shift (subject must still resolve to a candidate)
    default_idx = _default_index_from_text(text)
    for pat in (_PAT_RECLASS_TICKER_PAREN, _PAT_RECLASS_THEN_TICKER):
        for m in pat.finditer(text):
            gd = m.groupdict()
            tk = _normalize_ticker_token(gd.get("ticker") or "")
            sub = gd.get("sub") or tk
            _push(sub, gd.get("index") or "", "reclassification", default_index=default_idx)

    for m in _PAT_RECLASS_COMPANY.finditer(text):
        gd = m.groupdict()
        verb = "reclassification"
        # "Joins Russell Top 50" is a mega-cap subset move, not a parent-index add
        if re.search(r"top\s+50", text, re.I):
            verb = "joins russell top 50"
        _push(gd.get("sub") or "", gd.get("index") or "", verb, default_index=default_idx)

    for m in _PAT_EXIT_SHORT.finditer(text):
        gd = m.groupdict()
        tk = _normalize_ticker_token(gd.get("ticker") or "")
        if tk:
            _push(tk, gd.get("index") or "", "exit from")

    for m in _PAT_DOW_REPLACE.finditer(text):
        gd = m.groupdict()
        # Subject is the company entering the Dow (replacing someone else)
        _push(gd.get("sub") or "", gd.get("index") or "dow", "added to")

    # "Joins Russell Top 50" via normal join patterns → force reclassify; dedupe
    deduped: list[dict[str, Any]] = []
    seen_ti: set[tuple[str, str]] = set()
    for ev in found:
        if ev.get("index") == "russell_1000" and re.search(
            r"russell\s+top\s+50|top\s+50", text, re.I
        ):
            ev["action"] = "reclassify"
        key = (ev["ticker"], ev["index"])
        # Prefer reclassify over add for same ticker+index in one headline
        if key in seen_ti:
            for prev in deduped:
                if prev["ticker"] == ev["ticker"] and prev["index"] == ev["index"]:
                    if ev["action"] == "reclassify":
                        prev["action"] = "reclassify"
                    break
            continue
        seen_ti.add(key)
        deduped.append(ev)
    return deduped
