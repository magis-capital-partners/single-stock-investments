"""The ib_account_symbol_claims.v1 reader: what counts as a claim, and what fails closed.

reverse-split ("RS") names the positions it holds in this shared account in
``<IB_ACCOUNT_SYMBOL_CLAIMS_DIR>/reverse-split.json``. These tests pin the
contract: release only by a past ``release_after``, never by age; conid before
symbol; an unreadable file is never "no claims".
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves import symbol_claims as sc  # noqa: E402
from _system.trading.sleeves.symbol_claims import (  # noqa: E402
    CLAIMS_DIR_ENV,
    LAST_GOOD_DIR_ENV,
    SCHEMA,
    claim_refusal,
    claims_from_summary,
    claims_moment,
    load_symbol_claims,
)

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)


def claims_file(directory: Path, claims: dict | None = None, **overrides) -> Path:
    payload = {
        "schema": SCHEMA, "system": "reverse-split", "account": "U805366",
        "generated_at": "2026-11-18T14:59:00Z",
        "claims": claims if claims is not None else {
            "ABCD": {"conid": 123, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z", "release_after": None},
        },
        **overrides,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "reverse-split.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in (CLAIMS_DIR_ENV, LAST_GOOD_DIR_ENV, "IB_ACCOUNT_SYMBOL_CLAIMS_ACCOUNT", "IBKR_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    sc._LAST_GOOD.clear()
    yield
    sc._LAST_GOOD.clear()


def load(directory, **kw):
    return load_symbol_claims(directory=directory, **kw).at(NOW)


# --------------------------------------------------------------- configuration

def test_no_directory_anywhere_means_rs_is_not_deployed_here(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "DEFAULT_CLAIMS_DIR", str(tmp_path / "absent"))
    got = load_symbol_claims()
    assert (got.status, got.configured, got.unreadable, got.claims) == ("not_configured", False, False, ())
    assert claim_refusal({"symbol": "ABCD", "sec_type": "STK"}, got) is None


def test_the_env_var_names_the_directory(monkeypatch, tmp_path):
    claims_file(tmp_path)
    monkeypatch.setenv(CLAIMS_DIR_ENV, str(tmp_path))
    got = load_symbol_claims().at(NOW)
    assert (got.status, got.source, got.account) == ("ok", "file", "U805366")
    assert [c.symbol for c in got.active()] == ["ABCD"]


def test_an_existing_default_directory_is_configured_even_without_the_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "DEFAULT_CLAIMS_DIR", str(tmp_path))
    # RS's directory exists but its file does not: unreadable, never "no claims".
    got = load_symbol_claims()
    assert got.unreadable and "FileNotFoundError" in got.error


# -------------------------------------------------------------------- activity

def test_a_claim_is_active_until_release_after_has_passed(tmp_path):
    claims_file(tmp_path, {
        "OPEN": {"conid": 1, "sec_type": "STK", "claimed_at": "2026-11-01T15:00:00Z", "release_after": None},
        "LATER": {"conid": 2, "sec_type": "STK", "claimed_at": "2026-11-01T15:00:00Z", "release_after": "2026-11-18T16:00:00Z"},
        "GONE": {"conid": 3, "sec_type": "STK", "claimed_at": "2026-11-01T15:00:00Z", "release_after": "2026-11-18T14:00:00Z"},
    })
    assert sorted(c.symbol for c in load(tmp_path).active()) == ["LATER", "OPEN"]


def test_age_never_releases_a_claim(tmp_path):
    claims_file(tmp_path, generated_at="2025-01-02T00:00:00Z", claims={
        "OLD": {"conid": 9, "sec_type": "STK", "claimed_at": "2025-01-01T00:00:00Z", "release_after": None},
    })
    got = load(tmp_path)
    assert got.status == "ok" and [c.symbol for c in got.active()] == ["OLD"]


def test_a_statement_is_judged_at_the_start_of_its_session_date(tmp_path):
    # RS covered and released ABCD at 10:05 ET on the 18th. The 17th's statement
    # still held the short, so republishing it must still say RS.
    claims_file(tmp_path, {
        "ABCD": {"conid": 123, "sec_type": "STK", "claimed_at": "2026-11-10T15:00:00Z",
                 "release_after": "2026-11-18T15:05:00Z"},
    })
    claims = load_symbol_claims(directory=tmp_path)
    assert claims.at(claims_moment(session_date="2026-11-17")).position_match({"conid": 123, "secType": "STK"})
    assert claims.at(claims_moment(session_date="2026-11-18")).position_match({"conid": 123, "secType": "STK"})
    assert claims.at(claims_moment(session_date="2026-11-19")).position_match({"conid": 123, "secType": "STK"}) is None
    assert claims_moment(session_date="2026-11-17") == datetime(2026, 11, 17, 5, 0, tzinfo=timezone.utc)


# -------------------------------------------------------------------- matching

def test_positions_match_by_conid_first_then_symbol_and_only_the_claims_sec_type(tmp_path):
    got = load(claims_file(tmp_path).parent)
    assert got.position_match({"conid": 123, "symbol": "RENAMED", "secType": "STK"}) == "symbol_claim_conid"
    assert got.position_match({"conId": "123", "symbol": "X", "sec_type": "STK"}) == "symbol_claim_conid"
    # A new conid after the split still reads as RS's by symbol: fail closed.
    assert got.position_match({"conid": 999, "symbol": "abcd", "secType": "STK"}) == "symbol_claim_symbol"
    assert got.position_match({"symbol": "ABCD"}) == "symbol_claim_symbol"
    # An option on a claimed name is not RS's position.
    assert got.position_match({"conid": 555, "symbol": "ABCD  261218P00005000", "secType": "OPT",
                               "underlyingSymbol": "ABCD"}) is None
    assert got.position_match({"conid": 7, "symbol": "CSU", "secType": "STK"}) is None


def test_a_ticket_matches_any_sec_type_by_conid_symbol_or_underlying(tmp_path):
    got = load(claims_file(tmp_path).parent)
    for identity in (
        {"conid": 123, "symbol": "WHATEVER", "sec_type": "STK"},
        {"symbol": "ABCD", "sec_type": "STK"},
        {"conid": 888, "symbol": "ABCD", "sec_type": "OPT", "local_symbol": "ABCD  261218P00005000"},
        {"conid": 888, "symbol": "X", "sec_type": "OPT", "local_symbol": "ABCD  261218C00005000"},
    ):
        assert got.ticket_match(identity) is not None, identity
    assert got.ticket_match({"conid": 7, "symbol": "CSU", "sec_type": "STK"}) is None


# ----------------------------------------------------------------- fail closed

@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p.write_text("{not json", encoding="utf-8"), "JSONDecodeError"),
    (lambda p: p.unlink(), "FileNotFoundError"),
    (lambda p: p.write_text(json.dumps([1]), encoding="utf-8"), "not a JSON object"),
    (lambda p: claims_file(p.parent, schema="ib_account_symbol_claims.v2"), "schema"),
    (lambda p: claims_file(p.parent, system="etf-0dte"), "system"),
    (lambda p: claims_file(p.parent, generated_at=None), "generated_at"),
    (lambda p: claims_file(p.parent, claims=[]), "claims is not an object"),
    (lambda p: claims_file(p.parent, claims={"ABCD": {"sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z",
                                                      "release_after": None}}), "conid"),
    (lambda p: claims_file(p.parent, claims={"ABCD": {"conid": 1, "claimed_at": "2026-11-17T15:00:00Z",
                                                      "release_after": None}}), "sec_type"),
    (lambda p: claims_file(p.parent, claims={"ABCD": {"conid": 1, "sec_type": "STK", "claimed_at": "yesterday",
                                                      "release_after": None}}), "claimed_at"),
    (lambda p: claims_file(p.parent, claims={"ABCD": {"conid": 1, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z",
                                                      "release_after": 5}}), "release_after"),
])
def test_an_unreadable_file_is_an_error_never_no_claims(tmp_path, mutate, needle):
    path = claims_file(tmp_path)
    mutate(path)
    got = load(tmp_path)
    assert (got.status, got.source, got.claims) == ("error", "none", ())
    assert got.unreadable and needle in got.error
    # And so nothing is proven unclaimed: every ticket is refused.
    refusal = claim_refusal({"conid": 7, "symbol": "CSU", "sec_type": "STK"}, got)
    assert refusal and "unreadable" in refusal


def test_a_file_for_another_account_is_an_error(tmp_path, monkeypatch):
    claims_file(tmp_path)
    monkeypatch.setenv("IBKR_ACCOUNT_ID", "U999")
    got = load(tmp_path)
    assert got.unreadable and "not 'U999'" in got.error
    monkeypatch.setenv("IBKR_ACCOUNT_ID", "U805366")
    assert load(tmp_path).status == "ok"


def test_the_last_good_copy_survives_in_process_and_on_disk(tmp_path):
    claims_dir, cache = tmp_path / "claims", tmp_path / "cache"
    path = claims_file(claims_dir)
    assert load(claims_dir, last_good_dir=cache).status == "ok"
    assert (cache / "reverse-split.last-good.json").read_bytes() == path.read_bytes()

    path.write_text("{truncated", encoding="utf-8")
    got = load(claims_dir, last_good_dir=cache)
    assert (got.status, got.source) == ("error", "last_good")
    assert got.position_match({"conid": 123, "secType": "STK"}) == "symbol_claim_last_good_conid"

    sc._LAST_GOOD.clear()   # a new process: only the disk copy is left
    got = load(claims_dir, last_good_dir=cache)
    assert (got.source, [c.symbol for c in got.active()]) == ("last_good", ["ABCD"])
    # A last good copy names what it can; it does not make a ticket safe.
    assert "unreadable" in claim_refusal({"conid": 7, "symbol": "CSU", "sec_type": "STK"}, got)

    # Without any copy the error stands alone.
    sc._LAST_GOOD.clear()
    got = load(claims_dir)
    assert (got.status, got.source, got.claims) == ("error", "none", ())


def test_the_env_var_names_the_last_good_directory(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv(LAST_GOOD_DIR_ENV, str(cache))
    claims_file(tmp_path / "claims")
    load(tmp_path / "claims")
    assert (cache / "reverse-split.last-good.json").is_file()


# ------------------------------------------------------------------- refusal

def test_a_claimed_name_is_refused_whatever_the_side_or_sec_type(tmp_path):
    got = load(claims_file(tmp_path).parent)
    refusal = claim_refusal({"conid": 123, "symbol": "ABCD", "sec_type": "STK"}, got, who="The hub")
    assert "ABCD is claimed by reverse-split" in refusal and "The hub never orders it" in refusal
    assert claim_refusal({"symbol": "ABCD", "sec_type": "OPT", "local_symbol": "ABCD  261218P00005000"}, got)
    assert claim_refusal({"conid": 7, "symbol": "CSU", "sec_type": "STK"}, got) is None
    assert claim_refusal({"symbol": "ABCD"}, None) is None


# ----------------------------------------------------------------- transport

def test_the_published_summary_is_deterministic_and_round_trips(tmp_path):
    path = claims_file(tmp_path, {
        "ZZZ": {"conid": 2, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z", "release_after": None},
        "ABCD": {"conid": 123, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z", "release_after": None},
        "GONE": {"conid": 3, "sec_type": "STK", "claimed_at": "2026-11-01T15:00:00Z", "release_after": "2026-11-02T00:00:00Z"},
    })
    first = load(tmp_path).summary()
    # RS rewrites its file (new generated_at) without changing what it claims:
    # the snapshot content, and so its source_run_id, must not change.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["generated_at"] = "2026-11-18T14:59:59Z"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert load(tmp_path).summary() == first
    assert [row["symbol"] for row in first["claims"]] == ["ABCD", "ZZZ"]
    assert "generated_at" not in first and "sha256" not in first

    rebuilt = claims_from_summary(first)
    assert rebuilt.position_match({"conid": 123, "secType": "STK"}) == "symbol_claim_conid"
    assert rebuilt.position_match({"conid": 3, "secType": "STK", "symbol": "GONE"}) is None
    assert claims_from_summary(None).configured is False
