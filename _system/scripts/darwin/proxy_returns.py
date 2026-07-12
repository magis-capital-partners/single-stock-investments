"""Ensure covered-call ETF proxy monthly returns exist in the vault (Yahoo)."""
from __future__ import annotations

import csv
from pathlib import Path

from .config import ROOT
from .prices import RETURNS_DIR, fetch_yahoo_monthly


PROXY_DEFAULTS = ("XYLD", "QYLD")


def ensure_proxy_returns(tickers: list[str] | tuple[str, ...] | None = None, months: int = 60) -> dict:
    """Fetch missing proxy CSVs. Returns status per ticker."""
    tickers = list(tickers or PROXY_DEFAULTS)
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    for t in tickers:
        path = RETURNS_DIR / f"{t}.csv"
        if path.exists() and path.stat().st_size > 50:
            out[t] = {"status": "exists", "path": str(path)}
            continue
        dates, rets, src = fetch_yahoo_monthly(t, months=months)
        if len(rets) < 6:
            out[t] = {"status": "fetch_failed", "source": src}
            continue
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["date", "monthly_return", "source"])
            w.writeheader()
            for d, r in zip(dates, rets):
                w.writerow({"date": d, "monthly_return": f"{r:.8f}", "source": src})
        out[t] = {"status": "written", "path": str(path), "rows": len(rets), "source": src}
    return out
