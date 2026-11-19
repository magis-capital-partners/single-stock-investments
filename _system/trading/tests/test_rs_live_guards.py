"""Live-mode account-sharing guards. No socket, Gateway or vendor is contacted."""

from dataclasses import replace
import json

import pytest

from _system.trading.rs_paper_executor import __main__ as cli
from _system.trading.rs_paper_executor import safety
from _system.trading.rs_paper_executor.arm import SCHEMA as ARM_SCHEMA, arm_state
from _system.trading.rs_paper_executor.book import BookMargin
from _system.trading.rs_paper_executor.claims import ClaimBook
from _system.trading.rs_paper_executor.engine import Executor
from _system.trading.rs_paper_executor.journal import Journal
from _system.trading.rs_paper_executor.policy import Policy
from _system.trading.rs_paper_executor.safety import (
    LiveEndpoint,
    PaperEndpoint,
    SafetyError,
)
from _system.trading.tests.test_rs_paper_executor import (  # noqa: F401 (fixture)
    NOW,
    Broker,
    no_network,
    run,
    signal,
)

ACCOUNT = "U1234567"
LIVE = LiveEndpoint(ACCOUNT, 60, 7496)


class LiveBroker(Broker):
    def __init__(self, claims=None):
        super().__init__()
        self.snap["account"] = ACCOUNT
        self.snap["foreign_open_conids"] = []
        self.preview["account"] = ACCOUNT
        self.claims, self.claimed_at_submit = claims, []

    async def submit(self, intent):
        if self.claims is not None:
            self.claimed_at_submit.append(self.claims.held(NOW))
        ack = await super().submit(intent)
        self.snap["orders"][-1]["client_id"] = 60
        return ack


def spx_file(root, claim, *, nav=5_000_000, today="2026-11-18", product="spx"):
    day = root / today
    day.mkdir(parents=True, exist_ok=True)
    (day / f"book_margin_{product}.json").write_text(json.dumps({
        "schema": 1, "product": product, "today": today, "ts": NOW,
        "account_nav": nav, "engine_margin": claim, "pending_margin": 0,
        "sleeves": 0, "sleeves_source": "none", "claim": claim}))


def write_arm(path, policy, **changes):
    data = {"schema": ARM_SCHEMA, "account": ACCOUNT, "client_id": 60,
            "policy_hash": policy.digest, "armed_by": "owner",
            "valid_until": "2026-11-30T00:00:00+00:00", **changes}
    path.write_text(json.dumps(data))


@pytest.fixture
def live(tmp_path):
    policy = Policy(spx_reserve=1_000_000, cash_buffer=100_000, daily_loss_limit=2500,
                    cushion_halt=0.30, cushion_flatten=0.20)
    journal = Journal(tmp_path / "live.sqlite", policy.digest, "RSLIVE|")
    claims = ClaimBook(tmp_path / "claims", "reverse-split", ACCOUNT)
    spx_root = tmp_path / "spx-data-live"
    spx_file(spx_root, 1_000_000)
    book = BookMargin(spx_root, tmp_path / "rs-book", policy, 0.6)
    arm = tmp_path / "ARM"
    write_arm(arm, policy)
    broker = LiveBroker(claims)
    engine = Executor(LIVE, policy, journal, broker, claims=claims, book=book,
                      transmit=lambda: arm_state(arm, LIVE, policy, broker.now()))
    yield SimpleBox(engine=engine, journal=journal, broker=broker, claims=claims,
                    spx_root=spx_root, arm=arm, policy=policy, tmp=tmp_path)
    journal.close()


class SimpleBox:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def events(journal, kind):
    return [json.loads(x["payload"]) for x in journal.rows("events") if x["kind"] == kind]


# ---- endpoint ------------------------------------------------------------

def test_registered_executor_endpoint_validates():
    assert LIVE.validate() is LIVE and LIVE.prefix == "RSLIVE|"


