#!/usr/bin/env python3
"""Build dashboard/data/kpi_trends.json - second-derivative KPI signals per ticker.

Sources, in order of trust:
  - _system/reference/market-data/fundamentals/{TICKER}.json
        SEC XBRL companyfacts quarterly series (build_fundamental_series.py).
        Real fiscal period ends; quarterly scope enforced at extraction.
  - dashboard/data/equity_models.json  (model observation series)
  - dashboard/data/portfolio_news.json (monthly news-flow counts)

Quarterly fundamentals are analyzed on a year-over-year basis: growth compares
each quarter to the same quarter a year earlier (killing seasonality), and the
second derivative is the change in YoY growth between consecutive quarters.
Signals pass through smoothing, materiality gates, persistence confirmation,
TTM cross-check, metric-tier filtering, correlated-metric collapse, and a
per-ticker display cap so the Inflections view stays salient.

The legacy filing_facts_*.json source was removed: those extracts carry no
fiscal period or scope metadata, which produced false inflections (duplicate
snapshots + quarterly/annual mixing).
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from kpi_signal_enhancements import (
    analyze_growth_regime,
    compute_leadership_risk,
    cross_metric_freshness,
    passes_materiality,
    resolve_revenue_series,
    series_freshness,
    STALE_SERIES_MAX_DAYS,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "kpi_trends.json"
FUNDAMENTALS_DIR = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
EQUITY_MODELS_PATH = ROOT / "dashboard" / "data" / "equity_models.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
NEWS_HISTORY_PATH = ROOT / "_system" / "reference" / "market-data" / "news_flow_history.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

MIN_POINTS = 4
MAX_POINTS = 8
NEWS_WINDOW_MONTHS = 8

# YoY analysis knobs
YOY_MIN_QUARTERS = 8
YOY_MIN_GROWTH_POINTS = 4
YOY_MATCH_WINDOW = (330, 400)
GROWTH_OUTLIER_CAP = 5.0
DENOMINATOR_FLOOR_FRAC = 0.05

# Signal quality knobs
VOL_MULTIPLIER = 1.0
SMOOTH_WINDOW = 3
HIGH_CONFIDENCE_MULT = 2.0
MAX_PRIMARY_DISPLAY = 2
MAX_SECONDARY_DISPLAY = 1

METRIC_TIER_PRIMARY = frozenset({"revenues", "revenue", "operating_income", "cfo", "op_margin", "cfo_margin"})
METRIC_TIER_SECONDARY = frozenset({"net_income", "eps_basic", "news_flow"})
METRIC_TIER_EXCLUDED = frozenset({"cash", "total_assets", "stockholders_equity", "long_term_debt"})
CORE_COLLAPSE_METRICS = frozenset({"revenues", "revenue", "operating_income", "cfo"})
REGIME_METRICS = frozenset({"revenues", "revenue", "operating_income", "cfo", "net_income", "eps_basic"})

MATERIALITY_FLOORS: dict[str, float] = {
    "revenues": 0.03,
    "revenue": 0.03,
    "operating_income": 0.05,
    "net_income": 0.05,
    "eps_basic": 0.05,
    "cfo": 0.05,
    "op_margin": 0.01,
    "cfo_margin": 0.01,
    "news_flow": 0.0,
}

BMS_WEIGHTS: dict[str, float] = {
    "revenues": 0.40,
    "revenue": 0.40,
    "operating_income": 0.30,
    "cfo": 0.20,
    "op_margin": 0.10,
}

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "EPS (basic)",
    "cfo": "Operating cash flow",
    "total_assets": "Total assets",
    "stockholders_equity": "Stockholders' equity",
    "long_term_debt": "Long-term debt",
    "cash": "Cash",
    "news_flow": "News flow",
    "op_margin": "Operating margin",
    "cfo_margin": "Cash conversion (CFO/revenue)",
    "core_business": "Core business",
    "growth_regime.revenues": "Revenue growth regime",
    "growth_regime.revenue": "Revenue growth regime",
    "growth_regime.operating_income": "Operating income growth regime",
    "growth_regime.cfo": "Cash flow growth regime",
    "growth_regime.net_income": "Net income growth regime",
    "growth_regime.eps_basic": "EPS growth regime",
}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_date(period: str) -> datetime | None:
    try:
        return datetime.strptime(str(period)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def metric_base_name(metric: str) -> str:
    return str(metric or "").split(".")[-1]


def metric_tier(metric: str) -> str:
    base = metric_base_name(metric)
    if base in METRIC_TIER_PRIMARY:
        return "primary"
    if base in METRIC_TIER_SECONDARY:
        return "secondary"
    if base in METRIC_TIER_EXCLUDED:
        return "excluded"
    return "primary"


def strength(metric: dict) -> float:
    return abs(metric.get("accel") or 0) / max(metric.get("threshold") or 1e-9, 1e-9)


def robust_vol(history: list[float]) -> float:
    """Median absolute deviation scaled to approximate std dev."""
    if not history:
        return 0.0
    if len(history) == 1:
        return abs(history[0])
    med = statistics.median(history)
    deviations = [abs(x - med) for x in history]
    mad = statistics.median(deviations)
    return mad * 1.4826 if mad > 0 else abs(history[-1])


def rolling_median(values: list[float], window: int = SMOOTH_WINDOW) -> list[float]:
    if len(values) < window:
        return list(values)
    out: list[float] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(values[i])
        else:
            chunk = values[i + 1 - window : i + 1]
            out.append(statistics.median(chunk))
    return out


def classify_accel(latest_accel: float, history: list[float], *, floor: float) -> tuple[str, float]:
    vol = robust_vol(history)
    threshold = max(floor, VOL_MULTIPLIER * vol)
    if latest_accel > threshold:
        return "accelerating", threshold
    if latest_accel < -threshold:
        return "decelerating", threshold
    return "steady", threshold


def signal_tier_from_accels(accels: list[float], direction: str, threshold: float) -> str:
    if direction == "steady" or len(accels) < 2:
        return "steady" if direction == "steady" else "emerging"
    prev = accels[-2]
    if direction == "accelerating" and prev > threshold:
        return "confirmed"
    if direction == "decelerating" and prev < -threshold:
        return "confirmed"
    return "emerging"


def enrich_analysis(
    analysis: dict,
    *,
    metric_key: str,
    raw_accels: list[float],
    ttm_analysis: dict | None = None,
    series_meta: dict | None = None,
) -> dict:
    """Attach tier, persistence, materiality, strength, freshness, and TTM agreement."""
    direction = analysis["direction"]
    threshold = analysis["threshold"]
    material = passes_materiality(analysis.get("growth_latest"), metric_key, direction=direction)
    tier = signal_tier_from_accels(raw_accels, direction, threshold)
    if not material and direction != "steady":
        direction = "steady"
        tier = "steady"

    fresh = series_meta or {}
    stale = bool(fresh.get("stale"))
    if stale and direction != "steady":
        tier = "steady"
        direction = "steady"

    ttm_agrees: bool | None = None
    if ttm_analysis and analysis.get("basis") == "yoy":
        q_dir = direction
        t_dir = ttm_analysis.get("direction")
        if q_dir in ("accelerating", "decelerating"):
            if t_dir == q_dir:
                ttm_agrees = True
            elif t_dir in ("accelerating", "decelerating"):
                ttm_agrees = False

    if tier == "emerging" and ttm_agrees is True:
        tier = "confirmed"

    accel = analysis.get("accel")
    out = {
        **analysis,
        "direction": direction,
        "signal_tier": tier,
        "tier": metric_tier(metric_key),
        "material": material,
        "strength": round(strength({**analysis, "direction": direction}), 3),
        "confidence": (
            "high"
            if accel is not None and threshold and abs(accel) >= HIGH_CONFIDENCE_MULT * threshold
            else "med"
        ),
        "ttm_agrees": ttm_agrees,
        "display": False,
        "composite": False,
        "stale": stale,
        "latest_period": fresh.get("latest_period"),
        "series_age_days": fresh.get("age_days"),
        "revenue_proxy": bool(fresh.get("proxy")),
    }
    return out


def compute_yoy_growths(
    ordered: list[tuple[str, float]],
    dates: list[datetime | None],
    values: list[float],
) -> tuple[list[tuple[str, float]], int]:
    nonzero = [abs(v) for v in values if abs(v) > 1e-9]
    scale = statistics.median(nonzero) if nonzero else 0.0
    denom_floor = max(1e-9, DENOMINATOR_FLOOR_FRAC * scale)

    growths: list[tuple[str, float]] = []
    suspect = 0
    lo, hi = YOY_MATCH_WINDOW
    for i in range(len(ordered)):
        match = None
        for j in range(i - 1, -1, -1):
            days = (dates[i] - dates[j]).days
            if lo <= days <= hi:
                match = j
                break
            if days > hi:
                break
        if match is None:
            continue
        prev, cur = values[match], values[i]
        if abs(prev) < denom_floor:
            suspect += 1
            continue
        growth = (cur - prev) / abs(prev)
        if abs(growth) > GROWTH_OUTLIER_CAP:
            suspect += 1
            continue
        growths.append((ordered[i][0], growth))
    return growths, suspect


def analyze_growth_values(
    gvals: list[float],
    *,
    floor: float,
    metric_key: str,
    basis: str,
    mode: str,
    points: list[dict],
    suspect: int = 0,
    series_meta: dict | None = None,
) -> dict | None:
    min_growth = YOY_MIN_GROWTH_POINTS if basis == "yoy" else 3
    if len(gvals) < min_growth:
        return None

    raw_accels = [b - a for a, b in zip(gvals, gvals[1:])]
    if basis == "yoy":
        smoothed = rolling_median(gvals)
        accels = [b - a for a, b in zip(smoothed, smoothed[1:])]
    else:
        smoothed = gvals
        accels = raw_accels
    direction, threshold = classify_accel(accels[-1], accels[:-1], floor=floor)

    analysis = {
        "direction": direction,
        "basis": basis,
        "growth_latest": round(gvals[-1], 4),
        "growth_prior": round(gvals[-2], 4),
        "growth_smoothed_latest": round(smoothed[-1], 4),
        "accel": round(accels[-1], 4),
        "accel_raw": round(raw_accels[-1], 4),
        "threshold": round(threshold, 4),
        "mode": mode,
        "suspect_points": suspect,
        "points": points,
    }
    return enrich_analysis(
        analysis,
        metric_key=metric_key,
        raw_accels=accels,
        series_meta=series_meta,
    )


def quarterly_to_ttm(ordered: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if len(ordered) < 4:
        return []
    return [(ordered[i][0], sum(v for _p, v in ordered[i - 3 : i + 1])) for i in range(3, len(ordered))]


def analyze_quarterly_yoy(
    series: list[dict],
    *,
    metric_key: str = "",
    series_meta: dict | None = None,
) -> dict | None:
    """Second derivative of year-over-year growth for a quarterly series."""
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    if len(ordered) < YOY_MIN_QUARTERS:
        return None

    meta = dict(series_meta or series_freshness(series))
    dates = [parse_date(p) for p, _v in ordered]
    values = [v for _p, v in ordered]
    growths, suspect = compute_yoy_growths(ordered, dates, values)
    if len(growths) < YOY_MIN_GROWTH_POINTS:
        return None

    gvals = [g for _p, g in growths]
    floor = MATERIALITY_FLOORS.get(metric_base_name(metric_key), 0.03)
    points = [{"period": p, "value": v} for p, v in ordered[-MAX_POINTS:]]

    result = analyze_growth_values(
        gvals,
        floor=floor,
        metric_key=metric_key,
        basis="yoy",
        mode="pct",
        points=points,
        suspect=suspect,
        series_meta=meta,
    )
    if result is None:
        return None

    ttm_ordered = quarterly_to_ttm(ordered)
    if len(ttm_ordered) >= YOY_MIN_QUARTERS:
        ttm_dates = [parse_date(p) for p, _v in ttm_ordered]
        ttm_values = [v for _p, v in ttm_ordered]
        ttm_growths, _ = compute_yoy_growths(ttm_ordered, ttm_dates, ttm_values)
        if len(ttm_growths) >= YOY_MIN_GROWTH_POINTS:
            ttm_gvals = [g for _p, g in ttm_growths]
            ttm_result = analyze_growth_values(
                ttm_gvals,
                floor=floor,
                metric_key=metric_key,
                basis="yoy",
                mode="pct",
                points=[{"period": p, "value": v} for p, v in ttm_ordered[-MAX_POINTS:]],
                series_meta=meta,
            )
            if ttm_result:
                smooth = rolling_median(gvals)
                ttm_accels = [b - a for a, b in zip(smooth, smooth[1:])] if len(smooth) > 1 else []
                base = {k: v for k, v in result.items() if k not in (
                    "signal_tier", "tier", "material", "strength", "confidence",
                    "ttm_agrees", "display", "composite", "stale", "latest_period",
                    "series_age_days", "revenue_proxy",
                )}
                result = enrich_analysis(
                    base,
                    metric_key=metric_key,
                    raw_accels=ttm_accels,
                    ttm_analysis=ttm_result,
                    series_meta=meta,
                )
                result["ttm_direction"] = ttm_result.get("direction")
                result["ttm_growth_latest"] = ttm_result.get("growth_latest")

    return result


def yoy_growth_series(series: list[dict]) -> list[tuple[str, float]]:
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    if len(ordered) < YOY_MIN_QUARTERS:
        return []
    dates = [parse_date(p) for p, _v in ordered]
    values = [v for _p, v in ordered]
    growths, _ = compute_yoy_growths(ordered, dates, values)
    return growths


def build_regime_metric(
    growths: list[tuple[str, float]],
    *,
    metric_key: str,
    series: list[dict],
    evidence_ref: str,
    series_meta: dict | None = None,
) -> dict | None:
    regime = analyze_growth_regime(growths, metric_key=metric_key)
    if not regime:
        return None
    meta = series_meta or series_freshness(series)
    if meta.get("stale"):
        return None
    regime.update(
        {
            "source": "sec_fundamentals",
            "evidence_ref": evidence_ref,
            "points": [
                {"period": str(x.get("period") or "")[:10], "value": x.get("value")}
                for x in series[-MAX_POINTS:]
                if x.get("period")
            ],
            "stale": False,
            "latest_period": meta.get("latest_period"),
            "series_age_days": meta.get("age_days"),
            "revenue_proxy": bool(meta.get("proxy")),
        }
    )
    return regime


def analyze_series(
    points: list[tuple[str, float]],
    *,
    mode: str = "pct",
    metric_key: str = "",
) -> dict | None:
    """Sequential first/second derivative for non-quarterly series."""
    cleaned: dict[str, float] = {}
    for period, value in points:
        if not period or value is None:
            continue
        cleaned[str(period)[:10]] = float(value)
    ordered = sorted(cleaned.items())[-MAX_POINTS:]
    if len(ordered) < MIN_POINTS:
        return None

    values = [v for _p, v in ordered]
    growths: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if mode == "diff":
            growths.append(cur - prev)
        else:
            if abs(prev) < 1e-9:
                return None
            growth = (cur - prev) / abs(prev)
            if abs(growth) > GROWTH_OUTLIER_CAP:
                return None
            growths.append(growth)
    if len(growths) < 3:
        return None

    floor = 1.0 if mode == "diff" else MATERIALITY_FLOORS.get(metric_base_name(metric_key), 0.02)
    return analyze_growth_values(
        growths,
        floor=floor,
        metric_key=metric_key,
        basis="seq",
        mode=mode,
        points=[{"period": p, "value": v} for p, v in ordered],
    )


def derive_ratio_series(numerator: list[dict], denominator: list[dict]) -> list[dict]:
    num_map = {
        str(p.get("period") or "")[:10]: to_float(p.get("value"))
        for p in numerator
        if to_float(p.get("value")) is not None
    }
    denom_map = {
        str(p.get("period") or "")[:10]: to_float(p.get("value"))
        for p in denominator
        if to_float(p.get("value")) is not None
    }
    out: list[dict] = []
    for period in sorted(set(num_map) & set(denom_map)):
        denom = denom_map[period]
        if denom is None or abs(denom) < 1e-9:
            continue
        out.append({"period": period, "value": num_map[period] / denom})
    return out


def collapse_core_signals(metrics: list[dict]) -> list[dict]:
    """When multiple core operating metrics align, emit one composite signal."""
    firing = [
        m
        for m in metrics
        if metric_base_name(m.get("metric") or "") in CORE_COLLAPSE_METRICS
        and m.get("direction") in ("accelerating", "decelerating")
        and m.get("signal_tier") in ("confirmed", "emerging")
        and m.get("tier") != "excluded"
    ]
    if len(firing) < 2:
        return metrics

    by_direction: dict[str, list[dict]] = {}
    for m in firing:
        by_direction.setdefault(m["direction"], []).append(m)

    composites: list[dict] = []
    for direction, group in by_direction.items():
        if len(group) < 2:
            continue
        group.sort(key=strength, reverse=True)
        tiers = {m.get("signal_tier") for m in group}
        signal_tier = "confirmed" if tiers == {"confirmed"} or (tiers <= {"confirmed", "emerging"} and "confirmed" in tiers) else "emerging"
        avg_strength = statistics.mean(strength(m) for m in group)
        lead = group[0]
        composite = {
            "metric": "core_business",
            "label": METRIC_LABELS["core_business"],
            "source": lead.get("source"),
            "evidence_ref": lead.get("evidence_ref"),
            "direction": direction,
            "signal_tier": signal_tier,
            "tier": "primary",
            "basis": lead.get("basis"),
            "mode": "pct",
            "growth_latest": lead.get("growth_latest"),
            "growth_prior": lead.get("growth_prior"),
            "accel": lead.get("accel"),
            "threshold": lead.get("threshold"),
            "strength": round(avg_strength, 3),
            "confidence": "high" if avg_strength >= HIGH_CONFIDENCE_MULT else "med",
            "material": True,
            "ttm_agrees": any(m.get("ttm_agrees") for m in group if m.get("ttm_agrees") is not None) or None,
            "composite": True,
            "composite_members": [m.get("metric") for m in group],
            "display": True,
            "points": lead.get("points") or [],
        }
        composites.append(composite)
        for m in group:
            m["display"] = False
            m["collapsed_into"] = "core_business"

    return composites + metrics


def apply_display_cap(metrics: list[dict]) -> None:
    """Cap visible inflections: composites first, then regime, then 2 primary + 1 secondary."""
    for m in metrics:
        if m.get("composite"):
            continue
        if m.get("stale"):
            m["display"] = False
            continue
        if m.get("tier") == "excluded":
            m["display"] = False
            continue
        if m.get("signal_type") == "regime":
            continue
        if m.get("direction") not in ("accelerating", "decelerating", "downshift", "upshift"):
            m["display"] = False
            continue
        if m.get("signal_tier") == "steady":
            m["display"] = False
            continue
        if "display" not in m or m.get("collapsed_into"):
            m["display"] = False

    regime_candidates = sorted(
        [
            m
            for m in metrics
            if m.get("signal_type") == "regime"
            and not m.get("stale")
            and m.get("direction") in ("downshift", "upshift")
            and m.get("signal_tier") in ("confirmed", "emerging")
        ],
        key=lambda m: m.get("strength") or 0,
        reverse=True,
    )
    for m in regime_candidates[:1]:
        m["display"] = True

    candidates = [
        m
        for m in metrics
        if not m.get("composite")
        and m.get("signal_type") != "regime"
        and m.get("direction") in ("accelerating", "decelerating")
        and m.get("signal_tier") in ("confirmed", "emerging")
        and m.get("tier") != "excluded"
        and not m.get("collapsed_into")
        and not m.get("stale")
    ]
    primary = sorted([m for m in candidates if m.get("tier") == "primary"], key=strength, reverse=True)
    secondary = sorted([m for m in candidates if m.get("tier") == "secondary"], key=strength, reverse=True)

    shown = sum(1 for m in metrics if m.get("display"))
    for m in primary[: max(0, MAX_PRIMARY_DISPLAY - shown)]:
        m["display"] = True
        shown += 1
    for m in secondary[: max(0, MAX_SECONDARY_DISPLAY - (shown - sum(1 for x in metrics if x.get("display"))))]:
        if not m.get("display"):
            m["display"] = True


def compute_business_momentum(metrics: list[dict]) -> dict | None:
    score = 0.0
    weight_sum = 0.0
    for m in metrics:
        if m.get("stale"):
            continue
        base = metric_base_name(m.get("metric") or "")
        if m.get("signal_type") == "regime":
            if m.get("direction") == "downshift":
                sign = -1.0
                weight = BMS_WEIGHTS.get(base.replace("growth_regime.", ""), 0.25)
            elif m.get("direction") == "upshift":
                sign = 1.0
                weight = BMS_WEIGHTS.get(base.replace("growth_regime.", ""), 0.25)
            else:
                continue
            score += sign * weight * min(m.get("strength") or 1.0, 3.0)
            weight_sum += weight
            continue
        weight = BMS_WEIGHTS.get(base)
        if not weight or m.get("direction") not in ("accelerating", "decelerating"):
            continue
        sign = 1.0 if m["direction"] == "accelerating" else -1.0
        score += sign * weight * min(strength(m), 3.0)
        weight_sum += weight
    if weight_sum <= 0:
        return None
    normalized = score / weight_sum
    if normalized > 0.15:
        direction = "accelerating"
        label = "Business momentum improving"
    elif normalized < -0.15:
        direction = "decelerating"
        label = "Business momentum fading"
    else:
        direction = "steady"
        label = "Business momentum neutral"
    return {
        "score": round(normalized, 3),
        "direction": direction,
        "label": label,
    }


def finalize_ticker_entry(entry: dict, *, leadership_risk: dict | None = None) -> None:
    metrics = entry.get("metrics") or []
    metrics[:] = collapse_core_signals(metrics)
    apply_display_cap(metrics)

    summary = {
        "accelerating": 0,
        "decelerating": 0,
        "steady": 0,
        "confirmed": 0,
        "emerging": 0,
        "displayed": 0,
        "regime_downshift": 0,
        "stale_suppressed": 0,
    }
    for m in metrics:
        direction = m.get("direction") or "steady"
        if m.get("signal_type") == "regime" and direction == "downshift":
            summary["regime_downshift"] += 1
        elif direction in summary:
            summary[direction] += 1
        tier = m.get("signal_tier")
        if tier in ("confirmed", "emerging"):
            summary[tier] += 1
        if m.get("stale") and m.get("direction") not in ("steady", None):
            summary["stale_suppressed"] += 1
        if m.get("display"):
            summary["displayed"] += 1

    entry["summary"] = summary
    entry["business_momentum"] = compute_business_momentum(metrics)
    if leadership_risk:
        entry["leadership_risk"] = leadership_risk


def fundamentals_series() -> dict[str, dict[str, list[dict]]]:
    """ticker -> metric -> quarterly series from the XBRL cache."""
    out: dict[str, dict[str, list[dict]]] = {}
    if not FUNDAMENTALS_DIR.is_dir():
        return out
    for path in sorted(FUNDAMENTALS_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        doc = load_json(path)
        metrics = doc.get("metrics") if isinstance(doc, dict) else None
        if not isinstance(metrics, dict):
            continue
        out[str(doc.get("ticker") or path.stem).upper()] = metrics
    return out


def equity_model_series(ticker: str, models_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Extract observation series (lists of {period, <numeric>}) from equity models."""
    entry = ((models_doc or {}).get("tickers") or {}).get(ticker) or {}
    forms = (entry.get("production") or {}).get("forms") or {}
    out: dict[str, list[tuple[str, float]]] = {}
    for form_key, form in forms.items():
        if not isinstance(form, dict):
            continue
        observations = form.get("observations")
        if not isinstance(observations, list):
            continue
        by_field: dict[str, list[tuple[str, float]]] = {}
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            period = obs.get("period")
            if not period:
                continue
            for field, raw in obs.items():
                if field == "period":
                    continue
                value = to_float(raw)
                if value is None:
                    continue
                by_field.setdefault(field, []).append((str(period)[:10], value))
        for field, points in by_field.items():
            out[f"{form_key}.{field}"] = points
    return out


