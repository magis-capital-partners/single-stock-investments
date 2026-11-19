"""RS evidence producers: parsers, refusal rules and the executor round trip.

No socket is opened: every network edge is a fake, and the autouse guard
fails any real connection. Box R's own captured exchange files are reused as
fixtures so both hosts are tested on the same bytes.
"""

import asyncio
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from _system.trading.rs_evidence import reviews as reviews_mod
from _system.trading.rs_evidence import sources
from _system.trading.rs_evidence.borrow import build_borrow
from _system.trading.rs_evidence.eligibility import build_eligibility
from _system.trading.rs_evidence.identity import build_identities, earliest_action_day
from _system.trading.rs_evidence.reviews import Reviews
from _system.trading.rs_evidence.runner import Fetchers, Producers, load_config
from _system.trading.rs_evidence.store import EvidenceStore
from _system.trading.rs_paper_executor.engine import Executor
from _system.trading.rs_paper_executor.ibkr import PaperIBKR
from _system.trading.rs_paper_executor.inbox import proposals
from _system.trading.rs_paper_executor.safety import SafetyError, fresh, integer, number

ROOT = Path(__file__).resolve().parents[3]
BOX_R = ROOT / "dashboard/cloudflare/reverse-split-live/fixtures"
NOW = "2026-11-18T15:00:00+00:00"  # 10:00 ET, Wednesday
SHA_A = "a" * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original = socket.socket.connect

    def forbidden(*args, **kwargs):
        import sys

        caller = sys._getframe(1).f_code
        if (
            caller.co_name in ("socketpair", "_fallback_socketpair")
            and caller.co_filename == socket.__file__
        ):
            return original(*args, **kwargs)
        raise AssertionError("test attempted a real socket connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


# ------------------------------------------------------------------ fixtures


def ibkr_bytes(rows=None, *, bof="2026.11.18|09:45:00", count=None):
    rows = rows if rows is not None else [
        "TEST|USD|TEST CO|1001|US0000000001|-20.5|25.0|>10000000|",
        "DUAL|USD|DUAL CO A|2001|US0000000002|0|1.0|5000|",
        "DUAL|USD|DUAL CO B|2002|US0000000003|0|1.0|5000|",
        "NARATE|USD|NA RATE|3001|US0000000004|NA|NA|0|",
        "ADSX|USD|ADS CO|4001|US0000000005|0|3.0|900|",
    ]
    lines = ["#BOF|" + bof, "#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|", *rows]
    lines.append("#EOF|" + str(len(rows) if count is None else count))
    return ("\n".join(lines) + "\n").encode()


def filler(n=1000, prefix="F"):
    return [f"{prefix}{i:04d}" for i in range(n)]


def nasdaq_listed(extra=()):
    head = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
    rows = [f"{s}|{s} Inc. - Common Stock|S|N|N|100|N|N" for s in filler()]
    rows += list(extra) or [
        "TEST|Test Co. - Common Stock|S|N|D|100|N|N",
        "ADSX|ADS Co. - American Depositary Shares|S|N|N|100|N|N",
        "TESTW|Test Co. - Warrant|S|N|N|100|N|N",
        "DUAL|Dual Co. - Class A Common Stock|S|N|N|100|N|N",
        "ODDX|Odd Co.|S|N|N|100|N|N",
    ]
    return "\n".join([head, *rows, "File Creation Time: 1118202608:00|||||||"]) + "\n"


def other_listed():
    head = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
    rows = [f"{s}|{s} Corp Common Stock|A|{s}|N|100|N|{s}" for s in filler(prefix="G")]
    rows.append("AMX|Amx Corp. Common Stock|A|AMX|N|100|N|AMX")
    return "\n".join([head, *rows, "File Creation Time: 1118202608:00|||||||"]) + "\n"


def sec_bytes(extra=None):
    data = [[100000 + i, s, s, "Nasdaq"] for i, s in enumerate(filler(prefix="H"))]
    data += extra if extra is not None else [
        [12345, "Test Co", "TEST", "Nasdaq"],
        [22222, "Dual Co", "DUAL", "Nasdaq"],
        [44444, "ADS Co", "ADSX", "Nasdaq"],
        [55555, "Amx Corp", "AMX", "NYSE"],
    ]
    return json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": data}).encode()


def refs(now=NOW):
    return {
        "sec": sources.parse_sec_tickers(sec_bytes(), now),
        "listings": [
            sources.parse_symbol_directory(nasdaq_listed(), "nasdaqlisted", now),
            sources.parse_symbol_directory(other_listed(), "otherlisted", now),
        ],
        "ibkr": sources.parse_ibkr_shortstock(ibkr_bytes(), now),
    }


def candidate(**changes):
    row = {
        "id": "sec:one",
        "ticker": "TEST",
        "cik": "12345",
        "status": "scheduled",
        "checks": {"announcement": {"state": "pass"}, "repeat": {"state": "pass"}},
        "implementation_conditions": [],
        "source_urls": [{"url": "https://www.sec.gov/x.htm", "sha256": SHA_A}],
        "analyzed_at": "2026-11-18T14:59:20Z",
        "published_at": "2026-11-18T14:59:00Z",
        "publication_clock": "timestamp",
        "first_seen_at": "2026-11-18T14:59:10Z",
        "effective_date": "2026-11-25",
        "legal_effective_date": "2026-11-24",
        "trading_date": "2026-11-25",
        "ordinal_min": 2,
        "financials": {"score": 34, "signal_count": 5, "period": "2026-06-30"},
    }
    row.update(changes)
    return row


def review_row(**changes):
    row = {
        "schema": reviews_mod.SCHEMA,
        "candidate_id": "sec:one",
        "cik": "12345",
        "ticker": "TEST",
        "action_source_sha256": SHA_A,
        "ratio": 10,
        "action_day": "2026-11-24",
        "conditions_resolved": True,
        "reviewed_by": "owner",
        "reviewed_at": "2026-11-18T14:59:50Z",
    }
    row.update(changes)
    return row


def status_bytes(symbols, *, current="2026-11-18T14:59:55+00:00", source="licensed:test", gapless=True):
    return json.dumps(
        {
            "schema": sources.STATUS_SCHEMA,
            "source": source,
            "gapless": gapless,
            "current_as_of": current,
            "coverage": ["XNAS"],
            "symbols": symbols,
        }
    ).encode()


# --------------------------------------------------------------------- store


def test_store_replaces_only_its_own_section(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.json")
    store.write_section("borrow", {"1": {"conid": 1}}, {"producer": "borrow"})
    store.write_section("eligibility", {"1": {"conid": 1}}, {"producer": "eligibility"})
    store.write_section("borrow", {"2": {"conid": 2}}, {"producer": "borrow"})
    data = json.loads((tmp_path / "evidence.json").read_text())
    assert data["schema"] == "rs_paper_reviewed_evidence.v1"
    assert data["borrow"] == {"2": {"conid": 2}}
    assert data["eligibility"] == {"1": {"conid": 1}}
    assert data["identities"] == {}
    assert not list(tmp_path.glob("*.tmp-*"))
    with pytest.raises(SafetyError):
        store.write_section("orders", {}, {})


def test_store_replaces_a_corrupt_file_rather_than_trusting_it(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text("{not json")
    EvidenceStore(path).write_section("borrow", {}, {})
    assert json.loads(path.read_text())["eligibility"] == {}


def test_store_archives_proofs_by_hash(tmp_path):
    store = EvidenceStore(tmp_path / "e.json", tmp_path / "archive")
    digest = store.archive({"b": 1, "a": 2})
    assert (tmp_path / "archive" / digest).read_bytes() == b'{"a":2,"b":1}'


# ------------------------------------------------------------------- parsers


def test_ibkr_file_parses_by_conid_and_refuses_truncation_and_future():
    parsed = sources.parse_ibkr_shortstock(ibkr_bytes(), NOW)
    test = parsed["by_conid"][1001][0]
    assert parsed["as_of"] == "2026-11-18T14:45:00+00:00"  # #BOF read as Eastern
    assert test["apr"] == 0.25 and test["available_shares"] == 10_000_000
    assert test["available_at_least"] is True and test["currency"] == "USD"
    assert parsed["by_conid"][3001][0]["apr"] is None
    with pytest.raises(SafetyError):
        sources.parse_ibkr_shortstock(ibkr_bytes(count=9), NOW)
    with pytest.raises(SafetyError):
        sources.parse_ibkr_shortstock(ibkr_bytes(bof="2026.11.18|11:00:00"), NOW)


def test_halt_feed_box_r_fixture_and_halt_state():
    data = (BOX_R / "nasdaq-halts.rss").read_bytes()
    observed = "2026-11-09T17:05:10+00:00"
    feed = sources.parse_halt_feed(data, observed)
    assert feed["as_of"] == "2026-11-09T17:04:51+00:00" and len(feed["items"]) == 56
    # NWGL paused 10:42:52 ET, trading resumed 10:47:52 ET (15:47:52Z).
    assert sources.halt_state(feed, "NWGL", observed)[0] is False
    early = dict(feed, as_of="2026-11-09T15:45:00+00:00")
    assert sources.halt_state(early, "NWGL", "2026-11-09T15:45:00+00:00")[0] is True
    assert sources.halt_state(feed, "ZZZZ", observed) == (False, None)
    with pytest.raises(SafetyError):
        sources.parse_halt_feed(data, "2026-11-09T17:10:00+00:00")  # stale
    with pytest.raises(SafetyError):
        sources.parse_halt_feed(data.replace(b"<ndaq:numItems>56", b"<ndaq:numItems>57"), observed)
    with pytest.raises(SafetyError):
        sources.parse_halt_feed(b'<!DOCTYPE x [<!ENTITY a "b">]><rss/>', observed)


def test_restriction_file_proves_restriction_only():
    text = (BOX_R / "nasdaq-ssr-carry.txt").read_text(encoding="utf-8-sig")
    listing = sources.parse_shorthalts(text, "2026-11-09", "2026-11-09T14:00:00+00:00")
    assert "KRUS" in listing["symbols"] and listing["intraday_clearance"] is False
    assert listing["as_of"] == "2026-11-09T09:15:11+00:00"
    with pytest.raises(SafetyError):
        sources.parse_shorthalts(text, "2026-11-10", "2026-11-10T14:00:00+00:00")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Test Co. - Common Stock", "CS"),
        ("Hub Ltd. - Ordinary Shares", "CS"),
        ("Dual Co. - Class A Common Stock", "CS"),
        ("Ads Co. - American Depositary Shares", "NOT_COMMON"),
        ("Test Co. - Warrant", "NOT_COMMON"),
        ("Acq Corp - Units", "NOT_COMMON"),
        ("Bank - 6.5% Series A Preferred", "NOT_COMMON"),
        ("Odd Co.", "UNRESOLVED"),
        # Live SymDir names, 2026-11-18.
        ("Globavend Holdings Limited - Ord Shares", "CS"),
        ("ReTo Eco-Solutions, Inc. - Class A Shares", "CS"),
        ("Nanobiotix S.A. - ADSs", "NOT_COMMON"),
        ("Silence Therapeutics Plc - American Depository Share", "NOT_COMMON"),
        ("Nuveen New York Quality Municipal Income Fund Common Stock", "NOT_COMMON"),
        ("Carlyle Secured Lending, Inc. - Closed End Fund", "NOT_COMMON"),
        ("CarMax Inc", "UNRESOLVED"),
        ("Fundamental Global Inc. - Common Stock", "CS"),
    ],
)
def test_security_class_names_common_shares_only(name, expected):
    row = {"security_name": name, "test_issue": False, "etf": False}
    assert sources.security_class(row) == expected
    assert sources.security_class({**row, "etf": True}) in ("ETF",)
    assert sources.security_class(None) == "UNLISTED"


def test_market_status_reader_requires_owner_approval_gapless_and_fresh():
    ok = sources.parse_market_status(
        status_bytes({"TEST": {"halted": False, "ssr": False}}),
        NOW,
        allowed_sources={"licensed:test"},
        max_age_seconds=30,
    )
    assert ok["symbols"]["TEST"] == {"halted": False, "ssr": False}
    for data, allowed in (
        (status_bytes({}), set()),
        (status_bytes({}, gapless=False), {"licensed:test"}),
        (status_bytes({}, current="2026-11-18T14:59:00+00:00"), {"licensed:test"}),
        (status_bytes({"TEST": {"ssr": 0}}), {"licensed:test"}),
    ):
        with pytest.raises(SafetyError):
            sources.parse_market_status(data, NOW, allowed_sources=allowed, max_age_seconds=30)


def test_https_get_refuses_before_any_socket():
    with pytest.raises(SafetyError):
        sources.https_get("https://evil.invalid/x", user_agent="Org ops@example.invalid")
    with pytest.raises(SafetyError):
        sources.https_get("http://www.sec.gov/x", user_agent="Org ops@example.invalid")
    with pytest.raises(SafetyError):
        sources.https_get(sources.SEC_TICKERS_URL, user_agent=None)


# ------------------------------------------------------------------ identity


def test_identity_without_review_is_written_unverified_with_proposed_terms():
    rows, _ = build_identities({"candidates": [candidate()]}, refs(), Reviews([]), NOW, terms_mode="owner_review")
    row = rows["TEST"]
    assert row["verified"] is False and row["conditions_resolved"] is False
    assert row["refusals"] == ["owner_review_required"]
    assert row["proposed_terms"] == {"ratio": None, "action_day": "2026-11-24", "conditions_resolved": True}
    assert row["conid"] == 1001 and row["type"] == "CS" and row["primary_exchange"] == "NASDAQ"
    assert row["action_source_sha256"] == SHA_A


def test_identity_with_bound_review_is_verified():
    rows, _ = build_identities(
        {"candidates": [candidate()]}, refs(), Reviews([review_row()]), NOW, terms_mode="owner_review"
    )
    row = rows["TEST"]
    assert row["verified"] is True and row["conditions_resolved"] is True
    assert row["ratio"] == 10 and row["action_day"] == "2026-11-24"
    assert row["terms_basis"] == "owner_review" and row["at"] == NOW
    assert row["valid_until"] == "2026-11-19T15:00:00+00:00"  # 24 h
    # An action day sooner than 24 h ends validity at its start (Eastern).
    rows, _ = build_identities(
        {"candidates": [candidate()]}, refs(), Reviews([review_row(action_day="2026-11-19")]),
        NOW, terms_mode="owner_review",
    )
    assert rows["TEST"]["valid_until"] == "2026-11-19T00:00:00-05:00"


@pytest.mark.parametrize(
    "change",
    [
        {"action_source_sha256": "c" * 64},
        {"cik": "99999"},
        {"candidate_id": "sec:other"},
    ],
)
def test_review_must_bind_candidate_cik_and_source_hash(change):
    rows, _ = build_identities(
        {"candidates": [candidate()]}, refs(), Reviews([review_row(**change)]), NOW, terms_mode="owner_review"
    )
    assert rows["TEST"]["verified"] is False


def test_review_conid_must_match_reference():
    rows, _ = build_identities(
        {"candidates": [candidate()]}, refs(), Reviews([review_row(conid=7)]), NOW, terms_mode="owner_review"
    )
    assert "review_conid_differs_from_reference" in rows["TEST"]["refusals"]


def test_box_r_auto_needs_an_exported_single_ratio_and_no_conditions():
    ops = {"candidates": [candidate()]}
    rows, _ = build_identities(ops, refs(), Reviews([]), NOW, terms_mode="box_r_auto")
    assert rows["TEST"]["refusals"] == ["ratio_not_exported_by_box_r"]
    rows, _ = build_identities(
        {"candidates": [candidate(ratio=20, ratio_candidates=[20])]}, refs(), None, NOW, terms_mode="box_r_auto"
    )
    assert rows["TEST"]["verified"] is True and rows["TEST"]["ratio"] == 20
    rows, _ = build_identities(
        {"candidates": [candidate(ratio=20, ratio_candidates=[20, 25])]}, refs(), None, NOW, terms_mode="box_r_auto"
    )
    assert rows["TEST"]["verified"] is False
    rows, _ = build_identities(
        {"candidates": [candidate(ratio=20, implementation_conditions=["subject to approval"])]},
        refs(), None, NOW, terms_mode="box_r_auto",
    )
    assert "box_r_checks_or_conditions_open" in rows["TEST"]["refusals"]


@pytest.mark.parametrize(
    "ticker,cik,refusal",
    [
        ("TEST", "11111", "sec_ticker_cik_mismatch"),
        ("DUAL", "22222", "ibkr_conid_ambiguous"),
        ("ADSX", "44444", "security_class_not_common"),
        ("AMX", "55555", "ibkr_conid_missing"),
    ],
)
def test_identity_cross_checks_refuse(ticker, cik, refusal):
    rows, _ = build_identities(
        {"candidates": [candidate(ticker=ticker, cik=cik)]}, refs(), None, NOW, terms_mode="box_r_auto"
    )
    assert refusal in rows[ticker]["refusals"] and rows[ticker]["verified"] is False


def test_identity_skips_old_unscheduled_and_unsourced_candidates():
    ops = {
        "candidates": [
            candidate(first_seen_at="2026-11-18T13:00:00Z"),
            candidate(id="x", ticker="DUAL", cik="22222", status="proposed"),
            candidate(id="y", ticker="AMX", cik="55555", source_urls=[]),
        ]
    }
    rows, _ = build_identities(ops, refs(), None, NOW, terms_mode="owner_review")
    assert rows == {}


def test_identity_at_is_kept_while_content_is_unchanged():
    ops = {"candidates": [candidate()]}
    first, _ = build_identities(ops, refs(), Reviews([review_row()]), NOW, terms_mode="owner_review")
    later = "2026-11-18T15:05:00+00:00"
    second, _ = build_identities(
        ops, refs(later), Reviews([review_row()]), later, terms_mode="owner_review", previous=first
    )
    assert second["TEST"]["at"] == NOW  # IBKR file refresh is not a new mapping
    changed, _ = build_identities(
        ops, refs(later), Reviews([review_row(ratio=12, reviewed_at="2026-11-18T15:04:00Z")]),
        later, terms_mode="owner_review", previous=second,
    )
    assert changed["TEST"]["at"] == later and changed["TEST"]["ratio"] == 12


def test_earliest_action_day_is_the_safe_side():
    assert earliest_action_day(candidate()) == "2026-11-24"
    assert earliest_action_day(candidate(effective_date=None, legal_effective_date=None, trading_date=None)) is None


# -------------------------------------------------------------------- borrow


def test_borrow_rows_carry_ibkr_clock_and_never_invent_inventory():
    ibkr = sources.parse_ibkr_shortstock(ibkr_bytes(), NOW)
    rows, report = build_borrow(ibkr, {1001: "TEST", 3001: "NARATE", 9999: "GONE", 4001: "WRONG"}, NOW)
    assert set(rows) == {"1001"}
    row = rows["1001"]
    assert row["conid"] == 1001 and row["at"] == "2026-11-18T14:45:00+00:00"
    assert row["apr"] == 0.25 and row["locate_approved"] is False
    missing = {r["conid"]: r["missing"] for r in report if "missing" in r}
    assert missing == {3001: "rate_or_inventory_na", 9999: "not_in_public_file", 4001: "symbol_differs"}


# --------------------------------------------------------------- eligibility


def halt_feed(items=(), as_of="2026-11-18T14:59:50+00:00"):
    return {"as_of": as_of, "items": list(items), "complete": True}


def restriction(symbols):
    return {"as_of": "2026-11-18T09:15:00+00:00", "symbols": symbols, "source_url": "u", "source_sha256": "s", "day": "2026-11-18"}


def test_without_an_intraday_ssr_source_every_row_is_incomplete():
    rows, summary = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed(), halt_feed_clears=True)
    row = rows["1001"]
    assert row["complete"] is False and row["source_verified"] is False
    assert row["halted"] is False and row["ssr"] is None
    assert row["halt_complete"] is True and row["halt_at"] == "2026-11-18T14:59:50+00:00"
    assert row["missing"] == ["intraday_ssr_clearance_source_absent"]
    assert summary == {"complete": 0, "incomplete": 1}


