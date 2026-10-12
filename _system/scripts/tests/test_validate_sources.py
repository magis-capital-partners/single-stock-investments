"""The Magis source index stays internally consistent.

Python tests collects this module from `_system/scripts/tests/`. The validator
checks the JSON contract and that named repo paths exist on disk or at HEAD.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_sources as sources  # noqa: E402

BRIEFING_PHRASES = (
    "generated_at",
    "build_time",
    "_system/portfolio/registry.json",
    "ranked hits",
    "Special Situations",
    "nothing is new",
    "personal trades",
    "private correspondence",
    "Drew's approval",
    "personal brokerage mail",
    "newsletter",
    "filing confirms",
    "drewgoldman01@gmail.com",
    "drew@magiscapitalpartners.com",
    "MOI Global",
    "KEDM Lite",
    "Base Hit",
    "Friday Furnace",
    "7ad6d9cb-85bd-4f2c-b887-1bf4bf59b107",
    "Fundamental Analyst",
    "NOL and Tax Assets",
    "Technical Analyst",
    "Murray Stahl",
    "8:10",
    "research-equity",
    "[PROPOSED]",
    "Evidence",
    "Seen",
    "Harmful",
    "Scope",
    "Review after",
    "MEMORY.md",
    "borrow-etf",
    "diamond-creek",
    "spx-0dte",
    r"C:\Users\drewg\.codex\worktrees\energy-btc-model\single-stock-investments",
    r"C:\Users\drewg\Projects\.agent-memory\hubs\research-equity",
    "1q0B2FkNPF2onYEv9MBh6VJoDR6rqtBxQ",
    "1tL89aD9SDliM3BDCaQDJHU0CJ_YR0kgS",
    "1hsvaElY-UaFW0fGygv2685Bb9HJqatTS",
    "1m5c1VcKkGzy2rEp3V6GWAORQspMJHkjm",
    "1VLD6d4PpNWRagijg0ibsSeU5g3fMoNBz",
    "1LwfqcmaUU7X8uCMsoteeF8nRFt9mDNRe",
    "1BDzwtkgAHsKOda2NtxlHEwc37cEjTwD7",
    "1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C",
    "drive_intake_drop.py",
    "14:00 UTC",
    "- [x] Repo access: `mcricenti` holds `maintain` on this repository since 2026-10-12.",
    "- [x] Memory hub: write, by pull request on a `grok/<desk>/<date>-<slug>` branch into `_system/memory-hub/research-equity/`",
    "- [ ] Confirm whether Michael's bots join the Magis room.",
    "index_membership.json",
    "fico_watch.json",
    "You Can Be A Stock Market Genius",
    "Do not store email content",
)

DRIVE_IDS = {
    "drive-books": "1q0B2FkNPF2onYEv9MBh6VJoDR6rqtBxQ",
    "drive-books-value-investing": "1BDzwtkgAHsKOda2NtxlHEwc37cEjTwD7",
    "drive-books-accounting": "1tL89aD9SDliM3BDCaQDJHU0CJ_YR0kgS",
    "drive-books-trading-markets": "1hsvaElY-UaFW0fGygv2685Bb9HJqatTS",
    "drive-investment-wisdom-accounting": "1m5c1VcKkGzy2rEp3V6GWAORQspMJHkjm",
    "drive-short-selling-papers": "1VLD6d4PpNWRagijg0ibsSeU5g3fMoNBz",
    "drive-special-situations-checklist": "1LwfqcmaUU7X8uCMsoteeF8nRFt9mDNRe",
    "drive-admin-intake-vic": "1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C",
}

FRESHNESS = {
    "dashboard-kpi-trends": "generated_at",
    "dashboard-portfolio-news": "build_time",
    "dashboard-document-catalog": "generated_at",
    "dashboard-warrants": "generated_at",
    "dashboard-activist-feed": "generated_at",
    "dashboard-index-membership": "generated",
    "dashboard-fico-watch": "generated_at",
}


def _index() -> dict:
    return json.loads((ROOT / "_system" / "sources.json").read_text(encoding="utf-8"))


def _by_id(payload: dict) -> dict:
    return {item["id"]: item for item in payload["sources"]}


def _briefing_text() -> str:
    """SOURCES.md is outside the default _system sparse set, so fall back to git."""
    path = ROOT / "SOURCES.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "show", "HEAD:SOURCES.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_committed_index_and_briefing_match_the_contract():
    failures = sources.validate_index(ROOT / "_system" / "sources.json", ROOT)
    assert failures == [], failures
    payload = _index()
    rows = _by_id(payload)
    for source_id, field in FRESHNESS.items():
        assert rows[source_id]["freshness_field"] == field
    assert rows["dashboard-fico-watch"]["optional_path"] is True
    for source_id, drive_id in DRIVE_IDS.items():
        assert rows[source_id]["drive_id"] == drive_id
    assert rows["drive-books-value-investing"]["resolved_by"] == "name"
    assert rows["email-drewgoldman01"]["mode"] == "read"
    assert rows["email-magis"]["connector"] == "magis"
    assert "personal brokerage mail" in rows["email-drewgoldman01"]["never_surface"]
    briefing = _briefing_text()
    missing = [phrase for phrase in BRIEFING_PHRASES if phrase not in briefing]
    assert missing == [], missing


def test_cli_accepts_the_committed_index():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_sources.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_repo_path_fails(tmp_path: Path):
    payload = _index()
    payload["sources"][0]["repo_path"] = "dashboard/data/does-not-exist.json"
    failures = sources.validate_payload(payload, tmp_path)
    assert any("missing file" in failure for failure in failures)


def test_optional_repo_path_may_be_absent(tmp_path: Path):
    payload = {
        "schema": "sources.v1",
        "description": "fixture",
        "github_repo": "example/repo",
        "ground_rules": list(sources.REQUIRED_GROUND_RULES),
        "local_worktree": {"path": "local", "status": "stale"},
        "local_memory_hub": {"path": "hub", "status": "absent"},
        "room": {
            "name": "Magis Capital Partners",
            "id": "7ad6d9cb-85bd-4f2c-b887-1bf4bf59b107",
            "platform": "Grok Bot group",
            "desks": ["Fundamental Analyst"],
            "digest": "Weekday digests around 8:10-8:14 AM ET.",
        },
        "pending_access": ["Decide access."],
        "do_not_write": ["MEMORY.md", "borrow-etf", "diamond-creek", "spx-0dte"],
        "sources": [
            {
                "id": "optional-file",
                "type": "repo file",
                "location": "missing.json",
                "repo_path": "missing.json",
                "path_kind": "file",
                "optional_path": True,
                "purpose": "May be absent.",
                "owner_desk": "Magis Capital Partners / all desks",
                "mode": "read",
                "push": "No write.",
            }
        ],
    }
    assert sources.validate_payload(payload, tmp_path) == []


def test_duplicate_id_and_unknown_type_fail(tmp_path: Path):
    payload = _index()
    payload["sources"].append(dict(payload["sources"][0]))
    payload["sources"][0]["type"] = "slack"
    failures = sources.validate_payload(payload, tmp_path)
    assert any("type must be one of" in failure for failure in failures)
    assert any(failure.startswith("duplicate id:") for failure in failures)


def test_drive_source_needs_an_id_or_a_name_policy(tmp_path: Path):
    payload = _index()
    row = _by_id(payload)["drive-books"]
    row.pop("drive_id")
    failures = sources.validate_payload(payload, tmp_path)
    assert any("drive_id or drive_id_policy" in failure for failure in failures)


def test_committed_path_counts_when_the_worktree_file_is_absent(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tracked = tmp_path / "dashboard" / "data"
    tracked.mkdir(parents=True)
    target = tracked / "kpi_trends.json"
    target.write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "dashboard/data/kpi_trends.json"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=sources-test@example.com",
            "-c",
            "user.name=sources-test",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "seed",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    target.unlink()
    assert sources.path_exists(tmp_path, "dashboard/data/kpi_trends.json", "file")
    assert not (tmp_path / "dashboard" / "data" / "kpi_trends.json").exists()
