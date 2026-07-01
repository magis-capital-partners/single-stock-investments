#!/usr/bin/env python3
"""Build portfolio dashboard JSON from ticker folders and _system/portfolio/holdings.md."""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from dated_md import dated_md_label, dated_md_sort_key, latest_dated_md  # noqa: E402
from document_date import catalog_sort_key, infer_document_period  # noqa: E402
from document_store import best_document_label, best_document_url, document_id_for_ref  # noqa: E402
from market_order import sort_market_filters, sort_markets  # noqa: E402
from valuation_synthesis import website_implied_irr  # noqa: E402

DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "dashboard_data.json"
RESEARCH_MEMORY_PATH = DATA_DIR / "research_memory.json"
DOCUMENT_REGISTRY_PATH = DATA_DIR / "document_registry.json"
DOCUMENT_CATALOG_PATH = DATA_DIR / "document_catalog.json"
DRIVE_FOLDER_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_folder_index.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"
ONBOARD_WORKFLOW = "marvin-onboard.yml"


def github_blob_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/blob/main/{rel_path.replace(chr(92), '/')}"


def github_tree_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/tree/main/{rel_path.replace(chr(92), '/').rstrip('/')}"


def github_raw_url(rel_path: str) -> str:
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{rel_path.replace(chr(92), '/')}"


def source_document_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    clean = str(ref).strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://")):
        return clean
    base = clean.split("#", 1)[0].replace("\\", "/")
    suffix = f"#{clean.split('#', 1)[1]}" if "#" in clean else ""
    path = ROOT / base
    candidates: list[Path] = []
    if base.endswith(".pdf.txt"):
        candidates.append(ROOT / base[: -len(".txt")])
    if path.suffix.lower() in {".txt", ".md"}:
        candidates.append(path.with_suffix(".pdf"))
    if path.suffix.lower() != ".json":
        candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.relative_to(ROOT)).replace("\\", "/") + suffix
    return clean


DATED_MD_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.md$")


# Known metadata fallback when holdings.md is sparse
TICKER_META = {
    "8697.T": {"company": "Japan Exchange Group", "market": "JP", "exchange": "TSE"},
    "3905.T": {"company": "DataSection Co., Ltd.", "market": "JP", "exchange": "TSE"},
    "AMZN": {"company": "Amazon.com", "market": "US", "exchange": "NASDAQ"},
    "APLD": {"company": "Applied Digital", "market": "US", "exchange": "NASDAQ"},
    "BN": {"company": "Brookfield Corporation", "market": "US", "exchange": "NYSE"},
    "CPRT": {"company": "Copart", "market": "US", "exchange": "NASDAQ"},
    "CSGP": {"company": "CoStar Group", "market": "US", "exchange": "NASDAQ"},
    "CSU": {"company": "Constellation Software", "market": "CA", "exchange": "TSX"},
    "DHR": {"company": "Danaher Corporation", "market": "US", "exchange": "NYSE"},
    "FRMO": {"company": "FRMO Corporation", "market": "US", "exchange": "OTC"},
    "GOOGL": {"company": "Alphabet Inc.", "market": "US", "exchange": "NASDAQ"},
    "ICE": {"company": "Intercontinental Exchange", "market": "US", "exchange": "NYSE"},
    "KEWL": {"company": "Keweenaw Land Association", "market": "US", "exchange": "OTC Pink"},
    "OTCM": {"company": "OTC Markets Group", "market": "US", "exchange": "OTCQX"},
    "QDEL": {"company": "QuidelOrtho", "market": "US", "exchange": "NASDAQ"},
    "SPGI": {"company": "S&P Global", "market": "US", "exchange": "NYSE"},
    "TEQ.ST": {"company": "Teqnion AB", "market": "SE", "exchange": "Nasdaq First North"},
    "WBI": {"company": "WaterBridge Infrastructure", "market": "US", "exchange": "NYSE"},
    "SJT": {"company": "San Juan Basin Royalty Trust", "market": "US", "exchange": "NYSE"},
}


SKIP_TICKER_DIRS = {"_system", "dashboard", ".git", ".github", ".cursor", "_external"}


def list_tickers() -> list[str]:
    """Registry holdings are source of truth; folder scan is fallback only."""
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    if holdings:
        return sorted(holdings.keys())
    tickers = []
    for p in ROOT.iterdir():
        if not p.is_dir():
            continue
        if p.name in SKIP_TICKER_DIRS or p.name.startswith(("_", ".")):
            continue
        tickers.append(p.name)
    return sorted(tickers)


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"holdings": {}, "watchlist": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def parse_holdings() -> dict[str, dict]:
    reg = load_registry()
    meta: dict[str, dict] = {}
    for ticker, h in (reg.get("holdings") or {}).items():
        meta[ticker] = {
            "company": h.get("company", ticker),
            "market": h.get("market", "—"),
            "exchange": h.get("exchange", "—"),
        }
    if meta:
        return meta
    holdings_path = ROOT / "_system" / "portfolio" / "holdings.md"
    meta: dict[str, dict] = {}
    if not holdings_path.exists():
        return meta
    in_holdings_table = False
    for line in holdings_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith("| Ticker | Folder |"):
            in_holdings_table = True
            continue
        if not in_holdings_table or not line.startswith("|"):
            continue
        if line.startswith("|--------"):
            continue
        parts = [c.strip() for c in line.split("|")[1:-1]]
        if len(parts) >= 4 and parts[0] not in ("—", "-"):
            meta[parts[0]] = {
                "company": parts[2],
                "market": parts[3],
            }
    return meta


def onboard_status(ticker_dir: Path) -> dict | None:
    path = ticker_dir / ".onboard_status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def reconcile_onboard_status(ticker_dir: Path, pdf_count: int) -> dict | None:
    """Heal stale failed onboard when primary PDFs exist (e.g. partial BSE after CDN 403)."""
    status = onboard_status(ticker_dir)
    if not status or status.get("phase") != "failed" or pdf_count < 1:
        return status
    healed = {
        "phase": "complete",
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": None,
        "download_detail": (
            f"partial IR reconciled ({pdf_count} PDFs on disk); prior: {status.get('error', '')}"
        ).strip(),
        "ir_gap": True,
        "deep_dive_pending": status.get("deep_dive_pending", True),
    }
    path = ticker_dir / ".onboard_status.json"
    path.write_text(json.dumps(healed, indent=2) + "\n", encoding="utf-8")
    return healed


def build_watchlist_rows(watchlist: dict) -> list[dict]:
    rows = []
    for ticker, w in sorted(watchlist.items()):
        rows.append(
            {
                "ticker": ticker,
                "company": w.get("company", ticker),
                "market": w.get("market", "—"),
                "notes": w.get("notes", ""),
                "added": w.get("added"),
                "status": "watchlist",
            }
        )
    return rows


