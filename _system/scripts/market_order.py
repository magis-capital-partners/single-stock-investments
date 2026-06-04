"""Canonical market/country ordering for CLI, dashboard, and JSON."""

from __future__ import annotations

# Top choices first (SE, AU, UK per portfolio workflow).
MARKET_CHOICES: tuple[str, ...] = (
    "SE",
    "AU",
    "UK",
    "US",
    "JP",
    "CA",
    "EU",
    "IN",
    "OTC",
)

# Dashboard filter bar: All, then priority markets, then remainder.
MARKET_FILTER_PRIORITY: tuple[str, ...] = (
    "ALL",
    "SE",
    "AU",
    "UK",
    "US",
    "JP",
    "CA",
    "EU",
    "IN",
    "OTC",
)


def market_sort_key(code: str) -> tuple[int, str]:
    """Lower sort key = earlier in lists."""
    c = (code or "").strip().upper()
    try:
        return (MARKET_CHOICES.index(c), c)
    except ValueError:
        return (len(MARKET_CHOICES), c)


def sort_markets(markets: set[str] | list[str]) -> list[str]:
    return sorted({(m or "").strip().upper() for m in markets if m and m != "—"}, key=market_sort_key)


def sort_market_filters(markets: set[str] | list[str]) -> list[str]:
    """Return filter button codes: ALL + known markets in priority order."""
    present = {(m or "").strip().upper() for m in markets if m and m not in ("—", "ALL")}
    out = ["ALL"]
    for code in MARKET_FILTER_PRIORITY[1:]:
        if code in present:
            out.append(code)
    for code in sort_markets(present):
        if code not in out:
            out.append(code)
    return out
