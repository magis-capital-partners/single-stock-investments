"""The daily download sync tiers a new registry name before the dashboard sees it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_dashboard_data as dashboard  # noqa: E402
import build_valuation_universe_tiers as tiers  # noqa: E402
import download_all_holdings as downloads  # noqa: E402


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _root_with_registry(tmp_path: Path, holdings: dict) -> Path:
    policy = json.loads((tiers.ROOT / tiers.POLICY_REL).read_text(encoding="utf-8"))
    _write(tmp_path / tiers.POLICY_REL, policy)
    _write(tmp_path / "_system/portfolio/registry.json", {"holdings": holdings, "watchlist": {}})
    return tmp_path


def test_new_registry_ticker_is_tiered_by_the_existing_rules(tmp_path: Path) -> None:
    """Watch stays Tier 3. A priority stance is Tier 2. Nothing else is invented."""
    root = _root_with_registry(tmp_path, {
        "NEW": {"company": "New Listing", "classification": {"stance": "watch"}},
        "HELD": {"company": "Priority Name", "classification": {"stance": "hold"}},
    })

    payload = downloads.assign_valuation_universe_tiers(root)

    new = payload["assignments"]["NEW"]
    held = payload["assignments"]["HELD"]
    assert new["tier"] == 3
    assert new["label"] == "Broad screening universe"
    assert {row["code"] for row in new["assignment_reasons"]} == {"research_universe_member"}
    assert held["tier"] == 2
    assert "priority_classification" in {row["code"] for row in held["assignment_reasons"]}
    written = json.loads((root / tiers.OUTPUT_REL).read_text(encoding="utf-8"))
    assert written["assignments"]["NEW"]["tier"] == 3
    assert dashboard.missing_valuation_tier_tickers([
        {"ticker": "NEW"},
        {"ticker": "HELD", "valuation_tier": {"tier": held["tier"], "tier_id": "tier_2"}},
    ]) == ["NEW"]
    assert dashboard.missing_valuation_tier_tickers([
        {"ticker": "NEW", "valuation_tier": {"tier": new["tier"], "tier_id": "tier_3", "label": new["label"]}},
    ]) == []


def test_daily_refresh_assigns_tiers_before_the_dashboard_rebuild(monkeypatch) -> None:
    labels: list[str] = []

    def record_run(cmd, label, **kwargs):
        labels.append(label)

    def record_tiers():
        labels.append("assign tiers")
        return {}

    monkeypatch.setattr(downloads, "run", record_run)
    monkeypatch.setattr(downloads, "assign_valuation_universe_tiers", record_tiers)
    monkeypatch.setattr(
        downloads.subprocess,
        "run",
        lambda *args, **kwargs: labels.append("rebuild") or type("R", (), {"returncode": 0})(),
    )

    downloads.daily_refresh({})

    assert labels.index("assign tiers") < labels.index("rebuild")
    assert "Rebuild dashboard JSON" not in labels


def test_a_failed_dashboard_rebuild_is_not_swallowed(monkeypatch) -> None:
    monkeypatch.setattr(downloads, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(downloads, "assign_valuation_universe_tiers", lambda: {})
    monkeypatch.setattr(
        downloads.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"returncode": 1})(),
    )

    try:
        downloads.daily_refresh({})
    except SystemExit as exc:
        assert "Dashboard rebuild failed" in str(exc)
    else:
        raise AssertionError("daily_refresh committed past a failed dashboard rebuild")


def test_refuse_names_the_untiered_rows() -> None:
    try:
        dashboard.refuse_missing_valuation_tiers([
            {"ticker": "AENA.MC", "valuation_tier": None},
            {"ticker": "OK", "valuation_tier": {"tier": 3}},
        ])
    except SystemExit as exc:
        assert "AENA.MC" in str(exc)
        assert "OK" not in str(exc)
    else:
        raise AssertionError("untiered row was published")
