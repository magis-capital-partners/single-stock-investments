"""Migration may rewrite only its managed .gitattributes block.

LS-algo intake ad6fd761 checked out a tree without the root attributes file,
then migrate_dashboard_sources.py wrote a new file that contained only the
private-snapshot section. That commit deleted the global eol rules and the
checksum-protected research publication rules.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migrate_dashboard_sources as migration

MARKER = migration.ATTRIBUTE_MARKER
END = migration.ATTRIBUTE_END
PREAMBLE = "*.yml text eol=lf\n*.py text eol=lf\n# Keep checksum-protected research publications identical across platforms.\n/dashboard/data/shorts_net_edge_v3.json text eol=lf\n"
TRAILER = "/_system/scripts/short_framework/adapters.cjs text eol=lf\n\n/dashboard/third-plus-allocation.js text eol=lf\n/dashboard/data/free_short_packets/** text eol=lf\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    attributes = repo / ".gitattributes"
    block = f"{MARKER}\n/dashboard/private-assets.json text eol=lf\n{END}\n"
    attributes.write_text(PREAMBLE + block + TRAILER, encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-m", "seed")
    return repo


def test_rewrite_keeps_lines_outside_the_managed_block(tmp_path: Path):
    repo = _repo(tmp_path)
    migration.write_public_attributes(repo, {"assets": {"data/tickers/RX.V.json": {}}, "repository_assets": {}})
    text = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert PREAMBLE in text
    assert TRAILER in text
    assert '"/dashboard/data/tickers/RX.V.json" text eol=lf' in text
    assert text.index(PREAMBLE) < text.index(MARKER) < text.index(END) < text.index(TRAILER.strip().splitlines()[0])


def test_missing_worktree_file_does_not_drop_head_rules(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / ".gitattributes").unlink()
    migration.write_public_attributes(repo, {"assets": {}, "repository_assets": {}})
    text = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert "*.yml text eol=lf" in text
    assert "shorts_net_edge_v3.json" in text
    assert "free_short_packets" in text
    assert "third-plus-allocation.js" in text
    assert text.startswith("*.yml text eol=lf\n")
    assert text.rstrip().endswith("/dashboard/data/free_short_packets/** text eol=lf")


def test_restored_attributes_keep_the_rules_ad6fd761_deleted():
    text = Path(__file__).resolve().parents[3].joinpath(".gitattributes").read_text(encoding="utf-8")
    for line in (
        "*.yml text eol=lf",
        "*.yaml text eol=lf",
        "*.py text eol=lf",
        "*.sh text eol=lf",
        "/_system/data/reverse_splits/net_edge_audits_v3/** text eol=lf",
        "/dashboard/data/free_short_packets/** text eol=lf",
        "/dashboard/data/shorts_net_edge_v3.json text eol=lf",
        "/dashboard/third-plus-allocation.js text eol=lf",
        '"/dashboard/data/tickers/RX.V.json" text eol=lf',
    ):
        assert line in text
    assert text.index("*.yml text eol=lf") < text.index(MARKER)
    assert text.index(END) < text.index("/dashboard/third-plus-allocation.js text eol=lf")
