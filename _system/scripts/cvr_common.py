#!/usr/bin/env python3
"""Shared CVR discovery helpers (Parts 2–4).

Used by refresh_cvr_universe.py and check_cvr_universe.py.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
UNIVERSE_PATH = ROOT / "_system" / "reference" / "cvr" / "cvr_universe.json"
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
INBOX_DIR = ROOT / "_system" / "reference" / "cvr" / "inbox"
INBOX_PROCESSED = INBOX_DIR / "processed"
REVIEWS_PENDING = ROOT / "_system" / "reviews" / "pending"
CVR_AGENT_QUEUE = ROOT / "_system" / "data" / "cvr_agent_queue.json"
UA = "MarvinResearchBot/1.0 (single-stock-investments; cvr-refresh; contact: local)"

# Mega-cap acquirers often co-appear on merger 8-Ks; prefer the other ticker.
ACQUIRER_BIAS = {
    "JNJ",
    "BMY",
    "LLY",
    "PFE",
    "MRK",
    "ABBV",
    "AMGN",
    "GILD",
    "AZN",
    "NVO",
    "SNY",
    "RHHBY",
    "TAK",
    "GSK",
    "NVS",
    "TMO",
    "MDT",
    "ABT",
    "BSX",
    "SYK",
    "DHR",
    "UNH",
    "CVS",
    "WBA",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "AAPL",
    "ORCL",
    "IBM",
    "CSCO",
    "INTC",
    "QCOM",
    "TXN",
    "AVGO",
    "BAC",
    "JPM",
    "WFC",
    "C",
    "GS",
    "MS",
    "USB",
    "PNC",
    "TFC",
    "COF",
}

PREFERRED_FORMS = {"8-K", "8-K/A", "DEFM14A", "PREM14A", "S-4", "S-4/A", "SC TO-T", "SC 14D9"}
RISK_FACTOR_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"}

SEC_QUERY_PRIMARY = (
    '"Contingent Value Right" OR "CVR Agreement" OR "contingent value rights"'
)
SEC_QUERY_EXPANDED = (
    '"contingent consideration" OR earnout OR "earn-out" OR '
    '"additional merger consideration" OR "contingent cash consideration"'
)
SEC_QUERY_NON_SEC_FAMILY = (
    'ECIP AND (contingent OR redemption OR "preferred stock") AND '
    '(merger OR acquisition OR "agreement and plan")'
)

TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")


def today() -> str:
    return date.today().isoformat()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def terms_path_for(ticker: str) -> Path:
    return ROOT / ticker / "research" / "cvr_terms.json"


def load_terms(ticker: str) -> dict | None:
    path = terms_path_for(ticker)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def terms_are_complete(terms: dict | None) -> bool:
    """Skeleton stubs are not sleeve-ready."""
    if not terms:
        return False
    if terms.get("stub") is True:
        return False
    if terms.get("terms_complete") is False:
        return False
    # Need an economic anchor.
    if terms.get("max_payout_usd") is None and not terms.get("milestones"):
        return False
    return True


def row_is_sleeve_ready(row: dict) -> bool:
    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return False
    if row.get("sleeve_ready") is True and terms_are_complete(load_terms(ticker)):
        return True
    return terms_are_complete(load_terms(ticker))


def row_is_watch_candidate(row: dict) -> bool:
    """Context-tier names with a folder stub but incomplete terms."""
    ticker = str(row.get("ticker") or "").strip()
    if not ticker or row_is_sleeve_ready(row):
        return False
    terms = load_terms(ticker)
    if terms is not None:
        return True
    return bool(row.get("stub_created") or row.get("source_tier") == "context")


def iter_universe_rows(doc: dict) -> list[dict]:
    return list(doc.get("pre_close_opportunities") or []) + list(
        doc.get("post_close_universe") or []
    )


def http_get_json(url: str, timeout: int = 45) -> dict | list | None:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        print(f"WARN: HTTP JSON fetch failed: {exc}")
        return None


def http_get_text(url: str, timeout: int = 45) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
    ) as exc:
        print(f"WARN: HTTP text fetch failed: {exc}")
        return None


_CIK_CACHE: dict[str, str] | None = None
_TICKER_BY_CIK: dict[str, str] | None = None


def _load_company_tickers() -> tuple[dict[str, str], dict[str, str]]:
    """Return (ticker→cik, cik→ticker) from local cache or SEC."""
    global _CIK_CACHE, _TICKER_BY_CIK
    if _CIK_CACHE is not None and _TICKER_BY_CIK is not None:
        return _CIK_CACHE, _TICKER_BY_CIK

    ticker_to_cik: dict[str, str] = {}
    cik_to_ticker: dict[str, str] = {}
    paths = (
        ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json",
        ROOT / "_system" / "reference" / "securities" / "sec_company_tickers.json",
        ROOT / "_system" / "reference" / "market-data" / "index" / "sec_company_tickers.json",
    )
    for path in paths:
        if not path.exists():
            continue
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(cached, dict) and cached and not isinstance(next(iter(cached.values())), dict):
            # Flat ticker→cik map
            for t, cik in cached.items():
                t_u = str(t).upper()
                c = str(cik).zfill(10)
                ticker_to_cik[t_u] = c
                cik_to_ticker.setdefault(c, t_u)
            continue
        rows = cached.values() if isinstance(cached, dict) else cached
        for row in rows:
            if not isinstance(row, dict):
                continue
            t = str(row.get("ticker") or row.get("symbol") or "").upper()
            cik = row.get("cik_str") or row.get("cik")
            if t and cik:
                c = str(cik).zfill(10)
                ticker_to_cik[t] = c
                cik_to_ticker.setdefault(c, t)

    if not ticker_to_cik:
        payload = http_get_json("https://www.sec.gov/files/company_tickers.json")
        if isinstance(payload, dict):
            for row in payload.values():
                if not isinstance(row, dict):
                    continue
                t = str(row.get("ticker") or "").upper()
                cik = row.get("cik_str") or row.get("cik")
                if t and cik:
                    c = str(cik).zfill(10)
                    ticker_to_cik[t] = c
                    cik_to_ticker.setdefault(c, t)

    _CIK_CACHE = ticker_to_cik
    _TICKER_BY_CIK = cik_to_ticker
    return ticker_to_cik, cik_to_ticker


def resolve_ticker_for_cik(cik: str | int | None) -> str | None:
    if cik is None or cik == "":
        return None
    _, cik_to_ticker = _load_company_tickers()
    return cik_to_ticker.get(str(cik).zfill(10))


def resolve_cik_for_ticker(ticker: str) -> str | None:
    ticker_to_cik, _ = _load_company_tickers()
    return ticker_to_cik.get(str(ticker).upper())


def normalize_tickers(raw) -> list[str]:
    out: list[str] = []
    if raw is None:
        return out
    if isinstance(raw, str):
        raw = [raw]
    for t in raw:
        t = str(t).strip().upper()
        if TICKER_RE.fullmatch(t) and t not in out:
            out.append(t)
    return out


def pick_target_ticker(
    tickers: list[str],
    *,
    filing_cik: str | None = None,
) -> str | None:
    """Prefer filing-entity ticker; deprioritize mega-cap acquirers."""
    if not tickers:
        return None
    filing_ticker = resolve_ticker_for_cik(filing_cik) if filing_cik else None
    if filing_ticker and filing_ticker in tickers:
        return filing_ticker
    non_acq = [t for t in tickers if t not in ACQUIRER_BIAS]
    if non_acq:
        return non_acq[0]
    return tickers[0]


def form_is_preferred(form: str | None) -> bool:
    if not form:
        return True  # unknown — keep, Part 2 filters soft
    f = form.strip().upper()
    if f in RISK_FACTOR_FORMS:
        return False
    if f in PREFERRED_FORMS:
        return True
    # Allow other 8-K-like / proxy variants
    if f.startswith("8-K") or "14A" in f or f.startswith("S-4"):
        return True
    return False


def hit_looks_risk_factor_only(src: dict) -> bool:
    """Cheap heuristic: drop 10-K/10-Q and titles that scream risk-factor boilerplate."""
    form = str(src.get("form") or src.get("forms") or src.get("file_type") or "").upper()
    if form in RISK_FACTOR_FORMS:
        return True
    title = " ".join(
        str(src.get(k) or "")
        for k in ("display_title", "title", "file_description", "period_ending")
    ).lower()
    items = str(src.get("items") or src.get("item") or "").lower()
    # Prefer deal items when present
    if any(x in items for x in ("1.01", "2.01", "8.01", "9.01")):
        return False
    if "risk factor" in title and "agreement" not in title and "merger" not in title:
        return True
    return False


def skeleton_terms(
    ticker: str,
    *,
    accession: str | None = None,
    sec_hint: str | None = None,
    source: str = "sec_full_text",
    company: str | None = None,
) -> dict:
    return {
        "cvr_id": f"{ticker}.CVR_CANDIDATE",
        "as_of": today(),
        "stub": True,
        "terms_complete": False,
        "instrument_label": company or f"{ticker} contingent / CVR candidate",
        "parent_deal": {
            "acquirer": None,
            "acquirer_ticker": None,
            "target": company,
            "target_ticker": ticker,
            "announce_date": None,
            "close_date": None,
        },
        "stage": "pre_close",
        "tradeable": True,
        "tradeable_vehicle": ticker,
        "max_payout_usd": None,
        "milestones": [],
        "sec_links": (
            [{"label": "SEC discovery hit", "url": sec_hint, "accession": accession}]
            if sec_hint
            else []
        ),
        "source": source,
        "source_confidence": "low",
        "extracted_by": "cvr_discover_stub",
        "extraction_date": today(),
        "notes": (
            "Auto stub from discovery. Agent must extract max payout, milestones, "
            "outside date from merger exhibits, then set stub=false and terms_complete=true."
        ),
        "display": {"as_of": today(), "stage": "pre_close", "max_payout_usd": None},
        "last_refresh_utc": utc_now(),
    }


def skeleton_authorized_evidence(ticker: str, sec_hint: str | None) -> dict:
    docs = []
    if sec_hint:
        docs.append({"path": sec_hint, "role": "sec_discovery_hint", "remote": True})
    docs.append(
        {
            "path": f"{ticker}/research/cvr_terms.json",
            "role": "contingent_terms_stub",
        }
    )
    return {
        "ticker": ticker,
        "as_of": today(),
        "primary_documents": docs,
        "notes": "Discovery stub — replace with local merger exhibit paths once downloaded.",
    }


def create_candidate_stub(
    ticker: str,
    *,
    accession: str | None = None,
    sec_hint: str | None = None,
    source: str = "sec_full_text",
    company: str | None = None,
    force: bool = False,
) -> bool:
    """Create ticker folder + skeleton terms/evidence/manifest. Returns True if created."""
    td = ROOT / ticker
    research = td / "research"
    sec_dir = td / "investor-documents" / "sec"
    terms_path = research / "cvr_terms.json"
    if terms_path.exists() and not force:
        return False

    research.mkdir(parents=True, exist_ok=True)
    sec_dir.mkdir(parents=True, exist_ok=True)

    terms_path.write_text(
        json.dumps(
            skeleton_terms(
                ticker,
                accession=accession,
                sec_hint=sec_hint,
                source=source,
                company=company,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    auth_path = research / "authorized_evidence.json"
    if not auth_path.exists() or force:
        auth_path.write_text(
            json.dumps(skeleton_authorized_evidence(ticker, sec_hint), indent=2) + "\n",
            encoding="utf-8",
        )

    # Minimal research_agent_manifest so later agent PRs can clear the gate.
    try:
        from build_research_agent_manifest import build_manifest

        manifest = build_manifest(ticker, "cvr_discovery_stub")
        (research / "research_agent_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft stub path
        (research / "research_agent_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "ticker": ticker,
                    "reason": "cvr_discovery_stub",
                    "ready": False,
                    "primary_evidence_ready": False,
                    "error": str(exc),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    readme = td / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {company or ticker} contingent / CVR candidate ({ticker})\n\n"
            f"**Ticker:** {ticker} | **Market:** US  \n"
            f"**Last updated:** {today()}  \n"
            f"**Stage:** pre-close stub (discovery)\n\n"
            "## Next actions\n\n"
            "1. Pull merger 8-K / DEFM14A / CVR agreement into `investor-documents/sec/`.\n"
            "2. Fill `research/cvr_terms.json` (set `stub=false`, `terms_complete=true`).\n"
            "3. Nightly sync will sleeve onto the CVRs filter.\n",
            encoding="utf-8",
        )
    return True


def fetch_yahoo_price(ticker: str) -> float | None:
    """Reuse ownership_common when available; else chart API."""
    try:
        from ownership_common import fetch_yahoo_price as _fy

        return _fy(ticker)
    except Exception:  # noqa: BLE001
        pass
    sym = (ticker or "").upper().replace(".", "-")
    if not sym or ":" in sym or ".CVR" in (ticker or "").upper():
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    data = http_get_json(url)
    if not isinstance(data, dict):
        return None
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        return float(price) if price is not None else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def post_slack(text: str) -> bool:
    """Optional Slack alert via SLACK_WEBHOOK_URL env/secret."""
    url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
    if not url:
        return False
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
    ) as exc:
        print(f"WARN: Slack notify failed: {exc}")
        return False


def enqueue_cvr_agent_task(ticker: str, *, reason: str) -> None:
    """Append ticker to CVR agent handoff queue (Part 4)."""
    CVR_AGENT_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    doc: dict
    if CVR_AGENT_QUEUE.exists():
        try:
            doc = json.loads(CVR_AGENT_QUEUE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {"tickers": [], "events": []}
    else:
        doc = {"tickers": [], "events": []}
    tickers = [str(t).upper() for t in (doc.get("tickers") or [])]
    t = ticker.upper()
    if t not in tickers:
        tickers.append(t)
    events = list(doc.get("events") or [])
    events.append({"ticker": t, "reason": reason, "queued_at": utc_now()})
    doc["tickers"] = tickers
    doc["events"] = events[-200:]
    doc["updated"] = utc_now()
    CVR_AGENT_QUEUE.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


MILESTONE_PAID_RE = re.compile(
    r"\b(paid|payment\s+made|milestone\s+achieved|cvr\s+payment)\b", re.I
)
MILESTONE_FAILED_RE = re.compile(
    r"\b(expired|lapsed|will\s+not\s+be\s+paid|milestone\s+not\s+achieved|"
    r"outside\s+date\s+passed|terminated)\b",
    re.I,
)
MILESTONE_EXTENDED_RE = re.compile(
    r"\b(extended|extension\s+of|outside\s+date\s+extended)\b", re.I
)


def infer_milestone_status_from_text(text: str) -> str | None:
    if not text:
        return None
    # Order matters: paid beats failed beats extended for noisy docs.
    if MILESTONE_PAID_RE.search(text) and not MILESTONE_FAILED_RE.search(text):
        return "paid"
    if MILESTONE_FAILED_RE.search(text):
        return "failed"
    if MILESTONE_EXTENDED_RE.search(text):
        return "extended"
    return None


# --- Free automatic discovery feeds (no API keys) ---

GOOGLE_NEWS_CVR_QUERY = (
    '"contingent value right" OR "CVR Agreement" OR "earn-out" OR earnout '
    'OR "contingent consideration" merger OR acquisition'
)
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)
SEC_ATOM_8K = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    "&type=8-K&company=&dateb=&owner=include&count=100&output=atom"
)

EXCHANGE_TICKER_RE = re.compile(
    r"\((?:NASDAQ|NYSE|NYSEAMERICAN|AMEX|OTCQX|OTCQB|OTCMKTS|OTC)[:\s]+"
    r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)",
    re.I,
)
PAREN_TICKER_RE = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)")
TICKER_STOPWORDS = {
    "CVR",
    "CEO",
    "CFO",
    "FDA",
    "SEC",
    "USD",
    "IPO",
    "LLC",
    "INC",
    "THE",
    "FOR",
    "AND",
    "NEW",
    "USA",
    "PDF",
    "EPS",
    "GAAP",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "NYSE",
    "AMEX",
    "OTC",
    "PRESS",
    "WIRE",
}


def extract_tickers_from_headline(title: str) -> list[str]:
    """Pull equity symbols from news headlines (free-feed helper)."""
    out: list[str] = []
    if not title:
        return out
    for m in EXCHANGE_TICKER_RE.finditer(title):
        t = m.group(1).upper()
        if t not in TICKER_STOPWORDS and t not in out:
            out.append(t)
    for m in PAREN_TICKER_RE.finditer(title):
        t = m.group(1).upper()
        if t not in TICKER_STOPWORDS and TICKER_RE.fullmatch(t) and t not in out:
            out.append(t)
    return out


def fetch_google_news_cvr_items(*, limit: int = 40) -> list[dict]:
    """Google News RSS — free, no key. Fail-soft → []."""
    import xml.etree.ElementTree as ET
    import urllib.parse

    q = urllib.parse.quote_plus(GOOGLE_NEWS_CVR_QUERY)
    url = GOOGLE_NEWS_RSS.format(q=q)
    text = http_get_text(url)
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        print(f"WARN: Google News RSS parse failed: {exc}")
        return []
    items: list[dict] = []
    for it in root.findall("./channel/item")[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if not title:
            continue
        blob = title.lower()
        if not any(
            k in blob
            for k in (
                "cvr",
                "contingent value",
                "earnout",
                "earn-out",
                "contingent consideration",
                "contingent cash",
            )
        ):
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "published": pub,
                "tickers": extract_tickers_from_headline(title),
            }
        )
    return items


def fetch_sec_atom_cvr_items(*, limit: int = 100) -> list[dict]:
    """SEC current 8-K Atom feed — free. Keyword filter on title/summary."""
    import xml.etree.ElementTree as ET

    text = http_get_text(SEC_ATOM_8K)
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        print(f"WARN: SEC Atom parse failed: {exc}")
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items: list[dict] = []
    for e in root.findall("a:entry", ns)[:limit]:
        title = e.findtext("a:title", default="", namespaces=ns) or ""
        summary = e.findtext("a:summary", default="", namespaces=ns) or ""
        link_el = e.find("a:link", ns)
        href = link_el.get("href") if link_el is not None else None
        blob = f"{title} {summary}".lower()
        if not any(
            k in blob
            for k in (
                "cvr",
                "contingent value",
                "earnout",
                "earn-out",
                "contingent consideration",
            )
        ):
            continue
        # Title format often: "Company Name (CIK) (Filer)"
        cik_m = re.search(r"\((\d{6,10})\)", title)
        cik = cik_m.group(1).zfill(10) if cik_m else None
        ticker = resolve_ticker_for_cik(cik) if cik else None
        items.append(
            {
                "title": title.strip(),
                "link": href,
                "cik": cik,
                "ticker": ticker,
                "summary": summary[:500],
            }
        )
    return items


def clinicaltrials_status(query: str) -> dict | None:
    """ClinicalTrials.gov v2 — free status snapshot for a milestone query."""
    import urllib.parse

    if not query or len(query.strip()) < 3:
        return None
    params = urllib.parse.urlencode(
        {"query.term": query.strip()[:120], "pageSize": "3", "format": "json"}
    )
    url = f"https://clinicaltrials.gov/api/v2/studies?{params}"
    data = http_get_json(url)
    if not isinstance(data, dict):
        return None
    studies = data.get("studies") or []
    if not studies:
        return {"query": query, "n_studies": 0, "statuses": []}
    statuses = []
    for st in studies[:3]:
        proto = (st.get("protocolSection") or {})
        status_mod = proto.get("statusModule") or {}
        id_mod = proto.get("identificationModule") or {}
        statuses.append(
            {
                "nct": id_mod.get("nctId"),
                "title": id_mod.get("briefTitle"),
                "overall_status": status_mod.get("overallStatus"),
                "last_update": status_mod.get("lastUpdatePostDateStruct", {}).get("date")
                if isinstance(status_mod.get("lastUpdatePostDateStruct"), dict)
                else status_mod.get("lastUpdatePostDate"),
            }
        )
    return {"query": query, "n_studies": len(studies), "statuses": statuses}


def openfda_device_510k_hits(device_name: str) -> list[dict]:
    """OpenFDA 510(k) — free device clearance hits (fail-soft)."""
    import urllib.parse

    if not device_name or len(device_name.strip()) < 3:
        return []
    q = urllib.parse.quote(f'device_name:"{device_name.strip()[:80]}"')
    url = f"https://api.fda.gov/device/510k.json?search={q}&limit=3"
    data = http_get_json(url)
    if not isinstance(data, dict):
        return []
    out = []
    for row in data.get("results") or []:
        out.append(
            {
                "k_number": row.get("k_number"),
                "device_name": row.get("device_name"),
                "decision_date": row.get("decision_date"),
                "decision_description": row.get("decision_description"),
            }
        )
    return out
