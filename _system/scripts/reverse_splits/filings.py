"""Read a reverse-split announcement out of filing text."""

from __future__ import annotations

import re
from datetime import datetime

from .utils import RATIO_RE, parse_day_token, parse_iso_datetime

_NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "twenty-five": 25,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "one hundred": 100,
    "one-hundred": 100,
}

_WORD_RATIO = re.compile(
    r"(?:1|one)[\s\-]*for[\s\-]*("
    r"one hundred|twenty[\s\-]five|fifteen|twelve|twenty|thirty|forty|fifty|"
    r"ten|nine|eight|seven|six|five|four|three|two)\b",
    re.IGNORECASE,
)
_EFFECTIVE = re.compile(
    r"effective(?:\s+as\s+of|\s+on|\s+at)?\s+"
    r"([A-Z][a-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})",
)
_CANCEL = re.compile(
    r"(?:abandon\w*|terminat\w*|cancel(?:led|ed)?|not\s+(?:to\s+)?proceed|determined\s+not\s+to)"
    r".{0,80}reverse|reverse.{0,80}(?:abandon\w*|terminat\w*|cancel(?:led|ed)?)",
    re.IGNORECASE | re.DOTALL,
)
_SHAREHOLDER = re.compile(
    r"stockholders?\s+(?:have\s+)?(?:approved|voted)|shareholders?\s+(?:have\s+)?(?:approved|voted)",
    re.IGNORECASE,
)
_CONSENT = re.compile(r"written\s+consent", re.IGNORECASE)
_BOARD = re.compile(
    r"board\s+of\s+directors.{0,120}(?:approved|determined|set)|"
    r"(?:approved|determined)\s+by\s+the\s+board",
    re.IGNORECASE | re.DOTALL,
)


def ratio_new_over_old(text: str) -> float | None:
    """Return new/old, so a 1-for-10 is 0.1."""
    match = RATIO_RE.search(text or "")
    if match:
        raw = match.group(1) or match.group(2)
        try:
            old = float(raw)
        except (TypeError, ValueError):
            old = 0
        if old > 1:
            return 1.0 / old
    word = _WORD_RATIO.search(text or "")
    if not word:
        return None
    token = re.sub(r"[\s]+", "-", word.group(1).lower().strip())
    old = _NUMBER_WORDS.get(token)
    if not old or old <= 1:
        return None
    return 1.0 / old


def _parse_day(token: str) -> str | None:
    return parse_day_token(token)


def vote_path_from_text(text: str) -> str | None:
    if _SHAREHOLDER.search(text or ""):
        return "shareholder"
    if _CONSENT.search(text or ""):
        return "consent"
    if _BOARD.search(text or ""):
        return "board"
    return None


def vote_path_from_form(form: str | None) -> str | None:
    compact = (form or "").upper().replace(" ", "")
    if "14C" in compact:
        return "consent"
    if "14A" in compact:
        return "shareholder"
    return None


def parse_announcement(text: str) -> dict[str, object]:
    """Pull ratio, effective date, vote path, and cancellation from filing text."""
    body = text or ""
    effective = None
    found = _EFFECTIVE.search(body)
    if found:
        effective = _parse_day(found.group(1))
    return {
        "ratio": ratio_new_over_old(body),
        "announced_ex_date": effective,
        "vote_path": vote_path_from_text(body),
        "cancelled": bool(_CANCEL.search(body)),
        "substantive": bool(
            ratio_new_over_old(body)
            or re.search(r"announc|effect a reverse|reverse stock split", body, re.IGNORECASE)
        ),
    }


def choose_announce(
    hits: list[dict],
    ex_date: str,
    lookback_days: int = 365,
    lookahead_days: int = 30,
) -> dict | None:
    """Earliest substantive 8-K/6-K in the window, else the earliest phrase hit."""
    from datetime import timedelta

    ex = datetime.strptime(ex_date[:10], "%Y-%m-%d").date()
    window = []
    for hit in hits:
        form = str(hit.get("form") or "").upper()
        if not (form.startswith("8-K") or form.startswith("6-K")):
            continue
        filed = str(hit.get("filed_at") or "")[:10]
        if len(filed) != 10:
            continue
        fd = datetime.strptime(filed, "%Y-%m-%d").date()
        if fd < ex - timedelta(days=lookback_days) or fd > ex + timedelta(days=lookahead_days):
            continue
        window.append(hit)
    substantive = [hit for hit in window if hit.get("substantive")]
    pool = substantive or window
    if not pool:
        return None
    return min(pool, key=lambda hit: (str(hit.get("filed_at") or ""), str(hit.get("accept_time") or "")))


def parse_accept_time(value: str | None) -> datetime | None:
    return parse_iso_datetime(value)
