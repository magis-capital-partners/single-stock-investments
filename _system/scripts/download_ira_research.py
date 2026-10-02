#!/usr/bin/env python3
"""Download Tier A/B documents for Darwin IRA research plan.

  python3 _system/scripts/download_ira_research.py --tier A
  python3 _system/scripts/download_ira_research.py --tier B
  python3 _system/scripts/download_ira_research.py --ticker CPRT
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKET = ROOT / "_system" / "reference" / "market-data"
MANIFEST = MARKET / "ira_download_manifest.json"
UA = "Mozilla/5.0 (compatible; MarvinIRAResearch/1.0)"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stooq_csv import StooqNotCsvError, check_stooq_csv  # noqa: E402

# Public URLs (Tier B macro + benchmarks)
TIER_B_URLS = {
    "french/F-F_Research_Data_5_Factors_2x3.csv": (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3.csv"
    ),
    "macro/fred_dgs10.csv": (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    ),
    "macro/fred_cpi.csv": (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
    ),
    "macro/fred_vix.csv": (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
    ),
    "ira-compliance/README.txt": None,
}

# Daily benchmark history from Yahoo chart v8 (the endpoint
# build_technical_signals.fetch_yahoo_history uses). These were Stooq URLs,
# but Stooq answers scripted CSV requests with an HTML bot-check page and
# HTTP 200, and fetch_url stored that page as spy_us.csv / bnd_us.csv from
# the first run on 2026-06-01 onward. They never held a price.
TIER_B_YAHOO_DAILY = {
    "benchmarks/spy_us.csv": "SPY",
    "benchmarks/bnd_us.csv": "BND",
}
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
DAILY_CSV_HEADER = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]


def load_registry_holdings() -> list[str]:
    reg = json.loads((ROOT / "_system" / "portfolio" / "registry.json").read_text(encoding="utf-8"))
    return sorted((reg.get("holdings") or {}).keys())


def _write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)


def fetch_url(url: str, dest: Path) -> tuple[bool, str]:
    """Download url to dest. A body that is HTML is a failure and is never written.

    Data hosts answer bot checks and error pages with HTTP 200, so the status
    code proves nothing; the previous file is left in place instead.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = urllib.request.urlopen(req, timeout=180).read()
    except Exception as exc:
        return False, str(exc)
    head = data[:512].lstrip(b"\xef\xbb\xbf").lstrip().lower()
    if head.startswith(b"<"):
        return False, f"HTML response, not data (not written): {url}"
    if "stooq.com" in url:
        try:
            check_stooq_csv(data)
        except StooqNotCsvError as exc:
            return False, f"{exc} (not written): {url}"
    _write_atomic(dest, data)
    return True, str(dest.relative_to(ROOT))


def fetch_yahoo_daily_csv(symbol: str, dest: Path) -> tuple[bool, str]:
    """Full daily history for symbol as a Date,Open,High,Low,Close,... CSV."""
    end = int(datetime.now(timezone.utc).timestamp()) + 86400
    url = (
        f"{YAHOO_CHART_URL}/{urllib.parse.quote(symbol, safe='')}"
        f"?period1=0&period2={end}&interval=1d&events=div,splits"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=60).read())
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        adjclose = ((result["indicators"].get("adjclose") or [{}])[0]).get("adjclose") or []
    except Exception as exc:
        return False, f"yahoo {symbol}: {exc}"
    # Leave out today's bar while the session is open: it is a partial day.
    regular = ((result.get("meta") or {}).get("currentTradingPeriod") or {}).get("regular") or {}
    now = datetime.now(timezone.utc).timestamp()
    if regular.get("start") and regular.get("end") and now < regular["end"]:
        timestamps = [ts for ts in timestamps if ts < regular["start"]]

    def col(name: str, i: int):
        values = quote.get(name) or []
        return values[i] if i < len(values) else None

    rows = []
    for i, ts in enumerate(timestamps):
        close = col("close", i)
        if close is None:
            continue
        adj = adjclose[i] if i < len(adjclose) and adjclose[i] is not None else close
        rows.append([
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            *(round(v, 4) if v is not None else "" for v in (col("open", i), col("high", i), col("low", i))),
            round(close, 4),
            round(adj, 4),
            int(col("volume", i) or 0),
        ])
    if len(rows) < 250:
        return False, f"yahoo {symbol}: only {len(rows)} usable rows (not written)"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(DAILY_CSV_HEADER)
    w.writerows(rows)
    _write_atomic(dest, buf.getvalue().encode("utf-8"))
    return True, f"{dest.relative_to(ROOT)} (yahoo {symbol}, {len(rows)} rows, {rows[0][0]}..{rows[-1][0]})"


