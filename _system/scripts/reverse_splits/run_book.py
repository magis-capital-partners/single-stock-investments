"""Load the SQLite universe and run the shared book."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from .adjust import PriceFrame
from .book import (
    SIGNALS,
    Candidate,
    Settings,
    build_candidates,
    max_drawdown,
    monthly_pnl,
    simulate,
    summarize_unconstrained,
)
from .config import Config, load_config
from .controls import attach_matches
from .db import init_db


def settings_from_config(cfg: Config, **overrides) -> Settings:
    execution = cfg.section("execution")
    backtest = cfg.section("backtest")
    values = dict(
        signal=str(execution.get("entry_signal", "announce")),
        horizon=int(execution.get("horizon_days", 5)),
        min_price=float(execution.get("min_price", 1.0)),
        spread_floor=float(execution.get("spread_floor_usd", 0.01)),
        spread_range_fraction=float(execution.get("spread_range_fraction", 0.25)),
        force_cover=bool(execution.get("force_cover_before_ex", True)),
        max_book=float(execution.get("max_book_usd", backtest.get("max_book_usd", 50000))),
        max_names=int(execution.get("max_names", 10)),
        target_notional=float(backtest.get("default_notional_per_trade", 5000)),
        max_participation=float(backtest.get("max_participation", 0.25)),
        fee_annual=float(execution.get("assumed_fee_annual", 1.0)),
        borrow_policy=str(execution.get("borrow_policy", "assumed_fee")),
        listed_only=bool(execution.get("listed_only", True)),
        require_filing_text=bool(execution.get("require_filing_text", False)),
        jump_window=int(execution.get("jump_window_sessions", 3)),
        cohorts=None,
        outcomes=None,
    )
    values.update(overrides)
    for key in ("cohorts", "outcomes"):
        raw = values.get(key)
        if isinstance(raw, str):
            values[key] = None if raw in {"", "all"} else (raw,)
        elif isinstance(raw, list):
            values[key] = tuple(raw) or None
        elif raw == []:
            values[key] = None
    return Settings(**values)


def load_events(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.*, i.name AS issuer_name
        FROM reverse_splits s
        LEFT JOIN issuers i ON i.cik = s.cik
        ORDER BY s.ex_date, s.ticker
        """
    ).fetchall()
    evidence = {}
    for hit in conn.execute("SELECT cik,filed_at,accession FROM edgar_hits ORDER BY substantive, text_parsed"):
        evidence[(hit["cik"], str(hit["filed_at"] or "")[:10])] = hit["accession"]
    events = []
    for row in rows:
        item = dict(row)
        item["name"] = item.get("issuer_name") or item.get("ticker")
        acc = evidence.get((item.get("cik"), str(item.get("announce_date") or "")[:10]))
        if acc and item.get("cik"):
            item["accession"] = acc
            item["source_url"] = f"https://www.sec.gov/Archives/edgar/data/{int(item['cik'])}/{acc.replace('-', '')}/"
        events.append(item)
    return events


def load_frames(conn, table: str = "prices_daily") -> dict[str, PriceFrame]:
    buckets: dict[str, list] = defaultdict(list)
    for row in conn.execute(
        f"SELECT ticker, date, open, high, low, close, volume FROM {table} ORDER BY ticker, date"
    ):
        close = row["close"]
        if close is None:
            continue
        buckets[row["ticker"]].append(row)
    frames = {}
    for ticker, rows in buckets.items():
        frames[ticker] = PriceFrame(
            dates=[r["date"] for r in rows],
            open=[float(r["open"] if r["open"] is not None else r["close"]) for r in rows],
            high=[float(r["high"] if r["high"] is not None else r["close"]) for r in rows],
            low=[float(r["low"] if r["low"] is not None else r["close"]) for r in rows],
            close=[float(r["close"]) for r in rows],
            volume=[float(r["volume"] or 0) for r in rows],
        )
    return frames


def load_borrows(conn) -> dict[str, list[tuple[str, float | None, float | None]]]:
    out: dict[str, list[tuple[str, float | None, float | None]]] = defaultdict(list)
    for row in conn.execute("SELECT ticker, asof_ts, shortable_shares,fee_rate FROM borrow_snapshots"):
        out[row["ticker"]].append((row["asof_ts"], row["shortable_shares"], row["fee_rate"]))
    return out


