#!/usr/bin/env python3
"""Dated public fund portfolios and issuer ownership registers, independent of 13F.

Fetch mutable feeds afresh; keep every dated snapshot and original response in
the private vault. A content-addressed receipt makes publication reproducible.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import time
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from investor_history import ROOT, now, write_json

SOURCES = ROOT / "_system/reference/investors/public_holdings_sources.json"
RECEIPT = ROOT / "dashboard/data/holdings/public_sources_receipt.json"


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def date(value):
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return (
                datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt)
                .date()
                .isoformat()
            )
        except ValueError:
            pass
    raise ValueError("Public disclosure has no valid explicit reporting date")


def numeric(value):
    if value is None or str(value).strip() in {"", "-", "N/A", "—"}:
        return None
    result = float(
        str(value).replace(",", "").replace("$", "").replace("%", "").strip()
    )
    if not math.isfinite(result):
        raise ValueError("Public disclosure contains a non-finite number")
    return result


def symbol(value):
    value = str(value or "").strip()
    match = re.fullmatch(r"(.+?)\s+([A-Z]{2})", value)
    if not match:
        return value, ""
    code, market = match.groups()
    if market == "US":
        return code, market
    # Bloomberg codes are not necessarily local tickers (EDEL IN, SGX SP).
    # Preserve the published identifier rather than inventing a listing symbol.
    return value, market


def fetch(source):
    url = source["url"]
    if urlparse(url).scheme != "https":
        raise ValueError("Public holdings require HTTPS")
    payload = urlencode(source["post"]).encode() if source.get("post") else None
    request = Request(
        url,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Magis Capital Research; drew@magiscapitalpartners.com)",
            "Cache-Control": "no-cache",
        },
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=40) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise ValueError("Public holdings response exceeds size limit")
                return raw
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def snapshot(source, period, rows, *, observed_at, partial=False):
    if not rows:
        raise ValueError("Public disclosure contains no identified holdings")
    return {
        "manager_id": source["manager_id"],
        "vehicle_id": source["vehicle_id"],
        "vehicle_name": source["vehicle_name"],
        "period_end": period,
        "source_kind": source["kind"],
        "source_url": source["url"],
        "publisher_url": source.get("publisher_url", source["url"]),
        "observed_at": observed_at,
        "partial": partial,
        "frequency": source.get("frequency", "daily"),
        "scope": "single_fund_disclosure",
        "positions": rows,
    }


def parse_report_table(text, source):
    """Only an explicit dated USD table with a reconciled total establishes stakes."""
    section = re.search(source["section_pattern"], text, re.IGNORECASE)
    if not section:
        return None
    block = text[section.end():]
    header = re.search(
        r"Company\s+Owned\s+Cost\s+Basis\s+Market\s+Value\s+\d{4}\s+Dividends",
        block,
    )
    if not header:
        return None
    preamble = block[:header.start()]
    if not re.search(r"\(Dollars\s+in\s+millions\)", preamble):
        raise ValueError("Annual holdings table has no verified currency and scale")
    dates = re.findall(r"[A-Z][a-z]+\s+\d{1,2},\s+\d{4}", preamble)
    if len(dates) != 1:
        raise ValueError("Annual holdings table must have one explicit reporting date")
    period = date(re.sub(r"\s+", " ", dates[0]))
    number = r"[\d,]+(?:\.\d+)?"
    row_pattern = re.compile(
        rf"(?P<issuer>\S.*?)\s+(?P<stake>\d+(?:\.\d+)?)%\s+"
        rf"\$?\s*(?P<cost>{number})\s+\$?\s*(?P<value>{number})\s+"
        rf"\$?\s*(?P<dividend>{number})"
    )
    total_pattern = re.compile(
        rf"Total\s+\$?\s*{number}\s+\$?\s*(?P<value>{number})\s+\$?\s*{number}"
    )
    rows, total = [], None
    for line in block[header.end():].splitlines():
        line = line.strip()
        summary = total_pattern.fullmatch(line)
        if summary:
            total = numeric(summary["value"]) * 1_000_000
            break
        match = row_pattern.fullmatch(line)
        if not match:
            continue
        stake = numeric(match["stake"])
        if not 0 <= stake <= 100:
            raise ValueError("Annual report issuer ownership is outside 0–100 percent")
        rows.append({
            "issuer": match["issuer"],
            "country": source["country"],
            "shares": None,
            "weight_pct": None,
            "issuer_ownership_pct": stake,
            "value_usd": numeric(match["value"]) * 1_000_000,
            "cost_basis_usd": numeric(match["cost"]) * 1_000_000,
        })
    if len(rows) < source.get("minimum_positions", 1) or total is None:
        raise ValueError("Annual report holdings table is incomplete")
    if len({row["issuer"] for row in rows}) != len(rows):
        raise ValueError("Annual report holdings table repeats an issuer")
    # Each published row and the total can have been rounded independently.
    if abs(sum(row["value_usd"] for row in rows) - total) > len(rows) * 500_000:
        raise ValueError("Annual report holdings do not reconcile to its table total")
    return period, rows


def parse_public_report(raw, source, *, observed_at):
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [
            (number, page.extract_text() or "") for number, page in enumerate(
                reader.pages[:source.get("max_pages", 35)], 1
            )
        ]
    except PyPdfError as exc:
        raise ValueError("Official report could not be read as a PDF") from exc
    matches = []
    for page_number, text in pages:
        parsed = parse_report_table(text, source)
        if parsed:
            period, rows = parsed
            if source.get("report_year") and period[:4] != str(source["report_year"]):
                raise ValueError("Annual table date does not match its published report year")
            item = snapshot(source, period, rows, observed_at=observed_at, partial=True)
            item.update(
                scope="reported_foreign_equity_stakes",
                date_basis="publisher_report_date",
                report_page=page_number,
                reporting_currency="USD",
                source_url=source["url"] + f"#page={page_number}",
                publisher_url=source["url"] + f"#page={page_number}",
            )
            matches.append(item)
    if len(matches) != 1:
        raise ValueError("Expected one uniquely identified annual holdings table")
    return matches


def parse_filepoint_csv(raw, source, *, observed_at):
    """US Bank publishes every line, including cash, zero values and foreign shares."""
    rows, dates = [], set()
    for row in csv.DictReader(
        io.StringIO(raw.decode("utf-8-sig")), skipinitialspace=True
    ):
        if row.get("Account") != source["ticker"]:
            raise ValueError("Daily feed belongs to a different fund vehicle")
        dates.add(date(row["Date"]))
        ticker, exchange = symbol(row["StockTicker"])
        rows.append(
            {
                "issuer": row["SecurityName"].strip(),
                "ticker": ticker,
                "publisher_ticker": row["StockTicker"],
                "exchange_code": exchange,
                "security_identifier": row["CUSIP"],
                "shares": numeric(row["Shares"]),
                "value_usd": numeric(row["MarketValue"]),
                "weight_pct": numeric(row["Weightings"]),
                "weight_basis": "fund_net_assets",
                "asset_category": "cash_or_money_market"
                if row.get("MoneyMarketFlag") == "Y" or row["CUSIP"].startswith("CASH")
                else None,
            }
        )
    if len(dates) != 1:
        raise ValueError("Daily CSV must contain exactly one reporting date")
    result = snapshot(source, dates.pop(), rows, observed_at=observed_at)
    result["date_basis"] = "publisher_feed_date"
    return [result]


def parse_filepoint_json(raw, source, *, observed_at):
    envelope = json.loads(raw)
    rows = envelope.get("data") if isinstance(envelope, dict) else envelope
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            "Daily feed returned no live holdings; retaining the last dated portfolio"
        )
    positions, dates = [], set()
    for row in rows:
        if str(row["portfolioNumber"]) != str(source["post"]["fundID"]):
            raise ValueError("Daily feed belongs to a different fund vehicle")
        dates.add(date(row["asOfDate"]))
        ticker, exchange = symbol(row.get("securityTicker"))
        weight = numeric(row.get("netAssetsPercent"))
        positions.append(
            {
                "issuer": row["securityDescriptionLong"],
                "ticker": ticker,
                "publisher_ticker": row.get("securityTicker"),
                "exchange_code": exchange,
                "security_identifier": row.get("securityIdentifier"),
                "shares": numeric(row.get("shares")),
                "value_usd": numeric(row.get("marketValueBase")),
                "weight_pct": weight * 100 if weight is not None else None,
                "weight_basis": "fund_net_assets",
                "currency": row.get("tradingCurrency"),
                "country": row.get("country"),
                "position_side": row.get("longShortIndicator"),
                "asset_category": row.get("segment"),
            }
        )
    if len(dates) != 1:
        raise ValueError("Daily JSON must contain exactly one reporting date")
    return [snapshot(source, dates.pop(), positions, observed_at=observed_at)]


def parse_horizon_xlsx(raw, source, *, observed_at):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as book:
        if sum(info.file_size for info in book.infolist()) > 32 * 1024 * 1024:
            raise ValueError("Holdings workbook exceeds size limit")
        strings = [
            "".join(node.itertext())
            for node in ET.fromstring(book.read("xl/sharedStrings.xml"))
        ]
        cells = ET.fromstring(book.read("xl/worksheets/sheet1.xml")).findall(
            ".//s:row", ns
        )
        rows = []
        for row in cells:
            values = {}
            for cell in row:
                column = re.sub(r"\d", "", cell.attrib["r"])
                value = cell.find("s:v", ns)
                text = value.text if value is not None else "".join(cell.itertext())
                values[column] = (
                    strings[int(text)] if cell.attrib.get("t") == "s" else text
                )
            rows.append(values)
    expected = {
        "A": "Data as of:",
        "B": "% Net Assets",
        "C": "Name",
        "D": "Ticker",
        "E": "CUSIP",
        "F": "Shares Held",
        "G": "Market Value",
    }
    if not rows or rows[0] != expected:
        raise ValueError("Daily holdings workbook headers changed")
    dates, positions = set(), []
    for row in rows[1:]:
        if not row.get("C"):
            continue
        dates.add(date(row["A"]))
        ticker, exchange = symbol(row.get("D"))
        weight = numeric(row.get("B"))
        positions.append(
            {
                "issuer": row["C"],
                "ticker": ticker,
                "publisher_ticker": row.get("D"),
                "exchange_code": exchange,
                "security_identifier": row.get("E"),
                "shares": numeric(row.get("F")),
                "value_usd": numeric(row.get("G")),
                "weight_pct": weight * 100 if weight is not None else None,
                "weight_basis": "fund_net_assets",
            }
        )
    if len(dates) != 1:
        raise ValueError("Workbook must contain exactly one reporting date")
    return [snapshot(source, dates.pop(), positions, observed_at=observed_at)]


class FlightData(HTMLParser):
    """Read Next's public serialized data without executing page JavaScript."""

    def __init__(self):
        super().__init__()
        self.in_script = False
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        self.in_script = tag == "script" or self.in_script

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)


