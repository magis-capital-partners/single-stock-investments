"""US filing date availability for the RSI-3.0 research lane."""
from datetime import date
from zoneinfo import ZoneInfo

from .net_edge import moment

NY = ZoneInfo("America/New_York")


def market_date(value):
    stamp = moment(value) if isinstance(value, str) else value
    return stamp.astimezone(NY).date().isoformat()


def available(record, cutoff):
    stamp = moment(record.get("known_at"))
    if stamp is not None: return stamp <= cutoff
    try: day = date.fromisoformat(record.get("known_at", ""))
    except (TypeError, ValueError): return False
    # SEC filing dates are Eastern dates. UTC midnight can precede the end of
    # that filing day by four/five hours and must not expose a later filing.
    return day.isoformat() < market_date(cutoff)
