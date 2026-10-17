"""Load-reduction contracts: no sleeping gates, no per-push deploys, no peak crons."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def on_block(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


def test_data_pipeline_crons_avoid_the_hour_and_half_hour() -> None:
    crons = [entry["cron"] for entry in on_block(load("data-pipeline.yml"))["schedule"]]
    assert crons, "data pipeline must stay scheduled"
    for cron in crons:
        minute = cron.split()[0]
        assert minute not in {"0", "30"}, f"peak-minute cron: {cron}"


def test_automerge_code_gate_is_a_short_one_shot_assessor() -> None:
    workflow = load("marvin-pr-automerge.yml")
    triggered = on_block(workflow)["workflow_run"]["workflows"]
    # A completion of any gating workflow re-invokes the gate; the gate does
    # not sleep until checks finish.
    for name in ("Research quality", "Python tests", "CI bootstrap smoke", "LLM Workflow Governance"):
        assert name in triggered
    gate = workflow["jobs"]["code-gate"]
    assert gate["timeout-minutes"] <= 20
    # Twin runs queue, never cancel (PR #1022, pinned in test_automerge_workflow).
    assert gate["concurrency"]["cancel-in-progress"] is False
    assert "pending" in gate["outputs"]
    run = next(s["run"] for s in gate["steps"] if s.get("id") == "checks")
    assert "DEADLINE=$(( $(date +%s) + 900 ))" in run
    assert 'echo "pending=true" >> "$GITHUB_OUTPUT"' in run
    # Failure is still failure: a red check exits non-zero, never merges.
    assert '*) FAILED="$FAILED $NAME($CONCLUSION)"' in run
    merge = workflow["jobs"]["merge"]
    assert "needs.code-gate.outputs.head_sha != ''" in merge["if"]


def test_push_deploys_fingerprint_first() -> None:
    workflow = load("dashboard-pages.yml")
    gate = workflow["jobs"]["deploy-gate"]
    assert "push" in gate["if"]
    build = workflow["jobs"]["build"]
    assert "needs.deploy-gate.outputs.should_deploy == 'true'" in build["if"]
    # Manual dispatch stays an unconditional recovery path.
    assert "workflow_dispatch" in build["if"]


def test_research_quality_schedule_skips_an_unchanged_head() -> None:
    text = (WORKFLOWS / "research-quality.yml").read_text(encoding="utf-8")
    assert "listWorkflowRuns" in text
    assert "already has a successful Research quality run" in text
    # Schedule cadence is unchanged: detection latency is kept, work is not.
    crons = [entry["cron"] for entry in on_block(load("research-quality.yml"))["schedule"]]
    assert crons == ["37 1,7,13,19 * * *"]


def test_news_lane_has_a_duplicate_run_guard() -> None:
    workflow = load("data-pipeline.yml")
    news = workflow["jobs"]["news"]
    ids = [s.get("id") for s in news["steps"]]
    assert "preflight" in ids and "ingest" in ids
    ingest = next(s for s in news["steps"] if s.get("id") == "ingest")
    assert ingest["if"] == "steps.preflight.outputs.changed == 'true'"
    preflight = next(s for s in news["steps"] if s.get("id") == "preflight")
    assert "pipeline_preflight.py news" in preflight["run"]
