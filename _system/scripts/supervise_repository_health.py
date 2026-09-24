#!/usr/bin/env python3
"""Repository-health supervisor: judge lanes, heal what a retry can heal,
open one issue per persistent failure, and tell a human on Slack.

Run by ``.github/workflows/repository-health-supervisor.yml`` after
``build_lane_receipts.py`` has refreshed the job-level receipts.

What changed on 2026-09-24 (healer v2), and why:

* The v1 healer re-dispatched a lane every four hours for as long as it was
  stale. Of 186 healer-triggered runs between 2026-08-17 and 2026-09-24, 8
  succeeded, each only after a human fix commit; heal-warrants went 0 for 51
  and the falsifier lane re-ran the same deterministic error 84 times. Now
  every failure is fingerprinted (workflow + job + step + normalised first
  error line). A fingerprint seen once is treated as transient and retried
  with backoff, at most three dispatches per lane per UTC day. The same
  fingerprint twice stops dispatching and opens ONE GitHub issue for it.
* v1 escalated by appending to issue #847 on every run (123 bot comments,
  never read, never closed). Issues are now per fingerprint, labelled
  ``lane-failure``, assigned to a human, commented only on state changes and
  closed automatically when the lane recovers. #847 is no longer written.
* Nothing paged anyone. Slack now gets a message when a failure issue opens,
  a lane goes stale, a lane recovers, D1 usage crosses 60% or 80% of the
  free daily limits, or the supervisor itself has been silent for more than
  eight hours -- plus one daily digest. Every alert is deduplicated through
  this script's committed state file, so a condition is announced once.

Without ``--act`` the script only plans: no GitHub writes, no dispatches, no
Slack, no Cloudflare call. Output is ASCII (Windows cp1252 console trap).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_invariants  # noqa: E402
import lane_registry as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATE_REL = Path("_system/data/repository_health_supervisor.json")
STATE_SCHEMA = "2.0"

SUPERVISOR_GAP_HOURS = 8
DISPATCH_CAP_PER_DAY = 3
BACKOFF_HOURS = (0, 2, 4)          # wait before the 1st / 2nd / 3rd dispatch of a UTC day
LOOKBACK_MIN_HOURS = 168           # a fingerprint recurring within this (or 2x the lane window) is persistent
QUIET_MIN_HOURS = 24               # an issue closes after this long without a recurrence
FINGERPRINT_RUNS = 3               # failed runs fingerprinted per lane per supervisor run
FINGERPRINT_CACHE_MAX = 200
FINGERPRINTS_MAX = 80
CLOSED_ISSUES_KEPT = 40
RECOVERY_ALERT_DAYS = 7
ISSUE_LABEL = "lane-failure"
ISSUE_ASSIGNEE = "GoldmanDrew"
DIGEST_HOUR_UTC = 13
D1_LIMITS = {"rows_read": 5_000_000, "rows_written": 100_000}   # Cloudflare free plan, per day
D1_THRESHOLDS = (60, 80)

# Bounded on-demand triggers a stale or transiently failing lane may be
# re-run with. Only events and dispatch inputs that exist today belong here:
# repository_dispatch and workflow_dispatch are different APIs, and a type no
# workflow listens to would burn the lane's daily budget doing nothing.
P3_LANE_HEALERS = {
    "letters": {"workflow": "letter-backfill.yml", "fields": {}},
    "market-risk": {"event_type": "heal-market-risk"},
    "memory-digest": {"event_type": "memory-triage-run"},
    "falsifier": {"event_type": "falsifier-resolution-run"},
    "research-watchdog": {"event_type": "research-watchdog-run"},
    "data-pipeline-technicals": {"event_type": "heal-technicals"},
    "data-pipeline-warrant-discover": {"event_type": "heal-warrants"},
    "podcasts": {"workflow": "podcast-refresh.yml",
                 "fields": {"backfill": "false", "whisper_batch": "0"}},
    "ls-algo": {"event_type": "sync-ls-algo-universe"},
    "valuation": {"event_type": "refresh-power-zones"},
    "deploy": {"workflow": "dashboard-pages.yml",
               "fields": {"reason": "repository-health supervisor: deploy lane stale"}},
    # WS1 adds this repository_dispatch type to two-phase-watch.yml; until that
    # lands, healer_wired() holds the dispatch instead of burning the budget.
    "two-phase-watch": {"event_type": "two-phase-watch-run"},
}

WORK_QUEUE_REL = Path("_system/data/epistemic_work_queue.json")

# P6 feeds heal through a lane, so they share its budget and its
# persistent-failure stop (heal-warrants ran 51 times against one error).
P6_FEED_LANES = {
    "criticality_summary": "data-pipeline-technicals",
    "technical_summary": "data-pipeline-technicals",
    "vol_metrics": "data-pipeline-technicals",
    "spx_surface": "data-pipeline-technicals",
    "warrant_monitor": "data-pipeline-warrant-discover",
    "market_risk_components_committed": "market-risk",
    "podcast_catalog": "podcasts",
    # Rebuilt by forced-flow-daily and by the technicals job; only the latter
    # has an on-demand trigger (heal-technicals).
    "capitulation_daily": "data-pipeline-technicals",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def ascii_safe(text) -> str:
    return str(text if text is not None else "").encode("ascii", "replace").decode("ascii")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_between(later: datetime, earlier: datetime | None) -> float | None:
    if earlier is None:
        return None
    return (later - earlier).total_seconds() / 3600.0


def _head(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                            text=True, capture_output=True, check=False)
    return result.stdout.strip() or None


def quiet_hours(window: float) -> float:
    """How long a failure must stay away before its issue closes: one cadence
    period (a window is two periods plus jitter), never under a day. A daily
    lane closes a day after its last failure; a weekly lane after a week."""
    return max(QUIET_MIN_HOURS, (float(window) - lr.JITTER_HOURS) / 2.0)


def _fmt_age(hours: float | None) -> str:
    if hours is None:
        return "never"
    if hours >= 48:
        return f"{hours / 24:.0f}d"
    return f"{hours:.0f}h"


# --------------------------------------------------------------------------- #
# failure fingerprints
# --------------------------------------------------------------------------- #

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\^\[\[[0-9;]*m")
_TS_PREFIX = re.compile(r"^\ufeff?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s?")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
                  r"(?:Z|[+-]\d{2}:?\d{2})?)?")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,}\b", re.I)
_NUM = re.compile(r"\d+(?:\.\d+)?")
_GENERIC = (re.compile(r"^Process completed with exit code \d+\.?$"),
            re.compile(r"^The operation was canceled\.?$"),
            re.compile(r"^The job was canceled\b"))
_EXCEPTION = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?[A-Z]\w*(?:Error|Exception|Exit|Interrupt)\b(?::|$)")
_ERROR_WORD = re.compile(r"^(?:ERROR|FATAL|FAIL|FAILED|Error|error|fatal)\b[:\s]")
_NOISE_PREFIX = ("##[", "shell:", "env:", "[command]", "Post job", "Cleaning up",
                 "Node 20", "Node.js 20", "(node:", "(Use `node", "Warning:",
                 "Temporarily overriding HOME", "Adding repository directory",
                 "Copying '/home/runner", "http.https://github.com")


def clean_log_line(raw: str) -> str:
    text = _TS_PREFIX.sub("", raw.rstrip("\r\n"))
    return _ANSI.sub("", text)


def normalize_error(line: str) -> str:
    text = clean_log_line(line).strip()
    if text.startswith("##[error]"):
        text = text[len("##[error]"):]
    text = _ISO.sub("<ts>", text)
    text = _UUID.sub("<id>", text)
    text = _HEX.sub("<hex>", text)
    text = _NUM.sub("<n>", text)
    return re.sub(r"\s+", " ", text).strip()[:240]


def _generic(message: str) -> bool:
    return any(p.match(message.strip()) for p in _GENERIC)


def extract_error(annotations: list | None, log_text: str | None) -> tuple[str, str]:
    """Return (kind, first meaningful error line) for one failed job.

    kind is "timeout" when the job was killed by timeout-minutes. Otherwise
    the first specific ::error annotation wins; failing that, the log around
    the first ##[error] marker: the last exception or ERROR line before it,
    else the last line the job printed (usually the fatal message)."""
    rows = [a for a in (annotations or []) if isinstance(a, dict)]
    for row in rows:
        message = str(row.get("message") or "").strip().splitlines()[0:1]
        if message and lr.TIMEOUT_MARKER in message[0]:
            return "timeout", message[0]
    for row in rows:
        if str(row.get("annotation_level") or "failure") not in ("failure", "error"):
            continue
        lines = str(row.get("message") or "").strip().splitlines()
        if lines and not _generic(lines[0]):
            return "error", lines[0].strip()
    if not log_text:
        return "error", "no error line in annotations; log unavailable"
    lines, in_group = [], False
    for raw in log_text.splitlines():
        line = clean_log_line(raw)
        stripped = line.strip()
        if stripped.startswith("##[group]"):
            in_group = True
            continue
        if stripped.startswith("##[endgroup]"):
            in_group = False
            continue
        if in_group:
            continue
        lines.append(stripped)
    fail_at = next((i for i, s in enumerate(lines) if s.startswith("##[error]")), None)
    if fail_at is not None:
        specific = lines[fail_at][len("##[error]"):].strip()
        if specific and not _generic(specific):
            return "error", specific
        window = lines[max(0, fail_at - 60):fail_at]
    else:
        window = lines[-60:]
    for stripped in reversed(window):
        if _EXCEPTION.match(stripped) or _ERROR_WORD.match(stripped):
            return "error", stripped
    for stripped in reversed(window):
        if stripped and not stripped.startswith(_NOISE_PREFIX):
            return "error", stripped
    return "error", "no error line found in annotations or log"


def fingerprint(workflow: str, job: str, step: str | None, normalized: str) -> str:
    """Per-lane failure identity: decides retry versus stop."""
    key = "|".join([workflow or "", job or "", step or "", normalized or ""])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def issue_key(kind: str, normalized: str) -> str:
    """Issue identity: the normalised error alone, WITHOUT the lane, so the
    drive, intake-full and world-model jobs failing on the same
    check_warrant_universe.py error share one issue listing all three."""
    return hashlib.sha256(f"{kind}|{normalized}".encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# clients (network); every one is optional and injectable
# --------------------------------------------------------------------------- #

class GhCli:
    """GitHub REST through the gh CLI (GH_TOKEN in the workflow)."""

    def __init__(self, repository: str):
        self.repository = repository
        self.errors: list[str] = []

    def _call(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        cmd = ["gh", "api", "--method", method, path]
        if body is not None:
            cmd += ["--input", "-"]
        try:
            proc = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.errors.append(f"{method} {path}: {exc}")
            return None
        if proc.returncode != 0:
            self.errors.append(f"{method} {path}: {proc.stderr.strip()[:200]}")
            return None
        if raw:
            return proc.stdout
        try:
            return json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            return {}

    def _repo(self, tail: str) -> str:
        return f"repos/{self.repository}/{tail}"

    def job_annotations(self, job_id):
        payload = self._call("GET", self._repo(f"check-runs/{job_id}/annotations"))
        return payload if isinstance(payload, list) else None

    def job_log(self, job_id):
        return self._call("GET", self._repo(f"actions/jobs/{job_id}/logs"), raw=True)

    def open_issues(self, label: str):
        payload = self._call("GET", self._repo(f"issues?labels={label}&state=open&per_page=100"))
        if not isinstance(payload, list):
            return None
        return [row for row in payload if "pull_request" not in row]

    def ensure_label(self, name: str, color: str, description: str) -> bool:
        if isinstance(self._call("GET", self._repo(f"labels/{name}")), dict):
            return True
        return self._call("POST", self._repo("labels"), {
            "name": name, "color": color, "description": description}) is not None

    def create_issue(self, title: str, body: str, labels: list[str]):
        payload = self._call("POST", self._repo("issues"),
                             {"title": title, "body": body, "labels": labels})
        return payload.get("number") if isinstance(payload, dict) else None

    def assign(self, number: int, assignees: list[str]) -> bool:
        return self._call("POST", self._repo(f"issues/{number}/assignees"),
                          {"assignees": assignees}) is not None

    def update_issue(self, number: int, **fields) -> bool:
        return self._call("PATCH", self._repo(f"issues/{number}"), fields) is not None

    def comment(self, number: int, body: str) -> bool:
        return self._call("POST", self._repo(f"issues/{number}/comments"),
                          {"body": body}) is not None

    def dispatch_event(self, event_type: str) -> bool:
        return self._call("POST", self._repo("dispatches"),
                          {"event_type": event_type}) is not None

    def dispatch_workflow(self, workflow: str, fields: dict) -> bool:
        return self._call("POST", self._repo(f"actions/workflows/{workflow}/dispatches"),
                          {"ref": "main", "inputs": fields}) is not None


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 20):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310
        return response.status, response.read().decode("utf-8", "replace")


class SlackClient:
    """Incoming webhook first; bot token + channel as the fallback path."""

    def __init__(self, webhook_url: str | None, bot_token: str | None = None,
                 channel_id: str | None = None):
        self.webhook_url = webhook_url or None
        self.bot_token = bot_token or None
        self.channel_id = channel_id or None
        self.errors: list[str] = []

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url or (self.bot_token and self.channel_id))

    def send(self, text: str) -> bool:
        if self.webhook_url:
            try:
                status, _ = _post_json(self.webhook_url, {"text": text})
                if 200 <= status < 300:
                    return True
                self.errors.append(f"webhook HTTP {status}")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.errors.append(f"webhook: {exc}")
        if self.bot_token and self.channel_id:
            try:
                status, body = _post_json(
                    "https://slack.com/api/chat.postMessage",
                    {"channel": self.channel_id, "text": text, "unfurl_links": False},
                    headers={"Authorization": f"Bearer {self.bot_token}"})
                if 200 <= status < 300 and json.loads(body or "{}").get("ok"):
                    return True
                self.errors.append(f"chat.postMessage HTTP {status}")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.errors.append(f"chat.postMessage: {exc}")
        return False


class D1Unavailable(Exception):
    pass


D1_QUERY = """query D1Usage($accountTag: string!, $start: Date!, $end: Date!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      d1AnalyticsAdaptiveGroups(limit: 10000, filter: {date_geq: $start, date_leq: $end}) {
        sum { rowsRead rowsWritten }
      }
    }
  }
}"""


def parse_d1_usage(payload: dict) -> dict:
    """Sum rowsRead/rowsWritten across every database in the account."""
    if not isinstance(payload, dict):
        raise D1Unavailable("unparseable GraphQL response")
    errors = payload.get("errors") or []
    if errors:
        raise D1Unavailable("; ".join(str(e.get("message") or e) for e in errors)[:200])
    accounts = (((payload.get("data") or {}).get("viewer") or {}).get("accounts")) or []
    if not accounts:
        raise D1Unavailable("account not visible to this token")
    rows = accounts[0].get("d1AnalyticsAdaptiveGroups") or []
    read = sum(int((row.get("sum") or {}).get("rowsRead") or 0) for row in rows)
    written = sum(int((row.get("sum") or {}).get("rowsWritten") or 0) for row in rows)
    return {"rows_read": read, "rows_written": written}


class CloudflareD1:
    def __init__(self, api_token: str, account_id: str):
        self.api_token = api_token
        self.account_id = account_id

    def fetch(self, day: str) -> dict:
        try:
            status, body = _post_json(
                "https://api.cloudflare.com/client/v4/graphql",
                {"query": D1_QUERY,
                 "variables": {"accountTag": self.account_id, "start": day, "end": day}},
                headers={"Authorization": f"Bearer {self.api_token}"})
        except urllib.error.HTTPError as exc:
            raise D1Unavailable(f"HTTP {exc.code} (token may lack Account Analytics read)") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise D1Unavailable(f"network: {exc}") from exc
        try:
            return parse_d1_usage(json.loads(body))
        except json.JSONDecodeError as exc:
            raise D1Unavailable("unparseable GraphQL response") from exc


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #

def evaluate_lanes(root: Path, config: dict, now: datetime) -> dict:
    lanes = {}
    for lane in lr.declared_lanes(config):
        name = str(lane.get("name"))
        receipt = lr.load_receipt(root, name)
        current = lr.receipt_is_current(receipt, lane)
        usable = receipt if current else None
        success_at = lr.parse_iso((usable or {}).get("last_success_at"))
        age = hours_between(now, success_at)
        window = float(lane.get("freshness_hours") or 96)
        latest = (usable or {}).get("latest") if isinstance((usable or {}).get("latest"), dict) \
            else None
        # A lane is judged once it has a job-level receipt that either records
        # a success or has walked its whole lookback (build_lane_receipts). A
        # scan cut short by the API budget is "not yet judged", never stale.
        if lane.get("job"):
            judged = usable is not None and (success_at is not None
                                             or usable.get("history_complete", True) is not False)
        else:
            judged = True      # legacy whole-run lane: a missing receipt is simply stale
        lanes[name] = {
            "lane": lane, "receipt": usable, "window": window,
            "last_success_at": iso(success_at) if success_at else None,
            "age_hours": age,
            "judged": judged,
            "stale": judged and (success_at is None or age > window),
            "receipt_problem": None if current else ("missing" if receipt is None
                                                     else "predates the job-level contract"),
            "latest_outcome": (latest or {}).get("outcome"),
            "latest": latest,
            "failures": list((usable or {}).get("failures") or []),
            "in_flight": bool((usable or {}).get("in_flight")),
            "workflow_state": (usable or {}).get("workflow_state"),
        }
    return lanes


def operational_failures(root: Path, now: datetime | None = None) -> list[str]:
    """P3|/P6| failure keys: stale lane receipts and stale registered feeds."""
    now = now or datetime.now(timezone.utc)
    config = lr.load_config(root)
    hard = []
    for name, row in evaluate_lanes(root, config, now).items():
        if row["stale"] or not row["judged"]:
            reason = ("successful workflow receipt is missing or invalid"
                      if row["last_success_at"] is None else
                      "successful workflow receipt is stale")
            hard.append(f"P3|{name}: {reason}")
    p6 = graph_invariants.inv_p6(None, root, now)
    hard.extend(f"P6|{item}" for item in p6.violations)
    return hard


def _feed_name(violation: str) -> str:
    return violation.split(":", 1)[0].strip()


def healer_wired(root: Path, lane: dict | None, healer: dict) -> tuple[bool, str]:
    """A healer only helps if the lane's workflow listens for it: a
    repository_dispatch type nobody declares starts nothing and still spends
    the lane's daily budget. With no workflow tree checked out (unit fixtures)
    the registry is trusted; the supervisor job checks out .github/workflows."""
    workflows = root / lr.WORKFLOWS_REL
    if lane is None or not workflows.is_dir():
        return True, ""
    name = str(lane.get("workflow_file") or "")
    try:
        text = (workflows / name).read_text(encoding="utf-8")
    except OSError:
        return False, f"{name} is missing"
    event = healer.get("event_type")
    if event:
        token = re.compile(r"(?m)(?:^\s*-\s*|[\[,]\s*)[\"']?" + re.escape(event)
                           + r"[\"']?\s*(?:[,\]]|$)")
        if "repository_dispatch" not in text or not token.search(text):
            return False, f"{name} does not listen for repository_dispatch {event}"
        return True, ""
    if healer.get("workflow") != name or not re.search(r"(?m)^  workflow_dispatch:", text):
        return False, f"{healer.get('workflow')} has no workflow_dispatch trigger"
    return True, ""


def held_back_work(root: Path) -> list[dict]:
    """Work items parked in needs_semantic_review. The falsifier promoter
    (WS1, 2026-09-24) parks a draft it cannot promote there with its
    promotion_blockers instead of failing the lane, so the lane stays green
    and the quarantined draft would otherwise sit unseen."""
    try:
        payload = json.loads((root / WORK_QUEUE_REL).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    held = []
    for item in items or []:
        if not isinstance(item, dict) or item.get("state") != "needs_semantic_review":
            continue
        blockers = item.get("promotion_blockers") or []
        if isinstance(blockers, str):
            blockers = [blockers]
        held.append({"work_id": str(item.get("work_id") or ""),
                     "ticker": item.get("ticker"), "task_type": item.get("task_type"),
                     "spec_id": item.get("spec_id"), "reason": item.get("reason"),
                     "promotion_blockers": [str(b) for b in blockers],
                     "draft": bool(blockers)})
    return held


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #

def _load_state(root: Path) -> dict:
    path = root / STATE_REL
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fresh_state(prior: dict) -> dict:
    v2 = str(prior.get("schema_version")) == STATE_SCHEMA
    carry = (lambda key, default: prior.get(key, default) if v2 else default)
    return {
        "alerts": dict(carry("alerts", {})),
        "fingerprints": dict(carry("fingerprints", {})),
        "issues": dict(carry("issues", {})),
        "fingerprint_cache": dict(carry("fingerprint_cache", {})),
        "dispatch_log": dict(carry("dispatch_log", {})),
        "digest": dict(carry("digest", {})),
        "d1": dict(carry("d1", {})),
        "runs": list(carry("runs", [])),
        "unjudged_since": dict(carry("unjudged_since", {})),
        "first_v2_run": not v2,
    }


# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #

class Supervisor:
    def __init__(self, root: Path, now: datetime, github=None, slack=None, d1=None,
                 act: bool = False):
        self.root = root
        self.now = now
        self.github = github
        self.slack = slack
        self.d1 = d1
        self.act = act
        self.config = lr.load_config(root)
        self.prior = _load_state(root)
        self.state = _fresh_state(self.prior)
        self.alerts: list[dict] = []         # {"key", "text", "set": bool, "value"}
        self.dispatches: list[dict] = []
        self.issue_actions: list[str] = []
        self.notes: list[str] = []
        self.held_for_review: list[dict] = []
        self.today = now.strftime("%Y-%m-%d")

    # -- alert bookkeeping -------------------------------------------------- #
    def alert(self, key: str | None, text: str, value=None, clear: bool = False,
              also: tuple = ()):
        """Queue one Slack line. ``key`` is the dedupe key recorded (or, with
        clear=True, removed) once the message is delivered; ``also`` lists
        further keys to record silently with it."""
        self.alerts.append({"key": key, "text": text, "value": value, "clear": clear,
                            "also": tuple(also)})

    # -- supervisor gap ----------------------------------------------------- #
    def check_gap(self):
        previous = lr.parse_iso(self.prior.get("checked_at"))
        gap = hours_between(self.now, previous)
        if gap is not None and gap > SUPERVISOR_GAP_HOURS:
            key = f"gap:{iso(previous)}"
            if key not in self.state["alerts"]:
                self.alert(key, f"[GAP] The supervisor did not run for {gap:.1f}h (previous run"
                                f" {iso(previous)}). Lane and feed checks were blind for that"
                                " long.")
        runs = [r for r in self.state["runs"]
                if (hours_between(self.now, lr.parse_iso(r)) or 0) <= 48]
        runs.append(iso(self.now))
        self.state["runs"] = runs[-40:]
        return gap

    def age_unjudged(self, lanes: dict) -> None:
        """A lane with no readable job-level receipt is not judged -- but only
        for one freshness window. After that it is stale, so a receipt builder
        that keeps failing cannot hide a lane indefinitely."""
        since = self.state["unjudged_since"]
        for name, row in lanes.items():
            if row["judged"]:
                since.pop(name, None)
                continue
            first = lr.parse_iso(since.get(name)) or self.now
            since.setdefault(name, iso(first))
            hours = hours_between(self.now, first) or 0.0
            if hours > row["window"]:
                row["stale"] = True
                row["receipt_problem"] = (f"no complete job-level receipt for {hours:.0f}h"
                                          f" ({row['receipt_problem'] or 'scan unfinished'})")
        for name in [n for n in since if n not in lanes]:
            since.pop(name, None)

    # -- fingerprints ------------------------------------------------------- #
    def fingerprint_failure(self, name: str, lane: dict, failure: dict) -> dict | None:
        job_id = failure.get("job_id")
        cache_key = str(job_id) if job_id else f"run:{failure.get('run_id')}"
        cached = self.state["fingerprint_cache"].get(cache_key)
        if cached:
            return cached
        if self.github is None or not job_id:
            return None
        annotations = self.github.job_annotations(job_id)
        kind, raw = extract_error(annotations, None)
        if kind != "timeout" and failure.get("outcome") == lr.TIMEOUT:
            kind, raw = "timeout", "The job has exceeded the maximum execution time"
        if kind != "timeout" and (raw.startswith("no error line") or annotations is None):
            log_text = self.github.job_log(job_id)
            if annotations is None and not log_text:
                return None     # nothing to read: never fingerprint an API outage
            kind, raw = extract_error(annotations, log_text)
        if raw.startswith("no error line"):
            return None         # unreadable failure: retry it, never file an issue about it
        step = failure.get("failed_step")
        normalized = normalize_error(raw) if kind != "timeout" else \
            f"timeout while running step '{step or 'unknown'}'"
        result = {"fp": fingerprint(lane.get("workflow_file"), lane.get("job"), step, normalized),
                  "kind": kind, "step": step, "normalized": normalized,
                  "raw": ascii_safe(raw)[:500]}
        cache = self.state["fingerprint_cache"]
        cache[cache_key] = result
        while len(cache) > FINGERPRINT_CACHE_MAX:
            cache.pop(next(iter(cache)))
        return result

    def lookback_hours(self, window: float) -> float:
        return max(LOOKBACK_MIN_HOURS, 2 * window)

    def record_failures(self, name: str, row: dict) -> dict | None:
        """Fingerprint the newest failures of a failing lane; return the latest
        failure's registry entry (or None when it cannot be fingerprinted)."""
        lane = row["lane"]
        latest_entry = None
        for index, failure in enumerate(row["failures"][:FINGERPRINT_RUNS]):
            result = self.fingerprint_failure(name, lane, failure)
            if result is None:
                continue
            fps = self.state["fingerprints"]
            entry = fps.setdefault(result["fp"], {
                "lane": name, "workflow": lane.get("workflow_file"), "job": lane.get("job"),
                "step": result["step"], "kind": result["kind"],
                "error": result["normalized"], "raw": result["raw"],
                "first_seen_at": failure.get("at"), "last_seen_at": failure.get("at"),
                "runs": []})
            entry["issue_key"] = issue_key(result["kind"], result["normalized"])
            seen = {int(r["run_id"]) for r in entry["runs"]}
            if int(failure["run_id"]) not in seen:
                entry["runs"].append({"run_id": int(failure["run_id"]), "at": failure.get("at"),
                                      "url": failure.get("url")})
                entry["runs"].sort(key=lambda r: str(r.get("at") or ""))
                entry["runs"] = entry["runs"][-10:]
            entry["first_seen_at"] = min(str(entry["first_seen_at"] or failure.get("at") or ""),
                                         str(failure.get("at") or "")) or entry["first_seen_at"]
            entry["last_seen_at"] = max(str(entry["last_seen_at"] or ""),
                                        str(failure.get("at") or ""))
            if index == 0:
                latest_entry = (result["fp"], entry)
        return latest_entry

    def occurrences(self, entry: dict, window: float) -> int:
        horizon = self.lookback_hours(window)
        return sum(1 for r in entry["runs"]
                   if (hours_between(self.now, lr.parse_iso(r.get("at"))) or 0) <= horizon)

    # -- issues --------------------------------------------------------------- #
    # One issue per normalised error (issue_key), listing every lane that hits
    # it. Every GitHub write is checked before state moves: a failed create,
    # reopen or close changes nothing and is retried on the next run. Slack
    # lines about issues are derived from that state afterwards and keyed, so
    # a failed send is retried without being duplicated.

    def _can_write(self) -> bool:
        return self.github is not None and self.act

    def issue_title(self, key: str, issue: dict) -> str:
        error = issue["raw"] if issue["kind"] != "timeout" else issue["error"]
        short = re.sub(r"\s+", " ", ascii_safe(error)).strip()
        if len(short) > 80:
            short = short[:77] + "..."
        lanes = sorted(issue["lanes"])
        who = lanes[0] if len(lanes) == 1 else f"{lanes[0]} +{len(lanes) - 1}"
        return f"[lane-failure] {who}: {short} [fp:{key}]"

    def issue_body(self, key: str, issue: dict) -> str:
        lines = [
            f"The repository-health supervisor saw the same failure at least twice on"
            f" {len(issue['lanes'])} lane(s) and has **stopped re-dispatching them**: a retry"
            " cannot fix this, it needs a code or data change.",
            "",
            f"- Kind: {issue['kind']}",
            f"- Issue key: `{key}` (the normalised error; one issue for every lane that hits it)",
            f"- First seen: {issue['first_seen_at']}",
            f"- Last seen: {issue['last_seen_at']}",
            "",
            "First error line:",
            "```text",
            issue["raw"],
            "```",
            "",
            "Affected lanes:",
        ]
        for name, member in sorted(issue["lanes"].items()):
            lines.append(f"- `{name}`: `{member['workflow']}` / job `{member['job']}` / step"
                         f" `{member.get('step') or 'unknown'}` (fingerprint `{member['fp']}`,"
                         f" closes {quiet_hours(member['window']):.0f}h after its last failure)")
            for run in member["runs"][-5:]:
                lines.append(f"  - {run.get('at')}: {run.get('url')}")
        lines += ["",
                  "This issue closes itself once every lane above has a work-done success and"
                  " has not hit this failure for one cadence period. State:"
                  " `_system/data/repository_health_supervisor.json`.",
                  f"<!-- lane-failure fp:{key} -->"]
        return "\n".join(lines)

    def find_open_issue(self, key: str, open_issues: list | None) -> int | None:
        for row in open_issues or []:
            if f"[fp:{key}]" in str(row.get("title") or ""):
                return int(row["number"])
        return None

    def sync_issue(self, key: str, members: list, open_issues) -> None:
        """Open, refresh or reopen the issue for one normalised error."""
        first = members[0][2]
        issue = self.state["issues"].setdefault(key, {
            "number": None, "state": None, "episode": 0, "kind": first["kind"],
            "error": first["error"], "raw": first["raw"], "lanes": {},
            "first_seen_at": None, "last_seen_at": None, "body_sig": None,
            "stale_noted": [], "superseded_noted": {}, "closing_commented": False})
        for name, fp, entry, window in members:
            issue["lanes"][name] = {"fp": fp, "workflow": entry["workflow"], "job": entry["job"],
                                    "step": entry.get("step"),
                                    "first_seen_at": entry["first_seen_at"],
                                    "last_seen_at": entry["last_seen_at"],
                                    "runs": entry["runs"][-5:], "window": window}
        seen = [m for m in issue["lanes"].values()]
        issue["first_seen_at"] = min(str(m["first_seen_at"] or "") for m in seen) or None
        issue["last_seen_at"] = max(str(m["last_seen_at"] or "") for m in seen) or None
        body = self.issue_body(key, issue)
        signature = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        if not self._can_write():
            self.issue_actions.append(f"would open or keep issue [fp:{key}] for"
                                      f" {', '.join(sorted(issue['lanes']))}")
            return
        number = issue["number"] or self.find_open_issue(key, open_issues)
        if number and issue["state"] != "closed":
            if issue["state"] is None:
                # Found on GitHub after the state file lost it: it was announced
                # when it was opened, so do not announce it again.
                issue.update(number=number, state="open", episode=max(1, issue["episode"]))
                self.state["alerts"].setdefault(f"issue:{key}:open:{issue['episode']}",
                                                {"sent_at": iso(self.now), "value": number})
            if signature != issue["body_sig"]:
                if self.github.update_issue(number, body=body):   # silent: edits notify nobody
                    issue["body_sig"] = signature
                else:
                    self.notes.append(f"could not refresh #{number}; retrying next run")
            return
        if number and issue["state"] == "closed":
            if not self.github.update_issue(number, state="open", body=body):
                self.notes.append(f"could not reopen #{number} [fp:{key}]; retrying next run")
                return
            issue.update(state="open", episode=issue["episode"] + 1, body_sig=signature,
                         closing_commented=False, stale_noted=sorted(issue["lanes"]),
                         reopened_at=iso(self.now))
            if not self.github.comment(number, f"Recurred at {issue['last_seen_at']} on"
                                               f" {', '.join(sorted(issue['lanes']))}; reopened"
                                               " by the repository-health supervisor."):
                self.notes.append(f"reopened #{number} but could not comment")
            self.issue_actions.append(f"reopened #{number} [fp:{key}]")
            return
        self.github.ensure_label(ISSUE_LABEL, "b60205",
                                 "A lane failed the same way twice; the supervisor stopped retrying")
        number = self.github.create_issue(self.issue_title(key, issue), body, [ISSUE_LABEL])
        if not number:
            self.notes.append(f"could not open an issue [fp:{key}]; retrying next run")
            return
        # The new issue already says the lanes are failing; the stale-transition
        # comment would only repeat it.
        issue.update(number=number, state="open", episode=1, body_sig=signature,
                     opened_at=iso(self.now), stale_noted=sorted(issue["lanes"]),
                     closing_commented=False)
        if not self.github.assign(number, [ISSUE_ASSIGNEE]):
            self.notes.append(f"opened #{number} but could not assign {ISSUE_ASSIGNEE}")
        self.issue_actions.append(f"opened #{number} [fp:{key}] for"
                                  f" {', '.join(sorted(issue['lanes']))}")

    def member_recovered(self, key: str, name: str, member: dict, lanes: dict) -> bool:
        row = lanes.get(name)
        if row is None:
            return True                  # lane no longer declared
        since = hours_between(self.now, lr.parse_iso(member.get("last_seen_at")))
        if since is None or since < quiet_hours(row["window"]):
            return False
        if row.get("issue_key") and row["issue_key"] != key:
            return True                  # still failing, but with a different error now
        return not row["stale"] and row["latest_outcome"] == lr.SUCCESS

    def close_recovered_issues(self, lanes: dict) -> None:
        for key, issue in self.state["issues"].items():
            if issue.get("state") != "open" or not issue.get("number"):
                continue
            if not all(self.member_recovered(key, name, member, lanes)
                       for name, member in issue["lanes"].items()):
                continue
            number = issue["number"]
            if not self._can_write():
                self.issue_actions.append(f"would close #{number} [fp:{key}]")
                continue
            if not issue.get("closing_commented"):
                successes = ", ".join(f"`{n}` {lanes[n]['last_success_at']}"
                                      for n in sorted(issue["lanes"]) if n in lanes)
                if self.github.comment(number, "Recovered: every affected lane has a work-done"
                                               f" success ({successes or 'lanes retired'}) and"
                                               " has not hit this failure for a full cadence"
                                               " period. Closing automatically."):
                    issue["closing_commented"] = True
            if not self.github.update_issue(number, state="closed", state_reason="completed"):
                self.notes.append(f"could not close #{number}; retrying next run")
                continue
            issue.update(state="closed", closed_at=iso(self.now))
            self.issue_actions.append(f"closed #{number} [fp:{key}]")

    def issue_alerts(self) -> None:
        """Slack lines for issue state, keyed per issue episode."""
        repo = getattr(self.github, "repository", "") or ""
        for key, issue in self.state["issues"].items():
            number, episode = issue.get("number"), int(issue.get("episode") or 0)
            if not number or not episode:
                continue
            lanes = ", ".join(f"`{n}`" for n in sorted(issue["lanes"]))
            link = f"https://github.com/{repo}/issues/{number}" if repo else f"#{number}"
            if issue.get("state") == "open":
                alert_key = f"issue:{key}:open:{episode}"
                if alert_key not in self.state["alerts"]:
                    tag = "[NEW FAILURE ISSUE]" if episode == 1 else "[FAILING AGAIN]"
                    self.alert(alert_key, f"{tag} #{number} {lanes} ({issue['kind']}):"
                                          f" {issue['raw'][:200]} -- {link}", value=number)
            elif issue.get("state") == "closed":
                closed = lr.parse_iso(issue.get("closed_at"))
                recent = closed is not None and \
                    (hours_between(self.now, closed) or 0) <= RECOVERY_ALERT_DAYS * 24
                alert_key = f"issue:{key}:closed:{episode}"
                if recent and alert_key not in self.state["alerts"]:
                    self.alert(alert_key, f"[RECOVERED] issue #{number} closed: {lanes} no longer"
                                          f" hit \"{issue['raw'][:120]}\"", value=number)

    # -- dispatch ------------------------------------------------------------- #
    def may_dispatch(self, name: str, row: dict | None) -> tuple[bool, str]:
        healer = P3_LANE_HEALERS.get(name)
        if not healer:
            return False, "no healer registered"
        wired, why = healer_wired(self.root, (row or {}).get("lane"), healer)
        if not wired:
            return False, why
        if row is not None:
            if row["in_flight"]:
                return False, "a run is already queued or in progress"
            if str(row.get("workflow_state") or "").startswith("disabled"):
                return False, f"workflow is {row['workflow_state']}"
        log = self.state["dispatch_log"].get(name) or {}
        count = int(log.get("count") or 0) if log.get("date") == self.today else 0
        if count >= DISPATCH_CAP_PER_DAY:
            return False, f"daily cap of {DISPATCH_CAP_PER_DAY} dispatches reached"
        last = lr.parse_iso(log.get("last_at"))
        waited = hours_between(self.now, last)
        if count and waited is not None and waited < BACKOFF_HOURS[count]:
            return False, f"backing off ({waited:.1f}h of {BACKOFF_HOURS[count]}h)"
        return True, ""

    def dispatch(self, name: str, reason: str) -> None:
        healer = dict(P3_LANE_HEALERS[name])
        log = self.state["dispatch_log"].get(name) or {}
        count = int(log.get("count") or 0) if log.get("date") == self.today else 0
        sent = False
        if self.act and self.github is not None:
            if healer.get("event_type"):
                sent = bool(self.github.dispatch_event(healer["event_type"]))
            else:
                sent = bool(self.github.dispatch_workflow(healer["workflow"],
                                                          healer.get("fields") or {}))
        if sent:
            self.state["dispatch_log"][name] = {"date": self.today, "count": count + 1,
                                                "last_at": iso(self.now)}
        self.dispatches.append({**healer, "lane": name, "reason": reason, "sent": sent})

    # -- run ---------------------------------------------------------------- #
    def run(self) -> dict:
        gap = self.check_gap()
        lanes = evaluate_lanes(self.root, self.config, self.now)
        self.age_unjudged(lanes)
        open_issues = self.github.open_issues(ISSUE_LABEL) \
            if (self.github is not None and self.act) else None
        blocked: set[str] = set()      # lanes whose latest failure is persistent
        persistent: dict[str, list] = {}
        for name, row in lanes.items():
            if row["latest_outcome"] not in lr.FAILING_OUTCOMES or not row["failures"]:
                continue
            latest = self.record_failures(name, row)
            if latest is None:
                continue
            fp, entry = latest
            row["fingerprint"] = fp
            row["issue_key"] = entry["issue_key"]
            if self.occurrences(entry, row["window"]) >= 2:
                blocked.add(name)
                row["persistent"] = True
                persistent.setdefault(entry["issue_key"], []).append(
                    (name, fp, entry, row["window"]))
        for key, members in persistent.items():
            self.sync_issue(key, members, open_issues)
        # A lane now failing with a different persistent error: say so once on
        # its older issue (a state change), which then closes on its own once
        # its error has stayed away for a cadence period.
        for key, members in persistent.items():
            new_number = (self.state["issues"].get(key) or {}).get("number")
            for name, *_ in members:
                for old_key, old in self.state["issues"].items():
                    if (old_key == key or old.get("state") != "open" or name not in old["lanes"]
                            or old.get("superseded_noted", {}).get(name) == key
                            or not self._can_write()):
                        continue
                    target = f"#{new_number}" if new_number else f"[fp:{key}]"
                    if self.github.comment(old["number"], f"`{name}` now fails with a different"
                                                          f" error; see {target}."):
                        old.setdefault("superseded_noted", {})[name] = key
        self.close_recovered_issues(lanes)
        self.issue_alerts()

        # stale / recovered transitions
        for name, row in lanes.items():
            key = f"stale:{name}"
            if row["stale"] and key not in self.state["alerts"]:
                latest = row["latest"] or {}
                floor = (row["receipt"] or {}).get("scan_floor_at")
                detail = (f"last work-done success {_fmt_age(row['age_hours'])} ago"
                          if row["last_success_at"] else
                          f"no work-done success since at least {floor}" if floor else
                          "no work-done success on record")
                why = []
                if latest.get("outcome"):
                    why.append(f"latest run: {latest['outcome']}"
                               + (f" in '{latest.get('failed_step')}'" if latest.get("failed_step")
                                  else ""))
                if row.get("workflow_state") and row["workflow_state"] != "active":
                    why.append(f"workflow {row['workflow_state']}")
                if row["receipt_problem"]:
                    why.append(f"receipt {row['receipt_problem']}")
                self.alert(key, f"[STALE] `{name}`: {detail} (window {row['window']:.0f}h)"
                                + (f"; {'; '.join(why)}" if why else "")
                                + (f" -- {latest.get('url')}" if latest.get("url") else ""),
                           value=row["last_success_at"] or "never")
                for issue in self.state["issues"].values():
                    if (issue.get("state") != "open" or name not in issue["lanes"]
                            or name in issue.get("stale_noted", []) or not self._can_write()):
                        continue
                    if self.github.comment(issue["number"], f"`{name}` is now stale: {detail}"
                                                            f" (window {row['window']:.0f}h)."):
                        issue.setdefault("stale_noted", []).append(name)
            # "Not stale" only means recovered when the lane is JUDGED fresh. A
            # lane whose receipt scan was cut this build is merely unknown, and
            # announcing it as recovered produced "[RECOVERED] `ls-algo`:
            # work-done success at None" followed by [STALE] again.
            recovered = row["judged"] and not row["stale"] and bool(row["last_success_at"])
            if recovered:
                for issue in self.state["issues"].values():
                    if name in issue.get("stale_noted", []):
                        issue["stale_noted"].remove(name)
            if recovered and key in self.state["alerts"]:
                self.alert(key, f"[RECOVERED] `{name}`: work-done success at"
                                f" {row['last_success_at']}", clear=True)

        # P6 feeds
        p6 = graph_invariants.inv_p6(None, self.root, self.now)
        violated = {}
        for violation in p6.violations:
            violated.setdefault(_feed_name(violation), violation)
        for feed, violation in violated.items():
            key = f"feed:{feed}"
            if key not in self.state["alerts"]:
                self.alert(key, f"[STALE FEED] {ascii_safe(violation)[:220]}", value=True)
        for key in [k for k in self.state["alerts"] if k.startswith("feed:")]:
            if key[len("feed:"):] not in violated:
                self.alert(key, f"[RECOVERED FEED] {key[len('feed:'):]} is fresh again",
                           clear=True)

        # dispatch: stale or transiently failing lanes, and P6 feed healers
        wanted: dict[str, str] = {}
        for name, row in lanes.items():
            failing = row["latest_outcome"] in lr.FAILING_OUTCOMES
            if row["stale"] or failing:
                wanted.setdefault(name, "stale" if row["stale"] else "transient failure")
        for feed in violated:
            lane = P6_FEED_LANES.get(feed)
            if lane:
                wanted.setdefault(lane, f"P6 feed {feed}")
        held = {}
        for name, reason in wanted.items():
            if name in blocked:
                held[name] = "persistent failure: dispatching stopped, see the lane-failure issue"
                continue
            ok, why = self.may_dispatch(name, lanes.get(name))
            if ok:
                self.dispatch(name, reason)
            elif name in P3_LANE_HEALERS:
                held[name] = why

        # Work parked for semantic review: a held-back draft keeps its lane
        # green, so it is announced once here and listed in every digest.
        review = held_back_work(self.root)
        self.held_for_review = review
        current = {f"held:{item['work_id']}" for item in review if item["draft"]}
        for item in review:
            key = f"held:{item['work_id']}"
            if item["draft"] and key not in self.state["alerts"]:
                blockers = "; ".join(item["promotion_blockers"])[:200]
                self.alert(key, f"[HELD DRAFT] {item['ticker']} {item.get('spec_id') or ''}"
                                f" parked in needs_semantic_review by the promoter: {blockers}",
                           value=item.get("ticker"))
        for key in [k for k in self.state["alerts"] if k.startswith("held:")]:
            if key not in current:
                self.state["alerts"].pop(key, None)      # released; nothing to announce

        d1_status = self.check_d1()
        digest = self.maybe_digest(lanes, violated, d1_status, gap)
        sent = self.deliver(digest)
        if self.act:
            # A plan-only run must not touch the committed state: it sent
            # nothing, so recording dedupe keys or dispatch counts would lie.
            self.write_state(lanes, violated, held, sent)
        return self.payload(lanes, violated, held, sent, d1_status)

    # -- D1 -------------------------------------------------------------------- #
    def check_d1(self) -> dict:
        if self.d1 is None:
            status = {"status": "not configured"} if self.act else {"status": "skipped (plan only)"}
            self.state["d1"] = {**status, "checked_at": iso(self.now)}
            return self.state["d1"]
        try:
            usage = self.d1.fetch(self.today)
        except D1Unavailable as exc:
            self.state["d1"] = {"status": f"unavailable: {ascii_safe(exc)}",
                                "checked_at": iso(self.now)}
            return self.state["d1"]
        record = {"status": "ok", "date": self.today, "checked_at": iso(self.now)}
        for metric, limit in D1_LIMITS.items():
            used = int(usage.get(metric) or 0)
            pct = 100.0 * used / limit
            record[metric] = used
            record[f"{metric}_pct"] = round(pct, 1)
            crossed = [t for t in D1_THRESHOLDS if pct >= t]
            if not crossed:
                continue
            top = max(crossed)
            key = f"d1:{self.today}:{metric}:{top}"
            if key in self.state["alerts"]:
                continue
            label = "rows read" if metric == "rows_read" else "rows written"
            # One line for the highest threshold crossed; lower ones are
            # recorded with it so a first check at 85% does not also say 60%.
            self.alert(key, f"[D1 {top}%] D1 {label} today: {used:,} of the free {limit:,}/day"
                            f" ({pct:.0f}%). At 100% D1 stops serving"
                            f" {'reads' if metric == 'rows_read' else 'writes'} until 00:00 UTC.",
                       value=round(pct, 1),
                       also=tuple(f"d1:{self.today}:{metric}:{t}" for t in crossed if t != top))
        self.state["d1"] = record
        return record

    # -- digest ------------------------------------------------------------- #
    def maybe_digest(self, lanes, violated, d1_status, gap) -> str | None:
        if self.now.hour < DIGEST_HOUR_UTC or self.state["digest"].get("last_sent_date") == self.today:
            return None
        stale = [(n, r) for n, r in lanes.items() if r["stale"]]
        unjudged = [n for n, r in lanes.items() if not r["judged"] and not r["stale"]]
        lines = [f"*Repository health digest {self.today}*",
                 f"Lanes: {len(lanes)} declared, {len(lanes) - len(stale) - len(unjudged)} fresh,"
                 f" {len(stale)} stale, {len(unjudged)} not yet judged"
                 + (f" ({', '.join(sorted(unjudged))})" if unjudged else "") + "."]
        for name, row in sorted(stale, key=lambda item: -(item[1]["age_hours"] or 1e9)):
            latest = row["latest_outcome"] or "no run on record"
            lines.append(f"  - `{name}`: {_fmt_age(row['age_hours'])} since a work-done success"
                         f" (window {row['window']:.0f}h), latest {latest}")
        open_issues = [issue for issue in self.state["issues"].values()
                       if issue.get("state") == "open"]
        lines.append(f"Open lane-failure issues: {len(open_issues)}")
        for issue in open_issues[:10]:
            lanes_text = ", ".join(f"`{n}`" for n in sorted(issue["lanes"]))
            lines.append(f"  - #{issue.get('number')} {lanes_text}: {issue['raw'][:100]}")
        todays = {n: int(l.get("count") or 0) for n, l in self.state["dispatch_log"].items()
                  if l.get("date") == self.today and int(l.get("count") or 0)}
        lines.append("Healer dispatches today: " + (", ".join(f"{n} x{c}" for n, c in
                                                             sorted(todays.items())) or "none"))
        review = getattr(self, "held_for_review", [])
        drafts = [item for item in review if item["draft"]]
        lines.append(f"Held for semantic review: {len(review)} work item(s),"
                     f" {len(drafts)} draft(s) the promoter could not promote")
        for item in (drafts + [i for i in review if not i["draft"]])[:8]:
            why = "; ".join(item["promotion_blockers"]) or item.get("reason") or "no reason recorded"
            lines.append(f"  - {item['ticker']} {item.get('task_type') or ''}: {why[:100]}")
        lines.append(f"Registered feeds (P6): {len(violated)} stale"
                     + (": " + ", ".join(sorted(violated)) if violated else ""))
        if d1_status.get("status") == "ok":
            lines.append(f"D1 today: rows read {d1_status.get('rows_read_pct')}% of 5M, rows"
                         f" written {d1_status.get('rows_written_pct')}% of 100k")
        else:
            lines.append(f"D1 today: {d1_status.get('status')}")
        recent = [r for r in self.state["runs"]
                  if (hours_between(self.now, lr.parse_iso(r)) or 0) <= 24]
        lines.append(f"Supervisor: {len(recent)} runs in the last 24h"
                     + (f"; gap before this run {gap:.1f}h" if gap is not None else ""))
        return "\n".join(lines)

    # -- delivery ------------------------------------------------------------- #
    def deliver(self, digest: str | None) -> dict:
        sent = {"alerts": False, "digest": False}
        if self.alerts:
            head = (f"*Repository health: {len(self.alerts)} change(s)*"
                    if not self.state["first_v2_run"] else
                    "*Repository health supervisor v2 is live. Current state:*")
            text = "\n".join([head] + [a["text"] for a in self.alerts])
            sent["alerts"] = self._send(text)
        if digest:
            sent["digest"] = self._send(digest)
        # Dedupe keys move only when the message actually went out, so a failed
        # send is retried on the next run instead of being silently dropped.
        if sent["alerts"]:
            for item in self.alerts:
                if not item["key"]:
                    continue
                if item["clear"]:
                    self.state["alerts"].pop(item["key"], None)
                    continue
                for key in (item["key"],) + item["also"]:
                    self.state["alerts"][key] = {"sent_at": iso(self.now),
                                                 "value": item["value"]}
        if sent["digest"]:
            self.state["digest"] = {"last_sent_date": self.today, "sent_at": iso(self.now)}
        # Old dedupe keys for past days would otherwise accumulate forever.
        horizon = (self.now - timedelta(days=3)).strftime("%Y-%m-%d")
        for key in [k for k in self.state["alerts"] if k.startswith("d1:")]:
            if key.split(":")[1] < horizon:
                self.state["alerts"].pop(key, None)
        for key in [k for k in self.state["alerts"] if k.startswith("gap:")]:
            stamp = lr.parse_iso(key[len("gap:"):])
            if stamp and (hours_between(self.now, stamp) or 0) > 24 * 7:
                self.state["alerts"].pop(key, None)
        return sent

    def _send(self, text: str) -> bool:
        if not self.act or self.slack is None or not getattr(self.slack, "configured", True):
            return False
        return bool(self.slack.send(text))

    # -- persistence ---------------------------------------------------------- #
    def write_state(self, lanes, violated, held, sent) -> None:
        fps = self.state["fingerprints"]
        if len(fps) > FINGERPRINTS_MAX:
            keep = sorted(fps.items(), key=lambda item: str(item[1].get("last_seen_at") or ""),
                          reverse=True)[:FINGERPRINTS_MAX]
            self.state["fingerprints"] = dict(keep)
        issues = self.state["issues"]
        closed = sorted((k for k, i in issues.items() if i.get("state") != "open"),
                        key=lambda k: str(issues[k].get("closed_at") or issues[k].get("last_seen_at")
                                          or ""), reverse=True)
        for key in closed[CLOSED_ISSUES_KEPT:]:
            issues.pop(key, None)
        for alert_key in [k for k in self.state["alerts"] if k.startswith("issue:")]:
            if alert_key.split(":")[1] not in issues:
                self.state["alerts"].pop(alert_key, None)
        payload = {
            "schema_version": STATE_SCHEMA,
            "checked_at": iso(self.now),
            "previous_checked_at": self.prior.get("checked_at"),
            "git_head": _head(self.root),
            "hard_violation_count": sum(1 for r in lanes.values() if r["stale"]) + len(violated),
            "lanes": {name: {"stale": row["stale"], "last_success_at": row["last_success_at"],
                             "age_hours": round(row["age_hours"], 1)
                             if row["age_hours"] is not None else None,
                             "window_hours": row["window"],
                             "latest_outcome": row["latest_outcome"],
                             "fingerprint": row.get("fingerprint"),
                             "persistent": bool(row.get("persistent")),
                             "held": held.get(name)}
                      for name, row in lanes.items()},
            "feeds_stale": sorted(violated),
            "dispatches": self.dispatches,
            "issue_actions": self.issue_actions,
            "slack": sent,
            "alerts": self.state["alerts"],
            "fingerprints": self.state["fingerprints"],
            "issues": self.state["issues"],
            "fingerprint_cache": self.state["fingerprint_cache"],
            "dispatch_log": self.state["dispatch_log"],
            "digest": self.state["digest"],
            "d1": self.state["d1"],
            "runs": self.state["runs"],
            "unjudged_since": self.state["unjudged_since"],
        }
        path = self.root / STATE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        self._written = payload

    def payload(self, lanes, violated, held, sent, d1_status) -> dict:
        review = getattr(self, "held_for_review", [])
        return {
            "checked_at": iso(self.now),
            "held_for_review": {"items": len(review),
                                "drafts": sum(1 for item in review if item["draft"])},
            "stale_lanes": sorted(n for n, r in lanes.items() if r["stale"]),
            "persistent_lanes": sorted(n for n, r in lanes.items() if r.get("persistent")),
            "feeds_stale": sorted(violated),
            "dispatches": self.dispatches,
            "held": held,
            "issue_actions": self.issue_actions,
            "alerts": [a["text"] for a in self.alerts],
            "slack": sent,
            "d1": d1_status,
            "notes": self.notes + list(getattr(self.github, "errors", []) or [])[:10]
            + list(getattr(self.slack, "errors", []) or [])[:5],
        }


def plan(root: Path = ROOT, now: datetime | None = None, github=None, slack=None, d1=None,
         act: bool = False) -> dict:
    return Supervisor(root, now or datetime.now(timezone.utc), github, slack, d1, act).run()


def clients_from_env(repository: str | None):
    repository = repository or os.environ.get("GITHUB_REPOSITORY") or ""
    github = GhCli(repository) if repository else None
    slack = SlackClient(os.environ.get("SLACK_WEBHOOK_URL"), os.environ.get("SLACK_BOT_TOKEN"),
                        os.environ.get("SLACK_CHANNEL_ID"))
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    d1 = CloudflareD1(token, account) if token and account else None
    return github, slack, d1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository")
    parser.add_argument("--act", action="store_true",
                        help="dispatch healers, write issues and send Slack (default: plan only)")
    args = parser.parse_args()
    github = slack = d1 = None
    if args.act:
        github, slack, d1 = clients_from_env(args.repository)
    result = plan(args.root, github=github, slack=slack, d1=d1, act=args.act)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