def test_daily_file_absence_never_clears_but_listing_restricts():
    rows, _ = build_eligibility(
        {1001: "TEST", 2001: "KRUS"}, NOW, halt_feed=halt_feed(), halt_feed_clears=True,
        restrictions=[restriction({"KRUS": "11/17/2026 3:59:00 PM"})],
    )
    assert rows["1001"]["ssr"] is None and rows["1001"]["complete"] is False
    assert rows["2001"]["ssr"] is True and rows["2001"]["complete"] is True
    assert rows["2001"]["at"] == "2026-11-18T09:15:00+00:00"  # the oldest input decides


def test_halt_feed_absence_clears_only_when_owner_approved():
    status = sources.parse_market_status(
        status_bytes({"TEST": {"ssr": False}}), NOW, allowed_sources={"licensed:test"}, max_age_seconds=30
    )
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed(), status=status)
    assert rows["1001"]["halted"] is None
    assert "halt_clearance_source_not_approved" in rows["1001"]["missing"]
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed(), halt_feed_clears=True, status=status)
    row = rows["1001"]
    assert row["complete"] is True and row["source_verified"] is True
    assert row["halted"] is False and row["ssr"] is False
    assert row["at"] == "2026-11-18T14:59:50+00:00"


def test_a_listed_halt_restricts_and_a_stale_feed_is_unknown():
    event = {"ticker": "TEST", "halt_at": "2026-11-18T14:58:00+00:00", "resume_at": None, "market": "NASDAQ", "reason": "T1"}
    rows, _ = build_eligibility({1001: "TEST"}, NOW, halt_feed=halt_feed([event]))
    assert rows["1001"]["halted"] is True
    rows, _ = build_eligibility(
        {1001: "TEST"}, NOW, halt_feed=halt_feed(as_of="2026-11-18T14:59:00+00:00"), halt_feed_clears=True
    )
    assert rows["1001"]["halted"] is None and "halt_feed_stale_or_unavailable" in rows["1001"]["missing"]


