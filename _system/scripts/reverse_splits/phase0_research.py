"""Phase 0 of the shorts alpha program: the SSR cohort (H1) and the generic
weak-microcap fade baseline (H7, H8), with expanded matched controls.

Research only. Inputs are the frozen expansion run (per-event ex+1 outcomes),
the local SQLite SSR states and the local Databento venue files (daily bars,
official auction statistics, definitions). Nothing here contacts a broker,
ThetaData or a data vendor, and no new licensed data is downloaded.

Published output (``phase0_research.json`` + ``phase0_manifest.json``) is
aggregate only and covers the train and validation splits. Everything for
entry dates on or after the holdout start is computed but written only to
``local/holdout/`` (sealed). Per-event and per-symbol-day rows stay under
``local/phase0/``.

From ``_system/scripts``::

    python -m reverse_splits.phase0_research --publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .analysis import cluster_interval
from .config import Config, load_config
from .databento_bars import DATASETS, DEFINITION_DATASET, is_complete
from .hypotheses import declared_before, load_registry
from .ledger import load_jsonl, read_json, sha256_file, write_json
from .split_detector import (
    VENUE_OF_LISTING,
    _symbol_spans,
    is_listed_equity,
    load_bars,
    normalize_symbol,
)

VERSION = "shorts_phase0.v1"
HYPOTHESES = ("H1", "H7", "H8")
RUN_ID = "20261013T224003582762Z"
SPLITS = {"train": ("2018-05-01", "2022-12-31"), "validate": ("2023-01-01", "2024-12-31")}
HOLDOUT_START = "2025-01-01"
PUBLISHED_YEARS = tuple(str(y) for y in range(2018, 2025))
SEED = 20261018
DRAWS = 2000
PRICE_CAP = 5.0
ADV_LOW, ADV_HIGH = 50_000.0, 20_000_000.0
PRIOR_SESSIONS = 20
EXCLUSION_DAYS = 30
DOWN, UP = -0.10, 0.20
CONTROLS_PER_EVENT = 3
PRICE_CALIPER, VOLUME_CALIPER = math.log(2), math.log(3)
VERIFIED = frozenset({"primary_schedule_matched", "structured_corporate_action"})
BANDS = ((0.0, 1.0, "under_1"), (1.0, 2.0, "1_to_2"), (2.0, PRICE_CAP, "2_to_5"))
UNIVERSE_DEFINITION = (
    "Listed common, ordinary or ADS shares (Nasdaq ITCH definitions, listing venue XNAS/XNYS/XASE), "
    f"prior listing-venue close under ${PRICE_CAP:.0f}, prior {PRIOR_SESSIONS}-session three-venue dollar volume "
    f"between ${ADV_LOW:,.0f} and ${ADV_HIGH:,.0f}, at least {PRIOR_SESSIONS} prior printed sessions, no catalogued "
    f"reverse split within {EXCLUSION_DAYS} calendar days, and both official auction prints present. "
    "Gross short return = 1 - official close / official open on the listing venue. Equal weight per symbol-day."
)


# --- small helpers -----------------------------------------------------------

def assign_split(day: str) -> str | None:
    if day >= HOLDOUT_START:
        return "holdout"
    for name, (lo, hi) in SPLITS.items():
        if lo <= day <= hi:
            return name
    return None


def prior_bucket(prior_return) -> str | None:
    if prior_return is None or not isinstance(prior_return, (int, float)) or not math.isfinite(prior_return):
        return None
    if prior_return <= DOWN:
        return "down10"
    if prior_return >= UP:
        return "up20"
    return "middle"


def ssr_proxy(prev_low, prev2_close) -> bool | None:
    """Rule 201 trigger proxy for the open of the session after ``prev``: the
    prior session's low at or below 90% of the close before it."""
    try:
        if prev_low is None or prev2_close is None or not (prev2_close > 0) or not (prev_low > 0):
            return None
    except TypeError:
        return None
    return bool(prev_low <= 0.9 * prev2_close)


def price_band(prev_close) -> str | None:
    for lo, hi, label in BANDS:
        if prev_close is not None and lo <= prev_close < hi:
            return label
    return None


