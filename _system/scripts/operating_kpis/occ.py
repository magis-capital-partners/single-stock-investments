"""OCC monthly cleared-volume files.

Industry equity, ETF, and index option totals. The public batch file is CSV:

    https://marketdata.theocc.com/monthly-volume-reports
        ?reportDate=YYYYMMDD&reportType=options&reportClass=equity&format=csv

Equity plus ETF average daily volume is the industry pie MIAX quotes.
"""
from __future__ import annotations

import calendar
import csv
import io
import re
from datetime import date

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point

BATCH_URL = (
    "https://marketdata.theocc.com/monthly-volume-reports"
    "?reportDate={date}&reportType=options&reportClass={kind}&format=csv"
)
CLASSES = ("equity", "etf", "index")


def _side_totals(text: str, side: str) -> tuple[float, float]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == side:
            start = index
            break
    if start is None:
        raise LayoutError(f"OCC file has no {side} section")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip() in {"Calls", "Puts"} and index != start:
            end = index
            break
        if lines[index].startswith("Monthly Totals"):
            end = index
            break
    chunk = "\n".join(lines[start:end])
    for row in csv.reader(io.StringIO(chunk)):
        if not row or not row[0].startswith("OCC-TOTL"):
            continue
        if len(row) < 6:
            raise LayoutError("OCC-TOTL row is shorter than the volume header")
        contracts = float(row[1].replace(",", ""))
        adv = float(row[5].replace(",", ""))
        return contracts, adv
    raise LayoutError(f"OCC {side} section has no OCC-TOTL row")


def parse_occ_csv(
    text: str,
    *,
    kind: str,
    period: str,
    source_url: str,
    fetched_at: str,
) -> dict[str, float]:
    activity = re.search(r"ACTIVITY DATE\s*:\s*(\d{2})/(\d{2})/(\d{4})", text)
    if activity:
        period = f"{activity.group(3)}-{activity.group(1)}"
    calls_contracts, calls_adv = _side_totals(text, "Calls")
    puts_contracts, puts_adv = _side_totals(text, "Puts")
    return {
        "period": period,
        "contracts": calls_contracts + puts_contracts,
        "adv": calls_adv + puts_adv,
        "kind": kind,
        "source_url": source_url,
    }


def points_from_months(
    months: list[dict],
    *,
    fetched_at: str,
) -> list[dict]:
    """``months`` items are the dicts from ``parse_occ_csv``."""
    by_period: dict[str, dict[str, dict]] = {}
    for item in months:
        by_period.setdefault(item["period"], {})[item["kind"]] = item
    points = []
    for period, kinds in sorted(by_period.items()):
        for kind, item in kinds.items():
            points.append(
                make_point(
                    ticker="OCC",
                    kpi=f"{kind}_options_contracts",
                    period=period,
                    value=item["contracts"],
                    unit="contracts",
                    source_url=item["source_url"],
                    doc=f"occ-{kind}-{period}.csv",
                    fetched_at=fetched_at,
                )
            )
            points.append(
                make_point(
                    ticker="OCC",
                    kpi=f"{kind}_options_adv",
                    period=period,
                    value=item["adv"],
                    unit="contracts_per_day",
                    source_url=item["source_url"],
                    doc=f"occ-{kind}-{period}.csv",
                    fetched_at=fetched_at,
                )
            )
        if "equity" in kinds and "etf" in kinds:
            points.append(
                make_point(
                    ticker="OCC",
                    kpi="equity_etf_options_adv",
                    period=period,
                    value=kinds["equity"]["adv"] + kinds["etf"]["adv"],
                    unit="contracts_per_day",
                    source_url=kinds["equity"]["source_url"],
                    doc=f"occ-equity-etf-{period}.csv",
                    fetched_at=fetched_at,
                )
            )
    return points


def _month_ends(today: date, *, months: int) -> list[tuple[str, str]]:
    """Last ``months`` calendar months, newest last, as (YYYY-MM, YYYYMMDD)."""
    year, month = today.year, today.month
    # The current month's OCC file is published in the first days of the next
    # month. Try it, and always try the prior months.
    pairs = []
    y, m = year, month
    for _ in range(months):
        last = calendar.monthrange(y, m)[1]
        pairs.append((f"{y:04d}-{m:02d}", f"{y:04d}{m:02d}{last:02d}"))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    pairs.reverse()
    return pairs


def fetch_occ(fetched_at: str, *, months: int = 21, today: date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or date.today()
    parsed = []
    sources = []
    failures = 0
    for period, stamp in _month_ends(today, months=months):
        for kind in CLASSES:
            url = BATCH_URL.format(date=stamp, kind=kind)
            status, body, err = http_get(url)
            if status != 200 or b"OCC-TOTL" not in body:
                failures += 1
                if failures <= 6:
                    sources.append({
                        "ticker": "OCC",
                        "status": "blocked",
                        "source_url": url,
                        "http_status": status,
                        "note": err or f"no OCC-TOTL in {kind} {period}",
                    })
                continue
            item = parse_occ_csv(
                body.decode("utf-8", errors="replace"),
                kind=kind,
                period=period,
                source_url=url,
                fetched_at=fetched_at,
            )
            parsed.append(item)
    if not parsed:
        return [], sources or [{
            "ticker": "OCC",
            "status": "blocked",
            "source_url": BATCH_URL,
            "note": "OCC monthly volume files were not readable",
        }]
    sources.insert(0, {
        "ticker": "OCC",
        "status": "ok",
        "source_url": "https://marketdata.theocc.com/monthly-volume-reports",
        "note": f"{len(parsed)} class-months",
    })
    return points_from_months(parsed, fetched_at=fetched_at), sources
