"""Phase 5d: load delisted-company histories from a data vendor.

Free sources drop dead companies (Yahoo returns one bar), so the survivorship-
free replication needs vendor data. This loader takes any vendor export, one
file per ticker, and converts it into the study's raw bar format so the normal
pipeline (stock_batch -> phase5_panel -> phase5_analysis) includes it.

Expected layout under $TECH_STUDY_VENDOR_DIR (or --vendor-dir):
  <TICKER>.csv | <TICKER>.parquet   columns: date, open, high, low, close, volume
                                    and optionally adj_close (total-return adjusted)
  delistings.csv (optional)         ticker, delist_date, delisting_return, reason

delisting_return is the CRSP-style return from the last trade to the final
payout (e.g. -0.95 for a bankruptcy, +0.25 for a cash takeover premium already
paid). It is appended as a final synthetic bar on delist_date, because a
failure's last loss usually happens off-exchange and leaving it out
re-introduces exactly the bias this phase removes.

Usage:
  python vendor_bars.py --vendor-dir D:/norgate_export
  python stock_batch.py 2 vendor_delisted
  python phase5_panel.py 2 && python phase5_analysis.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS, MANIFEST_PATH  # noqa: E402

REQUIRED = ["date", "open", "high", "low", "close", "volume"]


def safe(symbol: str) -> str:
    return symbol.replace("^", "IDX_").replace("/", "_").replace("=", "_")


def read_vendor_file(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={"adjclose": "adj_close", "adjusted_close": "adj_close", "vol": "volume"})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def to_study_bars(df: pd.DataFrame, delisting_return: float | None = None, delist_date: str | None = None) -> pd.DataFrame:
    """Vendor bars -> the raw Yahoo-shaped frame stock_batch expects."""
    out = pd.DataFrame({
        "ts": (pd.to_datetime(df["date"]) - pd.Timestamp("1970-01-01")).dt.total_seconds().astype("int64") + 13 * 3600 + 30 * 60,
        "open": df["open"].astype(float), "high": df["high"].astype(float), "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "adjclose": (df["adj_close"] if "adj_close" in df.columns else df["close"]).astype(float),
        "volume": df["volume"].astype(float), "date": df["date"],
    })
    if delisting_return is not None and np.isfinite(delisting_return) and delist_date:
        last = out.iloc[-1]
        d = pd.Timestamp(delist_date)
        if d.strftime("%Y-%m-%d") <= last["date"]:
            d = pd.Timestamp(last["date"]) + pd.offsets.BDay(1)
        px = float(last["close"]) * (1.0 + float(delisting_return))
        adj = float(last["adjclose"]) * (1.0 + float(delisting_return))
        terminal = {"ts": int((d - pd.Timestamp("1970-01-01")).total_seconds()) + 13 * 3600 + 30 * 60,
                    "open": px, "high": max(px, 1e-6), "low": max(px, 1e-6), "close": max(px, 1e-6),
                    "adjclose": max(adj, 1e-6), "volume": 0.0, "date": d.strftime("%Y-%m-%d")}
        out = pd.concat([out, pd.DataFrame([terminal])], ignore_index=True)
    return out


def load(vendor_dir: Path, manifest_path: Path = MANIFEST_PATH, bars_dir: Path = BARS) -> dict:
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    dl = {}
    dl_path = vendor_dir / "delistings.csv"
    if dl_path.exists():
        t = pd.read_csv(dl_path)
        t.columns = [c.strip().lower() for c in t.columns]
        dl = {str(r.ticker).upper(): r for r in t.itertuples(index=False)}
    loaded, errors = [], {}
    bars_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(vendor_dir.glob("*")):
        if path.name == "delistings.csv" or path.suffix not in (".csv", ".parquet"):
            continue
        ticker = path.stem.upper()
        try:
            df = read_vendor_file(path)
            meta = dl.get(ticker)
            bars = to_study_bars(df, getattr(meta, "delisting_return", None) if meta else None,
                                 getattr(meta, "delist_date", None) if meta else None)
            symbol = f"{ticker}.VENDOR"
            bars.to_parquet(bars_dir / f"{safe(symbol)}.parquet", index=False)
            manifest[symbol] = {"kind": "vendor_delisted", "ticker": ticker, "benchmark": "SPY", "rows": int(len(bars)),
                                "first": bars["date"].iloc[0], "file": f"{safe(symbol)}.parquet", "source": "vendor",
                                "delist_reason": getattr(meta, "reason", None) if meta else None}
            loaded.append(symbol)
        except Exception as exc:  # noqa: BLE001
            errors[path.name] = str(exc)[:200]
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return {"loaded": loaded, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor-dir", default=os.environ.get("TECH_STUDY_VENDOR_DIR"))
    args = ap.parse_args()
    if not args.vendor_dir:
        print("set --vendor-dir or TECH_STUDY_VENDOR_DIR to a folder of vendor bar files", file=sys.stderr)
        return 2
    res = load(Path(args.vendor_dir))
    print(json.dumps(res, indent=1))
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
