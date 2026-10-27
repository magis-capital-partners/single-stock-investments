"""Dated US cash-equity session calendar with explicit coverage limits.

Full closures follow the exchange publications below. Early closes remain
trading sessions. Unsupported years require an update before current-price
metrics can be published. Dates represent end-of-day cutoffs.
"""
from datetime import date, timedelta

CALENDAR_ID = "US_EQUITIES_2025_2028"
SOURCES = [
    "https://www.nyse.com/trade/hours-calendars",
    "https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx",
    "https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx",
    "https://nasdaqtrader.com/Trader.aspx?id=Calendar",
]
HOLIDAYS = {
    2025: {"01-01", "01-09", "01-20", "02-17", "04-18", "05-26", "06-19", "07-04", "09-01", "11-27", "12-25"},
    2026: {"01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"},
    2027: {"01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"},
    2028: {"01-17", "02-21", "04-14", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"},
}

def trading_sessions(start, end, calendar=CALENDAR_ID):
    """Count session dates in (start, end], or None when unsupported."""
    try:
        first, last = (date.fromisoformat(str(value)[:10]) for value in (start, end))
    except (ValueError, TypeError):
        return None
    if calendar != CALENDAR_ID or first > last:
        return None
    if any(year not in HOLIDAYS for year in range(first.year, last.year + 1)):
        return None
    return sum(
        current.weekday() < 5 and current.strftime("%m-%d") not in HOLIDAYS[current.year]
        for current in (first + timedelta(days=i) for i in range(1, (last-first).days+1))
    )
