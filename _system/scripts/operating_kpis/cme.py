"""CME monthly market-statistics press release.

The release states asset-class ADV and the year-over-year change in prose.
cmegroup.com answers this environment with HTTP 403, so the live fetcher
records a block and the parser is locked to a fixture.
"""
from __future__ import annotations

import re

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point, month_period

# Tried in order. The slug changes every month; the listing page is the
# discovery path when it is not blocked.
CANDIDATE_URLS = (
    "https://cmegroupinc.gcs-web.com/news-releases",
    "https://www.cmegroup.com/media-room/press-releases.html",
)

_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "total_adv",
        "contracts_per_day",
        re.compile(
            r"with\s+([\d.]+)\s+million contracts,\s+up\s+([\d.]+)\s*%",
            re.I,
        ),
    ),
    (
        "interest_rate_adv",
        "contracts_per_day",
        re.compile(
            r"Interest Rate ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "equity_index_adv",
        "contracts_per_day",
        re.compile(
            r"Equity Index ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "energy_adv",
        "contracts_per_day",
        re.compile(
            r"Energy ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "agricultural_adv",
        "contracts_per_day",
        re.compile(
            r"Agricultural ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "fx_adv",
        "contracts_per_day",
        re.compile(
            r"Foreign Exchange ADV increased\s+([\d.]+)\s*%\s+to\s+([\d.]+)\s+million",
            re.I,
        ),
    ),
    (
        "metals_adv",
        "contracts_per_day",
        re.compile(r"Metals ADV of\s+([\d.]+)\s+million", re.I),
    ),
)


def parse_cme_release(
    text: str,
    *,
    source_url: str,
    doc: str,
    fetched_at: str,
) -> list[dict]:
    period = None
    for match in re.finditer(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        text,
    ):
        period = month_period(f"{match.group(1)} {match.group(2)}")
        if period:
            break
    if not period:
        raise LayoutError("CME release has no month and year")
    points = []
    for kpi, unit, pattern in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        if kpi == "total_adv":
            level, yoy_pct = float(groups[0]), float(groups[1])
        elif kpi == "metals_adv":
            level, yoy_pct = float(groups[0]), None
        else:
            yoy_pct, level = float(groups[0]), float(groups[1])
        point = make_point(
            ticker="CME",
            kpi=kpi,
            period=period,
            value=round(level * 1_000_000, 2),
            unit=unit,
            source_url=source_url,
            doc=doc,
            fetched_at=fetched_at,
            yoy_basis="ratio",
        )
        if yoy_pct is not None:
            point["yoy"] = round(yoy_pct / 100.0, 6)
        points.append(point)
    if not any(point["kpi"] == "total_adv" for point in points):
        raise LayoutError("CME release has no total ADV sentence")
    return points


def fetch_cme(fetched_at: str) -> tuple[list[dict], list[dict]]:
    notes = []
    for url in CANDIDATE_URLS:
        status, body, err = http_get(url, timeout=20)
        if status != 200:
            notes.append({
                "ticker": "CME",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": err or "CME volume page was not readable",
            })
            continue
        text = body.decode("utf-8", errors="replace")
        try:
            points = parse_cme_release(text, source_url=url, doc=url, fetched_at=fetched_at)
        except LayoutError as exc:
            notes.append({
                "ticker": "CME",
                "status": "blocked",
                "source_url": url,
                "http_status": status,
                "note": str(exc),
            })
            continue
        return points, [{"ticker": "CME", "status": "ok", "source_url": url}]
    return [], notes
