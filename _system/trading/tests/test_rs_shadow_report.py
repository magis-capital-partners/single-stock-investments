"""Shadow acceptance (read-only journal; no socket): owner rules of 2026-11-19."""

from datetime import datetime, timedelta
import json

from _system.trading.rs_paper_executor import __main__ as cli
from _system.trading.rs_paper_executor.journal import Journal
from _system.trading.rs_paper_executor.shadow_report import _feed, shadow_report, verify_mechanics


def test_republished_old_state_does_not_count_as_fresh_shadow_coverage():
    at = datetime.fromisoformat("2026-11-19T15:00:00+00:00")
    beat = {"operations_generated_at": "2026-11-19T14:59:55Z",
            "operations_state_at": "2026-11-19T14:57:59Z"}
    assert _feed([(at, beat)], 120)[0] == 0.0

DAYS = ("2026-11-17", "2026-11-18")  # 09:30-16:00 ET = 14:30-21:00Z


def entry(j, at, cik, action, **extra):
    j.event(at, "shadow_entry", {
        "id": "cand:" + action, "ticker": "T" + cik, "shares": 500, "limit": 2.0,
        "reason": "shadow journal", "initial_margin": 1000, "maintenance_margin": 900,
        "cik": cik, "action_id": action, "conid": int(cik),
        "published_at": at, "first_seen_at": at, "synthetic_control": False, **extra})


def build(path, *, role="shadow", stale=None, gap=None, order=False, halt=None,
          entries="three"):
    j = Journal(path, "p", "RSLIVE|")
    j.set("journal_role", role)
    for day in DAYS:
        t = datetime.fromisoformat(day + "T14:30:00+00:00")
        end = datetime.fromisoformat(day + "T21:00:00+00:00")
        while t < end:
            skip = gap and day == gap[0] and gap[1] <= t.hour < gap[2]
            if not skip:
                feed_age = 600 if (stale and day == stale[0] and stale[1] <= t.hour < stale[2]) else 20
                j.event(t.isoformat(), "heartbeat", {
                    "paper_only": False,
                    "operations_generated_at": (t - timedelta(seconds=feed_age)).isoformat(),
                    "operations_downloaded_at": (t - timedelta(seconds=feed_age - 3)).isoformat()})
            t += timedelta(seconds=30)
        j.event(day + "T15:00:00+00:00", "proposal_blocked",
                {"id": "x", "reason": "fresh eligibility source required"})
        j.event(day + "T15:01:00+00:00", "quote_check",
                {"conid": 7, "ticker": "Q", "available": False, "reason": "stale or future evidence"})
    if entries == "three":
        entry(j, "2026-11-17T15:05:00+00:00", "111", "a1")
        entry(j, "2026-11-18T15:05:00+00:00", "222", "a2")
        entry(j, "2026-11-18T15:06:00+00:00", "333", "a3")
    elif entries == "excluded":
        entry(j, "2026-11-17T15:05:00+00:00", "111", "a1")
        entry(j, "2026-11-17T15:06:00+00:00", "111", "a1", id="other-publisher")  # duplicate
        entry(j, "2026-11-18T15:05:00+00:00", "222", "synthetic-control:x")         # control
        entry(j, "2026-11-18T15:06:00+00:00", "333", "a3",
              first_seen_at="2026-11-18T15:06:00+00:00",
              published_at="2026-11-18T13:00:00+00:00")                            # catch-up
    if order:
        with j.db:
            j.db.execute("INSERT INTO orders(ref,side,shares,state) VALUES('RSLIVE|x','BUY',1,'filled')")
    if halt:
        j.set("entry_halt", halt)
    j.close()
    return path


def mechanics(tmp_path, *, flat=True, cancel=True):
    jp = tmp_path / "p.integration.sqlite"
    j = Journal(jp, "p")  # RSPAPER| namespace
    j.set("endpoint", {"account": "DU1234567", "client_id": 171, "port": 4002})
    with j.db:
        j.db.execute("INSERT INTO orders(ref,side,shares,filled,state) VALUES('RSPAPER|e','SELL',10,10,'filled')")
        j.db.execute("INSERT INTO orders(ref,side,shares,filled,state) VALUES('RSPAPER|c','SELL',1,0,?)",
                     ("cancelled" if cancel else "submitted",))
        j.db.execute("INSERT INTO orders(ref,side,shares,filled,state) VALUES('RSPAPER|b','BUY',10,10,'filled')")
        for n, ref in enumerate(["RSPAPER|e", "RSPAPER|e", "RSPAPER|b"]):
            j.db.execute("INSERT INTO fills(exec_id,ref,shares) VALUES(?,?,5)", ("x%d" % n, ref))
        j.db.execute("INSERT INTO positions(signal_id,shares) VALUES('s',?)", (0 if flat else 10,))
    j.set("kill", True)
    j.close()
    steps = {name: {"pass": True} for name in (
        "delayed_quote_refused", "whatif_preview", "duplicate_prevented", "reconnect_recovery",
        "cancel_confirmed", "scoped_cover", "kill_latch_holds")}
    steps["entry_fill"] = {"pass": True, "ref": "RSPAPER|e", "fills": 2}
    rp = tmp_path / "stage-p.json"
    rp.write_text(json.dumps({"mode": "mechanics_only", "paper_only": True, "pass": True,
                              "synthetic_control": True, "steps": steps, "journal": str(jp)}))
    return rp, jp


