"""Matched names that are not inside their own reverse split."""

from __future__ import annotations

import math
import random
from collections import defaultdict

from datetime import date

from .adjust import PriceFrame, to_nominal
from .book import Candidate
from .config import Config, load_config
from .db import init_db
from .execute import full_spread, short_fills, trade_pnl
from .ingest_splits import classify_exchange


def _series_cache(frames: dict[str, PriceFrame], splits: dict[str, list[tuple[str, float]]], window: int):
    cache = {}
    for ticker, frame in frames.items():
        if len(frame) == 0:
            continue
        cache[ticker] = to_nominal(frame, splits.get(ticker, []), window)
    return cache


def _level(series, index: int) -> tuple[float, float] | None:
    if index <= 0:
        return None
    px = series.frame.close[index - 1]
    vol = series.frame.volume[index - 1]
    if px <= 0 or vol <= 0:
        return None
    dollar = px * vol
    if dollar <= 0:
        return None
    return math.log(px), math.log(dollar)


def _hold_return(series, entry: str, exit_day: str, spread_floor: float, range_fraction: float, fee_annual: float) -> float | None:
    dates = series.frame.dates
    try:
        entry_i = dates.index(entry)
        exit_i = dates.index(exit_day)
    except ValueError:
        return None
    if exit_i < entry_i:
        return None
    for split in series.splits:
        if split.status == "missing":
            continue
        if dates[entry_i] < split.ex_date <= dates[exit_i]:
            return None
    spread_entry = (
        spread_floor
        if entry_i == 0
        else full_spread(series.frame.high[entry_i - 1], series.frame.low[entry_i - 1], spread_floor, range_fraction)
    )
    spread_exit = (
        spread_floor
        if exit_i == 0
        else full_spread(series.frame.high[exit_i - 1], series.frame.low[exit_i - 1], spread_floor, range_fraction)
    )
    fills = short_fills(series.frame.open[entry_i], series.frame.close[exit_i], spread_entry, spread_exit)
    if fills is None or fills[0] < 1.0:
        return None
    hold = max(1, (date.fromisoformat(exit_day[:10]) - date.fromisoformat(entry[:10])).days)
    _gross, _fee, net = trade_pnl(1.0, fills[0], fills[1], fee_annual, int(hold))
    return net / fills[0]


def attach_matches(
    trades: list[Candidate],
    subject_frames: dict[str, PriceFrame],
    pool_frames: dict[str, PriceFrame],
    splits: dict[str, list[tuple[str, float]]],
    *,
    window: int,
    spread_floor: float,
    range_fraction: float,
    fee_annual: float,
    price_caliper: float,
    volume_caliper: float,
    field: str,
    pool_splits: dict[str, list[tuple[str, float]]] | None = None,
) -> int:
    """Match each trade to another ticker on prior-day log price and dollar volume.

    The trade's own price comes from `subject_frames`. Candidates come from
    `pool_frames`, which is the same set for peers and a separate listed
    sample for the random control.
    """
    subject = _series_cache(subject_frames, splits, window)
    pool = subject if pool_frames is subject_frames else _series_cache(pool_frames, pool_splits or {}, window)
    index: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for ticker, series in pool.items():
        dates = series.frame.dates
        for i, day in enumerate(dates):
            if i == 0:
                continue
            level = _level(series, i)
            if level is None:
                continue
            index[day].append((ticker, level[0], level[1]))

    log_price_cap = math.log(price_caliper)
    log_volume_cap = math.log(volume_caliper)
    matched = 0
    for trade in trades:
        series = subject.get(trade.ticker)
        if series is None or trade.entry_date not in series.frame.dates:
            continue
        entry_i = series.frame.dates.index(trade.entry_date)
        level = _level(series, entry_i)
        if level is None:
            continue
        best = None
        best_dist = None
        for ticker, log_px, log_dv in index.get(trade.entry_date, []):
            if ticker == trade.ticker:
                continue
            dp = log_px - level[0]
            dv = log_dv - level[1]
            if abs(dp) > log_price_cap or abs(dv) > log_volume_cap:
                continue
            dist = dp * dp + dv * dv
            if best_dist is not None and dist >= best_dist:
                continue
            other = pool.get(ticker)
            if other is None:
                continue
            ret = _hold_return(
                other, trade.entry_date, trade.exit_date, spread_floor, range_fraction, fee_annual
            )
            if ret is None:
                continue
            best = (ticker, ret)
            best_dist = dist
        if best is None:
            continue
        setattr(trade, field, best[0])
        setattr(trade, "peer_return" if field == "peer_ticker" else "control_return", best[1])
        matched += 1
    return matched


def download_control_universe(cfg: Config | None = None, sample_size: int | None = None) -> dict[str, int]:
    """Random listed names that are not in the reverse-split event set."""
    import pandas as pd  # deferred: network command only
    import yfinance as yf

    cfg = cfg or load_config()
    sample_size = int(sample_size or cfg.section("controls").get("sample_size", 80))
    conn = init_db(cfg.db_path)
    taken = {row["ticker"] for row in conn.execute("SELECT DISTINCT ticker FROM reverse_splits")}
    raw_path = cfg.raw_dir / "sec_company_tickers_exchange.json"
    listed: list[str] = []
    if raw_path.exists():
        import json

        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        fields = payload.get("fields") or []
        for row in payload.get("data") or []:
            rec = dict(zip(fields, row))
            ticker = (rec.get("ticker") or "").upper().replace(".", "-")
            if not ticker or ticker in taken or classify_exchange(rec.get("exchange")) != "listed":
                continue
            listed.append(ticker)
    rng = random.Random(7)
    rng.shuffle(listed)
    pick = listed[:sample_size]
    if not pick:
        conn.close()
        return {"candidates": len(listed), "downloaded": 0}
    start = conn.execute("SELECT MIN(ex_date) AS d FROM reverse_splits").fetchone()["d"]
    end = conn.execute("SELECT MAX(ex_date) AS d FROM reverse_splits").fetchone()["d"]
    from .utils import add_days

    frame = yf.download(
        pick,
        start=add_days(start, -40) if start else None,
        end=add_days(end, 40) if end else None,
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )
    from .ingest_prices import _slice_ticker

    n = 0
    for ticker in pick:
        piece = _slice_ticker(frame, ticker)
        if piece is None or piece.empty:
            continue
        for idx, row in piece.iterrows():
            day = str(pd.Timestamp(idx).date())
            close = row.get("Close")
            if close is None or pd.isna(close):
                continue
            conn.execute(
                """
                INSERT INTO control_prices (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume
                """,
                (
                    ticker,
                    day,
                    float(row["Open"]) if pd.notna(row.get("Open")) else None,
                    float(row["High"]) if pd.notna(row.get("High")) else None,
                    float(row["Low"]) if pd.notna(row.get("Low")) else None,
                    float(close),
                    float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                ),
            )
            n += 1
    conn.commit()
    conn.close()
    return {"candidates": len(listed), "sampled": len(pick), "rows": n}
