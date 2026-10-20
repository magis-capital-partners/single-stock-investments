"""Turn operating-KPI points into kpi_trends metrics and shard rows.

Operating series stay visible when they are steady. The inflection list is
still only for accelerating and decelerating series. Levels live in
``operating_latest`` on the L0 summary.
"""
from __future__ import annotations

from collections import defaultdict

from operating_kpis.model import iter_stores

LABELS = {
    "options_adv": "Options ADV",
    "options_industry_adv": "Industry options ADV",
    "options_share": "Options market share",
    "options_rpc": "Options revenue per contract",
    "equities_adv": "Equities ADV",
    "equities_industry_adv": "Industry equities ADV",
    "equities_share": "Equities market share",
    "equities_capture": "Equities capture per 100 shares",
    "futures_ag_adv": "Agricultural futures ADV",
    "futures_ag_rpc": "Agricultural futures revenue per contract",
    "futures_financial_adv": "Financial futures ADV",
    "futures_financial_rpc": "Financial futures revenue per contract",
    "options_multilist_adv": "Multi-list options ADV",
    "options_index_adv": "Index options ADV",
    "options_multilist_share": "Multi-list options share",
    "options_multilist_rpc": "Multi-list options revenue per contract",
    "options_index_rpc": "Index options revenue per contract",
    "futures_adv": "Futures ADV",
    "futures_rpc": "Futures revenue per contract",
    "us_equities_adv": "U.S. equities ADV",
    "us_equities_share": "U.S. equities share",
    "spx_options_adv": "SPX options ADV",
    "vix_futures_adv": "VIX futures ADV",
    "total_adv": "Total ADV",
    "interest_rate_adv": "Interest-rate ADV",
    "equity_index_adv": "Equity-index ADV",
    "energy_adv": "Energy ADV",
    "agricultural_adv": "Agricultural ADV",
    "fx_adv": "Foreign-exchange ADV",
    "metals_adv": "Metals ADV",
    "equity_options_contracts": "Equity options contracts",
    "etf_options_contracts": "ETF options contracts",
    "index_options_contracts": "Index options contracts",
    "equity_options_adv": "Equity options ADV",
    "etf_options_adv": "ETF options ADV",
    "index_options_adv": "Index options ADV",
    "equity_etf_options_adv": "Equity and ETF options ADV",
}


def label_for(kpi: str) -> str:
    return LABELS.get(kpi, kpi.replace("_", " ").capitalize())


def _format_level(value: float, unit: str) -> str:
    if unit == "share_pct":
        return f"{value:.1f}%"
    if unit.startswith("usd"):
        magnitude = f"{abs(value):.3f}" if abs(value) < 10 else f"{abs(value):,.2f}"
        return f"-${magnitude}" if value < 0 else f"${magnitude}"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} billion"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} million"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.3f}"


def _format_yoy(yoy: float | None, basis: str) -> str:
    if yoy is None:
        return "no prior-year month"
    if basis == "percentage_points":
        return f"{yoy:+.1f} percentage points versus a year earlier"
    return f"{yoy * 100:+.1f}% versus a year earlier"


def human_summary(kpi: str, point: dict) -> str:
    level = _format_level(float(point["value"]), str(point.get("unit") or ""))
    change = _format_yoy(point.get("yoy"), str(point.get("yoy_basis") or "ratio"))
    return f"{label_for(kpi)} {level} in {point['period']} ({change})."


def _direction(yoy_points: list[tuple[str, float]], basis: str) -> tuple[str, float | None]:
    if len(yoy_points) < 3:
        return "steady", None
    deltas = [b - a for (_p1, a), (_p2, b) in zip(yoy_points, yoy_points[1:])]
    latest = deltas[-1]
    floor = 0.3 if basis == "percentage_points" else 0.02
    if abs(latest) < floor:
        return "steady", latest
    return ("accelerating" if latest > 0 else "decelerating"), latest


