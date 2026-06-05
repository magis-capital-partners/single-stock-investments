#!/usr/bin/env python3
"""P5 — Scrape JITA (投資信託協会) industry fund flows from free Excel downloads.

Downloads B-1 資産増減状況 (I0112B_pub_m.xlsx):
  - Sheet 株式 → jita_equity_net_flow (stock trusts, 百万円)
  - Sheet 株式 追加型 ＥＴＦ → jita_etf_net_flow (listed ETFs, 百万円)

Writes:
  research/model/data/jita_flows_monthly.csv
  research/model/data/jita_scrape_manifest.json
  research/model/data/jita_raw/I0112B_pub_m.xlsx

Run: python3 7176.T/_scripts/download_jita_flows.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research" / "model" / "data"
RAW = DATA / "jita_raw"
BASE_URL = "https://www.toushin.or.jp/tws/toukei_dw"
B1_FILE = "I0112B_pub_m.xlsx"
USER_AGENT = "MarvinResearch/1.0 (7176.T JITA flows scrape)"

# Column index for 資金増減額 (net flows) in 百万円
FLOW_COL = 5


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def download_b1(sess: requests.Session) -> bytes:
    url = f"{BASE_URL}/{B1_FILE}"
    r = sess.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def _parse_sheet(xlsx: bytes, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(xlsx), sheet_name=sheet, header=None)
    rows: list[dict] = []
    for _, r in df.iterrows():
        label = r.iloc[1]
        if pd.isna(label):
            continue
        m = re.match(r"(\d{4})年(\d{1,2})月", str(label).strip())
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        raw = r.iloc[FLOW_COL]
        if pd.isna(raw) or str(raw).strip() in ("-", ""):
            continue
        try:
            flow_mjpy = float(raw)
        except (TypeError, ValueError):
            continue
        month_end = pd.Timestamp(y, mo, 1) + pd.offsets.MonthEnd(0)
        rows.append({
            "month": month_end.strftime("%Y-%m-%d"),
            "flow_million_jpy": flow_mjpy,
            "flow_oku_jpy": flow_mjpy / 100.0,  # 百万円 → 億円
        })
    return pd.DataFrame(rows)


def build_monthly_table(xlsx: bytes) -> pd.DataFrame:
    eq = _parse_sheet(xlsx, "株式").rename(columns={
        "flow_million_jpy": "jita_equity_flow_mjpy",
        "flow_oku_jpy": "jita_equity_net_flow_bn_jpy",
    })
    etf = _parse_sheet(xlsx, "株式 追加型 ＥＴＦ").rename(columns={
        "flow_million_jpy": "jita_etf_flow_mjpy",
        "flow_oku_jpy": "jita_etf_net_flow_bn_jpy",
    })
    out = eq.merge(etf[["month", "jita_etf_net_flow_bn_jpy", "jita_etf_flow_mjpy"]], on="month", how="outer")
    out = out.sort_values("month")
    out["tag"] = "[Market]"
    out["source"] = f"{BASE_URL}/{B1_FILE}"
    out["note"] = "JITA B-1 資金増減額; bn columns are 億円 (flow_mjpy/100)"
    return out


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    sess = _session()
    content = download_b1(sess)
    dest = RAW / B1_FILE
    dest.write_bytes(content)

    monthly = build_monthly_table(content)
    monthly.to_csv(DATA / "jita_flows_monthly.csv", index=False)

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_url": f"{BASE_URL}/{B1_FILE}",
        "saved_path": str(dest),
        "rows": len(monthly),
        "month_range": [monthly["month"].min(), monthly["month"].max()] if len(monthly) else [],
        "sheets": ["株式", "株式 追加型 ＥＴＦ"],
    }
    (DATA / "jita_scrape_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
