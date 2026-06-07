#!/usr/bin/env python3
"""Build peer comparison panels for land, royalties, and exchanges.

  python3 _system/scripts/fetch_peer_panel.py
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PEERS_DIR = ROOT / "_system" / "reference" / "market-data" / "peers"
RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"
FILING_PANELS = ROOT / "_system" / "reference" / "market-data" / "themes" / "filing_panels"
TODAY = date.today().isoformat()

CLUSTERS = {
    "land_surface": {
        "tickers": ["TPL", "LB", "TRC", "BWEL", "AZLCZ"],
        "metric_sources": {
            "TPL": ("tpl_operating_panel.csv", "water_revenue_m"),
            "AZLCZ": ("azlcz_lease_panel.csv", "renewable_revenue_m"),
        },
    },
    "royalties": {
        "tickers": ["RGLD", "FNV", "WPM", "OR"],
        "metric_sources": {},
    },
    "exchanges": {
        "tickers": ["CME", "ICE", "CBOE", "MIAX", "8697.T"],
        "metric_sources": {},
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def latest_price_level(ticker: str) -> tuple[float | None, str | None]:
    """Cumulative index from monthly returns (100 at start of series)."""
    key = ticker.replace(".", "_")
    path = RETURNS_DIR / f"{key}.csv"
    if not path.exists():
        return None, None
    level = 100.0
    last_date = None
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row.get("date", "")
            try:
                r = float(row.get("monthly_return", ""))
            except ValueError:
                continue
            level *= 1.0 + r
            last_date = d
    return round(level, 2), last_date


def filing_metric(ticker: str, panel: str, metric: str) -> float | None:
    path = FILING_PANELS / panel
    if not path.exists():
        return None
    best = None
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("ticker") or "").upper() == ticker.upper():
                try:
                    best = float(row.get(metric) or "")
                except ValueError:
                    continue
    return best


def build_cluster(cluster_id: str, spec: dict) -> list[dict]:
    rows: list[dict] = []
    metric_sources = spec.get("metric_sources") or {}
    for tk in spec["tickers"]:
        price_idx, price_as_of = latest_price_level(tk)
        metric_val = None
        metric_name = None
        if tk in metric_sources:
            panel, metric = metric_sources[tk]
            metric_val = filing_metric(tk, panel, metric)
            metric_name = metric
        val_path = ROOT / tk / "research" / "valuation.json"
        irr = None
        if val_path.exists():
            val = load_json(val_path)
            irr = (val.get("results") or {}).get("base", {}).get("return_pct")
        rows.append({
            "as_of": TODAY,
            "ticker": tk,
            "price_index": price_idx,
            "price_as_of": price_as_of,
            "operating_metric": metric_val,
            "metric_name": metric_name,
            "lawrence_base_irr_pct": irr,
            "source": "returns_vault+filing_panels",
        })
    return rows


def write_cluster_csv(cluster_id: str, rows: list[dict]) -> Path:
    PEERS_DIR.mkdir(parents=True, exist_ok=True)
    path = PEERS_DIR / f"{cluster_id}.csv"
    fields = ["as_of", "ticker", "price_index", "price_as_of", "operating_metric", "metric_name", "lawrence_base_irr_pct", "source"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def main() -> int:
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": TODAY,
        "clusters": {},
    }
    for cluster_id, spec in CLUSTERS.items():
        rows = build_cluster(cluster_id, spec)
        path = write_cluster_csv(cluster_id, rows)
        manifest["clusters"][cluster_id] = {
            "path": str(path.relative_to(ROOT)),
            "tickers": spec["tickers"],
            "rows": len(rows),
        }
        print(f"OK {cluster_id}: {len(rows)} peers -> {path.relative_to(ROOT)}")
    (PEERS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
