"""Entry-window backtest with borrow-fee scenarios and capacity caps."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import pandas as pd

from .config import Config, load_config
from .db import init_db
from .borrow import latest_borrow, position_cap_shares
from .ingest_finra import nearest_short_interest
from .utils import add_days, parse_date

ENTRY_SIGNALS = [
    "first_proxy",
    "announce",
    "vote",
    "ratio_set",
    "day_before_ex",
    "ex_close",
    "ex_plus_1",
    "ex_plus_5",
    "ex_plus_10",
]


def _price_frame(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT date, open, high, low, close, adj_close, unadj_close, volume FROM prices_daily WHERE ticker=? ORDER BY date",
        (ticker,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def _signal_date(event: sqlite3.Row, signal: str) -> str | None:
    ex = event["ex_date"]
    mapping = {
        "first_proxy": event["first_proxy_date"],
        "announce": event["announce_date"],
        "vote": event["vote_date"],
        "ratio_set": event["ratio_set_date"],
        "day_before_ex": add_days(ex, -1),
        "ex_close": ex,
        "ex_plus_1": add_days(ex, 1),
        "ex_plus_5": add_days(ex, 5),
        "ex_plus_10": add_days(ex, 10),
    }
    return parse_date(mapping.get(signal))


def _on_or_after(df: pd.DataFrame, d: str, field: str = "close") -> tuple[pd.Timestamp, float] | None:
    if df.empty:
        return None
    ts = pd.Timestamp(d)
    sub = df[df.index >= ts]
    if sub.empty:
        return None
    row = sub.iloc[0]
    px = row.get(field)
    if px is None or pd.isna(px) or float(px) <= 0:
        return None
    return sub.index[0], float(px)


def _on_or_before(df: pd.DataFrame, d: str, field: str = "close") -> tuple[pd.Timestamp, float] | None:
    if df.empty:
        return None
    ts = pd.Timestamp(d)
    sub = df[df.index <= ts]
    if sub.empty:
        return None
    row = sub.iloc[-1]
    px = row.get(field)
    if px is None or pd.isna(px) or float(px) <= 0:
        return None
    return sub.index[-1], float(px)


def _horizon_exit(df: pd.DataFrame, entry_ts: pd.Timestamp, horizon: int) -> tuple[pd.Timestamp, float] | None:
    # trading-day horizon: shift by number of rows
    if entry_ts not in df.index:
        # find position
        pos_list = df.index.get_indexer([entry_ts], method="backfill")
        if len(pos_list) == 0 or pos_list[0] < 0:
            return None
        pos = int(pos_list[0])
    else:
        pos = int(df.index.get_loc(entry_ts))
        if isinstance(pos, slice):
            pos = pos.start
    target = pos + horizon
    if target >= len(df):
        return None
    row = df.iloc[target]
    px = row.get("close")
    if px is None or pd.isna(px) or float(px) <= 0:
        return None
    return df.index[target], float(px)


def _series_jumps_at_split(df: pd.DataFrame, ex_date: str, ratio: float) -> bool:
    """True if unadjusted prices jump near 1/ratio at ex_date (need neutralization)."""
    if not ratio or ratio <= 0 or ratio >= 1:
        return False
    ex_ts = pd.Timestamp(ex_date)
    if ex_ts not in df.index:
        # nearest on/after
        sub = df[df.index >= ex_ts]
        if sub.empty:
            return False
        ex_ts = sub.index[0]
    pre = df[df.index < ex_ts]
    if pre.empty:
        return False
    pre_px = float(pre.iloc[-1]["close"])
    ex_px = float(df.loc[ex_ts, "close"])
    if pre_px <= 0 or ex_px <= 0:
        return False
    observed = ex_px / pre_px
    expected = 1.0 / ratio  # e.g. 10 for 1-for-10
    # Allow wide band — OTC gaps — but must be clearly a split-sized jump
    return observed > max(1.8, expected * 0.4)


def short_return(entry: float, exit_px: float) -> float:
    # short PnL / entry notional
    return (entry - exit_px) / entry


def fee_drag(fee_annual: float, hold_days: int) -> float:
    return fee_annual * (hold_days / 365.0)


def run_backtest(cfg: Config | None = None, label: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    bt = cfg.section("backtest")
    horizons = [int(x) for x in bt.get("horizons_days", [1, 5, 10, 20])]
    fees = [float(x) for x in bt.get("fee_scenarios_annual", [0.0, 0.2, 0.5, 1.0])]
    target_notional = float(bt.get("default_notional_per_trade", 5000))
    max_part = float(bt.get("max_participation", 0.25))
    max_book = float(bt.get("max_book_usd", 50000))

    config = {
        "horizons": horizons,
        "fees": fees,
        "target_notional": target_notional,
        "max_participation": max_part,
        "max_book_usd": max_book,
        "note": "Returns use daily close. If Yahoo series already continuous across the split, no ratio neutralization; if raw jump detected, exits/entries after ex are scaled by ratio.",
    }
    cur = conn.execute(
        "INSERT INTO backtest_runs (label, config_json) VALUES (?, ?)",
        (label or f"run_{datetime.utcnow().isoformat(timespec='seconds')}", json.dumps(config)),
    )
    run_id = int(cur.lastrowid)

    events = conn.execute("SELECT * FROM reverse_splits ORDER BY ex_date").fetchall()
    trades = 0
    for ev in events:
        df = _price_frame(conn, ev["ticker"])
        if df.empty:
            continue
        borrow = latest_borrow(conn, ev["ticker"])
        shortable = float(borrow["shortable_shares"]) if borrow and borrow["shortable_shares"] is not None else None
        ratio = float(ev["ratio"]) if ev["ratio"] else None
        jumps = _series_jumps_at_split(df, ev["ex_date"], ratio) if ratio else False

        for signal in ENTRY_SIGNALS:
            sig_d = _signal_date(ev, signal)
            if not sig_d:
                continue
            if signal == "day_before_ex":
                entry = _on_or_before(df, sig_d, "close")
                if entry and entry[0] >= pd.Timestamp(ev["ex_date"]):
                    entry = None
            else:
                entry = _on_or_after(df, sig_d, "close")
            if not entry:
                continue
            entry_ts, entry_px = entry
            if signal in {"first_proxy", "announce", "vote", "ratio_set", "day_before_ex"}:
                if entry_ts >= pd.Timestamp(ev["ex_date"]):
                    continue
            finra = nearest_short_interest(conn, ev["ticker"], entry_ts.date().isoformat())
            si = float(finra["short_interest"]) if finra and finra["short_interest"] is not None else None
            adv = float(finra["avg_daily_volume"]) if finra and finra["avg_daily_volume"] is not None else None
            shares, cap_src, truncated = position_cap_shares(
                entry_px, target_notional, shortable, max_part, si, adv
            )
            if shares <= 0:
                continue
            notional = shares * entry_px
            if notional > max_book:
                shares = max_book / entry_px
                notional = max_book
                truncated = 1
                cap_src = cap_src + "+book_cap"

            for horizon in horizons:
                exit_ = _horizon_exit(df, entry_ts, horizon)
                if not exit_:
                    continue
                exit_ts, exit_px = exit_
                ex_ts = pd.Timestamp(ev["ex_date"])
                entry_cmp = entry_px
                exit_cmp = exit_px
                if jumps and ratio and ratio > 0:
                    if entry_ts >= ex_ts:
                        entry_cmp = entry_px * ratio
                    if exit_ts >= ex_ts:
                        exit_cmp = exit_px * ratio
                gross = short_return(entry_cmp, exit_cmp)

                hold_days = max(1, (exit_ts.date() - entry_ts.date()).days)
                for fee in fees:
                    net = gross - fee_drag(fee, hold_days)
                    conn.execute(
                        """
                        INSERT INTO backtest_trades (
                            run_id, event_id, entry_signal, entry_date, exit_date, horizon_days,
                            entry_price, exit_price, shares, notional, gross_return, fee_scenario,
                            net_return, capacity_source, short_interest, shortable_shares, truncated,
                            cohort, exchange_class
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            ev["id"],
                            signal,
                            entry_ts.date().isoformat(),
                            exit_ts.date().isoformat(),
                            horizon,
                            entry_px,
                            exit_px,
                            shares,
                            notional,
                            gross,
                            fee,
                            net,
                            cap_src,
                            si,
                            shortable,
                            truncated,
                            ev["cohort"],
                            ev["exchange_class"],
                        ),
                    )
                    trades += 1
        conn.commit()

    conn.commit()
    conn.close()
    return {"run_id": run_id, "trades": trades, "config": config}


if __name__ == "__main__":
    print(run_backtest())
