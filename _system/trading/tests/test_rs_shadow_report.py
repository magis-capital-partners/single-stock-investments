"""Shadow-session evidence report (read-only journal; no socket)."""

from datetime import datetime, timedelta, timezone
import json

from _system.trading.rs_paper_executor import __main__ as cli
from _system.trading.rs_paper_executor.journal import Journal
from _system.trading.rs_paper_executor.shadow_report import shadow_report

SESSIONS = (("2026-11-17", 14), ("2026-11-18", 14))  # 09:30-16:00 ET = 14:30-21:00Z


def build(path, *, gap_at=None, order=False, kill=False, entry=True):
    j = Journal(path, "p", "RSLIVE|")
    for day, _ in SESSIONS:
        t = datetime.fromisoformat(day + "T14:30:00+00:00")
        end = datetime.fromisoformat(day + "T21:00:00+00:00")
        while t < end:
            if not (gap_at and day == gap_at[0] and gap_at[1] <= t < gap_at[2]):
                j.event(t.isoformat(), "heartbeat", {"paper_only": False})
            t += timedelta(seconds=30)
        j.event(day + "T15:00:00+00:00", "proposal_blocked",
                {"id": "x", "reason": "fresh eligibility source required"})
    if entry:
        j.event("2026-11-18T15:05:00+00:00", "shadow_entry",
                {"id": "s1", "ticker": "ABC", "shares": 500, "limit": 2.0,
                 "reason": "arm file absent", "initial_margin": 1000,
                 "maintenance_margin": 900})
    if order:
        with j.db:
            j.db.execute("INSERT INTO orders(ref,side,shares,state) VALUES('RSLIVE|x','SELL',1,'filled')")
    if kill:
        j.set("kill", True)
    j.close()
    return path


def test_clean_shadow_week_is_ready_for_review(tmp_path):
    report = shadow_report(build(tmp_path / "s.sqlite"), min_sessions=2)
    assert report["ready_for_arm_review"] is True
    assert report["checks"]["sessions_observed"] == 2
    assert report["checks"]["worst_heartbeat_gap_seconds"] <= 60
    assert report["would_be_entries"] == 1
    assert report["refusals_total"] == {"fresh eligibility source required": 2}
    assert report["journal_prefix"] == "RSLIVE|"


def test_outage_order_or_latch_blocks_review(tmp_path):
    gap = ("2026-11-18", datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc),
           datetime(2026, 11, 18, 16, 10, tzinfo=timezone.utc))
    r = shadow_report(build(tmp_path / "a.sqlite", gap_at=gap), min_sessions=2)
    assert not r["ready_for_arm_review"] and not r["checks"]["uptime_ok"]
    r = shadow_report(build(tmp_path / "b.sqlite", order=True), min_sessions=2)
    assert not r["ready_for_arm_review"] and not r["checks"]["no_orders_transmitted"]
    r = shadow_report(build(tmp_path / "c.sqlite", kill=True), min_sessions=2)
    assert not r["ready_for_arm_review"] and not r["checks"]["kill_latch_clear"]
    r = shadow_report(build(tmp_path / "d.sqlite"), min_sessions=5)
    assert not r["checks"]["enough_sessions"]


def test_uptime_without_a_would_be_entry_is_not_ready(tmp_path):
    # Every proposal refused (no evidence producers): the live entry path never ran.
    r = shadow_report(build(tmp_path / "e.sqlite", entry=False), min_sessions=2)
    assert r["checks"]["uptime_ok"] and r["checks"]["enough_sessions"]
    assert r["would_be_entries"] == 0
    assert not r["checks"]["enough_would_be_entries"] and not r["ready_for_arm_review"]
    assert shadow_report(tmp_path / "e.sqlite", min_sessions=2,
                         min_entries=0)["ready_for_arm_review"] is True


def test_cli_shadow_report_exit_codes(tmp_path, capsys):
    state = build(tmp_path / "s.sqlite")
    config = tmp_path / "c.json"
    config.write_text(json.dumps({
        "endpoint": {"account": "DU000000", "client_id": 171, "port": 4002},
        "policy": {"spx_reserve": 1, "cash_buffer": 1, "daily_loss_limit": 1}}))
    assert cli.main(["shadow-report", "--config", str(config), "--state", str(state),
                     "--min-sessions", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["ready_for_arm_review"] is True
    assert cli.main(["shadow-report", "--config", str(config), "--state", str(state)]) == 3
