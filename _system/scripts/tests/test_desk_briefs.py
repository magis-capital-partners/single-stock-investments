"""Desk briefs: schema, checker, builder and the Inbox block.

Contract: _system/data/desk_briefs/README.md. The checker and builder take explicit
paths so these tests run against a temporary briefs directory and registry.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_desk_briefs as builder  # noqa: E402
import check_desk_briefs as checker  # noqa: E402

SEED = ROOT / "_system" / "data" / "desk_briefs" / "special_situations" / "2026-10-12.json"
VIZ = ROOT / "dashboard" / "desk-briefs-viz.js"
RUNNER = SCRIPTS / "desk_briefs_node_runner.cjs"
NODE = shutil.which("node")

GOOD = {
    "schema_version": "desk_briefs.v1",
    "desk": "activism",
    "as_of": "2026-10-12",
    "author": "grok-michael-activism",
    "owner": "michael",
    "inputs_read": [{"path": "dashboard/data/activist_feed.json", "generated_at": "2026-10-11T14:08:48Z"}],
    "items": [
        {
            "ticker": "FOX",
            "headline": "LGC Holdco SC 13D/A: stake unchanged, purpose item amended.",
            "one_number": "stake 7.1%",
            "lane": "13d",
            "evidence": [{"kind": "filing", "ref": "SC 13D/A 0000000000-26-000001", "url": "https://www.sec.gov/x"}],
            "confidence": "filing",
            "next": "Read the next amendment.",
            "handoff": None,
        }
    ],
    "screens_empty": ["short_report"],
    "research_only": True,
    "in_base_irr": False,
    "authority": "none",
}


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """A fake repo root: schema copied in, a small registry, the one input file the brief reads."""
    briefs = tmp_path / "_system" / "data" / "desk_briefs"
    briefs.mkdir(parents=True)
    shutil.copy(ROOT / "_system" / "data" / "desk_briefs" / "schema.json", briefs / "schema.json")
    (briefs / "README.md").write_text("fixture\n", encoding="utf-8")
    registry = tmp_path / "_system" / "portfolio" / "registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps({"meta": {"updated": "2026-10-11T20:17:50Z"}, "holdings": {"FOX": {}, "MDT": {}}, "watchlist": {"WATCH": {}}}),
        encoding="utf-8",
    )
    feed = tmp_path / "dashboard" / "data" / "activist_feed.json"
    feed.parent.mkdir(parents=True)
    feed.write_text('{"generated_at": "2026-10-11T14:08:48Z"}', encoding="utf-8")
    return tmp_path


def _paths(root: Path) -> dict:
    return {
        "briefs_dir": root / "_system" / "data" / "desk_briefs",
        "registry_path": root / "_system" / "portfolio" / "registry.json",
        "schema_path": root / "_system" / "data" / "desk_briefs" / "schema.json",
        "root": root,
    }


def _write(root: Path, desk: str, as_of: str, payload: dict) -> Path:
    path = root / "_system" / "data" / "desk_briefs" / desk / f"{as_of}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _check(root: Path, today: str = "2026-10-12") -> dict:
    return checker.check_all(today=date.fromisoformat(today), **_paths(root))


# --------------------------------------------------------------------------- schema

def test_schema_is_valid_draft_2020_12_and_accepts_the_fixture():
    schema = checker.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["properties"]["schema_version"]["enum"]) == {"desk_briefs.v1", "desk_briefs.v2"}
    assert set(schema["properties"]["desk"]["enum"]) == set(checker.DESKS)
    assert schema["properties"]["items"]["maxItems"] == 12
    assert schema["properties"]["items"]["items"]["properties"]["headline"]["maxLength"] == 160
    validator = checker.make_validator(schema)
    assert list(validator.iter_errors(GOOD)) == []


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda b: b.__setitem__("schema_version", "desk_briefs.v0"), "schema_version"),
        (lambda b: b.__setitem__("desk", "options"), "desk"),
        (lambda b: b.__setitem__("owner", "someone"), "owner"),
        (lambda b: b.__setitem__("authority", "full"), "authority"),
        (lambda b: b.__setitem__("research_only", False), "research_only"),
        (lambda b: b["items"][0].pop("one_number"), "one_number"),
        (lambda b: b["items"][0].__setitem__("headline", "x" * 161), "headline"),
        (lambda b: b["items"][0].__setitem__("confidence", "rumour"), "confidence"),
        (lambda b: b["items"][0].__setitem__("evidence", []), "evidence"),
        (lambda b: b["items"][0]["evidence"][0].__setitem__("kind", "chat"), "kind"),
        (lambda b: b["items"][0].__setitem__("ticker", "fox"), "ticker"),
        (lambda b: b.__setitem__("extra", 1), "extra"),
        (lambda b: b["items"][0].__setitem__("size", "2%"), "size"),
        (lambda b: b.__setitem__("inputs_read", []), "inputs_read"),
    ],
)
def test_schema_rejects_each_broken_field(mutate, needle):
    brief = copy.deepcopy(GOOD)
    mutate(brief)
    validator = checker.make_validator(checker.load_schema())
    errors = [f"{list(e.absolute_path)} {e.message}" for e in validator.iter_errors(brief)]
    assert errors, needle
    assert any(needle in e for e in errors), (needle, errors)


def test_thirteen_items_are_rejected(root: Path):
    brief = copy.deepcopy(GOOD)
    brief["items"] = [copy.deepcopy(GOOD["items"][0]) for _ in range(13)]
    _write(root, "activism", "2026-10-12", brief)
    report = _check(root)
    assert any("too long" in e or "maxItems" in e or "12" in e for e in report["errors"]), report["errors"]
    brief["items"] = brief["items"][:12]
    _write(root, "activism", "2026-10-12", brief)
    assert _check(root)["errors"] == []


# -------------------------------------------------------------------------- checker

def test_committed_seed_brief_passes_the_checker():
    # The seed is dated 2026-10-12. Freezing the checker on that day made
    # every later committed brief look "in the future" (tape_index
    # 2026-10-19, PR #1225). Judge the corpus against the real clock.
    report = checker.check_all(today=date.today())
    assert report["errors"] == [], report["errors"]
    seed = next(b for b in report["briefs"] if b["path"].endswith("special_situations/2026-10-12.json"))
    assert seed["desk"] == "special_situations"
    assert seed["as_of"] == "2026-10-12"
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    assert payload["author"] == "claude-drew-special-situations"
    assert payload["owner"] == "drew"
    assert 1 <= len(payload["items"]) <= 12
    assert any(item["ticker"] == "MDT" for item in payload["items"])
    stamps = {row["path"]: row["generated_at"] for row in payload["inputs_read"]}
    for path, stamp in stamps.items():
        doc = json.loads((ROOT / path).read_text(encoding="utf-8"))
        field = doc.get("generated_at") or (doc.get("meta") or {}).get("updated")
        # The brief records the build it read. CI rebuilds these files nightly,
        # so the committed file may be newer than the brief, never older.
        assert field is not None, path
        assert str(stamp) <= str(field), (path, field, stamp)


def test_unknown_ticker_is_rejected_and_unresolved_is_allowed(root: Path):
    brief = copy.deepcopy(GOOD)
    brief["items"][0]["ticker"] = "ZZZZ"
    _write(root, "activism", "2026-10-12", brief)
    report = _check(root)
    assert any("ZZZZ" in e and "registry" in e for e in report["errors"]), report["errors"]
    brief["items"][0]["ticker"] = "unresolved"
    _write(root, "activism", "2026-10-12", brief)
    assert _check(root)["errors"] == []
    brief["items"][0]["ticker"] = "WATCH"  # watchlist counts too
    _write(root, "activism", "2026-10-12", brief)
    assert _check(root)["errors"] == []


def test_as_of_must_match_the_file_name_and_the_directory_must_match_the_desk(root: Path):
    _write(root, "activism", "2026-10-11", GOOD)
    errors = _check(root)["errors"]
    assert any("as_of" in e and "2026-10-11" in e for e in errors), errors
    (root / "_system" / "data" / "desk_briefs" / "activism" / "2026-10-11.json").unlink()
    _write(root, "fundamentals", "2026-10-12", GOOD)
    errors = _check(root)["errors"]
    assert any("does not match its directory" in e for e in errors), errors


def test_missing_input_path_and_future_date_and_stray_files_are_rejected(root: Path):
    brief = copy.deepcopy(GOOD)
    brief["inputs_read"].append({"path": "dashboard/data/does_not_exist.json", "generated_at": None})
    _write(root, "activism", "2026-10-12", brief)
    report = _check(root)
    assert any("does not exist" in e for e in report["errors"]), report["errors"]
    assert any("no stamp" in w for w in report["warnings"]), report["warnings"]
    future = copy.deepcopy(GOOD)
    future["as_of"] = "2026-10-20"
    _write(root, "activism", "2026-10-20", future)
    assert any("in the future" in e for e in _check(root)["errors"])
    stray = root / "_system" / "data" / "desk_briefs" / "notes.txt"
    stray.write_text("x", encoding="utf-8")
    assert any("notes.txt" in e for e in _check(root)["errors"])
    stray.unlink()
    (root / "_system" / "data" / "desk_briefs" / "options").mkdir()
    _write(root, "options", "2026-10-12", GOOD)
    assert any("unknown desk directory" in e for e in _check(root)["errors"])


def test_confidence_must_be_backed_by_evidence_of_that_kind(root: Path):
    brief = copy.deepcopy(GOOD)
    brief["items"][0]["evidence"] = [{"kind": "news", "ref": "Reuters 2026-10-11", "url": "https://example.com"}]
    _write(root, "activism", "2026-10-12", brief)
    errors = _check(root)["errors"]
    assert any("confidence 'filing' needs evidence" in e for e in errors), errors
    brief["items"][0]["confidence"] = "news"
    _write(root, "activism", "2026-10-12", brief)
    assert _check(root)["errors"] == []
    brief["items"][0]["handoff"] = "activism"
    _write(root, "activism", "2026-10-12", brief)
    assert any("own id" in e for e in _check(root)["errors"])


def test_filing_instructions_rebuild_the_dashboard_payload_in_the_same_commit():
    readme = (ROOT / "_system" / "data" / "desk_briefs" / "README.md").read_text(encoding="utf-8")
    prompt = (ROOT / "_system" / "prompts" / "grok_scan_agents.md").read_text(encoding="utf-8")
    tape = prompt.split("## 5. Index, forced flow, and tape", 1)[1].split("## 6. Short selling", 1)[0]
    for text in (readme, tape):
        assert "python _system/scripts/build_desk_briefs.py" in text
        assert "dashboard/data/desk_briefs.json" in text
        assert "same commit" in text


def test_checker_rejects_a_stale_dashboard_payload(root: Path):
    _write(root, "activism", "2026-10-12", GOOD)
    payload = root / "dashboard" / "data" / "desk_briefs.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps({"schema_version": "desk_briefs.v1", "desks": []}) + "\n", encoding="utf-8")
    args = [
        "--briefs-dir", str(root / "_system" / "data" / "desk_briefs"),
        "--registry", str(root / "_system" / "portfolio" / "registry.json"),
        "--schema", str(root / "_system" / "data" / "desk_briefs" / "schema.json"),
        "--root", str(root), "--today", "2026-10-12",
    ]
    errors = checker.committed_payload_errors(
        root=root,
        briefs_dir=root / "_system" / "data" / "desk_briefs",
        registry_path=root / "_system" / "portfolio" / "registry.json",
        schema_path=root / "_system" / "data" / "desk_briefs" / "schema.json",
    )
    assert errors and "build_desk_briefs.py" in errors[0]
    assert "same commit" in errors[0]
    assert checker.main(args) == 1
    assert checker.main(args + ["--warn-only"]) == 0
    assert builder.main([
        "--out", str(payload),
        "--briefs-dir", str(root / "_system" / "data" / "desk_briefs"),
        "--registry", str(root / "_system" / "portfolio" / "registry.json"),
        "--schema", str(root / "_system" / "data" / "desk_briefs" / "schema.json"),
        "--root", str(root), "--now", "2026-10-12T12:00:00Z",
    ]) == 0
    assert checker.committed_payload_errors(
        root=root,
        briefs_dir=root / "_system" / "data" / "desk_briefs",
        registry_path=root / "_system" / "portfolio" / "registry.json",
        schema_path=root / "_system" / "data" / "desk_briefs" / "schema.json",
    ) == []
    assert checker.main(args) == 0


def test_cli_exit_codes_and_warn_only(root: Path):
    brief = copy.deepcopy(GOOD)
    brief["items"][0]["ticker"] = "ZZZZ"
    _write(root, "activism", "2026-10-12", brief)
    args = [
        "--briefs-dir", str(root / "_system" / "data" / "desk_briefs"),
        "--registry", str(root / "_system" / "portfolio" / "registry.json"),
        "--schema", str(root / "_system" / "data" / "desk_briefs" / "schema.json"),
        "--root", str(root), "--today", "2026-10-12",
    ]
    assert checker.main(args) == 1
    assert checker.main(args + ["--warn-only"]) == 0
    _write(root, "activism", "2026-10-12", GOOD)
    assert checker.main(args) == 0


# -------------------------------------------------------------------------- builder

def _build(root: Path, now: str = "2026-10-12T12:00:00Z", **kwargs) -> dict:
    return builder.build(now=builder.parse_stamp(now), **_paths(root), **kwargs)


def test_builder_output_shape(root: Path):
    _write(root, "activism", "2026-10-12", GOOD)
    other = copy.deepcopy(GOOD)
    other.update({"desk": "special_situations", "owner": "drew", "author": "claude-drew-special-situations"})
    other["items"][0]["ticker"] = "MDT"
    _write(root, "special_situations", "2026-10-12", other)
    doc = _build(root)
    assert doc["schema_version"] == "desk_briefs.v1"
    assert doc["generated_at"] == "2026-10-12T12:00:00Z"
    assert doc["research_only"] is True and doc["in_base_irr"] is False and doc["authority"] == "none"
    assert [d["desk"] for d in doc["desks"]] == ["special_situations", "activism"]
    entry = doc["desks"][1]
    for key in ("desk", "owner", "author", "as_of", "age_hours", "stale", "path", "items", "inputs_read", "screens_empty"):
        assert key in entry, key
    assert entry["owner"] == "michael" and entry["author"] == "grok-michael-activism"
    assert entry["age_hours"] == 12.0 and entry["stale"] is False
    assert entry["path"] == "_system/data/desk_briefs/activism/2026-10-12.json"
    read = entry["inputs_read"][0]
    assert read["path"] == "dashboard/data/activist_feed.json"
    assert read["generated_at"] == "2026-10-11T14:08:48Z"
    assert read["age_hours_at_read"] == 33.9 and read["exists"] is True
    assert doc["counts"] == {
        "briefs": 2, "items": 2, "files": 2,
        "by_desk": {"special_situations": 1, "activism": 1},
        "by_owner": {"drew": 1, "michael": 1},
    }
    flat = doc["items_flat"]
    assert len(flat) == 2 and {f["desk"] for f in flat} == {"special_situations", "activism"}
    assert all({"desk", "owner", "as_of", "author", "stale"} <= set(f) for f in flat)
    assert doc["desks_without_brief"] == ["fundamentals", "nol_tax_assets", "tape_index", "stahl", "short_selling"]
    assert doc["health"]["status"] == "healthy"
    assert doc["health"]["structural_errors"] == [] and doc["health"]["problems"] == []


def test_latest_file_per_desk_wins_and_stale_flag_marks_old_briefs(root: Path):
    old = copy.deepcopy(GOOD)
    old["as_of"] = "2026-09-30"
    _write(root, "activism", "2026-09-30", old)
    doc = _build(root)
    assert doc["desks"][0]["as_of"] == "2026-09-30"
    assert doc["desks"][0]["stale"] is True and doc["desks"][0]["age_hours"] == 300.0
    assert doc["items_flat"][0]["stale"] is True
    assert doc["health"]["status"] == "degraded"
    assert any("12 days old" in p for p in doc["health"]["problems"]), doc["health"]["problems"]
    _write(root, "activism", "2026-10-12", GOOD)
    doc = _build(root)
    assert len(doc["desks"]) == 1
    assert doc["desks"][0]["as_of"] == "2026-10-12" and doc["desks"][0]["stale"] is False
    assert doc["counts"]["files"] == 2 and doc["counts"]["briefs"] == 1
    assert doc["health"]["status"] == "healthy"


def test_invalid_brief_is_excluded_and_named_in_structural_errors(root: Path):
    bad = copy.deepcopy(GOOD)
    bad["items"][0]["ticker"] = "ZZZZ"
    _write(root, "activism", "2026-10-12", bad)
    doc = _build(root)
    assert doc["desks"] == []
    assert doc["health"]["status"] == "unhealthy"
    assert any("ZZZZ" in e for e in doc["health"]["structural_errors"])
    assert "activism" in doc["desks_without_brief"]


def test_builder_cli_writes_the_file(root: Path, tmp_path: Path):
    _write(root, "activism", "2026-10-12", GOOD)
    out = tmp_path / "out" / "desk_briefs.json"
    rc = builder.main([
        "--out", str(out),
        "--briefs-dir", str(root / "_system" / "data" / "desk_briefs"),
        "--registry", str(root / "_system" / "portfolio" / "registry.json"),
        "--schema", str(root / "_system" / "data" / "desk_briefs" / "schema.json"),
        "--root", str(root), "--now", "2026-10-12T12:00:00Z",
    ])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["counts"]["briefs"] == 1
    assert out.read_text(encoding="utf-8").endswith("}\n")


def test_committed_dashboard_payload_matches_the_committed_briefs():
    committed = ROOT / "dashboard" / "data" / "desk_briefs.json"
    if not committed.exists():
        pytest.skip("dashboard/data/desk_briefs.json not built yet")
    doc = json.loads(committed.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "desk_briefs.v1"
    assert doc["health"]["structural_errors"] == []
    assert doc["authority"] == "none"
    paths = {d["path"] for d in doc["desks"]}
    latest_special = max((ROOT / "_system" / "data" / "desk_briefs" / "special_situations").glob("????-??-??.json"))
    assert f"_system/data/desk_briefs/special_situations/{latest_special.name}" in paths
    now = datetime.now(timezone.utc)
    fresh = builder.build(now=now)
    assert [d["path"] for d in fresh["desks"]] == [d["path"] for d in doc["desks"]], "rebuild dashboard/data/desk_briefs.json"


# ------------------------------------------------------------------------- the block

def run_node(action: str) -> dict:
    proc = subprocess.run([NODE, str(RUNNER), action], cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_viz_parses_and_renders_cards_with_filters():
    subprocess.run([NODE, "--check", str(VIZ)], check=True)
    html = run_node("render")["html"]
    for needle in ("Desk briefs", "Special Situations", "Activism", "claude-drew-special-situations", "grok-michael-activism",
                   ">MDT<", "final exchange ratio 4.5939", "SC TO-I/A 0001628280-26-065406", "Read the final-results 8-K.",
                   "Hand off: Index, forced flow and tape", ">stale<", "12h ago", "12d ago",
                   "separations.json", "24h old at read", ">missing<", "Screens empty.", "odd lot alerts",
                   "No brief yet.", "Fundamentals, NOL and Tax Assets", "activism brief is 12 days old"):
        assert needle in html, needle
    assert html.count('class="desk-brief-card') == 2
    assert 'href="https://www.sec.gov/Archives/edgar/data/1613103/000162828026065406/mdt-amendedno2scheduleissu.htm"' in html
    assert "All owners · 2" in html and "Drew · 1" in html and "Michael · 1" in html
    assert "All desks · 2" in html


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_viz_owner_and_desk_chips_filter_the_cards():
    result = run_node("filter")
    assert result["changed"] == 2
    assert result["all"].count('class="desk-brief-card') == 2
    assert result["michael"].count('class="desk-brief-card') == 1
    assert "grok-michael-activism" in result["michael"] and "claude-drew-special-situations" not in result["michael"]
    assert result["none"].count('class="desk-brief-card') == 0
    assert "No brief matches these filters." in result["none"]
    assert result["reset"].count('class="desk-brief-card') == 2


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_viz_degrades_to_an_empty_state():
    result = run_node("empty")
    for key in ("missing", "error", "nodesks"):
        assert "No desk briefs filed yet." in result[key], key
        assert "desk-brief-card" not in result[key], key
    assert "Desk briefs data 404" in result["error"]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_viz_escapes_every_string_and_drops_non_http_urls():
    html = run_node("escape")["html"]
    assert "<img" not in html
    assert "javascript:" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert 'href="https://example.com/&lt;img src=x onerror=alert(1)&gt;"' in html
