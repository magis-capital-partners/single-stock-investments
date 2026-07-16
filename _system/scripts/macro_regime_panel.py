"""Portfolio macro regime panel for Insights (one strip, not per-ticker spam).

Builds a single `portfolio_macro_regime` object from the themes manifest + Darwin
regime label, with signed interpretation (risk_on / risk_off / neutral) so rising
yields or credit spreads are never auto-labeled bullish.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"

# Series where "up" means more risk / tighter financial conditions.
RISK_OFF_WHEN_UP = frozenset({
    "hy_oas",
    "ust_10y",
    "ust_2y",
    "vix_level",
    "spy_20d_realized_vol",
})
# Dollar strength is contextual, not auto bullish.
NEUTRAL_WHEN_UP = frozenset({
    "dxy_broad",
    "dxy_narrow",
})
# Credit impulse up = risk appetite (risk_on).
RISK_ON_WHEN_UP = frozenset({
    "credit_impulse_1m",
})

SERIES_PRIORITY = (
    "hy_oas",
    "vix_level",
    "ust_10y",
    "spy_20d_realized_vol",
    "credit_impulse_1m",
    "dxy_broad",
    "ust_2y",
)


def load_manifest(path: Path | None = None) -> dict:
    p = path or MANIFEST_PATH
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def signed_direction(series_id: str, direction: str | None) -> str:
    """Map raw series direction to risk_on / risk_off / neutral."""
    d = (direction or "flat").lower()
    if d not in {"up", "down"}:
        return "neutral"
    if series_id in RISK_OFF_WHEN_UP:
        return "risk_off" if d == "up" else "risk_on"
    if series_id in RISK_ON_WHEN_UP:
        return "risk_on" if d == "up" else "risk_off"
    if series_id in NEUTRAL_WHEN_UP:
        return "neutral" if d == "up" else "risk_on"
    return "neutral"


def series_why(series_id: str, signed: str, direction: str | None) -> str:
    d = (direction or "flat").lower()
    labels = {
        "hy_oas": ("Credit spreads widening", "Credit spreads tightening"),
        "ust_10y": ("Rates rising (duration headwind)", "Rates falling"),
        "ust_2y": ("Front-end rates rising", "Front-end rates falling"),
        "vix_level": ("Vol rising", "Vol falling"),
        "spy_20d_realized_vol": ("Realized equity vol rising", "Realized equity vol falling"),
        "credit_impulse_1m": ("Credit impulse improving", "Credit impulse weakening"),
        "dxy_broad": ("Dollar stronger (contextual)", "Dollar weaker"),
        "dxy_narrow": ("Dollar stronger (contextual)", "Dollar weaker"),
    }
    up_msg, down_msg = labels.get(series_id, ("Moving up", "Moving down"))
    if d == "up":
        return up_msg
    if d == "down":
        return down_msg
    return "Little change"


def surprise_rank(series: dict) -> float:
    """Rank by absolute YoY move when present, else presence of a value."""
    yoy = series.get("yoy_pct")
    if yoy is not None:
        try:
            return abs(float(yoy))
        except (TypeError, ValueError):
            pass
    if series.get("latest") is not None:
        return 1.0
    return 0.0


def format_value(series_id: str, latest) -> str | None:
    if latest is None:
        return None
    try:
        v = float(latest)
    except (TypeError, ValueError):
        return str(latest)
    if series_id in {"hy_oas", "ust_10y", "ust_2y", "credit_impulse_1m"}:
        return f"{v:.2f}%"
    if series_id in {"vix_level", "spy_20d_realized_vol", "dxy_broad", "dxy_narrow"}:
        return f"{v:.1f}"
    return f"{v:.2f}"


def darwin_regime_label() -> dict:
    """Best-effort Darwin regime; never raises."""
    try:
        from darwin.regime import latest_macro_state

        state = latest_macro_state()
        return {
            "label": state.get("label") or "calm",
            "as_of_month": state.get("as_of_month"),
            "vix": state.get("vix"),
            "yield_10y": state.get("yield_10y"),
            "cpi_yoy_pct": state.get("cpi_yoy_pct"),
            "macro_available": bool(state.get("macro_available")),
        }
    except Exception:
        return {
            "label": "calm",
            "as_of_month": None,
            "vix": None,
            "yield_10y": None,
            "cpi_yoy_pct": None,
            "macro_available": False,
        }


def regime_summary(label: str, series_rows: list[dict]) -> str:
    risk_off_n = sum(1 for s in series_rows if s.get("signed_direction") == "risk_off")
    risk_on_n = sum(1 for s in series_rows if s.get("signed_direction") == "risk_on")
    if label == "stressed":
        base = "Regime stressed."
    elif label == "adapting":
        base = "Regime adapting."
    else:
        base = "Regime calm."
    if risk_off_n > risk_on_n:
        return f"{base} More series pointing risk-off than risk-on."
    if risk_on_n > risk_off_n:
        return f"{base} More series pointing risk-on than risk-off."
    return f"{base} Mixed cross-asset signals."


def build_series_rows(manifest: dict, *, limit: int = 5) -> list[dict]:
    theme = (manifest.get("themes") or {}).get("macro_regime") or {}
    raw = theme.get("series") or {}
    rows: list[dict] = []
    seen: set[str] = set()
    # Prefer priority order, then fill by surprise.
    ordered_ids = list(SERIES_PRIORITY) + [sid for sid in raw if sid not in SERIES_PRIORITY]
    scored: list[tuple[float, str, dict]] = []
    for sid in ordered_ids:
        if sid in seen or sid not in raw:
            continue
        seen.add(sid)
        s = raw[sid] or {}
        if s.get("latest") is None and s.get("optional"):
            continue
        if s.get("latest") is None:
            continue
        scored.append((surprise_rank(s), sid, s))
    # Within priority bucket, keep priority order for the first few; still allow
    # high-surprise optional fills. Sort by: priority index (lower better), then -surprise.
    priority_index = {sid: i for i, sid in enumerate(SERIES_PRIORITY)}

    def sort_key(item: tuple[float, str, dict]) -> tuple:
        surprise, sid, _ = item
        return (priority_index.get(sid, 100), -surprise)

    scored.sort(key=sort_key)
    for _, sid, s in scored[:limit]:
        direction = s.get("direction") or "flat"
        signed = signed_direction(sid, direction)
        delta = s.get("yoy_pct")
        rows.append({
            "id": sid,
            "label": s.get("label") or sid,
            "value": format_value(sid, s.get("latest")),
            "raw_value": s.get("latest"),
            "delta": delta,
            "delta_label": f"{delta:+.1f}% YoY" if isinstance(delta, (int, float)) else None,
            "direction": direction,
            "signed_direction": signed,
            "why": series_why(sid, signed, direction),
            "as_of": s.get("as_of"),
            "stale": bool(s.get("stale")),
        })
    return rows


def build_portfolio_macro_regime(manifest: dict | None = None) -> dict:
    """Single portfolio-scoped macro object for the Insights strip."""
    doc = manifest if manifest is not None else load_manifest()
    darwin = darwin_regime_label()
    series = build_series_rows(doc, limit=5)
    as_of = doc.get("as_of") or darwin.get("as_of_month")
    if series:
        dates = [s.get("as_of") for s in series if s.get("as_of")]
        if dates:
            as_of = max(dates)
    label = darwin.get("label") or "calm"
    return {
        "label": label,
        "as_of": as_of,
        "summary": regime_summary(label, series),
        "darwin": darwin,
        "series": series,
        "theme_id": "macro_regime",
    }


def regime_to_compat_macro_list(regime: dict) -> list[dict]:
    """Thin compatibility list shaped like legacy portfolio_macro cards."""
    out: list[dict] = []
    for s in regime.get("series") or []:
        signed = s.get("signed_direction") or "neutral"
        direction = "bearish" if signed == "risk_off" else ("bullish" if signed == "risk_on" else "neutral")
        out.append({
            "id": f"macro:{s.get('id')}",
            "source": "macro",
            "source_label": "Macro",
            "title": regime.get("theme_id") or "macro_regime",
            "summary": s.get("why") or s.get("label"),
            "direction": direction,
            "date": s.get("as_of") or regime.get("as_of"),
            "confidence": "med",
            "score": 0,
            "signed_direction": signed,
            "series_id": s.get("id"),
            "value": s.get("value"),
        })
    return out
