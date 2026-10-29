"""Investors > Signals: full list, fund rail, and the per-row funds and 13F disclosure."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SUITE = Path(__file__).with_name("test_investor_signals_ui.cjs")


def test_investor_signals_ui_suite_passes():
    node = shutil.which("node")
    if not node:
        pytest.skip("needs node")
    proc = subprocess.run([node, "--test", str(SUITE)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
