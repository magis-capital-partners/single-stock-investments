"""Databento venue files for the reverse-split study: daily bars, status, definitions.

A local research step, like ``prices``. Files land under ``local/raw/databento/``
(gitignored). The data is licensed to us and SSI is public, so raw bars never
enter the ledger; only derived event facts do.

Venue datasets carry every instrument that traded that day, including ones
that later delisted, and their prices are printed (unadjusted). That is what
removes the survivor-only seed and what the split detector reads.

Every request is priced first with ``metadata.get_cost`` and refused unless the
quote is at most ``max_cost`` (default $0.00). The key comes from the
``DATABENTO_API_KEY`` environment variable. Nothing here touches the IB Gateway
or ThetaData.

Layout::

    databento/{dataset}/{schema}/{period}.dbn.zst        the file
    databento/{dataset}/{schema}/{period}.symbology.json  instrument_id -> [{d0, d1, s}]
    databento/{dataset}/{schema}/{period}.ok.json         request, quote, bytes, fetched_at
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import Config, load_config

DATASETS = ("XNAS.ITCH", "XNYS.PILLAR", "XASE.PILLAR")
FIRST_DAY = date(2018, 5, 1)  # the venue datasets start here
STATUS_DATASET = "XNAS.ITCH"  # disseminates Reg SHO 201 state for every NMS symbol
DEFINITION_DATASET = "XNAS.ITCH"
RESOLVE_BATCH = 1000


class CostRefused(RuntimeError):
    """Databento quoted more than the allowed cost for a request."""


def quarters(start: date, end: date) -> list[tuple[str, date, date]]:
    """Calendar quarters covering ``[start, end)``, clipped, as (label, start, end)."""
    out = []
    cur = date(start.year, 3 * ((start.month - 1) // 3) + 1, 1)
    while cur < end:
        nxt = date(cur.year + (cur.month + 3 > 12), (cur.month + 2) % 12 + 1, 1)
        lo, hi = max(cur, start), min(nxt, end)
        if lo < hi:
            out.append((f"{cur.year}Q{(cur.month - 1) // 3 + 1}", lo, hi))
        cur = nxt
    return out


def month_starts(start: date, end: date) -> list[date]:
    out, cur = [], date(start.year, start.month, 1)
    while cur < end:
        out.append(max(cur, start))
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


def file_path(cfg: Config, dataset: str, schema: str, period: str) -> Path:
    return cfg.databento_dir / dataset / schema / f"{period}.dbn.zst"


def _sidecar(path: Path, kind: str) -> Path:
    return path.with_name(path.name.replace(".dbn.zst", f".{kind}.json"))


def is_complete(path: Path) -> bool:
    return path.exists() and _sidecar(path, "ok").exists()


def client_from_env():
    import databento as db  # deferred: network command only

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit("DATABENTO_API_KEY is not set")
    return db.Historical(key)


def fetch(client, path: Path, max_cost: float = 0.0, *, quoted_cost: float | None = None, **request) -> dict:
    """Download one request to ``path`` unless it is already complete. The quote
    is checked first; a file is written under ``.part`` and renamed when done."""
    if is_complete(path):
        saved = json.loads(_sidecar(path, "ok").read_text(encoding="utf-8"))
        if saved.get("request") == {k: str(v) for k, v in request.items()}:
            return saved
    # A collector may pass the quote it just obtained for this exact request.
    # This avoids a duplicate metadata call while retaining the cost gate.
    quote = float(client.metadata.get_cost(**request) if quoted_cost is None else quoted_cost)
    if not math.isfinite(quote) or quote < 0:
        raise CostRefused('Databento returned an invalid cost quote')
    if quote > max_cost:
        raise CostRefused(f"Databento quotes ${quote:.2f} (> ${max_cost:.2f}) for {request}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)  # left by an interrupted run; the client refuses to overwrite
    client.timeseries.get_range(**request, path=str(part))
    part.replace(path)
    record = {
        "request": {k: str(v) for k, v in request.items()},
        "quoted_usd": quote,
        "bytes": path.stat().st_size,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _sidecar(path, "ok").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def resolve_symbology(client, path: Path, dataset: str, start: date, end: date) -> int:
    """instrument_id -> raw_symbol intervals for every id in the file. ALL_SYMBOLS
    downloads carry no symbol table; the resolve call is free metadata."""
    out = _sidecar(path, "symbology")
    if out.exists():
        return len(json.loads(out.read_text(encoding="utf-8")))
    import databento as db  # deferred
    import numpy as np

    ids = sorted(int(x) for x in np.unique(db.DBNStore.from_file(str(path)).to_ndarray()["instrument_id"]))
    intervals: dict[str, list] = {}
    # Instrument IDs are dataset-wide. Reuse the already resolved all-symbol
    # daily-bar intervals for the same period; resolve only genuinely new IDs.
    sibling=path.parent.parent/'ohlcv-1d'/_sidecar(path,'symbology').name
    if path.parent.name!='ohlcv-1d' and sibling.exists():
        saved=json.loads(sibling.read_text(encoding='utf-8'))
        intervals.update({str(i):saved[str(i)] for i in ids if str(i) in saved})
    remaining=[i for i in ids if str(i) not in intervals]
    for i in range(0, len(remaining), RESOLVE_BATCH):
        res = client.symbology.resolve(
            dataset=dataset, symbols=[str(x) for x in remaining[i:i + RESOLVE_BATCH]],
            stype_in="instrument_id", stype_out="raw_symbol",
            start_date=start.isoformat(), end_date=end.isoformat(),
        )
        intervals.update(res.get("result") or {})
    out.write_text(json.dumps(intervals), encoding="utf-8")
    return len(intervals)


def available_end(client, dataset: str, schema: str) -> date:
    """Exclusive end date of what Databento serves for this schema now."""
    rng = client.metadata.get_dataset_range(dataset=dataset)
    end = ((rng.get("schema") or {}).get(schema) or {}).get("end") or rng.get("end")
    return date.fromisoformat(str(end)[:10])


def drop_if_stale(path: Path, want_end: date) -> bool:
    """A partial quarter fetched earlier is refetched once more days exist."""
    if not is_complete(path):
        return False
    stored = json.loads(_sidecar(path, "ok").read_text(encoding="utf-8")).get("request", {}).get("end", "")
    if stored and stored[:10] < want_end.isoformat():
        for p in (path, _sidecar(path, "ok"), _sidecar(path, "symbology")):
            p.unlink(missing_ok=True)
        return True
    return False


def condition_path(cfg: Config, dataset: str) -> Path:
    return cfg.databento_dir / dataset / "condition.json"


def save_condition(client, cfg: Config, dataset: str, start: date, end: date) -> int:
    """Databento's per-day quality flags (free metadata). A detection on a
    degraded day is flagged, not dropped."""
    rows = client.metadata.get_dataset_condition(dataset=dataset, start_date=start.isoformat(),
                                                 end_date=(end - timedelta(days=1)).isoformat())
    flagged = [r for r in rows if r.get("condition") not in (None, "available")]
    path = condition_path(cfg, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "not_available": flagged}, indent=1), encoding="utf-8")
    return len(flagged)


def pull(cfg: Config | None = None, start: date = FIRST_DAY, end: date | None = None,
         schemas: tuple[str, ...] = ("ohlcv-1d", "definition", "status"),
         datasets: tuple[str, ...] = DATASETS, max_cost: float = 0.0, client=None, log=print) -> dict:
    """Fetch what is missing. Safe to rerun: complete files are skipped."""
    cfg = cfg or load_config()
    end = end or date.today()
    client = client or client_from_env()
    summary = {"files": 0, "skipped": 0, "bytes": 0, "quoted_usd": 0.0}
    import threading
    from concurrent.futures import ThreadPoolExecutor
    summary_lock=threading.Lock()

    def one(path, sym_range, **request):
        done = is_complete(path)
        record = fetch(client, path, max_cost, **request)
        if sym_range and path.stat().st_size:
            resolve_symbology(client, path, request["dataset"], *sym_range)
        with summary_lock:
            summary["skipped" if done else "files"] += 1
            summary["bytes"] += int(record.get("bytes") or 0)
            summary["quoted_usd"] += float(record.get("quoted_usd") or 0.0)
        log(f"{'have' if done else 'got '} {path.relative_to(cfg.databento_dir).as_posix()} "
            f"{int(record.get('bytes') or 0) / 1e6:.1f} MB")

    if "ohlcv-1d" in schemas:
        for dataset in datasets:
            stop = min(end, available_end(client, dataset, "ohlcv-1d"))
            for label, lo, hi in quarters(start, stop):
                path = file_path(cfg, dataset, "ohlcv-1d", label)
                if drop_if_stale(path, hi):
                    log(f"refresh {path.relative_to(cfg.databento_dir).as_posix()} through {hi}")
                one(path, (lo, hi), dataset=dataset,
                    schema="ohlcv-1d", symbols="ALL_SYMBOLS", start=lo.isoformat(), end=hi.isoformat())
            log(f"{dataset}: {save_condition(client, cfg, dataset, start, stop)} days not fully available")
    if "definition" in schemas:
        stop = min(end, available_end(client, DEFINITION_DATASET, "definition"))
        for first in month_starts(start, stop):
            # The first session of the month: a weekend or holiday returns an empty file.
            for offset in range(7):
                day = first + timedelta(days=offset)
                if day.weekday() >= 5 or day >= stop:
                    continue
                path = file_path(cfg, DEFINITION_DATASET, "definition", day.isoformat())
                one(path, None, dataset=DEFINITION_DATASET, schema="definition", symbols="ALL_SYMBOLS",
                    start=day.isoformat(), end=(day + timedelta(days=1)).isoformat())
                if path.stat().st_size > 1024:
                    break
    if "status" in schemas:
        stop = min(end, available_end(client, STATUS_DATASET, "status"))
        for label, lo, hi in quarters(start, stop):
            path = file_path(cfg, STATUS_DATASET, "status", label)
            drop_if_stale(path, hi)
            one(path, (lo, hi), dataset=STATUS_DATASET,
                schema="status", symbols="ALL_SYMBOLS", start=lo.isoformat(), end=hi.isoformat())
    if 'statistics' in schemas:
        def statistics_venue(dataset):
            stop=min(end,available_end(client,dataset,'statistics'))
            for label,lo,hi in quarters(start,stop):
                path=file_path(cfg,dataset,'statistics',label)
                drop_if_stale(path,hi)
                one(path,(lo,hi),dataset=dataset,schema='statistics',symbols='ALL_SYMBOLS',start=lo.isoformat(),end=hi.isoformat())
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(statistics_venue,datasets))
    return summary
