"""Phase 5a: a point-in-time S&P 500 universe, as close to survivorship-free as
free data allows.

Membership is reconstructed from Wikipedia's current constituent list (with
"Date added") and its "Historical components of the S&P 500" change table
(dated additions/removals with reasons, dense from 1997). Every ticker that was
ever a member is then requested from Yahoo:

* still trading under the same symbol -> full history, kept;
* history that starts after the membership began -> a reused ticker, rejected;
* one bar / 404 -> delisted; recorded as MISSING with its removal reason.

The missing set is exactly the survivorship gap, and its removal reasons
(acquisition vs. distress) are what the bound in phase5_analysis.py uses.
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS, DATA, MANIFEST_PATH, RESULTS  # noqa: E402
from fetch_bars import fetch, safe  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; MagisResearch/1.0)"}
CURRENT_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HISTORY_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
MEMBERSHIP = DATA / "sp500_membership.parquet"
DISTRESS = re.compile(r"bankrupt|chapter 11|insolven|delist|receivership|liquidat|default|fraud|govern(ment)? (took|seiz)|conservatorship|financial (difficult|distress)|going concern", re.I)
ACQUIRED = re.compile(r"acquir|merg|bought|purchase|taken private|take-private|buyout", re.I)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")


def _date(text) -> date | None:
    text = re.sub(r"\[.*?\]", "", str(text or "")).strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d", "%b %d, %Y", "%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def yahoo_symbol(ticker: str) -> str:
    t = str(ticker).strip().upper()
    return t.replace(".", "-")


def load_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    cur = pd.read_html(io.StringIO(_get(CURRENT_URL)))[0]
    hist = pd.read_html(io.StringIO(_get(HISTORY_URL)))[0]
    hist.columns = ["date", "added", "added_name", "removed", "removed_name", "reason", "refs"]
    hist["date"] = hist["date"].map(_date)
    cur = cur.rename(columns={"Symbol": "ticker", "Security": "name", "Date added": "date_added"})
    cur["date_added"] = cur["date_added"].map(_date)
    return cur, hist


def build_membership(cur: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, membership interval). end=None means still a member."""
    first_change = min(d for d in hist["date"] if d)
    rows = []
    for r in cur.itertuples(index=False):
        rows.append({"ticker": r.ticker, "name": r.name, "start": r.date_added or first_change, "end": None,
                     "status": "current", "reason": None})
    added_on = {}
    for r in hist.itertuples(index=False):
        if isinstance(r.added, str) and r.added.strip():
            added_on.setdefault(r.added.strip().upper(), []).append(r.date)
    for r in hist.itertuples(index=False):
        if not (isinstance(r.removed, str) and r.removed.strip()) or r.date is None:
            continue
        t = r.removed.strip().upper()
        starts = [d for d in added_on.get(t, []) if d and d < r.date]
        rows.append({"ticker": t, "name": r.removed_name, "start": max(starts) if starts else first_change,
                     "end": r.date, "status": "removed", "reason": str(r.reason)})
    m = pd.DataFrame(rows)
    m["reason_class"] = m["reason"].fillna("").map(
        lambda s: "distress" if DISTRESS.search(s) else "acquired" if ACQUIRED.search(s) else ("index_change" if s else None))
    return m


def main(workers: int = 6) -> int:
    cur, hist = load_tables()
    mem = build_membership(cur, hist)
    manifest = json.loads(MANIFEST_PATH.read_text())
    have = {s for s, v in manifest.items() if not v.get("error") and (v.get("rows") or 0) > 1}
    mem["yahoo"] = mem["ticker"].map(yahoo_symbol)
    todo = sorted(set(mem["yahoo"]) - have)
    print(f"{len(mem)} membership intervals, {mem['ticker'].nunique()} tickers; {len(todo)} not yet fetched", flush=True)

    def one(sym):
        try:
            frame = fetch(sym)
            if len(frame) <= 1:
                return sym, len(frame), None, None, "single_bar"
            frame.to_parquet(BARS / f"{safe(sym)}.parquet", index=False)
            return sym, len(frame), frame["date"].iloc[0], frame["date"].iloc[-1], None
        except Exception as exc:  # noqa: BLE001
            return sym, 0, None, None, str(exc)[:160]

    fetched = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(one, s) for s in todo]):
            sym, n, first, last, err = fut.result()
            fetched[sym] = {"rows": n, "first": first, "last": last, "error": err}
            if sym not in manifest and not err:
                manifest[sym] = {"kind": "pit_extra", "ticker": sym, "benchmark": "SPY", "rows": n, "first": first,
                                 "file": f"{safe(sym)}.parquet"}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1))

    def coverage(row):
        v = manifest.get(row.yahoo)
        info = fetched.get(row.yahoo)
        if (not v or v.get("error")) and info:
            return "missing_" + ("single_bar" if info.get("error") == "single_bar" else "error")
        if not v:
            return "missing_error"
        first = (v.get("first") or (info or {}).get("first") or "")[:10]
        start = row.start.isoformat() if row.start else "1900-01-01"
        if first and first > (pd.Timestamp(start) + pd.Timedelta(days=45)).date().isoformat():
            return "reused_or_late"  # history begins after the membership began
        return "ok"

    mem["coverage"] = [coverage(r) for r in mem.itertuples(index=False)]
    mem["start"] = mem["start"].astype(str)
    mem["end"] = mem["end"].astype(str)
    mem.to_parquet(MEMBERSHIP, index=False)
    summary = {
        "intervals": int(len(mem)), "tickers": int(mem["ticker"].nunique()),
        "coverage": mem["coverage"].value_counts().to_dict(),
        "removed_by_reason_and_coverage": mem[mem["status"] == "removed"].groupby(["reason_class", "coverage"]).size().rename("n").reset_index().to_dict("records"),
        "fetched_new": int(sum(1 for v in fetched.values() if not v["error"])),
        "as_of": date.today().isoformat(),
    }
    (RESULTS / "phase5_universe.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
