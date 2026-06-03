"""Market observatory: whole-market context for Darwin (Phase B)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, ROOT
from .external_sources import EXTERNAL_ROOT, save_sources_manifest
from .regime import latest_macro_state, macro_state_as_of

OBSERVATORY_PATH = DATA_DIR / "darwin_observatory.json"
REGIME_BRIEF_DIR = ROOT / "_system" / "reviews" / "pending"


def _load_external(name: str) -> dict:
    p = EXTERNAL_ROOT / f"{name}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_observatory(rows: list[dict], regime: dict) -> dict:
    save_sources_manifest()
    macro_now = latest_macro_state()
    vrp = _load_external("vrp_health")
    borrow = _load_external("borrow_spike_risk")
    macro_cal = _load_external("macro_event_calendar")
    risk = _load_external("risk_dashboard_summary")

    stale_pct = 0.0
    if rows:
        stale_pct = sum(1 for r in rows if (r.get("days_since_deep_dive") or 0) > 120) / len(rows)

    falsifier_total = sum(r.get("falsifier_count", 0) for r in rows)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regime": regime,
        "macro": macro_now,
        "research_stress": {
            "stale_research_pct": round(stale_pct, 3),
            "falsifier_count_total": falsifier_total,
            "human_review_pending": sum(1 for r in rows if r.get("human_review_pending")),
        },
        "vrp_health": vrp,
        "borrow_spike_risk": borrow,
        "macro_events": macro_cal,
        "magis_risk_book": risk,
        "context_etfs": ["SPY", "QQQ", "IWM", "TLT", "GLD", "HYG"],
        "sources_manifest": str(EXTERNAL_ROOT / "sources_manifest.json"),
    }


def write_regime_brief(observatory: dict, rows: list[dict]) -> Path:
    REGIME_BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = REGIME_BRIEF_DIR / f"darwin_regime_brief_{day}.md"
    regime = observatory.get("regime") or {}
    macro = observatory.get("macro") or {}
    risk = observatory.get("magis_risk_book") or {}
    lines = [
        f"# Darwin regime brief — {day}",
        "",
        "## Market regime",
        f"- Combined label: **{regime.get('label', '—')}** (research: {regime.get('research', '—')}, macro: {regime.get('macro', '—')})",
        f"- VIX: {macro.get('vix')} · 10Y: {macro.get('yield_10y')}% · month: {macro.get('as_of_month')}",
        "",
        "## Research book stress",
        f"- Stale dive share: {(observatory.get('research_stress') or {}).get('stale_research_pct', 0) * 100:.0f}%",
        f"- Open falsifiers: {(observatory.get('research_stress') or {}).get('falsifier_count_total', 0)}",
        f"- Human review pending: {(observatory.get('research_stress') or {}).get('human_review_pending', 0)}",
        "",
        "## External risk (ls-algo / MAGIS)",
    ]
    if risk:
        lines.append(f"- Gross exposure % NAV: {risk.get('gross_exposure_pct_nav')}")
        lines.append(f"- Net exposure % NAV: {risk.get('net_exposure_pct_nav')}")
        lines.append(f"- Risk breaches: {risk.get('breach_count', 0)}")
    else:
        lines.append("- Risk dashboard snapshot not linked (set DARWIN_LS_ALGO_ROOT or clone ls-algo).")
    lines.extend(["", "## Questions that changed", ""])
    for r in sorted(rows, key=lambda x: -(x.get("days_since_deep_dive") or 0))[:8]:
        qpath = ROOT / r["ticker"] / "research" / "open_questions.md"
        if qpath.exists():
            lines.append(f"- **{r['ticker']}**: see `{qpath.relative_to(ROOT)}`")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def save_observatory(payload: dict) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OBSERVATORY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return OBSERVATORY_PATH