def test_licensed_status_alone_can_clear_both():
    status = sources.parse_market_status(
        status_bytes({"TEST": {"halted": False, "ssr": False}, "SSRX": {"halted": False, "ssr": True}}),
        NOW, allowed_sources={"licensed:test"}, max_age_seconds=30,
    )
    rows, _ = build_eligibility({1001: "TEST", 2: "SSRX", 3: "ABSENT"}, NOW, status=status)
    assert rows["1001"]["complete"] is True and rows["1001"]["at"] == "2026-11-18T14:59:55+00:00"
    assert rows["2"]["ssr"] is True
    assert rows["3"]["complete"] is False  # a symbol the handler does not list is unknown


# ------------------------------------------- round trip through the executor


def write_config(tmp_path, **changes):
    ops = tmp_path / "operations.json"
    ops.write_text(json.dumps({"generated_at": NOW, "candidates": [candidate()]}))
    claims = tmp_path / "reverse-split.json"
    claims.write_text(json.dumps({
        "schema": "ib_account_symbol_claims.v1", "system": "reverse-split", "account": "U1",
        "generated_at": NOW, "claims": {"HELD": {"conid": 5005, "sec_type": "STK", "claimed_at": NOW, "release_after": None}},
    }))
    config = {
        "evidence": str(tmp_path / "evidence.json"),
        "archive_dir": str(tmp_path / "archive"),
        "operations_file": str(ops),
        "operations_mirror": str(tmp_path / "mirror" / "operations.json"),
        "claims_file": str(claims),
        "reviews": str(tmp_path / "reviews.jsonl"),
        "user_agent": "Org ops@example.invalid",
        "eligibility": {
            "halt_feed_clears": True,
            "market_status_file": str(tmp_path / "status.json"),
            "approved_status_sources": ["licensed:test"],
        },
    }
    config.update(changes)
    path = tmp_path / "producers.json"
    path.write_text(json.dumps(config))
    return path