def has_download_script(ticker_dir: Path) -> tuple[bool, str | None]:
    patterns = [
        ticker_dir / "_scripts" / "download_and_organize.ps1",
        ticker_dir / "investor-documents" / "download_*_investor_docs.py",
    ]
    ps1 = ticker_dir / "_scripts" / "download_and_organize.ps1"
    if ps1.exists():
        return True, str(ps1.relative_to(ROOT))
    scripts_dir = ticker_dir / "_scripts"
    if scripts_dir.exists():
        for script in scripts_dir.glob("download*"):
            if script.is_file():
                return True, str(script.relative_to(ROOT))
    for py in (ticker_dir / "investor-documents").glob("download_*_investor_docs.py"):
        return True, str(py.relative_to(ROOT))
    for py in ticker_dir.rglob("download_*.py"):
        if "_system" not in py.parts:
            return True, str(py.relative_to(ROOT))
    return False, None


def count_pdfs(ticker_dir: Path) -> int:
    return sum(1 for _ in ticker_dir.rglob("*.pdf"))


def source_type_label(source_type: str | None) -> str:
    labels = {
        "superinvestor_letter": "Letters",
        "company_document": "Company",
        "third_party": "VIC / third party",
        "sumzero_research": "SumZero",
        "research": "Research",
        "dropbox_ingestion": "Dropbox ingestion",
        "pdf": "Other PDFs",
    }
    return labels.get(source_type or "", str(source_type or "Other").replace("_", " ").title())


