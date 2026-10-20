"""MIAX monthly Volume & RPC report.

Primary source: the PDF linked from https://ir.miaxglobal.com/volume-rpc-reports.
MIAX does not file these statistics on an 8-K. The parser takes ``pdftotext
-layout`` text so tests never need the PDF or the network.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from operating_kpis.http_util import http_get
from operating_kpis.model import LayoutError, make_point, month_period, parse_number

INDEX_URL = "https://ir.miaxglobal.com/volume-rpc-reports"
PDF_HREF = re.compile(r'href="(image/MIH_Volume_and_RPC_Report[^"]+\.pdf)"', re.I)
MONTH_TOKEN = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}\b")
STOP_TOKEN = re.compile(r"\bQ[1-4]\b|\bYear\b")
VALUE_TOKEN = re.compile(
    r"\((?:\$)?-?[\d,]+(?:\.\d+)?\)%?|(?:\$)?-?[\d,]+(?:\.\d+)?%?|\bn/a\b",
    re.I,
)


def pdf_bytes_to_text(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(pdf_bytes)
        handle.flush()
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", handle.name, "-"],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LayoutError(
                "pdftotext is not installed. The nightly job installs poppler-utils "
                "before fetch_operating_kpis.py."
            ) from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace")[:400]
        raise LayoutError(f"pdftotext failed: {detail}")
    return proc.stdout.decode("utf-8", errors="replace")


def _month_columns(header: str) -> list[tuple[int, int, str]]:
    found = list(MONTH_TOKEN.finditer(header))
    if len(found) < 6:
        return []
    stop = None
    for match in STOP_TOKEN.finditer(header):
        if match.start() > found[-1].start():
            stop = match.start()
            break
    columns = []
    for index, match in enumerate(found):
        period = month_period(match.group())
        if not period:
            continue
        end = found[index + 1].start() if index + 1 < len(found) else (stop or match.end() + 12)
        if stop is not None:
            end = min(end, stop)
        columns.append((match.start(), end, period))
    return columns


def _row_values(line: str, columns: list[tuple[int, int, str]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for match in VALUE_TOKEN.finditer(line):
        number = parse_number(match.group())
        if number is None:
            continue
        for start, end, period in columns:
            if start - 1 <= match.start() < end:
                values[period] = number
                break
    return values


def _classify(line: str, section: str, subsection: str) -> tuple[str, str, float, str] | None:
    label = line.strip()
    if section == "options":
        if label.startswith("Industry ADV"):
            return "options_industry_adv", "contracts_per_day", 1000.0, "ratio"
        if label.startswith("MIH ADV"):
            return "options_adv", "contracts_per_day", 1000.0, "ratio"
        if label.startswith("MIH market share"):
            return "options_share", "share_pct", 1.0, "percentage_points"
        if "average RPC" in label:
            return "options_rpc", "usd_per_contract", 1.0, "ratio"
    if section == "equities":
        if label.startswith("Industry ADV"):
            return "equities_industry_adv", "shares_per_day", 1_000_000.0, "ratio"
        if label.startswith("MIH ADV"):
            return "equities_adv", "shares_per_day", 1_000_000.0, "ratio"
        if label.startswith("MIH market share"):
            return "equities_share", "share_pct", 1.0, "percentage_points"
        if "capture" in label.lower():
            return "equities_capture", "usd_per_100_shares", 1.0, "ratio"
    if section == "futures" and "from launch" not in label.lower():
        if subsection == "ag" and label.startswith("MIH - ADV"):
            return "futures_ag_adv", "contracts_per_day", 1.0, "ratio"
        if subsection == "ag" and "average RPC" in label:
            return "futures_ag_rpc", "usd_per_contract", 1.0, "ratio"
        if subsection == "financial" and label.startswith("MIH - ADV"):
            return "futures_financial_adv", "contracts_per_day", 1.0, "ratio"
        if subsection == "financial" and "average RPC" in label:
            return "futures_financial_rpc", "usd_per_contract", 1.0, "ratio"
    return None


def parse_miax_text(
    text: str,
    *,
    source_url: str,
    doc: str,
    fetched_at: str,
) -> list[dict]:
    lines = text.splitlines()
    columns: list[tuple[int, int, str]] = []
    for line in lines:
        found = _month_columns(line)
        if len(found) >= 6:
            columns = found
            break
    if not columns:
        raise LayoutError("MIAX volume report has no Jan-YY month header")

    section = ""
    subsection = ""
    points: list[dict] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Options (Equity"):
            section, subsection = "options", ""
            continue
        if stripped.startswith("U.S. Equities"):
            section, subsection = "equities", ""
            continue
        if stripped.startswith("Futures"):
            section, subsection = "futures", ""
            continue
        if section == "futures" and stripped.startswith("Agricultural"):
            subsection = "ag"
            continue
        if section == "futures" and stripped.startswith("Financial"):
            subsection = "financial"
            continue
        spec = _classify(line, section, subsection)
        if spec is None:
            continue
        kpi, unit, scale, basis = spec
        values = _row_values(line, columns)
        if not values:
            raise LayoutError(f"MIAX row {kpi} matched a label but no month columns")
        seen.add(kpi)
        for period, raw in values.items():
            points.append(
                make_point(
                    ticker="MIAX",
                    kpi=kpi,
                    period=period,
                    value=round(raw * scale, 6),
                    unit=unit,
                    source_url=source_url,
                    doc=doc,
                    fetched_at=fetched_at,
                    yoy_basis=basis,
                )
            )
    if "options_adv" not in seen or "options_share" not in seen:
        raise LayoutError(
            "MIAX volume report is missing options ADV or market share. "
            f"Parsed rows: {sorted(seen) or 'none'}."
        )
    return points


def discover_pdf_urls(index_html: str) -> list[str]:
    urls = []
    for match in PDF_HREF.finditer(index_html):
        href = match.group(1)
        if href.startswith("http"):
            urls.append(href)
        else:
            urls.append("https://ir.miaxglobal.com/" + href.lstrip("/"))
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    out = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def parse_pdf_file(path: Path, *, source_url: str, fetched_at: str) -> list[dict]:
    text = pdf_bytes_to_text(path.read_bytes())
    return parse_miax_text(text, source_url=source_url, doc=path.name, fetched_at=fetched_at)


def fetch_miax(fetched_at: str) -> tuple[list[dict], list[dict]]:
    status, body, err = http_get(INDEX_URL)
    if status != 200:
        return [], [{
            "ticker": "MIAX",
            "status": "blocked",
            "source_url": INDEX_URL,
            "http_status": status,
            "note": err or "volume-rpc index was not readable",
        }]
    html = body.decode("utf-8", errors="replace")
    urls = discover_pdf_urls(html)
    if not urls:
        raise LayoutError("MIAX volume-rpc page linked no Volume and RPC PDFs")
    points: list[dict] = []
    sources = []
    for url in urls:
        pdf_status, pdf_body, pdf_err = http_get(url)
        doc = url.rsplit("/", 1)[-1]
        if pdf_status != 200 or not pdf_body.startswith(b"%PDF"):
            sources.append({
                "ticker": "MIAX",
                "status": "blocked",
                "source_url": url,
                "http_status": pdf_status,
                "note": pdf_err or "response was not a PDF",
            })
            continue
        text = pdf_bytes_to_text(pdf_body)
        points.extend(parse_miax_text(text, source_url=url, doc=doc, fetched_at=fetched_at))
        sources.append({"ticker": "MIAX", "status": "ok", "source_url": url, "doc": doc})
    if not points:
        raise LayoutError("MIAX PDFs were downloaded but produced no points")
    return points, sources
