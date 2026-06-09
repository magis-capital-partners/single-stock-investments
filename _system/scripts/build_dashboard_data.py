#!/usr/bin/env python3
"""Build portfolio dashboard JSON from ticker folders and _system/portfolio/holdings.md."""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from dated_md import dated_md_label, dated_md_sort_key, latest_dated_md  # noqa: E402
from market_order import sort_market_filters, sort_markets  # noqa: E402
from valuation_synthesis import website_implied_irr  # noqa: E402

DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "dashboard_data.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"
ONBOARD_WORKFLOW = "marvin-onboard.yml"


def github_blob_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/blob/main/{rel_path.replace(chr(92), '/')}"


def github_tree_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/tree/main/{rel_path.replace(chr(92), '/').rstrip('/')}"


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
    }
    out = {k: merged.get(k, defaults[k]) for k in defaults}
    val = load_valuation(ticker_dir)
    if val:
        if not val.get("ticker"):
            val["ticker"] = ticker_dir.name
        irr_web = website_implied_irr(val)
        inputs = val.get("classification_inputs") or {}
        for key in ("archetype", "moat", "dhando", "cycle"):
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
            manifest_rows = json.loads(manifest.read_text(encoding="utf-8"))
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
    "superinvestor_letter": 0,
    "insider": 1,
    "third_party": 2,
    "macro": 3,
    "theme": 4,
    "news": 5,
}


def insight_evidence_url(evidence_ref: str | None) -> str | None:
    if not evidence_ref:
        return None
    ref = evidence_ref.strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    base = ref.split("#", 1)[0]
    return github_blob_url(base)


def enrich_ticker_insights(raw: list[dict], limit: int = 10) -> list[dict]:
    out: list[dict] = []
    for r in raw:
        row = dict(r)
        row["evidence_url"] = insight_evidence_url(row.get("evidence_ref"))
        out.append(row)
    out.sort(
        key=lambda x: (
            SOURCE_PRIORITY.get(x.get("source", ""), 9),
            x.get("as_of") or "",
        )
    )
    return out[:limit]


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


def build_ticker_row(ticker: str, holdings: dict[str, dict], portfolio_class: dict[str, dict], insights_doc: dict | None = None) -> dict:
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
    row["insights"] = enrich_ticker_insights(load_insights_for_ticker(ticker, insights_doc))
    return row


def build() -> dict:
    reg = load_registry()
    holdings = parse_holdings()
    portfolio_class = load_classification()
    tickers = list_tickers()
    insights_doc = _load_json(DATA_DIR / "insights.json")
    rows = [build_ticker_row(t, holdings, portfolio_class, insights_doc) for t in tickers]
    watchlist = build_watchlist_rows(reg.get("watchlist") or {})

    total_pdfs = sum(r["pdf_count"] for r in rows)
    with_research = sum(1 for r in rows if r["research_dir"])
    with_readme = sum(1 for r in rows if r["readme"])
    avg_complete = round(sum(r["completeness"] for r in rows) / len(rows)) if rows else 0

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
            "github_repo": GITHUB_REPO,
            "onboard_workflow": ONBOARD_WORKFLOW,
            "onboard_dispatch_event": "onboard-ticker",
        },
        "watchlist": watchlist,
        "tickers": rows,
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


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    equity_payload = build_equity_models()
    payload = build()
    merge_equity_model_rows(payload["tickers"], equity_payload)
    model_ready = sum(1 for r in payload["tickers"] if (r.get("equity_model") or {}).get("ready"))
    payload["summary"]["equity_models_ready"] = model_ready
    payload["equity_models"] = equity_payload
    insights_doc = _load_json(DATA_DIR / "insights.json")
    if not insights_doc:
        import subprocess

        ins_script = ROOT / "_system" / "scripts" / "build_insights.py"
        if ins_script.exists():
            subprocess.run([sys.executable, str(ins_script)], cwd=str(ROOT), check=False)
            insights_doc = _load_json(DATA_DIR / "insights.json")
    if insights_doc:
        payload["insights"] = insights_doc
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
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_oauth_config()
    print(f"Wrote {OUTPUT} ({payload['summary']['ticker_count']} tickers)")


if __name__ == "__main__":
    main()