def ready(tmp_path, path, **kw):
    folder = tmp_path / ("m-" + path.stem)  # one stage-P pair per journal under test
    folder.mkdir()
    rp, jp = mechanics(folder)
    return shadow_report(path, min_sessions=2, mechanics=verify_mechanics(rp, jp), **kw)


def test_clean_shadow_run_is_ready_for_review(tmp_path):
    r = ready(tmp_path, build(tmp_path / "s.sqlite"))
    assert r["ready_for_arm_review"] is True, r["failed_checks"]
    c = r["checks"]
    assert c["complete_sessions"] == 2 and c["opportunities"] == 3
    assert c["opportunity_issuers"] == 3 and c["opportunity_sessions"] == 2
    s = r["sessions"][0]
    assert s["process"]["max_gap_seconds"] <= 60 and s["source"]["feed_fresh_share"] == 1.0
    assert s["source"]["median_download_lag_seconds"] == 3.0
    assert s["quotes"]["7"] == {"ticker": "Q", "checks": 1, "available": False,
                                "reasons": ["stale or future evidence"]}
    assert r["mechanics"]["partial_fills"] == {"observed_on_paper": True, "unit_tested": True}


def test_duplicates_controls_and_catch_ups_never_count(tmp_path):
    r = ready(tmp_path, build(tmp_path / "s.sqlite", entries="excluded"))
    assert r["checks"]["opportunities"] == 1 and not r["checks"]["enough_opportunities"]
    assert r["excluded_entries"] == {"duplicate_issuer_action": 1, "synthetic_control": 1,
                                     "catch_up_announcement": 1}
    assert "enough_opportunities" in r["failed_checks"]


def test_quiet_sessions_alone_are_never_ready(tmp_path):
    r = ready(tmp_path, build(tmp_path / "s.sqlite", entries=None))
    assert r["checks"]["enough_complete_sessions"] and not r["ready_for_arm_review"]


def test_a_stale_feed_or_a_process_gap_makes_a_session_incomplete(tmp_path):
    r = ready(tmp_path, build(tmp_path / "a.sqlite", stale=("2026-11-18", 16, 17)))
    day = r["sessions"][1]
    assert day["process"]["max_gap_seconds"] <= 60 and not day["complete"]
    assert day["source"]["max_stale_seconds"] >= 3500
    assert not r["ready_for_arm_review"]
    r = ready(tmp_path, build(tmp_path / "b.sqlite", gap=("2026-11-18", 16, 17)))
    assert not r["sessions"][1]["complete"] and r["checks"]["complete_sessions"] == 1


def test_orders_role_halt_and_mechanics_each_block_review(tmp_path):
    r = ready(tmp_path, build(tmp_path / "a.sqlite", order=True))
    assert r["failed_checks"] == ["zero_orders"]
    r = ready(tmp_path, build(tmp_path / "b.sqlite", role="live"))
    assert r["failed_checks"] == ["dedicated_shadow_journal"]
    r = ready(tmp_path, build(tmp_path / "c.sqlite", halt="account_guard_publish:OSError"))
    assert r["failed_checks"] == ["entry_halt_clear"]
    r = shadow_report(build(tmp_path / "d.sqlite"), min_sessions=2)
    assert r["failed_checks"] == ["mechanics_verified"]


def test_mechanics_report_is_checked_against_its_own_journal(tmp_path):
    rp, jp = mechanics(tmp_path)
    assert verify_mechanics(rp, jp)["pass"] is True
    other = tmp_path / "other"
    other.mkdir()
    rp, jp = mechanics(other, flat=False, cancel=False)
    problems = verify_mechanics(rp, jp)["problems"]
    assert "journal is not flat" in problems
    assert "no broker-confirmed cancel in the journal" in problems
    data = json.loads(rp.read_text())
    data["steps"]["scoped_cover"]["pass"] = False
    data["journal"] = str(tmp_path / "elsewhere.sqlite")
    rp.write_text(json.dumps(data))
    problems = verify_mechanics(rp, jp)["problems"]
    assert "step missing or failed: scoped_cover" in problems
    assert "report names a different journal" in problems


def test_cli_shadow_report_exit_codes(tmp_path, capsys):
    state = build(tmp_path / "s.sqlite")
    rp, jp = mechanics(tmp_path)
    config = tmp_path / "c.json"
    config.write_text(json.dumps({
        "endpoint": {"account": "DU000000", "client_id": 171, "port": 4002},
        "policy": {"spx_reserve": 1, "cash_buffer": 1, "daily_loss_limit": 1}}))
    base = ["shadow-report", "--config", str(config), "--state", str(state), "--min-sessions", "2"]
    assert cli.main(base + ["--mechanics-report", str(rp), "--mechanics-journal", str(jp)]) == 0
    assert json.loads(capsys.readouterr().out)["ready_for_arm_review"] is True
    assert cli.main(base) == 3  # no verified stage-P mechanics
    capsys.readouterr()
    assert cli.main(base + ["--mechanics-report", str(rp)]) == 2
