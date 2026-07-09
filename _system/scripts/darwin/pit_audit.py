"""Leakage audit: static vs point-in-time features at each rebalance."""
from __future__ import annotations

from datetime import datetime, timezone

from .backtest import rebalance_points
from .config import load_mandate
from .features import build_features, rows_at_rebalance
from .pit import parse_iso_date, pit_mandate_cfg
from .prices import build_return_panel


def _input_provenance(ticker: str, as_of: str) -> list[dict]:
    from .config import ROOT
    from .pit import load_valuation_as_of

    ticker_dir = ROOT / ticker
    items: list[dict] = []
    val = load_valuation_as_of(ticker_dir, as_of)
    if val:
        items.append({"kind": "valuation", "date": str(val.get("as_of", ""))[:10]})
    research = ticker_dir / "research"
    if research.exists():
        from .pit import latest_dated_md_as_of

        dive = latest_dated_md_as_of(research, "deep_dive", as_of)
        if dive:
            import re

            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", dive.name)
            if m:
                items.append({"kind": "deep_dive", "date": m.group(1)})
    return items


def run_pit_audit(fast: bool = False) -> dict:
    mandate_doc = load_mandate()
    pit_cfg = pit_mandate_cfg(mandate_doc)
    lag = int(pit_cfg.get("research_publication_lag_days", 0))

    latest = build_features(mandate_doc)
    rows_latest = latest["tickers"]
    if not rows_latest:
        return {"error": "no_holdings", "leakage_count": 0}

    panel = build_return_panel(
        [
            {"ticker": r["ticker"], "market": r.get("market"), "irr_base_pct": r.get("irr_base_pct")}
            for r in rows_latest
        ],
        months=24 if fast else 60,
        allow_synthetic=True,
    )
    dates = panel.get("dates") or []
    freq = (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual")
    rebals = rebalance_points(dates, freq)
    issues: list[dict] = []
    rebalance_reports: list[dict] = []

    for ri in range(len(rebals) - 1):
        start = rebals[ri]
        as_of = dates[start] if start < len(dates) else dates[-1]
        pit_rows = rows_at_rebalance(as_of, lag_days=lag, mandate=mandate_doc)
        pit_by = {r["ticker"]: r for r in pit_rows}
        static_by = {r["ticker"]: r for r in rows_latest}

        for t in set(pit_by) | set(static_by):
            p = pit_by.get(t)
            s = static_by.get(t)
            prov = _input_provenance(t, as_of)
            for item in prov:
                pdt = parse_iso_date(item.get("date"))
                rdt = parse_iso_date(as_of)
                if pdt and rdt and pdt > rdt:
                    issues.append(
                        {
                            "ticker": t,
                            "rebalance_date": as_of,
                            "kind": item["kind"],
                            "file_date": item["date"],
                            "severity": "leak",
                        }
                    )
            if p and s:
                if (p.get("irr_base_pct") or 0) != (s.get("irr_base_pct") or 0):
                    issues.append(
                        {
                            "ticker": t,
                            "rebalance_date": as_of,
                            "kind": "irr_mismatch_static_vs_pit",
                            "pit_irr": p.get("irr_base_pct"),
                            "static_irr": s.get("irr_base_pct"),
                            "severity": "info",
                        }
                    )

        rebalance_reports.append(
            {
                "rebalance_date": as_of,
                "pit_tickers": len(pit_rows),
                "synthetic_sources": sum(
                    1 for s in (panel.get("sources") or {}).values() if s == "synthetic_irr_prior"
                ),
            }
        )

    leak_count = sum(1 for i in issues if i.get("severity") == "leak")
    synth = panel.get("sources") or {}
    synth_tickers = [t for t, src in synth.items() if src == "synthetic_irr_prior"]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "pit_audit",
        "rebalance_points": len(rebals) - 1,
        "leakage_count": leak_count,
        "issues": issues[:200],
        "rebalance_reports": rebalance_reports,
        "synthetic_tickers": synth_tickers,
        "pass": leak_count == 0,
        "lag_days": lag,
    }
