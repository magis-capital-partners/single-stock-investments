"""Shared helpers.

Third-party imports are deferred so the pure modules (book, strategy, ledger,
dashboard builder) load in CI with the standard library alone.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from typing import Any

try:  # pragma: no cover - exercised only where tqdm is installed
    from tqdm import tqdm
except ImportError:  # pragma: no cover

    def tqdm(iterable=None, **_kwargs):  # type: ignore[misc]
        """No-op progress wrapper when tqdm is not installed."""
        return iterable if iterable is not None else []


__all__ = [
    "RATIO_RE",
    "REVERSE_SPLIT_RE",
    "RateLimitedSession",
    "add_days",
    "looks_like_reverse_split",
    "normalize_ticker",
    "pad_cik",
    "parse_date",
    "parse_day_token",
    "parse_iso_datetime",
    "tqdm",
    "years_ago",
]


def pad_cik(cik: str | int | None) -> str | None:
    if cik is None or cik == "":
        return None
    return str(cik).strip().lstrip("0").zfill(10) if str(cik).strip() else None


def normalize_ticker(ticker: str | None) -> str | None:
    if not ticker:
        return None
    t = ticker.strip().upper()
    t = t.replace(".", "-")  # BRK.B -> BRK-B style for yfinance often uses -
    # Keep OTC suffixes like .OB rarely; strip whitespace
    return t


def parse_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" and len(s) >= 10 else s, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date().isoformat()
    except ValueError:
        return None


_DAY_FORMATS = ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d")


def parse_day_token(token: Any) -> str | None:
    """ISO date from a filing-text day such as ``January 5, 2024`` or ``1/5/2024``.

    Only the shapes the clause regexes capture are accepted; anything else is
    ``None``. Deterministic by construction (no fuzzy parsing).
    """
    text = re.sub(r"\s+", " ", str(token or "")).strip().rstrip(".")
    text = text.replace(" ,", ",")
    for fmt in _DAY_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_iso_datetime(value: Any) -> datetime | None:
    """ISO-8601 timestamp (``Z`` accepted) or ``None``; date-only input is a naive midnight."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def years_ago(years: int, today: date | None = None) -> date:
    today = today or date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        # Feb 29
        return today.replace(month=2, day=28, year=today.year - years)


def add_days(d: str | date, n: int) -> str:
    if isinstance(d, str):
        base = datetime.strptime(d[:10], "%Y-%m-%d").date()
    else:
        base = d
    return (base + timedelta(days=n)).isoformat()


REVERSE_SPLIT_RE = re.compile(
    r"reverse\s+(?:(?:stock|share)\s+)?split"
    r"|one[- ]for[- ]\d+"
    r"|1[- ]for[- ]\d+"
    r"|share\s+consolidation"
    r"|consolidation\s+of\s+(?:the\s+)?(?:issued\s+)?(?:and\s+outstanding\s+)?(?:ordinary\s+|common\s+)?shares",
    re.IGNORECASE,
)

# ``1-for-10`` / ``one for 10`` / ``10 to 1``: group 1 or 2 is the old share count.
RATIO_RE = re.compile(
    r"(?:1|one)[\s\-]*for[\s\-]*(\d{1,6})|(\d{1,6})[\s\-]*(?:to|into|for)[\s\-]*(?:1|one)",
    re.IGNORECASE,
)


def looks_like_reverse_split(text: str) -> bool:
    return bool(REVERSE_SPLIT_RE.search(text or ""))


class RateLimitedSession:
    """A ``requests`` session with a minimum delay between calls (SEC fair use)."""

    def __init__(self, user_agent: str, delay: float = 0.12):
        import requests  # deferred: only network commands need it

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.delay = delay
        self._last = 0.0

    def get(self, url: str, **kwargs):
        elapsed = time.time() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        resp = self.session.get(url, timeout=kwargs.pop("timeout", 60), **kwargs)
        self._last = time.time()
        resp.raise_for_status()
        return resp