def parse_kap(raw, source, *, observed_at):
    parser = FlightData()
    parser.feed(raw.decode("utf-8"))
    text = ""
    for script in parser.scripts:
        match = re.fullmatch(r"self\.__next_f\.push\((\[.*\])\)", script.strip(), re.S)
        if match:
            item = json.loads(match[1])
            if len(item) == 2 and item[0] == 1 and isinstance(item[1], str):
                text += item[1]
    # This is the DIRECT shareholder table. Indirect subsidiaries and voting
    # power are not a second portfolio position or fund allocation.
    marker = '"itemKey":"kpy41_acc5_sermayede_dogrudan"'
    start = text.find(marker)
    if start < 0:
        raise ValueError("KAP direct shareholder table unavailable or changed")
    values = re.search(r'"value":', text[start:])
    if not values:
        raise ValueError("KAP shareholder rows unavailable")
    shareholders, _ = json.JSONDecoder().raw_decode(text[start + values.end() :])
    if not isinstance(shareholders, list) or not shareholders:
        raise ValueError("KAP shareholder table is empty")
    normal = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    owners = {
        normal(alias): owner for owner in source["owners"] for alias in owner["names"]
    }
    output = []
    for row in shareholders:
        owner = owners.get(normal(row["shareholder"]))
        if not owner:
            continue
        local_number = lambda value: numeric(
            str(value).replace(".", "").replace(",", ".")
        )
        position = {
            "issuer": source["issuer"],
            "ticker": source["ticker"],
            "country": "TR",
            "currency": "TRY",
            "shares": None,
            "nominal_capital_try": local_number(row["shareInCapital"]),
            "issuer_ownership_pct": local_number(row["ratioInCapital"]),
            "weight_pct": None,
            "weight_basis": None,
            "value_usd": None,
        }
        item = snapshot(
            {**source, **{k: owner[k] for k in ("vehicle_id", "vehicle_name")}},
            None,
            [position],
            observed_at=observed_at,
            partial=True,
        )
        item.update(
            scope="issuer_ownership_register",
            disclosed_at=observed_at[:10],
            date_basis="register_observed_at",
            ownership_holder=row["shareholder"],
        )
        output.append(item)
    # An absent holder is not an exit. Retain previous observations and report it.
    if not output:
        raise ValueError(
            "No configured fund holder found in the direct shareholder table"
        )
    return output


