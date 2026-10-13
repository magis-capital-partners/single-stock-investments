"""Reverse-split detection from printed Databento daily bars.

A reverse split shows in printed prices as a session that opens (or closes)
near an integer multiple k of the prior close while share volume falls by
roughly k: the same dollar turnover over fewer shares. A news move of the same
size comes with volume that rises. The detector reads the venue files pulled by
``databento_bars`` and never adjusts a price.

It writes nothing to the ledger. Output is local (the detections carry licensed
prices): ``reports/split_detections.csv`` and a reconciliation against
``events.jsonl`` in ``reports/split_detection_reconciliation.json``. Each event
is ``matched``, ``ledger_only`` (detector work: a ticker change on the split
day, an OTC name, a first session below the jump threshold) or
``detector_only`` (a discovery gap to verify against the filing before it
enters the ledger).

The ratio is inferred from prices and labelled so; the filing's ratio wins.
"""

from __future__ import annotations

import bisect
import csv
import json
import re
import statistics
from datetime import date, timedelta
from pathlib import Path

from .config import Config, load_config
from .databento_bars import DATASETS, DEFINITION_DATASET, is_complete

MIN_JUMP = 1.8
# Small ratios overlap with ordinary news moves, so they need a tighter fit
# and a deeper volume contraction.
SMALL_K = 3
MAX_RATIO_ERR = 0.30
MAX_RATIO_ERR_SMALL_K = 0.15
MAX_VOLUME_RATIO = 0.8
MAX_VOLUME_RATIO_SMALL_K = 0.6
CONTEXT_SESSIONS = 5
COMMON_RATIOS = (
    2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 16, 20, 24, 25, 30, 35, 40, 45, 50, 60, 70, 75, 80,
    100, 120, 125, 150, 200, 250, 300, 400, 500, 1000,
)
# Nasdaq issue classification in the ITCH stock directory: common stock,
# ordinary share, American depositary share. Warrants, rights, units, ETPs,
# preferreds and notes are not reverse-split shorts for this study.
EQUITY_TYPES = frozenset({"C", "O", "A"})
LISTING_VENUES = frozenset({"XNAS", "XNYS", "XASE"})
MATCH_DAYS = 5
CLUSTER_DAYS = 10
STOPPED_TRADING_DAYS = 30


def nearest_ratio(jump: float) -> tuple[int, float]:
    k = min(COMMON_RATIOS, key=lambda r: abs(jump / r - 1))
    return k, abs(jump / k - 1)


def normalize_symbol(symbol: str | None) -> str:
    return re.sub(r"[.\s/]+", "-", str(symbol or "").strip().upper())


def score_jump(prev_close: float | None, open_: float | None, close: float | None,
               pre_volume: float | None, post_volume: float | None) -> dict | None:
    """The detection rule for one session against the session before it.

    ``pre_volume`` is the median share volume of up to five sessions before;
    ``post_volume`` the median of up to five sessions from this one. Returns the
    fitted ratio and evidence, or ``None``.
    """
    if not prev_close or prev_close <= 0 or not pre_volume or not post_volume or pre_volume <= 0:
        return None
    best = None
    for basis, price in (("open", open_), ("close", close)):
        if not price or price <= 0:
            continue
        jump = price / prev_close
        if jump < MIN_JUMP:
            continue
        k, err = nearest_ratio(jump)
        if best is None or err < best["ratio_error"]:
            best = {"basis": basis, "jump": jump, "ratio_inferred": k, "ratio_error": err}
    if best is None:
        return None
    small = best["ratio_inferred"] <= SMALL_K
    volume_ratio = post_volume / pre_volume
    if best["ratio_error"] > (MAX_RATIO_ERR_SMALL_K if small else MAX_RATIO_ERR):
        return None
    if volume_ratio > (MAX_VOLUME_RATIO_SMALL_K if small else MAX_VOLUME_RATIO):
        return None
    best["volume_ratio"] = volume_ratio
    best["confidence"] = "high" if best["ratio_error"] <= 0.10 and volume_ratio <= 0.5 else "medium"
    return best


def detect_in_series(bars: list[dict], keep_from: date | None = None, keep_to: date | None = None) -> list[dict]:
    """Scan one symbol's bars (dicts with day, open, close, volume), oldest first."""
    out = []
    for i in range(1, len(bars)):
        bar = bars[i]
        if keep_from and bar["day"] < keep_from or keep_to and bar["day"] >= keep_to:
            continue
        prev = bars[i - 1]
        pre = [b["volume"] for b in bars[max(0, i - CONTEXT_SESSIONS):i] if b["volume"]]
        post = [b["volume"] for b in bars[i:i + CONTEXT_SESSIONS] if b["volume"]]
        if len(pre) < 2 or len(post) < 2:
            continue
        hit = score_jump(prev["close"], bar["open"], bar["close"], statistics.median(pre), statistics.median(post))
        if hit:
            hit.update(day=bar["day"], prev_day=prev["day"], prev_close=prev["close"], open=bar["open"], close=bar["close"])
            out.append(hit)
    return out


