#!/usr/bin/env python3
"""Parse 運用資産残高 tables from 7176.T issuer-info text extracts."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT.parents[1] / "research" / "evidence" / "_text"
OUT_CSV = ROOT / "data" / "aum_filings_parsed.csv"

BUCKET_PATTERNS = {
    "equity": re.compile(r"^株式\s"),
    "etf": re.compile(r"^ETF"),
    "qis": re.compile(r"^QIS"),
    "other": re.compile(r"^その他\s"),
    "nonlisted_legacy": re.compile(r"^非上場"),
    "etf_legacy": re.compile(r"^上場投資"),
    "total": re.compile(r"^合計\s"),
}

COL_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月")


def _col_to_period_end(year: int, month: int) -> str:
    """Map filing column to panel period_end (Mar = FY end, Sep = interim)."""
    if month == 3:
        return f"{year}-03-31"
    if month == 9:
        return f"{year}-09-30"
    return f"{year}-{month:02d}-28"


def _parse_header(line: str) -> list[tuple[str, str]]:
    cols = []
    for m in COL_RE.finditer(line):
        pe = _col_to_period_end(int(m.group(1)), int(m.group(2)))
        cols.append((m.group(0).strip(), pe))
    return cols


def _parse_value(tok: str) -> float | None:
    tok = tok.strip().replace(",", "")
    if not tok or tok in ("－", "-", "—"):
        return None
    try:
        return float(tok)
    except ValueError:
        return None


def _extract_table_block(text: str) -> str | None:
    """Return lines around the AUM breakdown table (not MD&A one-liner totals)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "(４)" in ln and "運用資産残高" in ln:
            start = i
            break
        if "期末及び中間期末運用資産残高" in ln or "期末運用資産残高の推移" in ln:
            start = i
            break
    if start is None:
        for i, ln in enumerate(lines):
            if "運用資産残高" in ln and "推移" in ln:
                start = i
                break
    if start is None:
        return None
    return "\n".join(lines[start : start + 20])


def parse_aum_table(text: str, source_file: str) -> list[dict]:
    block = _extract_table_block(text)
    if not block:
        return []
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    header_line = next((ln for ln in lines if COL_RE.search(ln)), None)
    if not header_line:
        return []
    columns = _parse_header(header_line)
    if not columns:
        return []

    rows_out: list[dict] = []
    for ln in lines:
        if ln == header_line or "単位" in ln or ln.startswith("（注"):
            continue
        bucket = None
        values: list[float | None] = []
        for name, pat in BUCKET_PATTERNS.items():
            m = pat.match(ln)
            if not m:
                continue
            bucket = name
            tail = ln[m.end() :]
            values = [_parse_value(x) for x in re.findall(r"[\d,]+", tail)]
            break
        if not bucket or len(values) < len(columns):
            continue
        for (_, pe), val in zip(columns, values[: len(columns)]):
            if val is None:
                continue
            rows_out.append({
                "period_end": pe,
                "bucket": bucket,
                "aum_oku": val,
                "source_file": source_file,
                "tag": "[Filing]",
            })
    return rows_out


def _legacy_to_sleeves(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot buckets to total / nonlisted / etf oku per period."""
    records = []
    for pe, g in df.groupby("period_end"):
        by = dict(zip(g["bucket"], g["aum_oku"]))
        if "total" in by:
            total = by["total"]
        else:
            parts = [by.get(k) for k in ("equity", "etf", "qis", "other", "nonlisted_legacy", "etf_legacy")]
            parts = [p for p in parts if p is not None]
            total = sum(parts) if parts else None
        if "nonlisted_legacy" in by and "etf_legacy" in by:
            nl, etf = by["nonlisted_legacy"], by["etf_legacy"]
        elif "equity" in by:
            nl = by.get("equity", 0) + by.get("qis", 0) + by.get("other", 0)
            etf = by.get("etf")
        else:
            nl, etf = None, None
        if total is None:
            continue
        records.append({
            "period_end": pe,
            "aum_total_oku": total,
            "aum_nonlisted_oku": nl,
            "aum_etf_oku": etf,
            "aum_equity_oku": by.get("equity"),
            "aum_qis_oku": by.get("qis"),
            "aum_other_oku": by.get("other"),
            "tag": "[Filing]",
        })
    return pd.DataFrame(records).drop_duplicates("period_end", keep="last")


def scan_evidence(evidence_dir: Path | None = None) -> pd.DataFrame:
    evidence_dir = evidence_dir or EVIDENCE
    raw_rows: list[dict] = []
    for path in sorted(evidence_dir.glob("*.txt")):
        if "発行者情報" not in path.name and "中間発行者" not in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        raw_rows.extend(parse_aum_table(text, path.name))
    if not raw_rows:
        return pd.DataFrame()
    long = pd.DataFrame(raw_rows)
    wide = _legacy_to_sleeves(long)
    return wide.sort_values("period_end").reset_index(drop=True)


def apply_to_aum_sleeves(df: pd.DataFrame) -> dict:
    """Merge parsed filings into aum_sleeves.AUM_BY_PERIOD (does not overwrite provisional)."""
    from aum_sleeves import AUM_BY_PERIOD, AUM_PROVISIONAL_PERIODS, refresh_from_dataframe

    return refresh_from_dataframe(df)


def main() -> None:
    df = scan_evidence()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        print("[warn] no AUM tables parsed")
        return
    df.to_csv(OUT_CSV, index=False)
    stats = apply_to_aum_sleeves(df)
    print(json.dumps({"rows": len(df), "periods": df["period_end"].tolist(), **stats}, indent=2))


if __name__ == "__main__":
    main()
