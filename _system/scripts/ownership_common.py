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

from sec_client import get_bytes as sec_get_bytes
from sec_client import get_json as sec_get_json
from sec_client import sec_user_agent

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_DIR = ROOT / "_system" / "reference" / "market-data" / "ownership"
FUNDS_PATH = OWNERSHIP_DIR / "biotech_specialist_funds.json"
CIK_REGISTRY_PATH = OWNERSHIP_DIR / "fund_cik_registry.json"
RECORDS_DIR = OWNERSHIP_DIR / "records"
FULL_RECORDS_DIR = OWNERSHIP_DIR / "records" / "full"
CACHE_DIR = OWNERSHIP_DIR / "cache"
SIGNALS_PATH = OWNERSHIP_DIR / "signals_latest.json"
FUNDAMENTALS_PATH = OWNERSHIP_DIR / "biotech_fundamentals.json"
CLINICAL_PATH = OWNERSHIP_DIR / "biotech_clinical_profiles.json"
INSIDER_SCORES_PATH = OWNERSHIP_DIR / "biotech_insider_scores.json"
CUSIP_MAP_PATH = OWNERSHIP_DIR / "cusip_ticker_map.json"
OVERLAYS_DIR = OWNERSHIP_DIR / "overlays"
PAPER_BOOK_PATH = OWNERSHIP_DIR / "paper_book_latest.json"
SHORT_INTEREST_DIR = OWNERSHIP_DIR / "short_interest"
SHORT_INTEREST_PATH = OWNERSHIP_DIR / "biotech_short_interest.json"
BOOK_QUARTER_RE = re.compile(r"^\d{4}Q[1-4]$")
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SEC_TICKER_CIK_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json"

# Declared contact. SEC_USER_AGENT overrides this. The fetch client paces at ~5/s.
SEC_UA = sec_user_agent()
SLEEP_SEC = 0.0
FORM_13F = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}
HOLDINGS_FORMS = {"13F-HR", "13F-HR/A"}


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
    return sec_get_json(url)


def sec_fetch_bytes(url: str) -> bytes:
    return sec_get_bytes(url)


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
    reports = recent.get("reportDate") or []
    accessions = recent.get("accessionNumber") or []
    primaries = recent.get("primaryDocument") or []
    width = max(len(forms), len(dates), len(reports), len(accessions), len(primaries))
    forms = list(forms) + [""] * (width - len(forms))
    dates = list(dates) + [""] * (width - len(dates))
    reports = list(reports) + [""] * (width - len(reports))
    accessions = list(accessions) + [""] * (width - len(accessions))
    primaries = list(primaries) + [""] * (width - len(primaries))
    cik_path = str(int(cik))
    candidates: list[dict] = []
    for form, fdate, rdate, acc, primary in zip(forms, dates, reports, accessions, primaries):
        if form not in FORM_13F:
            continue
        candidates.append(
            {
                "form": form,
                "filing_date": fdate,
                "report_date": rdate,
                "accession": acc,
                "primary_document": primary,
                "cik_path": cik_path,
                "index_url": f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{acc.replace('-', '')}/index.json",
            }
        )
    candidates.sort(key=lambda f: f.get("filing_date") or "", reverse=True)
    return candidates[:limit]


def filing_document_urls(filing: dict) -> dict[str, str | None]:
    """Info table and cover page from one filing index request."""
    empty = {"info_table": None, "primary": None}
    try:
        index = sec_fetch_json(filing["index_url"])
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return empty
    base = filing["index_url"].rsplit("/", 1)[0]
    info = primary = None
    fallback = None
    for item in index.get("directory", {}).get("item") or []:
        name = item.get("name") or ""
        lower = name.lower()
        if not lower.endswith(".xml"):
            continue
        url = f"{base}/{name}"
        if "infotable" in lower:
            info = url
        elif lower.endswith("primary_doc.xml"):
            primary = url
        elif "primary" not in lower and "xsl" not in lower and fallback is None:
            fallback = url
    return {"info_table": info or fallback, "primary": primary}


def filing_info_table_url(filing: dict) -> str | None:
    return filing_document_urls(filing)["info_table"]


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
            elif key == "shrsOrPrnAmt":
                for sub in child:
                    row[_local(sub.tag)] = (sub.text or "").strip()
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


def load_cusip_document() -> dict:
    from thirteenf_core import cusip_entries_from_legacy

    doc = load_json(CUSIP_MAP_PATH, {"mappings": {}})
    mappings = doc.get("mappings") or {}
    if mappings and all(isinstance(value, str) for value in mappings.values()):
        migrated = cusip_entries_from_legacy(mappings)
        migrated["updated_at"] = doc.get("updated_at")
        return migrated
    if "quarantine" not in doc and mappings:
        migrated = cusip_entries_from_legacy(mappings)
        migrated["updated_at"] = doc.get("updated_at")
        return migrated
    return doc


