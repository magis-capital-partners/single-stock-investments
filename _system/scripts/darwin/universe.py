"""Darwin allocation universe resolvers."""
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


def _registry_keys(registry: dict) -> list[str]:
    holdings = registry.get("holdings") or {}
    return sorted(holdings.keys())


def filter_to_sp500(tickers: list[str], spx: set[str] | None = None) -> list[str]:
    members = spx if spx is not None else load_sp500_tickers()
    if not members:
        return []
    return [t for t in tickers if str(t).upper() in members]


def resolve_universe(
    spec: str,
    registry: dict,
    as_of: str | None = None,
    base_tickers: list[str] | None = None,
) -> list[str]:
    """Resolve mandate universe spec to ticker list.

    Specs:
      - registry_holdings: all registry holdings (or base_tickers if provided)
      - registry_sp500: registry holdings ∩ S&P 500
    """
    _ = as_of  # reserved for historical constituent files
    base = list(base_tickers) if base_tickers is not None else _registry_keys(registry)
    key = (spec or "registry_holdings").strip().lower()
    if key in ("registry_holdings", "holdings", ""):
        return sorted(base)
    if key in ("registry_sp500", "sp500", "registry_spx"):
        return sorted(filter_to_sp500(base))
    # Unknown spec: fail closed to empty rather than silently using full book
    return sorted(filter_to_sp500(base)) if "sp500" in key else sorted(base)


def universe_exclusion_sample(
    registry: dict,
    included: list[str],
    limit: int = 12,
) -> list[str]:
    all_keys = _registry_keys(registry)
    inc = set(included)
    excluded = [t for t in all_keys if t not in inc]
    return excluded[:limit]