def _summary(values, positives) -> dict:
    n = len(values)
    if not n:
        return {"events": 0, "mean": None, "median": None, "positive_share": None}
    ordered = sorted(values)
    return {"events": n, "mean": float(sum(values) / n),
            "median": float((ordered[(n - 1) // 2] + ordered[n // 2]) / 2),
            "positive_share": float(positives / n)}


def summarize_rows(rows: list[dict], field: str = "ret") -> dict:
    """Event-level summary with issuer and year clusters (same conventions as the frozen studies)."""
    vals = [r[field] for r in rows if r.get(field) is not None]
    out = _summary(vals, sum(v > 0 for v in vals))
    out["issuers"] = len({r["issuer"] for r in rows if r.get(field) is not None})
    out["issuer_interval"] = cluster_interval(rows, field=field, cluster="issuer")
    out["year_interval"] = cluster_interval(rows, field=field, cluster="year")
    return out


def agg_interval(sums, counts, *, seed: int = SEED, draws: int = DRAWS, label: str = "symbol") -> dict:
    """Whole-cluster bootstrap of a ratio-of-sums mean from per-cluster sums and counts."""
    import numpy as np

    sums = np.asarray(sums, dtype=float)
    counts = np.asarray(counts, dtype=float)
    n = len(sums)
    if n < 5:
        return {"clusters": int(n), "low": None, "high": None, "method": f"too few {label} clusters"}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(draws, n))
    d = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return {"clusters": int(n), "low": float(np.quantile(d, .025)), "high": float(np.quantile(d, .975)),
            "draws": draws, "se": float(d.std(ddof=1)),
            "method": f"95% percentile interval; whole-{label} bootstrap; observed sessions only"}


def difference_interval(rows: list[dict], group: str, a: str, b: str, *, field: str = "ret",
                        cluster: str = "issuer", seed: int = SEED, draws: int = DRAWS) -> dict:
    """Bootstrap of mean(a) - mean(b) resampling whole clusters jointly."""
    import numpy as np

    per = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        slot = per[r[cluster]]
        if r.get(group) == a:
            slot[0] += v
            slot[1] += 1
        elif r.get(group) == b:
            slot[2] += v
            slot[3] += 1
    keys = sorted(per)
    arr = np.array([per[k] for k in keys], dtype=float)
    na, nb = arr[:, 1].sum(), arr[:, 3].sum()
    if na == 0 or nb == 0:
        return {"clusters": len(keys), "point": None, "low": None, "high": None, "method": "one group empty"}
    point = arr[:, 0].sum() / na - arr[:, 2].sum() / nb
    if len(keys) < 5:
        return {"clusters": len(keys), "point": float(point), "low": None, "high": None, "method": "too few clusters"}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(draws, len(keys)))
    s = arr[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        d = s[:, :, 0].sum(1) / s[:, :, 1].sum(1) - s[:, :, 2].sum(1) / s[:, :, 3].sum(1)
    d = d[np.isfinite(d)]
    se = float(d.std(ddof=1)) if len(d) > 1 else None
    return {"clusters": len(keys), "point": float(point), "low": float(np.quantile(d, .025)), "high": float(np.quantile(d, .975)),
            "draws": int(len(d)), "se": se, "t_cluster": float(point / se) if se else None,
            "bootstrap_two_sided_p": float(2 * min((d <= 0).mean(), (d >= 0).mean())),
            "method": f"95% percentile interval of the difference; whole-{cluster} bootstrap resampling both groups jointly"}


# --- events: the 671 verified ex+1 paths with their SSR state -------------------

def default_run_dir(cfg: Config) -> Path:
    return cfg.local_dir / "expansion" / "expansion_v2" / "runs" / RUN_ID


def event_rows(cfg: Config, run_dir: Path) -> list[dict]:
    import sqlite3

    rows = []
    for path in sorted((run_dir / "event_outcomes").glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                e = json.loads(line)
                if e.get("verification") not in VERIFIED:
                    continue
                o = next((o for o in e.get("outcomes", []) if o.get("cohort") == "ex_plus_1_h1"), None)
                if not o or o.get("status") != "observed_price_path" or o.get("gross_short_return") is None:
                    continue
                rows.append({"event_id": e["event_id"], "ticker": e["ticker"], "new_ticker": e.get("new_ticker"),
                             "issuer": e["issuer"], "ex_date": e["ex_date"], "entry_date": o["entry_date"],
                             "year": o["entry_date"][:4], "split": assign_split(o["entry_date"]),
                             "ratio": e.get("ratio"), "exchange_class": e.get("exchange_class"),
                             "ret": float(o["gross_short_return"])})
    conn = sqlite3.connect(f"file:{cfg.db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        states = {(t, d): r for t, d, r in conn.execute("SELECT ticker,date,restricted FROM ssr_states")}
        tickers = sorted({r["ticker"] for r in rows})
        prices = defaultdict(list)
        for chunk in range(0, len(tickers), 400):
            batch = tickers[chunk:chunk + 400]
            marks = ",".join("?" * len(batch))
            for t, d, low, close in conn.execute(
                    f"SELECT ticker,date,low,close FROM prices_daily WHERE ticker IN ({marks}) ORDER BY ticker,date", batch):
                prices[t].append((d, low, close))
    finally:
        conn.close()
    for r in rows:
        state = states.get((r["ticker"], r["entry_date"]))
        r["ssr_state"] = "restricted" if state == 1 else "unrestricted" if state == 0 else "unknown"
        # Bar-based Rule 201 proxy for the entry open: the ex-date low against the
        # pre-split close restated to the post-split basis (printed prices change
        # basis at the split, as the exchange's reference price does).
        series = prices.get(r["ticker"], [])
        days = [d for d, _, _ in series]
        import bisect

        j = bisect.bisect_left(days, r["entry_date"])
        proxy = None
        if j >= 2 and j < len(days) and days[j] == r["entry_date"]:
            _, prev_low, _ = series[j - 1]
            _, _, prev2_close = series[j - 2]
            ratio = r.get("ratio")
            if days[j - 1] == r["ex_date"] and ratio and ratio > 0:
                prev2_close = prev2_close / ratio if prev2_close else None
            proxy = ssr_proxy(prev_low, prev2_close)
        r["ssr_proxy"] = proxy
    return rows


def h1_results(rows: list[dict]) -> dict:
    def block(subset):
        out = {}
        for state in ("restricted", "unrestricted"):
            group = [r for r in subset if r["ssr_state"] == state]
            out[state] = summarize_rows(group)
        out["unknown"] = len([r for r in subset if r["ssr_state"] == "unknown"])
        out["difference_restricted_minus_unrestricted"] = difference_interval(
            [r for r in subset if r["ssr_state"] != "unknown"], "ssr_state", "restricted", "unrestricted")
        return out

    by_split = {name: block([r for r in rows if r["split"] == name]) for name in ("train", "validate", "holdout")}
    by_split["pooled_train_validate"] = block([r for r in rows if r["split"] in ("train", "validate")])
    by_year = {}
    for year in sorted({r["year"] for r in rows}):
        by_year[year] = block([r for r in rows if r["year"] == year])
    confusion = defaultdict(int)
    for r in rows:
        if r["ssr_state"] != "unknown" and r["ssr_proxy"] is not None:
            confusion[f"status_{r['ssr_state']}__proxy_{'restricted' if r['ssr_proxy'] else 'unrestricted'}"] += 1
    counts = {s: sum(1 for r in rows if r["ssr_state"] == s) for s in ("restricted", "unrestricted", "unknown")}
    return {"definition": ("Verified reverse split; next exchange session official open to official close; gross short return. "
                           "SSR state is the cached Nasdaq status at the entry open (ssr_states): restricted, unrestricted or unknown."),
            "states": counts, "by_split": by_split, "by_year": by_year,
            "bar_proxy_validation": {"confusion": dict(sorted(confusion.items())),
                                     "proxy": "prior session low <= 0.9 x the close before it, with the pre-split close restated by the split ratio",
                                     "events_without_proxy": sum(1 for r in rows if r["ssr_proxy"] is None)}}


# --- the universe scan --------------------------------------------------------

def definitions_frame(cfg: Config):
    """Compressed (symbol, day, security_type, exchange, listed) history from the monthly snapshots."""
    import databento as db
    import pandas as pd

    folder = cfg.databento_dir / DEFINITION_DATASET / "definition"
    parts = []
    for path in sorted(folder.glob("*.dbn.zst")) if folder.exists() else []:
        if path.stat().st_size == 0:
            continue
        day = date.fromisoformat(path.name.split(".")[0])
        frame = db.DBNStore.from_file(str(path)).to_df(map_symbols=False)
        if frame.empty:
            continue
        g = pd.DataFrame({"raw": frame["raw_symbol"].astype(str).to_numpy(),
                          "security_type": frame["security_type"].astype(str).to_numpy(),
                          "exchange": frame["exchange"].astype(str).to_numpy()})
        g["day"] = pd.Timestamp(day)
        parts.append(g)
    snap = pd.concat(parts, ignore_index=True)
    uniq = snap["raw"].unique()
    snap["symbol"] = snap["raw"].map(dict(zip(uniq, [normalize_symbol(s) for s in uniq]))).astype(object)
    snap = snap.drop(columns="raw").drop_duplicates(["symbol", "day"], keep="last").sort_values(["symbol", "day"])
    prev = snap.groupby("symbol", sort=False)[["security_type", "exchange"]].shift()
    unchanged = (prev["security_type"] == snap["security_type"]) & (prev["exchange"] == snap["exchange"])
    snap = snap[~unchanged.fillna(False)].copy()
    snap["listed"] = [is_listed_equity(t, e, s) for t, e, s in zip(snap["security_type"], snap["exchange"], snap["symbol"])]
    return snap.sort_values("day").reset_index(drop=True)


def catalogue_exclusions(cfg: Config):
    """(symbol, lo, hi) windows around every catalogued reverse split, listed or not."""
    import pandas as pd

    rows = []
    for name in ("expansion_events.jsonl", "events.jsonl"):
        path = cfg.ledger_dir / name
        if not path.exists() and not path.with_name(name.replace(".jsonl", ".parts.json")).exists():
            continue
        for e in load_jsonl(path):
            ex = str(e.get("ex_date") or "")[:10]
            if len(ex) != 10:
                continue
            for symbol in (e.get("ticker"), e.get("new_ticker"), e.get("database_ticker")):
                if symbol:
                    rows.append((normalize_symbol(symbol), ex))
    frame = pd.DataFrame(sorted(set(rows)), columns=["symbol", "ex_date"])
    frame["ex_date"] = pd.to_datetime(frame["ex_date"])
    frame["lo"] = frame["ex_date"] - pd.Timedelta(days=EXCLUSION_DAYS)
    frame["hi"] = frame["ex_date"] + pd.Timedelta(days=EXCLUSION_DAYS)
    frame["symbol"] = frame["symbol"].astype(object)
    return frame[["symbol", "lo", "hi"]]


def quarter_labels(cfg: Config) -> list[str]:
    folder = cfg.databento_dir / "XNAS.ITCH" / "ohlcv-1d"
    labels = []
    for path in sorted(folder.glob("*.dbn.zst")) if folder.exists() else []:
        if is_complete(path) and path.with_name(path.name.replace(".dbn.zst", ".symbology.json")).exists():
            labels.append(path.name.split(".")[0])
    return labels


def bars_frame(cfg: Config, label: str):
    import pandas as pd

    parts = []
    for dataset in DATASETS:
        path = cfg.databento_dir / dataset / "ohlcv-1d" / f"{label}.dbn.zst"
        if not path.exists() or not path.with_name(f"{label}.symbology.json").exists():
            continue
        f = load_bars(path)
        if f is None or f.empty:
            continue
        f = f.copy()
        f["venue"] = dataset.split(".")[0]
        parts.append(f)
    if not parts:
        return None
    f = pd.concat(parts, ignore_index=True)
    uniq = f["symbol"].unique()
    f["symbol"] = f["symbol"].map(dict(zip(uniq, [normalize_symbol(s) for s in uniq]))).astype(object)
    f["day"] = pd.to_datetime(f["day"])
    return f


def auctions_frame(cfg: Config, label: str):
    """Official opening/closing auction prices per (symbol, day, dataset) from the statistics schema."""
    import databento as db
    import numpy as np
    import pandas as pd

    parts = []
    for dataset in DATASETS:
        path = cfg.databento_dir / dataset / "statistics" / f"{label}.dbn.zst"
        if not path.exists() or path.stat().st_size == 0 or not path.with_name(f"{label}.symbology.json").exists():
            continue
        arr = db.DBNStore.from_file(str(path)).to_ndarray()
        arr = arr[np.isin(arr["stat_type"], [1, 11]) & (arr["update_action"] != 2)]
        px = arr["price"].astype(np.float64) / 1e9
        valid = (px > 0) & (px < 1e8)
        arr, px = arr[valid], px[valid]
        if not len(arr):
            continue
        ref = arr["ts_ref"]
        ok = (ref > 0) & (ref < np.iinfo(np.uint64).max)
        ts = np.where(ok, ref, arr["ts_event"]).astype("int64")
        days = pd.to_datetime(ts, unit="ns", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
        f = pd.DataFrame({"instrument_id": arr["instrument_id"].astype("int64"), "day": days,
                          "point": np.where(arr["stat_type"] == 1, "open", "close"), "price": px,
                          "ts": arr["ts_event"].astype("int64")})
        spans = _symbol_spans(path)
        spans["d0"] = pd.to_datetime(spans["d0"])
        spans["d1"] = pd.to_datetime(spans["d1"])
        f = f.merge(spans, on="instrument_id", how="inner")
        f = f[(f["day"] >= f["d0"]) & (f["day"] < f["d1"])]
        f = f.sort_values("ts").drop_duplicates(["symbol", "day", "point"], keep="last")
        p = f.pivot_table(index=["symbol", "day"], columns="point", values="price", aggfunc="last").reset_index()
        p.columns = [str(c) for c in p.columns]
        for col in ("open", "close"):
            if col not in p.columns:
                p[col] = float("nan")
        p = p.rename(columns={"open": "auc_open", "close": "auc_close"})
        p["dataset"] = dataset
        parts.append(p[["symbol", "day", "dataset", "auc_open", "auc_close"]])
    if not parts:
        return None
    out = pd.concat(parts, ignore_index=True)
    uniq = out["symbol"].unique()
    out["symbol"] = out["symbol"].map(dict(zip(uniq, [normalize_symbol(s) for s in uniq]))).astype(object)
    return out.drop_duplicates(["symbol", "day", "dataset"], keep="last")


class Accumulator:
    """Running per-cluster sums for the universe; nothing per symbol-day is kept."""

    def __init__(self):
        self.parts = []          # per-quarter groupby frames (split, condition, symbol, month) -> sum, count, positives
        self.day_parts = []      # per-quarter (day, bucket) -> sum, count
        self.coverage = defaultdict(int)

    def add(self, elig):
        import pandas as pd

        if elig.empty:
            return
        frame = elig.copy()
        frame["month"] = frame["day"].dt.strftime("%Y-%m")
        frame["positive"] = (frame["ret"] > 0).astype(int)
        conditions = {"all": pd.Series(True, index=frame.index)}
        for bucket in ("down10", "middle", "up20"):
            conditions[bucket] = frame["bucket"] == bucket
        conditions["ssr_proxy_restricted"] = frame["proxy"] == True  # noqa: E712
        conditions["ssr_proxy_unrestricted"] = frame["proxy"] == False  # noqa: E712
        for _, _, band in BANDS:
            conditions[f"band_{band}"] = frame["band"] == band
        pieces = []
        for name, mask in conditions.items():
            sub = frame[mask]
            if sub.empty:
                continue
            g = sub.groupby(["split", "year", "symbol", "month"], sort=False)["ret"].agg(["sum", "count"])
            g["positive"] = sub.groupby(["split", "year", "symbol", "month"], sort=False)["positive"].sum()
            g = g.reset_index()
            g["condition"] = name
            pieces.append(g)
        self.parts.append(pd.concat(pieces, ignore_index=True))
        d = frame.groupby(["day", "bucket"], sort=False)["ret"].agg(["sum", "count"]).reset_index()
        self.day_parts.append(d)

    def frame(self):
        import pandas as pd

        if not self.parts:
            return None
        f = pd.concat(self.parts, ignore_index=True)
        return f.groupby(["condition", "split", "year", "symbol", "month"], sort=False)[["sum", "count", "positive"]].sum().reset_index()

    def day_means(self):
        import pandas as pd

        if not self.day_parts:
            return {}
        d = pd.concat(self.day_parts, ignore_index=True).groupby(["day", "bucket"], sort=False)[["sum", "count"]].sum()
        out = defaultdict(dict)
        for (day, bucket), row in d.iterrows():
            key = day.strftime("%Y-%m-%d")
            out[key][bucket] = (float(row["sum"]), int(row["count"]))
        for key, buckets in out.items():
            s = sum(v[0] for v in buckets.values())
            n = sum(v[1] for v in buckets.values())
            buckets["all"] = (s, n)
        return out


def scan_universe(cfg: Config, events: list[dict], *, labels: list[str] | None = None, log=print) -> dict:
    """Stream the venue files quarter by quarter; return aggregates plus per-event matches."""
    import numpy as np
    import pandas as pd

    snap = definitions_frame(cfg)
    log(f"definitions: {len(snap):,} classification rows for {snap['symbol'].nunique():,} symbols")
    excl = catalogue_exclusions(cfg)
    log(f"exclusion windows: {len(excl):,}")
    labels = labels or quarter_labels(cfg)
    acc = Accumulator()
    by_entry = defaultdict(list)
    for e in events:
        by_entry[e["entry_date"]].append(e)
    event_matches = {}
    carry = None
    base_cols = ["symbol", "day", "open", "high", "low", "close", "volume_total", "venue", "security_type", "exchange", "listed"]
    coverage = defaultdict(int)
    processed_days: set[str] = set()
    for label in labels:
        bars = bars_frame(cfg, label)
        if bars is None or bars.empty:
            log(f"{label}: no bars")
            continue
        auc = auctions_frame(cfg, label)
        bars = bars.sort_values("day")
        bars = pd.merge_asof(bars, snap[["day", "symbol", "security_type", "exchange", "listed"]].sort_values("day"),
                             on="day", by="symbol", direction="backward")
        bars["listed"] = bars["listed"].fillna(False).astype(bool)
        bars["is_listing"] = bars["venue"] == bars["exchange"]
        total = bars.groupby(["symbol", "day"], sort=False)["volume"].sum().rename("volume_total").reset_index()
        chosen = (bars.sort_values(["symbol", "day", "is_listing", "volume"], ascending=[True, True, False, False])
                  .drop_duplicates(["symbol", "day"], keep="first")
                  .merge(total, on=["symbol", "day"], how="left"))
        chosen = chosen[base_cols].copy()
        chosen["carried"] = False
        if carry is not None and not carry.empty:
            c = carry.copy()
            c["carried"] = True
            combined = pd.concat([c, chosen], ignore_index=True)
        else:
            combined = chosen
        combined = combined.sort_values(["symbol", "day"]).reset_index(drop=True)
        g = combined.groupby("symbol", sort=False)
        combined["prev_close"] = g["close"].shift(1)
        combined["prev2_close"] = g["close"].shift(2)
        combined["prev_low"] = g["low"].shift(1)
        combined["dollar"] = combined["close"] * combined["volume_total"].astype(float)
        prior_dollar = g["dollar"].shift(1)
        combined["adv20"] = prior_dollar.groupby(combined["symbol"]).rolling(PRIOR_SESSIONS).mean().reset_index(level=0, drop=True)
        combined["nprior"] = g.cumcount()
        if auc is not None:
            combined["listing_dataset"] = combined["exchange"].map(VENUE_OF_LISTING)
            combined = combined.merge(auc, left_on=["symbol", "day", "listing_dataset"],
                                      right_on=["symbol", "day", "dataset"], how="left").drop(columns=["dataset"])
        else:
            combined["auc_open"] = np.nan
            combined["auc_close"] = np.nan
        valid_auc = (combined["auc_open"] > 0) & (combined["auc_close"] > 0)
        combined["ret"] = np.where(valid_auc, 1 - combined["auc_close"] / combined["auc_open"], np.nan)
        # catalogued split windows
        combined["excluded"] = False
        sub = combined[["symbol", "day"]].reset_index().merge(excl, on="symbol", how="inner")
        if not sub.empty:
            hit = sub[(sub["day"] >= sub["lo"]) & (sub["day"] <= sub["hi"])]["index"].unique()
            combined.loc[hit, "excluded"] = True
        combined["prior_ret"] = np.where(combined["prev2_close"] > 0, combined["prev_close"] / combined["prev2_close"] - 1, np.nan)
        combined["bucket"] = np.select([combined["prior_ret"] <= DOWN, combined["prior_ret"] >= UP], ["down10", "up20"], default="middle")
        combined.loc[~np.isfinite(combined["prior_ret"]), "bucket"] = None
        combined["proxy"] = np.where((combined["prev_low"] > 0) & (combined["prev2_close"] > 0),
                                     combined["prev_low"] <= 0.9 * combined["prev2_close"], None)
        live = combined[~combined["carried"]]
        base = (live["listed"] & (live["prev_close"] > 0) & (live["nprior"] >= PRIOR_SESSIONS) & ~live["excluded"]
                & live["adv20"].between(ADV_LOW, ADV_HIGH) & (live["prev_close"] < PRICE_CAP) & live["bucket"].notna())
        coverage["candidate_symbol_days"] += int(base.sum())
        coverage["candidate_missing_auction"] += int((base & ~np.isfinite(live["ret"])).sum())
        elig = live[base & np.isfinite(live["ret"])].copy()
        elig["split"] = elig["day"].dt.strftime("%Y-%m-%d").map(assign_split)
        elig = elig[elig["split"].notna()]
        elig["year"] = elig["day"].dt.strftime("%Y")
        elig["band"] = pd.cut(elig["prev_close"], [b[0] for b in BANDS] + [PRICE_CAP], right=False,
                              labels=[b[2] for b in BANDS]).astype(object)
        acc.add(elig[["symbol", "day", "ret", "bucket", "proxy", "band", "split", "year"]])
        coverage["eligible_symbol_days"] += int(len(elig))
        # events whose entry session falls in this quarter: subject features and matched controls
        quarter_days = set(live["day"].dt.strftime("%Y-%m-%d").unique())
        processed_days |= quarter_days
        pool_all = live[live["listed"] & (live["prev_close"] > 0) & (live["adv20"] >= ADV_LOW) & ~live["excluded"] & np.isfinite(live["ret"])]
        for day in sorted(set(by_entry) & quarter_days):
            day_ts = pd.Timestamp(day)
            pool = pool_all[pool_all["day"] == day_ts]
            for e in by_entry[day]:
                match = _match_event(e, live, pool, day_ts)
                event_matches[e["event_id"]] = match
        carry = chosen.sort_values(["symbol", "day"]).groupby("symbol", sort=False).tail(PRIOR_SESSIONS + 5)
        log(f"{label}: {len(chosen):,} symbol-days, {len(elig):,} eligible, {len(set(by_entry) & quarter_days)} event days")
    for k, v in coverage.items():
        acc.coverage[k] = v
    return {"accumulator": acc, "event_matches": event_matches, "quarters": labels, "definitions_rows": int(len(snap)),
            "exclusion_windows": int(len(excl)), "processed_days": processed_days}


def _match_event(e: dict, live, pool, day_ts) -> dict:
    """Subject features from the bars and up to three same-day matched controls (two variants).

    Printed prices change basis at the split, so every prior session dated before
    the ex date is restated to the post-split basis with the catalogue ratio
    (new shares / old shares) before the prior-session return and the Rule 201
    proxy are formed. Dollar volume is split-invariant and needs no restatement.
    """
    import numpy as np

    out = {"subject_found": False}
    symbols = [normalize_symbol(e["ticker"])] + ([normalize_symbol(e["new_ticker"])] if e.get("new_ticker") else [])
    series = None
    for s in symbols:
        rows = live[live["symbol"] == s].sort_values("day")
        if (rows["day"] == day_ts).any():
            series = rows.reset_index(drop=True)
            break
    if series is None:
        out["reason"] = "subject_not_in_bars"
        return out
    at = int(series.index[series["day"] == day_ts][0])
    subject = series.iloc[at]
    ratio = e.get("ratio")
    ex_ts = np.datetime64(e["ex_date"])

    def restated(position, column):
        if position < 0:
            return None
        row = series.iloc[position]
        value = row[column]
        if value is None or not np.isfinite(value) or value <= 0:
            return None
        if np.datetime64(row["day"], "D") < ex_ts and ratio and ratio > 0:
            return float(value) / float(ratio)
        return float(value)

    prev_close = restated(at - 1, "close")
    prev2_close = restated(at - 2, "close")
    prev_low = restated(at - 1, "low")
    prior_ret = prev_close / prev2_close - 1 if prev_close and prev2_close else None
    out.update(subject_found=True, subject_symbol=str(subject["symbol"]), prev_close=prev_close,
               adv20=float(subject["adv20"]) if np.isfinite(subject["adv20"]) else None,
               prior_ret=prior_ret, bucket=prior_bucket(prior_ret), proxy=ssr_proxy(prev_low, prev2_close),
               restated_by_ratio=bool(ratio and ratio > 0 and at >= 1 and np.datetime64(series.iloc[at - 1]["day"], "D") < ex_ts),
               auction_ret=float(subject["ret"]) if np.isfinite(subject["ret"]) else None,
               listed=bool(subject["listed"]))
    if out["prev_close"] is None or out["adv20"] is None:
        out["reason"] = "subject_features_unavailable"
        return out
    cand = pool[pool["symbol"] != subject["symbol"]]
    if cand.empty:
        out["reason"] = "no_candidates"
        return out
    pd_ = np.abs(np.log(cand["prev_close"].to_numpy(dtype=float) / out["prev_close"]))
    vd = np.abs(np.log(cand["adv20"].to_numpy(dtype=float) / out["adv20"]))
    ok = (pd_ <= PRICE_CALIPER) & (vd <= VOLUME_CALIPER)
    out["candidates_within_calipers"] = int(ok.sum())
    for variant, extra in (("calipers", np.ones(len(cand), dtype=bool)),
                           ("calipers_same_bucket", (cand["bucket"] == out["bucket"]).to_numpy() if out["bucket"] else np.zeros(len(cand), dtype=bool))):
        mask = ok & extra
        if mask.sum() == 0:
            out[variant] = None
            continue
        dist = (pd_ + vd)[mask]
        picked = cand[mask].iloc[np.argsort(dist)[:CONTROLS_PER_EVENT]]
        out[variant] = {"n": int(len(picked)), "control_mean": float(picked["ret"].mean()),
                        "controls": [str(s) for s in picked["symbol"]]}
    return out


# --- results from the aggregates ----------------------------------------------

def universe_results(agg_frame, *, splits: tuple[str, ...]) -> dict:
    """Per split and condition: mean, positive share, symbol and month cluster intervals."""
    out = {}
    if agg_frame is None:
        return out
    for split in splits:
        part = agg_frame[agg_frame["split"] == split]
        block = {}
        for condition in sorted(part["condition"].unique()):
            sub = part[part["condition"] == condition]
            by_symbol = sub.groupby("symbol")[["sum", "count"]].sum()
            by_month = sub.groupby("month")[["sum", "count"]].sum()
            n = int(sub["count"].sum())
            block[condition] = {"symbol_days": n, "symbols": int(len(by_symbol)),
                                "mean": float(sub["sum"].sum() / n) if n else None,
                                "positive_share": float(sub["positive"].sum() / n) if n else None,
                                "symbol_interval": agg_interval(by_symbol["sum"], by_symbol["count"], label="symbol"),
                                "month_interval": agg_interval(by_month["sum"], by_month["count"], label="month")}
        if "down10" in block and "up20" in block and block["down10"]["mean"] is not None and block["up20"]["mean"] is not None:
            block["h8_down10_minus_up20"] = _condition_difference(part, "down10", "up20")
        if "ssr_proxy_restricted" in block and "ssr_proxy_unrestricted" in block:
            block["ssr_proxy_restricted_minus_unrestricted"] = _condition_difference(part, "ssr_proxy_restricted", "ssr_proxy_unrestricted")
        out[split] = block
    return out


def _condition_difference(part, a: str, b: str) -> dict:
    import numpy as np

    wide = {}
    for name in (a, b):
        g = part[part["condition"] == name].groupby("symbol")[["sum", "count"]].sum()
        wide[name] = g
    symbols = sorted(set(wide[a].index) | set(wide[b].index))
    if len(symbols) < 5:
        return {"point": None, "method": "too few symbol clusters"}
    sa = wide[a]["sum"].reindex(symbols).fillna(0).to_numpy()
    na = wide[a]["count"].reindex(symbols).fillna(0).to_numpy()
    sb = wide[b]["sum"].reindex(symbols).fillna(0).to_numpy()
    nb = wide[b]["count"].reindex(symbols).fillna(0).to_numpy()
    point = sa.sum() / na.sum() - sb.sum() / nb.sum()
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(symbols), size=(DRAWS, len(symbols)))
    with np.errstate(divide="ignore", invalid="ignore"):
        d = sa[idx].sum(1) / na[idx].sum(1) - sb[idx].sum(1) / nb[idx].sum(1)
    d = d[np.isfinite(d)]
    se = float(d.std(ddof=1)) if len(d) > 1 else None
    return {"point": float(point), "low": float(np.quantile(d, .025)), "high": float(np.quantile(d, .975)), "draws": int(len(d)),
            "se": se, "t_cluster": float(point / se) if se else None,
            "method": "95% percentile interval of the difference; whole-symbol bootstrap resampling both conditions jointly"}


def universe_by_year(agg_frame, *, years: tuple[str, ...]) -> list[dict]:
    rows = []
    if agg_frame is None:
        return rows
    for year in years:
        part = agg_frame[agg_frame["year"] == year]
        if part.empty:
            continue
        row = {"year": year}
        for condition in ("all", "down10", "middle", "up20"):
            sub = part[part["condition"] == condition]
            n = int(sub["count"].sum())
            by_symbol = sub.groupby("symbol")[["sum", "count"]].sum()
            row[condition] = {"symbol_days": n, "mean": float(sub["sum"].sum() / n) if n else None,
                              "positive_share": float(sub["positive"].sum() / n) if n else None,
                              "symbol_interval": agg_interval(by_symbol["sum"], by_symbol["count"], label="symbol")}
        rows.append(row)
    return rows


def excess_results(events: list[dict], matches: dict, day_means: dict, *, splits: tuple[str, ...],
                   processed_days: set[str] | None = None) -> dict:
    """The split family's return in excess of the same-day fade and of matched controls."""
    rows = []
    reasons = defaultdict(int)
    for e in events:
        if processed_days is not None and e["entry_date"] not in processed_days:
            reasons["entry_session_not_scanned"] += 1
            rows.append(dict(e))
            continue
        m = matches.get(e["event_id"]) or {}
        day = day_means.get(e["entry_date"], {})
        row = dict(e)
        s, n = day.get("all", (0.0, 0))
        row["day_mean_all"] = s / n if n >= 5 else None
        row["excess_all"] = e["ret"] - row["day_mean_all"] if row["day_mean_all"] is not None else None
        bucket = m.get("bucket")
        sb, nb = day.get(bucket, (0.0, 0)) if bucket else (0.0, 0)
        row["day_mean_bucket"] = sb / nb if nb >= 5 else None
        row["excess_bucket"] = e["ret"] - row["day_mean_bucket"] if row["day_mean_bucket"] is not None else None
        for variant in ("calipers", "calipers_same_bucket"):
            c = m.get(variant)
            row[f"control_{variant}"] = c["control_mean"] if c else None
            row[f"excess_{variant}"] = e["ret"] - c["control_mean"] if c else None
        row["auction_ret_recomputed"] = m.get("auction_ret")
        if not m.get("subject_found"):
            reasons[m.get("reason", "subject_not_in_bars")] += 1
        elif m.get("calipers") is None:
            reasons["no_control_within_calipers"] += 1
        rows.append(row)
    out = {"exclusions": dict(reasons)}
    members = {"pooled_train_validate": ("train", "validate")}
    for split in splits:
        subset = [r for r in rows if r["split"] in members.get(split, (split,))]
        block = {"events": len(subset)}
        for field in ("excess_all", "excess_bucket", "excess_calipers", "excess_calipers_same_bucket"):
            have = [r for r in subset if r.get(field) is not None]
            block[field] = summarize_rows(have, field=field)
            comparator = {"excess_all": "day_mean_all", "excess_bucket": "day_mean_bucket",
                          "excess_calipers": "control_calipers", "excess_calipers_same_bucket": "control_calipers_same_bucket"}[field]
            block[field]["subject_mean"] = float(sum(r["ret"] for r in have) / len(have)) if have else None
            block[field]["comparator_mean"] = float(sum(r[comparator] for r in have) / len(have)) if have else None
        both = [r for r in subset if r.get("auction_ret_recomputed") is not None]
        block["recomputed_auction_return_check"] = {
            "events": len(both),
            "mean_abs_difference": float(sum(abs(r["ret"] - r["auction_ret_recomputed"]) for r in both) / len(both)) if both else None,
            "within_1bp": int(sum(abs(r["ret"] - r["auction_ret_recomputed"]) <= 1e-4 for r in both))}
        out[split] = block
    return out, rows


# --- assembly, sealing and publication ------------------------------------------

def _covers_zero(interval: dict | None) -> bool:
    return bool(interval) and interval.get("low") is not None and interval["low"] <= 0 <= interval["high"]


def assessments(h1: dict, fade: dict) -> dict:
    """Read each measured hypothesis against its registered criteria; train and validation only."""
    train = h1["by_split"]["train"]["difference_restricted_minus_unrestricted"]
    validate = h1["by_split"]["validate"]["difference_restricted_minus_unrestricted"]
    if _covers_zero(train) and _covers_zero(validate):
        verdict = ("Kill criterion met: the restricted-minus-unrestricted interval covers zero on train and on validation. "
                   "Treat both states as one population for the gross return and model Rule 201 as a price constraint "
                   "in the fill model, not as an admission rule.")
    elif validate.get("t_cluster") is not None and abs(validate["t_cluster"]) >= 3:
        verdict = "Success criterion met on validation: |t_cluster| >= 3; the two states differ in gross return."
    else:
        verdict = "Inconclusive on the registered criteria: neither |t_cluster| >= 3 on validation nor zero inside both intervals."
    out = {"H1": {"registered_success": "either direction with |t_cluster| >= 3 on validation",
                  "registered_kill": "interval covers zero on train and validation",
                  "assessment": verdict,
                  "train_difference": {k: train.get(k) for k in ("point", "low", "high", "t_cluster")},
                  "validate_difference": {k: validate.get(k) for k in ("point", "low", "high", "t_cluster")}},
           "H7": {"assessment": "Reported, not promoted: registered as a descriptive baseline."}}
    h8 = {}
    for split in ("train", "validate"):
        d = ((fade.get("by_split") or {}).get(split) or {}).get("h8_down10_minus_up20") or {}
        if d.get("point") is None:
            h8[split] = {"reading": "not measured"}
            continue
        if d.get("low") is not None and d["low"] > 0:
            reading = "as registered: larger fade after a -10% close"
        elif d.get("high") is not None and d["high"] < 0:
            reading = "reversed: larger fade after a +20% close"
        else:
            reading = "not distinguishable from zero"
        h8[split] = {"reading": reading, **{k: d.get(k) for k in ("point", "low", "high", "t_cluster")}}
    out["H8"] = {"assessment": "Reported, not promoted: registered as descriptive. Positive difference means the registered direction.",
                 "by_split": h8}
    return out


def seal(doc: dict) -> dict:
    """Strip every holdout-split value from a results document before publication."""
    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if k != "holdout" and k not in HOLDOUT_YEARS}
        if isinstance(node, list):
            return [walk(v) for v in node if not (isinstance(v, dict) and str(v.get("year", "")) in HOLDOUT_YEARS)]
        return node
    return walk(doc)


HOLDOUT_YEARS = frozenset(str(y) for y in range(int(HOLDOUT_START[:4]), 2100))


def input_manifest(cfg: Config, run_dir: Path, labels: list[str]) -> dict:
    files = []
    for path in sorted((run_dir / "event_outcomes").glob("*.jsonl")) + [run_dir / "one_day_paths.local.json"]:
        if path.exists():
            files.append({"path": str(path.relative_to(cfg.local_dir).as_posix()), "sha256": sha256_file(path)})
    db = cfg.db_path
    files.append({"path": str(db.relative_to(cfg.local_dir).as_posix()), "sha256": sha256_file(db), "bytes": db.stat().st_size})
    venue = []
    for dataset in DATASETS:
        for schema in ("ohlcv-1d", "statistics"):
            for label in labels:
                p = cfg.databento_dir / dataset / schema / f"{label}.dbn.zst"
                if p.exists():
                    venue.append({"path": str(p.relative_to(cfg.local_dir).as_posix()), "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    defs = sorted((cfg.databento_dir / DEFINITION_DATASET / "definition").glob("*.dbn.zst"))
    return {"run_id": RUN_ID, "run_inputs": files, "venue_files": venue,
            "definition_snapshots": {"count": len(defs), "sha256_of_names_and_sizes": hashlib.sha256(
                "".join(f"{p.name}:{p.stat().st_size}" for p in defs).encode()).hexdigest()}}


def build(cfg: Config, *, run_dir: Path | None = None, labels: list[str] | None = None, skip_universe: bool = False, log=print) -> dict:
    run_dir = run_dir or default_run_dir(cfg)
    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    registry = load_registry(cfg.ledger_dir)
    if not declared_before(registry, list(HYPOTHESES), built_at):
        raise SystemExit("hypotheses H1, H7 and H8 must be registered before the study is built")
    events = event_rows(cfg, run_dir)
    log(f"events: {len(events)} verified ex+1 paths; splits "
        f"{ {s: sum(1 for e in events if e['split'] == s) for s in ('train', 'validate', 'holdout')} }")
    h1 = h1_results(events)
    doc = {"schema_version": VERSION, "built_at": built_at, "research_only": True, "authority": "none", "aggregate_only": True,
           "hypothesis_ids": list(HYPOTHESES), "source_run_id": RUN_ID,
           "splits": {k: list(v) for k, v in SPLITS.items()},
           "holdout_policy": {"start": HOLDOUT_START, "status": "sealed",
                              "location": "local/holdout/phase0_holdout.json (not committed, not read until the program's final review)"},
           "h1_ssr_cohort": h1}
    universe_doc = {}
    local_rows = {"events": events}
    if not skip_universe:
        scan = scan_universe(cfg, events, labels=labels, log=log)
        acc = scan["accumulator"]
        agg = acc.frame()
        day_means = acc.day_means()
        all_splits = ("train", "validate", "holdout")
        results = universe_results(agg, splits=all_splits)
        pooled = None
        if agg is not None:
            pooled_frame = agg[agg["split"].isin(["train", "validate"])].copy()
            pooled_frame["split"] = "pooled_train_validate"
            pooled = universe_results(pooled_frame, splits=("pooled_train_validate",)).get("pooled_train_validate")
        excess, excess_rows = excess_results(events, scan["event_matches"], day_means, splits=all_splits + ("pooled_train_validate",),
                                             processed_days=scan["processed_days"]) if agg is not None else ({}, [])
        universe_doc = {
            "definition": UNIVERSE_DEFINITION,
            "price_basis": ("Official listing-venue opening and closing auction prints (Databento statistics types 1 and 11). "
                            "Conditioning features (prior close, prior-session return, dollar volume, Rule 201 proxy) come from the "
                            "listing-venue daily bar and the three-venue volume sum; those bars span pre-market and after-hours prints."),
            "quarters": scan["quarters"], "coverage": {**dict(acc.coverage), "definition_rows": scan["definitions_rows"],
                                                      "exclusion_windows": scan["exclusion_windows"]},
            "by_split": {**results, "pooled_train_validate": pooled},
            "by_year": universe_by_year(agg, years=tuple(sorted({str(y) for y in agg["year"].unique()}))) if agg is not None else [],
            "split_family_excess": excess,
        }
        local_rows["event_matches"] = scan["event_matches"]
        local_rows["excess_rows"] = excess_rows
    doc["fade_baseline"] = universe_doc
    doc["assessments"] = assessments(h1, universe_doc)
    doc["definitions"] = {
        "short_return_convention": "1 - exit price / entry price; positive means the short gained.",
        "split": "By the entry session date. Train 2018-05-01 to 2022-12-31, validate 2023-01-01 to 2024-12-31, holdout from 2025-01-01 (sealed).",
        "issuer_interval": "95% percentile interval from 2,000 whole-issuer (CIK) bootstrap draws; events of one issuer move together.",
        "symbol_interval": "95% percentile interval from 2,000 whole-symbol bootstrap draws over per-symbol sums; a symbol is the issuer proxy for the universe.",
        "month_interval": "95% percentile interval from 2,000 whole-calendar-month bootstrap draws; sessions of one month move together.",
        "t_cluster": "Point estimate divided by the bootstrap standard error of the difference; a descriptive ratio, not an asymptotic test.",
        "excess_all": "Event return minus the same-session mean fade of all eligible sub-$5 names (at least five names that session).",
        "excess_bucket": "Event return minus the same-session mean fade of eligible names in the same prior-session-return bucket.",
        "excess_calipers": "Event return minus the mean of up to three same-session listed names nearest in log prior close (within x2) and log dollar volume (within x3), no price cap, no catalogued split within 30 days.",
        "excess_calipers_same_bucket": "As excess_calipers, additionally requiring the same prior-session-return bucket.",
    }
    doc["limits"] = [
        "Gross price behaviour only: no borrow, locate, spread, depth, commission or fill assumption enters any number here.",
        "The universe is listed names on the three venue datasets since 2018-05; OTC and pre-2018 names are absent, and a symbol is used as the issuer cluster.",
        "Conditioning features come from daily bars that include pre-market and after-hours prints; the return itself uses official auction prints.",
        "Three-venue volume understates consolidated volume, so the dollar-volume band is conservative relative to a consolidated definition.",
        "The Rule 201 proxy is a bar-based approximation; the event cohort's SSR state is the cached Nasdaq status and is the authoritative H1 contrast.",
        "Catalogued-split exclusion windows rely on the ledger and the expansion catalogue; an undiscovered split would leave its sessions in the universe.",
        "Matched controls use pre-entry features only; they describe a conditional comparison, not a causal or executable alpha claim.",
        "Holdout results exist only under local/holdout and were not read while writing this document; nothing here was selected on them.",
        "H7 and H8 are descriptive baselines by registration; they are reported, not promoted.",
    ]
    return {"doc": doc, "local": local_rows, "built_at": built_at, "run_dir": run_dir, "labels": labels}


def write_outputs(cfg: Config, result: dict, *, publish: bool, log=print) -> dict:
    doc, local = result["doc"], result["local"]
    phase_dir = cfg.local_dir / "phase0"
    phase_dir.mkdir(parents=True, exist_ok=True)
    holdout_dir = cfg.local_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    full_path = phase_dir / "phase0_full.local.json"
    write_json(full_path, {"doc": doc, "rows": local})
    holdout = {"schema_version": VERSION, "built_at": doc["built_at"], "sealed": True,
               "h1_ssr_cohort": {"by_split": {"holdout": doc["h1_ssr_cohort"]["by_split"].get("holdout")},
                                 "by_year": {y: v for y, v in doc["h1_ssr_cohort"]["by_year"].items() if y in HOLDOUT_YEARS}},
               "fade_baseline": {"by_split": {"holdout": (doc.get("fade_baseline") or {}).get("by_split", {}).get("holdout")},
                                 "by_year": [r for r in (doc.get("fade_baseline") or {}).get("by_year", []) if str(r.get("year")) in HOLDOUT_YEARS],
                                 "split_family_excess": {"holdout": ((doc.get("fade_baseline") or {}).get("split_family_excess") or {}).get("holdout")}}}
    holdout_path = holdout_dir / "phase0_holdout.json"
    write_json(holdout_path, holdout)
    public = seal(doc)
    outputs = {"full": str(full_path), "holdout": str(holdout_path)}
    if publish:
        out_path = cfg.ledger_dir / "phase0_research.json"
        write_json(out_path, public)
        manifest = {"schema_version": VERSION, "built_at": doc["built_at"], "hypothesis_ids": list(HYPOTHESES),
                    "aggregate_only": True,
                    "output": {"path": out_path.name, "sha256": sha256_file(out_path)},
                    "registry": {"path": "hypotheses.jsonl", "sha256": sha256_file(cfg.ledger_dir / "hypotheses.jsonl")},
                    "code": {"path": "_system/scripts/reverse_splits/phase0_research.py", "sha256": sha256_file(Path(__file__))},
                    "inputs": input_manifest(cfg, result["run_dir"], result["labels"] or quarter_labels(cfg)),
                    "holdout": {"path": "local/holdout/phase0_holdout.json", "sha256": sha256_file(holdout_path), "sealed": True},
                    "raw_market_data_public": False}
        write_json(cfg.ledger_dir / "phase0_manifest.json", manifest)
        outputs["published"] = str(out_path)
        outputs["manifest"] = str(cfg.ledger_dir / "phase0_manifest.json")
        log(f"published {out_path} and manifest")
    return outputs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None, help="frozen expansion run directory")
    parser.add_argument("--quarters", type=int, default=None, help="process only the first N quarters (smoke test)")
    parser.add_argument("--skip-universe", action="store_true", help="H1 only; no venue scan")
    parser.add_argument("--publish", action="store_true", help="write phase0_research.json and its manifest beside the ledger")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    labels = quarter_labels(cfg)
    if args.quarters:
        labels = labels[:args.quarters]
    result = build(cfg, run_dir=args.run_dir, labels=labels, skip_universe=args.skip_universe)
    outputs = write_outputs(cfg, result, publish=args.publish and not args.quarters)
    print(json.dumps(outputs, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
