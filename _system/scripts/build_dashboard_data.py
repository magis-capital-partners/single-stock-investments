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


def list_tickers() -> list[str]:
    skip = {"_system", "dashboard", ".git", ".github", ".cursor"}
    tickers = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in skip and not p.name.startswith("."):
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
        meta[ticker] = {"company": h.get("company", ticker), "market": h.get("market", "—")}
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
        ("implied_irr", r"Implied 10yr IRR"),
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
        if irr_web.get("falsifier_adjusted_pct") is not None:
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
    sm = re.search(r"## Executive summary\s*\n\s*\n(.+?)(?:\n\n---|\n\n## )", text, re.DOTALL)
    if sm:
        summary = sm.group(1).strip()
        summary = re.sub(r"\*\*", "", summary)
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


def build_ticker_row(ticker: str, holdings: dict[str, dict], portfolio_class: dict[str, dict]) -> dict:
    ticker_dir = ROOT / ticker
    meta = {**TICKER_META.get(ticker, {}), **holdings.get(ticker, {})}
    dl_script, dl_path = has_download_script(ticker_dir)
    classification = classification_for(ticker, ticker_dir, portfolio_class)
    row = {
        "ticker": ticker,
        "company": meta.get("company", ticker),
        "market": meta.get("market", "—"),
        "exchange": meta.get("exchange", "—"),
        "folder": f"{ticker}/",
        "readme": (ticker_dir / "README.md").exists(),
        "download_script": dl_script,
        "download_script_path": dl_path,
        "pdf_count": count_pdfs(ticker_dir),
        "sec_filings": count_sec_filings(ticker_dir),
        "research_dir": (ticker_dir / "research").exists(),
        "index_file": has_index(ticker_dir),
        "last_download": last_download(ticker_dir),
        "last_research": last_research(ticker_dir),
        "classification": classification,
        "thesis_status": classification["archetype"],
        "one_line_thesis": one_line_thesis(ticker_dir),
        "links": _research_links(ticker, ticker_dir),
        "deep_dive": latest_deep_dive(ticker_dir, classification),
        "human_review": valuation_human_review(ticker_dir),
        "recent_files": recent_files(ticker_dir),
        "developments": recent_developments(ticker_dir, ticker),
        "onboard": onboard_status(ticker_dir),
        "transcripts": transcript_summary(ticker, ticker_dir),
    }
    row["completeness"] = completeness_score(row)
    return row


def build() -> dict:
    reg = load_registry()
    holdings = parse_holdings()
    portfolio_class = load_classification()
    tickers = list_tickers()
    rows = [build_ticker_row(t, holdings, portfolio_class) for t in tickers]
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
            "markets": sorted({r["market"] for r in rows}),
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


def load_darwin_portfolio() -> dict | None:
    path = DATA_DIR / "darwin_portfolio.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_darwin_if_missing() -> dict | None:
    """Run Darwin pipeline when portfolio JSON absent (e.g. fresh clone)."""
    if (DATA_DIR / "darwin_portfolio.json").exists():
        return load_darwin_portfolio()
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
    return load_darwin_portfolio()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    darwin = load_darwin_portfolio() or build_darwin_if_missing()
    if darwin:
        payload["darwin"] = darwin
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_oauth_config()
    print(f"Wrote {OUTPUT} ({payload['summary']['ticker_count']} tickers)")


if __name__ == "__main__":
    main()
