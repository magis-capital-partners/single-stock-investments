"""Darwin allocation universe resolvers."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .config import ROOT

SP500_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents.json"
SP500_LIQUIDITY_PATH = (
    ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_options_liquidity.json"
)
RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"

# Markets / exchanges excluded from covered-call liquidity book
ADR_OTC_MARKETS = {"OTC"}
ADR_OTC_EXCHANGES = {"OTC", "PINK", "OTCMKTS", "OTCQB", "OTCQX"}

DEFAULT_LIQUID_BUCKETS = frozenset({"A", "B"})
LIQUIDITY_STALE_DAYS = 30


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


def _parse_as_of(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_liquidity_doc(path: Path | None = None) -> dict:
    p = path or SP500_LIQUIDITY_PATH
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_liquidity_map(path: Path | None = None) -> dict[str, dict]:
    """Per-ticker liquidity rows keyed by SPX ticker (plus BRK aliases)."""
    doc = load_liquidity_doc(path)
    raw = doc.get("tickers") or {}
    out: dict[str, dict] = {}
    for k, v in raw.items():
        u = str(k).strip().upper()
        if not u or not isinstance(v, dict):
            continue
        out[u] = v
        if "." in u:
            out[u.replace(".", "-")] = v
        if "-" in u:
            out[u.replace("-", ".")] = v
    return out


def liquidity_meta(path: Path | None = None) -> dict:
    doc = load_liquidity_doc(path)
    as_of = doc.get("as_of")
    d = _parse_as_of(as_of)
    age_days = (date.today() - d).days if d else None
    stale_after = int(doc.get("stale_after_days") or LIQUIDITY_STALE_DAYS)
    stale = age_days is None or age_days > stale_after
    summary = doc.get("summary") or {}
    return {
        "as_of": as_of,
        "source": doc.get("source"),
        "stale": stale,
        "age_days": age_days,
        "stale_after_days": stale_after,
        "eligible_buckets": doc.get("eligible_buckets") or sorted(DEFAULT_LIQUID_BUCKETS),
        "bucket_counts": summary.get("bucket_counts"),
        "eligible_ab": summary.get("eligible_ab"),
        "ticker_count": summary.get("ticker_count") or len(doc.get("tickers") or {}),
        "path": str(path or SP500_LIQUIDITY_PATH),
    }


def liquidity_is_stale(path: Path | None = None) -> bool:
    return bool(liquidity_meta(path).get("stale"))


def _registry_keys(registry: dict) -> list[str]:
    holdings = registry.get("holdings") or {}
    return sorted(holdings.keys())


def filter_to_sp500(tickers: list[str], spx: set[str] | None = None) -> list[str]:
    members = spx if spx is not None else load_sp500_tickers()
    if not members:
        return []
    return [t for t in tickers if str(t).upper() in members]


def _holding_meta(registry: dict, ticker: str) -> dict:
    return (registry.get("holdings") or {}).get(ticker) or {}


def is_adr_or_otc(registry: dict, ticker: str) -> bool:
    h = _holding_meta(registry, ticker)
    market = str(h.get("market") or "").upper()
    exchange = str(h.get("exchange") or "").upper()
    if market in ADR_OTC_MARKETS:
        return True
    if exchange in ADR_OTC_EXCHANGES:
        return True
    return False


def filter_adr_otc(tickers: list[str], registry: dict) -> tuple[list[str], list[str]]:
    keep: list[str] = []
    dropped: list[str] = []
    for t in tickers:
        if is_adr_or_otc(registry, t):
            dropped.append(t)
        else:
            keep.append(t)
    return keep, dropped


def filter_to_liquid(
    tickers: list[str],
    liquid_map: dict[str, dict] | None = None,
    buckets: set[str] | frozenset[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (kept, liquidity_miss, no_options)."""
    m = liquid_map if liquid_map is not None else load_liquidity_map()
    allow = set(buckets) if buckets is not None else set(DEFAULT_LIQUID_BUCKETS)
    keep: list[str] = []
    liq_miss: list[str] = []
    no_opts: list[str] = []
    for t in tickers:
        row = m.get(str(t).upper()) or m.get(t) or {}
        bucket = str(row.get("liquidity_bucket") or "D").upper()
        has_options = row.get("has_options")
        if has_options is False:
            no_opts.append(t)
            continue
        if bucket not in allow:
            liq_miss.append(t)
            continue
        keep.append(t)
    return keep, liq_miss, no_opts


def has_returns_csv(ticker: str) -> bool:
    key = ticker.replace(".", "_")
    return (RETURNS_DIR / f"{key}.csv").exists() or (RETURNS_DIR / f"{ticker}.csv").exists()


