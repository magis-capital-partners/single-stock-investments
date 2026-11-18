"""Symbol-claims contract tests (no network)."""

import json

import pytest

from _system.trading.rs_paper_executor.claims import ClaimBook, SCHEMA, foreign_claims
from _system.trading.rs_paper_executor.safety import SafetyError

NOW = "2026-11-18T15:00:00+00:00"
LATER = "2026-11-20T21:00:00+00:00"


def test_claim_is_durable_and_survives_age(tmp_path):
    book = ClaimBook(tmp_path, "reverse-split", "U1")
    book.claim("ABC", 123, NOW)
    assert book.held(LATER) == {"ABC"}  # age never releases a claim
    data = json.loads((tmp_path / "reverse-split.json").read_text())
    assert data["schema"] == SCHEMA and data["claims"]["ABC"]["release_after"] is None


def test_release_takes_effect_only_after_release_time(tmp_path):
    book = ClaimBook(tmp_path, "reverse-split", "U1")
    book.claim("ABC", 123, NOW)
    book.release("ABC", "2026-11-19T21:00:00+00:00", NOW)
    assert book.held("2026-11-19T20:59:00+00:00") == {"ABC"}
    assert book.held(LATER) == set()


def test_reclaim_reopens_and_conid_conflict_refused(tmp_path):
    book = ClaimBook(tmp_path, "reverse-split", "U1")
    book.claim("ABC", 123, NOW)
    book.release("ABC", NOW, NOW)
    book.claim("ABC", 123, LATER)
    assert book.held(LATER) == {"ABC"}
    with pytest.raises(SafetyError):
        book.claim("ABC", 999, LATER)


def test_wrong_account_file_refused(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("ABC", 1, NOW)
    with pytest.raises(SafetyError):
        ClaimBook(tmp_path, "reverse-split", "U2").load()


def test_foreign_reader_excludes_own_and_uses_last_good_copy(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("ABC", 1, NOW)
    ClaimBook(tmp_path, "other", "U1").claim("XYZ", 2, NOW)
    cache = {}
    assert foreign_claims(tmp_path, "other", NOW, cache) == {"ABC": "reverse-split"}
    (tmp_path / "reverse-split.json").write_text("{truncated")
    assert foreign_claims(tmp_path, "other", NOW, cache) == {"ABC": "reverse-split"}
    with pytest.raises(SafetyError):
        foreign_claims(tmp_path, "other", NOW, {})  # never read a good copy


def test_file_name_must_match_system(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("ABC", 1, NOW)
    (tmp_path / "reverse-split.json").rename(tmp_path / "imposter.json")
    with pytest.raises(SafetyError):
        foreign_claims(tmp_path, "other", NOW, {})
