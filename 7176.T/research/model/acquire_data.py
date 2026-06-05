#!/usr/bin/env python3
"""P0-P6 data acquisition for 7176.T earnings model.

Outputs under research/model/data/:
  etf_nav_daily.csv, etf_aum_daily.csv, fund_return_halfyear.csv
  flows_monthly.csv, fee_history.csv, factor_returns_monthly.csv
  comp_bridge_halfyear.csv, aum_pools_halfyear.csv
  capiq_peers.csv (template or import), data_acquisition_manifest.json

Run: python3 acquire_data.py
Then: python3 build_panel.py && python3 model.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EVIDENCE = ROOT.parent / "evidence"
EVIDENCE_TEXT = EVIDENCE / "_text"
REGISTRY = ROOT / "fund_registry.json"


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# P0 — ETF NAV × units (daily)
# ---------------------------------------------------------------------------

def _etf_aum_from_anchor(registry: dict, nav_by_ticker: dict[str, pd.Series]) -> dict[str, float]:
    """Filing-anchored AUM (JPY m) per ticker when Yahoo shares are unavailable."""
    anchor = registry.get("etf_aum_anchor", {})
    total = anchor.get("total_jpym")
    if not total:
        return {}
    weights = {e["ticker"]: e["weight"] for e in registry["etfs"]}
    wsum = sum(weights.values()) or 1.0
    anchor_date = pd.Timestamp(anchor.get("as_of", "2025-03-31"))
    out = {}
    for tk, w in weights.items():
        nav_s = nav_by_ticker.get(tk)
        if nav_s is None or nav_s.empty:
            continue
        nav_s = nav_s.sort_index()
        prior = nav_s[nav_s.index <= anchor_date]
        nav_anchor = float(prior.iloc[-1]) if len(prior) else float(nav_s.iloc[0])
        if nav_anchor <= 0:
            continue
        out[tk] = float(total) * (w / wsum)
    return out


def fetch_etf_nav_daily(registry: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    import yfinance as yf

    tickers = [e["ticker"] for e in registry["etfs"]]
    nav_by_ticker: dict[str, pd.Series] = {}
    rows_nav = []
    rows_aum = []
    anchor_aum: dict[str, float] = {}

    for tk in tickers:
        try:
            t = yf.Ticker(tk)
            hist = t.history(start="2019-09-01", interval="1d", auto_adjust=True)
            info = t.info or {}
        except Exception as exc:
            print(f"[warn] {tk}: {exc}")
            continue
        if hist.empty:
            continue
        unit = hist["Close"].rename("nav_jpy")
        unit.index = pd.to_datetime(unit.index).tz_localize(None).normalize()
        nav_by_ticker[tk] = unit
        for dt_idx, nav in unit.items():
            rows_nav.append({"date": dt_idx, "ticker": tk, "nav_jpy": float(nav)})

    anchor_aum = _etf_aum_from_anchor(registry, nav_by_ticker)
    anchor_date = pd.Timestamp(registry.get("etf_aum_anchor", {}).get("as_of", "2025-03-31"))

    for tk in tickers:
        if tk not in nav_by_ticker:
            continue
        unit = nav_by_ticker[tk]
        try:
            info = yf.Ticker(tk).info or {}
        except Exception:
            info = {}
        shares = info.get("sharesOutstanding") or info.get("fundSharesOutstanding") or np.nan
        prior = unit[unit.index <= anchor_date]
        nav_anchor = float(prior.iloc[-1]) if len(prior) else float(unit.iloc[0])
        filing_aum_m = anchor_aum.get(tk)
        for dt_idx, nav in unit.items():
            if pd.notna(shares) and shares:
                aum_jpy = nav * shares
                method = "[Market]"
            elif filing_aum_m and nav_anchor:
                aum_jpy = filing_aum_m * 1e6 * (float(nav) / nav_anchor)
                method = "[Filing/Derived]"
            else:
                aum_jpy = np.nan
                method = "[Pending]"
            rows_aum.append({
                "date": dt_idx,
                "ticker": tk,
                "nav_jpy": float(nav),
                "shares": float(shares) if pd.notna(shares) else np.nan,
                "aum_jpy": float(aum_jpy) if pd.notna(aum_jpy) else np.nan,
                "aum_jpym": float(aum_jpy) / 1e6 if pd.notna(aum_jpy) else np.nan,
                "aum_method": method,
            })

    nav_df = pd.DataFrame(rows_nav).sort_values(["ticker", "date"])
    aum_df = pd.DataFrame(rows_aum).sort_values(["ticker", "date"])
    return nav_df, aum_df


def fund_return_halfyear(registry: dict, nav_df: pd.DataFrame) -> pd.DataFrame:
    """P0 — weighted ETF basket returns + perf-eligible sub-basket."""
    if nav_df.empty:
        return pd.DataFrame()
    weights = {e["ticker"]: e["weight"] for e in registry["etfs"]}
    perf_tickers = {e["ticker"] for e in registry["etfs"] if e.get("perf_eligible")}
    wsum = sum(weights.values())
    piv = nav_df.pivot(index="date", columns="ticker", values="nav_jpy").sort_index()
    rets = piv.pct_change()

    panel_path = ROOT / "panel_halfyear.csv"
    if not panel_path.exists():
        return pd.DataFrame()
    panel = pd.read_csv(panel_path, parse_dates=["period_end"])

    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"]
        if pe.month == 9:
            start = pd.Timestamp(pe.year, 4, 1)
        else:
            start = pd.Timestamp(pe.year - 1, 10, 1)
        win = rets[(rets.index >= start) & (rets.index <= pe)]
        if win.empty:
            continue
        def wret(cols, wmap):
            acc, wt = 0.0, 0.0
            for c in cols:
                if c not in wmap or c not in win.columns:
                    continue
                sub = (1 + win[c].fillna(0)).prod() - 1
                w = wmap[c] / wsum
                acc += w * sub
                wt += w
            return acc / wt if wt else np.nan

        all_cols = [c for c in weights if c in win.columns]
        perf_cols = [c for c in perf_tickers if c in win.columns]
        rows.append({
            "period_end": pe.strftime("%Y-%m-%d"),
            "fy": int(r["fy"]),
            "half": r["half"],
            "etf_basket_ret": wret(all_cols, weights),
            "etf_perf_basket_ret": wret(perf_cols, weights) if perf_cols else np.nan,
            "etf_basket_vol": win[all_cols].std().mean() * np.sqrt(252) if all_cols else np.nan,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P0 — Fund NAV proxy (non-listed + hurdle model inputs)
# ---------------------------------------------------------------------------

def build_fund_nav_proxy(registry: dict, fund_rets: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Synthetic perf-eligible return from registry benchmarks × factor returns."""
    if fund_rets.empty or panel.empty:
        return pd.DataFrame()
    fr = fund_rets.set_index("period_end")
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        if pe not in fr.index:
            continue
        nik = r.get("nikkei_ret", np.nan)
        val = r.get("value_factor_ret", np.nan)
        etf_perf = fr.loc[pe, "etf_perf_basket_ret"] if "etf_perf_basket_ret" in fr.columns else np.nan
        pool_nl = registry["aum_pools"][0]
        pool_etf = registry["aum_pools"][1]
        perf_drive = 0.0
        wt = 0.0
        for fund in registry.get("nonlisted_funds", []):
            bm = fund.get("benchmark", "nikkei")
            if bm in ("nikkei",):
                ret = nik
            elif bm in ("value_pbr", "value"):
                ret = val if pd.notna(val) else nik
            else:
                ret = nik
            excess = max(0.0, float(ret) - fund.get("hurdle", 0))
            w = fund["aum_share_of_nonlisted"] * pool_nl["aum_share_fy2025"]
            perf_drive += w * excess
            wt += w
        if pd.notna(etf_perf):
            perf_drive += pool_etf["aum_share_fy2025"] * max(0.0, float(etf_perf))
            wt += pool_etf["aum_share_fy2025"]
        rows.append({
            "period_end": pe,
            "perf_eligible_excess_ret": perf_drive / wt if wt else np.nan,
            "etf_perf_basket_ret": etf_perf,
            "nikkei_ret": nik,
            "value_factor_ret": val,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P1 — Flows (JITA proxy + ETF implied flows)
# ---------------------------------------------------------------------------

def fetch_jita_proxy(etf_flows: pd.DataFrame) -> pd.DataFrame:
    """Monthly flow panel: aggregate ETF implied flows; JITA columns pending scrape."""
    months = pd.date_range("2019-09-01", "2026-06-01", freq="MS")
    if etf_flows.empty:
        return pd.DataFrame({
            "month": [m.strftime("%Y-%m-%d") for m in months],
            "etf_implied_flow_jpym": np.nan,
            "jita_equity_net_flow_bn_jpy": np.nan,
            "jita_etf_net_flow_bn_jpy": np.nan,
            "tag": "[Pending]",
            "note": "JITA: export from https://www.toushin.or.jp/ or Vicki scrape",
        })
    ef = etf_flows.copy()
    ef["date"] = pd.to_datetime(ef["date"])
    ef["month"] = ef["date"].dt.to_period("M").dt.to_timestamp()
    agg = ef.groupby("month")["flow_jpym"].sum().reset_index()
    agg["month"] = agg["month"].dt.strftime("%Y-%m-%d")
    base = pd.DataFrame({"month": [m.strftime("%Y-%m-%d") for m in months]})
    out = base.merge(agg.rename(columns={"flow_jpym": "etf_implied_flow_jpym"}), on="month", how="left")
    out["jita_equity_net_flow_bn_jpy"] = np.nan
    out["jita_etf_net_flow_bn_jpy"] = np.nan
    out["tag"] = "[Derived]"
    out["note"] = "etf_implied_flow from NAV×shares roll-forward; JITA columns pending"
    return out


def implied_etf_flows(aum_df: pd.DataFrame, nav_df: pd.DataFrame) -> pd.DataFrame:
    """ΔAUM - market return × prior AUM = net flow proxy per ETF."""
    if aum_df.empty:
        return pd.DataFrame()
    out = []
    for tk, g in aum_df.groupby("ticker"):
        g = g.sort_values("date").dropna(subset=["aum_jpym"])
        if len(g) < 2:
            continue
        g = g.set_index("date")
        aum = g["aum_jpym"]
        nav = nav_df[nav_df["ticker"] == tk].set_index("date")["nav_jpy"]
        aligned = pd.concat([aum, nav], axis=1, join="inner").dropna()
        if len(aligned) < 2:
            continue
        aligned["ret"] = aligned["nav_jpy"].pct_change()
        aligned["flow_jpym"] = aligned["aum_jpym"].diff() - aligned["aum_jpym"].shift(1) * aligned["ret"]
        for dt, row in aligned.iterrows():
            if pd.notna(row.get("flow_jpym")):
                out.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "ticker": tk,
                    "flow_jpym": round(float(row["flow_jpym"]), 3),
                    "tag": "[Derived]",
                })
    return pd.DataFrame(out)


