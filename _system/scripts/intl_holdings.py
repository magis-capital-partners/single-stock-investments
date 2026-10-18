"""Normalize public international ownership filings.

N-PORT is a US fund's full book, including securities listed outside the United
States. EDINET large-shareholding reports are Japan's 5 percent notices. Neither
is an input to the base return.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.split("}")[-1].lower() if tag else ""


def _number(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text or text.upper() in {"N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def parse_nport_holdings(xml: bytes) -> tuple[str | None, list[dict]]:
    """Period end and investment rows from one N-PORT primary document."""
    root = ET.fromstring(xml)
    period = None
    fiscal_end = None
    for node in root.iter():
        tag = _local(node.tag)
        text = (node.text or "").strip()[:10]
        if tag == "reppddate" and text and period is None:
            period = text
        elif tag == "reppdend" and text and fiscal_end is None:
            fiscal_end = text
    period = period or fiscal_end
    rows: list[dict] = []
    for node in root.iter():
        if _local(node.tag) != "invstorsec":
            continue
        row = {
            "name": "",
            "title": "",
            "cusip": "",
            "isin": "",
            "shares": None,
            "value_usd": None,
            "pct_val": None,
            "country": "",
            "payoff": "",
        }
        for child in node.iter():
            tag = _local(child.tag)
            text = (child.text or "").strip()
            if tag == "name" and text and not row["name"]:
                row["name"] = text
            elif tag == "title" and text and not row["title"]:
                row["title"] = text
            elif tag == "cusip" and text and text.upper() not in {"N/A", "NA"} and not row["cusip"]:
                row["cusip"] = text.upper()
            elif tag == "isin" and text and not row["isin"]:
                row["isin"] = text.upper()
            elif tag in {"balance", "shares"} and row["shares"] is None:
                row["shares"] = _number(text)
            elif tag == "valusd" and row["value_usd"] is None:
                row["value_usd"] = _number(text)
            elif tag == "pctval" and row["pct_val"] is None:
                row["pct_val"] = _number(text)
            elif tag == "invcountry" and text and not row["country"]:
                row["country"] = text.upper()
            elif tag == "payoffprofile" and text and not row["payoff"]:
                row["payoff"] = text
            elif tag in {"other", "identifier", "isin"}:
                ident = (child.get("value") or child.get("identifier") or text or "").strip().upper()
                kind = (child.get("type") or child.get("identifiertype") or tag).upper()
                if ident and ("ISIN" in kind or (len(ident) == 12 and ident[:2].isalpha() and ident[2:].isalnum())):
                    row["isin"] = ident
        if row["name"] or row["isin"]:
            rows.append(row)
    return period, rows


def match_portfolio_ticker(row: dict, portfolio: dict[str, str], isin_map: dict[str, str] | None = None) -> str | None:
    """One SSI ticker, or nothing when two names fit."""
    isin_map = isin_map or {}
    isin = (row.get("isin") or "").upper()
    if isin and isin in isin_map:
        return isin_map[isin]
    issuer = _compact(row.get("name"))
    if len(issuer) < 8:
        return None
    hits = []
    for ticker, company in portfolio.items():
        target = _compact(company)
        if len(target) < 8:
            continue
        if issuer.startswith(target) or target.startswith(issuer):
            hits.append(ticker)
    if len(hits) == 1:
        return hits[0]
    return None


def is_international(row: dict, ticker: str) -> bool:
    if "." in (ticker or ""):
        return True
    country = (row.get("country") or "").upper()
    if country and country not in {"US", "USA"}:
        return True
    isin = (row.get("isin") or "").upper()
    return bool(isin) and not isin.startswith("US")


def edinet_status(configured: bool, stakes: list[dict] | None = None, *, detail: str = "") -> dict:
    return {
        "schema_version": 1,
        "in_base_irr": False,
        "source": "edinet",
        "configured": configured,
        "threshold_basis": "5 percent large-shareholding report",
        "detail": detail,
        "stakes": stakes or [],
    }
