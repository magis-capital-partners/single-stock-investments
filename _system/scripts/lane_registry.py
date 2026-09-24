#!/usr/bin/env python3
"""Lane registry: the contract between graph_sources.json lanes and workflows.

A *lane* is one unit of scheduled work whose health the repository-health
supervisor judges. Since 2026-09-24 a lane is anchored to a workflow JOB, not
to a whole workflow run and not to commit subjects:

  * ``workflow_file`` -- the workflow under ``.github/workflows/``.
  * ``job``           -- the job's display name as the Actions API reports it
    (the job ``name:`` if set, else its id). ``fnmatch`` patterns cover matrix
    jobs (``analyze-*``); ``caller / callee`` covers a reusable-workflow job.
  * ``work_step``     -- optional step that must have concluded ``success``.
    Only needed where the job can succeed while its real work was skipped by
    an ``if:`` (for example Drive intake with no credentials).
  * ``freshness_hours`` -- the longest legitimate gap between two scheduled
    runs, plus one skipped cycle, plus start-time jitter (see
    ``JITTER_HOURS``).

Why job level: the old receipts recorded the newest *successful workflow run*,
so a run whose real job was skipped (a gate that decided there was nothing to
do) or a different cron of the same workflow kept a dead lane green -- the
ls-algo intake failed every scheduled run from 2026-08-12 while its receipt
stayed fresh, and the Data Pipeline's activist and news jobs timed out for
weeks behind the pipeline's other eight jobs.

This module is dependency-free on purpose (no PyYAML): graph_invariants runs
it in CI on a bare ``setup-python`` interpreter. The workflow parser below is
indentation-based and only understands what these checks need -- trigger
names, cron lines, job ids/names/``uses:`` and step names -- which is enough
because every workflow in this repository uses two-space indentation (the
governance tests already depend on that).
"""
from __future__ import annotations

import fnmatch
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_REL = Path("_system/graph/graph_sources.json")
RECEIPTS_REL = Path("_system/data/lane_receipts")
WORKFLOWS_REL = Path(".github/workflows")

# Scheduled runs here start 1.5-6.6h after their cron time since 2026-08-27
# (committee-outcomes and memory-digest started within 0.6h before that), and a
# job's receipt is stamped at its completion, so two consecutive runs of a daily
# lane can legitimately land up to ~6h further apart than the cron says. Every
# freshness window carries this allowance on top of "longest gap + one skipped
# cycle"; test_lane_registry pins that each declared window covers it.
JITTER_HOURS = 6

RECEIPT_SCHEMA = "2.0"

# Job outcomes a receipt can record. "timeout" is a failure: GitHub reports a
# job killed by timeout-minutes as conclusion "cancelled", which is exactly how
# the activist and news jobs hid for a month.
SUCCESS = "success"
FAILURE = "failure"
TIMEOUT = "timeout"
CANCELLED = "cancelled"   # superseded / evicted / manually cancelled: neutral
SKIPPED = "skipped"       # the lane's job did not run in this run
NOOP = "noop"             # job succeeded but its declared work step did not run
FAILING_OUTCOMES = frozenset({FAILURE, TIMEOUT})

TIMEOUT_MARKER = "exceeded the maximum execution time"


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

def load_config(root: Path = ROOT) -> dict:
    return json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))


def declared_lanes(config: dict) -> list[dict]:
    return [lane for lane in (config.get("lanes") or []) if isinstance(lane, dict)]


def receipt_path(root: Path, lane_name: str) -> Path:
    return root / RECEIPTS_REL / f"{lane_name}.json"


