#!/usr/bin/env python3
"""Refresh job-level, work-done lane receipts from GitHub Actions runs.

A lane's receipt advances only when the lane's JOB concluded ``success`` in a
run on main and, if the lane declares a ``work_step``, that step concluded
``success`` too (it was not skipped by an ``if:``). A job killed by its
``timeout-minutes`` is a failure even though GitHub reports it as
"cancelled". Skipped and no-op runs never refresh a receipt. See
``lane_registry.py`` for why; the short version is that whole-run receipts
kept the ls-algo intake "fresh" for six weeks while every real run failed.

Each receipt also records the newest meaningful outcome and the failures since
the last success, which the supervisor fingerprints. Runs are classified
incrementally: ``scanned_through`` is the highest run id below which every
listed run had completed when last scanned, so steady state costs one runs
listing per workflow plus one jobs call per new run.

This script never exits non-zero because a lane has no success: that is a
finding for the supervisor, not a reason to kill the supervisor before it can
report it. (The old version exited 1, which would have failed the supervisor
job before it planned anything the first time any lane never succeeded.)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_registry as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUNS_PER_WORKFLOW = 50
MAX_FAILURES = 10
# GITHUB_TOKEN allows 1,000 REST calls an hour per repository and the
# supervisor also reads annotations and logs. A first build walks at most the
# 50-run listing of each workflow whose lanes have not succeeded in it; past
# this budget the unscanned runs are simply picked up by the next build.
MAX_JOB_CALLS = 450


class GhApi:
    """Read-only Actions API through the gh CLI, with per-build caches."""

    def __init__(self, repository: str, max_job_calls: int = MAX_JOB_CALLS):
        self.repository = repository
        self.errors: list[str] = []
        self._cache: dict[str, object] = {}
        self.job_calls = 0
        self.max_job_calls = max_job_calls

    def _get(self, path: str):
        if path in self._cache:
            return self._cache[path]
        try:
            proc = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.errors.append(f"{path}: {exc}")
            return None
        if proc.returncode != 0:
            self.errors.append(f"{path}: {proc.stderr.strip()[:200]}")
            return None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.errors.append(f"{path}: unparseable response")
            return None
        self._cache[path] = payload
        return payload

    def workflow_runs(self, workflow_file: str, per_page: int = RUNS_PER_WORKFLOW):
        payload = self._get(f"repos/{self.repository}/actions/workflows/{workflow_file}"
                            f"/runs?branch=main&per_page={per_page}")
        if not isinstance(payload, dict):
            return None
        return [run for run in payload.get("workflow_runs") or []
                if run.get("event") != "pull_request"]

    def workflow_state(self, workflow_file: str):
        payload = self._get(f"repos/{self.repository}/actions/workflows/{workflow_file}")
        return payload.get("state") if isinstance(payload, dict) else None

    def run_jobs(self, run_id: int):
        path = f"repos/{self.repository}/actions/runs/{run_id}/jobs?per_page=100"
        if path not in self._cache:
            if self.job_calls >= self.max_job_calls:
                if not any(e.startswith("job-call budget") for e in self.errors):
                    self.errors.append(f"job-call budget of {self.max_job_calls} reached;"
                                       " the rest is scanned next run")
                return None
            self.job_calls += 1
        payload = self._get(path)
        return payload.get("jobs") if isinstance(payload, dict) else None

    def job_annotations(self, job_id: int):
        payload = self._get(f"repos/{self.repository}/check-runs/{job_id}/annotations")
        return payload if isinstance(payload, list) else None


def _is_timeout(api) -> callable:
    def check(job: dict) -> bool:
        annotations = api.job_annotations(job.get("id")) or []
        return any(lr.TIMEOUT_MARKER in str(item.get("message") or "")
                   for item in annotations)
    return check


def _legacy_outcome(run: dict) -> dict | None:
    """Whole-run outcome for a lane that declares no job (contract violation;
    kept only so an undeclared job degrades to the old behaviour, not a crash)."""
    conclusion = run.get("conclusion")
    outcome = {"success": lr.SUCCESS, "failure": lr.FAILURE,
               "timed_out": lr.TIMEOUT}.get(conclusion, lr.CANCELLED)
    return {"outcome": outcome, "at": run.get("updated_at") or run.get("created_at"),
            "job_id": None, "failed_step": None}


def refresh_lane(root: Path, lane: dict, api, runs: list[dict]) -> tuple[dict, list[str]]:
    """Return (receipt, notes) for one lane given its workflow's recent runs."""
    notes: list[str] = []
    existing = lr.load_receipt(root, lane["name"])
    base = existing if lr.receipt_is_current(existing, lane) else None
    if existing and base is None:
        notes.append("previous receipt predates the job-level contract; rebuilt from runs")
    receipt = {
        "schema_version": lr.RECEIPT_SCHEMA,
        "lane": lane["name"],
        "workflow_file": lane["workflow_file"],
        "job": lane.get("job"),
        "work_step": lane.get("work_step"),
        "last_success_at": None, "run_id": None, "head_sha": None, "url": None,
        "conclusion": None, "latest": None, "failures": [],
        "scanned_through": 0, "scan_floor_at": None,
    }
    if base:
        for key in receipt:
            if key in base:
                receipt[key] = base[key]
        receipt["schema_version"] = lr.RECEIPT_SCHEMA
    scanned_through = int(receipt.get("scanned_through") or 0)
    if receipt.get("scan_floor_at") is None and runs:
        receipt["scan_floor_at"] = min(str(r.get("created_at") or "") for r in runs) or None

    pending = [int(r["id"]) for r in runs if r.get("status") != "completed"]
    watermark = (min(pending) - 1) if pending else max((int(r["id"]) for r in runs),
                                                       default=scanned_through)
    watermark = max(watermark, scanned_through)
    is_timeout = _is_timeout(api)
    failures = {int(f["run_id"]): f for f in receipt.get("failures") or []
                if isinstance(f, dict) and f.get("run_id")}
    latest = receipt.get("latest") if isinstance(receipt.get("latest"), dict) else None

    # Newest first, stopping at the first work-done success: nothing older can
    # produce a newer success or a failure that happened after it. Steady state
    # costs one jobs call per new run; only a lane that has not succeeded in
    # the whole listing (the dead ones) walks all of it, and jobs are cached
    # per run, so the Data Pipeline's nine lanes share one walk.
    for run in sorted(runs, key=lambda r: int(r["id"]), reverse=True):
        run_id = int(run["id"])
        if run_id <= scanned_through or run.get("status") != "completed":
            continue
        if lane.get("job"):
            jobs = api.run_jobs(run_id)
            if jobs is None:
                watermark = min(watermark, run_id - 1)   # rescan it next time
                continue
            result = lr.classify_lane_run(jobs, lane, is_timeout)
        else:
            result = _legacy_outcome(run)
        if result is None:
            continue
        outcome, at = result["outcome"], result["at"]
        entry = {"run_id": run_id, "at": at, "outcome": outcome,
                 "url": run.get("html_url"), "event": run.get("event"),
                 "job_id": result.get("job_id"), "failed_step": result.get("failed_step")}
        if outcome in (lr.SUCCESS, lr.FAILURE, lr.TIMEOUT):
            if latest is None or run_id > int(latest.get("run_id") or 0):
                latest = entry
        if outcome in lr.FAILING_OUTCOMES:
            failures[run_id] = entry
        if outcome == lr.SUCCESS:
            if str(at or "") > str(receipt.get("last_success_at") or ""):
                receipt.update({"last_success_at": at, "run_id": run_id,
                                "head_sha": run.get("head_sha"), "url": run.get("html_url"),
                                "conclusion": "success"})
            break

    cutoff = str(receipt.get("last_success_at") or "")
    kept = sorted((f for f in failures.values() if str(f.get("at") or "") > cutoff),
                  key=lambda f: int(f["run_id"]), reverse=True)[:MAX_FAILURES]
    receipt["failures"] = kept
    receipt["latest"] = latest
    receipt["scanned_through"] = watermark
    receipt["in_flight"] = bool(pending)
    receipt["workflow_state"] = api.workflow_state(lane["workflow_file"])
    return receipt, notes


def build(root: Path = ROOT, repository: str | None = None, api=None) -> dict:
    config = lr.load_config(root)
    repository = repository or os.environ.get("GITHUB_REPOSITORY") or ""
    api = api or GhApi(repository)
    written, unchanged, unavailable, notes = [], [], [], {}
    for lane in lr.declared_lanes(config):
        workflow = lane.get("workflow_file")
        if not workflow:
            continue
        runs = api.workflow_runs(workflow)
        if runs is None:
            unavailable.append(lane["name"])
            continue
        receipt, lane_notes = refresh_lane(root, lane, api, runs)
        if lane_notes:
            notes[lane["name"]] = lane_notes
        path = lr.receipt_path(root, lane["name"])
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(receipt, indent=2, sort_keys=False) + "\n"
        try:
            previous = path.read_text(encoding="utf-8")
        except OSError:
            previous = None
        if previous != text:
            path.write_text(text, encoding="utf-8")
            written.append(lane["name"])
        else:
            unchanged.append(lane["name"])
    return {"written": written, "unchanged": unchanged, "unavailable": unavailable,
            "notes": notes, "api_errors": list(getattr(api, "errors", []))[:20]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository")
    args = parser.parse_args()
    result = build(args.root, args.repository)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
