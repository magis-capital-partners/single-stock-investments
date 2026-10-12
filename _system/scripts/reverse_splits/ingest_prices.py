"""Ingest daily OHLCV around reverse-split events."""

from __future__ import annotations

import sqlite3

from typing import TYPE_CHECKING

from .config import Config, load_config
from .db import init_db
from .utils import add_days, parse_date, tqdm

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def _window_for_event(ex_date: str, first_proxy: str | None, pre: int, post: int) -> tuple[str, str]:
    start = add_days(ex_date, -pre)
    if first_proxy:
        fp = parse_date(first_proxy)
        if fp and fp < start:
            start = fp
    end = add_days(ex_date, post)
    return start, end


def upsert_prices(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> int:
    import pandas as pd  # deferred

    if df is None or df.empty:
        return 0
    n = 0
    for idx, row in df.iterrows():
        d = parse_date(idx)
        if not d:
            continue
        close = float(row["Close"]) if pd.notna(row.get("Close")) else None
        adj = float(row["Adj Close"]) if "Adj Close" in row and pd.notna(row.get("Adj Close")) else close
        # yfinance Close is split-adjusted by default in recent versions; store both
        conn.execute(
            """
            INSERT INTO prices_daily (ticker, date, open, high, low, close, volume, adj_close, unadj_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume,
                adj_close=excluded.adj_close, unadj_close=excluded.unadj_close
            """,
            (
                ticker,
                d,
                float(row["Open"]) if pd.notna(row.get("Open")) else None,
                float(row["High"]) if pd.notna(row.get("High")) else None,
                float(row["Low"]) if pd.notna(row.get("Low")) else None,
                close,
                float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                adj,
                close,  # documented: use close as working series; reconstruct unadj around split in backtest
            ),
        )
        n += 1
    return n


def ingest_prices(cfg: Config | None = None, limit: int | None = None, since: str | None = None) -> dict[str, int]:
    """Download OHLCV around events; ``since`` keeps only events dated on or after it."""
    import pandas as pd  # deferred: network command only
    import yfinance as yf

    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    pre = int(cfg.section("prices").get("pre_event_days", 120))
    post = int(cfg.section("prices").get("post_event_days", 60))

    events = conn.execute(
        "SELECT id, ticker, ex_date, first_proxy_date, announce_date FROM reverse_splits "
        "WHERE ? IS NULL OR ex_date >= ? OR announce_date >= ? ORDER BY ex_date DESC",
        (since, since, since),
    ).fetchall()
    if limit:
        events = events[:limit]

    # Group by ticker to minimize downloads
    by_ticker: dict[str, list] = {}
    for e in events:
        by_ticker.setdefault(e["ticker"], []).append(e)

    windows: dict[str, tuple[str, str]] = {}
    for ticker, evs in by_ticker.items():
        starts, ends = [], []
        for event in evs:
            start, end = _window_for_event(event["ex_date"], event["first_proxy_date"] or event["announce_date"], pre, post)
            starts.append(start)
            ends.append(end)
        windows[ticker] = (min(starts), max(ends))

    rows_written = 0
    tickers_ok = 0
    tickers = list(windows)
    batch_size = 40
    for offset in tqdm(range(0, len(tickers), batch_size), desc="prices"):
        batch = tickers[offset : offset + batch_size]
        start = min(windows[t][0] for t in batch)
        end = max(windows[t][1] for t in batch)
        try:
            df = yf.download(
                batch,
                start=start,
                end=add_days(end, 1),
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="column",
            )
        except Exception:
            df = None
        for ticker in batch:
            piece = _slice_ticker(df, ticker) if df is not None else None
            if piece is None or piece.empty:
                try:
                    piece = yf.download(
                        ticker,
                        start=windows[ticker][0],
                        end=add_days(windows[ticker][1], 1),
                        auto_adjust=False,
                        progress=False,
                        threads=False,
                    )
                    piece = _slice_ticker(piece, ticker)
                except Exception:
                    piece = None
            if piece is None or piece.empty:
                continue
            lo, hi = windows[ticker]
            piece = piece.loc[(piece.index >= pd.Timestamp(lo)) & (piece.index <= pd.Timestamp(hi))]
            n = upsert_prices(conn, ticker, piece)
            rows_written += n
            if n:
                tickers_ok += 1
        conn.commit()
    conn.close()
    return {"tickers": len(by_ticker), "tickers_ok": tickers_ok, "rows": rows_written}


def _slice_ticker(df: pd.DataFrame | None, ticker: str) -> pd.DataFrame | None:
    import pandas as pd  # deferred

    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        level = 1 if ticker in df.columns.get_level_values(1) else 0
        if ticker not in df.columns.get_level_values(level):
            return None
        out = df.xs(ticker, axis=1, level=level)
    else:
        out = df
    if isinstance(out, pd.Series):
        return None
    return out.dropna(how="all")


if __name__ == "__main__":
    print(ingest_prices())