def load_cusip_map() -> dict[str, str]:
    from thirteenf_core import ticker_map

    doc = load_cusip_document()
    return ticker_map(doc.get("mappings") or {})


def save_cusip_map(mappings: dict[str, str], *, source: str = "legacy") -> None:
    """Persist ticker strings without dropping source, confidence, or the quarantine list.

    Name-match callers should not call this. OpenFIGI and reviewed corrections may.
    """
    from thirteenf_core import structural_ticker

    doc = load_cusip_document()
    current = doc.get("mappings") or {}
    quarantine = doc.get("quarantine") or {}
    for cusip, ticker in (mappings or {}).items():
        key = str(cusip).upper().strip()
        symbol = str(ticker or "").upper().strip()
        if not key or not symbol:
            continue
        if structural_ticker(symbol):
            quarantine[key] = {
                "ticker": symbol,
                "source": source,
                "confidence": "low",
                "reason": "structural_ticker",
            }
            current.pop(key, None)
            continue
        prior = current.get(key) if isinstance(current.get(key), dict) else None
        if prior and prior.get("ticker") == symbol:
            continue
        if prior and prior.get("source") == "reviewed" and source != "reviewed":
            continue
        current[key] = {"ticker": symbol, "source": source, "confidence": "high" if source in {"reviewed", "openfigi"} else "medium"}
    save_json(
        CUSIP_MAP_PATH,
        {
            "updated_at": now_iso(),
            "mappings": dict(sorted(current.items())),
            "quarantine": dict(sorted(quarantine.items())),
        },
    )


def match_holding_to_ticker(holding: dict, names: dict[str, str], cusip_map: dict[str, str]) -> str | None:
    from thirteenf_core import structural_ticker

    cusip = (holding.get("cusip") or "").upper().strip()
    if cusip and cusip in cusip_map:
        ticker = cusip_map[cusip]
        if structural_ticker(ticker):
            return None
        return ticker
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


BIOTECH_ISSUER_KEYWORDS = (
    "biotech",
    "biopharm",
    "therapeutic",
    "therapeutics",
    "pharma",
    "pharmaceutical",
    "bioscience",
    "biosciences",
    "genomic",
    "genetics",
    "genome",
    "oncology",
    "immuno",
    "diagnostic",
    "diagnostics",
    "lifesci",
    "life sci",
    "medical",
    "medicine",
    "medicines",
    "vaccine",
    "vaccines",
    "bio ",
    " bio",
    "biolog",
    "antibody",
    "antibodies",
    "rna ",
    "mrna",
    "gene ",
    "genes",
    "cell therapy",
    "cellular",
    "neuroscience",
    "neuro",
    "hematolog",
    "cardiolog",
    "ophthalm",
    "radiopharm",
    "molecular",
    "clinical",
    "health",
    "healthcare",
    "life sciences",
    "rx ",
    "drug",
    "drugs",
    "amgen",
    "biogen",
    "gilead",
    "regeneron",
    "vertex",
    "moderna",
    "illumina",
    "biomarin",
    "incyte",
    "alexion",
    "seagen",
    "sarepta",
    "alnylam",
    "ionis",
    "exelixis",
    "neurocrine",
    "united therapeutics",
    "jazz pharmaceuticals",
    "bristol myers",
    "bristol-myers",
    "eli lilly",
    "lilly",
    "pfizer",
    "merck",
    "novartis",
    "roche",
    "sanofi",
    "astrazeneca",
    "abbvie",
    "takeda",
    "bayer",
    "glaxosmithkline",
    "gsk ",
    "johnson johnson",
    "jnj",
)

NON_BIOTECH_ISSUER_KEYWORDS = (
    "alphabet",
    "google",
    "amazon",
    "meta platform",
    "facebook",
    "nvidia",
    "microsoft",
    "apple",
    "tesla",
    "advanced micro",
    "microstrategy",
    "enphase",
    "copart",
    "costar",
    "berkshire",
    "bank of",
    "jpmorgan",
    "goldman",
)


def issuer_looks_biotech(issuer: str | None) -> bool:
    text = normalize_name(str(issuer or ""))
    if not text:
        return False
    if any(term in text for term in NON_BIOTECH_ISSUER_KEYWORDS):
        return False
    return any(term in text for term in BIOTECH_ISSUER_KEYWORDS)


