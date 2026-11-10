#!/usr/bin/env python3
"""Publish a small company overview, a lazy signal index and bounded evidence shards.

Reads cached files only. It never fetches market data or contacts a broker. The
source stamp describes the observations; rebuilding these projections does not
make an old observation new. History is baselined on first publication.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "inflections.v1"
BUCKETS = 32
ACTIVE = {"accelerating", "decelerating", "upshift", "downshift"}
LABELS = {
    "revenues": "Revenue", "revenue": "Revenue", "operating_income": "Operating income",
    "cfo": "Operating cash flow", "net_income": "Net income", "eps_basic": "EPS",
    "op_margin": "Operating margin", "cfo_margin": "Cash conversion",
    "core_business": "Core business", "burn_rate": "Cash burn",
}
DOMAINS = {
    "revenues": "revenue", "revenue": "revenue", "operating_income": "profitability",
    "net_income": "profitability", "eps_basic": "profitability", "op_margin": "profitability",
    "cfo": "cash_flow", "cfo_margin": "cash_flow", "burn_rate": "cash_flow",
}
BALANCE = {"cash", "total_assets", "stockholders_equity", "long_term_debt"}
RATIOS = {"op_margin", "cfo_margin"}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def period_date(value) -> date | None:
    text = str(value or "")
    try:
        if re.fullmatch(r"\d{4}-Q[1-4]", text):
            year, quarter = int(text[:4]), int(text[-1])
            month = quarter * 3
            return date(year, month, calendar.monthrange(year, month)[1])
        if re.fullmatch(r"\d{4}-\d{2}", text):
            year, month = map(int, text.split("-"))
            return date(year, month, calendar.monthrange(year, month)[1])
        return date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        return None


def metric_period(metric: dict) -> str | None:
    for key in ("latest_period", "as_of", "period"):
        if period_date(metric.get(key)):
            return str(metric[key])
    for point in reversed(metric.get("points") or []):
        if isinstance(point, dict) and period_date(point.get("period")):
            return str(point["period"])
    return None


def source_time(value) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def base_metric(metric: str) -> str:
    return str(metric).removeprefix("growth_regime.").removesuffix(".peer_relative")


def pct(value) -> str:
    n = number(value)
    return "unavailable" if n is None else f"{n * 100:+.1f}%"


def level(value, base="", unit="") -> str:
    n = number(value)
    if n is None:
        return "unavailable"
    if base in RATIOS:
        return f"{n * 100:.1f}%"
    if unit == "share_pct":
        return f"{n:.2f}%"
    if unit == "usd_per_contract":
        return f"${n:,.3f} per contract"
    suffix = {"contracts_per_day": " contracts/day", "shares_per_day": " shares/day"}.get(unit, "")
    return f"{n:,.2f}{suffix}".removesuffix(".00")


def evidence_kind(metric: dict) -> str:
    source, kind = metric.get("source"), metric.get("signal_type")
    base = base_metric(metric.get("metric", ""))
    if kind == "peer_relative" or source == "peer_relative":
        return "peers"
    if kind == "estimate_revision" or source == "earnings_revision":
        return "expectations"
    if metric.get("tier") == "context" or source in {"respiratory_panel", "news_flow"}:
        return "context"
    if metric.get("tier") == "excluded" or base in BALANCE:
        return "balance_sheet"
    if source == "issuer_operating" or metric.get("tier") == "operating":
        return "operating"
    if kind == "regime":
        return "history"
    return "business"


def describe(metric: dict, kind: str, effect: str) -> tuple[str, str]:
    """Keep unlike comparisons and raw/smoothed changes explicitly separate."""
    base = base_metric(metric.get("metric", ""))
    label = LABELS.get(base, str(metric.get("label") or base).replace("_", " "))
    latest, prior = number(metric.get("growth_latest")), number(metric.get("growth_prior"))
    current, previous = number(metric.get("level_latest")), number(metric.get("level_prior"))
    comparison = f"Prior YoY growth {pct(prior)}; latest YoY growth {pct(latest)}."
    if kind == "peers":
        median = metric.get("peer_median")
        median = prior if median is None else median
        return (f"{label}: company growth {pct(latest)} vs peer median {pct(median)}.",
                f"Same comparison basis: YoY growth; {metric.get('peer_count') or 'unspecified'} peers. Peer reporting periods may differ.")
    if kind == "expectations":
        return (f"Reported EPS surprise: {pct(latest)} vs consensus.",
                f"Prior report surprise {pct(prior)}; latest {pct(latest)}. These are reported earnings surprises, not forward estimate revisions.")
    if kind == "context":
        return (str(metric.get("human_summary") or f"{label}: {pct(latest)} YoY."),
                "External demand or news context; excluded from the business assessment.")
    if kind == "operating":
        change = (f"{latest:+.2f} percentage points YoY" if latest is not None else "No prior-year comparison") if metric.get("yoy_basis") == "percentage_points" else f"{pct(latest)} YoY"
        return (f"{label}: {level(current, base, metric.get('unit', ''))}.", change + ". Reported operating observation; no quarterly persistence claim.")
    if metric.get("composite"):
        members = ", ".join(LABELS.get(base_metric(m), m) for m in metric.get("composite_members") or [])
        return (f"{members or label} trends are {effect} together.",
                "Combined signal. Component observations are shown separately below; one component's growth rate does not describe the whole group.")
    if current is not None and previous is not None and (current < 0 or previous < 0):
        if current < 0 and previous < 0:
            noun = "Cash outflow" if base in {"cfo", "burn_rate"} else "Loss"
            verb = "narrowed" if current > previous else "widened" if current < previous else "was unchanged"
            remaining = label if label == "EPS" else label.lower()
            return (f"{noun} {verb}; {remaining} remains negative.",
                    f"Prior reported value {level(previous, base)}; latest {level(current, base)}. Filing units; percentages over negative bases need care.")
        return (f"{label} {'turned positive' if current >= 0 else 'turned negative'}.",
                f"Prior reported value {level(previous, base)}; latest {level(current, base)}. A sign change makes percentage growth difficult to interpret.")
    if base in RATIOS and current is not None:
        change = f" Change {(current - previous) * 100:+.1f} percentage points between reported quarters." if previous is not None else ""
        return (f"{label} trend {effect}; latest level {level(current, base)}.",
                f"Prior level {level(previous, base)}; latest {level(current, base)}.{change} The signal assesses smoothed YoY growth of this ratio.")
    if kind == "history":
        place = "above" if metric.get("direction") == "upshift" else "below" if metric.get("direction") == "downshift" else "near"
        return (f"{label} growth is {place} the company's usual range.",
                f"Latest YoY growth {pct(latest)}; historical median {pct(metric.get('baseline_median'))}. The normal band also accounts for historical variation.")
    if metric.get("direction") in ACTIVE:
        raw_change = latest - prior if latest is not None and prior is not None else None
        up = metric.get("direction") in {"accelerating", "upshift"}
        disagreement = raw_change is not None and ((up and raw_change < 0) or (not up and raw_change > 0))
        prefix = "Smoothed " if disagreement else ""
        note = " The smoothed history and the latest two growth rates point in different directions." if disagreement else ""
        return f"{prefix}{label.lower() if prefix else label} growth trend is {effect}.", comparison + note
    return f"{label}: no qualifying growth change.", comparison


def normalize_metric(ticker: str, metric: dict, index: int, max_age: int) -> dict:
    base = base_metric(metric.get("metric", ""))
    kind = evidence_kind(metric)
    rising = metric.get("direction") in {"accelerating", "upshift"}
    falling = metric.get("direction") in {"decelerating", "downshift"}
    inverse = metric.get("lower_is_better") is True or base in {"burn_rate", "cost_ratio", "leverage"}
    effect = ("weakening" if inverse else "improving") if rising else ("improving" if inverse else "weakening") if falling else "steady"
    # Negative-denominator ratios describe shrinking/growing losses by their
    # absolute levels. A sign flip remains an artifact and never enters a headline.
    previous, latest = number(metric.get("level_prior")), number(metric.get("level_latest"))
    if previous is not None and latest is not None and previous < 0 and latest < 0 and kind in {"business", "history"}:
        effect = "improving" if latest > previous else "weakening" if latest < previous else "steady"
    summary, comparison = describe(metric, kind, effect)
    reasons = []
    if metric.get("stale"):
        reasons.append("source_stale")
    if metric.get("artifact"):
        reasons.append("volatile_base")
    if previous is not None and latest is not None and previous * latest < 0:
        if "volatile_base" not in reasons:
            reasons.append("volatile_base")
    if metric.get("collapsed_into"):
        reasons.append("duplicate_component")
    if not metric.get("display"):
        reasons.append("not_selected")
    if metric.get("revenue_proxy") and base in {"revenues", "revenue"}:
        reasons.append("revenue_proxy")
        summary = "Revenue proxy: " + summary
    period = metric_period(metric)
    if not period:
        reasons.append("period_unavailable")
    support = metric.get("signal_tier") if metric.get("signal_tier") in {"confirmed", "emerging"} and kind in {"business", "history"} else "observation"
    candidate = kind in {"business", "history"} and bool(DOMAINS.get(base) or metric.get("composite")) and metric.get("direction") in ACTIVE and support in {"confirmed", "emerging"} and metric.get("material") is not False
    identity = hashlib.sha256(f"{ticker}|{metric.get('metric')}|{metric.get('source')}|{metric.get('signal_type')}|{index}".encode()).hexdigest()[:16]
    return {
        "id": identity, "metric": metric.get("metric"), "label": LABELS.get(base, metric.get("label") or base),
        "kind": kind, "domain": DOMAINS.get(base, "core_business" if metric.get("composite") else kind),
        "source": metric.get("source") or "unspecified", "period": period,
        "effect": effect, "support": support, "summary": summary, "comparison": comparison,
        "support_basis": metric.get("confirmation_basis") or ("two_quarters" if kind == "history" and support == "confirmed" else "components" if metric.get("composite") and support == "confirmed" else "unspecified"),
        "candidate": candidate, "reasons": reasons, "max_age_days": max_age,
        "primary": metric.get("tier") == "primary", "strength": number(metric.get("strength")),
        "members": metric.get("composite_members") or [], "ttm_agrees": metric.get("ttm_agrees"),
    }


def eligible(signal: dict, as_of: date) -> bool:
    period = period_date(signal.get("period"))
    return bool(signal.get("candidate") and not signal.get("reasons") and period and 0 <= (as_of - period).days <= signal["max_age_days"])


def assess(signals: list[dict], as_of: date, data_period: str | None) -> tuple[str, list[dict]]:
    candidates = [s for s in signals if eligible(s, as_of)]
    parents = [s for s in candidates if s["members"]]
    candidates = [s for s in candidates if not any(s["metric"] in p["members"] and s["effect"] == p["effect"] for p in parents)]
    effects = {s["effect"] for s in candidates} & {"improving", "weakening"}
    if len(effects) == 2:
        direction = "mixed"
    elif effects:
        direction = next(iter(effects))
    else:
        period = period_date(data_period)
        direction = "no_shift" if period and 0 <= (as_of - period).days <= 200 else "insufficient"
    candidates.sort(key=lambda s: (not s["primary"], s["support"] != "confirmed", -(period_date(s["period"]) or date.min).toordinal(), s["metric"]))
    return direction, candidates


def tracked_rows(registry: dict) -> list[dict]:
    rows = {}
    for group in ("holdings", "watchlist"):
        for ticker, entry in (registry.get(group) or {}).items():
            rows[str(ticker).upper()] = {"ticker": str(ticker).upper(), "company": (entry or {}).get("company") or ticker}
    return list(rows.values())


def signature(signals: list[dict], raw_by_id: dict) -> str:
    observations = []
    for signal in signals:
        raw = raw_by_id[signal["id"]]
        observations.append({
            "metric": signal["metric"], "source": signal["source"], "kind": signal["kind"],
            "effect": signal["effect"], "support": signal["support"], "period": signal["period"],
            **{key: raw.get(key) for key in ("basis", "growth_latest", "growth_prior", "level_latest")},
        })
    return hashlib.sha256(json.dumps(sorted(observations, key=lambda v: (v["metric"], v["source"])), sort_keys=True).encode()).hexdigest()


def build_assets(kpi: dict, tickers: list[dict], previous: dict | None = None, *, as_of: date | None = None) -> tuple[dict, dict, dict, dict]:
    as_of = as_of or datetime.now(timezone.utc).date()
    previous = previous or {}
    prior_records = previous.get("records", {}) if previous.get("schema_version") == SCHEMA else {}
    old_stamp, new_stamp = source_time(previous.get("source_generated_at")), source_time(kpi.get("generated_at"))
    if old_stamp and (new_stamp is None or new_stamp < old_stamp):
        raise ValueError("Refusing to replace Inflections with an older source snapshot")
    raw_entries = kpi.get("by_ticker")
    if not isinstance(raw_entries, dict) or not raw_entries:
        raise ValueError("KPI source unavailable; preserving the last successful Inflections snapshot")
    # Identity metadata only. Holdings membership is supplied by the authenticated
    # SPA at runtime; brokerage state is never copied into these static artifacts.
    universe = {}
    for row in tickers:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            universe[ticker] = row
    if not universe:
        raise ValueError("Tracked universe unavailable; refusing to publish an empty overview")
    max_age = int((kpi.get("coverage") or {}).get("stale_max_days") or 200)
    companies, index_rows, records = [], [], {}
    evidence = {f"{i:02x}": {} for i in range(BUCKETS)}
    for ticker, row in sorted(universe.items()):
        entry = raw_entries.get(ticker) or {}
        raw_metrics = [m for m in entry.get("metrics") or [] if isinstance(m, dict)]
        normalized = [normalize_metric(ticker, m, i, max_age) for i, m in enumerate(raw_metrics)]
        raw_by_id = {s["id"]: m for s, m in zip(normalized, raw_metrics)}
        periods = [metric_period(m) for m in raw_metrics if evidence_kind(m) in {"business", "history"} and metric_period(m)]
        latest_period = max(periods, key=lambda p: period_date(p) or date.min) if periods else None
        usable_periods = [metric_period(m) for m in raw_metrics if evidence_kind(m) in {"business", "history"} and metric_period(m) and not m.get("stale") and not m.get("artifact")]
        data_period = max(usable_periods, key=lambda p: period_date(p) or date.min) if usable_periods else None
        direction, current = assess(normalized, as_of, data_period)
        digest = signature(current, raw_by_id)
        old = prior_records.get(ticker)
        change = old.get("change") if old else None
        if old is None and prior_records and current:
            change = {"kind": "new", "observed_at": as_of.isoformat()}
        if old and old.get("fingerprint") != digest:
            # Losing coverage is not resolution of a business change. Aging out
            # without a new report is not a newly observed business event either.
            newer_report = (period_date(latest_period) or date.min) > (period_date(old.get("period")) or date.min)
            if current and (newer_report or old.get("period") == latest_period):
                change = {"kind": "new" if not old.get("active") else "changed", "observed_at": as_of.isoformat()}
            elif old.get("active") and direction == "no_shift" and newer_report:
                change = {"kind": "resolved", "observed_at": as_of.isoformat()}
        records[ticker] = {"fingerprint": digest, "active": bool(current), "period": latest_period, "change": change}
        bucket = f"{int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16) % BUCKETS:02x}"
        aliases = sorted({str(row.get(key)).upper() for key in ("display_ticker", "quote_ticker") if row.get(key)} - {ticker})
        # Candidate metadata allows the reader to re-evaluate age on the viewing
        # date without downloading history or trusting cached series_age_days.
        company = {
            "ticker": ticker, "company": row.get("company") or ticker, "aliases": aliases,
            "data_tier": entry.get("data_tier") or "none", "latest_period": latest_period,
            "data_period": data_period, "max_age_days": max_age,
            "signals": [s for s in normalized if s["candidate"] and not s["reasons"]],
            "signal_count": sum(s["effect"] != "steady" for s in normalized),
            "suppressed_count": sum(bool(s["reasons"]) for s in normalized),
            "evidence_ref": f"data/inflection_evidence/{bucket}.json", "change": change,
        }
        companies.append(company)
        for s in normalized:
            index_rows.append({"ticker": ticker, **s})
        evidence[bucket][ticker] = [{**s, "raw": raw_by_id[s["id"]]} for s in normalized]
    # Source stamp changes alone do not become business-change badges. Include
    # content as well as the stamp to catch corrected same-stamp publications.
    snapshot = hashlib.sha256(json.dumps({"schema": SCHEMA, "source": kpi, "universe": sorted(universe)}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:20]
    common = {"schema_version": SCHEMA, "snapshot_id": snapshot, "source_generated_at": kpi.get("generated_at"), "evaluated_at": as_of.isoformat(), "max_age_days": max_age}
    overview = {**common, "companies": companies, "signals_ref": "data/inflection_signals.json"}
    signals = {**common, "signals": index_rows}
    history = {"schema_version": SCHEMA, "source_generated_at": kpi.get("generated_at"), "records": records}
    buckets = {key: {**common, "by_ticker": values} for key, values in evidence.items()}
    return overview, signals, buckets, history


def read_object(path: Path) -> dict:
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    return result if isinstance(result, dict) else {}


def write_json(path: Path, doc: dict) -> None:
    encoded = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == encoded:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def write_inflection_assets(kpi: dict, tickers: list[dict], data_dir: Path, *, as_of: date | None = None) -> dict:
    history_path = data_dir / "inflection_history.json"
    overview, signals, buckets, history = build_assets(kpi, tickers, read_object(history_path), as_of=as_of)
    for bucket, doc in buckets.items():
        write_json(data_dir / "inflection_evidence" / f"{bucket}.json", doc)
    write_json(data_dir / "inflection_signals.json", signals)
    # Publish the overview last; readers reject mismatched evidence snapshots.
    write_json(data_dir / "inflection_overview.json", overview)
    write_json(history_path, history)
    return {"companies": len(overview["companies"]), "signals": len(signals["signals"]), "overview_bytes": (data_dir / "inflection_overview.json").stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dashboard/data")
    parser.add_argument("--registry", type=Path, default=ROOT / "_system/portfolio/registry.json")
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(write_inflection_assets(read_object(args.data_dir / "kpi_trends.json"), tracked_rows(read_object(args.registry)), args.data_dir, as_of=args.as_of)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
