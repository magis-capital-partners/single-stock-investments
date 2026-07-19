#!/usr/bin/env python3
"""Mass-onboard remaining S&P 500 names efficiently.

Phases per batch:
  1. Registry + folder scaffold + thesis stub (no per-ticker dashboard)
  2. Monthly returns CSV (Yahoo)
  3. SEC/IR download (us_shared)
  4. Once per batch: sync portfolio, folder indexes, dashboard
  5. Print comma-separated tickers for deep-dive CI dispatch

Does NOT run Marvin deep dives locally (use GH Actions batch after push).

Usage:
  python _system/scripts/darwin/bulk_sp500_onboard.py --batch-size 10 --offset 0
  python _system/scripts/darwin/bulk_sp500_onboard.py --batch-size 10 --offset 10 --skip-download
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from darwin.prices import fetch_yahoo_monthly  # noqa: E402
from darwin.symbols import yahoo_for_ticker  # noqa: E402
from portfolio_registry import (  # noqa: E402
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    build_download_block,
    infer_download_type,
    load_registry,
    save_registry,
)

PY = sys.executable
SP500_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents.json"
SP500_ENRICHED = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents_enriched.json"
RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"
STATUS_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_onboard_status.jsonl"
SEC_UA = "Marvin Research single-stock-investments (contact: portfolio@local)"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def load_sp500_meta() -> dict[str, tuple[str, str | None]]:
    """Prefer Wikipedia-enriched map; fallback to SEC company_tickers; else empty."""
    out: dict[str, tuple[str, str | None]] = {}
    if SP500_ENRICHED.exists():
        data = json.loads(SP500_ENRICHED.read_text(encoding="utf-8"))
        for row in data.get("constituents") or []:
            t = str(row.get("ticker") or "").upper()
            if not t:
                continue
            company = str(row.get("company") or t)
            cik = row.get("cik")
            out[t] = (company, cik)
            out[t.replace(".", "-")] = (company, cik)
            out[t.replace("-", ".")] = (company, cik)
        if out:
            return out
    return {k: (v[0], v[1]) for k, v in load_sec_title_map().items()}


def load_sec_title_map() -> dict[str, tuple[str, str]]:
    """ticker -> (company title, cik10). Falls back to empty on SEC block."""
    cache = ROOT / "_system" / "reference" / "market-data" / "index" / "sec_company_tickers.json"
    data = None
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
    if data is None:
        for ua in (
            SEC_UA,
            "Mozilla/5.0 (compatible; MarvinResearch/1.0; +https://github.com/magis-capital-partners/single-stock-investments)",
            "Sample Company Name AdminContact@example.com",
        ):
            try:
                req = urllib.request.Request(SEC_TICKERS_URL, headers={"User-Agent": ua})
                data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data), encoding="utf-8")
                break
            except Exception as exc:
                log(f"SEC tickers fetch failed ({ua[:40]}…): {exc}")
                data = None
    if not data:
        log("WARN: no SEC title map — company names will be ticker symbols; CIK via per-ticker lookup")
        return {}
    out: dict[str, tuple[str, str]] = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper().replace("-", ".")
        title = str(row.get("title", "")).strip() or t
        cik = str(row.get("cik_str", "")).zfill(10)
        if t:
            out[t] = (title, cik)
            out[t.replace(".", "-")] = (title, cik)
    return out


def lookup_cik_one(ticker: str) -> str | None:
    from onboard_ticker import lookup_cik

    return lookup_cik(ticker)


def missing_sp500(reg: dict) -> list[str]:
    sp = json.loads(SP500_PATH.read_text(encoding="utf-8"))
    holdings = set((reg.get("holdings") or {}).keys())
    missing: list[str] = []
    for t in sp.get("tickers") or []:
        if t in holdings:
            continue
        if t.replace(".", "-") in holdings:
            continue
        if t.replace("-", ".") in holdings:
            continue
        # Skip dual-class alias if sibling already held/pending — keep GOOG if GOOGL held? Still onboard both if distinct.
        missing.append(t)
    return missing


def write_returns(ticker: str) -> tuple[bool, str]:
    path = RETURNS_DIR / f"{ticker.replace('.', '_')}.csv"
    if path.exists() and path.stat().st_size > 100:
        return True, "exists"
    ysym = yahoo_for_ticker(ticker, "US")
    if "." in ysym and not ysym.endswith(".T"):
        # Yahoo often wants BRK-B
        ysym = ysym.replace(".", "-")
    dates, rets, src = fetch_yahoo_monthly(ysym, months=120)
    if len(rets) < 6 and ysym != ticker:
        dates, rets, src = fetch_yahoo_monthly(ticker.replace(".", "-"), months=120)
    if len(rets) < 6:
        return False, f"insufficient:{src}"
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "monthly_return", "source"])
        for d, r in zip(dates, rets):
            w.writerow([d, round(r, 6), src])
    return True, str(path.relative_to(ROOT))


def append_status(row: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def onboard_one(
    ticker: str,
    company: str,
    cik: str | None,
    *,
    skip_download: bool,
    sleep_s: float,
) -> dict:
    from onboard_ticker import (  # local import after path setup
        initialize_proof_first_valuation,
        scaffold_folder,
        write_status,
        write_thesis,
        run_download,
        write_pending_review,
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reg = load_registry()
    holdings = reg.setdefault("holdings", {})

    already = ticker in holdings and (ROOT / ticker).is_dir()
    phase = ""
    if already:
        st_path = ROOT / ticker / ".onboard_status.json"
        if st_path.exists():
            try:
                phase = json.loads(st_path.read_text(encoding="utf-8")).get("phase") or ""
            except json.JSONDecodeError:
                phase = ""
        if phase == "complete":
            return {"ticker": ticker, "status": "skipped", "detail": "already_onboarded"}

    if already:
        entry = holdings[ticker]
        company = entry.get("company") or company
        download = entry.get("download") or {"type": "us_shared", "ir_roots": []}
        if cik and not (download.get("cik")):
            download["cik"] = cik
            entry["download"] = download
            holdings[ticker] = entry
            save_registry(reg)
    else:
        us_cfg = json.loads((SCRIPTS / "us_ticker_config.json").read_text(encoding="utf-8"))
        download = {
            "type": infer_download_type(ticker, "US", us_cfg),
            "ir_roots": [],
        }
        if cik:
            download["cik"] = cik
        classification = {**DEFAULT_CLASSIFICATION}
        entry = {
            "company": company,
            "market": "US",
            "exchange": EXCHANGE_META.get(ticker, "—"),
            "onboarded": today,
            "download": download,
            "classification": classification,
            "investment_sleeve": "sp500_liquidity",
        }
        holdings[ticker] = entry
        save_registry(reg)

    # Refresh us_ticker_config so download_us_investor_docs recognizes the ticker
    subprocess.run(
        [PY, str(SCRIPTS / "sync_portfolio_from_registry.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )

    if not already:
        scaffold_folder(ticker, company, "US", "")
        write_status(ROOT / ticker, "scaffold")
        write_thesis(ticker, company, entry.get("classification") or DEFAULT_CLASSIFICATION)
        subprocess.run(
            [PY, str(SCRIPTS / "scan_third_party_sources.py"), ticker, "--with-hk", "--date", today],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        subprocess.run(
            [PY, str(SCRIPTS / "scaffold_cross_check.py"), ticker, "--date", today],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        initialize_proof_first_valuation(ticker, today)

    ret_ok, ret_detail = write_returns(ticker)
    if sleep_s:
        time.sleep(sleep_s)

    dl_ok, dl_detail = True, "skipped"
    if not skip_download:
        write_status(ROOT / ticker, "downloading")
        dl_ok, dl_detail = run_download(ticker, download)
        n_pdf = sum(1 for _ in (ROOT / ticker).rglob("*.pdf"))
        if not dl_ok and n_pdf >= 1:
            dl_ok = True
            dl_detail = f"{dl_detail}; partial OK ({n_pdf} PDFs)"

    subprocess.run(
        [PY, str(SCRIPTS / "build_filing_evidence.py"), ticker],
        cwd=ROOT, check=False, capture_output=True,
    )
    initialize_proof_first_valuation(ticker, today)

    write_status(
        ROOT / ticker,
        "complete" if dl_ok else "failed",
        error=None if dl_ok else dl_detail,
        extra={"download_detail": dl_detail, "returns": ret_detail, "deep_dive_pending": True},
    )
    write_pending_review(ticker, company, "US", dl_ok, dl_detail)

    row = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": ticker,
        "status": "ok" if dl_ok else "download_failed",
        "returns_ok": ret_ok,
        "returns": ret_detail,
        "download": dl_detail,
        "company": company,
        "resumed": already,
    }
    append_status(row)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--skip-download", action="store_true", help="Scaffold+returns only")
    ap.add_argument("--sleep", type=float, default=0.8, help="Sleep after Yahoo fetch")
    ap.add_argument("--no-dashboard", action="store_true", help="Skip end-of-batch dashboard rebuild")
    ap.add_argument("--skip-indexes", action="store_true", help="Skip full-tree build_folder_indexes (faster, less dirty)")
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()

    reg = load_registry()
    missing = missing_sp500(reg)
    log(f"Missing S&P names: {len(missing)}")
    if args.list_only:
        for t in missing[args.offset : args.offset + args.batch_size]:
            print(t)
        print(f"# total_missing={len(missing)} offset={args.offset} batch={args.batch_size}")
        return 0

    batch = missing[args.offset : args.offset + args.batch_size]
    if not batch:
        log("Nothing to do at this offset")
        return 0

    titles = load_sp500_meta()
    results: list[dict] = []
    for i, ticker in enumerate(batch):
        info = titles.get(ticker) or titles.get(ticker.replace(".", "-")) or titles.get(ticker.replace("-", "."))
        if info:
            company, cik = info[0], info[1]
        else:
            company, cik = ticker, lookup_cik_one(ticker)
        log(f"\n[{i+1}/{len(batch)}] ONBOARD {ticker} — {company}")
        try:
            row = onboard_one(
                ticker,
                company,
                cik,
                skip_download=args.skip_download,
                sleep_s=args.sleep,
            )
        except Exception as exc:
            row = {"ticker": ticker, "status": "error", "detail": str(exc)}
            append_status(row)
            log(f"ERROR {ticker}: {exc}")
        results.append(row)
        log(f"  -> {row.get('status')} returns={row.get('returns_ok')} {row.get('download') or row.get('detail') or ''}")

    # Once per batch (token + time efficient)
    log("\n=== batch finalize: sync portfolio ===")
    subprocess.run([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], cwd=ROOT, check=False)
    if not args.skip_indexes:
        log("=== folder indexes ===")
        subprocess.run([PY, str(SCRIPTS / "build_folder_indexes.py")], cwd=ROOT, check=False)
    if not args.no_dashboard:
        log("=== dashboard rebuild ===")
        subprocess.run([PY, str(SCRIPTS / "build_dashboard_data.py")], cwd=ROOT, check=False)

    ok = [r["ticker"] for r in results if r.get("status") in ("ok", "skipped", "download_failed")]
    failed = [r["ticker"] for r in results if r.get("status") == "error"]
    log("\n=== BATCH SUMMARY ===")
    log(f"offset={args.offset} size={len(batch)} okish={len(ok)} errors={len(failed)}")
    log(f"DEEP_DIVE_TICKERS={','.join(r['ticker'] for r in results)}")
    log(f"remaining_after≈{max(0, len(missing) - len(batch))}")
    summary = {
        "offset": args.offset,
        "batch_size": args.batch_size,
        "tickers": [r["ticker"] for r in results],
        "results": results,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = ROOT / "_system" / "reference" / "market-data" / "index" / f"sp500_onboard_batch_{args.offset}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log(f"Wrote {out.relative_to(ROOT)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
