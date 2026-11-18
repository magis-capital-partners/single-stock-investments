"""reverse-split: small-cap stock shorts in this shared account (client 60, RSLIVE|).

Until RS's stamp and claims were rules here, an RS short fell through every
branch to ``Classification(ticker, "michael", "residual")``: Michael's book,
Michael's realized P&L, and a hub ticket could net against it. These tests pin
each branch of the RS rule and its order against the etf-0dte, index, LETF and
owner rules, mirroring test_classify_etf_0dte.py.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.ib_gateway_registry import load_registry  # noqa: E402
from _system.trading.sleeves import safeties  # noqa: E402
from _system.trading.sleeves.classify_positions import (  # noqa: E402
    OTHER_SYSTEM_BUCKETS,
    REVERSE_SPLIT,
    REVERSE_SPLIT_UNVERIFIED,
    RS_BUCKETS,
    RS_REF_PREFIXES,
    classify_position,
    classify_positions,
    has_rs_ref,
)
from _system.trading.sleeves.realized import owner_policy  # noqa: E402
from _system.trading.sleeves.strategy_ownership import OwnershipRegistry, reference_owner  # noqa: E402
from _system.trading.sleeves.symbol_claims import SCHEMA, SymbolClaims, load_symbol_claims  # noqa: E402

LETF = {"SPY", "QQQ", "TSLA", "NVDA", "AMZN", "TQQQ", "APLD"}
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)


def write_claims(directory: Path, claims: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "reverse-split.json"
    path.write_text(json.dumps({
        "schema": SCHEMA, "system": "reverse-split", "account": "U805366",
        "generated_at": "2026-11-18T14:59:00Z", "claims": claims,
    }), encoding="utf-8")
    return path


def claim(conid, release_after=None):
    return {"conid": conid, "sec_type": "STK", "claimed_at": "2026-11-17T15:00:00Z", "release_after": release_after}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from _system.trading.sleeves import symbol_claims

    for name in ("IB_ACCOUNT_SYMBOL_CLAIMS_DIR", "IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR",
                 "IB_ACCOUNT_SYMBOL_CLAIMS_ACCOUNT", "IBKR_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    symbol_claims._LAST_GOOD.clear()
    yield
    symbol_claims._LAST_GOOD.clear()


@pytest.fixture()
def rs(tmp_path) -> SymbolClaims:
    write_claims(tmp_path / "claims", {"ABCD": claim(123), "WXYZ": claim(456)})
    return load_symbol_claims(directory=tmp_path / "claims").at(NOW)


@pytest.fixture()
def broken(tmp_path) -> SymbolClaims:
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "reverse-split.json").write_text("{", encoding="utf-8")
    return load_symbol_claims(directory=tmp_path / "claims").at(NOW)


def cls(pos, **kw):
    kw.setdefault("blacklist_family", {"APLD"})
    kw.setdefault("etf_ls_symbols", LETF)
    return classify_position(pos, **kw)


def short(symbol="ABCD", conid=123, qty=-500, **overrides):
    return {"symbol": symbol, "secType": "STK", "conId": conid, "qty": qty, "marketValue": qty * 3.0, **overrides}


# ------------------------------------------------------------------ the stamp

def test_the_prefix_is_rslive_only():
    assert RS_REF_PREFIXES == ("RSLIVE|",)
    for ref in ("RSLIVE|ENTRY|ABCD|1", "rslive|cover|x", "  RSLIVE|STOP|y"):
        assert has_rs_ref(ref)
    # The paper executor's prefix is a different system and never touches this account.
    for ref in ("", "RSPAPER|ENTRY|ABCD", "XRSLIVE|x", "MAGIS|single_stock|michael|RSLIVE|", "SPY0DTE|x"):
        assert not has_rs_ref(ref)


def test_the_prefix_is_the_shared_registrys_once_it_is_registered():
    raw, _ = load_registry()
    system = raw["systems"].get("reverse-split")
    if system is None:
        pytest.skip("reverse-split is not in the canonical registry yet (owned by another change)")
    assert set(RS_REF_PREFIXES) == set(system["order_ref_prefixes"])


def test_a_stamped_order_is_rs_whatever_else_would_claim_it():
    for pos in (
        short(orderRef="RSLIVE|ENTRY|ABCD|1"),
        short("APLD", orderRef="RSLIVE|ENTRY|APLD|1"),                 # blacklist family
        short("TQQQ", orderRef="RSLIVE|ENTRY|TQQQ|1"),                 # LS universe
        short("SPY", orderRef="RSLIVE|ENTRY|SPY|1"),                   # an etf-0dte root
        {"symbol": "SPXW  260817P05000000", "secType": "OPT", "orderRef": "RSLIVE|x"},
    ):
        got = cls(pos, drew_symbols={"ABCD"})
        assert (got.bucket, got.reason, got.owner) == (REVERSE_SPLIT, "order_ref", None), pos


# --------------------------------------------------------------- the claims

def test_a_claimed_short_is_rs_not_michaels_residual(rs):
    assert cls(short()).bucket == "michael"                                    # the bug, without claims
    got = cls(short(), rs_claims=rs)
    assert (got.bucket, got.reason, got.ticker, got.owner) == (REVERSE_SPLIT, "symbol_claim_conid", "ABCD", None)
    assert cls(short("ABCD", conid=777), rs_claims=rs).reason == "symbol_claim_symbol"


def test_a_claim_beats_every_symbol_and_owner_rule(rs):
    # LS universe, a Drew symbol and the blacklist family would each claim it.
    for kw in ({"drew_symbols": {"ABCD"}}, {"blacklist_family": {"ABCD"}}, {"etf_ls_symbols": {"ABCD"}}):
        assert cls(short(), rs_claims=rs, **kw).bucket == REVERSE_SPLIT, kw
    # So does broker-matched opening evidence: the account nets the two.
    evidence = {"owner": "michael", "strategy": "single_stock", "reason": "broker_matched_opening_order_reference"}
    assert cls(short(_ownership=evidence), rs_claims=rs).bucket == REVERSE_SPLIT


def test_an_rs_opening_reference_is_rs_even_after_the_claim_is_gone():
    evidence = reference_owner("RSLIVE|ENTRY|ABCD|1")
    got = cls(short(_ownership={**evidence, "reason": "broker_matched_opening_order_reference"}))
    assert (got.bucket, got.owner) == (REVERSE_SPLIT, None)


def test_options_on_a_claimed_name_and_unclaimed_names_keep_their_rules(rs):
    option = {"symbol": "ABCD  261218P00005000", "secType": "OPT", "underlyingSymbol": "ABCD", "conId": 999}
    assert cls(option, rs_claims=rs, etf_ls_symbols=set()).bucket == "michael"
    assert cls(short("CSU", conid=7), rs_claims=rs).bucket == "michael"
    assert cls(short("TQQQ", conid=8), rs_claims=rs).bucket == "etf_ls"
    assert cls({"symbol": "SPY", "secType": "OPT", "localSymbol": "SPY   261027C00580000"}, rs_claims=rs).bucket == "etf_0dte"


def test_a_released_claim_no_longer_covers_the_name(tmp_path):
    write_claims(tmp_path, {"ABCD": claim(123, release_after="2026-11-18T14:00:00Z")})
    assert cls(short(), rs_claims=load_symbol_claims(directory=tmp_path).at(NOW)).bucket == "michael"


# ------------------------------------------------------------- unreadable

def test_unreadable_claims_quarantine_every_unproven_short(broken):
    got = cls(short("NEWX", conid=31), rs_claims=broken)
    assert (got.bucket, got.reason, got.owner) == (REVERSE_SPLIT_UNVERIFIED, "symbol_claims_unreadable", None)
    assert cls({"symbol": "NEWX", "secType": "STK"}, rs_claims=broken).bucket == REVERSE_SPLIT_UNVERIFIED  # no qty
    # RS only shorts: a long stays Michael's, and positive evidence still wins.
    assert cls(short("CSU", qty=12), rs_claims=broken).bucket == "michael"
    assert cls(short("NEWX", qty=-5, orderRef="MICHAEL_SLEEVE"), rs_claims=broken).bucket == "michael"
    assert cls(short("JPM", qty=-5), rs_claims=broken, blacklist_family={"JPM"}).reason == "blacklist_family"
    assert cls(short("TQQQ", qty=-5), rs_claims=broken).bucket == "etf_ls"
    assert cls(short("IBKR", qty=-5), rs_claims=broken, drew_symbols={"IBKR"}).bucket == "drew"
    evidence = {"owner": "michael", "strategy": "single_stock", "reason": "broker_matched_opening_order_reference"}
    assert cls(short("NEWX", _ownership=evidence), rs_claims=broken).bucket == "michael"


def test_unreadable_claims_with_a_last_good_copy_keep_its_names_rs(tmp_path):
    path = write_claims(tmp_path / "claims", {"ABCD": claim(123)})
    load_symbol_claims(directory=tmp_path / "claims", last_good_dir=tmp_path / "cache")
    path.write_text("{", encoding="utf-8")
    stale = load_symbol_claims(directory=tmp_path / "claims", last_good_dir=tmp_path / "cache").at(NOW)
    assert cls(short(), rs_claims=stale).reason == "symbol_claim_last_good_conid"
    assert cls(short("NEWX", conid=31), rs_claims=stale).bucket == REVERSE_SPLIT_UNVERIFIED


# ------------------------------------------------------------- the batch path

def test_a_claimed_row_is_never_split_and_tags_cannot_re_own_it(rs):
    rows = classify_positions(
        [short(), short("CSU", conid=7, qty=12)],
        blacklist_family=set(), etf_ls_symbols=set(), drew_symbols={"ABCD"}, rs_claims=rs,
    )
    assert [r["classification"]["bucket"] for r in rows] == [REVERSE_SPLIT, "michael"]
    assert "etf_0dte_split" not in rows[0]


def test_every_rs_bucket_is_another_systems():
    assert RS_BUCKETS <= OTHER_SYSTEM_BUCKETS
    assert not {"michael", "drew", "ignored"} & OTHER_SYSTEM_BUCKETS


# ---------------------------------------------------------- realized history

def test_realized_history_keeps_rs_executions_out_of_both_books():
    def owner(event):
        return owner_policy(event, ls_symbols=LETF, blacklist={"APLD"})

    cover = {"ticker": "ABCD", "symbol": "ABCD", "sec_type": "STK", "order_ref": "RSLIVE|COVER|ABCD|2"}
    assert owner(cover) == ("excluded", REVERSE_SPLIT, "order_reference")
    assert owner({**cover, "ticker": "APLD", "symbol": "APLD"})[1] == REVERSE_SPLIT   # ahead of the family
    assert owner({**cover, "order_ref": ""}) == ("michael", "single_stock", "residual")  # ref-less: see below


def test_reference_owner_and_resolve_treat_rs_as_another_strategy():
    assert reference_owner("RSLIVE|ENTRY|ABCD|1") == {
        "owner": "excluded", "strategy": REVERSE_SPLIT, "reason": "executed_rs_order_reference"}
    base = {"account": "U1", "conid": "123", "model": "", "sec_type": "STK", "trade_date": "2026-11-17"}
    events = [
        {**base, "event_id": "tx:1", "transaction_id": "1", "order_ref": "RSLIVE|ENTRY|ABCD|1", "trade_time": "20261117;100000"},
        {**base, "conid": "7", "event_id": "tx:2", "transaction_id": "2", "order_ref": "MAGIS|single_stock|michael|u",
         "trade_time": "20261117;110000"},
    ]
    registry = OwnershipRegistry.build(events, account="U1", through="2026-11-17")
    # A ref-less close of an RS lot (a buy-in) is RS's through its opening.
    rs_lot = registry.resolve(account="U1", conid="123", transaction_id="1", closing_ref="", symbol="ABCD")
    assert (rs_lot["owner"], rs_lot["strategy"]) == ("excluded", REVERSE_SPLIT)
    # RS closing a human lot is a cross-strategy close: review, never RS's or Michael's.
    crossed = registry.resolve(account="U1", conid="7", transaction_id="2", closing_ref="RSLIVE|COVER|CSU|3", symbol="CSU")
    assert (crossed["strategy"], crossed["reason"]) == ("ownership_review", "cross_strategy_close")
    # An RS close with no opening evidence is RS's.
    bare = registry.resolve(account="U1", conid="55", closing_ref="RSLIVE|COVER|QRST|4", symbol="QRST")
    assert bare["strategy"] == REVERSE_SPLIT


# ----------------------------------------------------------------- sleeves

def _safety(tmp_path, monkeypatch, *, ticker, side, claims, sec="STK", underlying=None):
    monkeypatch.setattr(safeties, "kill_path", lambda cfg=None: tmp_path / "NO_KILL")
    cfg = {"execution": {"dry_run": True}, "ibkr": {}, "operators": {"michael": {}}}
    monkeypatch.setattr(safeties, "load_blacklist", lambda cfg=None: set())
    monkeypatch.setattr(safeties, "load_etf_to_under", lambda cfg=None: {})
    monkeypatch.setattr(safeties, "load_etf_ls_universe", lambda cfg=None: set())
    quote = {"last": 3.0, "bid": 2.99, "ask": 3.01, "as_of": NOW.isoformat(), "sec_type": sec,
             "underlying": underlying or ticker, "multiplier": 100 if sec == "OPT" else 1}
    return safeties.check_safeties(owner="michael", ticker=ticker, side=side, qty=1, limit_price=3.0,
                                   quote=quote, cfg=cfg, now=NOW, symbol_claims=claims)


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_no_sleeve_order_on_a_claimed_name_either_side(tmp_path, monkeypatch, rs, side):
    result = _safety(tmp_path, monkeypatch, ticker="ABCD", side=side, claims=rs)
    assert any("claimed by reverse-split" in f for f in result.failures), result.failures
    option = _safety(tmp_path, monkeypatch, ticker="ABCD  261218P00005000", side=side, claims=rs,
                     sec="OPT", underlying="ABCD")
    assert any("claimed by reverse-split" in f for f in option.failures), option.failures
    clean = _safety(tmp_path, monkeypatch, ticker="CSU", side=side, claims=rs)
    assert not any("reverse-split" in f for f in clean.failures), clean.failures


def test_no_sleeve_order_at_all_while_the_claims_are_unreadable(tmp_path, monkeypatch, broken):
    result = _safety(tmp_path, monkeypatch, ticker="CSU", side="BUY", claims=broken)
    assert any("reverse-split symbol claims are unreadable" in f for f in result.failures), result.failures