def load_receipt(root: Path, lane_name: str) -> dict | None:
    try:
        payload = json.loads(receipt_path(root, lane_name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def receipt_is_current(receipt: dict | None, lane: dict) -> bool:
    """True when the receipt was written under this lane's job-level contract.

    A schema-1 receipt recorded any successful run of the whole workflow, so
    for a lane that declares a job it proves nothing: the ls-algo receipt read
    2026-09-24 from a run whose intake job was skipped."""
    if not isinstance(receipt, dict):
        return False
    if not lane.get("job"):
        return True
    return (str(receipt.get("schema_version")) == RECEIPT_SCHEMA
            and receipt.get("job") == lane.get("job")
            and (receipt.get("work_step") or None) == (lane.get("work_step") or None)
            and receipt.get("workflow_file") == lane.get("workflow_file"))


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


# --------------------------------------------------------------------------- #
# workflow parser (indentation based; see module docstring)
# --------------------------------------------------------------------------- #

_TOP_KEY = re.compile(r"^([A-Za-z_\"'][^:#]*):(.*)$")
_TRIGGER = re.compile(r"^  ([A-Za-z_]+):")
_CRON = re.compile(r"""^\s+-\s+cron:\s*["']?([^"'#]+?)["']?\s*(?:#.*)?$""")
_JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")
_JOB_KEY = re.compile(r"^    ([A-Za-z_-]+):\s*(.*)$")
_STEP_START = re.compile(r"^      - (.*)$")
_STEP_KEY = re.compile(r"^        ([A-Za-z_-]+):\s*(.*)$")
_EXPR = re.compile(r"\$\{\{.*?\}\}")


def _scalar(raw: str) -> str:
    text = raw.strip()
    if text[:1] in ("'", '"'):
        quote = text[0]
        end = text.find(quote, 1)
        return text[1:end] if end > 0 else text[1:]
    return re.sub(r"\s+#.*$", "", text).strip()


def parse_workflow(text: str) -> dict:
    """Return {"name", "triggers", "crons", "jobs": {id: {name, uses, steps}}}."""
    lines = text.splitlines()
    result = {"name": None, "triggers": set(), "crons": [], "jobs": {}}
    section = None
    job = None
    step = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" "):
            match = _TOP_KEY.match(raw)
            key = match.group(1).strip("\"'") if match else ""
            value = match.group(2).strip() if match else ""
            section = None
            if key == "name":
                result["name"] = _scalar(value)
            elif key in ("on", "true"):
                section = "on"
                inline = _scalar(value)
                if inline:
                    for item in re.split(r"[\[\],\s]+", inline):
                        if item:
                            result["triggers"].add(item)
            elif key == "jobs":
                section = "jobs"
            continue
        if section == "on":
            trig = _TRIGGER.match(raw)
            if trig:
                result["triggers"].add(trig.group(1))
            cron = _CRON.match(raw)
            if cron:
                result["crons"].append(cron.group(1).strip())
            continue
        if section != "jobs":
            continue
        head = _JOB.match(raw)
        if head:
            job = {"name": None, "uses": None, "steps": []}
            result["jobs"][head.group(1)] = job
            step = None
            continue
        if job is None:
            continue
        key = _JOB_KEY.match(raw)
        if key:
            step = None
            if key.group(1) == "name":
                job["name"] = _scalar(key.group(2))
            elif key.group(1) == "uses":
                job["uses"] = _scalar(key.group(2))
            continue
        start = _STEP_START.match(raw)
        if start:
            step = {"name": None}
            job["steps"].append(step)
            inner = start.group(1)
            inner_key = re.match(r"([A-Za-z_-]+):\s*(.*)$", inner)
            if inner_key and inner_key.group(1) == "name":
                step["name"] = _scalar(inner_key.group(2))
            continue
        if step is not None:
            skey = _STEP_KEY.match(raw)
            if skey and skey.group(1) == "name" and step["name"] is None:
                step["name"] = _scalar(skey.group(2))
    return result


def load_workflow(root: Path, workflow_file: str) -> dict | None:
    path = root / WORKFLOWS_REL / workflow_file
    try:
        return parse_workflow(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def job_display_pattern(job_id: str, job: dict) -> str:
    """What the Actions API will call this job, with ${{ }} expressions as '*'."""
    name = job.get("name") or job_id
    return _EXPR.sub("*", name)


def _names_match(display: str, wanted: str) -> bool:
    # Either side may carry wildcards: a matrix job's display name is a
    # template ("analyze-*"), and a lane may name a pattern itself.
    return (display == wanted or fnmatch.fnmatchcase(display, wanted)
            or fnmatch.fnmatchcase(wanted, display))


def resolve_lane_job(root: Path, workflow: dict, lane_job: str) -> tuple[dict | None, str]:
    """Find the job (or reusable-workflow callee job) a lane's ``job`` names.

    Matching is on the DISPLAY name only -- the job ``name:`` when set, else
    its id -- because that is what the Actions API reports and so what a
    receipt can match. A lane naming the id of a job that has a custom name
    would never advance, so it is reported as a broken contract.

    Returns (job_spec, error). job_spec carries the step list to check a
    work_step against."""
    if " / " in lane_job:
        caller, callee = lane_job.split(" / ", 1)
        for job_id, job in workflow["jobs"].items():
            if not _names_match(job_display_pattern(job_id, job), caller):
                continue
            uses = job.get("uses") or ""
            if not uses.startswith("./.github/workflows/"):
                return None, f"job '{caller}' is not a local reusable-workflow call"
            called = load_workflow(root, uses.rsplit("/", 1)[1])
            if called is None:
                return None, f"reusable workflow {uses} is missing"
            for cid, cjob in called["jobs"].items():
                if _names_match(job_display_pattern(cid, cjob), callee):
                    return cjob, ""
            return None, f"reusable workflow {uses} has no job '{callee}'"
        return None, f"no job '{caller}'"
    for job_id, job in workflow["jobs"].items():
        if _names_match(job_display_pattern(job_id, job), lane_job):
            return job, ""
    return None, f"no job named '{lane_job}' (match the Actions display name)"


def lane_contract(root: Path, config: dict) -> tuple[list[str], list[str]]:
    """Structural lane contract. Returns (violations, warnings).

    Violations are things a change under review can cause and must fix: a lane
    pointing at a workflow, job or step that does not exist (its receipt could
    never advance again), a duplicate lane, a missing freshness window, or a
    scheduled workflow that no lane watches (an undeclared lane is invisible to
    the supervisor -- nine of fifteen scheduled workflows were, and that set
    held every silent failure)."""
    violations: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    watched: set[str] = set()
    for lane in declared_lanes(config):
        name = str(lane.get("name") or "")
        if not name:
            violations.append("a lane has no name")
            continue
        if name in seen:
            violations.append(f"{name}: declared twice")
        seen.add(name)
        try:
            hours = float(lane.get("freshness_hours"))
        except (TypeError, ValueError):
            hours = 0.0
        if hours <= 0:
            violations.append(f"{name}: freshness_hours must be a positive number")
        workflow_file = lane.get("workflow_file")
        if not workflow_file:
            if lane.get("job") or lane.get("work_step"):
                violations.append(f"{name}: declares a job but no workflow_file")
            continue   # legacy commit-subject lane (fixtures); nothing to wire
        workflow = load_workflow(root, workflow_file)
        if workflow is None:
            violations.append(f"{name}: workflow {workflow_file} does not exist")
            continue
        watched.add(workflow_file)
        lane_job = lane.get("job")
        if not lane_job:
            violations.append(f"{name}: declares no job -- a whole-run receipt lets"
                              " a skipped or no-op run keep the lane green")
            continue
        job, error = resolve_lane_job(root, workflow, lane_job)
        if job is None:
            violations.append(f"{name}: {workflow_file}: {error}")
            continue
        step = lane.get("work_step")
        if step and step not in [s.get("name") for s in job["steps"]]:
            violations.append(f"{name}: {workflow_file} job '{lane_job}' has no step"
                              f" named '{step}'")
    exempt = config.get("unmonitored_workflows") or {}
    workflows_dir = root / WORKFLOWS_REL
    for path in sorted(workflows_dir.glob("*.yml")):
        spec = parse_workflow(path.read_text(encoding="utf-8"))
        if "schedule" not in spec["triggers"] or not spec["crons"]:
            continue
        if path.name in watched:
            continue
        if path.name in exempt:
            continue
        violations.append(f"{path.name}: scheduled workflow is not declared as a lane"
                          " (or listed in unmonitored_workflows with a reason)")
    for name, reason in sorted(exempt.items()):
        if not str(reason or "").strip():
            violations.append(f"unmonitored_workflows.{name}: an exemption needs a reason")
        elif not (workflows_dir / name).exists():
            warnings.append(f"unmonitored_workflows.{name}: workflow no longer exists;"
                            " drop the exemption")
    return violations, warnings


# --------------------------------------------------------------------------- #
# cron spans (for the freshness-window lint and documentation)
# --------------------------------------------------------------------------- #

def _field_values(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
            if step != 1:
                end = high
        values.update(range(start, end + 1, step))
    return values


def cron_fire_times(expr: str, start: datetime, end: datetime) -> list[datetime]:
    minute, hour, dom, month, dow = expr.split()
    minutes = sorted(_field_values(minute, 0, 59))
    hours = sorted(_field_values(hour, 0, 23))
    doms = _field_values(dom, 1, 31)
    months = _field_values(month, 1, 12)
    dows = {d % 7 for d in _field_values(dow, 0, 7)}
    dom_any, dow_any = dom == "*", dow == "*"
    times = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        cron_dow = (day.isoweekday()) % 7          # cron: 0 = Sunday
        dom_ok = day.day in doms
        dow_ok = cron_dow in dows
        if dom_any and dow_any:
            day_ok = True
        elif dom_any:
            day_ok = dow_ok
        elif dow_any:
            day_ok = dom_ok
        else:
            day_ok = dom_ok or dow_ok             # POSIX cron OR semantics
        if day_ok and day.month in months:
            for h in hours:
                for m in minutes:
                    stamp = day.replace(hour=h, minute=m)
                    if start <= stamp <= end:
                        times.append(stamp)
        day += timedelta(days=1)
    return times


def one_skip_span_hours(crons: list[str]) -> float:
    """Longest time between two scheduled runs when exactly one run in between
    is skipped: max(t[i+2] - t[i]) over five weeks of the union of the crons."""
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)   # a Monday
    end = start + timedelta(days=35)
    times = sorted({t for expr in crons for t in cron_fire_times(expr, start, end)})
    if len(times) < 3:
        return float("inf")
    return max((times[i + 2] - times[i]).total_seconds() / 3600
               for i in range(len(times) - 2))


# --------------------------------------------------------------------------- #
# job-level outcome of one run for one lane
# --------------------------------------------------------------------------- #

def lane_jobs(jobs: list[dict], lane_job: str) -> list[dict]:
    return [job for job in jobs
            if fnmatch.fnmatchcase(str(job.get("name") or ""), lane_job)]


def classify_lane_run(jobs: list[dict], lane: dict, is_timeout) -> dict | None:
    """Classify one completed run for one lane.

    ``jobs`` is the Actions API ``jobs`` array; ``is_timeout(job)`` decides
    whether a cancelled job was killed by its timeout (it reads annotations).
    Returns None when the lane's job is absent from the run (a different cron
    of the same workflow), else {"outcome", "at", "job_id", "failed_step"}."""
    matched = lane_jobs(jobs, lane["job"])
    if not matched:
        return None
    at = max((str(j.get("completed_at") or j.get("started_at") or "") for j in matched),
             default="") or None

    def first_step(job, conclusions):
        for step in job.get("steps") or []:
            if step.get("conclusion") in conclusions:
                return step.get("name")
        return None

    for job in matched:
        if job.get("conclusion") in ("failure", "timed_out"):
            outcome = TIMEOUT if job.get("conclusion") == "timed_out" else FAILURE
            return {"outcome": outcome, "at": at, "job_id": job.get("id"),
                    "failed_step": first_step(job, ("failure", "timed_out", "cancelled"))}
    for job in matched:
        if job.get("conclusion") == "cancelled":
            if is_timeout(job):
                return {"outcome": TIMEOUT, "at": at, "job_id": job.get("id"),
                        "failed_step": first_step(job, ("cancelled", "failure"))}
    if any(j.get("conclusion") == "cancelled" for j in matched):
        return {"outcome": CANCELLED, "at": at, "job_id": matched[0].get("id"),
                "failed_step": None}
    ran = [j for j in matched if j.get("conclusion") == "success"]
    if not ran:
        return {"outcome": SKIPPED, "at": at, "job_id": matched[0].get("id"),
                "failed_step": None}
    step_name = lane.get("work_step")
    if step_name:
        did_work = any(step.get("name") == step_name and step.get("conclusion") == "success"
                       for job in ran for step in (job.get("steps") or []))
        if not did_work:
            return {"outcome": NOOP, "at": at, "job_id": ran[0].get("id"),
                    "failed_step": None}
    success_at = max(str(j.get("completed_at") or "") for j in ran) or at
    return {"outcome": SUCCESS, "at": success_at, "job_id": ran[0].get("id"),
            "failed_step": None}