PARSERS = {
    "filepoint_csv": parse_filepoint_csv,
    "filepoint_json": parse_filepoint_json,
    "issuer_ownership": parse_kap,
    "horizon_xlsx": parse_horizon_xlsx,
    "annual_report_pdf": parse_public_report,
}


def collect(sources, archive, *, fetcher=fetch, observed_at=None):
    observed_at = observed_at or now()
    documents, review = [], []
    expanded = []
    for source in sources:
        if source["kind"] not in {"horizon_family", "annual_report_family"}:
            expanded.append(source)
            continue
        try:
            raw = fetcher(source)
            if source["kind"] == "annual_report_family":
                years = [
                    int(year) for year in re.findall(
                        source["annual_link_pattern"], raw.decode("utf-8")
                    ) if int(year) >= source["first_year"]
                ]
                if not years:
                    raise ValueError("No current official annual report discovered")
                expanded.append({
                    **source,
                    "kind": "annual_report_pdf",
                    "report_year": max(years),
                    "publisher_url": source["url"],
                    "url": source["report_url_template"].format(year=max(years)),
                })
                continue
            tickers = sorted(
                set(
                    re.findall(
                        r"https://horizonkinetics\.com/products/etf/([a-z0-9]+)/",
                        raw.decode("utf-8"),
                    )
                )
            )
            if not tickers:
                raise ValueError("No public Horizon ETF vehicles discovered")
            for ticker in tickers:
                expanded.append(
                    {
                        **source,
                        "kind": "horizon_xlsx",
                        "ticker": ticker.upper(),
                        "vehicle_id": "horizon-etf-" + ticker.upper(),
                        "vehicle_name": "Horizon Kinetics " + ticker.upper() + " ETF",
                        "publisher_url": f"https://horizonkinetics.com/products/etf/{ticker}/",
                        "url": "https://horizonkinetics.com/wp/wp-admin/admin-ajax.php?"
                        + urlencode(
                            {
                                "action": "daily_holdings",
                                "prefix": "Holdings",
                                "ticker": ticker.upper(),
                            }
                        ),
                    }
                )
        except (OSError, ValueError) as exc:
            review.append(
                {
                    "manager_id": source["manager_id"],
                    "source_url": source["url"],
                    "reason": str(exc),
                    "observed_at": observed_at,
                }
            )
    for source in expanded:
        try:
            raw = fetcher(source)
            parsed = PARSERS[source["kind"]](raw, source, observed_at=observed_at)
            sha = digest(raw)
            original = archive / "raw" / f"{sha}.gz"
            original.parent.mkdir(parents=True, exist_ok=True)
            if not original.exists():
                original.write_bytes(gzip.compress(raw, mtime=0))
            for document in parsed:
                document["source_sha256"] = sha
                # One revision per fund/source/date; corrections replace only
                # that exact snapshot. Distinct vehicles are never combined.
                key = [
                    document["manager_id"],
                    document["vehicle_id"],
                    source["url"],
                    document.get("period_end") or observed_at[:10],
                ]
                document["id"] = digest(canonical(key))[:24]
                documents.append(document)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            zipfile.BadZipFile,
            ET.ParseError,
            ImportError,
        ) as exc:
            review.append(
                {
                    "manager_id": source["manager_id"],
                    "source_url": source["url"],
                    "vehicle_name": source["vehicle_name"],
                    "observed_at": observed_at,
                    "reason": str(exc),
                }
            )
    return documents, review


