"""Shared KPI signal enhancements: freshness, growth regime, leadership risk."""
from __future__ import annotations

import csv
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSIDER_DIR = ROOT / "_system" / "reference" / "market-data" / "insider"
INSIDER_MANIFEST = INSIDER_DIR / "manifest.json"

# Series older than this are stale (suppress inflection display).
STALE_SERIES_MAX_DAYS = 200

# Growth regime: YoY below ticker baseline for N consecutive quarters.
REGIME_MIN_GROWTH_POINTS = 8
REGIME_CONFIRM_QUARTERS = 2
REGIME_SIGMA = 1.0

MATERIALITY_ACCEL_FLOORS: dict[str, float] = {
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

# Declines matter earlier than accelerations (asymmetric materiality).
MATERIALITY_DECEL_FLOORS: dict[str, float] = {
    "revenues": 0.02,
    "revenue": 0.02,
    "operating_income": 0.02,
    "net_income": 0.02,
    "eps_basic": 0.02,
    "cfo": 0.02,
    "op_margin": 0.005,
    "cfo_margin": 0.005,
    "news_flow": 0.0,
}

GOVERNANCE_RE = re.compile(
    r"\b("
    r"ceo|cfo|chief executive|chief financial|"
    r"step(?:ped)? down|departure|transition|resign|succession|interim|"
    r"executive change|leadership change|names .* (?:ceo|cfo)"
    r")\b",
    re.I,
)
EXEC_TITLE_RE = re.compile(
    r"\b(ceo|cfo|chief|president|chairman|chairwoman|chairperson|director|officer)\b",
    re.I,
)


def metric_base_name(metric: str) -> str:
    return str(metric or "").split(".")[-1]


def parse_date(period: str) -> datetime | None:
    try:
        return datetime.strptime(str(period)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def series_freshness(series: list[dict], *, now: datetime | None = None) -> dict:
    """Return latest period metadata for a quarterly series."""
    now = now or datetime.now(timezone.utc)
    periods = [str(p.get("period") or "")[:10] for p in series if p.get("period")]
    if not periods:
        return {"latest_period": None, "age_days": None, "stale": True}
    latest = max(periods)
    dt = parse_date(latest)
    if dt is None:
        return {"latest_period": latest, "age_days": None, "stale": True}
    age_days = (now.replace(tzinfo=None) - dt).days
    return {
        "latest_period": latest,
        "age_days": age_days,
        "stale": age_days > STALE_SERIES_MAX_DAYS,
    }


def passes_materiality(
    growth_latest: float | None,
    metric_key: str,
    *,
    direction: str = "steady",
) -> bool:
    if growth_latest is None:
        return False
    base = metric_base_name(metric_key)
    if direction == "decelerating" or (direction == "steady" and growth_latest < 0):
        floor = MATERIALITY_DECEL_FLOORS.get(base, 0.02)
    else:
        floor = MATERIALITY_ACCEL_FLOORS.get(base, 0.03)
    return abs(growth_latest) >= floor


def analyze_growth_regime(
    growths: list[tuple[str, float]],
    *,
    metric_key: str,
) -> dict | None:
    """First-derivative regime shift: YoY growth breaks below ticker baseline."""
    if len(growths) < REGIME_MIN_GROWTH_POINTS:
        return None

    periods = [p for p, _g in growths]
    gvals = [g for _p, g in growths]
    base = metric_base_name(metric_key)
    decel_floor = MATERIALITY_DECEL_FLOORS.get(base, 0.02)

    history = gvals[: -REGIME_CONFIRM_QUARTERS]
    recent = gvals[-REGIME_CONFIRM_QUARTERS:]
    recent_periods = periods[-REGIME_CONFIRM_QUARTERS:]

    if len(history) < 4:
        return None

    median = statistics.median(history)
    spread = statistics.pstdev(history) if len(history) >= 2 else abs(median) * 0.25 or 0.05
    down_threshold = median - REGIME_SIGMA * spread
    up_threshold = median + REGIME_SIGMA * spread

    rare_negative = median > 0.05 and any(g < 0 for g in recent)
    negative_quarters = sum(1 for g in recent if g < 0)

    direction: str | None = None
    signal_tier = "steady"
    label = ""

    if all(g < down_threshold and abs(g) >= decel_floor for g in recent):
        direction = "downshift"
        signal_tier = "confirmed"
        label = "Growth regime downshift"
    elif recent[-1] < down_threshold and abs(recent[-1]) >= decel_floor:
        direction = "downshift"
        signal_tier = "emerging"
        label = "Growth regime softening"
    elif rare_negative and negative_quarters >= REGIME_CONFIRM_QUARTERS:
        direction = "downshift"
        signal_tier = "confirmed"
        label = "Rare negative YoY quarter(s)"
    elif rare_negative and recent[-1] < 0 and abs(recent[-1]) >= decel_floor:
        direction = "downshift"
        signal_tier = "emerging"
        label = "Negative YoY growth"
    elif all(g > up_threshold for g in recent) and median <= up_threshold:
        direction = "upshift"
        signal_tier = "confirmed"
        label = "Growth regime upshift"
    elif recent[-1] > up_threshold and recent[-1] > median + spread:
        direction = "upshift"
        signal_tier = "emerging"
        label = "Growth regime strengthening"

    if direction is None:
        return None

    strength = abs(recent[-1] - median) / max(spread, decel_floor, 1e-9)
    return {
        "metric": f"growth_regime.{base}",
        "label": label,
        "signal_type": "regime",
        "direction": direction,
        "signal_tier": signal_tier,
        "tier": "primary" if base in {"revenues", "revenue", "operating_income", "cfo"} else "secondary",
        "basis": "yoy",
        "mode": "pct",
        "growth_latest": round(recent[-1], 4),
        "growth_prior": round(gvals[-REGIME_CONFIRM_QUARTERS - 1], 4) if len(gvals) > REGIME_CONFIRM_QUARTERS else round(recent[0], 4),
        "baseline_median": round(median, 4),
        "baseline_threshold": round(down_threshold if direction == "downshift" else up_threshold, 4),
        "strength": round(min(strength, 5.0), 3),
        "confidence": "high" if signal_tier == "confirmed" and strength >= 1.5 else "med",
        "material": True,
        "rare_negative": rare_negative,
        "as_of": recent_periods[-1],
        "display": False,
        "composite": False,
    }


def resolve_revenue_series(metrics: dict[str, list[dict]]) -> tuple[list[dict] | None, dict]:
    """Pick revenue series; fall back to operating_income proxy when revenue is stale."""
    revenue = metrics.get("revenues") or metrics.get("revenue")
    meta = {"proxy": False, "stale": False, "latest_period": None}

    if revenue:
        fresh = series_freshness(revenue)
        meta.update(fresh)
        if not fresh["stale"]:
            return revenue, meta
        meta["stale"] = True

    op_inc = metrics.get("operating_income")
    if op_inc:
        fresh = series_freshness(op_inc)
        if not fresh["stale"]:
            meta.update({"proxy": True, "stale": False, **fresh})
            return op_inc, meta

    return revenue, meta


def cross_metric_freshness(metrics: dict[str, list[dict]]) -> dict[str, dict]:
    """Freshness metadata per canonical metric key."""
    out: dict[str, dict] = {}
    for key in ("revenues", "operating_income", "net_income", "cfo", "eps_basic"):
        series = metrics.get(key)
        if series:
            out[key] = series_freshness(series)
    return out


def _load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default if default is not None else {}


def _insider_csv_path(csv_ref: str | None) -> Path | None:
    if not csv_ref:
        return None
    ref = Path(str(csv_ref).replace("\\", "/"))
    if ref.parts and ref.parts[0] == "insider":
        return INSIDER_DIR.parent / ref
    return INSIDER_DIR / ref


def _parse_news_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return parse_date(text)


def compute_leadership_risk(
    ticker: str,
    news_doc: dict | None,
    *,
    now: datetime | None = None,
    lookback_days: int = 120,
) -> dict:
    """Score governance/news and executive insider selling clusters."""
    now = now or datetime.now(timezone.utc)
    ticker = ticker.upper()
    score = 0.0
    factors: list[dict] = []

    for item in (news_doc or {}).get("items") or []:
        tickers = {str(t).upper() for t in (item.get("tickers") or [])}
        if ticker not in tickers:
            continue
        published = _parse_news_date(item.get("published_utc"))
        if published is None:
            continue
        pub = published.replace(tzinfo=None) if published.tzinfo else published
        age = (now.replace(tzinfo=None) - pub).days
        if age > lookback_days:
            continue
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        if GOVERNANCE_RE.search(text):
            score += 2.0
            factors.append(
                {
                    "type": "governance_news",
                    "as_of": pub.strftime("%Y-%m-%d"),
                    "title": str(item.get("title") or "")[:120],
                }
            )

    manifest = _load_json(INSIDER_MANIFEST, {})
    meta = ((manifest.get("tickers") or {}).get(ticker) or {})
    csv_path = _insider_csv_path(meta.get("csv"))
    exec_sell_value = 0.0
    exec_sell_count = 0
    if csv_path and csv_path.exists():
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    code = (row.get("transaction_code") or "").upper()
                    acquired = (row.get("acquired_disposed") or "").upper()
                    is_sale = code == "S" or acquired == "D"
                    if not is_sale:
                        continue
                    title = row.get("title") or row.get("officer_title") or ""
                    if not EXEC_TITLE_RE.search(title) and not EXEC_TITLE_RE.search(row.get("insider") or ""):
                        continue
                    tx_date = _parse_news_date(row.get("transaction_date") or row.get("filing_date"))
                    if tx_date is None:
                        continue
                    tx = tx_date.replace(tzinfo=None) if tx_date.tzinfo else tx_date
                    age = (now.replace(tzinfo=None) - tx).days
                    if age > lookback_days:
                        continue
                    try:
                        value = abs(float(row.get("value_usd") or 0))
                    except (TypeError, ValueError):
                        value = 0.0
                    if value < 25000:
                        continue
                    exec_sell_count += 1
                    exec_sell_value += value
        except OSError:
            pass

    if exec_sell_count >= 2:
        score += 1.5
        factors.append(
            {
                "type": "executive_selling_cluster",
                "as_of": now.strftime("%Y-%m-%d"),
                "title": f"{exec_sell_count} executive sales (${exec_sell_value:,.0f}) in {lookback_days}d",
            }
        )
    elif exec_sell_count == 1 and exec_sell_value >= 250000:
        score += 1.0
        factors.append(
            {
                "type": "executive_sale",
                "as_of": now.strftime("%Y-%m-%d"),
                "title": f"Executive sale (${exec_sell_value:,.0f})",
            }
        )

    if score >= 3.0:
        level = "elevated"
        label = "Leadership / governance risk elevated"
    elif score >= 1.0:
        level = "watch"
        label = "Leadership / governance on watch"
    else:
        level = "none"
        label = "No leadership risk flags"

    return {
        "score": round(score, 2),
        "level": level,
        "label": label,
        "factors": factors[:5],
    }


def peer_relative_signal(
    latest_growth: float,
    peer_growths: list[float],
    *,
    metric_key: str = "revenues",
    min_peers: int = 3,
) -> dict | None:
    """Flag when YoY growth materially trails investment-sleeve peers."""
    clean = [g for g in peer_growths if g is not None]
    if len(clean) < min_peers:
        return None
    median = statistics.median(clean)
    mad = statistics.median([abs(g - median) for g in clean]) or 0.01
    threshold = median - REGIME_SIGMA * mad
    if latest_growth >= threshold:
        return None
    gap = threshold - latest_growth
    strength = min(3.0, gap / max(mad, 0.01))
    return {
        "metric": f"{metric_base_name(metric_key)}.peer_relative",
        "label": f"{metric_base_name(metric_key).replace('_', ' ').title()} vs sleeve peers",
        "direction": "downshift",
        "signal_type": "peer_relative",
        "signal_tier": "confirmed" if gap >= mad * 1.5 else "emerging",
        "tier": "primary",
        "display": True,
        "strength": round(strength, 3),
        "growth_latest": latest_growth,
        "growth_prior": median,
        "basis": "yoy",
        "mode": "pct",
        "peer_median": round(median, 4),
        "peer_threshold": round(threshold, 4),
        "peer_count": len(clean),
    }


def earnings_revision_signal(events: list[dict]) -> dict | None:
    """Estimate-revision layer from reported EPS surprises (beat/miss streaks)."""
    reported: list[tuple[str, float]] = []
    for event in events:
        if not event.get("reported"):
            continue
        actual = event.get("actual_eps")
        estimate = event.get("estimated_eps")
        if actual is None or estimate is None:
            continue
        try:
            actual_f = float(actual)
            est_f = float(estimate)
        except (TypeError, ValueError):
            continue
        if abs(est_f) < 1e-9:
            continue
        surprise = (actual_f - est_f) / abs(est_f)
        date = str(event.get("date") or "")[:10]
        reported.append((date, surprise))

    if len(reported) < 2:
        return None
    reported.sort(key=lambda x: x[0])
    surprises = [s for _d, s in reported[-4:]]
    latest = surprises[-1]
    prior = surprises[-2]
    revision = latest - prior

    if latest < -0.05 and prior < -0.05:
        direction = "decelerating"
        label = "Consecutive EPS misses vs consensus"
    elif latest > 0.05 and prior > 0.05:
        direction = "accelerating"
        label = "Consecutive EPS beats vs consensus"
    elif revision <= -0.10:
        direction = "decelerating"
        label = "Estimate revision down (EPS surprise worsened)"
    elif revision >= 0.10:
        direction = "accelerating"
        label = "Estimate revision up (EPS surprise improved)"
    else:
        return None

    return {
        "metric": "eps_revision",
        "label": label,
        "direction": direction,
        "signal_type": "estimate_revision",
        "signal_tier": "confirmed" if abs(revision) >= 0.15 else "emerging",
        "tier": "secondary",
        "display": True,
        "strength": round(min(3.0, abs(revision) * 5), 3),
        "growth_latest": round(latest, 4),
        "growth_prior": round(prior, 4),
        "basis": "surprise",
        "mode": "pct",
        "surprise_streak": len(surprises),
    }
