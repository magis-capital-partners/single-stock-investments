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
the last success, which the supervisor fingerprints.

How runs are scanned (the part that has to fit GITHUB_TOKEN's 1,000 REST
calls an hour, shared with every other workflow in the repository):

* Each lane looks back ``2 x freshness_hours`` (so a weekly job inside the
  busy Data Pipeline is still found on the first build), newest first,
  stopping at its first work-done success: nothing older can change it.
* ``scanned_through`` is the high watermark: runs above it are new next time.
  While a lane has no success on record its history is walked downwards and
  ``scan_low`` / ``history_complete`` remember how far, so a scan cut short by
  the call budget resumes where it stopped instead of rescanning the top.
  A lane whose history is incomplete is "not yet judged", never "stale".
* A cancelled job whose annotations cannot be read is left unresolved and
  rescanned, never filed as a harmless cancel (it may have been a timeout).

This script never exits non-zero because a lane has no success: that is a
finding for the supervisor, not a reason to kill the supervisor before it can
report it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_registry as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUNS_PER_PAGE = 100
MAX_PAGES = 6
MAX_FAILURES = 10
# Jobs and annotation reads per build. The first build after the job-level
# receipts land walks each lane's lookback; past this budget the rest is
# resumed on the next build (two hours later) rather than skipped.
MAX_JOB_CALLS = 350


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

    def _budgeted(self, path: str):
        if path not in self._cache:
            if self.job_calls >= self.max_job_calls:
                if not any(e.startswith("job-call budget") for e in self.errors):
                    self.errors.append(f"job-call budget of {self.max_job_calls} reached;"
                                       " the rest is scanned next run")
                return None
            self.job_calls += 1
        return self._get(path)

    def workflow_runs(self, workflow_file: str, since: datetime):
        """Runs on main created since ``since``, newest first (paged)."""
        stamp = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self._get(f"repos/{self.repository}/actions/workflows/{workflow_file}"
                                f"/runs?branch=main&per_page={RUNS_PER_PAGE}"
                                f"&created={quote('>=' + stamp)}&page={page}")
            if not isinstance(payload, dict):
                return None if page == 1 else rows
            batch = payload.get("workflow_runs") or []
            rows.extend(run for run in batch if run.get("event") != "pull_request")
            if len(batch) < RUNS_PER_PAGE:
                break
        return rows

    def workflow_state(self, workflow_file: str):
        payload = self._get(f"repos/{self.repository}/actions/workflows/{workflow_file}")
        return payload.get("state") if isinstance(payload, dict) else None

    def run_jobs(self, run_id: int):
        payload = self._budgeted(f"repos/{self.repository}/actions/runs/{run_id}/jobs"
                                 "?per_page=100")
        return payload.get("jobs") if isinstance(payload, dict) else None

    def job_annotations(self, job_id: int):
        payload = self._budgeted(f"repos/{self.repository}/check-runs/{job_id}/annotations")
        return payload if isinstance(payload, list) else None


def _is_timeout(api):
    def check(job: dict):
        annotations = api.job_annotations(job.get("id"))
        if annotations is None:
            return None            # unknown: the caller leaves the run unresolved
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


def lookback_hours(lane: dict) -> float:
    return 2 * float(lane.get("freshness_hours") or 96)