# --- definitions: issue type and listing venue -------------------------------

def classify(snapshots: dict[str, list[tuple[date, str, str]]], symbol: str, day: date) -> tuple[str | None, str | None]:
    """Issue type and listing venue from the latest definition snapshot on or
    before ``day`` (else the earliest after). ``snapshots`` maps a normalized
    symbol to sorted (snapshot_day, security_type, exchange)."""
    rows = snapshots.get(normalize_symbol(symbol)) or []
    if not rows:
        return None, None
    i = bisect.bisect_right([r[0] for r in rows], day) - 1
    _, security_type, exchange = rows[i if i >= 0 else 0]
    return security_type, exchange


# Exchange test securities (Nasdaq's Z?ZZT family and friends) are classified
# as common stock and do "split" when the exchange tests corporate actions.
TEST_SYMBOL = re.compile(r"^(Z[A-Z]ZZT|ZXYZ[.-]A|ZVV|NTEST|[A-Z]?TEST[A-Z]?|CBO|CBX)$")


def is_test_symbol(symbol: str | None) -> bool:
    return bool(TEST_SYMBOL.match(normalize_symbol(symbol)))


def is_listed_equity(security_type: str | None, exchange: str | None, symbol: str | None = None) -> bool:
    return security_type in EQUITY_TYPES and exchange in LISTING_VENUES and not is_test_symbol(symbol)


# --- reconciliation ------------------------------------------------------------