def fake_fetchers(now=NOW, fail_halts=False):
    halts = (
        '<rss version="2.0" xmlns:ndaq="http://www.nasdaqtrader.com/"><channel>'
        "<pubDate>Wed, 18 Nov 2026 14:59:50 GMT</pubDate><ndaq:numItems>0</ndaq:numItems>"
        "</channel></rss>"
    ).encode()
    restriction_text = (
        "Symbol,Security Name,Market Category,Trigger Time\n"
        'HELD,"Held Co",S,11/17/2026 3:00:00 PM\n20261118041500\n'
    ).encode()

    def https(url):
        if url == sources.SEC_TICKERS_URL:
            return sec_bytes(), now
        if url.endswith("nasdaqlisted.txt"):
            return nasdaq_listed().encode(), now
        if url.endswith("otherlisted.txt"):
            return other_listed().encode(), now
        if url == sources.HALT_URL:
            if fail_halts:
                raise OSError("feed down")
            return halts, now
        if "shorthalts" in url:
            return restriction_text, now
        raise AssertionError("unexpected url " + url)

    return Fetchers(https=https, ibkr=lambda: (ibkr_bytes(), now), clock=lambda: now)


def test_round_trip_through_the_executor_consumers(tmp_path):
    config = load_config(write_config(tmp_path))
    Path(config["eligibility"]["market_status_file"]).write_bytes(
        status_bytes({"TEST": {"halted": False, "ssr": False}})
    )
    reviews_mod.append(config["reviews"], review_row())
    producers = Producers(config, fake_fetchers(), in_session=lambda now: True)
    ran = producers.step(NOW)
    assert ran == ["references", "ibkr_file", "identity", "borrow", "halt_feed", "restriction_file", "eligibility"]
    evidence = json.loads(Path(config["evidence"]).read_text())

    # 1. Identity: the executor's own inbox turns it into a proposal.
    operations = json.loads(Path(config["operations_file"]).read_text())
    rows = proposals(operations, evidence, NOW)
    assert len(rows) == 1 and rows[0]["expected_conid"] == 1001
    assert rows[0]["identity_verified"] is True and rows[0]["conditions_resolved"] is True
    assert rows[0]["primary_exchange"] == "NASDAQ" and rows[0]["ratio"] == 10
    assert json.loads(Path(config["operations_mirror"]).read_text()) == operations

    # 2. Borrow: exactly the checks engine.enter() applies to PaperIBKR.borrow's row.
    loan = evidence["borrow"]["1001"]
    assert loan["conid"] == 1001
    fresh(loan["at"], NOW, 1800)
    assert number(loan["apr"], minimum=0) == 0.25 and integer(loan["available_shares"]) > 0
    assert "5005" not in evidence["borrow"]  # held name not in the public file: no row, not zero

    # 3. Eligibility: PaperIBKR.eligibility then Executor.eligibility accept it.
    broker = SimpleNamespace(evidence=lambda: evidence, tickers={})
    proof = asyncio.run(PaperIBKR.eligibility(broker, 1001))
    Executor.eligibility(SimpleNamespace(policy=SimpleNamespace(evidence_age_seconds=30)), proof, NOW, 1001)
    held = asyncio.run(PaperIBKR.eligibility(broker, 5005))
    assert held["ssr"] is True and held["halted"] is False
    with pytest.raises(SafetyError):
        Executor.eligibility(SimpleNamespace(policy=SimpleNamespace(evidence_age_seconds=30)), held, NOW, 5005)
    # 31 s after its oldest deciding input (14:59:55) the row is refused for age.
    with pytest.raises(SafetyError):
        Executor.eligibility(
            SimpleNamespace(policy=SimpleNamespace(evidence_age_seconds=30)), proof, "2026-11-18T15:00:26+00:00", 1001
        )