def load_splits(events: list[dict]) -> dict[str, list[tuple[str, float]]]:
    splits: dict[str, list[tuple[str, float]]] = defaultdict(list)
    seen = set()
    for event in events:
        if (event.get("outcome") or "effective") != "effective":
            continue
        ratio = float(event.get("ratio") or 0)
        ex = (event.get("ex_date") or "")[:10]
        ticker = event.get("ticker") or ""
        if not ticker or not ex or ratio <= 0 or ratio >= 1:
            continue
        key = (ticker, ex)
        if key in seen:
            continue
        seen.add(key)
        splits[ticker].append((ex, ratio))
    return splits


def _trade_payload(trade: Candidate) -> dict:
    notional = trade.shares * trade.entry_fill
    excess = None
    if trade.peer_return is not None:
        excess = trade.net_return - trade.peer_return
    return {
        "event_id": trade.event_id,
        "ticker": trade.ticker,
        "name": trade.name,
        "cohort": trade.cohort,
        "outcome": trade.outcome,
        "signal": trade.signal,
        "entry_date": trade.entry_date,
        "exit_date": trade.exit_date,
        "entry_fill": round(trade.entry_fill, 4),
        "exit_fill": round(trade.exit_fill, 4),
        "shares": round(trade.shares, 2),
        "notional": round(notional, 2),
        "net_pnl": round(trade.net_pnl, 2),
        "net_return": trade.net_return,
        "forced_cover": trade.forced_cover,
        "jump_status": trade.jump_status,
        "hold_days": trade.hold_days,
        "exit_breach": trade.exit_breach,
        "peer_ticker": trade.peer_ticker,
        "peer_return": trade.peer_return,
        "control_ticker": trade.control_ticker,
        "control_return": trade.control_return,
        "excess_vs_peer": excess,
        "date_quality": trade.date_quality,
        "gross_pnl": trade.gross_pnl,
        "fee_pnl": trade.fee_pnl,
    }


def _stats(trades: list[Candidate], equity: list[dict], fee_annual: float) -> dict:
    rets = [t.net_return for t in trades]
    pnls = [t.net_pnl for t in trades]
    peers = [t.net_return - t.peer_return for t in trades if t.peer_return is not None]
    controls = [t.net_return - t.control_return for t in trades if t.control_return is not None]
    ordered = sorted(rets)
    if not ordered:
        median = 0.0
    elif len(ordered) % 2:
        median = ordered[len(ordered) // 2]
    else:
        median = 0.5 * (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2])
    final = float(equity[-1]["equity"]) if equity else None
    return {
        "taken": len(trades),
        "dollar_pnl": sum(pnls),
        "hit_rate": (sum(1 for value in rets if value > 0) / len(rets)) if rets else 0.0,
        "median_return": median,
        "mean_return": (sum(rets) / len(rets)) if rets else 0.0,
        "final_equity": final,
        "max_drawdown": max_drawdown(equity),
        "avg_notional": (sum(t.shares * t.entry_fill for t in trades) / len(trades)) if trades else 0.0,
        "forced_cover": sum(1 for t in trades if t.forced_cover),
        "exit_breach": sum(1 for t in trades if t.exit_breach),
        "peer_matches": len(peers),
        "mean_excess_vs_peer": (sum(peers) / len(peers)) if peers else None,
        "control_matches": len(controls),
        "mean_excess_vs_control": (sum(controls) / len(controls)) if controls else None,
        "fee_annual": fee_annual,
    }


def _book_dict(label: str, settings: Settings, taken, skipped, equity, funnel) -> dict:
    merged = dict(funnel)
    merged.update(skipped)
    merged["taken"] = len(taken)
    assumptions = {
        "signal": settings.signal,
        "horizon_days": settings.horizon,
        "min_price": settings.min_price,
        "spread_floor_usd": settings.spread_floor,
        "spread_range_fraction": settings.spread_range_fraction,
        "force_cover_before_ex": settings.force_cover,
        "max_book_usd": settings.max_book,
        "max_names": settings.max_names,
        "target_notional": settings.target_notional,
        "max_participation": settings.max_participation,
        "fee_annual": settings.fee_annual if settings.borrow_policy == "assumed_fee" else None,
        "borrow_policy": settings.borrow_policy,
        "listed_only": settings.listed_only,
        "require_filing_text": settings.require_filing_text,
        "cohorts": list(settings.cohorts) if settings.cohorts else None,
        "outcomes": list(settings.outcomes) if settings.outcomes else None,
    }
    return {
        "id": label,
        "label": label,
        "assumptions": assumptions,
        "funnel": [{"stage": key, "n": merged[key]} for key in
                   [k for k in _funnel_order() if k != "taken"] +
                   [k for k in merged if k not in _funnel_order()] + ["taken"] if key in merged],
        "stats": _stats(taken, equity, settings.fee_annual if settings.borrow_policy == "assumed_fee" else 0.0),
        "equity": equity,
        "monthly": monthly_pnl(taken),
        "trades": [_trade_payload(trade) for trade in taken],
    }


