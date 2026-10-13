"""The package never touches a broker, runs as a module from the repo root, and imports in CI's thin environment."""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap

import pytest

from conftest import ROOT, SCRIPTS

PACKAGE = SCRIPTS / "reverse_splits"
BROKER_TOKENS = ("ib_" + "insync", "ib_" + "async", "ibapi", "clientId", "reqMktData", "shortableShares")
# Modules the CI job (pytest + numpy + scipy only) must be able to import. backtest.py and
# report.py are the legacy pandas engine and are deliberately not on this list.
LIGHT_MODULES = (
    "reverse_splits.config", "reverse_splits.utils", "reverse_splits.db", "reverse_splits.ledger",
    "reverse_splits.export_ledger", "reverse_splits.import_ledger", "reverse_splits.filings",
    "reverse_splits.event_audit", "reverse_splits.adjust", "reverse_splits.execute", "reverse_splits.book",
    "reverse_splits.realism", "reverse_splits.replay", "reverse_splits.research_lens", "reverse_splits.framework_plan",
    "reverse_splits.strategy", "reverse_splits.fundamentals", "reverse_splits.analysis", "reverse_splits.rerun",
    "reverse_splits.run_book", "reverse_splits.controls", "reverse_splits.ingest_splits", "reverse_splits.enrich_edgar",
    "reverse_splits.enrich_edgar_fast", "reverse_splits.ingest_prices", "reverse_splits.ingest_finra",
    "reverse_splits.borrow", "reverse_splits.snapshot_export", "reverse_splits.classify_exchanges",
    "reverse_splits.rerun_sources", "reverse_splits.serve", "reverse_splits.cli",
    "reverse_splits.databento_bars", "reverse_splits.split_detector", "reverse_splits.filing_check", "reverse_splits.import_detections", "reverse_splits.databento_prices",
    "build_reverse_splits_dashboard", "check_reverse_splits",
)
BLOCKED = ("pandas", "yfinance", "requests", "bs4", "lxml", "dateutil", "tqdm", "exchange_calendars", "matplotlib", "openpyxl",
           "databento")


def test_no_broker_client_anywhere_in_the_package():
    offenders = []
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in BROKER_TOKENS:
            if token in text:
                offenders.append(f"{path.name}: {token}")
    assert offenders == []
    config = (ROOT / "_system" / "data" / "reverse_splits" / "config.toml").read_text(encoding="utf-8")
    assert "[ibkr]" not in config
    assert not re.search(r"^\s*client_id\s*=", config, re.M)
    for extra in ("build_reverse_splits_dashboard.py", "check_reverse_splits.py"):
        text = (SCRIPTS / extra).read_text(encoding="utf-8")
        assert not any(token in text for token in BROKER_TOKENS), extra


def test_borrow_module_only_imports_csv_rows():
    text = (PACKAGE / "borrow.py").read_text(encoding="utf-8")
    assert "def import_ibkr_slb_csv" in text
    assert "connect(" not in text and "socket" not in text
    assert "def snapshot_tickers" not in text and "def snapshot_open_events" not in text


def test_cli_runs_as_a_module_from_the_repo_root():
    proc = subprocess.run(
        [sys.executable, "-m", "_system.scripts.reverse_splits.cli", "--help"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    for command in ("export-ledger", "import-ledger", "build-dashboard", "check", "borrow-csv", "seed"):
        assert command in proc.stdout
    assert "ibkr-borrow" not in proc.stdout


def test_ledger_and_dashboard_modules_import_without_the_heavy_dependencies():
    code = textwrap.dedent(
        f"""
        import importlib, sys
        for name in {BLOCKED!r}:
            sys.modules[name] = None  # ImportError on import
        sys.path.insert(0, {str(SCRIPTS)!r})
        failures = []
        for name in {LIGHT_MODULES!r}:
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{{name}}: {{type(exc).__name__}}: {{exc}}")
        print("\\n".join(failures))
        raise SystemExit(1 if failures else 0)
        """
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("name", ["backtest", "report"])
def test_legacy_pandas_modules_are_documented_as_such(name):
    text = (PACKAGE / f"{name}.py").read_text(encoding="utf-8")
    assert "import pandas as pd" in text  # legacy engine; not imported by the dashboard or the checker


def test_dateutil_is_gone_from_the_parsers():
    for name in ("filings.py", "event_audit.py", "utils.py"):
        assert "dateutil" not in (PACKAGE / name).read_text(encoding="utf-8"), name
