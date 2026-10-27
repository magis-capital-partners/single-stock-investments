"""Cboe monthly volume statistics workbook.

The IR news HTML is behind a bot wall from datacenter addresses. The same
figures are published as an xlsx on Cboe's CDN, linked from
https://www.cboe.com/us/options/market_statistics/monthly_volume_rpc_reports/.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point, month_period, parse_number
from operating_kpis.xlsx_grid import read_sheet

PAGE_URL = "https://www.cboe.com/us/options/market_statistics/monthly_volume_rpc_reports/"
XLSX_HREF = re.compile(
    r"https://cdn\.cboe\.com/resources/investor_relations/revenue_per_contract/"
    r"[^\"'\s]*Monthly-Volume-Statistics[^\"'\s]*\.xlsx",
    re.I,
)

# (section, label prefix) -> kpi, unit, scale, yoy basis.
# Longer prefixes are matched first inside a section.
ROW_SPECS: dict[str, list[tuple[str, str, str, float, str]]] = {
    "adv": [
        ("Multiply-listed options", "options_multilist_adv", "contracts_per_day", 1000.0, "ratio"),
        ("Index options", "options_index_adv", "contracts_per_day", 1000.0, "ratio"),
        ("Futures - ADV", "futures_adv", "contracts_per_day", 1000.0, "ratio"),
        ("U.S. Equities - Exchange - ADV", "us_equities_adv", "shares_per_day", 1_000_000_000.0, "ratio"),
    ],
    "share": [
        ("Multiply-listed options", "options_multilist_share", "share_pct", 100.0, "percentage_points"),
        ("U.S. Equities - Exchange", "us_equities_share", "share_pct", 100.0, "percentage_points"),
    ],
    "rpc": [
        ("Multiply-listed options", "options_multilist_rpc", "usd_per_contract", 1.0, "ratio"),
        ("Index options", "options_index_rpc", "usd_per_contract", 1.0, "ratio"),
        ("Futures - per contract", "futures_rpc", "usd_per_contract", 1.0, "ratio"),
    ],
    "index": [
        ("SPX options", "spx_options_adv", "contracts_per_day", 1000.0, "ratio"),
        ("VIX futures", "vix_futures_adv", "contracts_per_day", 1000.0, "ratio"),
    ],
}


def discover_xlsx_urls(page_html: str) -> list[str]:
    seen: set[str] = set()
    out = []
    for match in XLSX_HREF.finditer(page_html):
        url = match.group(0).replace("&amp;", "&")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def december_url(year: int) -> str:
    return (
        "https://cdn.cboe.com/resources/investor_relations/revenue_per_contract/"
        f"December-{year}-Monthly-Volume-Statistics-Xlsx-.xlsx"
    )


def _section_for(label: str, current: str) -> str:
    if label.startswith("ADV/ADNV"):
        return "adv"
    if label.startswith("Market Share"):
        return "share"
    if label.startswith("Rolling Three-Month"):
        return "rpc"
    if label.startswith("ADV for Select"):
        return "index"
    return current


def _match_spec(section: str, label: str) -> tuple[str, str, float, str] | None:
    if label.startswith("Mini "):
        return None
    for prefix, kpi, unit, scale, basis in ROW_SPECS.get(section) or []:
        if label.startswith(prefix):
            # "U.S. Equities - Exchange" must not swallow the off-exchange row.
            if prefix == "U.S. Equities - Exchange" and "Off-Exchange" in label:
                continue
            return kpi, unit, scale, basis
    return None


def parse_cboe_xlsx(
    raw: bytes,
    *,
    source_url: str,
    doc: str,
    fetched_at: str,
) -> list[dict]:
    rows = read_sheet(raw)
    if not rows:
        raise LayoutError(f"Cboe workbook {doc} has no grid")
    header_index = None
    columns: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        periods = []
        for col, cell in enumerate(row):
            period = month_period(str(cell))
            if period and re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", str(cell), re.I):
                # Quarter labels such as 1Q26 are not month_period matches of Jan-26.
                if re.fullmatch(r"[A-Za-z]{3}-\d{2}", str(cell).strip()):
                    periods.append((col, period))
        if len(periods) >= 6:
            header_index = index
            columns = periods
            break
    if header_index is None:
        raise LayoutError(f"Cboe workbook {doc} has no Jan-YY header row")

    section = ""
    points: list[dict] = []
    seen: set[str] = set()
    for row in rows[header_index + 1 :]:
        label = str(row[0] or "").strip()
        if not label:
            continue
        section = _section_for(label, section)
        spec = _match_spec(section, label)
        if spec is None:
            continue
        kpi, unit, scale, basis = spec
        seen.add(kpi)
        for col, period in columns:
            if col >= len(row):
                continue
            number = parse_number(row[col])
            if number is None:
                continue
            scaled = number * scale
            if unit in {"contracts_per_day", "shares_per_day", "contracts"}:
                scaled = float(round(scaled))
            else:
                scaled = round(scaled, 6)
            points.append(
                make_point(
                    ticker="CBOE",
                    kpi=kpi,
                    period=period,
                    value=scaled,
                    unit=unit,
                    source_url=source_url,
                    doc=doc,
                    fetched_at=fetched_at,
                    yoy_basis=basis,
                )
            )
    if "options_multilist_adv" not in seen:
        raise LayoutError(f"Cboe workbook {doc} has no multiply-listed options ADV row")
    return points


def fetch_cboe(fetched_at: str) -> tuple[list[dict], list[dict]]:
    status, body, err = http_get(PAGE_URL)
    if status != 200:
        return [], [{
            "ticker": "CBOE",
            "status": "blocked",
            "source_url": PAGE_URL,
            "http_status": status,
            "note": err or "Cboe volume page was not readable",
        }]
    html = body.decode("utf-8", errors="replace")
    urls = discover_xlsx_urls(html)
    year = datetime.now(timezone.utc).year
    prior = december_url(year - 1)
    if prior not in urls:
        urls.append(prior)
    points: list[dict] = []
    sources = []
    for url in urls:
        file_status, raw, file_err = http_get(url)
        doc = url.rsplit("/", 1)[-1]
        if file_status != 200 or not raw.startswith(b"PK"):
            sources.append({
                "ticker": "CBOE",
                "status": "blocked",
                "source_url": url,
                "http_status": file_status,
                "note": file_err or "response was not an xlsx",
            })
            continue
        points.extend(parse_cboe_xlsx(raw, source_url=url, doc=doc, fetched_at=fetched_at))
        sources.append({"ticker": "CBOE", "status": "ok", "source_url": url, "doc": doc})
    if not points:
        raise LayoutError("Cboe volume workbooks produced no points")
    return points, sources
