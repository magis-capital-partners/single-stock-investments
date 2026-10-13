"""Printed Databento bars and Reg SHO 201 state for the ledger's listed events.

``load_prices`` fills ``prices_daily`` for every listed effective event over the
window ``ingest_prices`` uses (ex date -120 to +60 calendar days). For each
(ticker, day), OHLC comes from the venue with the most volume among XNAS, XNYS
and XASE; for a small cap that is usually its listing market, whose auctions
print the official open and close. Volume is the sum over those three venues.
That still falls short of consolidated volume, which also trades on other
exchanges and off-exchange, so participation caps built on it err tight. Bars
are printed, so ``adjust.classify_split`` sees the split jump and leaves the
series alone. Rows replace any yfinance rows for the same (ticker, date).

``load_ssr`` fills ``ssr_flags`` with every (ticker, day) restricted at the open:
the last explicit Y/N in Nasdaq's ``status`` feed at or before 09:30 ET. That
covers a restriction carried over from the prior session's trigger and its
lapse. Nasdaq disseminates the Rule 201 state for every NMS symbol, whatever
the listing market.

A ledger ticker maps to the symbol the venue files carried then: the rename
join first (``reports/rename_joins.json``), then the ticker in exchange
spelling (BRK-B is BRK.B). Raw Databento data never leaves ``local/``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .databento_bars import DATASETS, STATUS_DATASET, is_complete, quarters
from .split_detector import load_bars, normalize_symbol

PRE_DAYS, POST_DAYS = 120, 60
NEW_YORK = ZoneInfo("America/New_York")


def event_windows(events: list[dict], joins: list[dict]) -> list[dict]:
    """(db ticker, venue symbol, lo, hi) per listed effective event."""
    alias = {(j["ticker"], j["ex_date"]): j["filing_time_symbol"] for j in joins}
    out = []
    for event in events:
        if event.get("exchange_class") != "listed" or (event.get("outcome") or "effective") != "effective":
            continue
        ex = date.fromisoformat(str(event["ex_date"])[:10])
        symbol = alias.get((event["ticker"], ex.isoformat()), event["ticker"])
        out.append({"ticker": event["ticker"], "norm": normalize_symbol(symbol),
                    "lo": ex - timedelta(days=PRE_DAYS), "hi": ex + timedelta(days=POST_DAYS)})
    return out


def _quarter_files(cfg, dataset: str, schema: str, windows: list[dict]):
    lo, hi = min(w["lo"] for w in windows), max(w["hi"] for w in windows)
    for label, q_lo, q_hi in quarters(lo, hi + timedelta(days=1)):
        path = cfg.databento_dir / dataset / schema / f"{label}.dbn.zst"
        if is_complete(path) and path.with_name(path.name.replace(".dbn.zst", ".symbology.json")).exists():
            yield label, q_lo, q_hi, path


def load_prices(cfg, db_path, events: list[dict], joins: list[dict], log=print) -> dict:
    import pandas as pd

    from .db import init_db

    windows = event_windows(events, joins)
    if not windows:
        return {"events": 0, "bars": 0}
    win = pd.DataFrame(windows)
    parts = []
    for dataset in DATASETS:
        for label, q_lo, q_hi, path in _quarter_files(cfg, dataset, "ohlcv-1d", windows):
            active = win[(win["lo"] < q_hi) & (win["hi"] >= q_lo)]
            if active.empty:
                continue
            bars = load_bars(path)
            bars["norm"] = bars["symbol"].str.upper().str.replace(r"[.\s/]+", "-", regex=True)
            hit = bars.merge(active, on="norm")
            hit = hit[(hit["day"] >= hit["lo"]) & (hit["day"] <= hit["hi"])]
            hit = hit.drop_duplicates(["ticker", "day"])
            hit["dataset"] = dataset
            parts.append(hit[["ticker", "day", "open", "high", "low", "close", "volume", "dataset"]])
            log(f"prices {dataset} {label}: {len(hit):,} event bars")
    if not parts:
        return {"events": len(windows), "bars": 0}
    allbars = pd.concat(parts, ignore_index=True)
    best = allbars.loc[allbars.groupby(["ticker", "day"])["volume"].idxmax()].set_index(["ticker", "day"])
    best["volume"] = allbars.groupby(["ticker", "day"])["volume"].sum()
    conn = init_db(db_path)
    rows = [(t, d.isoformat(), float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume), float(r.close), float(r.close))
            for (t, d), r in best.iterrows()]
    conn.executemany("INSERT OR REPLACE INTO prices_daily (ticker, date, open, high, low, close, volume, adj_close, unadj_close) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    priced = {t for t, _ in best.index}
    conn.close()
    return {"events": len(windows), "tickers_priced": len(priced), "bars": len(rows)}


def open_states(messages: list[tuple[datetime, str]], days: list[date]) -> dict[date, bool]:
    """Restricted at the open of each day: the last explicit Y/N at or before
    09:30 New York time, carried forward from earlier days. Pure."""
    explicit = sorted((ts, flag) for ts, flag in messages if flag in ("Y", "N"))
    out, i, state = {}, 0, False
    for day in sorted(days):
        cutoff = datetime.combine(day, time(9, 30), NEW_YORK)
        while i < len(explicit) and explicit[i][0] <= cutoff:
            state = explicit[i][1] == "Y"
            i += 1
        out[day] = state
    return out


def load_ssr(cfg, db_path, events: list[dict], joins: list[dict], log=print) -> dict:
    import databento as db
    import numpy as np

    from .db import init_db

    windows = event_windows(events, joins)
    by_norm: dict[str, list[dict]] = {}
    for w in windows:
        by_norm.setdefault(w["norm"], []).append(w)
    flags = set()
    for label, q_lo, q_hi, path in _quarter_files(cfg, STATUS_DATASET, "status", windows):
        spans = json.loads(path.with_name(path.name.replace(".dbn.zst", ".symbology.json")).read_text(encoding="utf-8"))
        wanted = {}
        for iid, ivs in spans.items():
            for iv in ivs:
                norm = normalize_symbol(iv["s"])
                if norm in by_norm:
                    wanted.setdefault(int(iid), []).append((date.fromisoformat(iv["d0"]), date.fromisoformat(iv["d1"]), norm))
        if not wanted:
            continue
        arr = db.DBNStore.from_file(str(path)).to_ndarray()
        arr = arr[np.isin(arr["instrument_id"], np.fromiter(wanted, dtype=arr["instrument_id"].dtype))]
        per_symbol: dict[str, list[tuple[datetime, str]]] = {}
        for ts, iid, flag in zip(arr["ts_event"], arr["instrument_id"], arr["is_short_sell_restricted"]):
            when = datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc)
            flag = flag.decode() if isinstance(flag, bytes) else chr(flag) if isinstance(flag, (int, np.integer)) else str(flag)
            for d0, d1, norm in wanted[int(iid)]:
                if d0 <= when.astimezone(NEW_YORK).date() < d1:
                    per_symbol.setdefault(norm, []).append((when, flag))
        for norm, messages in per_symbol.items():
            for w in by_norm[norm]:
                days = [d for d in (q_lo + timedelta(days=i) for i in range((q_hi - q_lo).days)) if w["lo"] <= d <= w["hi"] and d.weekday() < 5]
                for day, restricted in open_states(messages, days).items():
                    if restricted:
                        flags.add((w["ticker"], day.isoformat()))
        log(f"ssr {label}: {len(flags):,} restricted (ticker, day) so far")
    conn = init_db(db_path)
    conn.executemany("INSERT OR REPLACE INTO ssr_flags (ticker, date, source) VALUES (?, ?, 'databento_status')", sorted(flags))
    conn.commit()
    conn.close()
    return {"restricted_days": len(flags)}