def test_round_trip_without_an_ssr_source_refuses_at_eligibility(tmp_path):
    config = load_config(write_config(tmp_path, eligibility={"halt_feed_clears": True}))
    reviews_mod.append(config["reviews"], review_row())
    Producers(config, fake_fetchers(), in_session=lambda now: True).step(NOW)
    evidence = json.loads(Path(config["evidence"]).read_text())
    proof = asyncio.run(PaperIBKR.eligibility(SimpleNamespace(evidence=lambda: evidence, tickers={}), 1001))
    with pytest.raises(SafetyError, match="fresh eligibility source required"):
        Executor.eligibility(SimpleNamespace(policy=SimpleNamespace(evidence_age_seconds=30)), proof, NOW, 1001)
    assert evidence["producers"]["eligibility"]["intraday_ssr_clearance"] is False


def test_failures_withdraw_eligibility_but_keep_identity_and_borrow(tmp_path):
    config = load_config(write_config(tmp_path))
    Path(config["eligibility"]["market_status_file"]).write_bytes(
        status_bytes({"TEST": {"halted": False, "ssr": False}})
    )
    reviews_mod.append(config["reviews"], review_row())
    producers = Producers(config, fake_fetchers(), in_session=lambda now: True)
    producers.step(NOW)
    later = "2026-11-18T15:10:00+00:00"
    Path(config["operations_file"]).unlink()
    producers.fetchers = fake_fetchers(later, fail_halts=True)
    producers.fetchers.ibkr = lambda: (_ for _ in ()).throw(OSError("ftp down"))
    producers.state.due.clear()
    producers.step(later)
    evidence = json.loads(Path(config["evidence"]).read_text())
    assert evidence["identities"]["TEST"]["verified"] is True
    assert evidence["producers"]["identities"]["status"] == "degraded_kept_previous"
    assert "1001" in evidence["borrow"]
    assert evidence["eligibility"]["1001"]["complete"] is False  # withdrawn, not left to age


