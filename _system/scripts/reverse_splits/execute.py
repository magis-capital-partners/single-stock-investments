"""Point-in-time entry, spread, and corporate-action cover."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)


def _as_et(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=ET)
    return moment.astimezone(ET)


def session_open(day: str) -> datetime:
    y, m, d = (int(p) for p in day[:10].split("-"))
    return datetime(y, m, d, SESSION_OPEN.hour, SESSION_OPEN.minute, tzinfo=ET)


def entry_index(
    dates: list[str],
    accept: datetime | None = None,
    filed: str | None = None,
) -> int | None:
    """First daily bar whose 9:30 ET open is strictly after the announcement.

    A date with no clock is treated as unusable until the next session, because
    the filing may have hit after the close.
    """
    if accept is not None:
        moment = _as_et(accept)
        for i, day in enumerate(dates):
            if session_open(day) > moment:
                return i
        return None
    if not filed:
        return None
    filed_day = filed[:10]
    for i, day in enumerate(dates):
        if day > filed_day:
            return i
    return None


def bar_on_or_after(dates: list[str], day: str) -> int | None:
    target = day[:10]
    for i, d in enumerate(dates):
        if d >= target:
            return i
    return None


def last_bar_before(dates: list[str], day: str) -> int | None:
    target = day[:10]
    found = None
    for i, d in enumerate(dates):
        if d < target:
            found = i
        else:
            break
    return found


def horizon_index(entry_i: int, horizon: int, n: int) -> int | None:
    target = entry_i + horizon
    if target >= n or target < 0:
        return None
    return target


def full_spread(
    prior_high: float | None,
    prior_low: float | None,
    floor: float,
    range_fraction: float,
) -> float:
    """Full bid-ask proxy from the prior session's range, with a penny floor.

    The prior session is known at the open. The same-day range is not.
    """
    if (
        prior_high is None
        or prior_low is None
        or prior_high < prior_low
        or prior_high <= 0
        or prior_low <= 0
    ):
        return floor
    return max(floor, (prior_high - prior_low) * range_fraction)


def short_fills(entry_px: float, exit_px: float, spread_entry: float, spread_exit: float) -> tuple[float, float] | None:
    """Sell the bid, buy the ask. Both fills have to stay positive."""
    sold = entry_px - spread_entry / 2.0
    bought = exit_px + spread_exit / 2.0
    if sold <= 0 or bought <= 0:
        return None
    return sold, bought


def trade_pnl(
    shares: float,
    entry_fill: float,
    exit_fill: float,
    fee_annual: float,
    hold_days: int,
    share_factor: float = 1.0,
) -> tuple[float, float, float]:
    """Return (gross_pnl, fee_dollars, net_pnl).

    `share_factor` is the product of split ratios crossed while the short is
    open. A forced cover before the ex-date leaves it at 1.
    """
    gross = shares * entry_fill - shares * share_factor * exit_fill
    fee = shares * entry_fill * fee_annual * max(hold_days, 1) / 365.0
    return gross, fee, gross - fee