@pytest.mark.parametrize("change", [
    dict(client_id=17), dict(client_id=50), dict(client_id=97), dict(client_id=91),
    dict(client_id=140), dict(client_id=61), dict(client_id=171), dict(port=4001),
    dict(port=7497), dict(port=4002), dict(host="10.0.0.5"), dict(account="DU123"),
    dict(account="U123|x"), dict(mode="paper"), dict(deployment_role="isolated_paper_executor"),
])
def test_live_endpoint_refuses_anything_but_the_registered_executor(change):
    with pytest.raises(SafetyError):
        replace(LIVE, **change).validate()


def test_paper_cannot_borrow_the_live_ids():
    for client in (60, 140):
        with pytest.raises(SafetyError):
            PaperEndpoint("DU000000", client, 4002).validate()


def test_live_session_proof_allows_extra_accounts_but_pins_ours():
    LIVE.prove_session([ACCOUNT, "U7654321"], 60)
    with pytest.raises(SafetyError):
        LIVE.prove_session(["U7654321"], 60)
    with pytest.raises(SafetyError):
        LIVE.prove_session([ACCOUNT], 61)


def test_live_runtime_requires_host_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(safety, "LIVE_APPROVAL", tmp_path / "rs-live-approved")
    with pytest.raises(SafetyError):
        LIVE.runtime_guard()
    (tmp_path / "rs-live-approved").write_text("owner")
    LIVE.runtime_guard()


def test_live_executor_requires_claims_and_book(tmp_path):
    policy = Policy(spx_reserve=1, cash_buffer=1, daily_loss_limit=1)
    journal = Journal(tmp_path / "s.sqlite", policy.digest, "RSLIVE|")
    with pytest.raises(SafetyError):
        Executor(LIVE, policy, journal, LiveBroker())
    journal.close()


def test_journal_namespace_cannot_switch(tmp_path):
    Journal(tmp_path / "s.sqlite", "p").close()
    with pytest.raises(SafetyError):
        Journal(tmp_path / "s.sqlite", "p", "RSLIVE|")


# ---- arm / shadow --------------------------------------------------------

def test_unarmed_live_runs_in_shadow(live):
    live.arm.unlink()
    assert run(live.engine.enter(signal(), live.broker.snap, NOW)) is None
    assert live.broker.sent == [] and live.journal.rows("orders") == []
    assert events(live.journal, "shadow_entry")[0]["reason"] == "arm file absent"
    assert live.claims.held(NOW) == set()  # shadow never claims a name


@pytest.mark.parametrize("change", [
    dict(policy_hash="0" * 64), dict(valid_until="2026-11-18T00:00:00+00:00"),
    dict(account="U9999999"), dict(client_id=61), dict(armed_by=""), dict(schema="x"),
])
def test_any_arm_mismatch_disarms(live, change):
    write_arm(live.arm, live.policy, **change)
    assert run(live.engine.enter(signal(), live.broker.snap, NOW)) is None
    assert live.broker.sent == []


def test_armed_entry_claims_the_name_before_the_order(live):
    ref = run(live.engine.enter(signal(), live.broker.snap, NOW))
    assert ref.startswith("RSLIVE|") and live.broker.sent[0]["side"] == "SELL"
    assert live.broker.claimed_at_submit == [{"TEST"}]


# ---- other systems' names and orders -------------------------------------

def test_name_claimed_by_another_system_is_refused(live):
    ClaimBook(live.tmp / "claims", "ls-algo", ACCOUNT).claim("TEST", 1001, NOW)
    with pytest.raises(SafetyError, match="claimed by ls-algo"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))
    assert live.broker.sent == []


def test_foreign_working_order_or_missing_proof_is_refused(live):
    live.broker.snap["foreign_open_conids"] = [1001]
    with pytest.raises(SafetyError, match="another system"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))
    del live.broker.snap["foreign_open_conids"]
    with pytest.raises(SafetyError, match="open-order proof"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))
    assert live.broker.sent == []


@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "TSLA", "NVDA", "AMZN", "SPX"])
def test_other_products_symbols_are_never_rs_names(live, ticker):
    with pytest.raises(SafetyError, match="another system's product"):
        run(live.engine.enter(signal(ticker=ticker), live.broker.snap, NOW))


# ---- cushion ladder ------------------------------------------------------