def catalog_ticker(doc: dict) -> str | None:
    folder = str(doc.get("drive_folder_path") or "")
    parts = [p for p in folder.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Single Stocks":
        return parts[1]
    local = str(doc.get("local_pdf_path") or "")
    first = local.split("/", 1)[0]
    if first and (ROOT / first).is_dir() and first not in SKIP_TICKER_DIRS and not first.startswith((".", "_")):
        return first
    return None


def catalog_quarter(doc: dict) -> str | None:
    folder = str(doc.get("drive_folder_path") or "")
    parts = [p for p in folder.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Letters":
        return parts[1]
    local = str(doc.get("local_pdf_path") or "")
    m = re.search(r"superinvestor-letters/(\d{4})Q([1-4])/", local)
    if m:
        return f"{m.group(1)} Q{m.group(2)}"
    return None


QUARTER_PATTERNS = [
    re.compile(r"(?<!\d)(20\d{2})\s*Q([1-4])(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})\s*([1-4])Q(?:\s+Letters)?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})Q([1-4])(?!\d)", re.IGNORECASE),
]


def normalize_quarter_id(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in QUARTER_PATTERNS:
        m = pattern.search(text)
        if m:
            return f"{m.group(1)}Q{m.group(2)}"
    return None


def quarter_label(quarter_id: str) -> str:
    m = re.match(r"^(20\d{2})Q([1-4])$", quarter_id)
    if not m:
        return quarter_id
    return f"Q{m.group(2)} {m.group(1)}"


def build_time_periods(rows: list[dict], folders: dict) -> dict:
    by_quarter: dict[str, dict] = {}

    def bucket(quarter_id: str) -> dict:
        year, q = int(quarter_id[:4]), int(quarter_id[-1])
        return by_quarter.setdefault(
            quarter_id,
            {
                "id": quarter_id,
                "label": quarter_label(quarter_id),
                "year": year,
                "quarter": q,
                "document_count": 0,
                "source_folder_count": 0,
                "source_folder_url": None,
            },
        )

    for row in rows:
        qid = row.get("document_quarter") or normalize_quarter_id(row.get("quarter"))
        if qid:
            bucket(qid)["document_count"] += 1

    for path, meta in (folders or {}).items():
        qid = normalize_quarter_id(path)
        if not qid:
            continue
        b = bucket(qid)
        b["source_folder_count"] += 1
        if not b.get("source_folder_url"):
            b["source_folder_url"] = (meta or {}).get("webViewLink")

    quarters = sorted(by_quarter.values(), key=lambda q: (q["year"], q["quarter"]), reverse=True)
    years = sorted({q["year"] for q in quarters}, reverse=True)
    return {
        "latest_quarter": quarters[0]["id"] if quarters else None,
        "years": years,
        "available_quarters": quarters,
    }


def load_drive_folder_index() -> dict:
    if not DRIVE_FOLDER_INDEX_PATH.exists():
        return {"folders": {}, "generated_at": None}
    try:
        return json.loads(DRIVE_FOLDER_INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"folders": {}, "generated_at": None}


def folder_url(folder_id: str | None) -> str | None:
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None


def build_document_catalog(document_registry: dict | None) -> dict | None:
    if not isinstance(document_registry, dict):
        return None
    docs = document_registry.get("documents") or []
    folder_index = load_drive_folder_index()
    folders = folder_index.get("folders") or {}
    rows: list[dict] = []
    by_source: Counter[str] = Counter()
    by_ticker: Counter[str] = Counter()
    by_quarter: Counter[str] = Counter()
    for doc in docs:
        source_type = doc.get("source_type") or "pdf"
        ticker = catalog_ticker(doc)
        period = infer_document_period(doc)
        quarter = period.quarter_display or catalog_quarter(doc)
        folder_path = doc.get("drive_folder_path")
        row = {
            "document_id": doc.get("document_id"),
            "title": doc.get("title"),
            "ticker": ticker,
            "quarter": quarter,
            "document_date": period.document_date,
            "document_year": period.document_year,
            "document_quarter": period.document_quarter,
            "period_label": period.period_label,
            "period_source": period.period_source,
            "source_type": source_type,
            "source_label": source_type_label(source_type),
            "drive_folder_path": folder_path,
            "drive_folder_id": doc.get("drive_folder_id"),
            "drive_folder_url": folder_url(doc.get("drive_folder_id")),
            "drive_web_view_link": doc.get("drive_web_view_link"),
            "modified_at": doc.get("modified_at"),
            "size_bytes": doc.get("size_bytes"),
        }
        if folder_path and folder_path in folders:
            row["drive_folder_id"] = folders[folder_path].get("id") or row.get("drive_folder_id")
            row["drive_folder_url"] = folders[folder_path].get("webViewLink") or folder_url(row.get("drive_folder_id"))
        rows.append(row)
        by_source[source_type] += 1
        if ticker:
            by_ticker[ticker] += 1
        if quarter:
            by_quarter[quarter] += 1
        elif period.document_quarter:
            by_quarter[period.quarter_display or quarter_label(period.document_quarter)] += 1
    rows.sort(key=catalog_sort_key)
    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry_generated_at": document_registry.get("generated_at"),
        "folder_index_generated_at": folder_index.get("generated_at"),
        "time_periods": build_time_periods(rows, folders),
        "summary": {
            "document_count": len(rows),
            "uploaded_count": (document_registry.get("summary") or {}).get("uploaded_count", 0),
            "pending_upload_count": (document_registry.get("summary") or {}).get("pending_upload_count", 0),
            "by_source_type": dict(sorted(by_source.items())),
            "by_ticker": dict(sorted(by_ticker.items())),
            "by_quarter": dict(sorted(by_quarter.items(), reverse=True)),
        },
        "documents": rows,
    }
    DOCUMENT_CATALOG_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def attach_pdf_store_rows(rows: list[dict], catalog: dict | None) -> None:
    if not isinstance(catalog, dict):
        return
    folders = (load_drive_folder_index().get("folders") or {})
    by_ticker = ((catalog.get("summary") or {}).get("by_ticker") or {})
    for row in rows:
        ticker = row.get("ticker")
        ticker_folder = folders.get(f"Single Stocks/{ticker}") or {}
        row["pdf_store"] = {
            "count": int(by_ticker.get(ticker, 0) or 0),
            "drive_folder_path": f"Single Stocks/{ticker}",
            "drive_folder_id": ticker_folder.get("id"),
            "drive_folder_url": ticker_folder.get("webViewLink") or folder_url(ticker_folder.get("id")),
        }


def count_sec_filings(ticker_dir: Path) -> int:
    sec = ticker_dir / "investor-documents" / "sec-edgar"
    if sec.exists():
        return sum(1 for f in sec.iterdir() if f.is_file())
    return 0


def last_download(ticker_dir: Path) -> str | None:
    log = ticker_dir / "_download_log.txt"
    if not log.exists():
        return None
    lines = [ln.strip() for ln in log.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1]
    m = re.match(r"(\d{4}-\d{2}-\d{2}T[\d:.+-]+)", last)
    if m:
        return m.group(1)[:10]
    return None


def last_research(ticker_dir: Path) -> str | None:
    research = ticker_dir / "research"
    if not research.exists():
        return None
    files = [f for f in research.rglob("*") if f.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def load_classification() -> dict[str, dict]:
    if not CLASS_PATH.exists():
        return {}
    return json.loads(CLASS_PATH.read_text(encoding="utf-8"))


def load_investment_sleeve_index() -> tuple[dict[str, str], dict[str, str]]:
    """Map ticker -> sleeve id and sleeve id -> display label."""
    if not SLEEVES_PATH.exists():
        return {}, {}
    try:
        doc = json.loads(SLEEVES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, {}
    ticker_to_sleeve: dict[str, str] = {}
    labels: dict[str, str] = {}
    for sleeve_id, meta in (doc.get("sleeves") or {}).items():
        labels[sleeve_id] = meta.get("label") or sleeve_id
        for ticker in meta.get("tickers") or []:
            ticker_to_sleeve[str(ticker).upper()] = sleeve_id
    return ticker_to_sleeve, labels


_INVESTMENT_SLEEVE_INDEX, _INVESTMENT_SLEEVE_LABELS = load_investment_sleeve_index()


def parse_classification_from_thesis(ticker_dir: Path) -> dict | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    fields = {}
    for key, label in [
        ("archetype", r"Archetype"),
        ("moat", r"Moat"),
        ("dhando", r"Dhando"),
        ("stance", r"Stance"),
        ("cycle", r"Cycle"),
        ("implied_irr", r"Implied 7yr IRR"),
        ("irr_method", r"IRR method"),
        ("lawrence_bucket", r"Lawrence bucket"),
    ]:
        m = re.search(rf"\*\*{label}\*\*[^|]*\|\s*([^\|]+)", text)
        if m:
            fields[key] = m.group(1).strip()
    return fields if fields else None


def parse_irr_pct(implied: str | None) -> float | None:
    if not implied or implied in ("pending", "—", "-", None):
        return None
    m = re.match(r"(-?\d+(?:\.\d+)?)", str(implied).strip())
    return float(m.group(1)) if m else None


def load_valuation(ticker_dir: Path) -> dict | None:
    for name in ("valuation.json", "irr_model.json"):
        path = ticker_dir / "research" / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def classification_for(ticker: str, ticker_dir: Path, portfolio: dict[str, dict]) -> dict:
    from_thesis = parse_classification_from_thesis(ticker_dir)
    from_json = portfolio.get(ticker, {})
    merged = {**from_json, **(from_thesis or {})}
    defaults = {
        "archetype": "unknown",
        "moat": "unproven",
        "dhando": "pending",
        "stance": "watch",
        "cycle": "—",
        "implied_irr": "pending",
        "irr_method": "pending",
        "lawrence_bucket": "—",
        "investment_sleeve": "—",
        "investment_sleeve_label": "—",
    }
    out = {k: merged.get(k, defaults[k]) for k in defaults}
    val = load_valuation(ticker_dir)
    if val:
        if not val.get("ticker"):
            val["ticker"] = ticker_dir.name
        irr_web = website_implied_irr(val)
        inputs = val.get("classification_inputs") or {}
        for key in ("archetype", "moat", "dhando", "cycle", "investment_sleeve"):
            if inputs.get(key) and inputs[key] not in ("-", "—", "pending"):
                out[key] = inputs[key]
        if irr_web.get("display"):
            out["implied_irr"] = irr_web["display"]
        method = val.get("method", val.get("irr_method"))
        if method and out.get("irr_method") == "pending":
            out["irr_method"] = method
        bucket = val.get("lawrence_bucket")
        if bucket and out.get("lawrence_bucket") == "—":
            out["lawrence_bucket"] = bucket
        proposal = val.get("stance_proposal", {})
        if proposal.get("suggested"):
            out["stance_proposed"] = proposal["suggested"]
        if proposal.get("irr_band"):
            out["irr_band"] = proposal["irr_band"]
        approved = val.get("approved_stance") or proposal.get("approved_stance")
        if approved:
            out["stance"] = approved
        elif proposal.get("suggested") and proposal["suggested"] != "pending":
            out["stance"] = proposal["suggested"]
        if val.get("as_of"):
            out["analysis_as_of"] = val["as_of"]
        if irr_web.get("base_pct") is not None:
            out["analysis_irr_pct"] = float(irr_web["base_pct"])
        else:
            out["analysis_irr_pct"] = parse_irr_pct(out.get("implied_irr"))
        gate_pct = irr_web.get("lawrence_stance_gate_pct")
        if gate_pct is not None:
            out["filing_irr_ref"] = f"{gate_pct}% (stance gate)"
        elif irr_web.get("falsifier_adjusted_pct") is not None:
            out["filing_irr_ref"] = f"{irr_web['falsifier_adjusted_pct']}% (falsifier-adjusted)"
        if irr_web.get("synthesis_status") == "complete":
            out["irr_source"] = "total_synthesis"
    sleeve_id = _INVESTMENT_SLEEVE_INDEX.get(ticker.upper())
    if sleeve_id and out.get("investment_sleeve") in ("—", "-", "pending", None, ""):
        out["investment_sleeve"] = sleeve_id
    if out.get("investment_sleeve") and out["investment_sleeve"] not in ("—", "-", "pending"):
        out["investment_sleeve_label"] = _INVESTMENT_SLEEVE_LABELS.get(
            out["investment_sleeve"], out["investment_sleeve"]
        )
    return out


def valuation_human_review(ticker_dir: Path) -> dict | None:
    val = load_valuation(ticker_dir)
    if not val:
        return None
    approved = val.get("approved_stance")
    proposal = val.get("stance_proposal") or {}
    override = val.get("override_reason") or proposal.get("override_reason")
    hr = val.get("human_review") or {}
    if not approved and not override and not hr:
        return None
    return {
        "approved_stance": approved,
        "model_stance": proposal.get("suggested"),
        "override_reason": override,
        "entry_band_15pct": hr.get("entry_band_15pct"),
        "live_price_confirmed": hr.get("live_price_confirmed"),
        "approved_date": hr.get("approved_date"),
        "notes": hr.get("notes"),
    }


def valuation_total_return_panel(ticker: str, ticker_dir: Path) -> dict | None:
    val = load_valuation(ticker_dir)
    if not val:
        return {
            "ticker": ticker,
            "status": "missing",
            "error": "no_valuation_json",
            "chart_github_url": None,
            "chart_raw_url": None,
            "panel_github_url": None,
        }
    panel = val.get("total_return_panel") or {}
    panel_path = ticker_dir / "research" / "total_return_panel.json"
    panel_file = None
    if panel_path.exists():
        try:
            panel_file = json.loads(panel_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            panel_file = None
    merged = {}
    if isinstance(panel_file, dict):
        merged.update(panel_file)
    if isinstance(panel, dict):
        merged.update(panel)
    if not merged:
        return {
            "ticker": ticker,
            "status": "missing",
            "error": "panel_not_built",
            "chart_github_url": None,
            "chart_raw_url": None,
            "panel_github_url": None,
        }
    chart_rel = merged.get("chart")
    panel_rel = merged.get("panel_json")
    merged["chart_github_url"] = (
        github_blob_url(chart_rel) if chart_rel else None
    )
    merged["chart_raw_url"] = (
        github_raw_url(chart_rel) if chart_rel else None
    )
    merged["panel_github_url"] = (
        github_blob_url(panel_rel) if panel_rel else None
    )
    merged["ticker"] = ticker
    return merged


def thesis_status(ticker_dir: Path) -> str:
    """Legacy alias — returns archetype for backward compatibility."""
    c = parse_classification_from_thesis(ticker_dir)
    if c and c.get("archetype"):
        return c["archetype"]
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return "unknown"
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\*\*Status:\*\*\s*(\w+)", text)
    return m.group(1).lower() if m else "unknown"


def one_line_thesis(ticker_dir: Path) -> str | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## One-line thesis\s*\n\s*\n(.+?)(?:\n\n|\Z)", text, re.DOTALL)
    if not m:
        return None
    return re.sub(r"\*\*", "", m.group(1).strip())


STALE_THESIS_PHRASE = "pending marvin deep dive"
EXEC_SUMMARY_RE = re.compile(
    r"## Executive summary\s*\n+(?!\s*##)(.+?)(?:\n\n---|\n\n## )",
    re.DOTALL | re.IGNORECASE,
)


def display_one_line_thesis(ticker_dir: Path, deep_dive: dict | None) -> str | None:
    thesis = one_line_thesis(ticker_dir)
    if thesis and STALE_THESIS_PHRASE not in thesis.lower():
        return thesis
    summary = (deep_dive or {}).get("executive_summary")
    if summary:
        first = re.match(r"([^.!?]+[.!?])", summary.strip())
        return first.group(1).strip() if first else summary[:200]
    return thesis


def _research_links(ticker: str, ticker_dir: Path) -> dict:
    research = ticker_dir / "research"
    links = {
        "folder": github_tree_url(f"{ticker}/"),
        "readme": github_blob_url(f"{ticker}/README.md") if (ticker_dir / "README.md").exists() else None,
        "thesis": github_blob_url(f"{ticker}/research/thesis.md")
        if (research / "thesis.md").exists()
        else None,
        "valuation": github_blob_url(f"{ticker}/research/valuation.json")
        if (research / "valuation.json").exists()
        else None,
        "adversarial": None,
    }
    if research.is_dir():
        adv = latest_dated_md(research, "adversarial")
        if adv:
            rel = str(adv.relative_to(ROOT)).replace("\\", "/")
            links["adversarial"] = github_blob_url(rel)
    return links


def latest_deep_dive(ticker_dir: Path, classification: dict) -> dict | None:
    research = ticker_dir / "research"
    if not research.exists():
        return None
    path = latest_dated_md(research, "deep_dive")
    if not path:
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    date_m = re.search(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$", path.name)
    dive_date = date_m.group(1) if date_m else None

    summary = None
    sm = EXEC_SUMMARY_RE.search(text)
    if sm:
        summary = re.sub(r"\*\*", "", sm.group(1).strip())
        if len(summary) > 600:
            summary = summary[:597] + "..."

    dive_stance = classification.get("stance", "watch")
    sm_stance = re.search(r"\*\*Stance\*\*[^|]*\|\s*(\w+)", text)
    if sm_stance:
        dive_stance = sm_stance.group(1).strip()

    return {
        "path": rel,
        "date": dive_date,
        "stance": dive_stance,
        "executive_summary": summary,
        "github_url": f"https://github.com/GoldmanDrew/single-stock-investments/blob/main/{rel}",
    }


def recent_files(ticker_dir: Path, limit: int = 5) -> list[dict]:
    skip_dirs = {"research", ".git"}
    files = []
    for f in ticker_dir.rglob("*"):
        if not f.is_file():
            continue
        if any(part.startswith("_") and part != "_scripts" for part in f.relative_to(ticker_dir).parts):
            if f.suffix.lower() not in {".pdf", ".htm", ".html"}:
                continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("_system"):
            continue
        files.append(f)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        out.append({
            "path": str(f.relative_to(ROOT)).replace("\\", "/"),
            "name": f.name,
            "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
            "type": f.suffix.lower().lstrip("."),
            "github_url": github_blob_url(str(f.relative_to(ROOT)).replace("\\", "/")),
        })
    return out


def recent_developments(ticker_dir: Path, ticker: str) -> list[dict]:
    devs: list[dict] = []

    manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
    manifest_rows: list[dict] = []
    if manifest.exists():
        try:
            raw_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(raw_manifest, list):
                manifest_rows = [r for r in raw_manifest if isinstance(r, dict)]
            else:
                manifest_rows = []
            rows = sorted(manifest_rows, key=lambda r: r.get("filingDate", ""), reverse=True)
            for row in rows[:5]:
                if row.get("form", "").startswith("8-K") and not row.get("exhibit"):
                    devs.append({
                        "date": row.get("filingDate"),
                        "type": "8-K",
                        "label": f"{row.get('form')} filed {row.get('filingDate')}",
                        "source": "SEC",
                        "url": row.get("url"),
                    })
        except json.JSONDecodeError:
            pass

    research = ticker_dir / "research"
    dive_paths: list[Path] = []
    if research.exists():
        dive_paths = sorted(
            research.glob("deep_dive_*.md"), key=dated_md_sort_key, reverse=True
        )[:2]
        for f in dive_paths:
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            devs.append({
                "date": dated_md_label(f),
                "type": "deep_dive",
                "label": f"Deep dive — {f.stem.replace('deep_dive_', '')}",
                "source": "Marvin",
                "url": github_blob_url(rel),
            })
        reports = research / "reports"
        if reports.exists():
            for f in sorted(reports.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
                devs.append({
                    "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "type": "research",
                    "label": f.name.replace("_", " ").replace(".md", ""),
                    "source": "Marvin",
                })

    for rf in recent_files(ticker_dir, limit=3):
        if rf["type"] == "pdf" and not any(d.get("label", "").endswith(rf["name"]) for d in devs):
            devs.append({
                "date": rf["date"],
                "type": "document",
                "label": rf["name"],
                "source": "local",
            })

    devs.sort(key=lambda d: d.get("date") or "", reverse=True)
    return devs[:6]


def completeness_score(row: dict) -> int:
    score = 0
    if row["readme"]:
        score += 20
    if row["download_script"]:
        score += 20
    if row["research_dir"]:
        score += 15
    primary_docs = row["pdf_count"] + row.get("sec_filings", 0)
    if primary_docs >= 10:
        score += 15
    if row["last_download"]:
        score += 15
    if row["index_file"]:
        score += 15
    return min(score, 100)


def has_index(ticker_dir: Path) -> bool:
    return (ticker_dir / "INDEX.csv").exists() or (ticker_dir / "document-index.csv").exists()


def transcript_summary(ticker: str, ticker_dir: Path) -> dict:
    """Verified transcript + earnings fields for dashboard (no unverified projections)."""
    manifest_path = ticker_dir / "investor-documents" / "TRANSCRIPT_MANIFEST.json"
    entries: list[dict] = []
    if manifest_path.exists():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8")).get("entries") or []
        except json.JSONDecodeError:
            entries = []

    earnings_path = ticker_dir / "research" / "evidence" / "earnings_calendar.json"
    earnings_events: list[dict] = []
    if earnings_path.exists():
        try:
            earnings_events = json.loads(earnings_path.read_text(encoding="utf-8")).get("events") or []
        except json.JSONDecodeError:
            earnings_events = []

    tx_sorted = sorted(
        [e for e in entries if e.get("event_type") in ("earnings", "other")],
        key=lambda e: (e.get("call_date") or "", e.get("downloaded_at") or ""),
        reverse=True,
    )
    latest_tx = tx_sorted[0] if tx_sorted else None

    reported = [e for e in earnings_events if e.get("reported") and e.get("verified")]
    reported.sort(key=lambda e: e.get("date") or "", reverse=True)
    latest_er = reported[0] if reported else None

    gap = False
    if latest_er and latest_tx:
        gap = (
            latest_er.get("fiscal_period")
            and latest_tx.get("fiscal_period")
            and latest_er.get("fiscal_period") != latest_tx.get("fiscal_period")
            and (latest_er.get("date") or "") > (latest_tx.get("call_date") or "")
        )
    elif latest_er and not latest_tx:
        gap = True

    return {
        "transcript_count": len(entries),
        "latest_transcript_date": latest_tx.get("call_date") if latest_tx else None,
        "latest_transcript_path": latest_tx.get("canonical_path") if latest_tx else None,
        "latest_reported_earnings_date": latest_er.get("date") if latest_er else None,
        "latest_reported_fiscal_period": latest_er.get("fiscal_period") if latest_er else None,
        "earnings_verified": bool(latest_er),
        "transcript_gap": gap,
    }


def load_lenses(ticker_dir: Path) -> dict | None:
    path = ticker_dir / "research" / "lenses.json"
    return _load_json(path)


def load_insights_for_ticker(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("by_ticker") or {}
    return by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []


SOURCE_PRIORITY = {
    "filing": 0,
    "earnings": 1,
    "insider": 2,
    "superinvestor_letter": 3,
    "news": 4,
    "sumzero_research": 5,
    "third_party": 6,
    "macro": 7,
    "theme": 8,
}


def insight_evidence_url(evidence_ref: str | None) -> str | None:
    if not evidence_ref:
        return None
    ref = source_document_ref(evidence_ref)
    if not ref:
        return None
    return best_document_url(ref, GITHUB_REPO)


def load_letter_discussants(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("ticker_discussants") or {}
    rows = by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        source_ref = row.get("source_document") or source_document_ref(row.get("source_file"))
        row["source_document"] = source_ref
        row["evidence_url"] = insight_evidence_url(source_ref) or row.get("evidence_url")
        row["evidence_label"] = row.get("evidence_label") or best_document_label(source_ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(source_ref)
        out.append(row)
    return out


def enrich_ticker_insights(raw: list[dict], limit: int = 12) -> list[dict]:
    out: list[dict] = []
    for r in raw:
        row = dict(r)
        row["evidence_url"] = insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url")
        if not row.get("evidence_label"):
            ref = source_document_ref(row.get("evidence_ref"))
            row["evidence_label"] = best_document_label(ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref"))
        out.append(row)
    out.sort(key=lambda x: x.get("as_of") or "", reverse=True)
    out.sort(key=lambda x: SOURCE_PRIORITY.get(x.get("source", ""), 9))
    out.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
    return out[:limit]


def load_events_for_ticker(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("events_by_ticker") or {}
    rows = by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        row["evidence_url"] = insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url")
        if not row.get("evidence_label"):
            ref = source_document_ref(row.get("evidence_ref"))
            row["evidence_label"] = best_document_label(ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref"))
        out.append(row)
    return out


def insight_date(row: dict) -> str:
    return str(row.get("observed_at") or row.get("as_of") or "")


def insight_score(row: dict) -> int:
    try:
        return int(row.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def insight_claim(row: dict) -> str:
    return str(row.get("summary") or row.get("claim") or row.get("title") or "").strip()


def days_since_iso(value: str | None) -> int | None:
    if not value:
        return None
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.now(timezone.utc).date() - d).days


def best_insight(rows: list[dict], predicate) -> dict | None:
    matches = [r for r in rows if predicate(r)]
    if not matches:
        return None
    matches.sort(key=lambda r: (insight_score(r), insight_date(r)), reverse=True)
    return matches[0]


def latest_insight(rows: list[dict]) -> dict | None:
    dated = [r for r in rows if insight_date(r)]
    if not dated:
        return best_insight(rows, lambda _r: True)
    dated.sort(key=lambda r: (insight_date(r), insight_score(r)), reverse=True)
    return dated[0]


def compact_insight(row: dict | None) -> dict | None:
    if not row:
        return None
    source = row.get("source")
    label = row.get("source_label") or source or "Insight"
    return {
        "id": row.get("id") or f"{source}:{row.get('event_type') or row.get('ref') or insight_date(row)}",
        "source": source,
        "source_label": row.get("source_label") or source or "Insight",
        "source_name": row.get("source_name") or row.get("fund") or row.get("publisher"),
        "event_type": row.get("event_type"),
        "impact_axis": row.get("impact_axis"),
        "date": insight_date(row) or None,
        "direction": row.get("direction") or "neutral",
        "confidence": row.get("confidence") or "med",
        "score": insight_score(row),
        "title": row.get("title") or str(label),
        "summary": insight_claim(row)[:320],
        "evidence_url": insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url"),
        "evidence_label": row.get("evidence_label") or best_document_label(row.get("evidence_ref")),
        "evidence_document_id": row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref")),
        "match_tier": row.get("match_tier"),
        "inventory_ref": row.get("inventory_ref"),
    }


def build_essential_insights(
    ticker: str,
    events: list[dict],
    raw_insights: list[dict],
    discussants: list[dict],
) -> dict:
    rows = events if events else raw_insights
    source_rows = [*events, *raw_insights]
    latest = compact_insight(latest_insight(rows))
    bull = compact_insight(best_insight(rows, lambda r: r.get("direction") == "bullish"))
    bear = compact_insight(
        best_insight(
            rows,
            lambda r: r.get("direction") == "bearish" or r.get("impact_axis") == "risk",
        )
    )
    owner = compact_insight(
        best_insight(rows, lambda r: r.get("source") in {"superinvestor_letter", "insider"})
    )
    if not owner and discussants:
        d0 = discussants[0]
        owner = {
            "id": f"letter:{ticker}:{d0.get('fund')}",
            "source": "superinvestor_letter",
            "source_label": "Letter",
            "source_name": d0.get("fund"),
            "event_type": "letter_position",
            "impact_axis": "ownership",
            "date": d0.get("letter_date"),
            "direction": {"add": "bullish", "trim": "bearish"}.get(d0.get("action"), "neutral"),
            "confidence": "med",
            "score": 0,
            "title": f"{d0.get('fund', 'Investor')} {d0.get('action', 'discussed')}",
            "summary": (d0.get("commentary") or "")[:320],
            "evidence_url": insight_evidence_url(d0.get("source_document") or d0.get("source_file")) or d0.get("evidence_url"),
            "evidence_label": d0.get("evidence_label") or best_document_label(d0.get("source_document") or d0.get("source_file")),
            "evidence_document_id": d0.get("evidence_document_id") or document_id_for_ref(d0.get("source_document") or d0.get("source_file")),
        }

    bullets: list[dict] = []
    seen: set[str] = set()
    for item in (latest, bear, bull, owner):
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        bullets.append(item)
        if len(bullets) >= 3:
            break

    source_mix = sorted({r.get("source") for r in source_rows if r.get("source")})
    freshness_days = None
    for r in rows:
        value = r.get("freshness_days")
        if isinstance(value, (int, float)) and (freshness_days is None or value < freshness_days):
            freshness_days = int(value)

    fresh = freshness_days is not None and freshness_days <= 30
    bear_specific = bool(
        bear
        and bear.get("source") not in {"macro", "theme"}
        and bear.get("impact_axis") in {"risk", "fundamentals", "ownership", "variant_view", None}
    )
    bull_specific = bool(
        bull
        and bull.get("source") not in {"macro", "theme"}
        and bull.get("impact_axis") in {"catalyst", "fundamentals", "ownership", "capital_allocation", "variant_view", None}
    )

    if not rows and not discussants:
        status = {"label": "No insight", "tone": "stale"}
    elif bear_specific and fresh:
        status = {"label": "Fresh risk", "tone": "risk"}
    elif bull_specific and fresh:
        status = {"label": "Fresh catalyst", "tone": "bullish"}
    elif owner:
        status = {"label": "Owner signal", "tone": "ownership"}
    elif freshness_days is not None and freshness_days > 120:
        status = {"label": "Stale", "tone": "stale"}
    else:
        status = {"label": "Covered", "tone": "neutral"}

    return {
        "status": status,
        "latest": latest,
        "bull": bull,
        "bear": bear,
        "owner": owner,
        "bullets": bullets,
        "source_mix": source_mix,
        "freshness_days": freshness_days,
        "event_count": len(events),
        "record_count": len(raw_insights),
        "needs_work": not source_rows or (freshness_days is not None and freshness_days > 90) or len(source_mix) < 2,
    }


def essential_needs_work_reasons(row: dict) -> list[str]:
    essential = row.get("essential_insights") or {}
    reasons: list[str] = []
    bullets = essential.get("bullets") or []
    if not bullets or any(not b.get("evidence_url") for b in bullets):
        reasons.append("missing evidence")
    freshness = essential.get("freshness_days")
    if isinstance(freshness, int) and freshness > 90:
        reasons.append("stale source")
    valuation_days = days_since_iso((row.get("classification") or {}).get("analysis_as_of"))
    if valuation_days is None or valuation_days > 90:
        reasons.append("stale valuation")
    outside_research_sources = {"third_party", "sumzero_research"}
    if not (outside_research_sources & set(essential.get("source_mix") or [])):
        reasons.append("no third-party check")
    return reasons[:4]


def build_active_lenses(lenses_doc: dict | None) -> tuple[list[dict], int]:
    if not lenses_doc:
        return [], 0
    personas = lenses_doc.get("lenses") or []
    active: list[dict] = []
    silent = 0
    for p in personas:
        rel = float(p.get("relevance") or 0)
        verdict = p.get("verdict") or "silent"
        if rel <= 0 or verdict == "silent":
            silent += 1
            continue
        label = (p.get("label") or p.get("persona") or "").split("/")[0].strip()
        active.append(
            {
                "persona": p.get("persona"),
                "label": label or p.get("persona"),
                "verdict": verdict,
                "return_pct": p.get("return_pct"),
                "relevance": rel,
                "horizon_yrs": p.get("horizon_yrs"),
                "key_metrics": p.get("key_metrics") or [],
                "falsifier": p.get("falsifier"),
            }
        )
    active.sort(key=lambda x: (-x["relevance"], -(x.get("return_pct") or -999)))
    return active[:3], silent


def build_decision_summary(
    classification: dict,
    lenses_doc: dict | None,
    human_review: dict | None,
    valuation: dict | None,
) -> dict | None:
    if not lenses_doc:
        return None
    blend = lenses_doc.get("valuation_blend") or {}
    consensus = lenses_doc.get("consensus") or {}
    lens_block = (valuation or {}).get("lens_consensus") or {}

    approved = (human_review or {}).get("approved_stance")
    if approved:
        stance = approved
        stance_source = "approved"
    elif consensus.get("stance"):
        stance = consensus["stance"]
        stance_source = "lens_consensus"
    else:
        stance = classification.get("stance", "watch")
        stance_source = "classification"

    dissents = consensus.get("dissents") or []
    top_dissent = None
    if dissents:
        d0 = dissents[0]
        top_dissent = {
            "persona": d0.get("persona"),
            "label": (d0.get("label") or d0.get("persona") or "").split("/")[0],
            "verdict": d0.get("verdict"),
        }

    house = classification.get("analysis_irr_pct")
    blend_pct = blend.get("blended_return_pct")
    divergence = bool(
        lens_block.get("lawrence_divergence")
        or consensus.get("lawrence_divergence")
    )
    if house is not None and blend_pct is not None and not divergence:
        divergence = abs(float(house) - float(blend_pct)) > 2.0

    lens_stance = consensus.get("stance")

    return {
        "stance": stance,
        "stance_source": stance_source,
        "lens_stance": lens_stance,
        "house_irr_pct": house,
        "lens_blend_pct": blend_pct,
        "lens_band_pct": blend.get("band_pct"),
        "agreement_pct": consensus.get("agreement_pct"),
        "top_dissent": top_dissent,
        "divergence": divergence,
        "as_of": lenses_doc.get("as_of") or classification.get("analysis_as_of"),
    }


def compact_research_memory(ticker: str, memory_doc: dict | None) -> dict | None:
    if not memory_doc:
        return None
    by_ticker = memory_doc.get("by_ticker") or {}
    mem = by_ticker.get(ticker.upper()) or by_ticker.get(ticker)
    if not mem:
        return None
    return {
        "claim_count": mem.get("claim_count", 0),
        "evidence_count": mem.get("evidence_count", 0),
        "source_count": mem.get("source_count", 0),
        "source_mix": mem.get("source_mix") or [],
        "confirming_count": mem.get("confirming_count", 0),
        "disconfirming_count": mem.get("disconfirming_count", 0),
        "mixed_count": mem.get("mixed_count", 0),
        "neutral_count": mem.get("neutral_count", 0),
        "top_claims": (mem.get("top_claims") or [])[:4],
        "inflection_claims": (mem.get("inflection_claims") or [])[:3],
        "risk_claims": (mem.get("risk_claims") or [])[:3],
        "ownership_claims": (mem.get("ownership_claims") or [])[:3],
        "biotech": mem.get("biotech") or {},
    }


def build_ticker_row(
    ticker: str,
    holdings: dict[str, dict],
    portfolio_class: dict[str, dict],
    insights_doc: dict | None = None,
    memory_doc: dict | None = None,
) -> dict:
    ticker_dir = ROOT / ticker
    meta = {**TICKER_META.get(ticker, {}), **holdings.get(ticker, {})}
    dl_script, dl_path = has_download_script(ticker_dir)
    classification = classification_for(ticker, ticker_dir, portfolio_class)
    pdf_count = count_pdfs(ticker_dir)
    deep_dive = latest_deep_dive(ticker_dir, classification)
    row = {
        "ticker": ticker,
        "company": meta.get("company", ticker),
        "market": meta.get("market", "—"),
        "exchange": meta.get("exchange", "—"),
        "folder": f"{ticker}/",
        "readme": (ticker_dir / "README.md").exists(),
        "download_script": dl_script,
        "download_script_path": dl_path,
        "pdf_count": pdf_count,
        "sec_filings": count_sec_filings(ticker_dir),
        "research_dir": (ticker_dir / "research").exists(),
        "index_file": has_index(ticker_dir),
        "last_download": last_download(ticker_dir),
        "last_research": last_research(ticker_dir),
        "classification": classification,
        "thesis_status": classification["archetype"],
        "one_line_thesis": display_one_line_thesis(ticker_dir, deep_dive),
        "links": _research_links(ticker, ticker_dir),
        "deep_dive": deep_dive,
        "human_review": valuation_human_review(ticker_dir),
        "total_return_panel": valuation_total_return_panel(ticker, ticker_dir),
        "recent_files": recent_files(ticker_dir),
        "developments": recent_developments(ticker_dir, ticker),
        "onboard": reconcile_onboard_status(ticker_dir, pdf_count),
        "transcripts": transcript_summary(ticker, ticker_dir),
    }
    row["completeness"] = completeness_score(row)
    lenses = load_lenses(ticker_dir)
    val = load_valuation(ticker_dir)
    if lenses:
        row["lenses"] = {
            "as_of": lenses.get("as_of"),
            "valuation_blend": lenses.get("valuation_blend"),
            "consensus": lenses.get("consensus"),
            "personas": lenses.get("lenses"),
        }
        active, silent_count = build_active_lenses(lenses)
        row["active_lenses"] = active
        row["silent_lens_count"] = silent_count
        row["decision_summary"] = build_decision_summary(
            classification, lenses, row.get("human_review"), val
        )
    full_insights = enrich_ticker_insights(load_insights_for_ticker(ticker, insights_doc), limit=200)
    display_insights = full_insights[:12]
    if not any(r.get("source") == "sumzero_research" for r in display_insights):
        sumzero_row = next((r for r in full_insights if r.get("source") == "sumzero_research"), None)
        if sumzero_row:
            display_insights = [*display_insights[:11], sumzero_row]
    row["insights"] = display_insights
    row["insight_events"] = load_events_for_ticker(ticker, insights_doc)
    row["letter_discussants"] = load_letter_discussants(ticker, insights_doc)
    row["essential_insights"] = build_essential_insights(
        ticker,
        row["insight_events"],
        full_insights,
        row["letter_discussants"],
    )
    reasons = essential_needs_work_reasons(row)
    row["essential_insights"]["needs_work_reasons"] = reasons
    row["essential_insights"]["needs_work"] = bool(reasons)
    row["research_memory"] = compact_research_memory(ticker, memory_doc)
    return row


def build() -> dict:
    reg = load_registry()
    holdings = parse_holdings()
    portfolio_class = load_classification()
    tickers = list_tickers()
    insights_doc = _load_json(DATA_DIR / "insights.json")
    memory_doc = _load_json(RESEARCH_MEMORY_PATH)
    rows = [build_ticker_row(t, holdings, portfolio_class, insights_doc, memory_doc) for t in tickers]
    watchlist = build_watchlist_rows(reg.get("watchlist") or {})

    total_pdfs = sum(r["pdf_count"] for r in rows)
    with_research = sum(1 for r in rows if r["research_dir"])
    with_readme = sum(1 for r in rows if r["readme"])
    avg_complete = round(sum(r["completeness"] for r in rows) / len(rows)) if rows else 0

    sleeve_filters = [{"id": "ALL", "label": "All sleeves"}]
    real_assets_union: set[str] = set()
    for sleeve_id in _INVESTMENT_SLEEVE_LABELS:
        if sleeve_id.startswith("real_assets"):
            real_assets_union.update(
                t
                for t, sid in _INVESTMENT_SLEEVE_INDEX.items()
                if sid == sleeve_id
            )
    if real_assets_union:
        sleeve_filters.append(
            {
                "id": "real_assets_all",
                "label": "All hard assets",
                "count": sum(
                    1
                    for r in rows
                    if r["ticker"] in real_assets_union
                ),
            }
        )
    for sleeve_id, label in sorted(_INVESTMENT_SLEEVE_LABELS.items(), key=lambda x: x[1]):
        count = sum(
            1
            for r in rows
            if (r.get("classification") or {}).get("investment_sleeve") == sleeve_id
        )
        sleeve_filters.append({"id": sleeve_id, "label": label, "count": count})

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(ROOT),
        "summary": {
            "ticker_count": len(rows),
            "watchlist_count": len(watchlist),
            "total_pdfs": total_pdfs,
            "with_readme": with_readme,
            "with_research": with_research,
            "avg_completeness": avg_complete,
            "markets": sort_markets({r["market"] for r in rows}),
            "market_filters": sort_market_filters({r["market"] for r in rows}),
            "sleeve_filters": sleeve_filters,
            "github_repo": GITHUB_REPO,
            "onboard_workflow": ONBOARD_WORKFLOW,
            "onboard_dispatch_event": "onboard-ticker",
        },
        "watchlist": watchlist,
        "tickers": rows,
        "research_memory": memory_doc,
    }


OAUTH_CONFIG = DATA_DIR / "oauth_config.json"


def write_oauth_config() -> None:
    """Merge OAuth client_id from env (CI) with committed config."""
    existing: dict = {}
    if OAUTH_CONFIG.exists():
        try:
            existing = json.loads(OAUTH_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    client_id = os.environ.get("OAUTH_CLIENT_ID", "").strip() or existing.get("client_id", "")
    exchange_url = os.environ.get("OAUTH_PROXY_URL", "").strip() or existing.get("exchange_url", "")
    payload = {
        "client_id": client_id,
        "exchange_url": exchange_url,
        "scopes": existing.get("scopes", "repo"),
        "setup": existing.get(
            "setup",
            "Create a GitHub OAuth App; callback URL must match .../oauth/callback.html on Pages.",
        ),
    }
    OAUTH_CONFIG.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_darwin_portfolio() -> dict | None:
    return _load_json(DATA_DIR / "darwin_portfolio.json") or _load_json(
        DATA_DIR / "darwin_portfolio_roth.json"
    )


def load_darwin_serving() -> dict | None:
    return _load_json(DATA_DIR / "darwin_serving.json")


def load_darwin_bundle() -> dict:
    """Prefer L4 serving; fallback to per-account portfolio files."""
    serving = load_darwin_serving()
    if serving and serving.get("accounts"):
        bundle = {
            "serving": serving,
            "default_account": serving.get("default_account", "roth"),
        }
        for aid, row in serving["accounts"].items():
            if row.get("portfolio"):
                bundle[aid] = row["portfolio"]
            if row.get("paper"):
                bundle[f"paper_{aid}"] = {
                    "last_mark": row["paper"],
                    "inception_date": row.get("paper_inception"),
                }
        return bundle
    bundle: dict = {"default_account": "roth"}
    for aid in ("roth", "taxable"):
        p = _load_json(DATA_DIR / f"darwin_portfolio_{aid}.json")
        if p:
            bundle[aid] = p
    roth = bundle.get("roth") or load_darwin_portfolio()
    if roth:
        bundle["roth"] = roth
    return bundle


def build_darwin_if_missing() -> dict | None:
    """Run Darwin pipeline when portfolio JSON absent (e.g. fresh clone)."""
    if (DATA_DIR / "darwin_serving.json").exists() or (DATA_DIR / "darwin_portfolio_roth.json").exists():
        return load_darwin_bundle()
    script = ROOT / "_system" / "scripts" / "build_darwin_portfolio.py"
    if not script.exists():
        return None
    import subprocess

    subprocess.run(
        [sys.executable, str(script), "--fast"],
        cwd=str(ROOT),
        check=False,
        timeout=600,
    )
    return load_darwin_bundle()


def build_nol_screener_if_missing() -> dict | None:
    path = DATA_DIR / "nol_screener.json"
    if path.exists():
        return _load_json(path)
    script = ROOT / "_system" / "scripts" / "build_nol_screener.py"
    if not script.exists():
        return None
    import subprocess

    subprocess.run(
        [sys.executable, str(script), "--write"],
        cwd=str(ROOT),
        check=False,
        timeout=300,
    )
    return _load_json(path)


def build_equity_models() -> dict:
    """Run equity model ingest and return payload for dashboard merge."""
    script = ROOT / "_system" / "scripts" / "build_equity_model_dashboard.py"
    if script.exists():
        import subprocess

        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=False)
    path = DATA_DIR / "equity_models.json"
    if not path.exists():
        return {"built_at": None, "ticker_count": 0, "tickers": {}, "summaries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"built_at": None, "ticker_count": 0, "tickers": {}, "summaries": {}}


def merge_equity_model_rows(rows: list[dict], equity_payload: dict) -> None:
    summaries = equity_payload.get("summaries") or {}
    tickers = equity_payload.get("tickers") or {}
    for row in rows:
        ticker = row["ticker"]
        if ticker in summaries:
            row["equity_model"] = summaries[ticker]
        elif ticker in tickers:
            row["equity_model"] = {"ready": True, "as_of": tickers[ticker].get("as_of")}
        else:
            row["equity_model"] = {"ready": False}


def build_document_registry() -> dict | None:
    import subprocess

    script = ROOT / "_system" / "scripts" / "build_document_registry.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=False)
    return _load_json(DOCUMENT_REGISTRY_PATH)


def build_research_memory() -> dict | None:
    return _load_json(RESEARCH_MEMORY_PATH)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    equity_payload = build_equity_models()
    document_registry = build_document_registry()
    document_catalog = build_document_catalog(document_registry)
    insights_doc = _load_json(DATA_DIR / "insights.json")
    memory_doc = build_research_memory()
    payload = build()
    attach_pdf_store_rows(payload["tickers"], document_catalog)
    merge_equity_model_rows(payload["tickers"], equity_payload)
    model_ready = sum(1 for r in payload["tickers"] if (r.get("equity_model") or {}).get("ready"))
    payload["summary"]["equity_models_ready"] = model_ready
    payload["equity_models"] = equity_payload
    if insights_doc:
        payload["insights"] = insights_doc
    if memory_doc:
        payload["research_memory"] = memory_doc
    if document_catalog:
        payload["document_catalog"] = {
            "generated_at": document_catalog.get("generated_at"),
            "registry_generated_at": document_catalog.get("registry_generated_at"),
            "folder_index_generated_at": document_catalog.get("folder_index_generated_at"),
            "time_periods": document_catalog.get("time_periods"),
            "summary": document_catalog.get("summary"),
            "documents": document_catalog.get("documents"),
        }
    persona_cal = _load_json(DATA_DIR / "persona_calibration.json")
    if persona_cal:
        payload["persona_calibration"] = persona_cal
    bundle = load_darwin_bundle() or build_darwin_if_missing() or {}
    serving = bundle.get("serving") or load_darwin_serving()
    if serving:
        payload["darwin_serving"] = serving
    if bundle.get("roth"):
        payload["darwin"] = bundle["roth"]
    if bundle:
        payload["darwin_accounts"] = bundle
    nol = build_nol_screener_if_missing()
    if nol:
        payload["nol_screener"] = nol
        payload["summary"]["nol_screener_count"] = nol.get("row_count") or len(
            nol.get("rows") or []
        )
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_oauth_config()
    print(f"Wrote {OUTPUT} ({payload['summary']['ticker_count']} tickers)")


if __name__ == "__main__":
    main()