def resolve_universe_detail(
    spec: str,
    registry: dict,
    as_of: str | None = None,
    base_tickers: list[str] | None = None,
    liquid_buckets: set[str] | frozenset[str] | None = None,
) -> dict:
    """Resolve universe with exclusion metadata (Phase A)."""
    _ = as_of  # reserved for historical constituent files
    base = list(base_tickers) if base_tickers is not None else _registry_keys(registry)
    key = (spec or "registry_holdings").strip().lower()
    spx = load_sp500_tickers()
    liq_meta = liquidity_meta()
    liquid_map = load_liquidity_map()
    buckets = set(liquid_buckets) if liquid_buckets is not None else set(DEFAULT_LIQUID_BUCKETS)

    not_in_sp500 = [t for t in base if str(t).upper() not in spx]
    in_sp500 = [t for t in base if str(t).upper() in spx]

    liquidity_fallback = False
    spec_effective = key
    adr_otc: list[str] = []
    liquidity_miss: list[str] = []
    no_options: list[str] = []
    returns_missing: list[str] = []

    if key in ("registry_holdings", "holdings", ""):
        tickers = sorted(base)
        spec_effective = "registry_holdings"
    elif key in ("registry_sp500", "sp500", "registry_spx"):
        tickers = sorted(in_sp500)
        spec_effective = "registry_sp500"
    elif key in ("registry_sp500_liquid", "sp500_liquid", "registry_spx_liquid"):
        # Fail closed to registry_sp500 when liquidity file missing/stale
        if not liquid_map or liq_meta.get("stale"):
            liquidity_fallback = True
            tickers = sorted(in_sp500)
            spec_effective = "registry_sp500"
        else:
            after_adr, adr_otc = filter_adr_otc(in_sp500, registry)
            keep, liquidity_miss, no_options = filter_to_liquid(after_adr, liquid_map, buckets)
            tickers = sorted(keep)
            spec_effective = "registry_sp500_liquid"
    elif "liquid" in key and "sp500" in key:
        if not liquid_map or liq_meta.get("stale"):
            liquidity_fallback = True
            tickers = sorted(in_sp500)
            spec_effective = "registry_sp500"
        else:
            after_adr, adr_otc = filter_adr_otc(in_sp500, registry)
            keep, liquidity_miss, no_options = filter_to_liquid(after_adr, liquid_map, buckets)
            tickers = sorted(keep)
            spec_effective = "registry_sp500_liquid"
    elif "sp500" in key:
        tickers = sorted(in_sp500)
        spec_effective = "registry_sp500"
    else:
        tickers = sorted(base)
        spec_effective = key or "registry_holdings"

    # Returns coverage among eligible (informational; does not drop from universe)
    returns_missing = [t for t in tickers if not has_returns_csv(t)]

    # Coverage gate for CC decision-grade (plan Phase A)
    with_returns = len(tickers) - len(returns_missing)
    coverage_gate_ok = len(tickers) >= 20 and with_returns >= 20

    by_reason = {
        "not_in_sp500": len(not_in_sp500) if "sp500" in spec_effective or "sp500" in key else 0,
        "adr_otc": len(adr_otc),
        "liquidity_miss": len(liquidity_miss),
        "no_options": len(no_options),
        "returns_missing": len(returns_missing),
    }
    # When not on an SPX spec, not_in_sp500 is N/A for exclusion of the book
    if "sp500" not in key and "sp500" not in spec_effective:
        by_reason["not_in_sp500"] = 0
        not_in_sp500 = []

    samples = {
        "not_in_sp500": not_in_sp500[:12],
        "adr_otc": adr_otc[:12],
        "liquidity_miss": liquidity_miss[:12],
        "no_options": no_options[:12],
        "returns_missing": returns_missing[:12],
    }

    return {
        "tickers": tickers,
        "spec_requested": key or "registry_holdings",
        "spec_effective": spec_effective,
        "liquidity_fallback": liquidity_fallback,
        "liquidity": liq_meta,
        "eligible_count": len(tickers),
        "eligible_with_returns": with_returns,
        "coverage_gate_ok": coverage_gate_ok,
        "coverage_gate": {"min_names": 20, "min_with_returns": 20},
        "by_reason": by_reason,
        "samples": samples,
        "excluded_total": sum(by_reason.values()),
    }


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
      - registry_sp500_liquid: registry ∩ SPX ∩ liquidity buckets A/B
        (falls back to registry_sp500 if liquidity file missing/stale >30d)
    """
    return resolve_universe_detail(spec, registry, as_of=as_of, base_tickers=base_tickers)["tickers"]


def universe_exclusion_sample(
    registry: dict,
    included: list[str],
    limit: int = 12,
) -> list[str]:
    all_keys = _registry_keys(registry)
    inc = set(included)
    excluded = [t for t in all_keys if t not in inc]
    return excluded[:limit]


def compute_universe_exclusions(
    registry: dict,
    included: list[str],
    spec: str,
    detail: dict | None = None,
    research_eligibility_miss: list[str] | None = None,
) -> dict:
    """Structured exclusions for serving / dashboard (Phase A)."""
    d = detail or resolve_universe_detail(spec, registry)
    research_miss = list(research_eligibility_miss or [])
    by_reason = dict(d.get("by_reason") or {})
    by_reason["research_eligibility_miss"] = len(research_miss)
    samples = dict(d.get("samples") or {})
    samples["research_eligibility_miss"] = research_miss[:12]
    return {
        "eligible_count": d.get("eligible_count", len(included)),
        "eligible_with_returns": d.get("eligible_with_returns"),
        "excluded_total": sum(by_reason.values()),
        "by_reason": by_reason,
        "samples": samples,
        "liquidity_fallback": bool(d.get("liquidity_fallback")),
        "spec_requested": d.get("spec_requested"),
        "spec_effective": d.get("spec_effective"),
        "liquidity": d.get("liquidity"),
        "coverage_gate_ok": d.get("coverage_gate_ok"),
        "coverage_gate": d.get("coverage_gate"),
    }