def _as_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def reconcile(detections: list[dict], ledger: list[dict], start: date, end: date,
              aliases: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Mark each detection matched/detector_only and list ledger events in the
    window that no detection matches. Same normalized ticker, ex dates within
    ``MATCH_DAYS`` calendar days. ``aliases`` maps a ledger (ticker, ex_date)
    to the symbol it traded under then (``filing_check`` rename joins)."""
    by_symbol: dict[str, list[dict]] = {}
    for det in detections:
        by_symbol.setdefault(normalize_symbol(det["symbol"]), []).append(det)
    ledger_only = []
    for event in ledger:
        ex = _as_date(event.get("ex_date"))
        if ex is None or not (start <= ex < end):
            continue
        symbols = {normalize_symbol(event.get("ticker"))}
        alias = (aliases or {}).get((event.get("ticker"), str(ex)))
        if alias:
            symbols.add(normalize_symbol(alias))
        hits = [d for s in symbols for d in by_symbol.get(s, []) if abs((d["day"] - ex).days) <= MATCH_DAYS]
        for d in hits:
            d.setdefault("ledger_matches", []).append({"ticker": event.get("ticker"), "ex_date": str(ex), "ratio": event.get("ratio")})
        if not hits:
            ledger_only.append(event)
    for det in detections:
        det["status"] = "matched" if det.get("ledger_matches") else "detector_only"
    return detections, ledger_only


# --- the venue files (pandas and databento, deferred) -------------------------

def _symbol_spans(path: Path):
    import pandas as pd

    sidecar = path.with_name(path.name.replace(".dbn.zst", ".symbology.json"))
    intervals = json.loads(sidecar.read_text(encoding="utf-8"))
    rows = [(int(iid), date.fromisoformat(iv["d0"]), date.fromisoformat(iv["d1"]), iv["s"])
            for iid, ivs in intervals.items() for iv in ivs]
    return pd.DataFrame(rows, columns=["instrument_id", "d0", "d1", "symbol"])


def load_bars(path: Path):
    """Daily bars with symbols: day, symbol, open, high, low, close, volume."""
    import databento as db

    if not path.exists() or path.stat().st_size == 0:
        return None
    frame = db.DBNStore.from_file(str(path)).to_df(price_type="float", pretty_ts=True, map_symbols=False).reset_index()
    frame["day"] = frame["ts_event"].dt.date
    frame = frame.merge(_symbol_spans(path), on="instrument_id", how="inner")
    frame = frame[(frame["day"] >= frame["d0"]) & (frame["day"] < frame["d1"])]
    return frame[["day", "symbol", "open", "high", "low", "close", "volume"]]


def _scan_frame(frame, keep_from: date, keep_to: date, dataset: str) -> list[dict]:
    """Vectorized prefilter (a jump of at least ``MIN_JUMP`` on open or close),
    then the exact rule on each candidate's own series."""
    frame = frame.sort_values(["symbol", "day"]).reset_index(drop=True)
    prev_close = frame.groupby("symbol", sort=False)["close"].shift(1)
    jump = (frame[["open", "close"]].max(axis=1) / prev_close).where(prev_close > 0)
    in_window = (frame["day"] >= keep_from) & (frame["day"] < keep_to)
    symbols = frame.loc[in_window & (jump >= MIN_JUMP), "symbol"].unique()
    out = []
    for symbol, series in frame[frame["symbol"].isin(symbols)].groupby("symbol", sort=False):
        bars = series[["day", "open", "close", "volume"]].to_dict("records")
        for hit in detect_in_series(bars, keep_from, keep_to):
            hit.update(symbol=symbol, dataset=dataset)
            out.append(hit)
    return out


def _scan_cache(cfg: Config) -> Path:
    return cfg.reports_dir / "split_detections_scan.json"


def _load_scan(cfg: Config):
    doc = json.loads(_scan_cache(cfg).read_text(encoding="utf-8"))
    for det in doc["detections"]:
        det["day"], det["prev_day"] = date.fromisoformat(det["day"]), date.fromisoformat(det["prev_day"])
    last_seen = {k: date.fromisoformat(v) for k, v in doc["last_seen"].items()}
    return doc["detections"], last_seen, date.fromisoformat(doc["first_day"]), date.fromisoformat(doc["last_day"])


def detect(cfg: Config | None = None, datasets: tuple[str, ...] = DATASETS, log=print, reuse_scan: bool = False) -> dict:
    """Scan, merge, classify, reconcile. ``reuse_scan`` skips the bar scan and
    reuses the last one (``reports/split_detections_scan.json``), so changes to
    merging, classification or reconciliation do not reread every quarter."""
    cfg = cfg or load_config()
    if reuse_scan and _scan_cache(cfg).exists():
        detections, last_seen, first_day, last_day = _load_scan(cfg)
        detections = [d for d in detections if d["dataset"] in datasets]
    else:
        detections, last_seen, first_day, last_day = _scan(cfg, datasets, log)
        cfg.reports_dir.mkdir(parents=True, exist_ok=True)
        _scan_cache(cfg).write_text(json.dumps({
            "datasets": list(datasets), "first_day": str(first_day), "last_day": str(last_day),
            "last_seen": {k: str(v) for k, v in last_seen.items()}, "detections": detections,
        }, default=str), encoding="utf-8")
    return _finish(cfg, datasets, detections, last_seen, first_day, last_day)


def _scan(cfg: Config, datasets, log):
    import pandas as pd

    detections: list[dict] = []
    last_seen: dict[str, date] = {}
    first_day, last_day = None, None
    for dataset in datasets:
        folder = cfg.databento_dir / dataset / "ohlcv-1d"
        # Only files whose download and symbol resolution both finished.
        labels = sorted(p.name.split(".")[0] for p in folder.glob("*.dbn.zst")
                        if is_complete(p) and p.with_name(p.name.replace(".dbn.zst", ".symbology.json")).exists()) if folder.exists() else []
        prev_tail, cur = None, None
        for i, label in enumerate(labels):
            cur = cur if cur is not None else load_bars(folder / f"{label}.dbn.zst")
            nxt = load_bars(folder / f"{labels[i + 1]}.dbn.zst") if i + 1 < len(labels) else None
            if cur is None or cur.empty:
                prev_tail, cur = None, nxt
                continue
            keep_from, keep_to = cur["day"].min(), cur["day"].max() + timedelta(days=1)
            first_day = min(first_day or keep_from, keep_from)
            last_day = max(last_day or cur["day"].max(), cur["day"].max())
            parts = [p for p in (prev_tail, cur) if p is not None]
            if nxt is not None:
                parts.append(nxt.sort_values("day").groupby("symbol", sort=False).head(CONTEXT_SESSIONS))
            found = _scan_frame(pd.concat(parts, ignore_index=True), keep_from, keep_to, dataset)
            detections.extend(found)
            for symbol, day in cur.groupby("symbol")["day"].max().items():
                if day > last_seen.get(symbol, date.min):
                    last_seen[symbol] = day
            prev_tail = cur.sort_values("day").groupby("symbol", sort=False).tail(CONTEXT_SESSIONS)
            log(f"{dataset} {label}: {len(cur):,} bars, {len(found)} jumps")
            cur = nxt
    return detections, last_seen, first_day, last_day


def _finish(cfg: Config, datasets, detections, last_seen, first_day, last_day) -> dict:
    merged = _merge_venues(detections)
    degraded = _degraded_days(cfg, datasets)
    for det in merged:
        det["degraded_day"] = any(day in degraded.get(v, ()) for v in det["venues"] for day in (det["day"], det["prev_day"]))
    _attach_definitions(cfg, merged)
    for det in merged:
        seen = last_seen.get(det["symbol"])
        det["last_bar"] = seen
        det["stopped_trading"] = bool(seen and last_day and (last_day - seen).days > STOPPED_TRADING_DAYS)
        det["corroborated"] = is_corroborated(det)
    from .ledger import load_jsonl
    ledger = load_jsonl(cfg.ledger_dir/'events.jsonl')
    window = (first_day + timedelta(days=14), last_day - timedelta(days=7)) if first_day else (date.min, date.min)
    # Reconcile against every detection, so a ledger event whose symbol is
    # missing from the definitions (a renamed ticker, say) is not miscounted as
    # undetected; the listed-equity filter applies to the counts afterwards.
    in_window = [d for d in merged if window[0] <= d["day"] < window[1]]
    joins_path = cfg.reports_dir / "rename_joins.json"
    aliases = {(j["ticker"], j["ex_date"]): j["filing_time_symbol"]
               for j in json.loads(joins_path.read_text(encoding="utf-8"))} if joins_path.exists() else {}
    in_window, ledger_only = reconcile(in_window, ledger, *window, aliases=aliases)
    listed = [d for d in in_window if d["listed_equity"]]
    summary = _summarize(listed, ledger_only, ledger, window, merged)
    summary["ledger_matched_by_unclassified"] = sum(1 for d in in_window if d["status"] == "matched" and not d["listed_equity"])
    _write(cfg, merged, summary, ledger_only)
    return summary


def _degraded_days(cfg: Config, datasets) -> dict[str, set[date]]:
    """Days Databento marks degraded, pending or missing, per venue."""
    from .databento_bars import condition_path

    out = {}
    for dataset in datasets:
        path = condition_path(cfg, dataset)
        if path.exists():
            rows = json.loads(path.read_text(encoding="utf-8")).get("not_available") or []
            out[dataset] = {d for r in rows if (d := _as_date(r.get("date")))}
    return out


def _merge_venues(detections: list[dict]) -> list[dict]:
    """One event per symbol per split. A venue with no print on the split day
    sees the jump at its next print, so detections of one symbol within
    ``CLUSTER_DAYS`` of the first are one event, dated by the earliest session
    (no venue can see a split before it happens). The fitted ratio comes from
    the best-fitting row."""
    by_symbol: dict[str, list[dict]] = {}
    for det in detections:
        by_symbol.setdefault(det["symbol"], []).append(det)
    out = []
    for rows in by_symbol.values():
        rows.sort(key=lambda r: r["day"])
        clusters: list[list[dict]] = []
        for row in rows:
            if clusters and (row["day"] - clusters[-1][0]["day"]).days <= CLUSTER_DAYS:
                clusters[-1].append(row)
            else:
                clusters.append([row])
        for cluster in clusters:
            first = min(cluster, key=lambda r: (r["day"], r["ratio_error"]))
            best = dict(min(cluster, key=lambda r: r["ratio_error"]))
            best.update(day=first["day"], prev_day=first["prev_day"], prev_close=first["prev_close"],
                        open=first["open"], close=first["close"])
            best["venues"] = sorted({r["dataset"] for r in cluster})
            best["venue_days"] = sorted({f"{r['dataset']}:{r['day']}" for r in cluster})
            out.append(best)
    return sorted(out, key=lambda r: (r["day"], r["symbol"]))


VENUE_OF_LISTING = {"XNAS": "XNAS.ITCH", "XNYS": "XNYS.PILLAR", "XASE": "XASE.PILLAR"}


def is_corroborated(det: dict) -> bool:
    """Seen on the stock's own listing exchange, or on at least two venues. A
    lone print on a venue that is not the listing market is the weakest
    evidence the detector produces."""
    return VENUE_OF_LISTING.get(det.get("listing_venue")) in det["venues"] or len(det["venues"]) >= 2


def _attach_definitions(cfg: Config, detections: list[dict]) -> None:
    import databento as db

    wanted = {normalize_symbol(d["symbol"]) for d in detections}
    snapshots: dict[str, list[tuple[date, str, str]]] = {}
    folder = cfg.databento_dir / DEFINITION_DATASET / "definition"
    for path in sorted(folder.glob("*.dbn.zst")) if folder.exists() else []:
        if path.stat().st_size == 0:
            continue
        day = date.fromisoformat(path.name.split(".")[0])
        frame = db.DBNStore.from_file(str(path)).to_df(map_symbols=False)
        if frame.empty:
            continue
        for symbol, security_type, exchange in frame[["raw_symbol", "security_type", "exchange"]].itertuples(index=False):
            key = normalize_symbol(symbol)
            if key in wanted:
                snapshots.setdefault(key, []).append((day, str(security_type), str(exchange)))
    for rows in snapshots.values():
        rows.sort()
    for det in detections:
        det["security_type"], det["listing_venue"] = classify(snapshots, det["symbol"], det["day"])
        det["listed_equity"] = is_listed_equity(det["security_type"], det["listing_venue"], det["symbol"])


def _summarize(listed: list[dict], ledger_only: list[dict], ledger: list[dict], window, merged) -> dict:
    by_year: dict[int, dict] = {}
    for det in listed:
        row = by_year.setdefault(det["day"].year, {"detected": 0, "matched": 0, "detector_only": 0, "stopped_trading": 0, "high_confidence": 0})
        row["detected"] += 1
        row[det["status"]] += 1
        row["corroborated"] = row.get("corroborated", 0) + int(det["corroborated"])
        row["stopped_trading"] += int(det["stopped_trading"])
        row["high_confidence"] += int(det["confidence"] == "high")
    for event in ledger_only:
        ex = _as_date(event.get("ex_date"))
        row = by_year.setdefault(ex.year, {"detected": 0, "matched": 0, "detector_only": 0, "stopped_trading": 0, "high_confidence": 0})
        key = "ledger_only_listed" if event.get("exchange_class") == "listed" else "ledger_only_other"
        row[key] = row.get(key, 0) + 1
    in_window = [e for e in ledger if (ex := _as_date(e.get("ex_date"))) and window[0] <= ex < window[1]]
    matched = sum(1 for d in listed if d["status"] == "matched")
    return {
        "window": [str(window[0]), str(window[1])],
        "thresholds": {"min_jump": MIN_JUMP, "max_ratio_err": MAX_RATIO_ERR, "max_ratio_err_small_k": MAX_RATIO_ERR_SMALL_K,
                       "max_volume_ratio": MAX_VOLUME_RATIO, "max_volume_ratio_small_k": MAX_VOLUME_RATIO_SMALL_K,
                       "context_sessions": CONTEXT_SESSIONS, "match_days": MATCH_DAYS},
        "all_detections": len(merged),
        "listed_equity_detections": len(listed),
        "matched": matched,
        "detector_only": len(listed) - matched,
        "corroborated": sum(1 for d in listed if d["corroborated"]),
        "corroborated_detector_only": sum(1 for d in listed if d["corroborated"] and d["status"] == "detector_only"),
        "corroborated_stopped_trading": sum(1 for d in listed if d["corroborated"] and d["stopped_trading"]),
        "stopped_trading": sum(1 for d in listed if d["stopped_trading"]),
        "on_degraded_days": sum(1 for d in listed if d.get("degraded_day")),
        "ledger_events_in_window": len(in_window),
        "ledger_listed_in_window": sum(1 for e in in_window if e.get("exchange_class") == "listed"),
        "ledger_only": len(ledger_only),
        "ledger_only_listed": sum(1 for e in ledger_only if e.get("exchange_class") == "listed"),
        "ledger_listed_recall": round(1 - sum(1 for e in ledger_only if e.get("exchange_class") == "listed")
                                      / max(1, sum(1 for e in in_window if e.get("exchange_class") == "listed")), 3),
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
    }


def _write(cfg: Config, merged: list[dict], summary: dict, ledger_only: list[dict]) -> None:
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    fields = ["day", "symbol", "ratio_inferred", "ratio_error", "jump", "basis", "volume_ratio", "confidence",
              "prev_day", "prev_close", "open", "close", "venues", "venue_days", "corroborated", "degraded_day",
              "security_type", "listing_venue", "listed_equity", "last_bar", "stopped_trading", "status", "ledger_matches"]
    with (cfg.reports_dir / "split_detections.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for det in merged:
            writer.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in det.items()})
    summary = dict(summary, ledger_only_events=[
        {k: e.get(k) for k in ("ticker", "ex_date", "exchange_class", "ratio", "source")} for e in ledger_only])
    (cfg.reports_dir / "split_detection_reconciliation.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
