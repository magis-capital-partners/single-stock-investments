"""Point-in-time helpers for Darwin backtests."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

VAL_HISTORY_DIR = "valuation_history"
PIT_DIR = ROOT / "_system" / "reference" / "market-data" / "pit"


def parse_iso_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def effective_as_of(as_of: str, lag_days: int = 0) -> str:
    """Last calendar day knowable at rebalance (publication lag)."""
    d = parse_iso_date(as_of)
    if not d:
        return as_of[:10]
    if lag_days <= 0:
        return d.strftime("%Y-%m-%d")
    return (d - timedelta(days=lag_days)).strftime("%Y-%m-%d")


def month_key(date_str: str) -> str:
    return date_str[:7]


def load_registry_raw() -> dict:
    path = ROOT / "_system" / "portfolio" / "registry.json"
    if not path.exists():
        return {"holdings": {}, "watchlist": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def holdings_universe_as_of(
    as_of: str,
    registry: dict | None = None,
    universe_spec: str = "registry_holdings",
) -> list[str]:
    """Holdings with onboarded <= as_of and not removed before as_of."""
    from .universe import resolve_universe

    reg = registry or load_registry_raw()
    cutoff = parse_iso_date(as_of)
    if not cutoff:
        base = sorted((reg.get("holdings") or {}).keys())
    else:
        out: list[str] = []
        for ticker, h in (reg.get("holdings") or {}).items():
            ob = parse_iso_date(h.get("onboarded"))
            if ob and ob > cutoff:
                continue
            rem = parse_iso_date(h.get("removed"))
            if rem and rem <= cutoff:
                continue
            out.append(ticker)
        base = sorted(out)
    return resolve_universe(universe_spec, reg, as_of=as_of, base_tickers=base)


def valuation_history_dir(ticker_dir: Path) -> Path:
    return ticker_dir / "research" / VAL_HISTORY_DIR


def archive_valuation_on_write(ticker_dir: Path, valuation: dict) -> Path | None:
    """Copy valuation.json into valuation_history/valuation_{as_of}.json."""
    as_of = valuation.get("as_of")
    if not as_of:
        return None
    hist = valuation_history_dir(ticker_dir)
    hist.mkdir(parents=True, exist_ok=True)
    dest = hist / f"valuation_{str(as_of)[:10]}.json"
    if not dest.exists():
        dest.write_text(json.dumps(valuation, indent=2) + "\n", encoding="utf-8")
    return dest


def load_valuation_as_of(ticker_dir: Path, as_of: str) -> dict | None:
    """Best valuation with as_of <= effective as_of."""
    lag = 0
    eff = effective_as_of(as_of, lag)
    eff_dt = parse_iso_date(eff)

    candidates: list[tuple[datetime, dict]] = []
    cur = ticker_dir / "research" / "valuation.json"
    if cur.exists():
        try:
            v = json.loads(cur.read_text(encoding="utf-8"))
            vdt = parse_iso_date(v.get("as_of"))
            if vdt and eff_dt and vdt <= eff_dt:
                candidates.append((vdt, v))
        except json.JSONDecodeError:
            pass

    hist = valuation_history_dir(ticker_dir)
    if hist.is_dir():
        for p in hist.glob("valuation_*.json"):
            m = re.search(r"valuation_(\d{4}-\d{2}-\d{2})\.json$", p.name)
            if not m:
                continue
            vdt = parse_iso_date(m.group(1))
            if not vdt or not eff_dt or vdt > eff_dt:
                continue
            try:
                candidates.append((vdt, json.loads(p.read_text(encoding="utf-8"))))
            except json.JSONDecodeError:
                continue

    legacy = ticker_dir / "research" / "irr_model.json"
    if legacy.exists() and not candidates:
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
            vdt = parse_iso_date(raw.get("as_of")) or datetime.min.replace(tzinfo=timezone.utc)
            if eff_dt and vdt <= eff_dt:
                candidates.append((vdt, raw))
        except json.JSONDecodeError:
            pass

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0].timestamp())
    return candidates[0][1]


def latest_dated_md_as_of(research: Path, prefix: str, as_of: str) -> Path | None:
    eff = effective_as_of(as_of, 0)
    eff_dt = parse_iso_date(eff)
    if not research.exists():
        return None
    best: tuple[datetime, Path] | None = None
    for p in research.glob(f"{prefix}_*.md"):
        m = re.search(r"_(\d{4}-\d{2}-\d{2})\.md$", p.name)
        if not m:
            continue
        pdt = parse_iso_date(m.group(1))
        if not pdt or not eff_dt or pdt > eff_dt:
            continue
        if best is None or pdt > best[0]:
            best = (pdt, p)
    return best[1] if best else None


def list_pit_snapshots(prefix: str) -> list[tuple[str, Path]]:
    if not PIT_DIR.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for p in PIT_DIR.glob(f"{prefix}_*.json"):
        m = re.search(rf"{prefix}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$", p.name)
        if m:
            out.append((m.group(1), p))
    return sorted(out, key=lambda x: x[0])


def load_features_snapshot_as_of(as_of: str) -> dict | None:
    """Nearest feature snapshot with snapshot_date <= as_of."""
    eff_dt = parse_iso_date(effective_as_of(as_of, 0))
    if not eff_dt:
        return None
    best: tuple[datetime, dict] | None = None
    for day, path in list_pit_snapshots("darwin_features"):
        sdt = parse_iso_date(day)
        if not sdt or sdt > eff_dt:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if best is None or sdt > best[0]:
            best = (sdt, data)
    return best[1] if best else None


def load_registry_snapshot_as_of(as_of: str) -> dict | None:
    eff_dt = parse_iso_date(effective_as_of(as_of, 0))
    if not eff_dt:
        return None
    best: tuple[datetime, dict] | None = None
    for day, path in list_pit_snapshots("registry"):
        sdt = parse_iso_date(day)
        if not sdt or sdt > eff_dt:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if best is None or sdt > best[0]:
            best = (sdt, data)
    return best[1] if best else None


def pit_mandate_cfg(mandate_doc: dict) -> dict:
    return mandate_doc.get("pit") or {}


def bootstrap_valuation_history(tickers: list[str]) -> int:
    """Archive current valuation.json into valuation_history/ for PIT backtests."""
    n = 0
    for ticker in tickers:
        ticker_dir = ROOT / ticker
        cur = ticker_dir / "research" / "valuation.json"
        if not cur.exists():
            continue
        try:
            val = json.loads(cur.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if archive_valuation_on_write(ticker_dir, val):
            n += 1
    return n
