"""Shared utilities for activist report ingestion and indexing."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
PORTFOLIO_REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
US_TICKER_CONFIG = Path(__file__).resolve().parent / "us_ticker_config.json"
GLOBAL_SCAN_PATH = ROOT / "_system" / "data" / "activist_scan_latest.json"
SCAN_LOG_PATH = ROOT / "_system" / "data" / "activist_scan_log.json"
ACTIVIST_FORMS = frozenset(
    {
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
        "DEFC14A",
        "PREC14A",
        "DFAN14A",
    }
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default if default is not None else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_firm_registry() -> dict:
    return load_json(REGISTRY_PATH, {"firms": []})


def active_firms(*, side: str | None = None) -> list[dict]:
    firms = load_firm_registry().get("firms") or []
    out = [f for f in firms if f.get("active", True)]
    if side:
        out = [f for f in out if f.get("side") in (side, "both")]
    return out


def firm_matchers() -> list[tuple[str, re.Pattern[str]]]:
    matchers: list[tuple[str, re.Pattern[str]]] = []
    for firm in load_firm_registry().get("firms") or []:
        fid = firm.get("id") or ""
        terms = [firm.get("name", "")]
        terms.extend(firm.get("aliases") or [])
        terms.extend(firm.get("sec_filer_patterns") or [])
        seen: set[str] = set()
        for term in terms:
            key = str(term or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            matchers.append((fid, re.compile(re.escape(key), re.I)))
    return matchers


def match_firm_id(text: str) -> str | None:
    if not text:
        return None
    for fid, pattern in firm_matchers():
        if pattern.search(text):
            return fid
    return None


def portfolio_tickers() -> list[str]:
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holdings = reg.get("holdings") or {}
    if holdings:
        return sorted(holdings.keys())
    tickers = []
    skip = {"_system", "dashboard", ".git", ".github", ".cursor", "_external"}
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in skip and not p.name.startswith((".", "_")):
            tickers.append(p.name)
    return sorted(tickers)


def ticker_meta(ticker: str) -> dict:
    ticker = ticker.upper()
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holding = (reg.get("holdings") or {}).get(ticker) or {}
    us_cfg = load_json(US_TICKER_CONFIG, {})
    download = holding.get("download") or {}
    cik = download.get("cik")
    if not cik:
        cik = (us_cfg.get(ticker) or {}).get("cik")
    company = holding.get("company") or ticker
    aliases = {company, ticker}
    for token in re.split(r"[\s,./]+", company):
        if len(token) >= 3:
            aliases.add(token)
    return {
        "ticker": ticker,
        "company": company,
        "cik": str(cik).strip() if cik else None,
        "aliases": sorted(aliases, key=len, reverse=True),
    }


def activist_reports_dir(ticker: str, side: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports" / side


def activist_index_path(ticker: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"


def load_ticker_index(ticker: str) -> dict:
    path = activist_index_path(ticker)
    data = load_json(path, {"ticker": ticker.upper(), "reports": []})
    data.setdefault("ticker", ticker.upper())
    data.setdefault("reports", [])
    return data


def save_ticker_index(ticker: str, index: dict) -> Path:
    path = activist_index_path(ticker)
    index["updated_at"] = now_iso()
    write_json(path, index)
    return path


def report_key(entry: dict) -> str:
    return "|".join(
        [
            entry.get("firm_id") or "",
            entry.get("report_date") or "",
            entry.get("source_url") or "",
            entry.get("local_pdf") or "",
            entry.get("accession") or "",
        ]
    )


def upsert_report(index: dict, entry: dict) -> bool:
    key = report_key(entry)
    reports = index.setdefault("reports", [])
    for i, existing in enumerate(reports):
        if report_key(existing) == key:
            merged = {**existing, **entry}
            if merged != existing:
                reports[i] = merged
                return True
            return False
    reports.append(entry)
    return True


def side_for_firm(firm_id: str, default: str = "long") -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("side") if firm.get("side") != "both" else default
    return default


def firm_name(firm_id: str) -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("name") or firm_id
    return firm_id


def text_matches_ticker(text: str, meta: dict) -> bool:
    hay = text.lower()
    ticker = meta["ticker"].lower()
    if re.search(rf"\b{re.escape(ticker)}\b", hay, re.I):
        return True
    for alias in meta.get("aliases") or []:
        alias = str(alias).strip()
        if len(alias) >= 4 and alias.lower() in hay:
            return True
    return False


def safe_report_filename(firm_id: str, report_date: str, suffix: str, ext: str = ".pdf") -> str:
    date_part = (report_date or date.today().isoformat())[:10]
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", f"{firm_id}_{date_part}_{suffix}").strip("-")
    return f"{stem}{ext}"


def load_global_scan() -> dict:
    return load_json(GLOBAL_SCAN_PATH, {"reports": [], "generated_at": None})


def save_global_scan(payload: dict) -> None:
    write_json(GLOBAL_SCAN_PATH, payload)


def append_scan_log(entry: dict) -> None:
    log = load_json(SCAN_LOG_PATH, {"entries": []})
    log.setdefault("entries", []).append({**entry, "at": now_iso()})
    log["entries"] = log["entries"][-500:]
    write_json(SCAN_LOG_PATH, log)
