"""Queue lag and execution are different costs; measure them apart."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import measure_workflow_load as load  # noqa: E402


def _run(workflow: str, conclusion: str, created: str, started: str, updated: str) -> dict:
    return {
        "workflowName": workflow,
        "conclusion": conclusion,
        "createdAt": created,
        "startedAt": started,
        "updatedAt": updated,
    }


def test_summarise_splits_queue_lag_from_execution() -> None:
    runs = [
        _run("Auto - Agent PR Merge", "success",
             "2026-10-16T10:00:00Z", "2026-10-16T10:30:00Z", "2026-10-16T10:35:00Z"),
        _run("Auto - Agent PR Merge", "cancelled",
             "2026-10-16T11:00:00Z", "2026-10-16T11:01:00Z", "2026-10-16T11:03:00Z"),
        _run("Data Pipeline", "success",
             "2026-10-16T12:00:00Z", "2026-10-16T12:00:30Z", "2026-10-16T12:49:00Z"),
    ]
    summary = load.summarise(runs)
    merge = summary["Auto - Agent PR Merge"]
    assert merge["runs"] == 2
    assert merge["cancelled_share"] == 0.5
    # Queue lag is GitHub's scheduler: 30 min and 1 min waits.
    assert merge["queue_median_seconds"] == 930.0
    # Execution is runner time: 5 min and 2 min.
    assert merge["execution_total_minutes"] == 7.0
    assert summary["Data Pipeline"]["execution_median_seconds"] == 2910.0


def test_summarise_tolerates_missing_started_at() -> None:
    runs = [_run("X", "", "2026-10-16T10:00:00Z", "", "2026-10-16T10:05:00Z")]
    summary = load.summarise(runs)
    assert summary["X"]["queue_median_seconds"] == 0.0
    assert summary["X"]["execution_total_minutes"] == 5.0