def test_cushion_below_floor_blocks_entry(live):
    live.broker.snap["excess_liquidity"] = 2_000_000  # 0.20 < 0.30
    with pytest.raises(SafetyError, match="cushion below"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))


def test_entry_that_would_breach_the_floor_is_refused(live):
    live.broker.snap["excess_liquidity"] = 3_010_000  # 0.301 now, < 0.30 after stress
    with pytest.raises(SafetyError, match="leave the account cushion"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))


def test_cushion_flatten_covers_rs_first(live):
    run(live.engine.enter(signal(), live.broker.snap, NOW))
    live.broker.execute()
    live.broker.snap["excess_liquidity"] = 1_500_000  # 0.15 < 0.20
    run(live.engine.tick([], NOW))
    assert live.broker.sent[-1]["side"] == "BUY"
    assert events(live.journal, "cover_trigger")[-1]["reason"] == "cushion_flatten"
    assert live.journal.get("entry_halt") == "cushion_flatten"


def test_cushion_ladder_validation():
    with pytest.raises(SafetyError):
        Policy(spx_reserve=1, cash_buffer=1, daily_loss_limit=1, cushion_halt=0.2).validate()
    with pytest.raises(SafetyError):
        Policy(spx_reserve=1, cash_buffer=1, daily_loss_limit=1,
               cushion_halt=0.2, cushion_flatten=0.3).validate()


# ---- book margin: RS takes only what SPX's reserve leaves ------------------

def test_no_room_after_spx_claim(live):
    spx_file(live.spx_root, 4_990_000)
    with pytest.raises(SafetyError, match="book margin"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))


def test_spx_reserve_binds_even_when_spx_claims_little(live):
    spx_file(live.spx_root, 0)
    spx_file(live.spx_root, 1_995_000, product="qqq")  # 0.6 x 5M reserve + 1.995M
    with pytest.raises(SafetyError, match="book margin"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))


@pytest.mark.parametrize("damage", ["absent", "garbage", "yesterday"])
def test_no_valid_spx_file_means_no_entry(live, damage):
    path = live.spx_root / "2026-11-18" / "book_margin_spx.json"
    if damage == "absent":
        path.unlink()
    elif damage == "garbage":
        path.write_text("{")
    else:
        path.unlink()
        spx_file(live.spx_root, 0, today="2026-11-17")
        (live.spx_root / "2026-11-17" / "book_margin_spx.json").rename(path)
    with pytest.raises(SafetyError):
        run(live.engine.enter(signal(), live.broker.snap, NOW))
    assert live.broker.sent == []


def test_rs_yields_when_spx_needs_the_room(live):
    run(live.engine.enter(signal(), live.broker.snap, NOW))
    live.broker.execute()
    spx_file(live.spx_root, 4_999_000)
    run(live.engine.tick([], NOW))
    assert live.broker.sent[-1]["side"] == "BUY"
    assert events(live.journal, "cover_trigger")[-1]["reason"] == "book_margin_yield"


def test_rs_publishes_its_claim_outside_spx_tree(live):
    run(live.engine.enter(signal(), live.broker.snap, NOW))
    live.broker.execute()
    run(live.engine.tick([], NOW))
    own = json.loads((live.tmp / "rs-book" / "2026-11-18" / "book_margin_rs.json").read_text())
    assert own["schema"] == 1 and own["product"] == "rs" and own["claim"] > 0
    assert not (live.spx_root / "2026-11-18" / "book_margin_rs.json").exists()
    with pytest.raises(SafetyError):
        BookMargin(live.spx_root, live.spx_root, live.policy, 0.6)


# ---- claim release -------------------------------------------------------

def test_flat_name_released_only_after_next_close(live):
    run(live.engine.enter(signal(), live.broker.snap, NOW))
    live.broker.execute()
    live.journal.set("kill", True)
    run(live.engine.tick([], NOW))
    live.broker.execute(index=1, exec_id="cover1")
    run(live.engine.tick([], NOW))
    row = live.claims.load()["claims"]["TEST"]
    assert row["release_after"] == "2026-11-19T21:00:00+00:00"
    assert live.claims.held("2026-11-19T20:00:00+00:00") == {"TEST"}


# ---- CLI live config -----------------------------------------------------

