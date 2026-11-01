"""Normalized operating-KPI points and the on-disk store.

One row is one observation:

    ticker, kpi, period, value, unit, yoy, source_url, doc, accession, fetched_at

``period`` is ``YYYY-MM``. ``yoy`` is a ratio (0.048 means +4.8%) except when
``yoy_basis`` is ``percentage_points`` (share and other rate series). ``yoy``
is null when the prior-year month is not in the same file.
"""
from __future__ import annotations

import json
import calendar
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from atomic_io import write_json_if_changed

ROOT = Path(__file__).resolve().parents[3]
STORE_DIR = ROOT / "_system" / "reference" / "market-data" / "operating_kpis"

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

POINT_KEYS = (
    "ticker",
    "kpi",
    "period",
    "value",
    "unit",
    "yoy",
    "yoy_basis",
    "source_url",
    "doc",
    "accession",
    "fetched_at",
)


class LayoutError(ValueError):
    """The document was fetched but its table shape is not the one we parse."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_number(token: str) -> float | None:
    text = str(token or "").strip()
    if not text or text.lower() in {"-", "—", "n/a", "na", "nm"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").replace("%", "").replace("\u00a0", "").strip()
    if not text or text in {"-", "—"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def month_period(token: str) -> str | None:
    """``Jan-26`` or ``September 2026`` -> ``2026-01`` / ``2026-09``."""
    text = str(token or "").strip()
    match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-]+(\d{2}|\d{4})\b",
        text,
        re.I,
    )
    if not match:
        return None
    month = MONTHS[match.group(1).lower()[:3]]
    year_raw = match.group(2)
    year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)
    return f"{year:04d}-{month:02d}"


def shift_year(period: str, years: int) -> str:
    match = re.fullmatch(r"(\d{4})(-\d{2}|Q[1-4]|)", period)
    if not match:
        raise LayoutError(f"Invalid operating period: {period}")
    return f"{int(match.group(1)) + years:04d}{match.group(2)}"


def period_end(period: str):
    """Economic end date for monthly, quarterly and annual observations."""
    from datetime import date
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})|Q([1-4]))?", str(period))
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else int(match.group(3) or 4) * 3
    if not 1 <= month <= 12:
        return None
    return date(year, month, calendar.monthrange(year, month)[1])


def period_key(period: str):
    end = period_end(period)
    return end.isoformat() if end else ""


def make_point(
    *,
    ticker: str,
    kpi: str,
    period: str,
    value: float,
    unit: str,
    source_url: str,
    doc: str,
    fetched_at: str,
    accession: str | None = None,
    yoy_basis: str = "ratio",
) -> dict:
    return {
        "ticker": ticker,
        "kpi": kpi,
        "period": period,
        "value": value,
        "unit": unit,
        "yoy": None,
        "yoy_basis": yoy_basis,
        "source_url": source_url,
        "doc": doc,
        "accession": accession,
        "fetched_at": fetched_at,
    }


def attach_yoy(points: list[dict]) -> list[dict]:
    """Fill ``yoy`` from the same kpi one year earlier. Later rows win on ties."""
    by_key: dict[tuple[str, str, str], dict] = {}
    for point in points:
        by_key[(point["ticker"], point["kpi"], point["period"])] = point
    for point in by_key.values():
        if "guidance" in point["kpi"]:
            point["yoy"] = None
            continue
        if point.get("yoy_origin") == "issuer_reported" and point.get("yoy") is not None:
            continue
        prior = by_key.get((point["ticker"], point["kpi"], shift_year(point["period"], -1)))
        if prior is None:
            # Keep a year-over-year rate the release already stated (CME prose).
            continue
        if point.get("yoy_basis") == "percentage_points" or point.get("unit") == "share_pct":
            point["yoy_basis"] = "percentage_points"
            point["yoy"] = round(float(point["value"]) - float(prior["value"]), 4)
            continue
        base = float(prior["value"])
        if base == 0:
            point["yoy"] = None
            continue
        point["yoy_basis"] = "ratio"
        point["yoy"] = round(float(point["value"]) / base - 1.0, 6)
    return [by_key[key] for key in sorted(by_key)]


def write_ticker_store(ticker: str, points: list[dict], *, sources: list[dict], fetched_at: str) -> Path:
    # A partial release must never erase older observations or another source.
    previous = load_ticker_store(ticker) or {}
    merged = {(p["kpi"], p["period"]): p for p in previous.get("points") or []}
    revisions = list(previous.get("revisions") or [])
    for point in points:
        if point.get("ticker") != ticker or not period_end(point.get("period")):
            raise LayoutError(f"Invalid ticker/period in {ticker} observation")
        value = point.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise LayoutError(f"Non-finite operating value for {ticker}/{point.get('kpi')}")
        key = (point["kpi"], point["period"])
        old = merged.get(key)
        if old and (old.get("value"), old.get("unit")) != (value, point.get("unit")):
            revision = {"before": old, "after": point, "observed_at": fetched_at}
            if not any(r.get("before") == old and r.get("after") == point for r in revisions):
                revisions.append(revision)
        merged[key] = point
    payload = {
        "ticker": ticker,
        "schema": "magis.operating_kpis.v1",
        "fetched_at": fetched_at,
        "sources": list({json.dumps(row, sort_keys=True): row for row in
                         [*(previous.get("sources") or []), *sources]}.values()),
        "points": attach_yoy(list(merged.values())),
        "revisions": revisions,
        "conflicts": previous.get("conflicts") or [],
    }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = STORE_DIR / f"{ticker}.json"
    write_json_if_changed(path, payload, ignore_keys={"fetched_at"})
    return path


def load_ticker_store(ticker: str) -> dict | None:
    path = STORE_DIR / f"{ticker}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_stores() -> list[dict]:
    if not STORE_DIR.is_dir():
        return []
    out = []
    for path in sorted(STORE_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("points"):
            out.append(doc)
    return out
