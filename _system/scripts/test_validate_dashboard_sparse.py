from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from _system.scripts.validate_dashboard_data import repository_file_exists


class RepositoryFileExistsTests(unittest.TestCase):
    def run_git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_tracked_sparse_file_counts_as_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_git(root, "init")
            self.run_git(root, "config", "user.name", "CI Test")
            self.run_git(root, "config", "user.email", "ci@example.test")
            report = root / "ABC" / "third-party-analyses" / "activist_reports" / "report.htm"
            report.parent.mkdir(parents=True)
            report.write_text("report", encoding="utf-8")
            self.run_git(root, "add", ".")
            self.run_git(root, "commit", "-m", "fixture")
            report.unlink()

            self.assertFalse(repository_file_exists(root, report.relative_to(root).as_posix()))

            self.run_git(root, "config", "core.sparseCheckout", "true")
            self.assertTrue(repository_file_exists(root, report.relative_to(root).as_posix()))

    def test_untracked_sparse_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_git(root, "init")
            self.run_git(root, "config", "core.sparseCheckout", "true")
            self.assertFalse(repository_file_exists(root, "ABC/missing-report.htm"))


if __name__ == "__main__":
    unittest.main()