def _funnel_order() -> list[str]:
    return [
        "events",
        "mention",
        "not_listed",
        "cohort",
        "outcome",
        "no_filing_text",
        "no_prices",
        "no_signal_date",
        "no_entry_bar",
        "ambiguous_print",
        "no_exit_bar",
        "below_min_price",
        "bad_fill",
        "thin_history",
        "no_locate",
        "participation",
        "taken_pool",
        "already_open",
        "max_names",
        "cash",
        "taken",
    ]


def universe_counts(conn) -> dict:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS events,
            SUM(CASE WHEN COALESCE(outcome, 'effective') = 'effective' THEN 1 ELSE 0 END) AS effective,
            SUM(CASE WHEN outcome = 'announced_only' THEN 1 ELSE 0 END) AS announced_only,
            SUM(CASE WHEN outcome = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
            SUM(CASE WHEN outcome = 'mention' THEN 1 ELSE 0 END) AS mention,
            SUM(CASE WHEN exchange_class = 'listed' THEN 1 ELSE 0 END) AS listed,
            SUM(CASE WHEN exchange_class = 'otc' THEN 1 ELSE 0 END) AS otc,
            SUM(CASE WHEN date_quality = 'filing_text' THEN 1 ELSE 0 END) AS filing_text,
            SUM(CASE WHEN date_quality = 'acceptance_time' THEN 1 ELSE 0 END) AS acceptance_time,
            SUM(CASE WHEN jump_status = 'ambiguous' THEN 1 ELSE 0 END) AS ambiguous_stored
        FROM reverse_splits
        """
    ).fetchone()
    return {key: row[key] or 0 for key in row.keys()}


def run_snapshot(cfg: Config | None = None, grid: bool = True, **overrides) -> dict:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    events = load_events(conn)
    frames = load_frames(conn)
    borrows = load_borrows(conn)
    control_frames = load_frames(conn, "control_prices")
    hits = [dict(row) for row in conn.execute("SELECT * FROM edgar_hits")]
    conn.close()
    splits = load_splits(events)
    base = settings_from_config(cfg, **overrides)
    controls_cfg = cfg.section("controls")
    price_caliper = float(controls_cfg.get("price_caliper", 1.5))
    volume_caliper = float(controls_cfg.get("volume_caliper", 3.0))

    signal_outcomes = base.outcomes if "outcomes" in overrides else ("effective",)
    signals = []
    for signal in SIGNALS:
        signal_settings = settings_from_config(
            cfg,
            signal=signal,
            horizon=base.horizon,
            fee_annual=base.fee_annual,
            borrow_policy="assumed_fee",
            listed_only=base.listed_only,
            min_price=base.min_price,
            force_cover=base.force_cover,
            require_filing_text=base.require_filing_text,
            outcomes=signal_outcomes,
        )
        eligible, _funnel = build_candidates(events, frames, signal_settings, borrows)
        summary = summarize_unconstrained(eligible, signal_settings.fee_annual)
        summary["signal"] = signal
        signals.append(summary)

    if grid and not overrides:
        specs = [
            ("strict", settings_from_config(cfg, borrow_policy="strict", fee_annual=0.0, signal=base.signal, horizon=base.horizon, outcomes=("effective",))),
            ("assumed_100_h5_effective", settings_from_config(cfg, borrow_policy="assumed_fee", fee_annual=1.0, signal=base.signal, horizon=5, outcomes=("effective",))),
            ("assumed_300_h5_effective", settings_from_config(cfg, borrow_policy="assumed_fee", fee_annual=3.0, signal=base.signal, horizon=5, outcomes=("effective",))),
            ("assumed_100_h20_effective", settings_from_config(cfg, borrow_policy="assumed_fee", fee_annual=1.0, signal=base.signal, horizon=20, outcomes=("effective",))),
            ("assumed_100_h5_all_hits", settings_from_config(cfg, borrow_policy="assumed_fee", fee_annual=1.0, signal=base.signal, horizon=5)),
        ]
    else:
        label = "custom" if overrides else "assumed_100_h5"
        specs = [(label, base)]

    books = []
    candidates_by_book = {}
    for label, settings in specs:
        eligible, funnel = build_candidates(events, frames, settings, borrows)
        fee = settings.fee_annual if settings.borrow_policy == "assumed_fee" else 0.0
        taken, skipped, equity = simulate(eligible, settings.max_book, settings.max_names, fee)
        if label != "strict":
            attach_matches(
                taken,
                frames,
                frames,
                splits,
                window=settings.jump_window,
                spread_floor=settings.spread_floor,
                range_fraction=settings.spread_range_fraction,
                fee_annual=fee,
                price_caliper=price_caliper,
                volume_caliper=volume_caliper,
                field="peer_ticker",
            )
            if control_frames:
                attach_matches(
                    taken,
                    frames,
                    control_frames,
                    splits,
                    window=settings.jump_window,
                    spread_floor=settings.spread_floor,
                    range_fraction=settings.spread_range_fraction,
                    fee_annual=fee,
                    price_caliper=price_caliper,
                    volume_caliper=volume_caliper,
                    field="control_ticker",
                    pool_splits={},
                )
        candidates_by_book[label] = taken
        books.append(_book_dict(label, settings, taken, skipped, equity, funnel))

    conn = init_db(cfg.db_path)
    counts = universe_counts(conn)
    conn.close()
    snapshot = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": counts,
        "signals": signals,
        "books": books,
        "defaults": {
            "signal": base.signal,
            "horizon_days": base.horizon,
            "min_price": base.min_price,
            "fee_annual": base.fee_annual,
            "borrow_policy": base.borrow_policy,
            "max_names": base.max_names,
            "max_book_usd": base.max_book,
            "target_notional": base.target_notional,
        },
        "notes": [
            "Prices are nominal printed dollars. A continuous Yahoo series is scaled back by the split ratio before the ex-date.",
            "Entry is the first 9:30 ET open after the EDGAR accept time. A filing date with no clock waits until the next session.",
            "A hold that would cross the ex-date is covered at the prior close. The share count is not left on through the corporate action.",
            "The spread is the greater of one cent and 25% of the prior session's high-low range.",
            "Names with a nominal open under the price floor are not shorted. Size is the smaller of the target dollars and 25% of the prior 20-session average volume.",
            "FINRA short interest is not treated as shares that can be sold.",
            "strict drops every name without a locate snapshot dated on or before entry. assumed_fee is a labeled scenario, not a borrow.",
            "The book is one cash account. Same-day names are taken in ticker order until cash or the name cap runs out.",
            "The peer is another listed name in this file, matched on the prior day's price and dollar volume, and it is not inside its own split. The control sample is random listed names with no reverse split in this database.",
            "The signal table and the books named effective use completed splits only. The all-hits book also keeps phrase matches that never became a split.",
            "Unconstrained signal rows ignore the shared account. They are not the book.",
        ],
    }
    from .analysis import extend_snapshot
    return extend_snapshot(cfg, snapshot, events, frames, borrows, candidates_by_book, hits)


def persist_snapshot(cfg: Config, snapshot: dict) -> None:
    conn = init_db(cfg.db_path)
    for book in snapshot["books"] + snapshot.get("realism", {}).get("books", []):
        cur = conn.execute(
            "INSERT INTO book_runs (label, config_json,analysis_json,source_manifest_json) VALUES (?, ?, ?, ?)",
            (book["id"], json.dumps(book["assumptions"]), json.dumps(book.get("analysis")),
             json.dumps(snapshot.get("provenance"))),
        )
        run_id = int(cur.lastrowid)
        for stage in book["funnel"]:
            conn.execute(
                "INSERT INTO book_funnel (run_id, stage, n) VALUES (?, ?, ?)",
                (run_id, stage["stage"], stage["n"]),
            )
        for row in book["equity"]:
            conn.execute(
                "INSERT INTO book_equity (run_id, date, equity, cash, open_names,margin_required,gross_exposure,margin_breach) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, row["date"], row["equity"], row["cash"], row["open_names"],
                 row.get("margin_required"), row.get("gross_exposure"), row.get("margin_breach")),
            )
        for trade in book["trades"]:
            conn.execute(
                """
                INSERT INTO book_trades (
                    run_id, event_id, ticker, name, cohort, outcome, signal,
                    entry_date, exit_date, entry_fill, exit_fill, shares, notional,
                    net_pnl, net_return, forced_cover, jump_status, hold_days,
                    exit_breach, borrow_policy, fee_annual, peer_ticker, peer_return,
                    control_ticker, control_return, date_quality, gross_pnl, fee_pnl, adv_shares, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trade["event_id"],
                    trade["ticker"],
                    trade["name"],
                    trade["cohort"],
                    trade["outcome"],
                    trade["signal"],
                    trade["entry_date"],
                    trade["exit_date"],
                    trade["entry_fill"],
                    trade["exit_fill"],
                    trade["shares"],
                    trade["notional"],
                    trade["net_pnl"],
                    trade["net_return"],
                    int(trade["forced_cover"]),
                    trade["jump_status"],
                    trade["hold_days"],
                    int(trade["exit_breach"]),
                    book["assumptions"]["borrow_policy"],
                    book["assumptions"]["fee_annual"],
                    trade["peer_ticker"],
                    trade["peer_return"],
                    trade["control_ticker"],
                    trade["control_return"],
                    trade["date_quality"],
                    trade.get("gross_pnl"),
                    trade.get("fee_pnl"),
                    trade.get("adv_shares"),
                    json.dumps(trade),
                ),
            )
    conn.commit()
    conn.close()