def news_flow_series(news_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Monthly news item counts per ticker from the current feed window."""
    items = (news_doc or {}).get("items") or []
    counts: dict[str, dict[str, float]] = {}
    for item in items:
        published = str(item.get("published_utc") or "")[:7]
        if not published or len(published) != 7:
            continue
        for ticker in item.get("tickers") or []:
            bucket = counts.setdefault(str(ticker).upper(), {})
            bucket[published] = bucket.get(published, 0.0) + 1
    return {
        ticker: [(f"{m}-01", v) for m, v in sorted(by_month.items())]
        for ticker, by_month in counts.items()
    }


def merged_news_history(news_doc: dict, *, write: bool = True) -> dict[str, list[tuple[str, float]]]:
    """Merge the current 30-day feed into a persistent monthly history."""
    history = load_json(NEWS_HISTORY_PATH, {})
    by_ticker: dict[str, dict[str, float]] = {
        str(t).upper(): {str(m): float(v) for m, v in (months or {}).items()}
        for t, months in (history.get("by_ticker") or {}).items()
    }
    months_observed = set(history.get("months_observed") or [])

    current = news_flow_series(news_doc)
    for ticker, points in current.items():
        bucket = by_ticker.setdefault(ticker, {})
        for period, count in points:
            month = period[:7]
            months_observed.add(month)
            bucket[month] = max(bucket.get(month, 0.0), count)

    if write:
        NEWS_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEWS_HISTORY_PATH.write_text(
            json.dumps(
                {
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "months_observed": sorted(months_observed),
                    "by_ticker": by_ticker,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    usable_months = sorted(m for m in months_observed if m < this_month)
    out: dict[str, list[tuple[str, float]]] = {}
    for ticker, bucket in by_ticker.items():
        out[ticker] = [(f"{m}-01", bucket.get(m, 0.0)) for m in usable_months[-NEWS_WINDOW_MONTHS:]]
    return out


def build_trends() -> dict:
    models_doc = load_json(EQUITY_MODELS_PATH)
    news_doc = load_json(NEWS_PATH)
    news_series = merged_news_history(news_doc if isinstance(news_doc, dict) else {})
    fundamentals = fundamentals_series()
    registry = load_json(REGISTRY_PATH, {})
    universe = sorted((registry.get("holdings") or {}).keys())

    by_ticker: dict[str, dict] = {}
    suspect_excluded = 0

    def add_metric(ticker: str, metric: str, source: str, analysis: dict, evidence_ref: str | None) -> None:
        entry = by_ticker.setdefault(ticker, {"metrics": []})
        entry["metrics"].append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric_base_name(metric), metric.replace("_", " ").title()),
                "source": source,
                "evidence_ref": evidence_ref,
                **analysis,
            }
        )

    for ticker, metrics in sorted(fundamentals.items()):
        evidence_ref = f"_system/reference/market-data/fundamentals/{ticker}.json"
        freshness = cross_metric_freshness(metrics)
        revenue_series, rev_meta = resolve_revenue_series(metrics)
        derived: dict[str, list[dict]] = {}
        if revenue_series and not rev_meta.get("proxy"):
            if metrics.get("operating_income"):
                derived["op_margin"] = derive_ratio_series(metrics["operating_income"], revenue_series)
            if metrics.get("cfo"):
                derived["cfo_margin"] = derive_ratio_series(metrics["cfo"], revenue_series)

        all_metrics = {**metrics, **derived}
        growths_by_metric: dict[str, list[tuple[str, float]]] = {}

        for metric, series in sorted(all_metrics.items()):
            if metric == "revenues" and rev_meta.get("stale"):
                continue

            meta = freshness.get(metric) or series_freshness(series)
            if metric == "revenues" and rev_meta.get("proxy"):
                meta = {**rev_meta, "proxy": True}

            if metric in REGIME_METRICS and not meta.get("stale"):
                growths = yoy_growth_series(series)
                if growths:
                    growths_by_metric[metric] = growths

            analysis = analyze_quarterly_yoy(series, metric_key=metric, series_meta=meta)
            if analysis is None:
                continue

            suspect_excluded += analysis.pop("suspect_points", 0) or 0
            add_metric(ticker, metric, "sec_fundamentals", analysis, evidence_ref)

        for metric, growths in growths_by_metric.items():
            if metric not in REGIME_METRICS:
                continue
            series = all_metrics.get(metric) or []
            meta = freshness.get(metric) or series_freshness(series)
            regime = build_regime_metric(
                growths,
                metric_key=metric,
                series=series,
                evidence_ref=evidence_ref,
                series_meta=meta,
            )
            if regime:
                add_metric(ticker, regime["metric"], "sec_fundamentals", regime, evidence_ref)

    equity_model_tickers = set()
    for ticker in sorted(((models_doc or {}).get("tickers") or {}).keys()):
        for metric, points in equity_model_series(ticker, models_doc).items():
            analysis = analyze_series(points, mode="pct", metric_key=metric)
            if analysis:
                equity_model_tickers.add(ticker)
                add_metric(ticker, metric, "equity_model", analysis, "dashboard/data/equity_models.json")

    for ticker, points in news_series.items():
        analysis = analyze_series(points, mode="diff", metric_key="news_flow")
        if analysis and analysis["direction"] != "steady":
            add_metric(ticker, "news_flow", "news_flow", analysis, "dashboard/data/portfolio_news.json")

    confirmed_count = 0
    emerging_count = 0
    displayed_count = 0
    regime_count = 0
    stale_suppressed = 0
    leadership_elevated = 0
    strength_values: list[float] = []

    for ticker, entry in by_ticker.items():
        leadership = compute_leadership_risk(ticker, news_doc if isinstance(news_doc, dict) else {})
        finalize_ticker_entry(entry, leadership_risk=leadership)
        if leadership.get("level") in ("elevated", "watch"):
            leadership_elevated += 1
        for metric in entry.get("metrics") or []:
            if metric.get("signal_tier") == "confirmed":
                confirmed_count += 1
            elif metric.get("signal_tier") == "emerging":
                emerging_count += 1
            if metric.get("signal_type") == "regime" and metric.get("direction") == "downshift":
                regime_count += 1
            if metric.get("stale"):
                stale_suppressed += 1
            if metric.get("display"):
                displayed_count += 1
                strength_values.append(metric.get("strength") or 0)

    inflection_count = sum(
        1
        for entry in by_ticker.values()
        for metric in entry["metrics"]
        if metric.get("direction") != "steady" and metric.get("tier") != "excluded"
    )
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(by_ticker),
        "inflection_count": inflection_count,
        "coverage": {
            "universe": len(universe),
            "fundamentals_tickers": len(fundamentals),
            "equity_model_tickers": len(equity_model_tickers),
            "analyzed_tickers": len(by_ticker),
            "suspect_points_excluded": suspect_excluded,
            "confirmed_count": confirmed_count,
            "emerging_count": emerging_count,
            "displayed_count": displayed_count,
            "regime_downshift_count": regime_count,
            "stale_suppressed_count": stale_suppressed,
            "leadership_risk_watch": leadership_elevated,
            "avg_strength": round(statistics.mean(strength_values), 3) if strength_values else 0.0,
            "stale_max_days": STALE_SERIES_MAX_DAYS,
        },
        "by_ticker": by_ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KPI trend (second derivative) JSON.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build_trends()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cov = payload["coverage"]
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({payload['ticker_count']} tickers, {cov['displayed_count']} displayed / "
        f"{payload['inflection_count']} raw inflections, "
        f"confirmed {cov['confirmed_count']}, emerging {cov['emerging_count']}, "
        f"fundamentals {cov['fundamentals_tickers']}/{cov['universe']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
