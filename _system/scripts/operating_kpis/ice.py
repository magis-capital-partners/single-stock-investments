"""ICE monthly statistics release.

The press release states year-over-year rates. Contract levels live in the
monthly statistics spreadsheet on the IR site, which answers this environment
with HTTP 403. This parser records a level only when the release states one,
and otherwise returns no points rather than inventing a volume.
"""
from __future__ import annotations

import re

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point, month_period

CANDIDATE_URLS = (
    "https://ir.theice.com/press/news-details",
    "https://ir.theice.com/ir-resources/supplemental-information",
)

_LEVEL = re.compile(
    r"(?P<label>Total|Total Energy|Total Oil|Brent|Natural Gas|Total Financials|"
    r"Total Interest Rates|NYSE Equity Options) average daily volume \(ADV\)"
    r"(?: of| was|:)?\s+(?P<level>[\d.]+)\s+million",
    re.I,
)
_YOY_ONLY = re.compile(
    r"(?P<label>Total average daily volume \(ADV\)|Total Energy ADV|Total Oil ADV|"
    r"Total Financials ADV|Total Interest Rates ADV|NYSE Equity Options ADV)"
    r"\s+up\s+(?P<pct>[\d.]+)\s*%",
    re.I,
)


def parse_ice_release(
    text: str,
    *,
    source_url: str,
    doc: str,
    fetched_at: str,
) -> tuple[list[dict], str | None]:
    """Return points and a note when the release has rates but no levels."""
    period = None
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        text,
    )
    if match:
        period = month_period(f"{match.group(1)} {match.group(2)}")
    if not period:
        raise LayoutError("ICE release has no month and year")

    points = []
    for found in _LEVEL.finditer(text):
        label = found.group("label").lower().replace(" ", "_")
        points.append(
            make_point(
                ticker="ICE",
                kpi=f"{label}_adv" if not label.endswith("adv") else label,
                period=period,
                value=round(float(found.group("level")) * 1_000_000, 2),
                unit="contracts_per_day",
                source_url=source_url,
                doc=doc,
                fetched_at=fetched_at,
            )
        )
    note = None
    if not points and _YOY_ONLY.search(text):
        note = (
            "ICE monthly release states year-over-year rates only. "
            "Contract levels are in the monthly statistics spreadsheet on "
            "ir.theice.com, which was not readable."
        )
    return points, note


def fetch_ice(fetched_at: str) -> tuple[list[dict], list[dict]]:
    notes = []
    for url in CANDIDATE_URLS:
        status, body, err = http_get(url, timeout=20)
        if status != 200:
            notes.append({
                "ticker": "ICE",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": err or "ICE statistics page was not readable",
            })
            continue
        text = body.decode("utf-8", errors="replace")
        try:
            points, note = parse_ice_release(text, source_url=url, doc=url, fetched_at=fetched_at)
        except LayoutError as exc:
            notes.append({
                "ticker": "ICE",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": str(exc),
            })
            continue
        if not points:
            notes.append({
                "ticker": "ICE",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": note or "release had no ADV levels",
            })
            continue
        return points, [{"ticker": "ICE", "status": "ok", "source_url": url}]
    return [], notes
