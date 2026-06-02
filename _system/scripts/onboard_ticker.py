#!/usr/bin/env python3
"""Onboard a new ticker: scaffold, register, download, dashboard refresh, optional deep dive."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import (
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    ROOT,
    build_download_block,
    infer_download_type,
    load_registry,
    save_registry,
)

PY = sys.executable
SCRIPTS = ROOT / "_system" / "scripts"
SEC_UA = "Marvin Research single-stock-investments (contact: portfolio@local)"
REVIEWS = ROOT / "_system" / "reviews" / "pending"


def log(msg: str) -> None:
    print(msg, flush=True)


def write_status(ticker_dir: Path, phase: str, error: str | None = None, extra: dict | None = None) -> None:
    payload = {
        "phase": phase,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error,
        **(extra or {}),
    }
    (ticker_dir / ".onboard_status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def lookup_cik(ticker: str) -> str | None:
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": SEC_UA},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        upper = ticker.upper()
        for row in data.values():
            if str(row.get("ticker", "")).upper() == upper:
                return str(row["cik_str"]).zfill(10)
    except Exception as exc:
        log(f"CIK lookup failed: {exc}")
    return None


def parse_ir_urls(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [u.strip() for u in re.split(r"[\s,;]+", raw) if u.strip()]


def scaffold_us(ticker: str, company: str) -> Path:
    td = ROOT / ticker
    inv = td / "investor-documents"
    for sub in ("sec-edgar", f"ir-{ticker.lower()}", "research-notes"):
        (inv / sub).mkdir(parents=True, exist_ok=True)
    (td / "research" / "reports").mkdir(parents=True, exist_ok=True)
    script = inv / f"download_{ticker.lower()}_investor_docs.py"
    if not script.exists():
        script.write_text(
            f'''#!/usr/bin/env python3
"""Download {ticker} investor documents via shared Marvin script."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_us_investor_docs.py"),
    "--ticker",
    "{ticker}",
])
''',
            encoding="utf-8",
        )
    readme = td / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {company} ({ticker})\n\n"
            f"**Ticker:** {ticker} | **Market:** US\n"
            f"**Last updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
            f"## Download\n\n"
            f"```powershell\npython {ticker}/investor-documents/download_{ticker.lower()}_investor_docs.py\n```\n",
            encoding="utf-8",
        )
    return td


def scaffold_jp(ticker: str, company: str) -> Path:
    td = ROOT / ticker
    for sub in ("01_Official", "02_Quarterly", "03_Events", "04_Strategy", "06_References", "_scripts", "research"):
        (td / sub).mkdir(parents=True, exist_ok=True)
    ps1 = td / "_scripts" / "download_and_organize.ps1"
    if not ps1.exists():
        ps1.write_text(
            f"# {ticker} — JP IR download script (adapt from 8697.T/_scripts/download_and_organize.ps1)\n",
            encoding="utf-8",
        )
    urls = td / "_pdf_urls.txt"
    if not urls.exists():
        urls.write_text(f"# IR PDF URLs for {ticker}\n", encoding="utf-8")
    readme = td / "README.md"
    if not readme.exists():
        readme.write_text(f"# {company} ({ticker})\n\n**Market:** JP\n", encoding="utf-8")
    return td


def scaffold_eu(ticker: str, company: str) -> Path:
    td = ROOT / ticker
    for sub in (
        "official-reports",
        "corporate-documents",
        "presentations-and-media",
        "third-party-analyses",
        "research",
    ):
        (td / sub).mkdir(parents=True, exist_ok=True)
    idx = td / "document-index.csv"
    if not idx.exists():
        idx.write_text("path,title,date,type\n", encoding="utf-8")
    readme = td / "README.md"
    if not readme.exists():
        readme.write_text(f"# {company} ({ticker})\n\n**Market:** EU/SE\n", encoding="utf-8")
    return td


def scaffold_folder(ticker: str, company: str, market: str) -> Path:
    if market == "JP":
        return scaffold_jp(ticker, company)
    if market in {"SE", "EU"}:
        return scaffold_eu(ticker, company)
    return scaffold_us(ticker, company)


def write_thesis(ticker: str, company: str, classification: dict) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = ROOT / ticker / "research" / "thesis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    pred = classification.get("predictive_attribute")
    pred_row = f"| **Predictive attribute** | {pred} |\n" if pred else ""
    path.write_text(
        f"# {ticker} — Investment Thesis\n\n"
        f"**Last updated:** {today}\n\n"
        f"## Classification\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| **Archetype** (Stahl) | {classification.get('archetype', 'unknown')} |\n"
        f"| **Moat** (Munger) | {classification.get('moat', 'unproven')} |\n"
        f"| **Dhando** (Pabrai) | {classification.get('dhando', 'pending')} |\n"
        f"| **Stance** | {classification.get('stance', 'watch')} |\n"
        f"| **Cycle** | {classification.get('cycle', '-')} |\n"
        f"| **MOI bucket** (legacy) | {classification.get('moi_bucket', 'pending')} |\n"
        f"| **Payoff lens** | {classification.get('payoff_lens', 'pending')} |\n"
        f"{pred_row}\n"
        f"## One-line thesis\n\n"
        f"{company} — thesis pending Marvin deep dive.\n\n"
        f"## Key questions\n\n"
        f"- [ ] Read latest annual report\n"
        f"- [ ] Read latest quarterly report\n"
        f"- [ ] Apply `_system/frameworks/mental_models.md` Tier 1 lenses\n\n"
        f"## [HUMAN REVIEW]\n\n"
        f"- Onboarded {today}; awaiting deep dive.\n",
        encoding="utf-8",
    )


def run_cmd(cmd: list[str], label: str, check: bool = False) -> int:
    log(f"\n=== {label} ===")
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"{label} failed with code {result.returncode}")
    return result.returncode


def run_download(ticker: str, download: dict) -> tuple[bool, str]:
    dtype = download.get("type", "us_shared")
    if dtype == "us_shared":
        code = run_cmd([PY, str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker], ticker)
        return code == 0, f"us_shared exit {code}"
    if dtype == "us_dedicated":
        script = ROOT / ticker / "investor-documents" / f"download_{ticker.lower()}_investor_docs.py"
        if not script.exists():
            script = ROOT / "QDEL/investor-documents/download_qdel_investor_docs.py"
        code = run_cmd([PY, str(script)], f"{ticker} dedicated")
        return code == 0, f"us_dedicated exit {code}"
    if dtype == "ca_csu":
        code = run_cmd([PY, str(SCRIPTS / "download_csu.py")], "CSU")
        return code == 0, f"ca_csu exit {code}"
    if dtype == "eu_teq":
        code = run_cmd([PY, str(SCRIPTS / "download_teq_st.py")], "TEQ.ST")
        return code == 0, f"eu_teq exit {code}"
    if dtype == "jp_ps1":
        import shutil

        for exe in ("pwsh", "powershell"):
            if shutil.which(exe):
                script = ROOT / ticker / "_scripts" / "download_and_organize.ps1"
                if script.exists() and script.stat().st_size > 80:
                    code = run_cmd([exe, "-ExecutionPolicy", "Bypass", "-File", str(script)], ticker)
                    return code == 0, f"jp_ps1 exit {code}"
        log("JP script placeholder only — skip download until IR URLs configured")
        return True, "jp_ps1 skipped (placeholder)"
    if dtype == "jp_archive":
        dl_log = ROOT / ticker / "_download_log.txt"
        dl_log.write_text(
            f"{datetime.now(timezone.utc).isoformat()} Archive/onboard placeholder; configure _pdf_urls.txt\n",
            encoding="utf-8",
        )
        return True, "jp_archive placeholder"
    return False, f"unknown download type {dtype}"


def write_pending_review(ticker: str, company: str, market: str, download_ok: bool, detail: str) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = REVIEWS / f"{ticker}_onboard_{today}.md"
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {ticker} — Onboard Summary\n\n"
        f"**Date:** {today}\n**Company:** {company}\n**Market:** {market}\n\n"
        f"## Download\n\n"
        f"{'Success' if download_ok else 'Partial/failed'}: {detail}\n\n"
        f"## [HUMAN REVIEW]\n\n"
        f"- Verify CIK and IR URLs in registry\n"
        f"- Review deep dive PR when Cloud Agent completes\n"
        f"- Confirm classification defaults\n\n"
        f"## [PROPOSED MEMORY]\n\n"
        f"- [PROPOSED COMPANY] {ticker} onboarded {today}.\n",
        encoding="utf-8",
    )
    return path


def remove_from_watchlist(reg: dict, ticker: str) -> None:
    wl = reg.get("watchlist") or {}
    if ticker in wl:
        del wl[ticker]
        reg["watchlist"] = wl


def add_watchlist_entry(reg: dict, ticker: str, company: str, market: str, notes: str = "") -> None:
    reg.setdefault("watchlist", {})
    reg["watchlist"][ticker] = {
        "company": company,
        "market": market,
        "notes": notes,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def onboard(args: argparse.Namespace) -> int:
    ticker = args.ticker.strip().upper() if args.market != "JP" else args.ticker.strip()
    company = args.company.strip()
    market = args.market.strip().upper()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    reg = load_registry()
    holdings = reg.setdefault("holdings", {})

    if args.watchlist_only:
        add_watchlist_entry(reg, ticker, company, market, args.notes or "")
        save_registry(reg)
        run_cmd([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], "sync portfolio")
        run_cmd([PY, str(SCRIPTS / "build_dashboard_data.py")], "dashboard")
        log(f"Added {ticker} to watchlist")
        return 0

    ticker_dir = ROOT / ticker
    if ticker_dir.exists() and not args.force:
        log(f"Folder {ticker}/ already exists. Use --force to continue.")
        return 1
    if ticker in holdings and not args.force:
        log(f"{ticker} already in registry holdings.")
        return 1

    cik = args.cik
    if market == "US" and not cik:
        cik = lookup_cik(ticker)
        if cik:
            log(f"CIK lookup: {cik}")

    ir_roots = parse_ir_urls(args.ir_url)
    download = {
        "type": infer_download_type(ticker, market, json.loads((SCRIPTS / "us_ticker_config.json").read_text())),
        "ir_roots": ir_roots,
    }
    if cik:
        download["cik"] = cik
    if args.download_8k_exhibits:
        download.setdefault("options", {})["download_8k_exhibits"] = True

    classification = {**DEFAULT_CLASSIFICATION}
    if args.from_watchlist and ticker in (reg.get("watchlist") or {}):
        remove_from_watchlist(reg, ticker)

    entry = {
        "company": company,
        "market": market,
        "exchange": EXCHANGE_META.get(ticker, "—"),
        "onboarded": today,
        "download": download,
        "classification": classification,
    }

    if args.dry_run:
        log(json.dumps(entry, indent=2))
        return 0

    holdings[ticker] = entry
    save_registry(reg)

    run_cmd([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], "sync portfolio")

    ticker_dir = scaffold_folder(ticker, company, market)
    write_status(ticker_dir, "scaffold")
    write_thesis(ticker, company, classification)

    run_cmd(
        [PY, str(SCRIPTS / "scan_third_party_sources.py"), ticker, "--with-hk", "--date", today],
        "third-party scan",
    )
    run_cmd(
        [PY, str(SCRIPTS / "scaffold_cross_check.py"), ticker, "--date", today],
        "cross-check scaffold",
    )

    if not args.skip_download:
        write_status(ticker_dir, "downloading")
        ok, detail = run_download(ticker, download)
        if not ok:
            write_status(ticker_dir, "failed", error=detail)
            write_pending_review(ticker, company, market, False, detail)
            run_cmd([PY, str(SCRIPTS / "build_folder_indexes.py")], "indexes")
            run_cmd([PY, str(SCRIPTS / "build_dashboard_data.py")], "dashboard")
            return 2
    else:
        ok, detail = True, "skipped"

    run_cmd([PY, str(SCRIPTS / "build_folder_indexes.py")], "indexes")
    write_status(
        ticker_dir,
        "complete",
        extra={"download_detail": detail, "deep_dive_pending": True},
    )
    review_path = write_pending_review(ticker, company, market, ok, detail)
    run_cmd([PY, str(SCRIPTS / "build_dashboard_data.py")], "dashboard")
    log(f"Onboard complete: {ticker}")
    log(f"Review: {review_path.relative_to(ROOT)}")

    if args.deep_dive and not args.dry_run:
        log("\n=== Marvin deep dive (Cloud Agent) ===")
        code = run_cmd([PY, str(SCRIPTS / "run_deep_dive.py"), "--ticker", ticker], "deep dive")
        if code != 0:
            log("Deep dive dispatch failed — run marvin-deep-dive workflow manually")
            return 3

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboard a new portfolio ticker")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--market", default="US", choices=["US", "JP", "CA", "SE", "EU", "OTC"])
    parser.add_argument("--cik", default=None)
    parser.add_argument("--ir-url", default=None, help="One or more IR root URLs")
    parser.add_argument("--notes", default="", help="Watchlist notes")
    parser.add_argument("--from-watchlist", action="store_true")
    parser.add_argument("--watchlist-only", action="store_true", help="Add to watchlist without onboarding")
    parser.add_argument("--download-8k-exhibits", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--deep-dive", action="store_true", default=True)
    parser.add_argument("--no-deep-dive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.no_deep_dive:
        args.deep_dive = False
    sys.exit(onboard(args))


if __name__ == "__main__":
    main()