FEED_URL = ("https://api.cloudflare.com/client/v4/accounts/x/r2/buckets/"
            "single-stock-reverse-splits-evidence/objects/collector-dashboard/operations.json")


def live_config(tmp=None, **policy):
    config = _live_config(**policy)
    if tmp is not None:  # real directories, so preflight's path checks can pass
        for key in ("claims_dir", "book_margin_root", "book_publish_root", "arm_file"):
            config["live"][key] = str(tmp / key)
        (tmp / "claims_dir").mkdir(exist_ok=True)
        (tmp / "book_margin_root").mkdir(exist_ok=True)
    return config


def _live_config(**policy):
    return {"endpoint": {"account": ACCOUNT, "client_id": 60, "port": 7496,
                         "host": "127.0.0.1", "mode": "live",
                         "deployment_role": "ny4_reverse_split_live"},
            "policy": {"spx_reserve": 1_000_000, "cash_buffer": 100_000,
                       "daily_loss_limit": 2500, "target_notional": 5000,
                       "max_name_notional": 5000, "max_gross_notional": 15000,
                       "max_names": 3, "cushion_halt": 0.3, "cushion_flatten": 0.2,
                       "pre_action_exit": True,
                       **policy},
            "live": {"claims_dir": "/var/lib/ib-account-claims",
                     "book_margin_root": "/home/spx/spx-0dte/data/live",
                     "book_publish_root": "/var/lib/rs-live/book",
                     "arm_file": "/etc/rs-live/ARM", "spx_book_reserve_fraction": 0.6}}


def test_cli_live_preflight_states_every_owner_decision(tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config(tmp_path)))
    assert cli.main(["preflight", "--config", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "live" and out["connection_opened"] is False
    config = live_config()
    del config["policy"]["max_gross_notional"], config["live"]["arm_file"]
    path.write_text(json.dumps(config))
    assert cli.main(["preflight", "--config", str(path)]) == 2
    reason = json.loads(capsys.readouterr().out)["reason"]
    assert "max_gross_notional" in reason and "arm_file" in reason


def test_cli_live_requires_pre_action_exit(tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config(pre_action_exit=False)))
    assert cli.main(["preflight", "--config", str(path)]) == 2
    assert "pre_action_exit" in capsys.readouterr().out


def test_cli_live_run_needs_its_own_flag(tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config()))
    assert cli.main(["run", "--config", str(path), "--connect-paper", "--evidence",
                     "e", "--operations-file", "o", "--state", str(tmp_path / "s")]) == 2
    assert "--connect-live is required" in capsys.readouterr().out


def test_unreadable_spx_tree_is_named_not_treated_as_absent(live, monkeypatch):
    book = live.engine.book
    found, nav = book.others(NOW, for_entry=False)  # one good read
    assert nav == 5_000_000
    day = live.spx_root / "2026-11-18"
    real = type(day).is_dir

    def denied(self):  # the spx home without the install's read grant
        if self == day:
            raise PermissionError(13, "Permission denied")
        return real(self)

    monkeypatch.setattr(type(day), "is_dir", denied)
    with pytest.raises(SafetyError, match="directory unreadable: PermissionError"):
        run(live.engine.enter(signal(), live.broker.snap, NOW))
    assert live.broker.sent == []
    # The yield check keeps the last good figures instead of crashing the tick.
    assert book.others(NOW, for_entry=False) == (found, nav)


def test_preflight_checks_live_paths_without_writing(tmp_path, capsys):
    path = tmp_path / "c.json"
    config = live_config(tmp_path)
    path.write_text(json.dumps(config))
    spx_file(tmp_path / "book_margin_root", 0)
    assert cli.main(["preflight", "--config", str(path)]) == 0
    paths = json.loads(capsys.readouterr().out)["paths"]
    assert paths["book_margin_root"] == "readable (2026-11-18: 1 claim files)"
    assert paths["claims_dir"] == "writable"
    assert paths["book_publish_root"].startswith("creatable under")
    assert paths["arm_file"] == "absent (shadow)"
    assert not (tmp_path / "book_publish_root").exists()
    # The NEWEST day must be readable too (the default ACL reaching new days).
    (tmp_path / "book_margin_root" / "2026-11-19" / "book_margin_spx.json").mkdir(parents=True)
    assert cli.main(["preflight", "--config", str(path)]) == 2
    assert "book_margin_root FAILED" in json.loads(capsys.readouterr().out)["reason"]
    config["live"]["book_margin_root"] = str(tmp_path / "missing")
    path.write_text(json.dumps(config))
    assert cli.main(["preflight", "--config", str(path)]) == 2
    assert "book_margin_root FAILED" in capsys.readouterr().out


