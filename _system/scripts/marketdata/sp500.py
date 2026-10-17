"""S&P 500 membership from the committed constituents snapshot."""
from __future__ import annotations

import json
from pathlib import Path

from .config import ROOT

SP500_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents.json"


def load_sp500_tickers(path: Path | None = None) -> set[str]:
    """Return S&P 500 ticker set with BRK.B / BRK-B style aliases."""
    p = path or SP500_PATH
    if not p.exists():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    raw = data.get("tickers") or []
    out: set[str] = set()
    for t in raw:
        u = str(t).strip().upper()
        if not u:
            continue
        out.add(u)
        if "." in u:
            out.add(u.replace(".", "-"))
        if "-" in u:
            out.add(u.replace("-", "."))
    return out


def sp500_meta(path: Path | None = None) -> dict:
    p = path or SP500_PATH
    if not p.exists():
        return {"as_of": None, "source": None, "count": 0}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "as_of": data.get("as_of"),
        "source": data.get("source"),
        "count": data.get("count") or len(data.get("tickers") or []),
    }
