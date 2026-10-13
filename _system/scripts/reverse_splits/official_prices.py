"""Official venue auction benchmarks; raw statistics remain licensed/local.

Databento's UTC-day OHLCV is not a regular-session open/close. Statistics
types 1 and 11 are official prices. Zero/sentinel prices and deleted updates
are unavailable. Symbol intervals come from dataset-wide instrument IDs.
Reference: https://databento.com/docs/schemas-and-data-formats/statistics
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date

from .databento_bars import DATASETS, DEFINITION_DATASET, is_complete
from .split_detector import normalize_symbol


def listing_snapshots(cfg, wanted):
    import databento as db

    snapshots = defaultdict(list)
    for path in sorted(
        (cfg.databento_dir / DEFINITION_DATASET / "definition").glob("*.dbn.zst")
    ):
        if not is_complete(path) or path.stat().st_size == 0:
            continue
        day = date.fromisoformat(path.name.split(".")[0])
        frame = db.DBNStore.from_file(str(path)).to_df(map_symbols=False)
        for symbol, kind, venue in frame[
            ["raw_symbol", "security_type", "exchange"]
        ].itertuples(index=False, name=None):
            norm = normalize_symbol(symbol)
            if norm in wanted:
                snapshots[norm].append((day, str(kind), str(venue)))
    return snapshots


def load_official(cfg, windows, *, log=print):
    import bisect
    import databento as db
    import numpy as np
    import pandas as pd

    by_norm = defaultdict(list)
    for w in windows:
        by_norm[w["norm"]].append(w)
    snapshots = listing_snapshots(cfg, set(by_norm))

    def primary(norm, day):
        rows = snapshots.get(norm, [])
        ix = bisect.bisect_right([r[0] for r in rows], day) - 1
        return rows[ix][2] if ix >= 0 else None

    observations = {}
    files = []
    for dataset in DATASETS:
        for path in sorted(
            (cfg.databento_dir / dataset / "statistics").glob("*.dbn.zst")
        ):
            mapping = path.with_name(path.name.replace(".dbn.zst", ".symbology.json"))
            if not is_complete(path) or not mapping.exists():
                continue
            spans = json.loads(mapping.read_text(encoding="utf-8"))
            wanted = {
                int(i): [
                    (
                        date.fromisoformat(v["d0"]),
                        date.fromisoformat(v["d1"]),
                        normalize_symbol(v["s"]),
                    )
                    for v in ivs
                    if normalize_symbol(v["s"]) in by_norm
                ]
                for i, ivs in spans.items()
            }
            wanted = {i: ivs for i, ivs in wanted.items() if ivs}
            if not wanted:
                continue
            arr = db.DBNStore.from_file(str(path)).to_ndarray()
            arr = arr[
                np.isin(arr["instrument_id"], list(wanted))
                & np.isin(arr["stat_type"], [1, 11])
            ]
            # Statistics reference a market session. If the venue supplies no
            # reference time, use its event time in New York, not UTC midnight.
            ts = np.where(
                (arr["ts_ref"] > 0) & (arr["ts_ref"] < np.iinfo(np.uint64).max),
                arr["ts_ref"],
                arr["ts_event"],
            )
            days = (
                pd.to_datetime(ts, unit="ns", utc=True)
                .tz_convert("America/New_York")
                .date
            )
            for iid, day, kind, price, action in zip(
                arr["instrument_id"],
                days,
                arr["stat_type"],
                arr["price"],
                arr["update_action"],
            ):
                for d0, d1, norm in wanted[int(iid)]:
                    if (
                        not d0 <= day < d1
                        or primary(norm, day) != dataset.split(".")[0]
                    ):
                        continue
                    px = float(price) / 1e9
                    value = px if int(action) != 2 and 0 < px < 1e8 else None
                    for w in by_norm[norm]:
                        if w["lo"] <= day <= w["hi"]:
                            observations[w["ticker"], day.isoformat(), int(kind)] = (
                                value,
                                dataset,
                                norm,
                            )
            files.append(str(path.relative_to(cfg.databento_dir)))
            log(
                f"official {dataset} {path.stem.split('.')[0]}: {len(observations):,} observations"
            )
    conn = sqlite3.connect(cfg.db_path, timeout=30)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS official_auction_prices (ticker TEXT,date TEXT,point TEXT,price REAL,dataset TEXT,symbol TEXT,PRIMARY KEY(ticker,date,point))"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO official_auction_prices VALUES (?,?,?,?,?,?)",
            [
                (t, d, "open" if k == 1 else "close", v, source, symbol)
                for (t, d, k), (v, source, symbol) in observations.items()
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "files": len(files),
        "observations": len(observations),
        "valid_prices": sum(v[0] is not None for v in observations.values()),
        "basis": "official_listing_venue_auction",
        "missing_auctions_remain_unavailable": True,
    }