def aggregate_flows_halfyear(flows_monthly: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    if flows_monthly.empty or panel.empty:
        return pd.DataFrame()
    fm = flows_monthly.copy()
    fm["month"] = pd.to_datetime(fm["month"])
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"]
        if pe.month == 9:
            start = pd.Timestamp(pe.year, 4, 1)
        else:
            start = pd.Timestamp(pe.year - 1, 10, 1)
        win = fm[(fm["month"] >= start) & (fm["month"] <= pe)]
        etf_flow = float(win["etf_implied_flow_jpym"].sum()) if "etf_implied_flow_jpym" in win.columns and len(win) else np.nan
        jita_eq = float(win["jita_equity_net_flow_bn_jpy"].sum()) if "jita_equity_net_flow_bn_jpy" in win.columns and len(win) else np.nan
        jita_etf = float(win["jita_etf_net_flow_bn_jpy"].sum()) if "jita_etf_net_flow_bn_jpy" in win.columns and len(win) else np.nan
        rows.append({
            "period_end": pe.strftime("%Y-%m-%d"),
            "etf_implied_flow_jpym": etf_flow,
            "jita_equity_flow_bn": jita_eq if pd.notna(jita_eq) and jita_eq != 0 else np.nan,
            "jita_etf_flow_bn": jita_etf if pd.notna(jita_etf) and jita_etf != 0 else np.nan,
            "tag": "[Derived]",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P1 — AUM pools (perf-eligible split)
# ---------------------------------------------------------------------------

def build_aum_pools_halfyear(registry: dict, panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in panel.iterrows():
        aum = r.get("aum_end_jpym", np.nan)
        aum_nl = r.get("aum_nonlisted_jpym", np.nan)
        aum_etf = r.get("aum_etf_jpym", np.nan)
        if pd.isna(aum_nl) and pd.notna(aum) and pd.notna(aum_etf):
            aum_nl = aum - aum_etf
        pool_nl = registry["aum_pools"][0]
        pool_etf = registry["aum_pools"][1]
        rows.append({
            "period_end": r["period_end"].strftime("%Y-%m-%d"),
            "aum_total_jpym": aum,
            "aum_nonlisted_jpym": aum_nl,
            "aum_etf_jpym": aum_etf,
            "perf_eligible_aum_jpym": (
                (aum_nl if pd.notna(aum_nl) else 0)
                + (aum_etf if pd.notna(aum_etf) else 0)
            ),
            "base_fee_aum_jpym": aum,
            "nonlisted_share": aum_nl / aum if pd.notna(aum) and aum else np.nan,
            "etf_share": aum_etf / aum if pd.notna(aum) and aum else np.nan,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P2 — Fee history backfill from filings
# ---------------------------------------------------------------------------

FEE_PATTERNS = [
    (r"基本報酬は[^0-9]*?(\d+)億(\d+)百万円", "base_fee_h1", 1e3),
    (r"基本報酬は前期比[^。]*?(\d+)億(\d+)百万円", "base_fee_annual", 1e3),
    (r"基本報酬は前年比[^。]*?(\d+)億(\d+)百万円", "base_fee_annual", 1e3),
    (r"基本報酬が前期比[^。]*?(\d+)億(\d+)百万円", "base_fee_annual", 1e3),
    (r"成功報酬[^。]*?(\d+)億(\d+)百万円", "perf_fee", 1e3),
    (r"成功報酬も、[^。]*?(\d+)億(\d+)百万円", "perf_fee_annual", 1e3),
    (r"成功報酬（ファンド[^）]*）は同[^。]*?(\d+)億(\d+)百万円", "perf_fee_h1", 1e3),
]


def _oku_man_to_thousand(boku: str, man: str, scale: float) -> float:
    return (int(boku) * 1e8 + int(man) * 1e6) / 1000.0 * scale / 1e3 * 1e3


def extract_fee_history() -> pd.DataFrame:
    rows = []
    for path in sorted(EVIDENCE_TEXT.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        date_m = re.search(r"(20\d{6})", path.name)
        doc_date = date_m.group(1) if date_m else None
        is_interim = "中間" in path.name
        is_variance = "Pnotice" in path.name or "差異" in path.name
        for pat, field, _ in FEE_PATTERNS:
            for m in re.finditer(pat, text):
                val_thousand = int(m.group(1)) * 1e8 / 1e3 + int(m.group(2)) * 1e6 / 1e3
                rows.append({
                    "source_file": path.name,
                    "doc_date": doc_date,
                    "field": field,
                    "value_jpy_thousand": val_thousand,
                    "is_interim": is_interim,
                    "is_variance": is_variance,
                    "tag": "[Filing]",
                })
    df = pd.DataFrame(rows).drop_duplicates()
    return df


def fee_history_halfyear(fee_raw: pd.DataFrame) -> pd.DataFrame:
    """Map extracted fees to fiscal halves where possible."""
    # Hand-curated from filing extract + build_panel ANNUAL/H1
    curated = [
        ("2020-09-30", "H1", None, None),
        ("2021-03-31", "H2", None, None),
        ("2021-09-30", "H1", None, None),
        ("2022-03-31", "H2", 5133, None),
        ("2022-09-30", "H1", 2851, None),
        ("2023-03-31", "H2", 5820, None),
        ("2023-09-30", "H1", 2872, 932),
        ("2024-03-31", "H2", 5942, 8907),
        ("2024-09-30", "H1", 3266, 1996),
        ("2025-03-31", "H2", 6721, 9320),
        ("2025-09-30", "H1", 3711, 1713),
        ("2026-03-31", "H2", 7869, 14316),
    ]
    return pd.DataFrame([
        {"period_end": pe, "half": h, "base_fee_jpy_thousand": b, "perf_fee_jpy_thousand": p, "tag": "[Filing/Derived]"}
        for pe, h, b, p in curated
    ])


# ---------------------------------------------------------------------------
# P2 — Factor returns
# ---------------------------------------------------------------------------

def _repair_price_splits(series: pd.Series, jump: float = 0.35) -> pd.Series:
    """Scale yfinance series after one-day jumps (ETF unit splits / bad ticks)."""
    s = series.dropna().astype(float).copy()
    if len(s) < 2:
        return s
    ratio = s.pct_change()
    for i in range(1, len(s)):
        r = ratio.iloc[i]
        if pd.isna(r) or abs(r) <= jump:
            continue
        scale = s.iloc[i - 1] / s.iloc[i]
        s.iloc[i:] *= scale
        ratio = s.pct_change()
    return s


def fetch_factor_returns(registry: dict) -> pd.DataFrame:
    import yfinance as yf

    proxies = registry["factor_proxies"]
    frames = {}
    for name, tk in proxies.items():
        try:
            h = yf.Ticker(tk).history(start="2019-09-01", interval="1d", auto_adjust=True)
            if len(h):
                px = _repair_price_splits(h["Close"])
                frames[name] = px.rename(name)
        except Exception as exc:
            print(f"[warn] factor {name} ({tk}): {exc}")
    if not frames:
        return pd.DataFrame()
    m = pd.concat(frames.values(), axis=1)
    m.index = pd.to_datetime(m.index).tz_localize(None)
    m["value_spread"] = m["value_pbr"].pct_change() - m["nikkei"].pct_change()
    m.to_csv(DATA / "factor_returns_daily.csv")
    monthly = m.resample("ME").last().pct_change()
    monthly.index.name = "month"
    out = monthly.reset_index()
    out["month"] = pd.to_datetime(out["month"]).dt.strftime("%Y-%m-%d")
    return out


def factor_halfyear(panel: pd.DataFrame, factor_monthly: pd.DataFrame) -> pd.DataFrame:
    if factor_monthly.empty or panel.empty:
        return pd.DataFrame()
    fd = factor_monthly.copy()
    date_col = "month" if "month" in fd.columns else fd.columns[0]
    fd[date_col] = pd.to_datetime(fd[date_col])
    fd = fd.set_index(date_col).sort_index()
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"]
        if pe.month == 9:
            start = pd.Timestamp(pe.year, 4, 1)
        else:
            start = pd.Timestamp(pe.year - 1, 10, 1)
        win = fd[(fd.index >= start) & (fd.index <= pe)]
        row = {"period_end": pe.strftime("%Y-%m-%d")}
        for col in ["nikkei", "value_pbr", "growth", "reit", "leveraged", "topix"]:
            if col in win.columns:
                rets = win[col].dropna()
                if len(rets) >= 1:
                    row[f"{col}_ret"] = float((1 + rets).prod() - 1)
        if "value_spread" in win.columns:
            row["value_factor_ret"] = float(win["value_spread"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P6 — March crystallization window (Jan–Mar into FY-end)
# ---------------------------------------------------------------------------

def march_window_halfyear(panel: pd.DataFrame) -> pd.DataFrame:
    """P6 — Last 3 months return into March year-end (H2 crystallization path)."""
    daily_path = DATA / "factor_returns_daily.csv"
    if not daily_path.exists() or panel.empty:
        return pd.DataFrame()
    fd = pd.read_csv(daily_path, index_col=0, parse_dates=True)
    if "nikkei" not in fd.columns:
        return pd.DataFrame()
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"]
        row = {"period_end": pe.strftime("%Y-%m-%d"), "half": r["half"]}
        if r["half"] == "H2" and pe.month == 3:
            jan1 = pd.Timestamp(pe.year, 1, 1)
            win = fd[(fd.index >= jan1) & (fd.index <= pe)]
            for col, out in [("nikkei", "march_nikkei_ret"), ("value_pbr", "march_value_ret")]:
                if col in win.columns:
                    s = win[col].dropna()
                    if len(s) >= 2:
                        row[out] = float(s.iloc[-1] / s.iloc[0] - 1)
            if "march_nikkei_ret" in row:
                nik = max(0.0, row.get("march_nikkei_ret", 0))
                val = row.get("march_value_ret", np.nan)
                row["march_blended_ret"] = (
                    0.65 * nik + 0.35 * max(0.0, float(val)) if pd.notna(val) else nik
                )
        else:
            row["march_nikkei_ret"] = r.get("nikkei_ret", np.nan)
            row["march_blended_ret"] = r.get("nikkei_ret", np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P4 — Mandate NAV from scraped monthly reports + ETF history
# ---------------------------------------------------------------------------

MANDATE_CATALOG = ROOT / "mandate_funds.json"
MANDATE_SCRIPT = ROOT.parents[1] / "_scripts" / "download_mandate_nav.py"


def _run_mandate_scrape() -> None:
    """Invoke download_mandate_nav.py (Vicki/Marvin HTTP scrape)."""
    import subprocess
    import sys

    if not MANDATE_SCRIPT.exists():
        return
    subprocess.run([sys.executable, str(MANDATE_SCRIPT)], check=False, cwd=str(ROOT.parents[1]))


def _benchmark_ret(row: pd.Series, bm: str) -> float:
    """Half-year benchmark return (decimal); drop corrupt |r|>50% half-year moves."""
    nik = float(row.get("nikkei_ret") or 0)

    def _sanitized(val) -> float | None:
        if pd.isna(val):
            return None
        v = float(val)
        return v if abs(v) <= 0.5 else None

    if bm in ("value_pbr", "value"):
        vf = _sanitized(row.get("value_factor_ret"))
        vp = _sanitized(row.get("value_pbr_ret"))
        val = vf if vf is not None and abs(vf) > 1e-9 else vp
        return val if val is not None else nik
    if bm == "topix":
        t = _sanitized(row.get("topix_etf_ret")) or _sanitized(row.get("topix_ret"))
        return t if t is not None else nik
    return nik


def _halfyear_fund_return(monthly: pd.DataFrame, fund_id: str, period_end: pd.Timestamp, half: str) -> float:
    """Compound monthly returns for fiscal half ending period_end."""
    sub = monthly[monthly["fund_id"] == fund_id].copy()
    if sub.empty:
        return np.nan
    sub["as_of"] = pd.to_datetime(sub["as_of"])
    sub = sub.sort_values("as_of")
    fy = period_end.year if period_end.month == 3 else period_end.year + 1
    if half == "H1":
        start, end = pd.Timestamp(fy - 1, 4, 1), pd.Timestamp(fy - 1, 9, 30)
    else:
        start, end = pd.Timestamp(fy - 1, 10, 1), pd.Timestamp(fy, 3, 31)
    win = sub[(sub["as_of"] >= start) & (sub["as_of"] <= end)]
    if len(win) >= 2 and win["nav_jpy"].notna().sum() >= 2:
        nav = win["nav_jpy"].dropna()
        return float(nav.iloc[-1] / nav.iloc[0] - 1.0)
    if win["month_ret"].notna().any():
        return float((1 + win["month_ret"].fillna(0)).prod() - 1.0)
    return np.nan


def build_mandate_nav(registry: dict, panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """P4 — Pool scraped mandate returns; impute institutional residual from value proxy."""
    monthly_path = DATA / "mandate_nav_monthly.csv"
    if not monthly_path.exists():
        _run_mandate_scrape()
    if not monthly_path.exists():
        return pd.DataFrame(), pd.DataFrame()

    catalog = json.loads(MANDATE_CATALOG.read_text(encoding="utf-8")) if MANDATE_CATALOG.exists() else {}
    monthly = pd.read_csv(monthly_path, parse_dates=["as_of"])
    detail_rows: list[dict] = []
    agg_rows: list[dict] = []

    etf_weights = {e["id"]: e["weight"] for e in catalog.get("perf_etfs", [])}
    latest_public_aum = (
        monthly.dropna(subset=["aum_jpym"]).groupby("fund_id")["aum_jpym"].last().sum()
        if "aum_jpym" in monthly.columns else 0.0
    )

    for _, r in panel.iterrows():
        pe = pd.Timestamp(r["period_end"])
        pe_str = pe.strftime("%Y-%m-%d")
        half = r["half"]
        mandate_slices: list[dict] = []

        for fund in catalog.get("sam_funds", []):
            ret = _halfyear_fund_return(monthly, fund["id"], pe, half)
            if np.isnan(ret):
                continue
            bm_ret = _benchmark_ret(r, fund.get("benchmark", "nikkei"))
            hurdle = fund.get("hurdle", 0.0)
            excess = max(0.0, ret - bm_ret - hurdle)
            aum = monthly.loc[monthly["fund_id"] == fund["id"], "aum_jpym"].dropna()
            aum_jpym = float(aum.iloc[-1]) if len(aum) else np.nan
            mandate_slices.append({
                "period_end": pe_str, "half": half, "mandate_id": fund["mandate_id"],
                "fund_id": fund["id"], "period_return": ret, "benchmark_return": bm_ret,
                "excess_vs_hurdle": excess, "aum_jpym": aum_jpym,
                "perf_rate": fund.get("perf_rate"), "tag": fund.get("tag", "[Filing/Market]"),
                "source": "simplex_monthly_pdf",
            })

        for etf in catalog.get("perf_etfs", []):
            ret = _halfyear_fund_return(monthly, etf["id"], pe, half)
            if np.isnan(ret):
                continue
            bm_ret = _benchmark_ret(r, etf.get("benchmark", "value_pbr"))
            excess = max(0.0, ret - bm_ret)
            etf_aum = r.get("aum_etf_jpym", np.nan)
            w = etf_weights.get(etf["id"], 1.0 / max(len(catalog.get("perf_etfs", [])), 1))
            aum_jpym = float(etf_aum) * w if pd.notna(etf_aum) else np.nan
            mandate_slices.append({
                "period_end": pe_str, "half": half, "mandate_id": etf["mandate_id"],
                "fund_id": etf["id"], "period_return": ret, "benchmark_return": bm_ret,
                "excess_vs_hurdle": excess, "aum_jpym": aum_jpym,
                "perf_rate": etf.get("perf_rate"), "tag": "[Market]",
                "source": "yfinance_etf",
            })

        # Institutional residual (non-listed minus disclosed public SAM AUM)
        resid = catalog.get("nonlisted_residual", {})
        proxy_id = resid.get("proxy_fund_id", "value_up_fund")
        proxy_ret = _halfyear_fund_return(monthly, proxy_id, pe, half)
        nonlisted = r.get("aum_nonlisted_jpym", np.nan)
        if pd.notna(nonlisted) and pd.notna(proxy_ret):
            residual_aum = max(0.0, float(nonlisted) - float(latest_public_aum or 0))
            if residual_aum > 0:
                bm_ret = _benchmark_ret(r, "nikkei")
                mandate_slices.append({
                    "period_end": pe_str, "half": half,
                    "mandate_id": resid.get("mandate_id", "mandate_japan_equity"),
                    "fund_id": "nonlisted_residual",
                    "period_return": float(proxy_ret),
                    "benchmark_return": bm_ret,
                    "excess_vs_hurdle": max(0.0, float(proxy_ret) - bm_ret),
                    "aum_jpym": residual_aum,
                    "perf_rate": 0.15,
                    "tag": resid.get("tag", "[Derived]"),
                    "source": f"proxy:{proxy_id}",
                })

        detail_rows.extend(mandate_slices)
        if not mandate_slices:
            continue
        ddf = pd.DataFrame(mandate_slices)
        w = ddf["aum_jpym"].fillna(0)
        wsum = w.sum()
        if wsum <= 0:
            w = pd.Series(1.0, index=ddf.index)
            wsum = len(ddf)
        agg_rows.append({
            "period_end": pe_str,
            "mandate_weighted_excess": float((ddf["excess_vs_hurdle"] * w).sum() / wsum),
            "mandate_weighted_return": float((ddf["period_return"] * w).sum() / wsum),
            "mandate_count": len(ddf),
            "tag": "[Filing/Market/Derived]",
            "note": "Scraped SAM PDFs + ETF yfinance + nonlisted residual proxy",
        })

    detail = pd.DataFrame(detail_rows)
    agg = pd.DataFrame(agg_rows)
    if not detail.empty:
        detail.to_csv(DATA / "mandate_nav_detail.csv", index=False)
    return agg, detail


# ---------------------------------------------------------------------------
# P3 — Comp bridge + CapIQ
# ---------------------------------------------------------------------------

OPEX_ANNUAL = [
    ("2023-03-31", 4811, 49),
    ("2024-03-31", 6293, 51),
    ("2025-03-31", 6916, 55),
    ("2026-03-31", 8542, 55),
]


def build_comp_bridge(panel: pd.DataFrame) -> pd.DataFrame:
    opex = {pe: (v, hc) for pe, v, hc in OPEX_ANNUAL}
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        opex_val, hc = opex.get(pe, (np.nan, r.get("headcount")))
        rev = r.get("revenue", np.nan)
        perf = r.get("perf_fee", np.nan)
        ordinary = r.get("ordinary", np.nan)
        rows.append({
            "period_end": pe,
            "revenue_jpy_thousand": rev,
            "perf_fee_jpy_thousand": perf,
            "ordinary_jpy_thousand": ordinary,
            "opex_sga_jpy_million": opex_val,
            "headcount": hc,
            "incremental_margin": ordinary / rev if pd.notna(ordinary) and rev else np.nan,
            "comp_ratio_proxy": None,
            "tag": "[Filing]",
        })
    return pd.DataFrame(rows)


def capiq_template() -> pd.DataFrame:
    template = DATA / "capiq_export.csv"
    if template.exists():
        return pd.read_csv(template)
    rows = [
        {"ticker": "7176.T", "field": "ownership_institutional_pct", "value": None, "as_of": None, "note": "Paste CapIQ export"},
        {"ticker": "7176.T", "field": "tpm_volume_days_12m", "value": None, "as_of": None, "note": "Paste CapIQ or Yahoo"},
        {"ticker": "8697.T", "field": "peer_base_fee_rate_ann_pct", "value": 0.35, "as_of": "2025", "note": "[Assumption] JPX peer prior"},
        {"ticker": "8306.T", "field": "peer_base_fee_rate_ann_pct", "value": 0.4, "as_of": "2025", "note": "[Assumption] AM arm prior"},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(template, index=False)
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    registry = load_registry()
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "steps": {}}

    # P0
    nav_df, aum_df = fetch_etf_nav_daily(registry)
    nav_df.to_csv(DATA / "etf_nav_daily.csv", index=False)
    aum_df.to_csv(DATA / "etf_aum_daily.csv", index=False)
    manifest["steps"]["p0_etf_nav"] = {"rows": len(nav_df), "tickers": nav_df["ticker"].nunique() if len(nav_df) else 0}

    panel = pd.read_csv(ROOT / "panel_halfyear.csv", parse_dates=["period_end"]) if (ROOT / "panel_halfyear.csv").exists() else pd.DataFrame()

    # P2 factors first (fund proxy needs value_factor_ret on panel)
    factor_m = fetch_factor_returns(registry)
    factor_m.to_csv(DATA / "factor_returns_monthly.csv", index=False)
    factor_h = factor_halfyear(panel, factor_m) if not panel.empty else pd.DataFrame()
    if not factor_h.empty:
        factor_h.to_csv(DATA / "factor_returns_halfyear.csv", index=False)
        fh = factor_h.copy()
        fh["period_end"] = pd.to_datetime(fh["period_end"])
        panel = panel.merge(fh, on="period_end", how="left", suffixes=("", "_fac"))

    fund_rets = fund_return_halfyear(registry, nav_df)
    fund_rets.to_csv(DATA / "fund_return_halfyear.csv", index=False)
    fund_proxy = build_fund_nav_proxy(registry, fund_rets, panel)
    fund_proxy.to_csv(DATA / "fund_nav_proxy_halfyear.csv", index=False)
    manifest["steps"]["p0_fund_proxy"] = {"rows": len(fund_proxy)}

    # P1
    etf_flows = implied_etf_flows(aum_df, nav_df)
    etf_flows.to_csv(DATA / "etf_flows_daily.csv", index=False)
    flows_m = fetch_jita_proxy(etf_flows)
    flows_m.to_csv(DATA / "flows_monthly.csv", index=False)
    if not panel.empty:
        flows_h = aggregate_flows_halfyear(flows_m, panel)
        flows_h.to_csv(DATA / "flows_halfyear.csv", index=False)
        pools = build_aum_pools_halfyear(registry, panel)
        pools.to_csv(DATA / "aum_pools_halfyear.csv", index=False)
    manifest["steps"]["p1_flows"] = {"monthly": len(flows_m), "etf_flow_rows": len(etf_flows)}

    # P2 fees (factors already written above)
    fee_raw = extract_fee_history()
    fee_raw.to_csv(DATA / "fee_history_raw.csv", index=False)
    fee_h = fee_history_halfyear(fee_raw)
    fee_h.to_csv(DATA / "fee_history_halfyear.csv", index=False)
    manifest["steps"]["p2_factors"] = {
        "fee_raw": len(fee_raw),
        "fee_halfyear": len(fee_h),
        "factor_halfyear": len(factor_h) if not factor_h.empty else 0,
    }

    # P3
    comp_rows = 0
    if not panel.empty:
        comp = build_comp_bridge(panel)
        comp.to_csv(DATA / "comp_bridge_halfyear.csv", index=False)
        comp_rows = len(comp)
    capiq = capiq_template()
    capiq.to_csv(DATA / "capiq_peers.csv", index=False)
    manifest["steps"]["p3_comp_capiq"] = {"comp_rows": comp_rows}

    # P4 / P6
    p4_rows = p4_detail = p6_rows = 0
    p4_tag = "[Filing/Market/Derived]"
    if not panel.empty:
        mandate, mandate_detail = build_mandate_nav(registry, panel)
        mandate.to_csv(DATA / "mandate_nav_halfyear.csv", index=False)
        p4_rows = len(mandate)
        p4_detail = len(mandate_detail)
        march = march_window_halfyear(panel)
        march.to_csv(DATA / "march_window_halfyear.csv", index=False)
        p6_rows = len(march)
    manifest["steps"]["p4_mandate_nav"] = {
        "rows": p4_rows, "detail_rows": p4_detail, "tag": p4_tag,
        "scrape_script": str(MANDATE_SCRIPT.relative_to(ROOT.parents[1])),
    }
    manifest["steps"]["p6_march_window"] = {"rows": p6_rows}

    (DATA / "data_acquisition_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