def download_ticker_returns(ticker: str, market: str) -> tuple[bool, str]:
    """Yahoo monthly returns via existing price helper."""
    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from darwin.prices import fetch_yahoo_monthly  # noqa: E402
    from darwin.symbols import yahoo_for_ticker  # noqa: E402

    ysym = yahoo_for_ticker(ticker, market)
    dates, rets, src = fetch_yahoo_monthly(ysym, months=120)
    if len(rets) < 6:
        return False, f"insufficient returns ({src})"
    out = MARKET / "returns" / f"{ticker.replace('.', '_')}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "monthly_return", "source"])
        for d, r in zip(dates, rets):
            w.writerow([d, round(r, 6), src])
    return True, str(out.relative_to(ROOT))


def tier_a(tickers: list[str] | None, with_sec: bool = False) -> list[dict]:
    reg = json.loads((ROOT / "_system" / "portfolio" / "registry.json").read_text(encoding="utf-8"))
    holdings = reg.get("holdings") or {}
    universe = tickers or load_registry_holdings()
    log: list[dict] = []
    ok, msg = download_ticker_returns("SPY", "US")
    log.append({"ticker": "SPY", "tier": "A", "type": "benchmark_returns", "ok": ok, "path": msg})
    for t in universe:
        m = (holdings.get(t) or {}).get("market", "US")
        ok, msg = download_ticker_returns(t, m)
        log.append({"ticker": t, "tier": "A", "type": "returns_csv", "ok": ok, "path": msg})
        if not with_sec:
            continue
        py = ROOT / t / "investor-documents" / f"download_{t.lower().split('.')[0]}_investor_docs.py"
        for alt in (ROOT / t / "investor-documents").glob("download_*_investor_docs.py"):
            py = alt
            break
        if py.exists():
            try:
                subprocess.run([sys.executable, str(py)], cwd=str(ROOT), timeout=300, check=False)
                log.append({"ticker": t, "tier": "A", "type": "sec_ir", "ok": True, "path": str(py.relative_to(ROOT))})
            except subprocess.TimeoutExpired:
                log.append({"ticker": t, "tier": "A", "type": "sec_ir", "ok": False, "path": "timeout"})
    return log


def tier_b() -> list[dict]:
    log: list[dict] = []
    readme = MARKET / "ira-compliance" / "README.txt"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "Download IRS Pub 590-B manually: https://www.irs.gov/publications/p590b\n",
        encoding="utf-8",
    )
    log.append({"tier": "B", "type": "ira_compliance_note", "ok": True, "path": str(readme.relative_to(ROOT))})
    for rel, url in TIER_B_URLS.items():
        if url is None:
            continue
        dest = MARKET / rel
        ok, msg = fetch_url(url, dest)
        log.append({"tier": "B", "type": rel, "ok": ok, "path": msg})
    for rel, symbol in TIER_B_YAHOO_DAILY.items():
        ok, msg = fetch_yahoo_daily_csv(symbol, MARKET / rel)
        log.append({"tier": "B", "type": rel, "ok": ok, "path": msg})
    return log


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["A", "B", "all"], default="all")
    parser.add_argument("--ticker", help="Limit Tier A to one ticker")
    parser.add_argument(
        "--with-sec",
        action="store_true",
        help="Also run per-ticker SEC/IR download scripts (slow)",
    )
    args = parser.parse_args()

    log: list[dict] = []
    if args.tier in ("A", "all"):
        tickers = [args.ticker] if args.ticker else None
        log.extend(tier_a(tickers, with_sec=args.with_sec))
    if args.tier in ("B", "all"):
        log.extend(tier_b())

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": log,
        "ok": sum(1 for r in log if r.get("ok")),
        "fail": sum(1 for r in log if not r.get("ok")),
    }
    MARKET.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"IRA research download: {payload['ok']} ok, {payload['fail']} fail → {MANIFEST}")


if __name__ == "__main__":
    main()