def load(archive, receipt):
    if not receipt.is_file():
        return {"disclosures": [], "review": []}
    pointer = json.loads(receipt.read_text(encoding="utf-8"))
    identity = pointer["identity"]
    if not re.fullmatch("[0-9a-f]{64}", identity):
        raise ValueError("Invalid public holdings archive identity")
    raw = gzip.decompress((archive / "snapshots" / f"{identity}.json.gz").read_bytes())
    if digest(raw) != identity:
        raise ValueError("Public holdings archive checksum mismatch")
    return json.loads(raw)


def save(archive, receipt, previous, current, review):
    merged = {(d["manager_id"], d["id"]): d for d in previous + current}
    payload = {
        "schema_version": 1,
        "disclosures": sorted(
            merged.values(), key=lambda d: (d["manager_id"], d["id"])
        ),
        "review": review,
    }
    raw = canonical(payload)
    identity = digest(raw)
    path = archive / "snapshots" / f"{identity}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0))
    write_json(
        receipt, {"schema_version": 1, "identity": identity, "snapshots": len(merged)}
    )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    previous = load(args.archive, args.receipt)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    current, review = collect(sources, args.archive)
    result = save(args.archive, args.receipt, previous["disclosures"], current, review)
    print(
        json.dumps(
            {
                "fetched": len(current),
                "retained": len(result["disclosures"]),
                "review": review,
            }
        )
    )
    if not current:
        raise SystemExit("No public source succeeded; previous portfolios retained")


if __name__ == "__main__":
    main()
