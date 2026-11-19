"""Exercise the pilot display logic in the standard repository test run."""
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is required for dashboard display tests")
def test_stock_one_pager_display():
    suites = [str(Path(__file__).with_name(name)) for name in ("test_stock_one_pager.cjs", "test_stock_performance.cjs", "test_stock_valuation.cjs")]
    result = subprocess.run(["node", "--test", *suites], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