def classify_fund_biotech_share(holdings: list[dict]) -> dict:
    """Estimate biotech MV share from InfoTable rows using issuer keywords."""
    total = 0
    biotech = 0
    for row in holdings:
        value = row.get("market_value_usd") or 0
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        total += max(value, 0)
        if issuer_looks_biotech(row.get("issuer") or row.get("nameOfIssuer")):
            biotech += max(value, 0)
    share = (biotech / total) if total else 0.0
    return {
        "total_market_value_usd": total,
        "biotech_market_value_usd": biotech,
        "biotech_mv_share": round(share, 4),
        "is_specialist_by_rule": share > 0.50,
        "holding_count": len(holdings),
        "biotech_holding_count": sum(
            1 for r in holdings if issuer_looks_biotech(r.get("issuer") or r.get("nameOfIssuer"))
        ),
    }


def yahoo_symbol(ticker: str) -> str:
    return (ticker or "").upper().replace(".", "-")


def fetch_yahoo_price(ticker: str) -> float | None:
    """Latest regular-market price from Yahoo chart API (v7 quote often blocked)."""
    sym = yahoo_symbol(ticker)
    if not sym or ":" in sym:
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MarvinResearch/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        return float(price) if price is not None else None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def sec_shares_outstanding(ticker: str, cik: str | None = None) -> float | None:
    """Latest shares outstanding from SEC companyfacts."""
    if not cik:
        sec_map = load_json(SEC_TICKER_CIK_PATH, {})
        cik = sec_map.get(ticker.upper()) or sec_map.get(ticker.upper().replace(".", "-"))
    if not cik:
        return None
    padded = cik_padded(cik)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json"
    try:
        facts = sec_fetch_json(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    best_date = ""
    best_val: float | None = None
    for tag in ("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"):
        block = us_gaap.get(tag) or {}
        for unit_key, entries in (block.get("units") or {}).items():
            if "share" not in unit_key.lower():
                continue
            for entry in entries or []:
                end = entry.get("end") or entry.get("instant") or ""
                val = entry.get("val")
                if val is None or not end:
                    continue
                try:
                    fval = float(val)
                except (TypeError, ValueError):
                    continue
                if end >= best_date:
                    best_date = end
                    best_val = fval
    return best_val


def issuer_size_bucket(market_cap: float | None) -> str:
    """Verdad-style issuer market-cap buckets (not position liquidity)."""
    if market_cap is None or market_cap <= 0:
        return "unknown"
    if market_cap < 2_000_000_000:
        return "small"
    if market_cap < 10_000_000_000:
        return "mid"
    return "large"


def fetch_issuer_market_cap(ticker: str, *, offline: bool = False) -> dict:
    """Prefer SEC shares outstanding × Yahoo price; cache in biotech_fundamentals.json."""
    tk = (ticker or "").upper()
    funda = load_json(FUNDAMENTALS_PATH, {"by_ticker": {}})
    by_ticker = funda.setdefault("by_ticker", {})
    cached = by_ticker.get(tk) or {}
    if offline and cached.get("issuer_market_cap"):
        return {
            "issuer_market_cap": cached.get("issuer_market_cap"),
            "market_cap_source": cached.get("market_cap_source") or "cache",
            "shares_outstanding": cached.get("shares_outstanding"),
            "price": cached.get("price"),
        }
    if offline:
        return {
            "issuer_market_cap": cached.get("issuer_market_cap"),
            "market_cap_source": cached.get("market_cap_source"),
            "shares_outstanding": cached.get("shares_outstanding"),
            "price": cached.get("price"),
        }

    shares = sec_shares_outstanding(tk)
    sleep()
    price = fetch_yahoo_price(tk)
    mcap = None
    source = None
    if shares and price and shares > 0 and price > 0:
        mcap = round(shares * price, 2)
        source = "sec_shares_x_yahoo"
    elif cached.get("issuer_market_cap"):
        mcap = cached.get("issuer_market_cap")
        source = cached.get("market_cap_source") or "cache"
        shares = shares or cached.get("shares_outstanding")
        price = price or cached.get("price")

    if mcap:
        by_ticker[tk] = {
            **cached,
            "ticker": tk,
            "issuer_market_cap": mcap,
            "market_cap_source": source,
            "shares_outstanding": shares,
            "price": price,
            "issuer_size_bucket": issuer_size_bucket(mcap),
            "updated_at": now_iso(),
        }
        funda["generated_at"] = now_iso()
        save_json(FUNDAMENTALS_PATH, funda)

    return {
        "issuer_market_cap": mcap,
        "market_cap_source": source,
        "shares_outstanding": shares,
        "price": price,
    }


def assign_quintiles(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    n = len(ordered)
    out: dict[str, int] = {}
    for i, (ticker, _) in enumerate(ordered):
        out[ticker] = 5 - min(4, int(i * 5 / max(n, 1)))
    return out