def refresh_lane(root: Path, lane: dict, api, runs: list[dict],
                 now: datetime) -> tuple[dict, list[str]]:
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
        "scanned_through": 0, "scan_low": None, "history_complete": False,
        "scan_floor_at": None,
    }
    if base:
        for key in receipt:
            if key in base:
                receipt[key] = base[key]
        receipt["schema_version"] = lr.RECEIPT_SCHEMA
    floor = now - timedelta(hours=lookback_hours(lane))
    window = [r for r in runs
              if (lr.parse_iso(r.get("created_at")) or now) >= floor]
    receipt["scan_floor_at"] = floor.strftime("%Y-%m-%dT%H:%M:%SZ")

    high = int(receipt.get("scanned_through") or 0)
    low = receipt.get("scan_low")
    success_known = bool(receipt.get("last_success_at"))
    history_done = bool(receipt.get("history_complete")) or success_known
    pending = [int(r["id"]) for r in window if r.get("status") != "completed"]
    top = (min(pending) - 1) if pending else max((int(r["id"]) for r in window), default=high)
    top = max(top, high)

    is_timeout = _is_timeout(api)
    failures = {int(f["run_id"]): f for f in receipt.get("failures") or []
                if isinstance(f, dict) and f.get("run_id")}
    latest = receipt.get("latest") if isinstance(receipt.get("latest"), dict) else None

    def in_scope(run_id: int) -> bool:
        if run_id > high:
            return True                                    # new since the last build
        return not history_done and (low is None or run_id < int(low))

    candidates = sorted((r for r in window if r.get("status") == "completed"
                         and in_scope(int(r["id"]))),
                        key=lambda r: int(r["id"]), reverse=True)
    cut_at = None          # first run that could not be classified (budget / API)
    lowest = None          # lowest run classified in this build
    found_success = False
    for run in candidates:
        run_id = int(run["id"])
        if lane.get("job"):
            jobs = api.run_jobs(run_id)
            result = lr.classify_lane_run(jobs, lane, is_timeout) if jobs is not None else \
                {"outcome": lr.UNRESOLVED}
        else:
            result = _legacy_outcome(run)
        if result is not None and result["outcome"] == lr.UNRESOLVED:
            cut_at = run_id
            break
        lowest = run_id
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
            found_success = True
            if str(at or "") > str(receipt.get("last_success_at") or ""):
                receipt.update({"last_success_at": at, "run_id": run_id,
                                "head_sha": run.get("head_sha"), "url": run.get("html_url"),
                                "conclusion": "success"})
            break

    if cut_at is None:
        receipt["scanned_through"] = top
        if found_success or success_known:
            receipt["history_complete"] = True
        elif not history_done:
            # Walked the whole lookback without a success: the lane is judged.
            receipt["history_complete"] = True
            receipt["scan_low"] = lowest if lowest is not None else low
    elif success_known and cut_at > high:
        # Steady state: new runs were cut short -- rescan them next time.
        receipt["scanned_through"] = max(high, cut_at - 1)
        notes.append(f"scan cut at run {cut_at}; resumes next build")
    else:
        # History mode: keep the top, resume the walk just below the cut.
        receipt["scanned_through"] = top
        receipt["scan_low"] = cut_at + 1
        receipt["history_complete"] = False
        notes.append(f"history scan cut at run {cut_at}; resumes next build")

    cutoff = str(receipt.get("last_success_at") or "")
    kept = sorted((f for f in failures.values() if str(f.get("at") or "") > cutoff),
                  key=lambda f: int(f["run_id"]), reverse=True)[:MAX_FAILURES]
    receipt["failures"] = kept
    receipt["latest"] = latest
    receipt["in_flight"] = bool(pending)
    receipt["workflow_state"] = api.workflow_state(lane["workflow_file"])
    return receipt, notes


def build(root: Path = ROOT, repository: str | None = None, api=None,
          now: datetime | None = None) -> dict:
    config = lr.load_config(root)
    repository = repository or os.environ.get("GITHUB_REPOSITORY") or ""
    api = api or GhApi(repository)
    now = now or datetime.now(timezone.utc)
    lanes = [lane for lane in lr.declared_lanes(config) if lane.get("workflow_file")]
    by_workflow: dict[str, list[dict]] = {}
    for lane in lanes:
        by_workflow.setdefault(lane["workflow_file"], []).append(lane)
    listings = {}
    for workflow, members in by_workflow.items():
        since = now - timedelta(hours=max(lookback_hours(l) for l in members))
        listings[workflow] = api.workflow_runs(workflow, since)
    # Cheapest workflows first, so a budget cut lands on the busiest history
    # (the Data Pipeline) and every other lane is judged on the first build.
    order = sorted(by_workflow, key=lambda wf: len(listings[wf] or []))
    written, unchanged, unavailable, notes = [], [], [], {}
    for workflow in order:
        runs = listings[workflow]
        for lane in by_workflow[workflow]:
            if runs is None:
                unavailable.append(lane["name"])
                continue
            receipt, lane_notes = refresh_lane(root, lane, api, runs, now)
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
