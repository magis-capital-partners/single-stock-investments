#!/usr/bin/env python3
"""The D1 half of a dashboard deploy: measured, gated, and deferrable.

Stages, in order (every stage runs whatever the one before it did, except
that write stages stop once the daily quota is known to be spent):

  budget guard   today's account-wide usage (d1_budget.py); above 70k rows
                 written or 3.5M rows read, the write stages are DEFERRED
  migrations     always -- the code this deploy ships may need them
  ops state      one read of ops_state (a handful of rows)
  sleeve book    applied only when the committed book's SQL changed
  retention      once per UTC day (prune_cloudflare_d1.py)
  dashboard seed incremental export; skipped when the content hash matches

A stage stopped by the daily quota (code 7500) is DEFERRED too. Deferral is not
a failure here: the static Pages deploy still has to ship, so this step exits 0
and the workflow fails the job afterwards, with a Slack alert. Anything else
that goes wrong is a real failure and exits 1.

Every stage reports rows_read / rows_written (from D1's own counters) to the
job summary; the retention stage reports them per statement in its log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import d1_budget  # noqa: E402

SEED_EXPORTER = ROOT / "_system" / "scripts" / "export_dashboard_d1_seed.py"
SLEEVE_EXPORTER = ROOT / "_system" / "scripts" / "export_sleeve_d1.py"
PRUNER = ROOT / "_system" / "scripts" / "prune_cloudflare_d1.py"

SLEEVE_KEY = "sleeve:sql_sha256"
PRUNE_KEY = "prune:last_date"
QUOTA_EXIT_CODE = 75
QUOTA_PATTERN = re.compile(
    r"exceeded D1's free tier daily row (read|write) limit|\"code\"\s*:\s*7500\b", re.IGNORECASE
)
EXECUTED_PATTERN = re.compile(
    r"Executed\s+(\d+)\s+quer(?:y|ies)\s+in\s+[^(]*\((\d+)\s+rows?\s+read,\s*(\d+)\s+rows?\s+written\)",
    re.IGNORECASE,
)
MIGRATION_NAME = re.compile(r"\b\d{4}_[A-Za-z0-9_]+\.sql\b")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def log(message: str) -> None:
    # The Windows console is cp1252 and wrangler prints emoji: stay ASCII.
    print(message.encode("ascii", "replace").decode("ascii"), flush=True)


def _decode_json(output: str) -> Any:
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON in output")


def _tail(proc: subprocess.CompletedProcess, limit: int = 600) -> str:
    return ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-limit:]


@dataclass
class Stage:
    name: str
    status: str  # ok | skipped | deferred | failed
    detail: str = ""
    rows_read: int | None = None
    rows_written: int | None = None
    seconds: float = 0.0


class D1Sync:
    def __init__(
        self,
        *,
        wrangler: str,
        config: str,
        database: str,
        workdir: Path,
        today: str,
        now: str,
        runner: Runner | None = None,
        python: str = sys.executable,
        budget: d1_budget.Budget | None = None,
        full_resync: bool = False,
    ):
        self.wrangler = wrangler
        self.config = config
        self.database = database
        self.workdir = workdir
        self.today = today
        self.now = now
        self.runner = runner or _run
        self.python = python
        self.budget = budget
        self.full_resync = full_resync
        self.stages: list[Stage] = []
        self.quota_hit = False
        self.pruned_today = False
        self.ops_state: dict[str, str] | None = None

    # -- plumbing -----------------------------------------------------------
    def _wrangler(self, *args: str) -> subprocess.CompletedProcess:
        return self.runner([self.wrangler, "d1", *args])

    def _is_quota(self, proc: subprocess.CompletedProcess) -> bool:
        return proc.returncode == QUOTA_EXIT_CODE or bool(
            QUOTA_PATTERN.search((proc.stdout or "") + (proc.stderr or ""))
        )

    def _record(self, stage: Stage, started: float) -> Stage:
        stage.seconds = round(time.monotonic() - started, 1)
        self.stages.append(stage)
        rows = ""
        if stage.rows_read is not None or stage.rows_written is not None:
            rows = f" rows_read={stage.rows_read} rows_written={stage.rows_written}"
        log(f"=== D1 stage '{stage.name}': {stage.status}{rows} {stage.detail}".rstrip())
        if stage.status == "deferred":
            log(f"::warning::D1 stage deferred: {stage.name}. {stage.detail}")
        elif stage.status == "failed":
            log(f"::error::D1 stage failed: {stage.name}. {stage.detail}")
        return stage

    def _write_blocked(self) -> str | None:
        if self.budget is not None and self.budget.over:
            return f"daily budget guard: {self.budget.describe()}"
        if self.quota_hit:
            return "the D1 daily free-tier quota was hit by an earlier stage (code 7500)"
        return None

    def execute_file(self, path: Path) -> subprocess.CompletedProcess:
        return self._wrangler(
            "execute", self.database, "--remote", "--yes", "--file", str(path), "--config", self.config,
        )

    @staticmethod
    def executed_rows(proc: subprocess.CompletedProcess) -> tuple[int | None, int | None]:
        match = EXECUTED_PATTERN.search((proc.stdout or "") + "\n" + (proc.stderr or ""))
        if not match:
            return None, None
        return int(match.group(2)), int(match.group(3))

    # -- stages --------------------------------------------------------------
    def stage_budget(self) -> None:
        started = time.monotonic()
        budget = self.budget
        if budget is None:
            budget = d1_budget.check(
                os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
                os.environ.get("CLOUDFLARE_API_TOKEN", ""),
                self.today,
            )
            self.budget = budget
        if not budget.available:
            # Warn once and carry on: the 7500 quota error stays the backstop.
            log(f"::warning::{budget.describe()}. D1 stages run without the pre-check.")
            self._record(Stage("budget guard", "skipped", budget.describe()), started)
            return
        status = "deferred" if budget.over else "ok"
        detail = budget.describe() + ("; write stages deferred" if budget.over else "")
        stage = Stage("budget guard", status, detail, budget.rows_read, budget.rows_written)
        stage.seconds = round(time.monotonic() - started, 1)
        self.stages.append(stage)
        log(f"=== D1 budget guard: {detail}")

    def stage_migrations(self) -> None:
        started = time.monotonic()
        proc = self._wrangler("migrations", "apply", self.database, "--remote", "--config", self.config)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            applied = sorted(set(MIGRATION_NAME.findall(output)))
            if "No migrations to apply" in output or not applied:
                self._record(Stage("migrations", "skipped", "no pending migrations"), started)
            else:
                self._record(Stage("migrations", "ok", "applied " + ", ".join(applied)), started)
            return
        if self._is_quota(proc):
            self.quota_hit = True
            self._record(Stage("migrations", "deferred", "daily quota (7500)"), started)
            return
        self._record(Stage("migrations", "failed", _tail(proc)), started)

    def stage_ops_state(self) -> None:
        started = time.monotonic()
        proc = self._wrangler(
            "execute", self.database, "--remote", "--yes",
            "--command", "SELECT key, value FROM ops_state",
            "--config", self.config, "--json",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            if "no such table" in output.lower():
                self.ops_state = {}
                self._record(Stage("ops state", "ok", "no ops_state table yet (first deploy)"), started)
            elif self._is_quota(proc):
                self.quota_hit = True
                self._record(Stage("ops state", "deferred", "daily quota (7500)"), started)
            else:
                # Not fatal: every stage below still has a safe path without it.
                self._record(Stage("ops state", "skipped", "unreadable: " + _tail(proc, 200)), started)
            return
        try:
            statements = _decode_json(proc.stdout)
            statements = statements if isinstance(statements, list) else [statements]
            rows = [row for statement in statements for row in (statement.get("results") or [])]
            rows_read = sum(int((statement.get("meta") or {}).get("rows_read") or 0) for statement in statements)
        except (ValueError, AttributeError, TypeError):
            self._record(Stage("ops state", "skipped", "unparseable wrangler output"), started)
            return
        self.ops_state = {str(row.get("key")): str(row.get("value")) for row in rows if row.get("key")}
        self._record(Stage("ops state", "ok", f"{len(self.ops_state)} keys", rows_read, 0), started)

    def stage_sleeve(self) -> None:
        started = time.monotonic()
        blocked = self._write_blocked()
        if blocked:
            self._record(Stage("sleeve book", "deferred", blocked), started)
            return
        sql_path = self.workdir / "sleeve_book.sql"
        proc = self.runner([self.python, str(SLEEVE_EXPORTER), "--out", str(sql_path)])
        if proc.returncode != 0:
            self._record(Stage("sleeve book", "failed", "export failed: " + _tail(proc)), started)
            return
        digest = hashlib.sha256(sql_path.read_bytes()).hexdigest()
        if self.ops_state is not None and self.ops_state.get(SLEEVE_KEY) == digest:
            self._record(Stage("sleeve book", "skipped", "committed book unchanged", 0, 0), started)
            return
        with sql_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "INSERT INTO ops_state (key, value, updated_at) "
                f"VALUES ('{SLEEVE_KEY}', '{digest}', '{self.now}') "
                "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;\n"
            )
        proc = self.execute_file(sql_path)
        rows_read, rows_written = self.executed_rows(proc)
        if proc.returncode == 0:
            self._record(Stage("sleeve book", "ok", "published", rows_read, rows_written), started)
        elif self._is_quota(proc):
            self.quota_hit = True
            self._record(Stage("sleeve book", "deferred", "daily quota (7500)", rows_read, rows_written), started)
        else:
            self._record(Stage("sleeve book", "failed", _tail(proc), rows_read, rows_written), started)

    def stage_retention(self) -> None:
        started = time.monotonic()
        blocked = self._write_blocked()
        if blocked:
            self._record(Stage("retention", "deferred", blocked), started)
            return
        if self.ops_state is not None and self.ops_state.get(PRUNE_KEY) == self.today:
            self.pruned_today = True
            self._record(Stage("retention", "skipped", f"already ran today ({self.today} UTC)", 0, 0), started)
            return
        proc = self.runner([
            self.python, str(PRUNER),
            "--wrangler", self.wrangler, "--database", self.database, "--config", self.config,
        ])
        metrics: dict[str, Any] = {}
        for line in (proc.stdout or "").splitlines():
            if line.startswith("D1_METRICS "):
                try:
                    metrics = json.loads(line.split(" ", 1)[1])
                except json.JSONDecodeError:
                    metrics = {}
        rows_read = metrics.get("rows_read")
        rows_written = metrics.get("rows_written")
        if proc.returncode == 0:
            self.pruned_today = True
            status = "skipped" if metrics.get("status") == "skipped" else "ok"
            detail = (
                f"{metrics.get('deleted', 0)} rows deleted in {metrics.get('statements', 0)} statements"
                if status == "ok" else str(metrics.get("reason") or "already ran today")
            )
            self._record(Stage("retention", status, detail, rows_read, rows_written), started)
        elif proc.returncode == QUOTA_EXIT_CODE or self._is_quota(proc):
            self.quota_hit = True
            self._record(Stage("retention", "deferred", "daily quota (7500); retried after 00:00 UTC",
                               rows_read, rows_written), started)
        else:
            self._record(Stage("retention", "failed", _tail(proc), rows_read, rows_written), started)

    def stage_seed(self) -> None:
        started = time.monotonic()
        blocked = self._write_blocked()
        if blocked:
            self._record(Stage("dashboard seed", "deferred", blocked), started)
            return
        seed_path = self.workdir / "dashboard_seed.sql"
        report_path = self.workdir / "dashboard_seed_report.json"
        command = [self.python, str(SEED_EXPORTER), "--output", str(seed_path), "--report", str(report_path)]
        if self.ops_state is not None:
            state_path = self.workdir / "ops_state.json"
            state_path.write_text(json.dumps(self.ops_state), encoding="utf-8")
            command += ["--ops-state", str(state_path)]
        if self.full_resync:
            command.append("--full")
        proc = self.runner(command)
        if proc.returncode != 0 or not report_path.is_file():
            # A failed export must never re-apply an older seed file.
            self._record(Stage("dashboard seed", "failed", "export failed: " + _tail(proc)), started)
            return
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("skip"):
            self._record(Stage(
                "dashboard seed", "skipped",
                f"content unchanged ({str(report.get('content_sha256'))[:12]})", 0, 0,
            ), started)
            return
        detail = (
            f"{report.get('mode')}: {report.get('changed_ticker_count')} tickers changed, "
            f"{report.get('removed_ticker_count')} removed, {report.get('statement_count')} statements"
        )
        proc = self.execute_file(seed_path)
        rows_read, rows_written = self.executed_rows(proc)
        if proc.returncode == 0:
            self._record(Stage("dashboard seed", "ok", detail, rows_read, rows_written), started)
        elif self._is_quota(proc):
            self.quota_hit = True
            self._record(Stage("dashboard seed", "deferred", "daily quota (7500); " + detail,
                               rows_read, rows_written), started)
        else:
            self._record(Stage("dashboard seed", "failed", _tail(proc), rows_read, rows_written), started)

    def run(self) -> list[Stage]:
        self.stage_budget()
        self.stage_migrations()
        if self._write_blocked() is None:
            self.stage_ops_state()
        self.stage_sleeve()
        self.stage_retention()
        self.stage_seed()
        return self.stages

    # -- results -------------------------------------------------------------
    def deferred(self) -> list[Stage]:
        return [s for s in self.stages if s.status == "deferred" and s.name != "budget guard"]

    def failed(self) -> list[Stage]:
        return [s for s in self.stages if s.status == "failed"]

    def deferred_reason(self) -> str:
        if self.budget is not None and self.budget.over:
            return self.budget.describe()
        if self.quota_hit:
            return "Cloudflare refused a write: the D1 free-tier daily row quota is exhausted (code 7500)"
        return ""

    def outputs(self) -> dict[str, str]:
        deploy_stages = [s for s in self.stages if s.name != "budget guard"]
        return {
            "d1_deferred": "true" if self.deferred() else "false",
            "d1_deferred_stages": ",".join(s.name for s in self.deferred()),
            "d1_deferred_reason": self.deferred_reason(),
            "d1_failed": "true" if self.failed() else "false",
            "d1_utc_date": self.today,
            "d1_pruned_today": "true" if self.pruned_today else "false",
            "d1_rows_read": str(sum(s.rows_read or 0 for s in deploy_stages)),
            "d1_rows_written": str(sum(s.rows_written or 0 for s in deploy_stages)),
        }

    def summary_markdown(self) -> str:
        def cell(value: int | None) -> str:
            return "n/a" if value is None else f"{value:,}"

        lines = [
            "### D1 synchronization",
            "",
            "| Stage | Status | Rows read | Rows written | Seconds | Detail |",
            "|---|---|---:|---:|---:|---|",
        ]
        for stage in self.stages:
            detail = stage.detail.replace("|", "/").replace("\n", " ")[:220]
            label = stage.name + (" (account, today)" if stage.name == "budget guard" else "")
            lines.append(
                f"| {label} | {stage.status} | {cell(stage.rows_read)} | "
                f"{cell(stage.rows_written)} | {stage.seconds} | {detail} |"
            )
        out = self.outputs()
        lines += [
            "",
            f"This deploy: **{int(out['d1_rows_read']):,} rows read, "
            f"{int(out['d1_rows_written']):,} rows written** (D1 free tier: 5,000,000 read / "
            f"100,000 written per UTC day).",
        ]
        if self.deferred():
            lines.append(
                f"\n**Deferred:** {out['d1_deferred_stages']} -- {out['d1_deferred_reason']}. "
                "The static site deployed; the first deploy after 00:00 UTC retries."
            )
        return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--wrangler", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--database", default="DB")
    parser.add_argument("--workdir", type=Path, default=Path(os.environ.get("RUNNER_TEMP", ".")))
    parser.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--full-resync", default="false")
    args = parser.parse_args(argv)

    moment = datetime.now(timezone.utc)
    args.workdir.mkdir(parents=True, exist_ok=True)
    sync = D1Sync(
        wrangler=args.wrangler,
        config=args.config,
        database=args.database,
        workdir=args.workdir,
        today=moment.strftime("%Y-%m-%d"),
        now=moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        full_resync=str(args.full_resync).lower() == "true",
    )
    sync.run()
    summary = sync.summary_markdown()
    log(summary)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(summary)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in sync.outputs().items():
                handle.write(f"{key}={value}\n")
    if sync.failed():
        log("::error::A D1 stage failed for a reason other than the daily quota.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
