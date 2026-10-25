"""Run the stock-workspace financial-display regressions in the repository test suite."""
import shutil
import subprocess
from pathlib import Path
import pytest

@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is required for dashboard display tests")
def test_research_workspace_display_contracts():
    suite = Path(__file__).with_suffix(".cjs")
    result = subprocess.run(["node", "--test", str(suite)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
