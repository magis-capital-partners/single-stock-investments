#!/usr/bin/env python3
"""Shared helpers for biotech specialist 13F ownership pipeline."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_DIR = ROOT / "_system" / "reference" / "market-data" / "ownership"
FUNDS_PATH = OWNERSHIP_DIR / "biotech_specialist_funds.json"
CIK_REGISTRY_PATH = OWNERSHIP_DIR / "fund_cik_registry.json"
RECORDS_DIR = OWNERSHIP_DIR / "records"
CACHE_DIR = OWNERSHIP_DIR / "cache"
SIGNALS_PATH = OWNERSHIP_DIR / "signals_latest.json"
CUSIP_MAP_PATH = OWNERSHIP_DIR / "cusip_ticker_map.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SEC_TICKER_CIK_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json"

SEC_UA = "MarvinResearch contact@example.com"
SLEEP_SEC = 0.12
FORM_13F = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(value: str | None, limit: int = 80) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text[:limit].strip("-") or "unknown"


def sec_fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def sec_fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def cik_padded(cik: str | int) -> str:
    return f"{int(str(cik).lstrip('0') or '0'):010d}"


def fetch_submissions(cik: str) -> dict:
    url = f"https://data.sec.gov/submissions/CIK{cik_padded(cik)}.json"
    return sec_fetch_json(url)


def latest_13f_filings(cik: str, limit: int = 4) -> list[dict]:
    try:
        submissions = fetch_submissions(cik)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    recent = submissions.get("filings", {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    primaries = recent.get("primaryDocument") or []
    cik_path = str(int(cik))
    candidates: list[dict] = []
    for form, fdate, acc, primary in zip(forms, dates, accessions, primaries):
        if form not in FORM_13F:
            continue
        candidates.append(
            {
                "form": form,
                "filing_date": fdate,
                "accession": acc,
                "primary_document": primary,
                "cik_path": cik_path,
                "index_url": f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{acc.replace('-', '')}/index.json",
            }
        )
    candidates.sort(key=lambda f: f.get("filing_date") or "", reverse=True)
    return candidates[:limit]


def filing_info_table_url(filing: dict) -> str | None:
    try:
        index = sec_fetch_json(filing["index_url"])
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    base = filing["index_url"].rsplit("/", 1)[0]
    for item in index.get("directory", {}).get("item") or []:
        name = (item.get("name") or "").lower()
        if "infotable" in name and name.endswith(".xml"):
            return f"{base}/{item['name']}"
    for item in index.get("directory", {}).get("item") or []:
        name = (item.get("name") or "").lower()
        if name.endswith(".xml") and "primary" not in name and "xsl" not in name:
            return f"{base}/{item['name']}"
    return None


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_13f_info_table_xml(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []
    for node in root.iter():
        if _local(node.tag) != "infoTable":
            continue
        row: dict[str, str | int | None] = {}
        for child in node:
            key = _local(child.tag)
            if key == "votingAuthority":
                for sub in child:
                    row[f"voting_{_local(sub.tag)}"] = (sub.text or "").strip()
            else:
                row[key] = (child.text or "").strip()
        if row.get("cusip") or row.get("nameOfIssuer"):
            rows.append(row)
    return rows


def normalize_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def portfolio_universe() -> tuple[dict[str, dict], dict[str, str]]:
    registry = load_json(REGISTRY_PATH, {"holdings": {}, "watchlist": {}})
    tickers: dict[str, dict] = {}
    names: dict[str, str] = {}
    for bucket in ("holdings", "watchlist"):
        for ticker, meta in (registry.get(bucket) or {}).items():
            tickers[ticker.upper()] = {**meta, "portfolio_section": bucket}
            names[ticker.upper()] = meta.get("company") or ticker
    return tickers, names


def load_cusip_map() -> dict[str, str]:
    doc = load_json(CUSIP_MAP_PATH, {"mappings": {}})
    return doc.get("mappings") or {}


def save_cusip_map(mappings: dict[str, str]) -> None:
    save_json(CUSIP_MAP_PATH, {"updated_at": now_iso(), "mappings": dict(sorted(mappings.items()))})


def match_holding_to_ticker(holding: dict, names: dict[str, str], cusip_map: dict[str, str]) -> str | None:
    cusip = (holding.get("cusip") or "").upper().strip()
    if cusip and cusip in cusip_map:
        return cusip_map[cusip]
    issuer = normalize_name(str(holding.get("nameOfIssuer") or ""))
    if not issuer:
        return None
    best: tuple[int, str] | None = None
    for ticker, company in names.items():
        company_norm = normalize_name(company)
        if not company_norm:
            continue
        if issuer == company_norm or issuer.startswith(company_norm) or company_norm.startswith(issuer):
            score = len(company_norm)
            if best is None or score > best[0]:
                best = (score, ticker)
        elif company_norm in issuer or issuer in company_norm:
            score = min(len(company_norm), len(issuer))
            if best is None or score > best[0]:
                best = (score, ticker)
    return best[1] if best else None


def quarter_from_date(value: str | None) -> str | None:
    if not value or len(value) < 7:
        return None
    try:
        year = int(value[:4])
        month = int(value[5:7])
    except ValueError:
        return None
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"


def specialist_funds_for_ingest() -> list[dict]:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    cik_doc = load_json(CIK_REGISTRY_PATH, {"funds": {}})
    cik_by_id = cik_doc.get("funds") or {}
    out: list[dict] = []
    for fund in funds_doc.get("funds") or []:
        if fund.get("signal_role") != "specialist_13f":
            continue
        if fund.get("ingest_13f") is False:
            continue
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        cik_entry = cik_by_id.get(fid) or {}
        cik = fund.get("cik") or cik_entry.get("cik")
        if not cik:
            continue
        out.append({**fund, "fund_id": fid, "cik": str(cik).lstrip("0")})
    return out


def sleep() -> None:
    time.sleep(SLEEP_SEC)
