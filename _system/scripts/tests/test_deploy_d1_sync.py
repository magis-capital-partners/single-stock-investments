"""The deploy's D1 stage: budget guard, deferral, per-stage metrics, alerting.

No network and no Cloudflare: wrangler and the exporter scripts are replaced
by a scripted runner, the GraphQL API by a scripted poster, Slack by an opener.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / ".github" / "actions" / "deploy-cloudflare-dashboard"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


d1_budget = load_module("d1_budget", ACTION / "d1_budget.py")
d1_sync = load_module("d1_sync", ACTION / "d1_sync.py")
d1_alert = load_module("d1_alert", ACTION / "d1_alert.py")

TODAY = "2026-09-25"
SLEEVE_SQL = "DELETE FROM sleeve_positions WHERE owner='drew';\n"
SLEEVE_HASH = hashlib.sha256(SLEEVE_SQL.encode("utf-8")).hexdigest()


def done(code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


QUOTA_ERROR = done(1, stderr=(
    '{"error": {"text": "A request to the Cloudflare API failed.", "notes": [{"text": '
    '"Your account has exceeded D1\'s free tier daily row write limit."}], "code": 7500}}'
))


class FakeCloud:
    """Scripted wrangler + exporter scripts, recording every command."""

    def __init__(
        self,
        *,
        ops_state: dict | None = None,
        ops_result: subprocess.CompletedProcess | None = None,
        migrations: subprocess.CompletedProcess | None = None,
        seed_report: dict | None = None,
        executes: dict[str, subprocess.CompletedProcess] | None = None,
        prune: subprocess.CompletedProcess | None = None,
    ):
        self.ops_state = ops_state if ops_state is not None else {}
        self.ops_result = ops_result
        self.migrations = migrations or done(0, "No migrations to apply!")
        self.seed_report = seed_report or {"skip": True, "content_sha256": "c" * 64}
        self.executes = executes or {}
        self.prune = prune or done(0, 'D1_METRICS {"status": "ran", "deleted": 12, "statements": 4, '
                                      '"rows_read": 30, "rows_written": 24}\n')
        self.calls: list[list[str]] = []

    def kinds(self) -> list[str]:
        return [self.kind(call) for call in self.calls]

    @staticmethod
    def kind(command: list[str]) -> str:
        if command[1:3] == ["d1", "migrations"]:
            return "migrations"
        if command[1:3] == ["d1", "execute"]:
            if "--command" in command:
                return "query"
            return "file:" + Path(command[command.index("--file") + 1]).name
        return Path(command[1]).name

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(command)
        kind = self.kind(command)
        if kind == "migrations":
            return self.migrations
        if kind == "query":
            if self.ops_result is not None:
                return self.ops_result
            rows = [{"key": k, "value": v} for k, v in self.ops_state.items()]
            return done(0, json.dumps([{"results": rows, "success": True,
                                        "meta": {"rows_read": len(rows), "rows_written": 0}}]))
        if kind.startswith("file:"):
            return self.executes.get(kind[5:], done(
                0, "Processed 3 queries.\nExecuted 3 queries in 2.10ms (6 rows read, 4 rows written)\n"))
        if kind == "export_sleeve_d1.py":
            # Bytes, not text: the hash must not depend on the platform newline.
            Path(command[command.index("--out") + 1]).write_bytes(SLEEVE_SQL.encode("utf-8"))
            return done(0)
        if kind == "export_dashboard_d1_seed.py":
            Path(command[command.index("--output") + 1]).write_text("-- seed\n", encoding="utf-8")
            Path(command[command.index("--report") + 1]).write_text(json.dumps(self.seed_report), encoding="utf-8")
            return done(0, json.dumps(self.seed_report))
        if kind == "prune_cloudflare_d1.py":
            return self.prune
        raise AssertionError(f"unexpected command {command}")


def budget(written: int = 1_000, read: int = 10_000) -> "d1_budget.Budget":
    return d1_budget.Budget(True, rows_read=read, rows_written=written)


def sync_with(cloud: FakeCloud, tmp_path: Path, **kwargs) -> "d1_sync.D1Sync":
    options = {"budget": budget(), **kwargs}
    return d1_sync.D1Sync(
        wrangler="wrangler", config="cfg.jsonc", database="DB", workdir=tmp_path,
        today=TODAY, now=f"{TODAY}T01:00:00Z", runner=cloud, python="python", **options,
    )


def statuses(sync) -> dict[str, str]:
    return {stage.name: stage.status for stage in sync.stages}


# -- budget guard -------------------------------------------------------------

def graphql(groups: list[dict] | None = None, errors: list[dict] | None = None, accounts=True, status=200):
    captured: dict = {}

    def post(url, headers, body):
        captured.update(url=url, headers=headers, body=json.loads(body))
        payload: dict = {"data": {"viewer": {"accounts": (
            [{"d1AnalyticsAdaptiveGroups": groups or []}] if accounts else [])}}}
        if errors:
            payload = {"data": None, "errors": errors}
        return status, json.dumps(payload)

    return post, captured


def test_budget_sums_every_database_on_the_utc_day():
    post, captured = graphql([
        {"sum": {"rowsRead": 1_200_000, "rowsWritten": 40_000}},
        {"sum": {"rowsRead": 300_000, "rowsWritten": 25_000}},
    ])
    result = d1_budget.check("acct", "token", TODAY, post=post)
    assert (result.available, result.rows_read, result.rows_written, result.over) == (
        True, 1_500_000, 65_000, False,
    )
    assert captured["body"]["variables"] == {"accountTag": "acct", "date": TODAY}
    assert "d1AnalyticsAdaptiveGroups" in captured["body"]["query"]
    assert captured["headers"]["Authorization"] == "Bearer token"


@pytest.mark.parametrize("read,written,over", [
    (3_500_000, 70_000, False),
    (3_500_001, 0, True),
    (0, 70_001, True),
])
def test_budget_thresholds(read, written, over):
    assert d1_budget.Budget(True, rows_read=read, rows_written=written).over is over


@pytest.mark.parametrize("post", [
    lambda url, headers, body: (403, '{"success": false}'),
    lambda url, headers, body: (200, json.dumps({"data": None, "errors": [
        {"message": "not authorized for that account"}]})),
    lambda url, headers, body: (200, json.dumps({"data": {"viewer": {"accounts": []}}})),
    lambda url, headers, body: (_ for _ in ()).throw(urllib.error.URLError("dns")),
])
def test_guard_is_unavailable_not_fatal(post):
    result = d1_budget.check("acct", "token", TODAY, post=post)
    assert result.available is False
    assert result.over is False
    assert "unavailable" in result.describe()


def test_guard_without_credentials_is_unavailable():
    assert d1_budget.check("", "", TODAY).available is False


# -- orchestration --------------------------------------------------------------

def test_nothing_new_writes_nothing(tmp_path):
    cloud = FakeCloud(ops_state={"sleeve:sql_sha256": SLEEVE_HASH, "prune:last_date": TODAY})
    sync = sync_with(cloud, tmp_path)
    sync.run()
    assert statuses(sync) == {
        "budget guard": "ok", "migrations": "skipped", "ops state": "ok",
        "sleeve book": "skipped", "retention": "skipped", "dashboard seed": "skipped",
    }
    assert not [kind for kind in cloud.kinds() if kind.startswith("file:")]
    assert "prune_cloudflare_d1.py" not in cloud.kinds()
    outputs = sync.outputs()
    assert (outputs["d1_deferred"], outputs["d1_rows_written"], outputs["d1_pruned_today"]) == (
        "false", "0", "true",
    )


def test_changes_are_applied_and_measured(tmp_path):
    cloud = FakeCloud(
        ops_state={"sleeve:sql_sha256": "stale"},
        seed_report={"skip": False, "mode": "incremental", "changed_ticker_count": 115,
                     "removed_ticker_count": 0, "statement_count": 1270},
        executes={"dashboard_seed.sql": done(
            0, "\U0001F6A3 Executed 1270 queries in 812.40ms (1269 rows read, 577 rows written)\n")},
    )
    sync = sync_with(cloud, tmp_path)
    sync.run()
    stages = {stage.name: stage for stage in sync.stages}
    assert stages["dashboard seed"].status == "ok"
    assert (stages["dashboard seed"].rows_read, stages["dashboard seed"].rows_written) == (1269, 577)
    assert (stages["retention"].rows_read, stages["retention"].rows_written) == (30, 24)
    assert stages["sleeve book"].status == "ok"
    sleeve_sql = (tmp_path / "sleeve_book.sql").read_text(encoding="utf-8")
    assert f"VALUES ('sleeve:sql_sha256', '{SLEEVE_HASH}'" in sleeve_sql  # recorded atomically
    assert sync.outputs()["d1_rows_written"] == str(577 + 24 + 4)
    summary = sync.summary_markdown()
    assert "| dashboard seed | ok | 1,269 | 577 |" in summary
    assert "115 tickers changed" in summary


def test_over_budget_defers_writes_but_still_migrates(tmp_path):
    cloud = FakeCloud()
    sync = sync_with(cloud, tmp_path, budget=budget(written=82_504))
    sync.run()
    assert cloud.kinds() == ["migrations"]
    assert [s.name for s in sync.deferred()] == ["sleeve book", "retention", "dashboard seed"]
    outputs = sync.outputs()
    assert outputs["d1_deferred"] == "true"
    assert outputs["d1_deferred_stages"] == "sleeve book,retention,dashboard seed"
    assert "82,504 rows written" in outputs["d1_deferred_reason"]
    assert not sync.failed()


def test_quota_error_defers_the_remaining_write_stages(tmp_path):
    cloud = FakeCloud(executes={"sleeve_book.sql": QUOTA_ERROR})
    sync = sync_with(cloud, tmp_path)
    sync.run()
    assert statuses(sync)["sleeve book"] == "deferred"
    assert statuses(sync)["retention"] == "deferred"
    assert statuses(sync)["dashboard seed"] == "deferred"
    assert "prune_cloudflare_d1.py" not in cloud.kinds()
    assert "export_dashboard_d1_seed.py" not in cloud.kinds()
    assert "7500" in sync.outputs()["d1_deferred_reason"]
    assert not sync.failed()


def test_retention_quota_exit_code_defers_the_seed(tmp_path):
    cloud = FakeCloud(prune=done(75, 'D1_METRICS {"status": "quota", "rows_read": 5, "rows_written": 0}\n'))
    sync = sync_with(cloud, tmp_path)
    sync.run()
    assert statuses(sync)["retention"] == "deferred"
    assert statuses(sync)["dashboard seed"] == "deferred"
    assert sync.outputs()["d1_pruned_today"] == "false"


def test_a_real_failure_is_not_a_deferral(tmp_path):
    cloud = FakeCloud(
        seed_report={"skip": False, "mode": "incremental"},
        executes={"dashboard_seed.sql": done(1, stderr="SQLITE_CONSTRAINT: FOREIGN KEY constraint failed")},
    )
    sync = sync_with(cloud, tmp_path)
    sync.run()
    assert [s.name for s in sync.failed()] == ["dashboard seed"]
    assert sync.outputs()["d1_deferred"] == "false"
    assert sync.outputs()["d1_failed"] == "true"


def test_unavailable_guard_warns_once_and_proceeds(tmp_path, capsys):
    cloud = FakeCloud()
    sync = sync_with(cloud, tmp_path, budget=d1_budget.Budget(False, reason="HTTP 403"))
    sync.run()
    assert statuses(sync)["dashboard seed"] == "skipped"
    assert "prune_cloudflare_d1.py" in cloud.kinds()
    out = capsys.readouterr().out
    assert out.count("::warning::budget guard unavailable") == 1


def test_first_deploy_without_ops_state_runs_everything(tmp_path):
    cloud = FakeCloud(ops_result=done(1, stderr="no such table: ops_state: SQLITE_ERROR"))
    sync = sync_with(cloud, tmp_path)
    sync.run()
    assert statuses(sync)["ops state"] == "ok"
    assert "file:sleeve_book.sql" in cloud.kinds()
    assert "prune_cloudflare_d1.py" in cloud.kinds()
    seed_call = next(c for c in cloud.calls if cloud.kind(c) == "export_dashboard_d1_seed.py")
    state = json.loads(Path(seed_call[seed_call.index("--ops-state") + 1]).read_text(encoding="utf-8"))
    assert state == {}


def test_full_resync_is_passed_to_the_exporter(tmp_path):
    cloud = FakeCloud()
    sync_with(cloud, tmp_path, full_resync=True).run()
    seed_call = next(c for c in cloud.calls if cloud.kind(c) == "export_dashboard_d1_seed.py")
    assert "--full" in seed_call


def test_main_writes_outputs_and_summary_and_exits_0_on_deferral(tmp_path, monkeypatch):
    cloud = FakeCloud()
    monkeypatch.setattr(d1_sync, "_run", cloud)
    monkeypatch.setattr(d1_sync.d1_budget, "check", lambda *a, **k: budget(written=90_000))
    output, summary = tmp_path / "out.txt", tmp_path / "summary.md"
    code = d1_sync.main([
        "--wrangler", "wrangler", "--config", "cfg", "--workdir", str(tmp_path / "w"),
        "--summary", str(summary), "--github-output", str(output),
    ])
    assert code == 0
    written = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    assert written["d1_deferred"] == "true"
    assert "Deferred:" in summary.read_text(encoding="utf-8")


def test_main_exits_1_on_a_real_failure(tmp_path, monkeypatch):
    cloud = FakeCloud(migrations=done(1, stderr="Authentication error [code: 10000]"))
    monkeypatch.setattr(d1_sync, "_run", cloud)
    monkeypatch.setattr(d1_sync.d1_budget, "check", lambda *a, **k: budget())
    code = d1_sync.main([
        "--wrangler", "wrangler", "--config", "cfg", "--workdir", str(tmp_path),
        "--summary", str(tmp_path / "s.md"), "--github-output", str(tmp_path / "o.txt"),
    ])
    assert code == 1


# -- Slack --------------------------------------------------------------------

def test_alert_names_the_stages_the_reason_and_the_run():
    payload = d1_alert.build_message(
        repository="org/repo", run_url="https://github.com/org/repo/actions/runs/1",
        stages="retention,dashboard seed", reason="today 82,504 rows written", utc_date=TODAY,
    )
    text = payload["text"]
    assert "retention, dashboard seed" in text
    assert "82,504 rows written" in text
    assert "actions/runs/1" in text
    text.encode("ascii")


def test_alert_posts_to_the_webhook(monkeypatch, capsys):
    seen = {}

    class Response:
        status = 200

    def opener(request):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/T/B/X")
    assert d1_alert.main(["--stages", "dashboard seed", "--reason", "quota"], opener=opener) == 0
    assert seen["url"] == "https://hooks.slack.test/T/B/X"
    assert "dashboard seed" in seen["body"]["text"]
    assert "Slack alert posted." in capsys.readouterr().out


def test_alert_failures_are_warnings_never_errors(monkeypatch, capsys):
    def opener(request):
        raise urllib.error.URLError("unreachable")

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/T/B/X")
    assert d1_alert.main(["--stages", "retention"], opener=opener) == 0
    assert "::warning::Slack alert was not delivered" in capsys.readouterr().out
    monkeypatch.delenv("SLACK_WEBHOOK_URL")
    assert d1_alert.main(["--stages", "retention"]) == 0
    assert "SLACK_WEBHOOK_URL is not set" in capsys.readouterr().out
