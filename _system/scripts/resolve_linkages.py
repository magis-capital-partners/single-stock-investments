#!/usr/bin/env python3
"""Resolve World Model linkage edges → derived_metrics (+ optional ledger actuals).

  python _system/scripts/resolve_linkages.py
  python _system/scripts/resolve_linkages.py --update-ledgers

Context only. Never edits valuation.json IRR fields.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_model_common as wm  # noqa: E402


def _theme_metric(series_id: str) -> dict | None:
    return wm.theme_series_lookup(series_id)


def resolve_edge(edge: dict) -> dict | None:
    formula = edge.get("formula") or {}
    ftype = formula.get("type")
    if ftype == "passthrough_theme":
        series_id = formula.get("theme_series") or (edge.get("from") or {}).get("metric")
        row = _theme_metric(series_id)
        if not row or row.get("latest") is None:
            return {
                "edge_id": edge.get("edge_id"),
                "metric": series_id,
                "latest": None,
                "as_of": None,
                "status": "missing",
                "theme_id": edge.get("theme_id"),
                "unit": (edge.get("from") or {}).get("unit"),
                "evidence_tier": edge.get("evidence_tier"),
                "in_base_irr": False,
                "to": edge.get("to"),
                "stale": True,
                "source": f"theme:{series_id}",
            }
        return {
            "edge_id": edge.get("edge_id"),
            "metric": series_id,
            "latest": row.get("latest"),
            "as_of": row.get("as_of"),
            "status": "ok",
            "theme_id": edge.get("theme_id"),
            "unit": (edge.get("from") or {}).get("unit"),
            "evidence_tier": edge.get("evidence_tier"),
            "in_base_irr": False,
            "to": edge.get("to"),
            "stale": bool(row.get("stale")),
            "direction": row.get("direction"),
            "yoy_pct": row.get("yoy_pct"),
            "source": row.get("source") or f"theme:{series_id}",
            "contributors": row.get("contributors"),
        }
    return {
        "edge_id": edge.get("edge_id"),
        "status": "unsupported_formula",
        "formula_type": ftype,
        "in_base_irr": False,
    }


def update_ledgers_from_metrics(metrics: dict[str, dict]) -> list[str]:
    """Patch ledger actuals for bound kpi_ids when value is available."""
    notes: list[str] = []
    today = date.today().isoformat()
    for edge_metric in metrics.values():
        to = edge_metric.get("to") or {}
        tickers = to.get("tickers") or []
        kpi_ids = set(to.get("kpi_ids") or [])
        if edge_metric.get("latest") is None or not kpi_ids:
            continue
        for ticker in tickers:
            path = wm.ROOT / ticker / "research" / "kpi_ledger.json"
            if not path.exists():
                continue
            ledger = wm.load_json(path)
            changed = False
            for kpi in ledger.get("kpis") or []:
                if kpi.get("kpi_id") not in kpi_ids:
                    continue
                # Only refresh when source is theme/derived; leave manual rows alone.
                src = str(kpi.get("source") or "")
                if not (src.startswith("theme:") or src.startswith("derived:")):
                    continue
                kpi["actual"] = {
                    "value": edge_metric.get("latest"),
                    "as_of": edge_metric.get("as_of"),
                }
                kpi["last_checked"] = today
                # Do not auto-set pass/fail unless already numeric gate-ready;
                # check_kpi_ledger --mark-auto owns status flips.
                changed = True
            if changed:
                ledger["as_of"] = today
                ledger["summary"] = wm.summarize_statuses(ledger.get("kpis") or [])
                wm.write_json(path, ledger)
                notes.append(f"updated {ticker}/research/kpi_ledger.json")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--update-ledgers",
        action="store_true",
        help="Refresh ledger actuals for bound theme/derived KPI rows",
    )
    args = ap.parse_args()

    manifest = wm.load_json(wm.LINKAGES_MANIFEST)
    edges = manifest.get("edges") or []
    metrics: dict[str, dict] = {}
    for edge in edges:
        resolved = resolve_edge(edge)
        if not resolved:
            continue
        key = resolved.get("edge_id") or resolved.get("metric")
        metrics[str(key)] = resolved

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": date.today().isoformat(),
        "disclaimer": (
            "Context only. Derived linkages inform stance and KPI ledgers; "
            "they never auto-inflate Lawrence base IRR."
        ),
        "edge_count": len(metrics),
        "metrics": metrics,
    }
    wm.write_json(wm.DERIVED_METRICS, payload)
    print(f"wrote {wm.DERIVED_METRICS.relative_to(wm.ROOT)} ({len(metrics)} edges)")

    if args.update_ledgers:
        for note in update_ledgers_from_metrics(metrics):
            print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
