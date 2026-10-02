"""Pull FULL-history daily bars from Yahoo chart v8 for the study universe.

Stores the raw vendor arrays (open/high/low/close/adjclose/volume) per symbol so
the production adjustment (adjclose/close ratio applied to OHLC) can be replayed
exactly. Read-only HTTPS; no ThetaData, no IB Gateway.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS as OUT, MANIFEST_PATH, REPO  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (compatible; MagisTechnicalResearch/1.0)"
CUTOFF = "2026-10-01"  # exclude today's partial session (study run 2026-10-01 during RTH)

INDEX_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA", "EWJ", "VXX", "HYG", "LQD", "TLT", "UUP", "EFA", "EEM",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
]
EXTRA = ["^GSPC", "^VIX", "^IXIC", "^RUT", "^NDX", "^DJI",
         "XIC.TO", "IEUR", "ISF.L", "^OMX", "1321.T", "STW.AX", "^NSEI"]


def safe(symbol: str) -> str:
    return symbol.replace("^", "IDX_").replace("/", "_").replace("=", "_")


def fetch(symbol: str) -> pd.DataFrame:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?"
        + urllib.parse.urlencode({
            "period1": -2208988800,
            "period2": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "interval": "1d",
            "events": "div,splits",
        })
    )
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as response:
                payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):  # unknown/delisted symbol: permanent, don't back off
                raise RuntimeError(f"{symbol}: HTTP {exc.code}") from exc
            last = exc
            time.sleep(2.0 * (attempt + 1) ** 2)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2.0 * (attempt + 1) ** 2)
    else:
        raise RuntimeError(f"{symbol}: {last}")
    result = payload["chart"]["result"][0]
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or [None] * len(ts)

    def col(key):
        values = quote.get(key) or [None] * len(ts)
        return np.array([np.nan if v is None else float(v) for v in values], dtype="float64")

    frame = pd.DataFrame({
        "ts": np.array(ts, dtype="int64"),
        "open": col("open"), "high": col("high"), "low": col("low"), "close": col("close"),
        "adjclose": np.array([np.nan if v is None else float(v) for v in adj], dtype="float64"),
        "volume": col("volume"),
    })
    # production: datetime.fromtimestamp(ts, tz=utc).strftime('%Y-%m-%d')
    frame["date"] = (pd.Timestamp("1970-01-01") + pd.to_timedelta(frame["ts"], unit="s")).dt.strftime("%Y-%m-%d")
    frame = frame[frame["date"] < CUTOFF].reset_index(drop=True)
    meta = result.get("meta") or {}
    frame.attrs["meta"] = {k: meta.get(k) for k in ("symbol", "currency", "exchangeName", "instrumentType", "firstTradeDate", "gmtoffset", "timezone")}
    return frame


def main() -> int:
    summary = json.loads((REPO / "dashboard/data/technical_summary.json").read_text(encoding="utf-8"))
    by_ticker = summary["by_ticker"]
    jobs: dict[str, dict] = {}
    for ticker, row in by_ticker.items():
        symbol = str(row.get("source", "")).split(":", 1)[1]
        jobs[symbol] = {"kind": "stock", "ticker": ticker, "benchmark": row.get("benchmark")}
    for symbol in INDEX_UNIVERSE + EXTRA:
        jobs.setdefault(symbol, {"kind": "index"})
    manifest_path = MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    todo = [s for s in jobs if not (OUT / f"{safe(s)}.parquet").exists()]
    print(f"{len(jobs)} symbols, {len(todo)} to fetch", flush=True)

    def one(symbol):
        frame = fetch(symbol)
        frame.to_parquet(OUT / f"{safe(symbol)}.parquet", index=False)
        return symbol, len(frame), (frame["date"].iloc[0] if len(frame) else None), frame.attrs.get("meta")

    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, s): s for s in todo}
        for future in as_completed(futures):
            symbol = futures[future]
            done += 1
            try:
                sym, n, first, meta = future.result()
                manifest[symbol] = {**jobs[symbol], "rows": n, "first": first, "meta": meta, "file": f"{safe(symbol)}.parquet"}
            except Exception as exc:  # noqa: BLE001
                manifest[symbol] = {**jobs[symbol], "error": str(exc)[:300]}
                print(f"ERR {symbol}: {exc}", flush=True)
            if done % 50 == 0:
                print(f"{done}/{len(todo)}", flush=True)
                manifest_path.write_text(json.dumps(manifest, indent=1))
    for symbol in jobs:
        manifest.setdefault(symbol, {**jobs[symbol]})
        manifest[symbol].update({k: v for k, v in jobs[symbol].items()})
    manifest_path.write_text(json.dumps(manifest, indent=1))
    errors = [s for s, m in manifest.items() if m.get("error")]
    print(f"done; errors={len(errors)} {errors[:20]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
