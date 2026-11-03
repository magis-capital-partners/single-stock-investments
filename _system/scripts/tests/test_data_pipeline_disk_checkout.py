"""Data Pipeline jobs that died on a full checkout stay inside a runner disk.

The tracked tree is about 53 GiB, and 41 GiB of that is investor-document
PDFs and HTML. The private research vault is about 19 GiB more. buyback-radar,
downloads, drive, activist, and company-source-backfill were still checking
out one or both of those wholes. These tests pin the narrowed paths each job
actually reads and writes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import ci_rebuild_profile  # noqa: E402
from ci_sparse_checkout_paths import paths_for_profile  # noqa: E402
from download_all_holdings import planned_batch, select_batch  # noqa: E402
from build_company_research import preserve_unscanned_records  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
DATA = yaml.safe_load((WORKFLOWS / "data-pipeline.yml").read_text(encoding="utf-8"))
BACKFILL = yaml.safe_load((WORKFLOWS / "company-source-backfill.yml").read_text(encoding="utf-8"))

VAULT_EXTRAS = [
    "/vic-research/",
    "/superinvestor-letters/insights.json",
    "/podcasts/insights.json",
    "/videos/insights.json",
]

ACTIVIST_VAULT_EXTRAS = [
    "/superinvestor-letters/letters_index.json",
    "/superinvestor-letters/drive_import_manifest.json",
    "/investment-wisdom/hk_ticker_index.json",
    "/valuation-underwriting/packets/",
]


def _job(name: str) -> dict:
    return DATA["jobs"][name]


def _steps(job: dict) -> list[dict]:
    return job["steps"]


def _run(job: dict) -> str:
    return "\n".join(str(step.get("run") or "") for step in _steps(job))


def _vault_steps(job: dict) -> list[dict]:
    return [step for step in _steps(job) if str(step.get("uses") or "").endswith("checkout-vault")]


def test_buyback_downloads_and_drive_no_longer_check_out_the_full_tree():
    for name in ("buyback-radar", "downloads", "drive"):
        text = _run(_job(name))
        assert "ci_checkout_workspace.sh full" not in text, name
        assert f"ci_checkout_workspace.sh {name}" in text, name
    assert _vault_steps(_job("buyback-radar"))[0]["with"]["publication-only"] == "true"
    assert _vault_steps(_job("downloads"))[0]["with"]["publication-only"] == "true"
    drive_vault = _vault_steps(_job("drive"))[0]["with"]
    assert drive_vault["publication-only"] == "true"
    for pattern in VAULT_EXTRAS:
        assert pattern in drive_vault["extra-paths"]
    assert "superinvestor-letters/" not in drive_vault["extra-paths"].replace(
        "/superinvestor-letters/insights.json", ""
    )


def test_buyback_seeds_the_path_script_before_the_narrow_checkout():
    """Run 41431614985 failed here. The listed profile does not check out
    _system first, so the script that emits the path list has to be seeded
    on its own. Seeding all of _system would download the activist PDFs."""
    shell = (ROOT / "_system/scripts/ci_checkout_workspace.sh").read_text(encoding="utf-8")
    arm = re.search(r"(?ms)^  buyback-radar\)\n(.*?\n    ;;\n)", shell)
    assert arm, "ci_checkout_workspace.sh has no buyback-radar profile"
    body = arm.group(1)
    seed = body.index("_system/scripts/ci_sparse_checkout_paths.py")
    apply = body.index("apply_sparse_paths listed")
    assert seed < apply
    assert "sparse-checkout set _system .github" not in body
    assert "apply_sparse_paths files-only" not in body


def test_buyback_frees_disk_before_checkout_and_lists_every_committed_path():
    steps = _steps(_job("buyback-radar"))
    assert "free-disk-space" in steps[0]["uses"]
    assert "actions/checkout" in steps[1]["uses"]
    paths = set(paths_for_profile("buyback-radar"))
    paths.add(".github")
    commit = next(step for step in steps if str(step.get("uses") or "").endswith("commit-main"))
    for rel in str(commit["with"]["git_add"]).split():
        assert any(rel == entry or rel.startswith(entry + "/") or entry.startswith(rel + "/") for entry in paths), rel
    for required in (
        "dashboard/data/buyback_snapshots",
        "dashboard/data/tickers",
        "dashboard/data/agent_shards",
        "dashboard/data/special_situations.json",
        "dashboard/data/short_alpha.json",
        "_system/reference/market-data/fundamentals/index_float_adv.json",
    ):
        assert any(required == entry or required.startswith(entry + "/") or entry.startswith(required) for entry in paths), required


def test_downloads_keeps_research_trees_and_not_the_filing_archive():
    paths = paths_for_profile("downloads")
    holdings = json.loads((ROOT / "_system/portfolio/registry.json").read_text(encoding="utf-8"))["holdings"]
    for ticker in holdings:
        assert f"{ticker}/research" in paths
    allowed_manifests = ("DOWNLOAD_MANIFEST.json", "TRANSCRIPT_MANIFEST.json")
    for path in paths:
        if "investor-documents" not in path:
            continue
        assert path.endswith(allowed_manifests), path
    job = _job("downloads")
    assert job["env"]["DASHBOARD_PRESERVE_DOCUMENT_REGISTRY"] == "1"
    assert job["env"]["DASHBOARD_PRESERVE_INFRA_ALWAYS"] == "1"
    text = _run(job)
    assert "--skip-indexes" in text
    assert "planned_batch" in text
    assert "build_folder_indexes.py" in text
    assert "free-disk-space" in _steps(job)[0]["uses"]


def test_drive_checkout_is_research_and_intake_not_filing_pdfs():
    paths = paths_for_profile("drive")
    assert any(path.endswith("/third-party-analyses") for path in paths)
    assert any(path.endswith("/research") for path in paths)
    assert any(path.endswith("/investor-documents/drive-intake") for path in paths)
    assert not any(path.endswith("/investor-documents") for path in paths)
    rebuild = next(step for step in _steps(_job("drive")) if str(step.get("uses") or "").endswith("rebuild-data"))
    assert rebuild["with"]["vault-publication-only"] == "true"
    for pattern in VAULT_EXTRAS:
        assert pattern in rebuild["with"]["vault-extra-paths"]
    assert _job("drive")["env"]["DASHBOARD_PRESERVE_INFRA_ALWAYS"] == "1"


def test_rebuild_checkouts_hold_every_path_a_desk_brief_cites():
    """Run 41540991704: the drive rebuild failed check_desk_briefs because the
    activism brief cites AGENT_INDEX.md, a root file the drive checkout left
    out. Both narrowed jobs that run build_dashboard_data need these paths."""
    cited: set[str] = set()
    for brief in (ROOT / "_system/data/desk_briefs").glob("*/*.json"):
        payload = json.loads(brief.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for entry in payload.get("inputs_read") or []:
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                cited.add(entry["path"])
    assert "AGENT_INDEX.md" in cited
    for profile in ("drive", "activist"):
        entries = {path.lstrip("/") for path in paths_for_profile(profile)} | {"_system", "dashboard", ".github"}
        for rel in sorted(cited):
            assert _covered(rel, entries), (profile, rel)
        assert "/AGENT_INDEX.md" in paths_for_profile(profile), profile


def test_desk_brief_input_patterns_are_anchored_and_literal(tmp_path: Path):
    import ci_sparse_checkout_paths

    desk = tmp_path / "activism"
    desk.mkdir()
    (desk / "2026-10-30.json").write_text(
        json.dumps(
            {
                "inputs_read": [
                    {"path": "AGENT_INDEX.md"},
                    {"path": "AAA/research/latest.json"},
                    {"path": "BBB/research/odd[1]*.md"},
                    {"path": "../outside.md"},
                    {"path": "/abs.md"},
                    {"path": "C:/x.md"},
                    "not-a-dict",
                ]
            }
        ),
        encoding="utf-8",
    )
    (desk / "broken.json").write_text("{", encoding="utf-8")
    with mock.patch.object(ci_sparse_checkout_paths, "DESK_BRIEFS_DIR", tmp_path):
        patterns = ci_sparse_checkout_paths.desk_brief_inputs()
    assert patterns == [
        "/AAA/research/latest.json",
        "/AGENT_INDEX.md",
        "/BBB/research/odd\\[1]\\*.md",
    ]

    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "-C", str(origin), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "t"], check=True)
    files = {
        "AGENT_INDEX.md": "index\n",
        "AAA/AGENT_INDEX.md": "nested\n",
        "AAA/research/latest.json": "{}\n",
        "AAA/investor-documents/sec-edgar/10-K.pdf": "filing",
        "BBB/research/odd[1]*.md": "odd\n",
        "BBB/research/odd1x.md": "glob would match this\n",
    }
    for relative, content in files.items():
        path = origin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(origin), "commit", "-q", "-m", "fixture"], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", "--no-checkout", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "sparse-checkout", "init", "--no-cone"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "sparse-checkout", "set", "--stdin"],
        input="\n".join(patterns) + "\n",
        text=True,
        check=True,
    )
    subprocess.run(["git", "-C", str(work), "checkout", "-q", "main"], check=True)
    assert (work / "AGENT_INDEX.md").is_file()
    assert (work / "AAA/research/latest.json").is_file()
    assert (work / "BBB/research/odd[1]*.md").is_file()
    assert not (work / "AAA/AGENT_INDEX.md").exists()
    assert not (work / "BBB/research/odd1x.md").exists()
    assert not (work / "AAA/investor-documents/sec-edgar/10-K.pdf").exists()


def test_company_source_backfill_checks_out_only_its_archive():
    steps = BACKFILL["jobs"]["backfill"]["steps"]
    assert "free-disk-space" in steps[0]["uses"]
    vault = next(step for step in steps if str(step.get("uses") or "").endswith("checkout-vault"))
    assert str(vault["with"]["publication-only"]).lower() == "true"
    assert str(vault["with"]["hydrate"]).lower() == "false"
    assert "/dashboard-private/company-source-backfill-v2/" in vault["with"]["extra-paths"]
    assert "superinvestor-letters" not in vault["with"]["extra-paths"]
    assert "podcasts" not in vault["with"]["extra-paths"]
    refresh = next(step for step in steps if step.get("name") == "Refresh the complete publication snapshot")
    assert refresh["env"]["COMPANY_SOURCE_ABSENT_COLLECTIONS_ARE_UNSCANNED"] == "1"


def test_planned_batch_matches_the_batch_select_persists(tmp_path: Path):
    holdings = {"BBB": {}, "AAA": {}, "CCC": {}}
    cursor = tmp_path / "cursor.json"
    first = planned_batch(holdings, 2, cursor)
    assert first == ["AAA", "BBB"]
    assert not cursor.exists()
    assert select_batch(holdings, 2, cursor) == first
    assert planned_batch(holdings, 2, cursor) == ["CCC", "AAA"]


def test_unscanned_vault_collections_keep_prior_records():
    records = {"seen": {"id": "seen", "origins": ["git"]}}
    previous = {
        "seen": {"id": "seen", "origins": ["git"], "availability": "current"},
        "letter": {"id": "letter", "origins": ["vault:superinvestor-letters"], "availability": "current"},
        "mixed": {"id": "mixed", "origins": ["vault:podcasts", "drive"], "title": "kept by the scan"},
    }
    kept = preserve_unscanned_records(records, previous, {"vault:superinvestor-letters", "vault:podcasts"})
    assert kept == 1
    assert records["letter"]["availability"] == "current"
    assert "mixed" not in records


def test_archive_sparse_pattern_does_not_check_out_letters(tmp_path: Path):
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "-C", str(origin), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "t"], check=True)
    files = {
        "dashboard-private/company-source-backfill-v2/manifest.json": "{}\n",
        "dashboard-private/company-source-backfill-v2/abc.zip": "zip",
        "superinvestor-letters/insights.json": "{}\n",
        "superinvestor-letters/fund/letter.txt": "letter",
        "podcasts/insights.json": "{}\n",
        "vic-research/AAA/note.txt": "vic",
    }
    for relative, content in files.items():
        path = origin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(origin), "commit", "-q", "-m", "fixture"], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "-C", str(origin), "clone", "-q", "--sparse", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "sparse-checkout", "init", "--no-cone"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "sparse-checkout", "set", "--no-cone", "--stdin"],
        input="/dashboard-private/migration-journal.jsonl\n",
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "sparse-checkout", "add", "--skip-checks", "--stdin"],
        input="/dashboard-private/company-source-backfill-v2/\n/vic-research/\n/superinvestor-letters/insights.json\n",
        text=True,
        check=True,
    )
    assert (work / "dashboard-private/company-source-backfill-v2/abc.zip").read_text() == "zip"
    assert (work / "vic-research/AAA/note.txt").read_text() == "vic"
    assert (work / "superinvestor-letters/insights.json").is_file()
    assert not (work / "superinvestor-letters/fund/letter.txt").exists()
    assert not (work / "podcasts/insights.json").exists()


def _covered(rel: str, entries: set[str]) -> bool:
    return any(rel == entry or rel.startswith(entry + "/") for entry in entries)


def test_activist_checks_out_its_trees_and_a_narrow_vault():
    """Run 41473899301 spent 15 minutes on the full tree, then timed out
    cloning the whole vault, so every scan step was skipped."""
    job = _job("activist")
    text = _run(job)
    assert "ci_checkout_workspace.sh full" not in text
    assert "ci_checkout_workspace.sh activist" in text
    assert "free-disk-space" in _steps(job)[0]["uses"]
    shell = (ROOT / "_system/scripts/ci_checkout_workspace.sh").read_text(encoding="utf-8")
    arm = re.search(r"(?m)^  ([a-z|-]*\bactivist\b[a-z|-]*)\)$", shell)
    assert arm and "downloads" in arm.group(1), "activist must share the research-tree arm"
    assert job["env"]["DASHBOARD_PRESERVE_DOCUMENT_REGISTRY"] == "1"
    assert job["env"]["DASHBOARD_PRESERVE_INFRA_ALWAYS"] == "1"

    vault = _vault_steps(job)
    assert len(vault) == 1
    rebuild = next(step for step in _steps(job) if str(step.get("uses") or "").endswith("rebuild-data"))
    for chosen, extras in (
        (vault[0]["with"]["publication-only"], vault[0]["with"]["extra-paths"]),
        (rebuild["with"]["vault-publication-only"], rebuild["with"]["vault-extra-paths"]),
    ):
        assert chosen == "true"
        assert extras.split() == ACTIVIST_VAULT_EXTRAS
        # Named files only. A whole letters or wisdom tree is what timed out.
        for line in extras.split():
            assert line not in {"/superinvestor-letters/", "/investment-wisdom/", "/podcasts/", "/videos/"}


def test_activist_paths_hold_what_the_scan_reads_and_writes_and_no_filings():
    paths = paths_for_profile("activist")
    holdings = json.loads((ROOT / "_system/portfolio/registry.json").read_text(encoding="utf-8"))["holdings"]
    for ticker in holdings:
        for sub in ("research", "third-party-analyses", "README.md"):
            assert f"{ticker}/{sub}" in paths, (ticker, sub)
    allowed = ("DOWNLOAD_MANIFEST.json", "TRANSCRIPT_MANIFEST.json", "research-notes")
    for path in paths:
        if "investor-documents" in path:
            assert path.endswith(allowed), path

    # Every file an activist index points at must be in the checkout, or the
    # verify and triage steps would see a report as missing.
    entries = set(paths) | {"_system", "dashboard", ".github"}
    refs = 0
    for ticker in holdings:
        index = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
        if not index.is_file():
            continue
        for report in json.loads(index.read_text(encoding="utf-8")).get("reports") or []:
            for key in ("local_file", "local_pdf", "canonical_file"):
                rel = report.get(key)
                if isinstance(rel, str) and rel and not rel.startswith("http"):
                    refs += 1
                    assert _covered(rel, entries), (ticker, key, rel)
    print(f"activist index refs checked: {refs}")


def test_sparse_add_leaves_files_outside_the_checkout_in_the_index(tmp_path: Path):
    """commit-main stages `git add --sparse -A`. On the activist checkout that
    must stage scan output and never delete the filing PDFs left out."""
    action = (ROOT / ".github/actions/commit-main/action.yml").read_text(encoding="utf-8")
    assert "git add --sparse ${{ inputs.git_add }}" in action
    for step in _steps(_job("activist")):
        if str(step.get("uses") or "").endswith("commit-main"):
            assert "git_add" not in (step.get("with") or {}), step.get("name")

    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "-C", str(origin), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "t"], check=True)
    files = {
        "AAA/investor-documents/sec-edgar/10-K.pdf": "filing",
        "AAA/third-party-analyses/activist_reports_index.json": "{}\n",
        "AAA/research/thesis.md": "thesis\n",
        "_system/data/activist_scan_state.json": "{}\n",
    }
    for relative, content in files.items():
        path = origin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(origin), "commit", "-q", "-m", "fixture"], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", "--no-checkout", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "sparse-checkout", "init", "--no-cone"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "sparse-checkout", "set", "--stdin"],
        input="_system\nAAA/research\nAAA/third-party-analyses\n",
        text=True,
        check=True,
    )
    subprocess.run(["git", "-C", str(work), "checkout", "-q", "main"], check=True)
    assert not (work / "AAA/investor-documents/sec-edgar/10-K.pdf").exists()

    (work / "AAA/third-party-analyses/activist_reports_index.json").write_text('{"reports": []}\n', encoding="utf-8")
    (work / "AAA/third-party-analyses/activist_reports/long").mkdir(parents=True)
    (work / "AAA/third-party-analyses/activist_reports/long/13D.htm").write_text("13D", encoding="utf-8")
    (work / "_system/data/activist_scan_state.json").write_text('{"sec": {}}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "--sparse", "-A"], check=True)
    staged = subprocess.run(
        ["git", "-C", str(work), "diff", "--cached", "--name-status"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "M\tAAA/third-party-analyses/activist_reports_index.json" in staged
    assert "A\tAAA/third-party-analyses/activist_reports/long/13D.htm" in staged
    assert "M\t_system/data/activist_scan_state.json" in staged
    assert "investor-documents" not in staged
    listed = subprocess.run(
        ["git", "-C", str(work), "ls-files", "-v", "AAA/investor-documents/sec-edgar/10-K.pdf"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert listed.startswith("S ")


def test_activist_rebuild_keeps_the_document_registry_when_asked():
    registry = ["_system/scripts/build_document_registry.py"]
    assert registry in ci_rebuild_profile.PROFILES["activist"]
    with mock.patch.dict(os.environ, {"DASHBOARD_PRESERVE_DOCUMENT_REGISTRY": "1"}):
        assert ci_rebuild_profile.should_skip_step(registry)
        assert "PRESERVE_DOCUMENT_REGISTRY" in ci_rebuild_profile.skip_reason(registry)
        assert not ci_rebuild_profile.should_skip_step(["_system/scripts/build_activist_feed.py"])
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DASHBOARD_PRESERVE_DOCUMENT_REGISTRY", None)
        assert not ci_rebuild_profile.should_skip_step(registry)


def test_heal_activist_runs_only_the_activist_job():
    triggers = DATA.get("on") or DATA.get(True)
    assert "heal-activist" in triggers["repository_dispatch"]["types"]
    assert "workflow_dispatch" not in triggers
    decide = _run(_job("decide"))
    assert '"dispatch:heal-activist") activist=true ;;' in decide
