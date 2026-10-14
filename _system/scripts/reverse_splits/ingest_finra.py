"""Ingest FINRA bi-monthly consolidated short interest files."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config, load_config
from .db import init_db
from .utils import normalize_ticker, parse_date, tqdm

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

# FINRA consolidated short interest historical files (example pattern).
# Users can also drop CSVs manually into data/raw/finra/.
FINRA_INDEX = "https://cdn.finra.org/equity/regsho/weekly/"


def _read_table(path: Path) -> pd.DataFrame | None:
    import pandas as pd  # deferred

    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                name = next(n for n in zf.namelist() if n.lower().endswith((".txt", ".csv")))
                with zf.open(name) as f:
                    raw = f.read()
            bio = io.BytesIO(raw)
            for sep in ["|", ",", "\t"]:
                bio.seek(0)
                try:
                    df = pd.read_csv(bio, sep=sep, dtype=str)
                    if df.shape[1] >= 3:
                        return df
                except Exception:
                    continue
            return None
        for sep in ["|", ",", "\t"]:
            try:
                df = pd.read_csv(path, sep=sep, dtype=str)
                if df.shape[1] >= 3:
                    return df
            except Exception:
                continue
    except Exception:
        return None
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=colmap)
    rename = {}
    for c in df.columns:
        if c in {"symbolcode", "symbol", "ticker_symbol", "issue_symbol", "stock_symbol"}:
            rename[c] = "ticker"
        elif c in {"accountingyearmonthnumber", "settlementdate", "settlement_date", "date"}:
            rename[c] = "settlement_date"
        elif "currentshortposition" in c or c in {"shortinterest", "short_interest", "current_short_position"}:
            rename[c] = "short_interest"
        elif "averagedailyvolume" in c or c in {"avg_daily_volume", "average_daily_volume", "adv"}:
            rename[c] = "avg_daily_volume"
        elif "daystocover" in c or c in {"days_to_cover", "dtc"}:
            rename[c] = "days_to_cover"
    return df.rename(columns=rename)


def ingest_finra_file(conn: sqlite3.Connection, path: Path) -> int:
    df = _read_table(path)
    if df is None or df.empty:
        return 0
    df = _normalize_columns(df)
    if "ticker" not in df.columns:
        return 0
    n = 0
    for _, row in df.iterrows():
        ticker = normalize_ticker(row.get("ticker"))
        sett = parse_date(row.get("settlement_date"))
        if not ticker or not sett:
            # accountingyearmonthnumber like 202401
            ay = str(row.get("settlement_date") or row.get("accountingyearmonthnumber") or "")
            if len(ay) == 6 and ay.isdigit():
                sett = f"{ay[:4]}-{ay[4:6]}-15"
            else:
                continue
        def num(x):
            try:
                return float(str(x).replace(",", ""))
            except Exception:
                return None

        si = num(row.get("short_interest"))
        adv = num(row.get("avg_daily_volume"))
        dtc = num(row.get("days_to_cover"))
        if dtc is None and si and adv and adv > 0:
            dtc = si / adv
        conn.execute(
            """
            INSERT INTO finra_short_interest (ticker, settlement_date, short_interest, avg_daily_volume, days_to_cover, source_file)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, settlement_date) DO UPDATE SET
                short_interest=excluded.short_interest,
                avg_daily_volume=excluded.avg_daily_volume,
                days_to_cover=excluded.days_to_cover,
                source_file=excluded.source_file
            """,
            (ticker, sett, si, adv, dtc, path.name),
        )
        n += 1
    return n


def download_sample_finra_note(cfg: Config) -> Path:
    note = cfg.finra_dir / "README_FINRA.txt"
    note.write_text(
        "Place FINRA Consolidated Short Interest files (.txt/.csv/.zip) in this folder.\n"
        "Download from FINRA Equity Short Interest / Reg SHO consolidated files.\n"
        "Expected columns include Symbol, Settlement Date, Current Short Position, Average Daily Volume.\n",
        encoding="utf-8",
    )
    return note


def ingest_finra(cfg: Config | None = None) -> dict[str, int]:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    download_sample_finra_note(cfg)
    files = sorted(
        [
            p
            for p in cfg.finra_dir.iterdir()
            if p.suffix.lower() in {".txt", ".csv", ".zip"} and not p.name.upper().startswith("README")
        ]
    )
    total = 0
    for path in tqdm(files, desc="FINRA"):
        total += ingest_finra_file(conn, path)
        conn.commit()
    # Synthetic proxy rows from event prices volume if no FINRA files — keeps backtest usable
    synthetic = 0
    if total == 0:
        events = conn.execute("SELECT DISTINCT ticker, ex_date FROM reverse_splits").fetchall()
        for e in events:
            row = conn.execute(
                """
                SELECT AVG(volume) AS adv FROM prices_daily
                WHERE ticker=? AND date <= ? AND date >= date(?, '-30 day')
                """,
                (e["ticker"], e["ex_date"], e["ex_date"]),
            ).fetchone()
            adv = row["adv"] if row and row["adv"] else None
            if not adv:
                continue
            # No true short interest — store NULL SI with ADV for participation sizing fallback
            conn.execute(
                """
                INSERT INTO finra_short_interest (ticker, settlement_date, short_interest, avg_daily_volume, days_to_cover, source_file)
                VALUES (?, ?, NULL, ?, NULL, 'synthetic_adv_only')
                ON CONFLICT(ticker, settlement_date) DO NOTHING
                """,
                (e["ticker"], e["ex_date"], float(adv)),
            )
            synthetic += 1
        conn.commit()
    conn.close()
    return {"files": len(files), "rows": total, "synthetic_adv_rows": synthetic}


def nearest_short_interest(conn: sqlite3.Connection, ticker: str, asof: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM finra_short_interest
        WHERE ticker=? AND settlement_date <= ?
        ORDER BY settlement_date DESC LIMIT 1
        """,
        (ticker, asof),
    ).fetchone()


if __name__ == "__main__":
    print(ingest_finra())
