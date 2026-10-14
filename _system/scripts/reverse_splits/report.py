"""Timing reports by entry signal, cohort, and exchange class."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import Config, load_config
from .db import init_db


def _latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def load_trades(cfg: Config | None = None, run_id: int | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    rid = run_id or _latest_run_id(conn)
    if rid is None:
        conn.close()
        return pd.DataFrame()
    df = pd.read_sql_query(
        "SELECT * FROM backtest_trades WHERE run_id=?",
        conn,
        params=(rid,),
    )
    conn.close()
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    gcols = ["entry_signal", "horizon_days", "fee_scenario", "cohort", "exchange_class"]
    agg = (
        df.groupby(gcols, dropna=False)
        .agg(
            n=("net_return", "count"),
            mean_gross=("gross_return", "mean"),
            median_gross=("gross_return", "median"),
            mean_net=("net_return", "mean"),
            median_net=("net_return", "median"),
            hit_rate=("net_return", lambda s: float((s > 0).mean())),
            mean_notional=("notional", "mean"),
            pct_truncated=("truncated", "mean"),
        )
        .reset_index()
        .sort_values(["fee_scenario", "horizon_days", "mean_net"], ascending=[True, True, False])
    )
    return agg


def best_entries(df: pd.DataFrame, fee: float = 0.0, horizon: int = 5) -> pd.DataFrame:
    if df.empty:
        return df
    sub = df[(df["fee_scenario"] == fee) & (df["horizon_days"] == horizon)]
    if sub.empty:
        return sub
    return (
        sub.groupby(["entry_signal", "cohort", "exchange_class"], dropna=False)
        .agg(
            n=("net_return", "count"),
            mean_net=("net_return", "mean"),
            median_net=("net_return", "median"),
            hit_rate=("net_return", lambda s: float((s > 0).mean())),
        )
        .reset_index()
        .sort_values("mean_net", ascending=False)
    )


def write_reports(cfg: Config | None = None, run_id: int | None = None) -> dict[str, Path]:
    cfg = cfg or load_config()
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    df = load_trades(cfg, run_id)
    paths: dict[str, Path] = {}
    if df.empty:
        empty = cfg.reports_dir / "NO_TRADES.txt"
        empty.write_text("No backtest trades found. Run: python -m _system.scripts.reverse_splits.cli book\n", encoding="utf-8")
        return {"note": empty}

    summary = summarize(df)
    p1 = cfg.reports_dir / "timing_summary.csv"
    summary.to_csv(p1, index=False)
    paths["timing_summary"] = p1

    # Headline: fee=0, horizon=5
    best = best_entries(df, fee=0.0, horizon=5)
    p2 = cfg.reports_dir / "best_entries_h5_fee0.csv"
    best.to_csv(p2, index=False)
    paths["best_entries"] = p2

    # Second+ reverse splits only
    second = best_entries(df[df["cohort"].isin(["second", "third_plus"])], fee=0.0, horizon=5)
    p3 = cfg.reports_dir / "repeat_rs_best_entries_h5_fee0.csv"
    second.to_csv(p3, index=False)
    paths["repeat_rs"] = p3

    # Fee sensitivity at best signal overall
    if not best.empty:
        top_signal = best.iloc[0]["entry_signal"]
        sens = (
            df[(df["entry_signal"] == top_signal) & (df["horizon_days"] == 5)]
            .groupby("fee_scenario")
            .agg(n=("net_return", "count"), mean_net=("net_return", "mean"), hit_rate=("net_return", lambda s: float((s > 0).mean())))
            .reset_index()
        )
        p4 = cfg.reports_dir / f"fee_sensitivity_{top_signal}_h5.csv"
        sens.to_csv(p4, index=False)
        paths["fee_sensitivity"] = p4

    # Markdown digest
    md = cfg.reports_dir / "timing_report.md"
    lines = [
        "# Reverse Split Short Timing Report",
        "",
        f"Trades: {len(df):,}",
        "",
        "## Best entries (horizon=5d, fee=0)",
        "",
        best.head(20).to_markdown(index=False) if not best.empty else "_no data_",
        "",
        "## Repeat reverse splits (second+)",
        "",
        second.head(20).to_markdown(index=False) if not second.empty else "_no data_",
        "",
        "## Notes",
        "",
        "- Gross/net returns are for short positions using continuous (split-neutralized) closes.",
        "- Capacity: IBKR shortable shares if snapped; else FINRA short interest proxy; else ADV proxy.",
        "- FINRA SI is **not** a locate — treat historical capacity as approximate.",
        "- Listed vs OTC and first vs second+ cohorts are split in the CSVs.",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    paths["markdown"] = md
    return paths


def event_coverage(cfg: Config | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    df = pd.read_sql_query(
        """
        SELECT
            COUNT(*) AS events,
            SUM(CASE WHEN first_proxy_date IS NOT NULL THEN 1 ELSE 0 END) AS with_proxy,
            SUM(CASE WHEN announce_date IS NOT NULL THEN 1 ELSE 0 END) AS with_announce,
            SUM(CASE WHEN vote_date IS NOT NULL THEN 1 ELSE 0 END) AS with_vote,
            SUM(CASE WHEN cohort = 'first' THEN 1 ELSE 0 END) AS first_rs,
            SUM(CASE WHEN cohort = 'second' THEN 1 ELSE 0 END) AS second_rs,
            SUM(CASE WHEN cohort = 'third_plus' THEN 1 ELSE 0 END) AS third_plus,
            SUM(CASE WHEN exchange_class = 'listed' THEN 1 ELSE 0 END) AS listed,
            SUM(CASE WHEN exchange_class = 'otc' THEN 1 ELSE 0 END) AS otc
        FROM reverse_splits
        """,
        conn,
    )
    conn.close()
    return df


if __name__ == "__main__":
    paths = write_reports()
    print(paths)
    print(event_coverage())
