#!/usr/bin/env python3
"""P0-P7 data acquisition for 7176.T earnings model.

Outputs under research/model/data/:
  etf_nav_daily.csv, etf_aum_daily.csv, fund_return_halfyear.csv
  flows_monthly.csv, fee_history.csv, factor_returns_monthly.csv
  comp_bridge_halfyear.csv, aum_pools_halfyear.csv
  mandate_nav_*.csv, perf_fee_by_bucket_halfyear.csv, aum_rollforward_halfyear.csv
  etf_units_daily.csv, perf_eligible_aum_halfyear.csv, other_revenue_halfyear.csv
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
JPX_SCRIPT = ROOT.parents[1] / "_scripts" / "download_jpx_etf_units.py"


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


def _run_jpx_units_scrape() -> None:
    import subprocess
    import sys

    if not JPX_SCRIPT.exists():
        return
    subprocess.run([sys.executable, str(JPX_SCRIPT)], check=False, cwd=str(ROOT.parents[1]))


def _load_jpx_units_daily() -> pd.DataFrame:
    path = DATA / "jpx_etf_units_daily.csv"
    if not path.exists():
        _run_jpx_units_scrape()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


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
    jpx_units = _load_jpx_units_daily()
    jpx_by_ticker: dict[str, pd.Series] = {}
    if not jpx_units.empty:
        for tk, g in jpx_units.groupby("ticker"):
            s = g.set_index("date")["listed_shares"].sort_index()
            jpx_by_ticker[tk] = s

    for tk in tickers:
        if tk not in nav_by_ticker:
            continue
        unit = nav_by_ticker[tk]
        jpx_shares = jpx_by_ticker.get(tk)
        try:
            info = yf.Ticker(tk).info or {}
        except Exception:
            info = {}
        yahoo_shares = info.get("sharesOutstanding") or info.get("fundSharesOutstanding") or np.nan
        prior = unit[unit.index <= anchor_date]
        nav_anchor = float(prior.iloc[-1]) if len(prior) else float(unit.iloc[0])
        filing_aum_m = anchor_aum.get(tk)
        for dt_idx, nav in unit.items():
            shares = np.nan
            method = "[Pending]"
            if jpx_shares is not None:
                prior_jpx = jpx_shares[jpx_shares.index <= dt_idx]
                if len(prior_jpx) and pd.notna(prior_jpx.iloc[-1]):
                    shares = float(prior_jpx.iloc[-1])
                    method = "[Market/JPX]"
            elif pd.notna(yahoo_shares) and yahoo_shares:
                shares = float(yahoo_shares)
                method = "[Market/Yahoo]"
            if pd.notna(shares) and shares:
                aum_jpy = nav * shares
            elif filing_aum_m and nav_anchor:
                aum_jpy = filing_aum_m * 1e6 * (float(nav) / nav_anchor)
                method = "[Filing/Derived]"
                shares = np.nan
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

    if not rows_nav:
        nav_path = DATA / "etf_nav_daily.csv"
        aum_path = DATA / "etf_aum_daily.csv"
        if nav_path.exists():
            print("[warn] yfinance empty; reusing cached etf_nav_daily.csv")
            nav_df = pd.read_csv(nav_path, parse_dates=["date"])
            aum_df = pd.read_csv(aum_path, parse_dates=["date"]) if aum_path.exists() else pd.DataFrame()
            return nav_df, aum_df
    nav_df = pd.DataFrame(rows_nav).sort_values(["ticker", "date"])
    aum_df = pd.DataFrame(rows_aum).sort_values(["ticker", "date"])
    return nav_df, aum_df


def refresh_aum_with_jpx(nav_df: pd.DataFrame, registry: dict) -> pd.DataFrame:
    """Recompute AUM rows after jpx_etf_units_daily.csv is built."""
    if nav_df.empty:
        return pd.DataFrame()
    jpx_units = _load_jpx_units_daily()
    if jpx_units.empty:
        return pd.DataFrame()
    anchor_aum = _etf_aum_from_anchor(registry, {
        tk: nav_df[nav_df["ticker"] == tk].set_index("date")["nav_jpy"].sort_index()
        for tk in nav_df["ticker"].unique()
    })
    anchor_date = pd.Timestamp(registry.get("etf_aum_anchor", {}).get("as_of", "2025-03-31"))
    jpx_by_ticker: dict[str, pd.Series] = {}
    for tk, g in jpx_units.groupby("ticker"):
        jpx_by_ticker[tk] = g.set_index("date")["listed_shares"].sort_index()

    rows_aum = []
    for tk in nav_df["ticker"].unique():
        unit = nav_df[nav_df["ticker"] == tk].set_index("date")["nav_jpy"].sort_index()
        jpx_shares = jpx_by_ticker.get(tk)
        prior = unit[unit.index <= anchor_date]
        nav_anchor = float(prior.iloc[-1]) if len(prior) else float(unit.iloc[0])
        filing_aum_m = anchor_aum.get(tk)
        for dt_idx, nav in unit.items():
            shares = np.nan
            method = "[Pending]"
            if jpx_shares is not None:
                prior_jpx = jpx_shares[jpx_shares.index <= dt_idx]
                if len(prior_jpx) and pd.notna(prior_jpx.iloc[-1]):
                    shares = float(prior_jpx.iloc[-1])
                    method = "[Market/JPX]"
            if pd.notna(shares) and shares:
                aum_jpy = nav * shares
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
    return pd.DataFrame(rows_aum).sort_values(["ticker", "date"])


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
    """Business-line weighted perf-eligible excess (bucket proxy layer)."""
    from bucket_proxy import build_bucket_weighted_proxy

    bw = build_bucket_weighted_proxy(panel, registry)
    if bw.empty:
        return pd.DataFrame()
    fr = fund_rets.set_index("period_end") if not fund_rets.empty else pd.DataFrame()
    rows = []
    for _, r in bw.iterrows():
        pe = r["period_end"]
        row = {
            "period_end": pe,
            "perf_eligible_excess_ret": r.get("bucket_weighted_excess"),
            "bucket_weighted_ret": r.get("bucket_weighted_ret"),
            "bucket_weighted_march_ret": r.get("bucket_weighted_march_ret"),
            "tag": r.get("tag", "[Proxy/Derived]"),
        }
        if not fr.empty and pe in fr.index:
            row["etf_perf_basket_ret"] = fr.loc[pe, "etf_perf_basket_ret"] if "etf_perf_basket_ret" in fr.columns else np.nan
        p = panel[panel["period_end"].dt.strftime("%Y-%m-%d") == pe]
        if not p.empty:
            pr = p.iloc[0]
            row["nikkei_ret"] = pr.get("nikkei_ret")
            row["value_factor_ret"] = pr.get("value_factor_ret")
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P1 / P5 — Flows (JITA scrape + ETF implied flows)
# ---------------------------------------------------------------------------

JITA_SCRIPT = ROOT.parents[1] / "_scripts" / "download_jita_flows.py"


def _run_jita_scrape() -> None:
    import subprocess
    import sys

    if not JITA_SCRIPT.exists():
        return
    subprocess.run([sys.executable, str(JITA_SCRIPT)], check=False, cwd=str(ROOT.parents[1]))


def _load_jita_monthly() -> pd.DataFrame:
    path = DATA / "jita_flows_monthly.csv"
    if not path.exists():
        _run_jita_scrape()
    if not path.exists():
        return pd.DataFrame()
    j = pd.read_csv(path, parse_dates=["month"])
    j["month"] = j["month"].dt.strftime("%Y-%m-%d")
    return j


def fetch_jita_proxy(etf_flows: pd.DataFrame) -> pd.DataFrame:
    """Monthly flow panel: Simplex ETF implied flows + JITA industry flows (P5)."""
    months = pd.date_range("2019-09-01", "2026-06-01", freq="MS")
    base = pd.DataFrame({"month": [m.strftime("%Y-%m-%d") for m in months]})
    base["period"] = pd.to_datetime(base["month"]).dt.to_period("M")

    if etf_flows.empty:
        out = base.copy()
        out["etf_implied_flow_jpym"] = np.nan
    else:
        ef = etf_flows.copy()
        ef["date"] = pd.to_datetime(ef["date"])
        ef["period"] = ef["date"].dt.to_period("M")
        agg = ef.groupby("period")["flow_jpym"].sum().reset_index()
        out = base.merge(agg.rename(columns={"flow_jpym": "etf_implied_flow_jpym"}), on="period", how="left")

    jita = _load_jita_monthly()
    if not jita.empty:
        jita = jita.copy()
        jita["period"] = pd.to_datetime(jita["month"]).dt.to_period("M")
        use = [c for c in ["period", "jita_equity_net_flow_bn_jpy", "jita_etf_net_flow_bn_jpy"] if c in jita.columns]
        out = out.merge(jita[use], on="period", how="left")
    else:
        out["jita_equity_net_flow_bn_jpy"] = np.nan
        out["jita_etf_net_flow_bn_jpy"] = np.nan

    has_jita = out["jita_equity_net_flow_bn_jpy"].notna().any() if "jita_equity_net_flow_bn_jpy" in out.columns else False
    out["tag"] = "[Filing/Market]" if has_jita else "[Derived]"
    out["note"] = (
        "JITA B-1 株式 + ETF flows (億円); etf_implied_flow from Simplex ETF NAV roll-forward"
        if has_jita else "etf_implied_flow only; JITA scrape failed"
    )
    out.drop(columns=["period"], inplace=True)
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
        cap = aligned["aum_jpym"].shift(1).abs() * 0.05
        aligned["flow_jpym"] = aligned["flow_jpym"].clip(lower=-cap, upper=cap)
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
    fm["period"] = fm["month"].dt.to_period("M")
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"]
        if pe.month == 9:
            start_p = pd.Period(f"{pe.year}-04", freq="M")
        else:
            start_p = pd.Period(f"{pe.year - 1}-10", freq="M")
        end_p = pd.Period(f"{pe.year}-{pe.month:02d}", freq="M")
        win = fm[(fm["period"] >= start_p) & (fm["period"] <= end_p)]
        etf_flow = float(win["etf_implied_flow_jpym"].sum()) if "etf_implied_flow_jpym" in win.columns and len(win) else np.nan
        jita_eq = float(win["jita_equity_net_flow_bn_jpy"].sum()) if "jita_equity_net_flow_bn_jpy" in win.columns and len(win) else np.nan
        jita_etf = float(win["jita_etf_net_flow_bn_jpy"].sum()) if "jita_etf_net_flow_bn_jpy" in win.columns and len(win) else np.nan
        rows.append({
            "period_end": pe.strftime("%Y-%m-%d"),
            "etf_implied_flow_jpym": etf_flow,
            "jita_equity_flow_bn": jita_eq if pd.notna(jita_eq) else np.nan,
            "jita_etf_flow_bn": jita_etf if pd.notna(jita_etf) else np.nan,
            "tag": "[Filing/Market]" if pd.notna(jita_eq) or pd.notna(jita_etf) else "[Derived]",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P1 — AUM pools (perf-eligible split)
# ---------------------------------------------------------------------------

def build_aum_pools_halfyear(registry: dict, panel: pd.DataFrame) -> pd.DataFrame:
    from aum_sleeves import fill_panel_aum_row

    rows = []
    for _, r in panel.iterrows():
        r = fill_panel_aum_row(r)
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
        monthly_path = DATA / "factor_returns_monthly.csv"
        daily_path = DATA / "factor_returns_daily.csv"
        if monthly_path.exists() and monthly_path.stat().st_size > 20:
            print("[warn] yfinance empty; reusing cached factor_returns_monthly.csv")
            return pd.read_csv(monthly_path)
        if daily_path.exists() and daily_path.stat().st_size > 20:
            print("[warn] yfinance empty; rebuilding monthly from cached factor_returns_daily.csv")
            fd = pd.read_csv(daily_path, index_col=0, parse_dates=True)
            monthly = fd.resample("ME").last().pct_change()
            monthly.index.name = "month"
            out = monthly.reset_index()
            out["month"] = pd.to_datetime(out["month"]).dt.strftime("%Y-%m-%d")
            return out
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
    if bm == "growth":
        g = _sanitized(row.get("growth_ret"))
        return g if g is not None else nik
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


def _implied_nonlisted_return(panel_sorted: pd.DataFrame, idx: int, row: pd.Series) -> float:
    """Filing-anchored half-year return on non-listed AUM pool (decimal)."""
    if idx <= 0:
        return np.nan
    prior = panel_sorted.iloc[idx - 1]
    cur = row.get("aum_nonlisted_jpym")
    prev = prior.get("aum_nonlisted_jpym")
    if pd.isna(cur) or pd.isna(prev) or float(prev) <= 0:
        return np.nan
    return float(cur) / float(prev) - 1.0


def _build_nonlisted_mandate_slices(
    row: pd.Series,
    panel_sorted: pd.DataFrame,
    idx: int,
    registry: dict,
    resid_cfg: dict,
    latest_public_aum: float,
    pe_str: str,
    half: str,
) -> list[dict]:
    """Business-line institutional buckets with factor + march proxies."""
    from aum_sleeves import business_line_aum_jpym
    from bucket_proxy import bucket_excess

    bl_aum = business_line_aum_jpym(pe_str, row.get("aum_end_jpym"))
    if not bl_aum:
        return []

    slices: list[dict] = []
    buckets = registry.get("business_line_buckets") or []
    if not buckets:
        buckets = [
            {**f, "id": f.get("id"), "fund_id": f"nonlisted_{f['id']}"}
            for f in registry.get("nonlisted_funds", [])
        ]
    for bucket in buckets:
        bid = bucket.get("id")
        if bid == "etf":
            continue
        fund_id = bucket.get("fund_id") or f"nonlisted_{bucket.get('id', 'mandate')}"
        aum_jpym = bl_aum.get(bid or "", np.nan)
        if pd.isna(aum_jpym) or float(aum_jpym) <= 0:
            continue
        bm = bucket.get("benchmark", "nikkei")
        bm_ret = _benchmark_ret(row, bm)
        period_ret, excess, source = bucket_excess(row, bucket, half=half)
        slices.append({
            "period_end": pe_str,
            "half": half,
            "mandate_id": bucket.get("mandate_id", resid_cfg.get("mandate_id")),
            "fund_id": fund_id,
            "period_return": period_ret,
            "benchmark_return": bm_ret,
            "excess_vs_hurdle": excess,
            "aum_jpym": float(aum_jpym),
            "perf_rate": bucket.get("perf_rate", bucket.get("perf_rate_assumption", 0.15)),
            "tag": bucket.get("tag", resid_cfg.get("tag", "[Proxy/Derived]")),
            "source": source,
        })
    return slices


def _load_etf_aum_daily() -> pd.DataFrame:
    path = DATA / "etf_aum_daily.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def _perf_etf_aum_at(period_end: pd.Timestamp, ticker: str, aum_daily: pd.DataFrame) -> float:
    """Listed ETF AUM (¥m) at or before period_end from P5 daily series."""
    if aum_daily.empty or "ticker" not in aum_daily.columns:
        return np.nan
    sub = aum_daily[(aum_daily["ticker"] == ticker) & (aum_daily["date"] <= period_end)]
    if sub.empty:
        return np.nan
    val = sub.sort_values("date").iloc[-1].get("aum_jpym")
    return float(val) if pd.notna(val) else np.nan


def build_mandate_nav(registry: dict, panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """P4 — Pool scraped mandate returns; impute institutional residual from value proxy."""
    monthly_path = DATA / "mandate_nav_monthly.csv"
    if not monthly_path.exists():
        _run_mandate_scrape()
    if not monthly_path.exists():
        return pd.DataFrame(), pd.DataFrame()

    catalog = json.loads(MANDATE_CATALOG.read_text(encoding="utf-8")) if MANDATE_CATALOG.exists() else {}
    monthly = pd.read_csv(monthly_path, parse_dates=["as_of"])
    etf_aum_daily = _load_etf_aum_daily()
    detail_rows: list[dict] = []
    agg_rows: list[dict] = []
    from aum_sleeves import fill_panel_aum_row

    panel_sorted = panel.sort_values("period_end").reset_index(drop=True)
    panel_sorted = pd.DataFrame([fill_panel_aum_row(r) for _, r in panel_sorted.iterrows()])

    etf_weights = {e["id"]: e["weight"] for e in catalog.get("perf_etfs", [])}
    latest_public_aum = (
        monthly.dropna(subset=["aum_jpym"]).groupby("fund_id")["aum_jpym"].last().sum()
        if "aum_jpym" in monthly.columns else 0.0
    )

    for idx, r in panel_sorted.iterrows():
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
            from hwm_engine import hwm_excess_return, nav_hwm_at

            nav_end, hwm_end = nav_hwm_at(fund["id"], pe, monthly)
            hwm_exc = hwm_excess_return(nav_end, hwm_end, hurdle) if half == "H2" else 0.0
            if hwm_exc > excess:
                excess = hwm_exc
            mandate_slices.append({
                "period_end": pe_str, "half": half, "mandate_id": fund["mandate_id"],
                "fund_id": fund["id"], "period_return": ret, "benchmark_return": bm_ret,
                "excess_vs_hurdle": excess, "aum_jpym": aum_jpym,
                "nav_jpy_end": nav_end, "high_water_mark_jpy": hwm_end, "hwm_excess": hwm_exc,
                "perf_rate": fund.get("perf_rate"), "tag": fund.get("tag", "[Filing/Market]"),
                "source": "simplex_monthly_pdf",
            })

        for etf in catalog.get("perf_etfs", []):
            ret = _halfyear_fund_return(monthly, etf["id"], pe, half)
            if np.isnan(ret):
                continue
            bm_ret = _benchmark_ret(r, etf.get("benchmark", "value_pbr"))
            excess = max(0.0, ret - bm_ret)
            ticker = etf.get("ticker", "")
            aum_jpym = _perf_etf_aum_at(pe, ticker, etf_aum_daily)
            if pd.isna(aum_jpym):
                etf_aum = r.get("aum_etf_jpym", np.nan)
                w = etf_weights.get(etf["id"], 1.0 / max(len(catalog.get("perf_etfs", [])), 1))
                aum_jpym = float(etf_aum) * w if pd.notna(etf_aum) else np.nan
            from hwm_engine import hwm_excess_return, nav_hwm_at

            nav_end, hwm_end = nav_hwm_at(etf["id"], pe, monthly)
            hwm_exc = hwm_excess_return(nav_end, hwm_end, 0.0) if half == "H2" else 0.0
            if hwm_exc > excess:
                excess = hwm_exc
            mandate_slices.append({
                "period_end": pe_str, "half": half, "mandate_id": etf["mandate_id"],
                "fund_id": etf["id"], "period_return": ret, "benchmark_return": bm_ret,
                "excess_vs_hurdle": excess, "aum_jpym": aum_jpym,
                "nav_jpy_end": nav_end, "high_water_mark_jpy": hwm_end, "hwm_excess": hwm_exc,
                "perf_rate": etf.get("perf_rate"), "tag": "[Market]",
                "source": "yfinance_etf",
            })

        for proxy in catalog.get("etf_style_proxies", []):
            ret = _halfyear_fund_return(monthly, proxy["id"], pe, half)
            if np.isnan(ret):
                continue
            bm_ret = _benchmark_ret(r, proxy.get("benchmark", "nikkei"))
            hurdle = float(proxy.get("hurdle") or 0.0)
            excess = max(0.0, ret - bm_ret - hurdle)
            mandate_slices.append({
                "period_end": pe_str, "half": half, "mandate_id": proxy["mandate_id"],
                "fund_id": proxy["id"], "period_return": ret, "benchmark_return": bm_ret,
                "excess_vs_hurdle": excess, "aum_jpym": np.nan,
                "perf_rate": proxy.get("perf_rate"), "tag": "[Proxy/Market]",
                "source": "etf_style_proxy",
            })

        # Institutional residual: filing-implied return split across registry buckets
        resid = catalog.get("nonlisted_residual", {})
        mandate_slices.extend(
            _build_nonlisted_mandate_slices(
                r, panel_sorted, int(idx), registry, resid, latest_public_aum, pe_str, half
            )
        )

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
            "note": "Scraped SAM + ETF history + filing-implied nonlisted buckets",
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


# ---------------------------------------------------------------------------
# P4 — mandate terms + perf fee by bucket + march excess on detail
# ---------------------------------------------------------------------------

def build_mandate_terms_export() -> dict:
    """Copy mandate_terms.json metadata into manifest (file lives in model/)."""
    terms_path = ROOT / "mandate_terms.json"
    if not terms_path.exists():
        return {}
    return json.loads(terms_path.read_text(encoding="utf-8"))


def enrich_mandate_detail_march(
    detail: pd.DataFrame,
    march: pd.DataFrame,
    factor_h: pd.DataFrame,
) -> pd.DataFrame:
    """Add march_excess per fund row for H2 crystallization (P6)."""
    if detail.empty:
        return detail
    d = detail.copy()
    d["march_excess"] = np.nan
    if march.empty:
        return d
    march_map = march.set_index("period_end") if "period_end" in march.columns else pd.DataFrame()
    strat_map = {
        "value_up_fund": "march_value_ret",
        "etf_2080": "march_value_ret",
        "etf_2081": "march_value_ret",
        "etf_2082": "march_value_ret",
        "orka_fund": "march_nikkei_ret",
        "nonlisted_residual": "march_nikkei_ret",
        "proxy_nikkei_equity": "march_nikkei_ret",
        "proxy_growth_equity": "march_nikkei_ret",
        "proxy_topix_qis": "march_nikkei_ret",
        "nonlisted_mandate_value_pbr": "march_value_ret",
        "nonlisted_mandate_other": "march_nikkei_ret",
    }
    for i, row in d.iterrows():
        if row["half"] != "H2":
            continue
        pe = row["period_end"]
        mrow = march_map.loc[pe] if pe in march_map.index else None
        if mrow is None:
            continue
        fid = str(row.get("fund_id", ""))
        col = strat_map.get(fid)
        if col is None and fid.startswith("nonlisted_mandate_value"):
            col = "march_value_ret"
        elif col is None and fid.startswith("nonlisted_"):
            col = "march_nikkei_ret"
        elif col is None:
            col = "march_nikkei_ret"
        march_ret = mrow.get(col, mrow.get("march_nikkei_ret", np.nan))
        if pd.isna(march_ret):
            continue
        hurdle = 0.0
        d.at[i, "march_excess"] = max(0.0, float(march_ret) - hurdle)
    return d


def build_perf_fee_by_bucket(detail: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate structural perf driver by mandate bucket (¥m)."""
    if detail.empty or panel.empty:
        return pd.DataFrame()
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        half = r["half"]
        sub = detail[(detail["period_end"] == pe) & (detail["half"] == half)]
        if sub.empty:
            continue
        for mid, g in sub.groupby("mandate_id"):
            drive = 0.0
            for _, s in g.iterrows():
                aum = s.get("aum_jpym")
                if pd.isna(aum) or float(aum) <= 0:
                    continue
                exc = max(0.0, float(s.get("excess_vs_hurdle") or 0))
                rate = float(s.get("perf_rate") or 0.15)
                drive += float(aum) * exc * rate
            rows.append({
                "period_end": pe,
                "half": half,
                "mandate_id": mid,
                "structural_perf_drive_jpym": round(drive, 2),
                "fund_count": len(g),
                "tag": "[Derived]",
            })
        actual = r.get("perf_fee")
        if pd.notna(actual):
            rows.append({
                "period_end": pe,
                "half": half,
                "mandate_id": "_actual_total",
                "structural_perf_drive_jpym": float(actual) / 1000.0,
                "fund_count": np.nan,
                "tag": "[Filing]",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# P5 — ETF units + AUM roll-forward
# ---------------------------------------------------------------------------

def build_etf_units_daily(aum_df: pd.DataFrame) -> pd.DataFrame:
    if aum_df.empty:
        return pd.DataFrame()
    cols = ["date", "ticker", "shares", "nav_jpy", "aum_jpym", "aum_method"]
    out = aum_df[[c for c in cols if c in aum_df.columns]].copy()
    out["tag"] = out["aum_method"] if "aum_method" in out.columns else "[Derived]"
    jpx_meta = DATA / "jpx_etf_meta.csv"
    if jpx_meta.exists():
        meta = pd.read_csv(jpx_meta)
        meta["ticker"] = meta["ticker"].astype(str)
        out = out.merge(
            meta[["ticker", "creation_unit_shares", "redemption_unit_shares"]],
            on="ticker",
            how="left",
        )
    return out.sort_values(["ticker", "date"])


def _resolve_halfyear_flow(
    pe: str,
    fh: pd.DataFrame,
    registry: dict,
    row: pd.Series,
) -> tuple[float, str, dict]:
    """Pick net flow (¥m) for AUM roll-forward: ETF-implied, else JITA-scaled industry flows."""
    meta = {"etf_implied_flow_jpym": np.nan, "jita_equity_flow_bn": np.nan, "jita_etf_flow_bn": np.nan}
    if fh.empty or pe not in fh.index:
        return np.nan, "[Derived]", meta
    fr = fh.loc[pe]
    meta["etf_implied_flow_jpym"] = fr.get("etf_implied_flow_jpym", np.nan)
    meta["jita_equity_flow_bn"] = fr.get("jita_equity_flow_bn", np.nan)
    meta["jita_etf_flow_bn"] = fr.get("jita_etf_flow_bn", np.nan)

    scale = float(registry.get("jita_flow_scale", 0.012))
    etf_share = float(row.get("etf_share") or registry["aum_pools"][1].get("aum_share_fy2025", 0.19))
    nl_share = 1.0 - etf_share

    ef = meta["etf_implied_flow_jpym"]
    jita_etf = meta["jita_etf_flow_bn"]
    jita_eq = meta["jita_equity_flow_bn"]

    etf_flow = np.nan
    if pd.notna(ef) and abs(float(ef)) > 1e-3:
        etf_flow = float(ef)
    elif pd.notna(jita_etf):
        etf_flow = float(jita_etf) * 100.0 * scale  # 億円 → ¥m, industry → Simplex

    nl_flow = float(jita_eq) * 100.0 * scale if pd.notna(jita_eq) else 0.0
    etf_part = float(etf_flow) if pd.notna(etf_flow) else 0.0
    total = etf_part * etf_share + nl_flow * nl_share

    tag = "[Filing/Market]" if pd.notna(jita_etf) or pd.notna(jita_eq) else "[Derived]"
    if pd.notna(etf_flow) and abs(float(ef or 0)) > 1e-3:
        tag = "[Derived]"
    return total, tag, meta


def build_aum_rollforward(
    panel: pd.DataFrame,
    flows_h: pd.DataFrame,
    registry: dict,
) -> pd.DataFrame:
    """AUM_t = AUM_{t-1} × (1 + ret) + net_flows; compare to filing anchor."""
    if panel.empty:
        return pd.DataFrame()
    fh = flows_h.set_index("period_end") if not flows_h.empty and "period_end" in flows_h.columns else pd.DataFrame()
    rows = []
    prior_end = np.nan
    for _, r in panel.sort_values("period_end").iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        filing_end = r.get("aum_end_jpym")
        filing_avg = r.get("aum_avg_jpym")
        nik_ret = float(r.get("nikkei_ret") or 0)
        etf_ret = float(r.get("etf_basket_ret") or nik_ret)
        etf_share = float(r.get("etf_share") or registry["aum_pools"][1].get("aum_share_fy2025", 0.19))
        nl_share = 1.0 - etf_share
        blended_ret = nik_ret * nl_share + etf_ret * etf_share

        flow, flow_tag, flow_meta = _resolve_halfyear_flow(pe, fh, registry, r)
        nowcast_end = np.nan
        if pd.notna(prior_end):
            nowcast_end = float(prior_end) * (1.0 + blended_ret) + (float(flow) if pd.notna(flow) else 0.0)
        if pd.notna(filing_end):
            prior_end = float(filing_end)
        elif pd.notna(nowcast_end):
            prior_end = float(nowcast_end)
        avg_nowcast = np.nan
        if pd.notna(nowcast_end) and pd.notna(filing_avg):
            avg_nowcast = (float(nowcast_end) + float(filing_avg)) / 2.0
        elif pd.notna(nowcast_end):
            avg_nowcast = float(nowcast_end)
        rows.append({
            "period_end": pe,
            "half": r["half"],
            "aum_end_filing_jpym": filing_end,
            "aum_end_nowcast_jpym": round(nowcast_end, 1) if pd.notna(nowcast_end) else np.nan,
            "aum_avg_filing_jpym": filing_avg,
            "aum_avg_nowcast_jpym": round(avg_nowcast, 1) if pd.notna(avg_nowcast) else np.nan,
            "net_flow_jpym": round(flow, 1) if pd.notna(flow) else np.nan,
            "etf_implied_flow_jpym": flow_meta.get("etf_implied_flow_jpym"),
            "jita_equity_flow_bn": flow_meta.get("jita_equity_flow_bn"),
            "jita_etf_flow_bn": flow_meta.get("jita_etf_flow_bn"),
            "blended_return": blended_ret,
            "nikkei_ret": nik_ret,
            "tag": flow_tag,
        })
    return pd.DataFrame(rows)


def build_perf_eligible_aum(panel: pd.DataFrame, pools: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame()
    pool = pools.set_index("period_end") if not pools.empty else pd.DataFrame()
    rows = []
    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        row = {"period_end": pe, "half": r["half"]}
        if not pool.empty and pe in pool.index:
            pr = pool.loc[pe]
            row["perf_eligible_aum_jpym"] = pr.get("perf_eligible_aum_jpym")
            row["nonlisted_share"] = pr.get("nonlisted_share")
            row["etf_share"] = pr.get("etf_share")
        else:
            aum = r.get("aum_end_jpym")
            row["perf_eligible_aum_jpym"] = aum
            row["nonlisted_share"] = np.nan
            row["etf_share"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def build_other_revenue(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in panel.iterrows():
        rev = r.get("revenue")
        base = r.get("base_fee")
        perf = r.get("perf_fee")
        other = np.nan
        if pd.notna(rev):
            other = float(rev) / 1000.0
            if pd.notna(base):
                other -= float(base) / 1000.0
            if pd.notna(perf):
                other -= float(perf) / 1000.0
        rows.append({
            "period_end": r["period_end"].strftime("%Y-%m-%d"),
            "half": r["half"],
            "other_revenue_jpym": other,
            "tag": "[Derived]" if pd.notna(other) else "[Pending]",
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
    try:
        from parse_aum_filings import apply_to_aum_sleeves, scan_evidence

        filing_df = scan_evidence()
        if not filing_df.empty:
            filing_df.to_csv(DATA / "aum_filings_parsed.csv", index=False)
            apply_to_aum_sleeves(filing_df)
    except Exception as exc:
        print(f"[warn] parse_aum_filings: {exc}")

    registry = load_registry()
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "steps": {}}

    # P0
    nav_df, aum_df = fetch_etf_nav_daily(registry)
    nav_df.to_csv(DATA / "etf_nav_daily.csv", index=False)
    aum_df.to_csv(DATA / "etf_aum_daily.csv", index=False)
    _run_jpx_units_scrape()
    aum_jpx = refresh_aum_with_jpx(nav_df, registry)
    if not aum_jpx.empty:
        aum_df = aum_jpx
        aum_df.to_csv(DATA / "etf_aum_daily.csv", index=False)
    jpx_rows = len(pd.read_csv(DATA / "jpx_etf_units_daily.csv")) if (DATA / "jpx_etf_units_daily.csv").exists() else 0
    manifest["steps"]["p0_etf_nav"] = {
        "rows": len(nav_df),
        "tickers": nav_df["ticker"].nunique() if len(nav_df) else 0,
        "jpx_units_rows": jpx_rows,
    }

    panel = pd.read_csv(ROOT / "panel_halfyear.csv", parse_dates=["period_end"]) if (ROOT / "panel_halfyear.csv").exists() else pd.DataFrame()

    # P2 factors first (fund proxy needs value_factor_ret on panel)
    factor_m = fetch_factor_returns(registry)
    if not factor_m.empty:
        factor_m.to_csv(DATA / "factor_returns_monthly.csv", index=False)
    else:
        print("[warn] factor fetch empty; keeping existing factor_returns_monthly.csv")
        factor_path = DATA / "factor_returns_monthly.csv"
        if factor_path.exists() and factor_path.stat().st_size > 20:
            factor_m = pd.read_csv(factor_path)
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
    from bucket_proxy import build_bucket_weighted_proxy

    bucket_proxy_df = build_bucket_weighted_proxy(panel, registry)
    if not bucket_proxy_df.empty:
        bucket_proxy_df.to_csv(DATA / "bucket_weighted_proxy_halfyear.csv", index=False)
    manifest["steps"]["p0_fund_proxy"] = {
        "rows": len(fund_proxy),
        "bucket_proxy_rows": len(bucket_proxy_df),
    }

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
    jita_rows = int(flows_m["jita_equity_net_flow_bn_jpy"].notna().sum()) if "jita_equity_net_flow_bn_jpy" in flows_m.columns else 0
    manifest["steps"]["p1_flows"] = {"monthly": len(flows_m), "etf_flow_rows": len(etf_flows)}
    manifest["steps"]["p5_jita_flows"] = {
        "jita_months": jita_rows,
        "scrape_script": str(JITA_SCRIPT.relative_to(ROOT.parents[1])),
        "source": "https://www.toushin.or.jp/tws/toukei_dw/I0112B_pub_m.xlsx",
    }

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
    p4_rows = p4_detail = p6_rows = p5_roll = p7_other = 0
    p4_tag = "[Filing/Market/Derived]"
    oos_acceptance: list[dict] = []
    if not panel.empty:
        mandate, mandate_detail = build_mandate_nav(registry, panel)
        mandate.to_csv(DATA / "mandate_nav_halfyear.csv", index=False)
        p4_rows = len(mandate)
        p4_detail = len(mandate_detail)
        march = march_window_halfyear(panel)
        march.to_csv(DATA / "march_window_halfyear.csv", index=False)
        p6_rows = len(march)
        mandate_detail = enrich_mandate_detail_march(mandate_detail, march, factor_h)
        from hwm_engine import apply_synthetic_hwm_to_nonlisted

        mandate_detail = apply_synthetic_hwm_to_nonlisted(mandate_detail, registry)
        from perf_calibration import run_perf_calibration

        _, cal_manifest, mandate_detail = run_perf_calibration(panel, mandate_detail, registry)
        manifest["steps"]["p8_perf_calibration"] = cal_manifest
        if not mandate_detail.empty:
            mandate_detail.to_csv(DATA / "mandate_nav_detail.csv", index=False)
        perf_bucket = build_perf_fee_by_bucket(mandate_detail, panel)
        perf_bucket.to_csv(DATA / "perf_fee_by_bucket_halfyear.csv", index=False)
        terms = build_mandate_terms_export()
        manifest["steps"]["p4_mandate_terms"] = {
            "funds": len(terms.get("funds", {})),
            "path": "mandate_terms.json",
        }

        units = build_etf_units_daily(aum_df)
        units.to_csv(DATA / "etf_units_daily.csv", index=False)
        flows_h_path = DATA / "flows_halfyear.csv"
        flows_h_df = pd.read_csv(flows_h_path) if flows_h_path.exists() else pd.DataFrame()
        pools_path = DATA / "aum_pools_halfyear.csv"
        pools_df = pd.read_csv(pools_path) if pools_path.exists() else pd.DataFrame()
        roll = build_aum_rollforward(panel, flows_h_df, registry)
        roll.to_csv(DATA / "aum_rollforward_halfyear.csv", index=False)
        p5_roll = len(roll)
        perf_elig = build_perf_eligible_aum(panel, pools_df)
        perf_elig.to_csv(DATA / "perf_eligible_aum_halfyear.csv", index=False)
        other_rev = build_other_revenue(panel)
        other_rev.to_csv(DATA / "other_revenue_halfyear.csv", index=False)
        p7_other = len(other_rev)
        manifest["steps"]["p5_aum_rollforward"] = {
            "rows": p5_roll,
            "etf_units_rows": len(units),
        }
        manifest["steps"]["p7_other_revenue"] = {"rows": p7_other}

    manifest["steps"]["p4_mandate_nav"] = {
        "rows": p4_rows, "detail_rows": p4_detail, "tag": p4_tag,
        "scrape_script": str(MANDATE_SCRIPT.relative_to(ROOT.parents[1])),
        "perf_fee_by_bucket": int((DATA / "perf_fee_by_bucket_halfyear.csv").exists()),
    }
    manifest["steps"]["p6_march_window"] = {"rows": p6_rows}
    manifest["oos_acceptance"] = oos_acceptance

    (DATA / "data_acquisition_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