def metric_from_points(points: list[dict], *, evidence_ref: str) -> dict:
    ordered = sorted(points, key=lambda row: row["period"])
    latest = ordered[-1]
    basis = str(latest.get("yoy_basis") or "ratio")
    yoy_points = [(row["period"], float(row["yoy"])) for row in ordered if row.get("yoy") is not None]
    direction, accel = _direction(yoy_points, basis)
    growth = latest.get("yoy")
    return {
        "metric": latest["kpi"],
        "label": label_for(latest["kpi"]),
        "source": "issuer_operating",
        "evidence_ref": evidence_ref,
        "tier": "operating",
        "basis": "yoy",
        "mode": "level",
        "direction": direction,
        "signal_tier": "operating",
        "signal_type": "operating",
        "growth_latest": growth,
        "level_latest": latest["value"],
        "latest_period": latest["period"],
        "unit": latest.get("unit"),
        "yoy_basis": basis,
        "accel": accel,
        "display": True,
        "material": True,
        "stale": False,
        "human_summary": human_summary(latest["kpi"], latest),
        "points": [{"period": row["period"], "value": row["value"], "yoy": row.get("yoy")} for row in ordered],
    }


def metrics_by_ticker() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for doc in iter_stores():
        ticker = str(doc.get("ticker") or "").upper()
        grouped: dict[str, list[dict]] = defaultdict(list)
        for point in doc.get("points") or []:
            if point.get("kpi") and point.get("period") and point.get("value") is not None:
                grouped[str(point["kpi"])].append(point)
        if not grouped:
            continue
        evidence = f"_system/reference/market-data/operating_kpis/{ticker}.json"
        out[ticker] = [metric_from_points(rows, evidence_ref=evidence) for _kpi, rows in sorted(grouped.items())]
    return out


def compact_row(metric: dict) -> dict:
    return {
        "metric": metric.get("metric"),
        "label": metric.get("label"),
        "direction": metric.get("direction") or "steady",
        "signal_tier": metric.get("signal_tier") or "operating",
        "latest": metric.get("level_latest"),
        "growth_latest": metric.get("growth_latest"),
        "strength": None,
        "period": metric.get("latest_period"),
        "human_summary": metric.get("human_summary"),
        "unit": metric.get("unit"),
        "yoy_basis": metric.get("yoy_basis"),
        "source": "issuer_operating",
        "tier": "operating",
    }


def merge_operating_series(by_ticker: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Operating rows first, and they are not dropped when the series is steady."""
    operating = metrics_by_ticker()
    for ticker, metrics in operating.items():
        rows = [compact_row(metric) for metric in metrics]
        names = {row["metric"] for row in rows}
        existing = [row for row in (by_ticker.get(ticker) or []) if row.get("metric") not in names]
        by_ticker[ticker] = rows + existing
    return by_ticker


def select_shard_series(rows: list[dict], *, other_cap: int = 8) -> list[dict]:
    operating = [row for row in rows if row.get("tier") == "operating"]
    rest = [row for row in rows if row.get("tier") != "operating"]
    if not operating:
        return rows[:12]
    return operating + rest[:other_cap]


def operating_latest_rows() -> list[dict]:
    rows = []
    for doc in iter_stores():
        ticker = str(doc.get("ticker") or "").upper()
        latest: dict[str, dict] = {}
        for point in doc.get("points") or []:
            kpi = str(point.get("kpi") or "")
            period = str(point.get("period") or "")
            if not kpi or not period:
                continue
            prev = latest.get(kpi)
            if prev is None or period > str(prev.get("period") or ""):
                latest[kpi] = point
        for kpi, point in sorted(latest.items()):
            rows.append({
                "ticker": ticker,
                "kpi": kpi,
                "label": label_for(kpi),
                "period": point.get("period"),
                "value": point.get("value"),
                "unit": point.get("unit"),
                "yoy": point.get("yoy"),
                "yoy_basis": point.get("yoy_basis"),
                "source_url": point.get("source_url"),
                "doc": point.get("doc"),
            })
    return rows
