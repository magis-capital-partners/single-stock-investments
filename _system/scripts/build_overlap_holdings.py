"""Build dashboard/data/overlap_holdings.json from filings already on disk, then optional EDGAR pulls.

--local-only uses specialist books and the six cached adviser info tables.
A later run without that flag adds the fixed large-adviser list, a filtered 13F
data-set zip, and N-PORT borrowings. The unfiltered zip is not kept.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    SEC_UA,
    SLEEP_SEC,
    cik_padded,
    fetch_submissions,
    filing_info_table_url,
    latest_13f_filings,
    load_cusip_map,
    normalize_name,
    now_iso,
    parse_13f_info_table_xml,
    portfolio_universe,
    save_cusip_map,
    sec_fetch_bytes,
    sec_fetch_json,
)

TIERS_PATH = ROOT / "_system" / "data" / "valuation_universe_tiers.json"
FLOAT_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "index_float_adv.json"
INDEX_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
HOLDERS_PATH = ROOT / "dashboard" / "data" / "overlap_holders.json"
OUT_PATH = ROOT / "dashboard" / "data" / "overlap_holdings.json"
SPECIALIST_DIR = ROOT / "_system" / "reference" / "market-data" / "ownership" / "records" / "full"
TRACKED_CACHE = ROOT / "_system" / "reference" / "market-data" / "ownership" / "tracked_funds" / "cache"
TRACKED_FUNDS = ROOT / "_system" / "reference" / "market-data" / "ownership" / "tracked_funds.json"
CACHE_DIR = ROOT / "_system" / "reference" / "market-data" / "ownership" / "overlap_cache"
ETF_HOLDINGS = Path.home() / "Projects" / "quant" / "etf-dashboard" / "data" / "etf_holdings_latest.json"
HUB_SHARE = 0.25
HOLDER_CAP = 40
ZIP_URLS = [
    "https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip",
    "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip",
]
STRUCTURAL_SUFFIXES = (".ESC", ".CVR", ".WTS", ".DB", ".CNT", ".MRG")
FOREIGN_SUFFIXES = (
    ".TO", ".V", ".HK", ".PA", ".MX", ".AX", ".ST", ".SW", ".DE", ".OL", ".HE",
    ".CO", ".AS", ".SA", ".SI", ".KS", ".TW", ".SS", ".SZ", ".BR", ".T", ".L",
)
LEGAL_SUFFIXES = (
    " incorporated", " corporation", " corp", " company", " inc", " ltd", " plc",
    " llc", " lp", " sa", " nv", " ag", " co", " limited",
)


def structural(ticker: str) -> bool:
    upper = (ticker or "").upper()
    if any(upper.endswith(suffix) for suffix in STRUCTURAL_SUFFIXES):
        return True
    return re.search(r"\.PS\d", upper) is not None


def foreign_listing(ticker: str) -> bool:
    upper = (ticker or "").upper()
    return any(upper.endswith(suffix) for suffix in FOREIGN_SUFFIXES)


def resolve_mapped(tickers: list[str], universe: set[str]) -> tuple[str | None, str | None]:
    cleaned = [ticker for ticker in tickers if ticker]
    stocks = []
    structural_hits = []
    for ticker in cleaned:
        if structural(ticker):
            structural_hits.append(ticker)
        elif ticker in universe:
            stocks.append(ticker)
    unique = list(dict.fromkeys(stocks))
    if len(unique) > 1:
        return None, "ambiguous"
    if len(unique) == 1:
        return unique[0], None
    if structural_hits:
        return None, "not_common_stock"
    return None, "unmapped"


def company_key(name: str) -> str:
    text = normalize_name(name)
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def parse_number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def shares_from_row(row: dict) -> float | None:
    kind = str(row.get("sshPrnamtType") or "SH").upper()
    if kind not in {"SH", ""}:
        return None
    return parse_number(row.get("sshPrnamt"))


class Book:
    def __init__(self) -> None:
        self.funds: dict[str, dict] = {}
        self.cells: dict[tuple[str, str], dict] = {}
        self.exceptions: list[dict] = []
        self.seen_exceptions: set[str] = set()

    def fund(self, fund_id: str, name: str, kind: str, cik: str) -> None:
        current = self.funds.get(fund_id)
        if current is None:
            self.funds[fund_id] = {"fund_id": fund_id, "name": name, "kind": kind, "cik": cik or ""}
            return
        if kind == "bulk_13f" and current["kind"] != "bulk_13f":
            return
        current["name"] = current["name"] or name

    def add(self, fund_id: str, cusip: str, ticker: str, market_value: float, shares: float | None, source: str) -> None:
        key = (fund_id, cusip)
        prior = self.cells.get(key)
        if prior and prior["source"] == "bulk_13f" and source != "bulk_13f":
            return
        if prior and source != "bulk_13f" and prior["source"] == source and prior["ticker"] == ticker:
            prior["market_value"] += market_value
            if shares is not None:
                prior["shares"] = (prior["shares"] or 0) + shares
            return
        self.cells[key] = {
            "fund_id": fund_id,
            "cusip": cusip,
            "ticker": ticker,
            "market_value": market_value,
            "shares": shares,
            "source": source,
        }

    def exception(self, cusip: str, reason: str, detail: str) -> None:
        if cusip in self.seen_exceptions:
            return
        self.seen_exceptions.add(cusip)
        self.exceptions.append({"cusip": cusip, "reason": reason, "detail": detail})


def attach_row(book: Book, cusip: str, issuer: str, market_value: float, shares: float | None, fund_id: str, name: str, kind: str, cik: str, cusip_map: dict[str, str], universe: set[str], names_by_key: dict[str, list[str]], allow_name: bool, origin: str | None = None) -> None:
    if not cusip or market_value is None or market_value <= 0:
        return
    mapped = cusip_map.get(cusip)
    ticker, reason = resolve_mapped([mapped] if mapped else [], universe)
    if reason == "ambiguous":
        book.exception(cusip, "ambiguous", mapped or "")
        return
    if ticker is None and allow_name and cusip not in cusip_map:
        matches = names_by_key.get(company_key(issuer), [])
        matches = [match for match in matches if len(company_key(issuer)) >= 6]
        if len(matches) > 1:
            book.exception(cusip, "ambiguous", issuer)
            return
        if len(matches) == 1:
            ticker = matches[0]
            cusip_map[cusip] = ticker
    if ticker is None:
        if reason == "not_common_stock":
            book.exception(cusip, "not_common_stock", mapped or "")
        return
    book.fund(fund_id, name, kind, cik)
    book.add(fund_id, cusip, ticker, market_value, shares, origin or ("bulk_13f" if kind == "bulk_13f" else kind))


def load_universe() -> tuple[dict[str, dict], set[str]]:
    document = json.loads(TIERS_PATH.read_text(encoding="utf-8"))
    assignments = document.get("assignments") or {}
    universe = {ticker.upper(): row for ticker, row in assignments.items()}
    return universe, set(universe)


def load_names(universe: set[str]) -> dict[str, str]:
    names = {ticker: ticker for ticker in universe}
    _, registry_names = portfolio_universe()
    for ticker, company in registry_names.items():
        if ticker in names and company:
            names[ticker] = company
    if INDEX_PATH.exists():
        memberships = (json.loads(INDEX_PATH.read_text(encoding="utf-8")).get("by_ticker") or {})
        for ticker in universe:
            if names.get(ticker) and names[ticker] != ticker:
                continue
            company = (memberships.get(ticker) or {}).get("company")
            if company:
                names[ticker] = company
    return names


def load_local(book: Book, cusip_map: dict[str, str], universe: set[str]) -> dict:
    stats = {"specialist_funds": 0, "specialist_rows": 0, "tracked_files": 0, "tracked_rows": 0}
    if SPECIALIST_DIR.exists():
        for path in sorted(SPECIALIST_DIR.glob("*/latest.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            fund_id = payload.get("fund_id") or path.parent.name
            fund_name = payload.get("fund") or payload.get("fund_name") or payload.get("name") or fund_id
            stats["specialist_funds"] += 1
            for record in payload.get("records") or []:
                cusip = str(record.get("cusip") or "").upper()
                value = parse_number(record.get("market_value_usd"))
                if not cusip or value is None:
                    continue
                before = len(book.cells)
                attach_row(
                    book, cusip, record.get("issuer") or "", value, parse_number(record.get("shares")),
                    fund_id, record.get("fund_name") or fund_name, "specialist_13f", str(record.get("cik") or payload.get("cik") or ""),
                    cusip_map, universe, {}, False,
                )
                if len(book.cells) != before or (fund_id, cusip) in book.cells:
                    stats["specialist_rows"] += 1
    if TRACKED_CACHE.exists():
        labels = {}
        if TRACKED_FUNDS.exists():
            labels = {row.get("fund_id"): row.get("fund") for row in (json.loads(TRACKED_FUNDS.read_text(encoding="utf-8")).get("funds") or [])}
        for path in sorted(TRACKED_CACHE.glob("*.xml")):
            fund_id = path.name.split("_", 1)[0]
            rows = parse_13f_info_table_xml(path.read_bytes())
            stats["tracked_files"] += 1
            for record in rows:
                if record.get("putCall"):
                    continue
                value = parse_number(record.get("value"))
                cusip = str(record.get("cusip") or "").upper()
                if value is None or not cusip:
                    continue
                attach_row(
                    book, cusip, record.get("nameOfIssuer") or "", value, shares_from_row(record),
                    fund_id, labels.get(fund_id) or fund_id, "tracked_13f", "", cusip_map, universe, {}, False,
                )
                stats["tracked_rows"] += 1
    return stats


def confirm_adviser(adviser: dict) -> dict:
    cik = str(adviser.get("cik") or "").strip()
    if not cik and adviser.get("id") == "capital-world":
        cik = search_capital_world() or ""
        adviser["cik"] = cik
    if not cik:
        adviser["confirmed"] = False
        adviser["stale"] = True
        adviser["confirm_error"] = "no CIK on file"
        return adviser
    try:
        submissions = fetch_submissions(cik)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        adviser["confirmed"] = False
        adviser["stale"] = True
        adviser["confirm_error"] = str(error)
        return adviser
    adviser["sec_name"] = submissions.get("name") or ""
    adviser["sec_url_used"] = f"https://data.sec.gov/submissions/CIK{cik_padded(cik)}.json"
    filings = latest_13f_filings(cik, limit=2)
    adviser["confirmed"] = bool(filings) and adviser["sec_name"] != ""
    adviser["latest_filing"] = filings[0]["filing_date"] if filings else None
    if not filings:
        adviser["stale"] = True
        adviser["confirm_error"] = "no 13F-HR on the submissions feed"
    time.sleep(SLEEP_SEC)
    return adviser


def search_capital_world() -> str | None:
    url = "https://efts.sec.gov/LATEST/search-index?q=" + quote('"Capital World Investors"') + "&forms=13F-HR"
    try:
        request = Request(url, headers={"User-Agent": SEC_UA, "Accept": "application/json"})
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    hits = ((payload.get("hits") or {}).get("hits") or [])
    for hit in hits:
        source = hit.get("_source") or {}
        ciks = source.get("ciks") or source.get("entity_id") or []
        if isinstance(ciks, list) and ciks:
            return cik_padded(ciks[0])
        display = " ".join(source.get("display_names") or [])
        if "Capital World" in display and source.get("ciks"):
            return None
    return None


def fetch_adviser_table(adviser: dict, book: Book, cusip_map: dict[str, str], universe: set[str]) -> str:
    if not adviser.get("confirmed"):
        return "skipped"
    filings = latest_13f_filings(adviser["cik"], limit=1)
    if not filings:
        adviser["stale"] = True
        return "no filing"
    filing = filings[0]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{adviser['id']}_{filing['accession'].replace('-', '')}.xml"
    if not cache_path.exists():
        info_url = filing_info_table_url(filing)
        time.sleep(SLEEP_SEC)
        if not info_url:
            adviser["stale"] = True
            adviser["confirm_error"] = "info table URL missing"
            return "no info table"
        cache_path.write_bytes(sec_fetch_bytes(info_url))
        time.sleep(SLEEP_SEC)
    rows = parse_13f_info_table_xml(cache_path.read_bytes())
    kept = 0
    for record in rows:
        if record.get("putCall"):
            continue
        value = parse_number(record.get("value"))
        cusip = str(record.get("cusip") or "").upper()
        if value is None or not cusip:
            continue
        attach_row(
            book, cusip, record.get("nameOfIssuer") or "", value, shares_from_row(record),
            adviser["id"], adviser.get("sec_name") or adviser["name"], "large_13f", adviser["cik"],
            cusip_map, universe, {}, False,
        )
        kept += 1
    adviser["rows_kept"] = kept
    adviser["quarter_filing_date"] = filing["filing_date"]
    return "ok"


def download_zip(url: str, dest: Path) -> bool:
    request = Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urlopen(request, timeout=300) as response, dest.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except (HTTPError, URLError, TimeoutError):
        if dest.exists():
            dest.unlink()
        return False
    return dest.exists() and dest.stat().st_size > 0


def column(fieldnames: list[str], *options: str) -> str | None:
    folded = {name.lower(): name for name in fieldnames}
    for option in options:
        if option.lower() in folded:
            return folded[option.lower()]
    return None


def sortable_sec_date(value: str) -> str:
    months = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
        "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }
    parts = (value or "").upper().split("-")
    if len(parts) == 3 and parts[1] in months:
        return f"{parts[2]}-{months[parts[1]]}-{parts[0]}"
    return value or ""


def quarter_is_mid_2026(value: str) -> bool:
    text = (value or "").upper().replace(" ", "")
    return "30-JUN-2026" in text or "2026-06-30" in text or "06/30/2026" in text


def load_bulk_zip(book: Book, cusip_map: dict[str, str], universe: set[str], names_by_key: dict[str, list[str]], curated: dict[str, dict]) -> str:
    zip_path = CACHE_DIR / "form13f_q2.zip"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    used = None
    if zip_path.exists() and zip_path.stat().st_size > 1_000_000:
        used = "local cache form13f_q2.zip"
    else:
        for url in ZIP_URLS:
            print(f"trying {url}", flush=True)
            if download_zip(url, zip_path):
                used = url
                break
    if used is None:
        return "zip not published at the tried URLs"
    map_before = len(cusip_map)
    kept = 0
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            info_name = next((name for name in names if name.lower().endswith("infotable.tsv")), None)
            cover_name = next((name for name in names if "coverpage" in name.lower() and name.lower().endswith(".tsv")), None)
            if not info_name or not cover_name:
                return "zip had no info table"
            best: dict[str, tuple] = {}
            with archive.open("SUBMISSION.tsv") as handle:
                reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
                for row in reader:
                    if not quarter_is_mid_2026(row.get("PERIODOFREPORT") or ""):
                        continue
                    padded = cik_padded(row.get("CIK") or "")
                    accession = row.get("ACCESSION_NUMBER") or ""
                    if not padded or not accession:
                        continue
                    filed = sortable_sec_date(row.get("FILING_DATE") or "")
                    prior = best.get(padded)
                    if prior is None or filed > prior[0]:
                        best[padded] = (filed, accession)
            if not best:
                return "submission file had no 30 Jun 2026 report period"
            accession_cik = {accession: cik for cik, (_filed, accession) in best.items()}
            manager_names: dict[str, str] = {}
            with archive.open(cover_name) as handle:
                reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
                fields = reader.fieldnames or []
                acc_col = column(fields, "ACCESSION_NUMBER")
                name_col = column(fields, "FILINGMANAGER_NAME")
                if not acc_col or not name_col:
                    return "cover page columns were not recognized"
                for row in reader:
                    if row.get(acc_col) in accession_cik:
                        manager_names[row[acc_col]] = row.get(name_col) or ""
            print(f"parsing {len(best)} filers for 30 Jun 2026", flush=True)
            with archive.open(info_name) as handle:
                reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
                fields = reader.fieldnames or []
                acc_col = column(fields, "ACCESSION_NUMBER")
                cusip_col = column(fields, "CUSIP")
                value_col = column(fields, "VALUE")
                shares_col = column(fields, "SSHPRNAMT")
                share_type = column(fields, "SSHPRNAMTTYPE")
                issuer_col = column(fields, "NAMEOFISSUER")
                put_col = column(fields, "PUTCALL")
                if not acc_col or not cusip_col or not value_col:
                    return "info table columns were not recognized"
                for row in reader:
                    if put_col and row.get(put_col):
                        continue
                    cik = accession_cik.get(row[acc_col], "")
                    if not cik:
                        continue
                    manager = manager_names.get(row[acc_col], "")
                    cusip = str(row.get(cusip_col) or "").upper()
                    value = parse_number(row.get(value_col))
                    if value is None or not cusip:
                        continue
                    shares = parse_number(row.get(shares_col)) if shares_col else None
                    if share_type and str(row.get(share_type) or "").upper() not in {"SH", ""}:
                        shares = None
                    known = curated.get(cik)
                    fund_id = known["id"] if known else f"cik-{cik}"
                    kind = "large_13f" if known else "bulk_13f"
                    label = (known or {}).get("name") or manager or f"CIK {cik}"
                    before = (fund_id, cusip) not in book.cells
                    attach_row(
                        book, cusip, row.get(issuer_col) or "", value, shares,
                        fund_id, label, kind, cik, cusip_map, universe, names_by_key, True, "bulk_13f",
                    )
                    if before and (fund_id, cusip) in book.cells:
                        kept += 1
    finally:
        if zip_path.exists() and "local cache" not in (used or ""):
            zip_path.unlink()
    added = len(cusip_map) - map_before
    if added:
        save_cusip_map(cusip_map)
    return f"SEC 13F data set for 30 Jun 2026, {len(best)} filers. The unfiltered zip is not in the repo. New CUSIP links this run: {added}."


def local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def load_nport(book: Book, holders: dict, cusip_map: dict[str, str], universe: set[str]) -> list[str]:
    notes = []
    seen_cik: dict[str, bytes] = {}
    for etf in holders.get("plain_etfs") or []:
        cik = str(etf.get("cik") or "")
        ticker = etf.get("etf_ticker")
        if not cik:
            notes.append(f"{ticker}: no CIK")
            continue
        try:
            if cik not in seen_cik:
                submissions = fetch_submissions(cik)
                time.sleep(SLEEP_SEC)
                recent = (submissions.get("filings") or {}).get("recent") or {}
                forms = recent.get("form") or []
                accessions = recent.get("accessionNumber") or []
                primaries = recent.get("primaryDocument") or []
                xml = None
                for form, accession, _primary in zip(forms, accessions, primaries):
                    if form not in {"NPORT-P", "NPORT-P/A"}:
                        continue
                    folder = accession.replace("-", "")
                    index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/index.json"
                    index = sec_fetch_json(index_url)
                    time.sleep(SLEEP_SEC)
                    base = index_url.rsplit("/", 1)[0]
                    items = index.get("directory", {}).get("item") or []
                    name = next((item.get("name") for item in items if (item.get("name") or "").lower() == "primary_doc.xml"), None)
                    if name is None:
                        name = next((item.get("name") for item in items if (item.get("name") or "").lower().endswith(".xml") and "xsl" not in (item.get("name") or "").lower()), None)
                    xml = sec_fetch_bytes(f"{base}/{name}") if name else None
                    time.sleep(SLEEP_SEC)
                    break
                seen_cik[cik] = xml or b""
            xml = seen_cik.get(cik) or b""
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            notes.append(f"{ticker}: {error}")
            continue
        if not xml:
            notes.append(f"{ticker}: no N-PORT-P")
            continue
        parsed = parse_nport_series(xml, ticker, whole=cik_padded(cik) in {"0000884394", "0001067839"} and ticker in {"SPY", "QQQ"})
        if parsed is None:
            notes.append(f"{ticker}: series not isolated")
            continue
        borrowings, assets, rows = parsed
        ratio = (borrowings / assets) if assets else None
        for cusip, value, shares in rows:
            attach_row(
                book, cusip, "", value, shares, ticker.lower(), ticker, "etf", cik,
                cusip_map, universe, {}, False,
            )
        for cell in book.cells.values():
            if cell["fund_id"] == ticker.lower() and ratio is not None:
                book.funds[ticker.lower()]["borrowings_ratio"] = ratio
        etf["borrowings_ratio"] = ratio
        etf["holdings_kept"] = len(rows)
    return notes


def parse_nport_series(xml: bytes, ticker: str, whole: bool = False) -> tuple[float | None, float | None, list[tuple[str, float, float | None]]] | None:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    ticker_leaves = [
        node for node in root.iter()
        if local_tag(node.tag).lower() in {"ticker", "classticker", "seriesticker"}
        and (node.text or "").strip().upper() == ticker.upper()
    ]
    series_ids = [node for node in root.iter() if local_tag(node.tag).lower() == "seriesid"]
    if len(ticker_leaves) == 1:
        chosen = ticker_leaves[0]
        parent = {child: node for node in root.iter() for child in list(node)}
        for _ in range(6):
            if chosen is root or local_tag(chosen.tag).lower() in {"series", "fund"}:
                break
            chosen = parent.get(chosen, root)
    elif whole:
        head = xml.decode("utf-8", "replace")[:8000].upper()
        if ticker == "SPY" and "SPDR" not in head:
            return None
        if ticker == "QQQ" and "NASDAQ" not in head and "QQQ" not in head:
            return None
        chosen = root
    else:
        return None
    borrowings = 0.0
    saw_borrow = False
    assets = None
    rows = []
    for node in chosen.iter():
        tag = local_tag(node.tag).lower()
        if tag.startswith("amtpay"):
            amount = parse_number((node.text or "").strip())
            if amount is not None:
                borrowings += amount
                saw_borrow = True
        if tag == "totassets" and assets is None:
            assets = parse_number((node.text or "").strip())
        if tag == "invstorsec":
            cusip = value = shares = None
            for child in node.iter():
                child_tag = local_tag(child.tag).lower()
                if child_tag == "cusip":
                    cusip = (child.text or "").strip().upper()
                elif child_tag in {"valusd", "value"}:
                    value = parse_number((child.text or "").strip())
                elif child_tag in {"balance", "shares"}:
                    shares = parse_number((child.text or "").strip())
            if cusip and value:
                rows.append((cusip, value, shares))
    if not rows:
        return None
    return (borrowings if saw_borrow else None), assets, rows


def load_etf_file(book: Book, holders: dict, cusip_map: dict[str, str], universe: set[str]) -> str:
    if not ETF_HOLDINGS.exists():
        return "holdings file not on this machine"
    payload = json.loads(ETF_HOLDINGS.read_text(encoding="utf-8"))
    multiples = {row["etf_ticker"]: row for row in holders.get("stated_multiples") or []}
    by_symbol = payload.get("by_symbol") or {}
    kept = 0
    for symbol, rows in by_symbol.items():
        if not isinstance(rows, list):
            continue
        meta = multiples.get(symbol)
        if meta is None:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cusip = str(row.get("cusip") or "").upper()
            ticker = str(row.get("holding_ticker") or row.get("underlying_ticker") or row.get("ticker") or "").upper()
            value = parse_number(row.get("market_value") or row.get("market_value_usd"))
            target = None
            if cusip:
                target, _reason = resolve_mapped([cusip_map.get(cusip)] if cusip_map.get(cusip) else [], universe)
            elif ticker in universe and not structural(ticker):
                target = ticker
            if target is None or value is None:
                continue
            book.fund(symbol.lower(), symbol, "etf", "")
            book.funds[symbol.lower()]["stated_multiple"] = meta["stated_multiple"]
            book.add(symbol.lower(), cusip or ticker, target, value, parse_number(row.get("shares")), "etf")
            kept += 1
    if kept == 0:
        return "holdings file had no cusip or ticker rows for the stated-multiple list"
    return f"loaded {kept} rows"


def full_stats(holders: list[dict]) -> dict:
    total = sum(holder["market_value"] for holder in holders)
    if total <= 0:
        return {
            "holder_count": 0, "top_share": None, "top_holder": None, "top_shares": None,
            "herfindahl": None, "hub_name": False, "leverage_above": 0, "leverage_text": "no holder on file",
        }
    ranked = sorted(holders, key=lambda holder: (-holder["market_value"], holder.get("cik") or ""))
    top = ranked[0]
    herfindahl = sum((holder["market_value"] / total) ** 2 for holder in holders)
    above = 0
    reported = None
    for holder in holders:
        multiple = holder.get("stated_multiple")
        ratio = holder.get("borrowings_ratio")
        if multiple is not None and abs(multiple) >= 2:
            above += 1
            reported = f"{multiple}×"
        elif ratio is not None and ratio >= 0.10:
            above += 1
            reported = f"{ratio * 100:.1f}% borrowings"
        elif reported is None and (multiple is not None or ratio is not None):
            reported = f"{multiple}×" if multiple is not None else f"{ratio * 100:.1f}% borrowings"
    return {
        "holder_count": len(holders),
        "top_share": top["market_value"] / total,
        "top_holder": top["name"],
        "top_shares": top.get("shares"),
        "herfindahl": herfindahl,
        "hub_name": (top["market_value"] / total) >= HUB_SHARE,
        "leverage_above": above,
        "leverage_text": f"{above} above the threshold" if above else (reported or "not reported"),
    }


def render(book: Book, universe: dict[str, dict], names: dict[str, str], mode: str, coverage: dict) -> dict:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    fund_kind = {fund_id: meta["kind"] for fund_id, meta in book.funds.items()}
    for cell in book.cells.values():
        meta = book.funds[cell["fund_id"]]
        by_ticker[cell["ticker"]].append({
            "fund_id": cell["fund_id"],
            "name": meta["name"],
            "kind": meta["kind"],
            "cik": meta.get("cik") or "",
            "market_value": round(cell["market_value"], 2),
            "shares": cell["shares"],
            **({"stated_multiple": meta["stated_multiple"]} if "stated_multiple" in meta else {}),
            **({"borrowings_ratio": meta["borrowings_ratio"]} if "borrowings_ratio" in meta else {}),
        })
    mapped_tickers = set(by_ticker)
    float_doc = json.loads(FLOAT_PATH.read_text(encoding="utf-8")) if FLOAT_PATH.exists() else {}
    floats = float_doc.get("by_ticker") or {}
    index_doc = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    memberships = index_doc.get("by_ticker") or {}
    names_out = {}
    counts = {"with_holders": 0, "no_holder_on_file": 0, "not_on_13f": 0, "not_stock": 0}
    for ticker, assignment in sorted(universe.items()):
        company = names.get(ticker) or (memberships.get(ticker) or {}).get("company") or ticker
        if structural(ticker):
            counts["not_stock"] += 1
            names_out[ticker] = {"tier": assignment.get("tier_id") or assignment.get("tier"), "company": company, "omitted": "not_stock", "holders": []}
            continue
        if foreign_listing(ticker) and ticker not in mapped_tickers:
            counts["not_on_13f"] += 1
            names_out[ticker] = {"tier": assignment.get("tier_id") or assignment.get("tier"), "company": company, "omitted": "not_on_13f", "holders": []}
            continue
        raw_holders = by_ticker.get(ticker) or []
        merged: dict[str, dict] = {}
        for holder in raw_holders:
            current = merged.get(holder["fund_id"])
            if current is None:
                merged[holder["fund_id"]] = dict(holder)
                continue
            current["market_value"] = round(current["market_value"] + holder["market_value"], 2)
            if holder.get("shares") is not None:
                current["shares"] = (current.get("shares") or 0) + holder["shares"]
        holders = list(merged.values())
        stats = full_stats(holders)
        if holders:
            counts["with_holders"] += 1
        else:
            counts["no_holder_on_file"] += 1
        float_row = floats.get(ticker) or {}
        index_row = memberships.get(ticker) or {}
        shown = sorted(holders, key=lambda holder: -holder["market_value"])
        curated = [holder for holder in shown if holder["kind"] != "bulk_13f"]
        bulk = [holder for holder in shown if holder["kind"] == "bulk_13f"]
        kept = curated + bulk[:max(HOLDER_CAP - len(curated), 0)]
        kept.sort(key=lambda holder: -holder["market_value"])
        truncated = len(shown) > len(kept)
        record = {
            "tier": assignment.get("tier_id") or assignment.get("tier"),
            "company": company,
            "omitted": None,
            "index_tags": index_row.get("current_memberships") or [],
            "float_shares": float_row.get("float_shares"),
            "short_percent_float": float_row.get("short_percent_float"),
            "float_as_of": float_row.get("as_of") or float_doc.get("as_of"),
            "holders": kept,
        }
        if truncated:
            record["full_stats"] = stats
        names_out[ticker] = record
    coverage.update(counts)
    coverage["exceptions"] = book.exceptions[:200]
    coverage["exception_count"] = len(book.exceptions)
    coverage["funds"] = len(book.funds)
    coverage["fund_kinds"] = dict(sorted((kind, sum(1 for item in fund_kind.values() if item == kind)) for kind in set(fund_kind.values())))
    note = coverage.get("holder_set_note")
    return {
        "schema_version": 1,
        "research_only": True,
        "in_base_irr": False,
        "authority": "none",
        "built_at": now_iso(),
        "mode": mode,
        "quarter": "2026Q2",
        "as_of": "2026-10-07",
        "holder_set_note": note,
        "coverage": coverage,
        "names": names_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    universe, universe_set = load_universe()
    names = load_names(universe_set)
    names_by_key: dict[str, list[str]] = defaultdict(list)
    for ticker, company in names.items():
        if company and company != ticker and not structural(ticker):
            names_by_key[company_key(company)].append(ticker)
    cusip_map = {cusip.upper(): ticker.upper() for cusip, ticker in load_cusip_map().items()}
    book = Book()
    coverage = {"universe": len(universe_set), "float_as_of": "2026-08-11", "index_as_of": "2026-10-01"}
    coverage.update(load_local(book, cusip_map, universe_set))
    holders = json.loads(HOLDERS_PATH.read_text(encoding="utf-8"))
    coverage["etf_holdings"] = load_etf_file(book, holders, cusip_map, universe_set)
    mode = "local_only"
    if args.local_only:
        coverage["holder_set_note"] = (
            "Holder set is the specialist books plus six cached advisers. "
            "The large complexes are not in it yet. " + coverage["etf_holdings"] + "."
        )
    else:
        mode = "with_network"
        errors = []
        for adviser in holders.get("advisers") or []:
            try:
                confirm_adviser(adviser)
                status = fetch_adviser_table(adviser, book, cusip_map, universe_set)
                print(f"{adviser['id']}: {status}", flush=True)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ET.ParseError) as error:
                adviser["stale"] = True
                adviser["confirm_error"] = str(error)
                errors.append(f"{adviser['id']}: {error}")
                print(f"{adviser['id']}: FAILED {error}", flush=True)
        try:
            coverage["bulk_13f"] = load_bulk_zip(book, cusip_map, universe_set, names_by_key, {
                cik_padded(row["cik"]): row for row in holders.get("advisers") or [] if row.get("cik")
            })
        except (HTTPError, URLError, TimeoutError, zipfile.BadZipFile, OSError) as error:
            coverage["bulk_13f"] = f"failed: {error}"
            errors.append(str(error))
        try:
            coverage["nport"] = load_nport(book, holders, cusip_map, universe_set)
        except (HTTPError, URLError, TimeoutError, ET.ParseError) as error:
            coverage["nport"] = [str(error)]
            errors.append(str(error))
        coverage["network_errors"] = errors
        coverage["holder_set_note"] = "Large advisers were fetched when the submissions feed confirmed a 13F. " + coverage.get("bulk_13f", "")
        HOLDERS_PATH.write_text(json.dumps(holders, indent=2) + "\n", encoding="utf-8")
    payload = render(book, universe, names, mode, coverage)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(
        f"wrote {OUT_PATH} names={coverage['universe']} with_holders={coverage['with_holders']} "
        f"not_on_13f={coverage['not_on_13f']} not_stock={coverage['not_stock']} funds={coverage['funds']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