def test_exchange_pages_are_not_polled_outside_the_session(tmp_path):
    config = load_config(write_config(tmp_path))
    producers = Producers(config, fake_fetchers(), in_session=lambda now: False)
    assert producers.step(NOW) == ["references", "ibkr_file", "identity", "borrow"]


def test_review_cli_binds_the_current_candidate(tmp_path, capsys):
    from _system.trading.rs_evidence.__main__ import main

    path = write_config(tmp_path)
    assert main(["review", "--config", str(path), "--candidate", "sec:one", "--ratio", "10",
                 "--action-day", "2026-11-24", "--by", "owner"]) == 0
    line = json.loads(Path(tmp_path / "reviews.jsonl").read_text().splitlines()[0])
    assert line["action_source_sha256"] == SHA_A and line["cik"] == "12345"
    assert main(["review", "--config", str(path), "--candidate", "sec:none", "--ratio", "10",
                 "--action-day", "2026-11-24", "--by", "owner"]) == 2


def test_config_refuses_an_eligibility_age_the_executor_would_reject(tmp_path):
    path = write_config(tmp_path, eligibility={"max_age_seconds": 60})
    with pytest.raises(SafetyError):
        load_config(path)


def test_config_refuses_polling_faster_than_the_sources_allow(tmp_path):
    with pytest.raises(SafetyError, match="halt_feed"):
        load_config(write_config(tmp_path, cadence_seconds={"halt_feed": 15}))


def test_an_unreadable_claims_file_keeps_the_last_held_names(tmp_path):
    config = load_config(write_config(tmp_path))
    producers = Producers(config, fake_fetchers(), in_session=lambda now: True)
    assert producers.watch({"identities": {}}) == {5005: "HELD"}
    Path(config["claims_file"]).write_text("{torn")
    assert producers.watch({"identities": {}}) == {5005: "HELD"}


def test_operations_url_comes_from_the_executor_environment(tmp_path, monkeypatch):
    path = write_config(tmp_path, operations_file=None)
    monkeypatch.delenv("RS_OPERATIONS_URL", raising=False)
    with pytest.raises(SafetyError, match="operations source"):
        load_config(path)
    url = ("https://api.cloudflare.com/client/v4/accounts/x/r2/buckets/"
           "single-stock-reverse-splits-evidence/objects/collector-dashboard/operations.json")
    monkeypatch.setenv("RS_OPERATIONS_URL", url)
    assert load_config(path)["operations_url"] == url
