#!/usr/bin/env python3
"""Guard intake-full CI: Darwin deps + lazy imports for ls-algo pipeline step."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REBUILD_ACTION = ROOT / ".github" / "actions" / "rebuild-data" / "action.yml"
DARWIN_INIT = ROOT / "_system" / "scripts" / "darwin" / "__init__.py"
REBUILD = ROOT / "_system" / "scripts" / "ci_rebuild_profile.py"


class RebuildDataDarwinDepsTests(unittest.TestCase):
    def test_full_profile_includes_ls_algo_valuation_pipeline(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REBUILD), "full", "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn(
            "_system/scripts/darwin/run_ls_algo_valuation_pipeline.py",
            proc.stdout,
        )

    def test_rebuild_action_installs_darwin_deps_for_full_profiles(self) -> None:
        text = REBUILD_ACTION.read_text(encoding="utf-8")
        self.assertIn("Install Darwin dependencies", text)
        self.assertIn("requirements-darwin.txt", text)
        self.assertIn("inputs.profile == 'full'", text)
        self.assertIn("inputs.profile == 'intake-full'", text)

    def test_darwin_package_lazy_loads_run_pipeline(self) -> None:
        text = DARWIN_INIT.read_text(encoding="utf-8")
        # Module-level eager import broke intake-full when numpy was absent.
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        module_level = []
        for line in lines:
            if line.startswith("def "):
                break
            module_level.append(line)
        joined = "\n".join(module_level)
        self.assertNotIn("from .pipeline import run_pipeline", joined)
        self.assertIn("def __getattr__", text)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
