#!/usr/bin/env python3
"""P4 — Scrape Simplex mandate NAV from monthly reports + ETF prices.

Downloads SAM monthly PDFs (受益権月次レポート), parses NAV/AUM/returns,
backfills ETF history via yfinance, writes:
  research/model/data/mandate_nav_monthly.csv
  research/model/data/mandate_nav_detail.csv
  research/model/data/mandate_scrape_manifest.json

Run: python3 7176.T/_scripts/download_mandate_nav.py
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "research" / "model"
DATA = MODEL / "data"
CATALOG = MODEL / "mandate_funds.json"
PDF_DIR = DATA / "mandate_reports"
USER_AGENT = "MarvinResearch/1.0 (7176.T mandate NAV scrape)"

MONTH_END = {
    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _month_end_ts(year: int, month: int) -> pd.Timestamp:
    day = MONTH_END[month]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        day = 29
    return pd.Timestamp(year=year, month=month, day=day)


def parse_sam_monthly_pdf(text: str, fund_id: str) -> dict:
    """Extract NAV, AUM, as-of date, 1-month return from monthly report text."""
    out = {"fund_id": fund_id}
    m_date = re.search(r"(\d{4})年(\d{1,2})月末", text)
    if m_date:
        y, mo = int(m_date.group(1)), int(m_date.group(2))
        out["as_of"] = _month_end_ts(y, mo).strftime("%Y-%m-%d")
    m_alt = re.search(r"データは(\d{4})年(\d{1,2})月(\d{1,2})日現在", text)
    if m_alt and "as_of" not in out:
        y, mo, d = int(m_alt.group(1)), int(m_alt.group(2)), int(m_alt.group(3))
        out["as_of"] = pd.Timestamp(y, mo, d).strftime("%Y-%m-%d")

    nav_m = re.findall(r"【基準価額】\s*([\d,]+)\s*円", text)
    if nav_m:
        out["nav_jpy"] = float(nav_m[0].replace(",", ""))
    else:
        # Value Up layout: fund name then NAV on next line
        m_nav = re.search(
            r"シンプレクス・ジャパン・バリューアップ・ファンド\s*([\d,]+)円", text.replace("\n", " ")
        )
        if m_nav:
            out["nav_jpy"] = float(m_nav.group(1).replace(",", ""))

    aum_m = re.search(r"【純資産総額】\s*([\d.]+)\s*億円", text)
    if aum_m:
        out["aum_jpym"] = float(aum_m.group(1)) * 100.0  # 億円 -> JPY m
    else:
        m_aum2 = re.search(r"([\d.]+)億円\s*シンプレクス・ジャパン・バリューアップ", text.replace("\n", " "))
        if m_aum2:
            out["aum_jpym"] = float(m_aum2.group(1)) * 100.0

    ret_m = re.search(r"当ファンドの基準価額伸び率は([+-]?[\d.]+)%", text)
    if ret_m:
        out["month_ret"] = float(ret_m.group(1)) / 100.0
    else:
        # Orka table: "謳歌ファンド 1.86%" style near start
        ret2 = re.search(r"謳歌ファンド\s*([+-]?[\d.]+)%", text.replace("\n", " "))
        if ret2:
            out["month_ret"] = float(ret2.group(1)) / 100.0

    hwm = re.search(r"ハイ・ウォーター・マークは[「\"]([\d,]+)円", text)
    if hwm:
        out["high_water_mark_jpy"] = float(hwm.group(1).replace(",", ""))

    return out


def download_pdf(sess: requests.Session, url: str, dest: Path) -> bool:
    try:
        r = sess.get(url, timeout=60)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except requests.RequestException:
        return False


def extract_pdf_text(path: Path) -> str:
    import pypdf

    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages)


def scrape_sam_funds(sess: requests.Session, catalog: dict) -> list[dict]:
    rows: list[dict] = []
    base = catalog["docs_base"]
    manifest_pdfs: list[dict] = []

    for fund in catalog["sam_funds"]:
        prefix = fund["docs_prefix"]
        suffixes = [""] + fund.get("archive_suffixes", [])
        for suf in suffixes:
            fname = f"{prefix}{suf}Monthlyrpt.pdf"
            url = f"{base}/{fname}"
            dest = PDF_DIR / fund["id"] / fname
            ok = download_pdf(sess, url, dest)
            manifest_pdfs.append({"fund_id": fund["id"], "url": url, "saved": ok, "path": str(dest)})
            if not ok:
                continue
            parsed = parse_sam_monthly_pdf(extract_pdf_text(dest), fund["id"])
            if "as_of" not in parsed:
                continue
            parsed.update({
                "mandate_id": fund["mandate_id"],
                "source": "simplex_monthly_pdf",
                "source_url": url,
                "benchmark": fund["benchmark"],
                "perf_rate": fund.get("perf_rate"),
                "tag": fund.get("tag", "[Filing/Market]"),
            })
            rows.append(parsed)
            time.sleep(0.3)

    return rows, manifest_pdfs


def etf_monthly_history(ticker: str, start: str = "2019-09-01") -> pd.DataFrame:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(start=start, interval="1d", auto_adjust=True)
    if hist.empty:
        return pd.DataFrame()
    hist = hist.reset_index()
    hist["month"] = hist["Date"].dt.to_period("M")
    monthly = hist.groupby("month").agg(
        nav_jpy=("Close", "last"),
        month_start=("Close", "first"),
    ).reset_index()
    monthly["as_of"] = monthly["month"].dt.to_timestamp(how="end").dt.strftime("%Y-%m-%d")
    monthly["month_ret"] = monthly["nav_jpy"] / monthly["month_start"] - 1.0
    monthly["fund_id"] = ticker.replace(".T", "").lower()
    return monthly[["as_of", "fund_id", "nav_jpy", "month_ret"]]


def build_monthly_table(catalog: dict, sam_rows: list[dict]) -> pd.DataFrame:
    frames = []
    for row in sam_rows:
        frames.append(pd.DataFrame([{
            "as_of": row["as_of"],
            "fund_id": row["fund_id"],
            "mandate_id": row["mandate_id"],
            "nav_jpy": row.get("nav_jpy"),
            "aum_jpym": row.get("aum_jpym"),
            "month_ret": row.get("month_ret"),
            "benchmark": row.get("benchmark"),
            "perf_rate": row.get("perf_rate"),
            "high_water_mark_jpy": row.get("high_water_mark_jpy"),
            "source": row.get("source"),
            "source_url": row.get("source_url"),
            "tag": row.get("tag"),
        }]))

    for etf in catalog["perf_etfs"]:
        hist = etf_monthly_history(etf["ticker"])
        if hist.empty:
            continue
        hist["mandate_id"] = etf["mandate_id"]
        hist["benchmark"] = etf["benchmark"]
        hist["perf_rate"] = etf["perf_rate"]
        hist["fund_id"] = etf["id"]
        hist["aum_jpym"] = np.nan
        hist["high_water_mark_jpy"] = np.nan
        hist["source"] = "yfinance_etf"
        hist["source_url"] = f"https://finance.yahoo.com/quote/{etf['ticker']}"
        hist["tag"] = "[Market]"
        frames.append(hist)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["as_of"] = pd.to_datetime(out["as_of"])
    return out.sort_values(["fund_id", "as_of"]).drop_duplicates(["fund_id", "as_of"], keep="last")


def extend_sam_with_etf_proxy(monthly: pd.DataFrame, catalog: dict) -> pd.DataFrame:
    """Backfill value_up_fund history using 2080.T where SAM PDFs are sparse."""
    proxy = catalog["nonlisted_residual"]["proxy_etf"]
    etf_id = next((e["id"] for e in catalog["perf_etfs"] if e["ticker"] == proxy), None)
    if not etf_id or monthly.empty:
        return monthly

    etf = monthly[monthly["fund_id"] == etf_id].copy()
    vu = monthly[monthly["fund_id"] == "value_up_fund"].copy()
    if etf.empty:
        return monthly

    if len(vu) >= 3:
        return monthly

    # Scale ETF returns to approximate value fund; anchor on latest scraped NAV if present
    anchor_nav = float(vu["nav_jpy"].iloc[-1]) if len(vu) else np.nan
    anchor_date = vu["as_of"].iloc[-1] if len(vu) else etf["as_of"].iloc[-1]
    etf = etf.sort_values("as_of")
    etf["cum"] = (1 + etf["month_ret"].fillna(0)).cumprod()
    if pd.notna(anchor_nav) and len(vu):
        base_cum = float(etf.loc[etf["as_of"] == anchor_date, "cum"].iloc[-1]) if (etf["as_of"] == anchor_date).any() else float(etf["cum"].iloc[-1])
        etf["nav_jpy"] = anchor_nav * (etf["cum"] / base_cum)
    else:
        etf["nav_jpy"] = 50000 * etf["cum"]

    synth = etf[etf["as_of"] < anchor_date] if len(vu) else etf
    synth = synth.assign(
        fund_id="value_up_fund",
        mandate_id="mandate_value_pbr",
        benchmark="topix",
        perf_rate=0.20,
        aum_jpym=np.nan,
        high_water_mark_jpy=np.nan,
        source="etf_proxy_backfill",
        source_url=f"proxy:{proxy}",
        tag="[Derived]",
    )
    combined = pd.concat([monthly, synth], ignore_index=True)
    return combined.sort_values(["fund_id", "as_of"]).drop_duplicates(["fund_id", "as_of"], keep="first")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    sess = _session()

    sam_rows, pdf_manifest = scrape_sam_funds(sess, catalog)
    monthly = build_monthly_table(catalog, sam_rows)
    monthly = extend_sam_with_etf_proxy(monthly, catalog)

    monthly_out = monthly.copy()
    monthly_out["as_of"] = monthly_out["as_of"].dt.strftime("%Y-%m-%d")
    monthly_out.to_csv(DATA / "mandate_nav_monthly.csv", index=False)

    detail = monthly_out.copy()
    detail.to_csv(DATA / "mandate_nav_detail.csv", index=False)

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sam_pdf_downloads": pdf_manifest,
        "monthly_rows": len(monthly_out),
        "funds": sorted(monthly_out["fund_id"].unique().tolist()),
        "note": "Institutional non-listed pool aggregated in acquire_data.build_mandate_nav()",
    }
    (DATA / "mandate_scrape_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
