"""Research event log for purge/embargo (PIT discipline)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .pit import latest_dated_md_as_of, load_valuation_as_of, parse_iso_date

EVENTS_PATH = ROOT / "_system" / "portfolio" / "research_events.jsonl"


def append_event(ticker: str, event_type: str, date: str, source: str = "") -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ticker": ticker,
        "event": event_type,
        "date": date[:10],
        "source": source,
        "logged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    out: list[dict] = []
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _dedupe_events(events: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for e in sorted(events, key=lambda x: (x.get("date", ""), x.get("ticker", ""))):
        key = (e.get("ticker", ""), e.get("event", ""), e.get("date", "")[:10])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def scan_ticker_events(ticker: str) -> list[dict]:
    """Discover valuation + deep_dive dates from repo."""
    events: list[dict] = []
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        return events
    val = load_valuation_as_of(ticker_dir, "9999-12-31")
    if val and val.get("as_of"):
        events.append(
            {
                "ticker": ticker,
                "event": "valuation_refresh",
                "date": str(val["as_of"])[:10],
                "source": f"{ticker}/research/valuation.json",
            }
        )
    hist = ticker_dir / "research" / "valuation_history"
    if hist.is_dir():
        for p in hist.glob("valuation_*.json"):
            m = p.stem.replace("valuation_", "")
            if len(m) >= 10:
                events.append(
                    {
                        "ticker": ticker,
                        "event": "valuation_refresh",
                        "date": m[:10],
                        "source": str(p.relative_to(ROOT)),
                    }
                )
    research = ticker_dir / "research"
    if research.is_dir():
        for p in research.glob("deep_dive_*.md"):
            m = p.name
            import re

            dm = re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", m)
            if dm:
                events.append(
                    {
                        "ticker": ticker,
                        "event": "deep_dive",
                        "date": dm.group(1),
                        "source": str(p.relative_to(ROOT)),
                    }
                )
    dive = latest_dated_md_as_of(research, "deep_dive", "9999-12-31")
    if dive:
        import re

        dm = re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", dive.name)
        if dm:
            events.append(
                {
                    "ticker": ticker,
                    "event": "deep_dive",
                    "date": dm.group(1),
                    "source": str(dive.relative_to(ROOT)),
                }
            )
    return events


def rebuild_events_log(tickers: list[str] | None = None) -> int:
    """Rewrite research_events.jsonl from repo scan."""
    from .features import holdings_universe

    universe = tickers or holdings_universe()
    all_events: list[dict] = []
    for t in universe:
        all_events.extend(scan_ticker_events(t))
    all_events = _dedupe_events(all_events)
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("w", encoding="utf-8") as f:
        for e in all_events:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    return len(all_events)


def event_dates_by_ticker(events: list[dict] | None = None) -> dict[str, list[str]]:
    ev = events or load_events()
    out: dict[str, list[str]] = {}
    for e in ev:
        t = e.get("ticker", "")
        d = (e.get("date") or "")[:10]
        if t and d:
            out.setdefault(t, []).append(d)
    for t in out:
        out[t] = sorted(set(out[t]))
    return out


def is_embargoed(
    rebalance_date: str,
    ticker: str,
    events: list[dict] | None = None,
    embargo_rebalances: int = 1,
) -> bool:
    """Block using post-event research in train fold for N rebalance periods after event."""
    ev = events or load_events()
    rdt = parse_iso_date(rebalance_date)
    if not rdt:
        return False
    for e in ev:
        if e.get("ticker") != ticker:
            continue
        edt = parse_iso_date(e.get("date"))
        if not edt:
            continue
        if edt <= rdt and (rdt - edt).days < 30 * max(embargo_rebalances, 1) * 6:
            return True
    return False


def purge_tickers_at_rebalance(
    rebalance_date: str,
    tickers: list[str],
    events: list[dict] | None = None,
    purge_days: int = 120,
) -> list[str]:
    """Drop tickers with research event within purge_days before rebalance (train contamination)."""
    ev = events or load_events()
    rdt = parse_iso_date(rebalance_date)
    if not rdt:
        return tickers
    keep: list[str] = []
    for t in tickers:
        contaminated = False
        for e in ev:
            if e.get("ticker") != t:
                continue
            edt = parse_iso_date(e.get("date"))
            if not edt:
                continue
            delta = abs((rdt - edt).days)
            if delta <= purge_days:
                contaminated = True
                break
        if not contaminated:
            keep.append(t)
    return keep if keep else tickers
