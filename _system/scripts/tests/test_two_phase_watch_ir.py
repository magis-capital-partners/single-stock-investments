"""The IR-allowlist path of the INV two-phase cooling watch.

two-phase-watch.yml always passes --ir, and the file's first commit lost the
IR fetcher's def line: its body sat unreachable after _ir_downloadable's
return, so every scheduled run from 2026-08-30 died on
"NameError: name 'fetch_ir' is not defined" and the INV pane went stale.
test_two_phase_watch.py never called run(), so nothing caught it.

No network: http_get is stubbed and every path is redirected into tmp_path.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import two_phase_watch as tpw  # noqa: E402

WORKFLOW = SCRIPTS.parents[1] / ".github/workflows/two-phase-watch.yml"
TODAY = "2026-09-20"
INDEX = "https://ir.innventure.com/news-events/press-releases"
RELEASE = ("https://ir.innventure.com/news-events/press-releases/detail/42/"
           "accelsius-two-phase-cooling-order")


def _isolate(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    inv = tmp_path / "INV"
    evidence = inv / "research" / "evidence"
    competitive = inv / "investor-documents" / "competitive"
    paths = {
        "ROOT": tmp_path,
        "INV_DIR": inv,
        "EVIDENCE_DIR": evidence,
        "LEDGER_PATH": evidence / "two_phase_watch_ledger.json",
        "COMPETITIVE_DIR": competitive,
        "SEEN_URLS_PATH": competitive / "seen_urls.json",
        "REVIEWS_DIR": tmp_path / "_system" / "reviews" / "pending",
    }
    for name, value in paths.items():
        monkeypatch.setattr(tpw, name, value)
    monkeypatch.setattr(tpw.time, "sleep", lambda _seconds: None)
    return paths


def _stub_http(monkeypatch) -> list[str]:
    pages = {
        INDEX: (b'<html><body><h1>Press releases</h1>'
                b'<a href="/news-events/press-releases/detail/42/'
                b'accelsius-two-phase-cooling-order">Accelsius order</a>'
                b'</body></html>', "text/html"),
        RELEASE: (b"<html><body><p>Accelsius NeuCool two-phase direct-to-chip "
                  b"cooling enters production with a hyperscaler.</p></body></html>",
                  "text/html"),
    }
    calls: list[str] = []

    def http_get(url: str, *, accept: str = "") -> tuple[bytes, str, int]:
        calls.append(url)
        if url in pages:
            body, ctype = pages[url]
            return body, ctype, 200
        return b"", "", 404

    monkeypatch.setattr(tpw, "http_get", http_get)
    return calls


def test_run_with_ir_pages_fetches_the_allowlist_and_records_hits(tmp_path, monkeypatch):
    paths = _isolate(tmp_path, monkeypatch)
    calls = _stub_http(monkeypatch)

    ledger = tpw.run(fetch_ir_pages=True, fetch_events=False, fetch_news=False,
                     skip_local=True, today=TODAY)

    # Every allowlisted IR page is requested, then the linked release.
    for _name, url in tpw.IR_PAGES:
        assert url in calls
    assert RELEASE in calls
    ir_hits = [hit for hit in ledger["hits"] if hit.get("source_kind") == "ir"]
    assert any(hit["source_url"] == RELEASE for hit in ir_hits)
    saved = list((paths["COMPETITIVE_DIR"] / "ir").glob(f"{TODAY}_*.htm"))
    assert len(saved) == 1
    assert RELEASE in json.loads(paths["SEEN_URLS_PATH"].read_text(encoding="utf-8"))
    on_disk = json.loads(paths["LEDGER_PATH"].read_text(encoding="utf-8"))
    assert on_disk["as_of"] == TODAY
    assert any(hit.get("source_url") == RELEASE for hit in on_disk["hits"])


def test_a_seen_release_is_not_downloaded_twice(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    calls = _stub_http(monkeypatch)
    tpw.run(fetch_ir_pages=True, fetch_events=False, fetch_news=False,
            skip_local=True, today=TODAY)
    calls.clear()
    tpw.run(fetch_ir_pages=True, fetch_events=False, fetch_news=False,
            skip_local=True, today="2026-09-27")
    assert RELEASE not in calls


def _git_add_args(workflow_text: str) -> str:
    """The commit step's git_add input, as commit-main hands it to the shell."""
    lines = workflow_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith("git_add:"))
    indent = len(lines[start]) - len(lines[start].lstrip())
    head = lines[start].split("git_add:", 1)[1].strip()
    parts = [] if head in {">", ">-", "|", "|-"} else [head]
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        if line.strip() and not line.strip().startswith("#"):
            parts.append(line.strip())
    return " ".join(parts)


@pytest.mark.skipif(not (shutil.which("git") and shutil.which("bash")),
                    reason="git and bash required")
def test_commit_step_survives_a_week_without_a_pending_review(tmp_path):
    # commit-main runs `git add --sparse ${{ inputs.git_add }}` unquoted, so a
    # glob with no match reaches git literally: "pathspec did not match".
    repo = tmp_path / "repo"
    for rel in ("INV/research/evidence/two_phase_watch_ledger.json",
                "INV/investor-documents/competitive/seen_urls.json",
                "_system/reviews/pending/OTHER_review.md",
                "dashboard/data/tickers/INV.json"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("{}\n", encoding="utf-8")

    def git(*args):
        return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                               "-c", "core.autocrlf=false", *args],
                              cwd=repo, capture_output=True, text=True)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (repo / "INV/research/evidence/two_phase_watch_ledger.json").write_text(
        '{"as_of": "2026-09-27"}\n', encoding="utf-8")
    args = _git_add_args(WORKFLOW.read_text(encoding="utf-8"))
    run = subprocess.run(["bash", "-c", f"git add --sparse {args}"], cwd=repo,
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    staged = git("diff", "--cached", "--name-only").stdout.split()
    assert staged == ["INV/research/evidence/two_phase_watch_ledger.json"]


def test_schedule_avoids_the_congested_minutes():
    minutes = re.findall(r'cron:\s*"(\S+)\s', WORKFLOW.read_text(encoding="utf-8"))
    assert minutes and all(int(minute) not in {0, 15, 30} for minute in minutes)
