#!/usr/bin/env python3
"""Point-in-time LPPLS error diagram on SPY closes.

Samples every N trading sessions once 750 sessions of history exist. Each
sample uses only prices up to that session. The written JSON is what the
World Model reads when it decides whether a live SPY ensemble may cap
market-path language.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from criticality.error_diagram import (  # noqa: E402
    CATALOG,
    LEAD_SESSIONS,
    MODEL_VERSION,
    evaluate,
)
from criticality.lppls import fit_ensemble  # noqa: E402

PRICES = ROOT / "_system" / "reference" / "market-data" / "benchmarks" / "spy_us.csv"
CATALOG_PATH = ROOT / "_system" / "research" / "criticality_monitor" / "event_catalog.csv"
OUTPUT = ROOT / "dashboard" / "data" / "criticality_error_diagram.json"
SAMPLES_OUTPUT = ROOT / "_system" / "research" / "criticality_monitor" / "error_diagram_samples.json"
MIN_HISTORY = 750


def load_closes(path: Path) -> list[tuple[str, float]]:
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            close = row.get("Close")
            day = row.get("Date")
            if not day or close in (None, ""):
                continue
            price = float(close)
            if price > 0:
                rows.append((day, price))
    rows.sort()
    return rows


def write_catalog(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("id", "kind", "peak_date", "label", "notes"),
        )
        writer.writeheader()
        writer.writerows(CATALOG)


def fit_job(job: tuple[str, list[float]]) -> dict:
    day, prices = job
    result = fit_ensemble(prices)
    dispersion = (result.get("critical_time") or {}).get("dispersion")
    concentration = (
        None if dispersion is None
        else max(0.0, min(100.0, 100.0 - 3.0 * float(dispersion)))
    )
    confidence = result.get("confidence") or {}
    return {
        "date": day,
        "positive": confidence.get("positive"),
        "negative": confidence.get("negative"),
        "status": result.get("status"),
        "direction": result.get("direction"),
        "concentration": None if concentration is None else round(concentration, 2),
        "score": result.get("score"),
        "tail_kind": (result.get("tail") or {}).get("kind"),
    }


def build(*, step: int = 10, workers: int = 4, limit: int | None = None) -> dict:
    series = load_closes(PRICES)
    calendar = [day for day, _ in series]
    prices = [price for _, price in series]
    jobs = []
    for index in range(MIN_HISTORY - 1, len(series), step):
        start = index - (MIN_HISTORY - 1)
        jobs.append((calendar[index], prices[start:index + 1]))
    if limit is not None:
        jobs = jobs[:limit]
    samples = []
    if workers <= 1:
        for job in jobs:
            samples.append(fit_job(job))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fit_job, job) for job in jobs]
            for future in as_completed(futures):
                samples.append(future.result())
    samples.sort(key=lambda row: row["date"])
    diagram = evaluate(samples, CATALOG, calendar, lead_sessions=LEAD_SESSIONS)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "source": str(PRICES.relative_to(ROOT)).replace("\\", "/"),
        "price_field": "Close",
        "sample_step_sessions": step,
        "min_history_sessions": MIN_HISTORY,
        "research_only": True,
        "in_base_irr": False,
        "authority": "none",
        "sample_count": len(samples),
        "sample_first": samples[0]["date"] if samples else None,
        "sample_last": samples[-1]["date"] if samples else None,
        "samples": samples,
        **diagram,
    }
    return payload


def _write(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    write_catalog(CATALOG_PATH)
    payload = build(step=args.step, workers=max(1, args.workers), limit=args.limit)
    samples = payload.pop("samples")
    events_by_threshold = payload.pop("events_by_threshold")
    chosen = (payload.get("selection") or {}).get("confidence_threshold")
    payload["events"] = next(
        (row["events"] for row in events_by_threshold if row["threshold"] == chosen),
        events_by_threshold[0]["events"] if events_by_threshold else [],
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SAMPLES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _write(OUTPUT, payload)
    _write(SAMPLES_OUTPUT, {
        "model_version": payload["model_version"],
        "generated_at": payload["generated_at"],
        "samples": samples,
        "events_by_threshold": events_by_threshold,
    })
    selection = payload["selection"]
    print(json.dumps({
        "samples": payload["sample_count"],
        "demotion_enabled": selection["demotion_enabled"],
        "confidence_threshold": selection["confidence_threshold"],
        "miss_rate": selection["miss_rate"],
        "time_in_alarm": selection["time_in_alarm"],
        "output": str(OUTPUT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
