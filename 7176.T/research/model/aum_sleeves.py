"""Shared AUM sleeve resolution for 7176.T panel + mandate engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Sep-2025 interim mix (20251225_中間発行者情報): ETF 2,721 / total 13,733 億円
AUM_MIX_ETF_SHARE = 2_721 / 13_733
AUM_MIX_TAG = "[Assumption]"

# Filing-extracted or derived (oku). None = fill via mix.
AUM_BY_PERIOD: dict[str, tuple[float, float | None, float | None]] = {
    "2023-03-31": (12_759, 10_723, 2_037),
    "2024-03-31": (13_080, 10_478, 2_601),
    "2024-09-30": (12_495, 10_170, 2_325),
    "2025-03-31": (12_973, 10_493, 2_479),
    "2025-09-30": (13_733, 11_012, 2_721),  # nl = total − etf [Filing/Derived]
    # Provisional until FY2026 有報: scale Sep-2025 ETF share to Mar-2026 total
    "2026-03-31": (13_357, 10_711, 2_646),
}
AUM_PROVISIONAL_PERIODS: set[str] = {"2026-03-31"}

# Business-line AUM (億円) from filings — populated by parse_aum_filings.py
AUM_BUSINESS_LINES: dict[str, dict[str, float]] = {}

# Sep-2025 interim mix (億円 5,329 / 2,721 / 5,421 / 261 of 13,733 total)
DEFAULT_BUSINESS_LINE_SHARE: dict[str, float] = {
    "equity": 5_329 / 13_733,
    "etf": 2_721 / 13_733,
    "qis": 5_421 / 13_733,
    "other": 261 / 13_733,
}


def business_line_aum_jpym(period_key: str, total_jpym: float | None) -> dict[str, float]:
    """Business-line AUM in ¥m from filing buckets or scaled total."""
    bl = AUM_BUSINESS_LINES.get(period_key[:10])
    if bl:
        return {k: float(v) * 100.0 for k, v in bl.items()}
    if total_jpym is None or not np.isfinite(total_jpym):
        return {}
    t_oku = float(total_jpym) / 100.0
    return {k: t_oku * share * 100.0 for k, share in DEFAULT_BUSINESS_LINE_SHARE.items()}


def refresh_from_dataframe(df: pd.DataFrame) -> dict:
    """Merge filing-parsed sleeves into AUM_BY_PERIOD; filings override provisional."""
    global AUM_BUSINESS_LINES, AUM_PROVISIONAL_PERIODS
    updated = []
    cleared_provisional: list[str] = []
    for _, r in df.iterrows():
        pe = str(r["period_end"])[:10]
        total = float(r["aum_total_oku"])
        nl = r.get("aum_nonlisted_oku")
        etf = r.get("aum_etf_oku")
        nl_f = float(nl) if pd.notna(nl) else None
        etf_f = float(etf) if pd.notna(etf) else None
        AUM_BY_PERIOD[pe] = (total, nl_f, etf_f)
        if pe in AUM_PROVISIONAL_PERIODS:
            AUM_PROVISIONAL_PERIODS.discard(pe)
            cleared_provisional.append(pe)
        bl = {}
        for col, key in [
            ("aum_equity_oku", "equity"),
            ("aum_qis_oku", "qis"),
            ("aum_other_oku", "other"),
            ("aum_etf_oku", "etf"),
        ]:
            if col in r and pd.notna(r[col]):
                bl[key] = float(r[col])
        if bl:
            AUM_BUSINESS_LINES[pe] = bl
        updated.append(pe)
    return {
        "updated_periods": updated,
        "n": len(updated),
        "cleared_provisional": cleared_provisional,
    }


def resolve_aum_oku(
    period_key: str,
    total: float | None,
    nonlisted: float | None,
    etf: float | None,
) -> tuple[float | None, float | None, float | None, str]:
    """Return (total, nonlisted, etf, tag) in 億円."""
    if total is None:
        return None, None, None, "[Filing]"
    nl, etf_v = nonlisted, etf
    tag = "[Filing]"
    if nl is None and etf_v is None:
        etf_v = round(total * AUM_MIX_ETF_SHARE)
        nl = total - etf_v
        tag = AUM_MIX_TAG
    elif nl is None and etf_v is not None:
        nl = total - etf_v
        tag = "[Filing/Derived]"
    elif etf_v is None and nl is not None:
        etf_v = total - nl
        tag = "[Filing/Derived]"
    if period_key in AUM_PROVISIONAL_PERIODS:
        tag = AUM_MIX_TAG
    return total, nl, etf_v, tag


def resolve_aum_jpym(
    period_key: str,
    total: float | None,
    nonlisted: float | None,
    etf: float | None,
) -> tuple[float | None, float | None, float | None, str]:
    """Return sleeve AUM in ¥m (million yen)."""
    t, nl, etf_v, tag = resolve_aum_oku(period_key, total, nonlisted, etf)
    scale = 100.0  # 億円 → ¥m
    return (
        t * scale if t is not None else np.nan,
        nl * scale if nl is not None else np.nan,
        etf_v * scale if etf_v is not None else np.nan,
        tag,
    )


def fill_panel_aum_row(row: pd.Series) -> pd.Series:
    """Fill missing aum_nonlisted_jpym / aum_etf_jpym on a panel row."""
    key = (
        row["period_end"].strftime("%Y-%m-%d")
        if hasattr(row["period_end"], "strftime")
        else str(row["period_end"])[:10]
    )
    raw = AUM_BY_PERIOD.get(key)
    total_m = row.get("aum_end_jpym")
    nl_m = row.get("aum_nonlisted_jpym")
    etf_m = row.get("aum_etf_jpym")

    if raw:
        t_oku, nl_oku, etf_oku = raw
    else:
        t_oku = float(total_m) / 100.0 if pd.notna(total_m) else None
        nl_oku = float(nl_m) / 100.0 if pd.notna(nl_m) else None
        etf_oku = float(etf_m) / 100.0 if pd.notna(etf_m) else None

    nl_in = float(nl_m) / 100.0 if pd.notna(nl_m) else nl_oku
    etf_in = float(etf_m) / 100.0 if pd.notna(etf_m) else etf_oku
    t_in = float(total_m) / 100.0 if pd.notna(total_m) else t_oku

    _, nl_res, etf_res, tag = resolve_aum_oku(key, t_in, nl_in, etf_in)
    out = row.copy()
    if t_in is not None:
        out["aum_end_jpym"] = t_in * 100.0
    if nl_res is not None:
        out["aum_nonlisted_jpym"] = nl_res * 100.0
    if etf_res is not None:
        out["aum_etf_jpym"] = etf_res * 100.0
    out["aum_sleeve_tag"] = tag
    return out
