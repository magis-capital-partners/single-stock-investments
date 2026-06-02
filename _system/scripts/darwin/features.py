"""Build Marvin feature vectors per holding (Phase 1)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

import sys

sys_path = ROOT / "_system" / "scripts"
if str(sys_path) not in sys.path:
    sys.path.insert(0, str(sys_path))

from dated_md import dated_md_label, latest_dated_md  # noqa: E402

CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
HOLDINGS_PATH = ROOT / "_system" / "portfolio" / "holdings.md"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"holdings": {}, "watchlist": {}}


def load_classification() -> dict[str, dict]:
    if CLASS_PATH.exists():
        return json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    return {}


def parse_holdings() -> dict[str, dict]:
    reg = load_registry()
    meta: dict[str, dict] = {}
    for ticker, h in (reg.get("holdings") or {}).items():
        meta[ticker] = {"company": h.get("company", ticker), "market": h.get("market", "—")}
    if meta:
        return meta
    if not HOLDINGS_PATH.exists():
        return meta
    in_table = False
    for line in HOLDINGS_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith("| Ticker |"):
            in_table = True
            continue
        if not in_table or not line.startswith("|") or line.startswith("|--------"):
            continue
        parts = [c.strip() for c in line.split("|")[1:-1]]
        if len(parts) >= 4 and parts[0] not in ("—", "-"):
            meta[parts[0]] = {"company": parts[2], "market": parts[3]}
    return meta


def parse_classification_from_thesis(ticker_dir: Path) -> dict | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    fields = {}
    for key, label in [
        ("archetype", r"Archetype"),
        ("moat", r"Moat"),
        ("dhando", r"Dhando"),
        ("stance", r"Stance"),
        ("cycle", r"Cycle"),
        ("implied_irr", r"Implied 7yr IRR"),
        ("irr_method", r"IRR method"),
        ("lawrence_bucket", r"Lawrence bucket"),
    ]:
        m = re.search(rf"\*\*{label}\*\*[^|]*\|\s*([^\|]+)", text)
        if m:
            fields[key] = m.group(1).strip()
    return fields if fields else None


def classification_for(ticker: str, ticker_dir: Path, portfolio: dict[str, dict]) -> dict:
    from_thesis = parse_classification_from_thesis(ticker_dir)
    from_json = portfolio.get(ticker, {})
    merged = {**(from_thesis or {}), **from_json}
    # Registry stance (hold/core) wins over stale thesis watch when both exist
    reg = load_registry().get("holdings", {}).get(ticker, {}).get("classification") or {}
    for key in ("stance", "archetype", "moat", "dhando", "cycle"):
        if reg.get(key) and reg[key] not in ("-", "—", "pending"):
            merged[key] = reg[key]
    defaults = {
        "archetype": "unknown",
        "moat": "unproven",
        "dhando": "pending",
        "stance": "watch",
        "cycle": "—",
        "implied_irr": "pending",
    }
    return {k: merged.get(k, defaults.get(k, "—")) for k in defaults}


def one_line_thesis(ticker_dir: Path) -> str | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## One-line thesis\s*\n\s*\n(.+?)(?:\n\n|\Z)", text, re.DOTALL)
    if not m:
        return None
    return re.sub(r"\*\*", "", m.group(1).strip())


def _completeness_stub(ticker_dir: Path) -> int:
    score = 0
    if (ticker_dir / "README.md").exists():
        score += 20
    if (ticker_dir / "research").exists():
        score += 15
    pdfs = sum(1 for _ in ticker_dir.rglob("*.pdf"))
    if pdfs >= 10:
        score += 25
    if (ticker_dir / "INDEX.csv").exists() or (ticker_dir / "document-index.csv").exists():
        score += 15
    if (ticker_dir / "_download_log.txt").exists():
        score += 15
    return min(score, 100)

ARCHETYPES = [
    "compounder",
    "croupier",
    "serial_acquirer",
    "platform",
    "holding_co",
    "optionality",
    "turnaround",
    "infrastructure",
    "unknown",
]
MOATS = ["widening", "stable", "eroding", "unproven", "n/a"]
DHANDO = ["full", "partial", "none", "pending"]
STANCES = ["core", "accumulate", "hold", "watch", "trim", "exit"]
BUCKETS = ["pricing_power", "multi_sided", "other", "yield", "volume"]


def _one_hot(value: str, choices: list[str]) -> list[float]:
    v = (value or "unknown").lower().replace(" ", "_")
    return [1.0 if v == c else 0.0 for c in choices]


def _parse_irr_pct(val) -> float | None:
    if val is None:
        return None
    m = re.match(r"(-?\d+(?:\.\d+)?)", str(val).strip())
    return float(m.group(1)) if m else None


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except ValueError:
        return None


def load_valuation(ticker_dir: Path) -> dict | None:
    for name in ("valuation.json", "irr_model.json"):
        p = ticker_dir / "research" / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def feature_row(
    ticker: str,
    holdings_meta: dict,
    portfolio_class: dict,
    as_of: str | None = None,
    registry: dict | None = None,
) -> dict:
    ticker_dir = ROOT / ticker
    classification = classification_for(ticker, ticker_dir, portfolio_class)
    if as_of:
        from .pit import effective_as_of, load_valuation_as_of

        eff = effective_as_of(as_of, 0)
        val = load_valuation_as_of(ticker_dir, eff) or {}
        if registry:
            h = (registry.get("holdings") or {}).get(ticker, {})
            cl = h.get("classification") or {}
            for key in ("stance", "archetype", "moat", "dhando", "cycle"):
                if cl.get(key) and cl[key] not in ("-", "—", "pending"):
                    classification[key] = cl[key]
    else:
        val = load_valuation(ticker_dir) or {}
    ge = val.get("growth_explanation") or {}
    fa = ge.get("falsifier_adjusted") or {}
    triggered = fa.get("triggered") or ge.get("falsifiers_triggered") or []
    if isinstance(triggered, list):
        falsifier_count = len(triggered)
    else:
        falsifier_count = int(triggered) if triggered else 0

    irr_base = classification.get("analysis_irr_pct")
    if irr_base is None:
        irr_base = _parse_irr_pct(classification.get("implied_irr"))
    scenarios = val.get("scenarios") or val.get("results") or {}
    irr_bear = None
    irr_bull = None
    if "bear" in scenarios:
        irr_bear = scenarios["bear"].get("return_pct")
    if "bull" in scenarios:
        irr_bull = scenarios["bull"].get("return_pct")
    ir = val.get("implied_return") or {}
    if irr_base is None:
        irr_base = ir.get("base_pct")
    if irr_bear is None:
        irr_bear = ir.get("bear_pct")
    if irr_bull is None:
        irr_bull = ir.get("bull_pct")
    irr_fals = fa.get("irr_pct") or ir.get("falsifier_adjusted_pct")

    research = ticker_dir / "research"
    if as_of and research.exists():
        from .pit import latest_dated_md_as_of

        dive = latest_dated_md_as_of(research, "deep_dive", as_of)
    else:
        dive = latest_dated_md(research, "deep_dive") if research.exists() else None
    dive_date = dated_md_label(dive) if dive else None

    completeness = _completeness_stub(ticker_dir)

    hr = val.get("human_review") or {}
    human_pending = not val.get("approved_stance") and (
        bool(hr) or bool((val.get("stance_proposal") or {}).get("suggested"))
    )

    meta = holdings_meta.get(ticker, {})
    from .narrative import narrative_features_for_row

    narr = narrative_features_for_row(ticker, one_line_thesis(ticker_dir), as_of=as_of)

    vector = (
        [irr_base or 0.0, irr_bear or irr_base or 0.0, irr_bull or irr_base or 0.0, irr_fals or irr_base or 0.0]
        + narr["narrative_embedding"]
        + _one_hot(classification.get("archetype"), ARCHETYPES)
        + _one_hot(classification.get("moat"), MOATS)
        + _one_hot(classification.get("dhando"), DHANDO)
        + _one_hot(classification.get("stance"), STANCES)
        + _one_hot(classification.get("lawrence_bucket"), BUCKETS)
        + [
            completeness / 100.0,
            min((falsifier_count or 0) / 5.0, 1.0),
            1.0 if human_pending else 0.0,
            min((_days_since(dive_date) or 365) / 365.0, 2.0),
        ]
    )

    names = (
        ["irr_base", "irr_bear", "irr_bull", "irr_falsifier"]
        + [f"narr_{i}" for i in range(len(narr["narrative_embedding"]))]
        + [f"archetype_{a}" for a in ARCHETYPES]
        + [f"moat_{m}" for m in MOATS]
        + [f"dhando_{d}" for d in DHANDO]
        + [f"stance_{s}" for s in STANCES]
        + [f"bucket_{b}" for b in BUCKETS]
        + ["completeness", "falsifier_norm", "human_review_pending", "staleness_years"]
    )

    return {
        "ticker": ticker,
        "company": meta.get("company", ticker),
        "market": meta.get("market", "—"),
        "classification": classification,
        "irr_base_pct": irr_base,
        "irr_bear_pct": irr_bear,
        "irr_bull_pct": irr_bull,
        "irr_falsifier_pct": irr_fals,
        "falsifier_count": falsifier_count,
        "completeness": completeness,
        "days_since_deep_dive": _days_since(dive_date),
        "deep_dive_date": dive_date,
        "feature_as_of": as_of,
        "one_line_thesis": one_line_thesis(ticker_dir),
        "human_review_pending": human_pending,
        "narrative_embedding": narr["narrative_embedding"],
        "narrative_snippet_len": narr["narrative_snippet_len"],
        "feature_names": names,
        "feature_vector": vector,
    }


def holdings_universe() -> list[str]:
    reg = load_registry()
    holdings = sorted((reg.get("holdings") or {}).keys())
    if holdings:
        return holdings
    return sorted(parse_holdings().keys())


def build_features() -> dict:
    return build_features_as_of(None)


def build_features_as_of(as_of: str | None) -> dict:
    holdings_meta = parse_holdings()
    reg = load_registry()
    for t, h in (reg.get("holdings") or {}).items():
        holdings_meta.setdefault(t, {"company": h.get("company", t), "market": h.get("market", "—")})
    portfolio_class = load_classification()
    if as_of:
        from .pit import effective_as_of, holdings_universe_as_of, load_registry_snapshot_as_of

        eff = effective_as_of(as_of, 0)
        snap_reg = load_registry_snapshot_as_of(eff) or reg
        tickers = holdings_universe_as_of(eff, snap_reg)
        reg = snap_reg
    else:
        tickers = holdings_universe()
    rows = [feature_row(t, holdings_meta, portfolio_class, as_of=as_of, registry=reg) for t in tickers]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "ticker_count": len(rows),
        "feature_dim": len(rows[0]["feature_vector"]) if rows else 0,
        "feature_names": rows[0]["feature_names"] if rows else [],
        "tickers": rows,
    }


def rows_at_rebalance(
    rebalance_date: str,
    lag_days: int = 0,
    prefer_snapshot: bool = True,
) -> list[dict]:
    """PIT feature rows for one rebalance date."""
    from .pit import effective_as_of, load_features_snapshot_as_of

    eff = effective_as_of(rebalance_date, lag_days)
    if prefer_snapshot:
        snap = load_features_snapshot_as_of(eff)
        if snap and snap.get("tickers"):
            snap_day = (snap.get("generated_at") or "")[:10]
            if snap_day and snap_day <= eff:
                return snap["tickers"]
    return build_features_as_of(eff)["tickers"]
