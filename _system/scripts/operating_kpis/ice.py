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


def _fetch_legacy_ice(fetched_at: str) -> tuple[list[dict], list[dict]]:
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


# Source discovery and row definitions ported from the dated Magis mirror.
FEED = ("https://ir.theice.com/feed/ContentAsset.svc/GetContentAssetList?apiKey=BF185719B0464B3CB809D23926182246"
        "&LanguageId=1&assetType=&pageSize=-1&pageNumber=0&tagList=&includeTags=true&year=-1&excludeSelection=1")
DERIV = {  # (col A label stripped, col B label stripped or None) -> kpi, unit ; block = ADV/RPC/OI
    ("ADV", "TOTAL ENERGY", None): ("adv_energy", "contracts_k"),
    ("ADV", None, "Brent (1)"): ("adv_brent", "contracts_k"),
    ("ADV", None, "Nat Gas (4)"): ("adv_natgas", "contracts_k"),
    ("ADV", "TOTAL AGRICULTURE & METALS", None): ("adv_ag_metals", "contracts_k"),
    ("ADV", "TOTAL COMMODITIES", None): ("adv_commodities", "contracts_k"),
    ("ADV", "Interest Rates", "Short-term Interest Rates (9)"): ("adv_stir", "contracts_k"),
    ("ADV", "TOTAL FINANCIALS", None): ("adv_financials", "contracts_k"),
    ("ADV", "TOTAL FUTURES & OPTIONS", None): ("adv_total_fo", "contracts_k"),
    ("RPC", "Energy", None): ("rpc3m_energy", "usd_per_contract"),
    ("RPC", "Agriculture & Metals", None): ("rpc3m_ag_metals", "usd_per_contract"),
    ("RPC", "TOTAL COMMODITIES", None): ("rpc3m_commodities", "usd_per_contract"),
    ("RPC", "Interest Rates", None): ("rpc3m_interest_rates", "usd_per_contract"),
    ("RPC", "TOTAL FINANCIALS", None): ("rpc3m_financials", "usd_per_contract"),
    ("OI", "TOTAL COMMODITIES", None): ("oi_commodities", "contracts_k"),
    ("OI", "TOTAL FINANCIALS", None): ("oi_financials", "contracts_k"),
}
REQUIRED = {"adv_total_fo", "adv_energy", "rpc3m_energy", "rpc3m_financials"}


def _period(value: str) -> str | None:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value[:7]
    quarter = re.fullmatch(r"([1-4])Q(\d{2})", value.strip())
    return f"20{quarter.group(2)}Q{quarter.group(1)}" if quarter else month_period(value)


def parse_ice_xlsx(raw: bytes, *, source_url: str, doc: str, fetched_at: str) -> list[dict]:
    import io
    import zipfile
    from operating_kpis.xlsx_grid import read_sheet, sheet_names
    from operating_kpis.model import parse_number

    with zipfile.ZipFile(io.BytesIO(raw)) as book:
        names = [name for name, _ in sheet_names(book)]
    derivatives = next((name for name in names if name.startswith("Derivs")), None)
    if not derivatives:
        raise LayoutError("ICE workbook has no Derivs sheet")
    out, found = [], set()
    for sheet in [derivatives, *(["US Equity Options"] if "US Equity Options" in names else [])]:
        columns, block = {}, None
        for row in read_sheet(raw, sheet_name=sheet):
            periods = {i: _period(value) for i, value in enumerate(row) if _period(value)}
            if len(periods) >= 3:
                columns = periods
                continue
            a, b = (row + ["", ""])[:2]
            a, b = a.strip(), b.strip()
            if "Monthly ADV" in a:
                block = "ADV"
            elif "Rate per Contract" in a:
                block = "RPC"
            elif a.endswith("Derivatives OI"):
                block = "OI"
            specs = []
            if sheet == "US Equity Options":
                spec = {"US Equity Options": ("nyse_options_adv", "contracts_k"),
                        "NYSE Share of Group Total": ("nyse_options_share", "share")}.get(a or b)
                if spec:
                    specs = [spec]
            else:
                for (section, label_a, label_b), spec in DERIV.items():
                    if section != block or (label_a is not None and a != label_a) or (label_b is not None and b != label_b):
                        continue
                    if label_a and label_b is None and b and block == "ADV" and not a.startswith("TOTAL"):
                        continue
                    specs.append(spec)
            for kpi, source_unit in specs:
                for index, period in columns.items():
                    value = parse_number(row[index]) if index < len(row) else None
                    if value is None:
                        continue
                    unit = source_unit
                    if source_unit == "contracts_k":
                        value *= 1000
                        unit = "contracts" if kpi.startswith("oi_") else "contracts_per_day"
                    elif source_unit == "share":
                        value *= 100
                        unit = "share_pct"
                    if kpi == "rpc3m_energy" and not 0.3 < value < 5:
                        raise LayoutError(f"ICE implausible energy RPC {value}")
                    point = make_point(ticker="ICE", kpi=kpi, period=period, value=value, unit=unit,
                                       source_url=source_url, doc=doc, fetched_at=fetched_at,
                                       yoy_basis="percentage_points" if unit == "share_pct" else "ratio")
                    point["source_unit"] = source_unit
                    point["measurement_basis"] = "rolling_three_months" if kpi.startswith("rpc3m_") else "period"
                    out.append(point)
                    found.add(kpi)
    if REQUIRED - found:
        raise LayoutError(f"ICE required rows missing: {sorted(REQUIRED - found)}")
    return out


def fetch_ice(fetched_at: str) -> tuple[list[dict], list[dict]]:
    import json
    status, body, error = http_get(FEED, timeout=30)
    if status != 200:
        return [], [{"ticker": "ICE", "status": "blocked", "source_url": FEED, "note": error}]
    assets = json.loads(body).get("GetContentAssetListResult", [])
    assets = [a for a in assets if "Monthly Statistics" in a.get("Title", "") and a.get("FilePath", "").endswith(".xlsx")]
    if not assets:
        raise LayoutError("ICE Monthly Statistics workbook missing from content feed")
    url = max(assets, key=lambda a: a.get("ContentAssetDate") or "")["FilePath"]
    status, body, error = http_get(url, timeout=30)
    if status != 200:
        return [], [{"ticker": "ICE", "status": "blocked", "source_url": url, "note": error}]
    points = parse_ice_xlsx(body, source_url=url, doc=url.rsplit("/", 1)[-1], fetched_at=fetched_at)
    return points, [{"ticker": "ICE", "status": "ok", "source_url": url}]