def test_operations_check_reports_feed_age_without_a_connection(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timedelta, timezone

    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config(tmp_path)))
    ops = tmp_path / "ops.json"
    now = datetime.now(timezone.utc)
    ops.write_text(json.dumps({"generated_at": now.isoformat(), "candidates": [{}, {}]}))
    argv = ["operations-check", "--config", str(path), "--operations-file", str(ops)]
    assert cli.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fresh_within_120s"] is True and out["candidates"] == 2
    assert out["broker_connection_opened"] is False
    ops.write_text(json.dumps({"generated_at": (now - timedelta(seconds=300)).isoformat()}))
    assert cli.main(argv) == 3
    assert json.loads(capsys.readouterr().out)["fresh_within_120s"] is False
    monkeypatch.delenv("RS_OPERATIONS_READ_TOKEN", raising=False)
    assert cli.main(["operations-check", "--config", str(path), "--operations-url", FEED_URL]) == 2
    assert "RS_OPERATIONS_READ_TOKEN is not set" in capsys.readouterr().out


def test_live_run_refuses_feed_url_without_token(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("RS_OPERATIONS_READ_TOKEN", raising=False)
    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config(tmp_path)))
    state = tmp_path / "s.sqlite"
    assert cli.main(["run", "--config", str(path), "--connect-live", "--evidence", "e",
                     "--operations-url", FEED_URL, "--state", str(state)]) == 2
    assert "RS_OPERATIONS_READ_TOKEN is not set" in capsys.readouterr().out
    assert not state.exists()


def test_shipped_unit_reads_the_feed_url_from_a_required_env_file():
    from pathlib import Path
    unit = Path(cli.__file__).with_name("rs-live-executor.service").read_text()
    assert "EnvironmentFile=/etc/rs-live/executor.env" in unit
    assert "--operations-url ${RS_OPERATIONS_URL}" in unit
    assert "--operations-file" not in unit


def test_shipped_live_template_cannot_pass_preflight(capsys):
    from pathlib import Path
    template = Path(cli.__file__).with_name("config.live.example.json")
    assert cli.main(["preflight", "--config", str(template)]) == 2
    reason = json.loads(capsys.readouterr().out)["reason"]
    for field in ("explicit pinned U live account", ):
        assert field in reason


def test_publish_failure_halts_entries_but_keeps_protecting(live, monkeypatch):
    run(live.engine.enter(signal(), live.broker.snap, NOW))
    live.broker.execute()

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(live.engine.book, "publish", broken)
    run(live.engine.tick([signal(id="x")], NOW))  # must not raise
    assert live.journal.get("entry_halt") == "account_guard_publish:OSError"


@pytest.mark.parametrize("host", ["ny4", "spx-ny4", "FXVPS374628", "spx-ny4.localdomain"])
def test_paper_refuses_every_ny4_name(monkeypatch, host):
    import socket
    monkeypatch.setattr(socket, "gethostname", lambda: host)
    with pytest.raises(SafetyError):
        PaperEndpoint("DU000000", 171, 4002).runtime_guard()


def test_paper_refuses_a_host_with_the_spx_install(monkeypatch, tmp_path):
    import socket
    monkeypatch.setattr(socket, "gethostname", lambda: "laptop")
    monkeypatch.setattr(safety, "NY4_MARKERS", (tmp_path,))
    with pytest.raises(SafetyError):
        PaperEndpoint("DU000000", 171, 4002).runtime_guard()
    monkeypatch.setattr(safety, "NY4_MARKERS", (tmp_path / "absent",))
    PaperEndpoint("DU000000", 171, 4002).runtime_guard()
