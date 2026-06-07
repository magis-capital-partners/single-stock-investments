#!/usr/bin/env python3
"""P5 — JPX ETF beneficiary shares + creation/redemption unit metadata.

Downloads:
  - JPX ETF database (annual): creation/redemption units, year-end AUM
  - JPX monthly beneficiary shares (前月末 受益権口数)

Writes:
  research/model/data/jpx_etf_meta.csv
  research/model/data/jpx_etf_shares_monthly.csv
  research/model/data/jpx_etf_units_daily.csv
  research/model/data/jpx_scrape_manifest.json

Run: python3 7176.T/_scripts/download_jpx_etf_units.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "research" / "model"
DATA = MODEL / "data"
REGISTRY = MODEL / "fund_registry.json"
RAW = DATA / "jpx_raw"
USER_AGENT = "MarvinResearch/1.0 (7176.T JPX ETF units scrape)"

ETF_DB_URL = "https://www.jpx.co.jp/equities/products/etfs/investors/tvdivq0000005cdd-att/nlsgeu000000vx9t.xlsx"
SHARES_BASE = "https://www.jpx.co.jp/equities/products/etfs/base-price/nlsgeu0000051wtj-att"
BASE_PRICE_PAGE = "https://www.jpx.co.jp/equities/products/etfs/base-price/index.html"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _load_tickers() -> list[str]:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [e["ticker"].replace(".T", "") for e in reg.get("etfs", [])]


def download_etf_database(sess: requests.Session) -> bytes:
    r = sess.get(ETF_DB_URL, timeout=120)
    r.raise_for_status()
    return r.content


def parse_etf_database(xlsx: bytes, tickers: list[str]) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(xlsx), sheet_name=0, header=2)
    code_col = df.columns[1]
    aum_col = df.columns[12]
    nav_col = df.columns[40]
    create_col = df.columns[34]
    redeem_col = df.columns[37]
    rows: list[dict] = []
    ticker_set = set(tickers)
    for _, r in df.iterrows():
        raw_code = r[code_col]
        if pd.isna(raw_code):
            continue
        code = str(int(raw_code)) if isinstance(raw_code, (int, float)) else str(raw_code).strip()
        if code not in ticker_set:
            continue
        rows.append({
            "ticker": f"{code}.T",
            "code": code,
            "aum_million_jpy_ye": r[aum_col],
            "nav_jpy_ye": r[nav_col],
            "creation_unit_shares": r[create_col],
            "redemption_unit_shares": r[redeem_col],
            "source": ETF_DB_URL,
            "tag": "[Market]",
        })
    return pd.DataFrame(rows)


def discover_latest_shares_url(sess: requests.Session) -> str | None:
    try:
        html = sess.get(BASE_PRICE_PAGE, timeout=60).text
    except requests.RequestException:
        return None
    matches = re.findall(r'href="(/equities/products/etfs/base-price/[^"]+/\d{6}_etfs\.xlsx)"', html)
    if not matches:
        return None
    # Prefer highest YYYYMM in filename
    def _ym(path: str) -> int:
        m = re.search(r"/(\d{6})_etfs\.xlsx", path)
        return int(m.group(1)) if m else 0

    best = max(matches, key=_ym)
    return f"https://www.jpx.co.jp{best}"


def download_monthly_shares(sess: requests.Session, url: str) -> bytes:
    r = sess.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def parse_monthly_shares(xlsx: bytes, tickers: list[str]) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(xlsx), header=0)
    df.columns = ["code", "name", "listed_shares", "as_of"]
    df["code"] = df["code"].astype(str).str.replace(".0", "", regex=False)
    df = df[df["code"].isin(tickers)].copy()
    df["ticker"] = df["code"] + ".T"
    df["as_of"] = pd.to_datetime(df["as_of"]).dt.strftime("%Y-%m-%d")
    df["tag"] = "[Market]"
    return df[["as_of", "ticker", "code", "listed_shares", "name", "tag"]]


def _merge_stored_monthly(new_df: pd.DataFrame, path: Path) -> pd.DataFrame:
    if path.exists() and not new_df.empty:
        old = pd.read_csv(path)
        combined = pd.concat([old, new_df], ignore_index=True)
    elif not new_df.empty:
        combined = new_df
    else:
        return pd.DataFrame()
    combined = combined.drop_duplicates(["ticker", "as_of"], keep="last")
    return combined.sort_values(["ticker", "as_of"])


def build_daily_units(
    monthly: pd.DataFrame,
    meta: pd.DataFrame,
    nav_path: Path,
) -> pd.DataFrame:
    """Forward-fill JPX monthly listed shares to daily; AUM = shares × Yahoo NAV."""
    if monthly.empty or not nav_path.exists():
        return pd.DataFrame()
    nav_df = pd.read_csv(nav_path, parse_dates=["date"])
    nav_df = nav_df[nav_df["ticker"].isin(monthly["ticker"].unique())]
    meta_map = meta.set_index("ticker") if not meta.empty else pd.DataFrame()

    rows: list[dict] = []
    for tk, mg in monthly.groupby("ticker"):
        mg = mg.sort_values("as_of")
        nav_s = nav_df[nav_df["ticker"] == tk].set_index("date")["nav_jpy"].sort_index()
        if nav_s.empty:
            continue
        snap_dates = pd.to_datetime(mg["as_of"])
        share_series = pd.Series(mg["listed_shares"].values, index=snap_dates).sort_index()
        # Reindex to all NAV dates, forward-fill from last JPX month-end snapshot
        aligned_shares = share_series.reindex(nav_s.index, method="ffill")
        create_u = meta_map.loc[tk, "creation_unit_shares"] if tk in meta_map.index else np.nan
        redeem_u = meta_map.loc[tk, "redemption_unit_shares"] if tk in meta_map.index else np.nan
        for dt, nav in nav_s.items():
            sh = aligned_shares.get(dt)
            if pd.isna(sh):
                continue
            aum_jpy = float(sh) * float(nav)
            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "ticker": tk,
                "listed_shares": float(sh),
                "creation_unit_shares": create_u,
                "redemption_unit_shares": redeem_u,
                "nav_jpy": float(nav),
                "aum_jpym": aum_jpy / 1e6,
                "units_method": "[Market/JPX]",
                "tag": "[Market/JPX]",
            })
    return pd.DataFrame(rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    tickers = _load_tickers()
    sess = _session()

    db_bytes = download_etf_database(sess)
    (RAW / "etf_database.xlsx").write_bytes(db_bytes)
    meta = parse_etf_database(db_bytes, tickers)
    meta.to_csv(DATA / "jpx_etf_meta.csv", index=False)

    shares_url = discover_latest_shares_url(sess)
    monthly_new = pd.DataFrame()
    shares_saved = None
    if shares_url:
        sh_bytes = download_monthly_shares(sess, shares_url)
        fname = shares_url.rsplit("/", 1)[-1]
        shares_saved = RAW / fname
        shares_saved.write_bytes(sh_bytes)
        monthly_new = parse_monthly_shares(sh_bytes, tickers)

    monthly_path = DATA / "jpx_etf_shares_monthly.csv"
    monthly = _merge_stored_monthly(monthly_new, monthly_path)
    if not monthly.empty:
        monthly.to_csv(monthly_path, index=False)

    nav_path = DATA / "etf_nav_daily.csv"
    daily = build_daily_units(monthly, meta, nav_path)
    if not daily.empty:
        daily.to_csv(DATA / "jpx_etf_units_daily.csv", index=False)

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "etf_database_url": ETF_DB_URL,
        "shares_url": shares_url,
        "shares_saved": str(shares_saved) if shares_saved else None,
        "meta_rows": len(meta),
        "monthly_rows": len(monthly),
        "daily_rows": len(daily),
        "tickers": tickers,
    }
    (DATA / "jpx_scrape_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
