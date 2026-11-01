"""Read spx-0dte's SPY / QQQ delivery forecast. Read-only: it opens files, nothing else.

etf-0dte is spx-0dte's SPY and QQQ 0DTE executors (IB clients 50/51, dead-executor
watchdogs 130/131, orderRef prefixes ``SPY0DTE|`` / ``QQQ0DTE|``). They trade
physically settled options in the account this repo shares, so an assigned short
delivers 100 shares per contract overnight. At each close the executor (or, if it
died, its watchdog) writes the shares it expects to be delivered:

    <live_dir>/<product>/<session>/expected_delivery_<account>.json
    {"written_at": ..., "shares": {"SPY": -100}, "detail": [...]}

``live_dir`` is spx-0dte's ``data/live``; ``product`` is ``spy`` or ``qqq``;
``session`` is the session that closed (``YYYY-MM-DD``); ``shares`` is signed net
shares (a short put assigned delivers +100, a short call -100). The morning unwind
reads the same file and sells the delivery at 09:30. A dry run writes under
``<live_dir>/<dry-run dir>/<product>/...``, which this reader never looks at, so a
simulated book can never explain real shares.

The classifier uses the result only to LABEL SPY / QQQ shares that no other book is
known to hold: ``etf_0dte_delivery`` when this forecast predicted them,
``etf_0dte_delivery_unattributed`` when nothing did. No SSI book owns either.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

PRODUCT_SYMBOLS = {"spy": "SPY", "qqq": "QQQ"}

# The newest forecast at most this many calendar days old. It covers a weekend
# plus a holiday: Friday's forecast still explains shares a failed Monday unwind
# left behind. Anything older is not evidence about today's account.
DEFAULT_MAX_AGE_DAYS = 4

_SESSION_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def new_york_today() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:  # pragma: no cover - no tz database on this host
        return date.today()


def forecast_path(live_dir: str | Path, product: str, session_day: str, account: str) -> Path:
    """Where spx-0dte's ``live_paths.expected_delivery_path`` puts one session's forecast."""
    return Path(live_dir) / product / str(session_day) / f"expected_delivery_{str(account).strip()}.json"


def _read_shares(path: Path) -> dict[str, float] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        shares = payload.get("shares")
        if not isinstance(shares, dict):
            return None
        return {str(symbol).strip().upper(): float(value) for symbol, value in shares.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def read_expected_delivery(
    live_dir: str | Path | None,
    account: str | None,
    *,
    today: date | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, float] | None:
    """Symbol -> forecast net shares from each product's newest forecast, or None.

    None means no forecast was available at all, which is a real answer: every
    SPY / QQQ share no other book holds is then unattributed. A symbol missing from
    the result had no forecast either. A product whose newest forecast cannot be
    read is treated as having none -- an older file is never substituted for it.
    """
    if not live_dir or not str(account or "").strip():
        return None
    root = Path(live_dir)
    today = today or new_york_today()
    found: dict[str, float] = {}
    for product, symbol in PRODUCT_SYMBOLS.items():
        product_dir = root / product
        if not product_dir.is_dir():
            continue
        sessions = sorted(
            (entry.name for entry in product_dir.iterdir() if entry.is_dir() and _SESSION_DIR.match(entry.name)),
            reverse=True,
        )
        for name in sessions:
            try:
                day = date.fromisoformat(name)
            except ValueError:
                continue
            if day > today:
                continue
            if (today - day).days > max_age_days:
                break
            path = forecast_path(root, product, name, str(account))
            if not path.is_file():
                continue
            shares = _read_shares(path)
            if shares is not None:
                found[symbol] = float(shares.get(symbol, 0.0))
            break
    return found or None