def write_book_report(cfg: Config, snapshot: dict) -> str:
    path = cfg.reports_dir / "book_report.md"
    lines = [
        "# Realistic reverse-split book",
        "",
        f"Built {snapshot['built_at']}.",
        "",
        "Dollar P&L is the shared account. Signal rows further down ignore that account.",
        "",
    ]
    universe = snapshot["universe"]
    lines.append(
        f"Events: {universe.get('events', 0)} "
        f"(effective {universe.get('effective', 0)}, "
        f"announced only {universe.get('announced_only', 0)}, "
        f"cancelled {universe.get('cancelled', 0)}, "
        f"mentions set aside {universe.get('mention', 0)}). "
        f"Filing-text dates: {universe.get('filing_text', 0)}."
    )
    lines.append("")
    for book in snapshot["books"]:
        stats = book["stats"]
        lines.append(f"## {book['id']}")
        lines.append("")
        lines.append(
            f"Trades {stats['taken']}. "
            f"P&L ${stats['dollar_pnl']:,.0f}. "
            f"Median {stats['median_return'] * 100:.1f}%. "
            f"Hit {stats['hit_rate'] * 100:.0f}%. "
            f"Max drawdown {stats['max_drawdown'] * 100:.1f}%."
        )
        if stats.get("mean_excess_vs_peer") is not None:
            lines.append(
                f"Peer matches {stats['peer_matches']}. "
                f"Mean excess vs peer {stats['mean_excess_vs_peer'] * 100:.1f}%."
            )
        if stats.get("mean_excess_vs_control") is not None:
            lines.append(
                f"Random-listed matches {stats['control_matches']}. "
                f"Mean excess vs control {stats['mean_excess_vs_control'] * 100:.1f}%."
            )
        lines.append("")
        lines.append("| Stage | N |")
        lines.append("|---|---:|")
        for stage in book["funnel"]:
            lines.append(f"| {stage['stage']} | {stage['n']} |")
        lines.append("")
    lines.append("## Unconstrained listed signals")
    lines.append("")
    lines.append("Same gates and fee as the default assumed book. No shared cash, so names overlap.")
    lines.append("")
    lines.append("| Signal | N | Median | Mean | Hit | Dollar P&L |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in snapshot["signals"]:
        lines.append(
            f"| {row['signal']} | {row['n']} | {row['median_return'] * 100:.1f}% | "
            f"{row['mean_return'] * 100:.1f}% | {row['hit_rate'] * 100:.0f}% | ${row['dollar_pnl']:,.0f} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
