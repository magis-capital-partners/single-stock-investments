"""Account-wide ownership reconciliation (files only; no socket)."""

import json

from _system.trading.account_ownership import ledger_quantities, main, read_positions, reconcile
from _system.trading.rs_paper_executor.claims import ClaimBook
from _system.trading.rs_paper_executor.journal import Journal

NOW = "2026-11-18T22:00:00+00:00"
RULES = [
    {"system": "spx-0dte", "asset": ["OPT"], "underlyings": ["SPX", "SPXW"]},
    {"system": "etf-0dte", "asset": ["OPT", "STK"], "underlyings": ["SPY", "QQQ"]},
    {"system": "reverse-split", "claims": True},
]


def pos(conid, symbol, sec="STK", qty=-100, und=None):
    return {"conid": conid, "symbol": symbol, "sec_type": sec, "underlying": und or symbol,
            "position": qty, "account": "U1"}


def test_each_position_has_exactly_one_owner(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("ABC", 11, NOW)
    report = reconcile([pos(1, "SPXW 261118P", "OPT", 5, "SPX"), pos(2, "SPY", qty=100),
                        pos(11, "ABC")], RULES, claims_dir=tmp_path, now=NOW)
    assert report["status"] == "ok"
    assert {k: len(v) for k, v in report["owned"].items()} == {
        "spx-0dte": 1, "etf-0dte": 1, "reverse-split": 1}


def test_unowned_and_double_owned_are_alarms(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("SPY", 2, NOW)  # RS claiming a product
    report = reconcile([pos(2, "SPY"), pos(99, "XYZ")], RULES, claims_dir=tmp_path, now=NOW)
    assert report["status"] == "alarm"
    assert report["double_owned"][0]["systems"] == ["etf-0dte", "reverse-split"]
    assert report["unowned"][0]["symbol"] == "XYZ"


def test_residual_owner_takes_only_what_nobody_claimed(tmp_path):
    rules = RULES + [{"system": "portfolio-hub", "residual": True}]
    report = reconcile([pos(99, "XYZ")], rules, claims_dir=tmp_path, now=NOW)
    assert report["status"] == "ok" and report["owned"]["portfolio-hub"][0]["symbol"] == "XYZ"


def test_released_claim_still_owns_a_position_the_broker_shows(tmp_path):
    book = ClaimBook(tmp_path, "reverse-split", "U1")
    book.claim("ABC", 11, NOW)
    book.release("ABC", "2026-11-18T21:00:00+00:00", NOW)
    report = reconcile([pos(11, "ABC")], RULES, claims_dir=tmp_path, now=NOW)
    assert report["owned"]["reverse-split"][0]["conid"] == 11


def test_ledger_mismatch_both_directions(tmp_path):
    ClaimBook(tmp_path, "reverse-split", "U1").claim("ABC", 11, NOW)
    ClaimBook(tmp_path, "reverse-split", "U1").claim("DEF", 12, NOW)
    report = reconcile([pos(11, "ABC", qty=-100), pos(12, "DEF", qty=-50)], RULES,
                       claims_dir=tmp_path, now=NOW,
                       ledgers={"reverse-split": {11: -90, 13: -10}})
    rows = {(r["conid"], r["ledger"], r["broker"]) for r in report["ledger_mismatch"]}
    assert rows == {(11, -90, -100), (13, -10, 0), (12, 0, -50)}


def test_flex_xml_summary_rows_only(tmp_path):
    xml = tmp_path / "flex.xml"
    xml.write_text('<FlexQueryResponse><FlexStatements><FlexStatement><OpenPositions>'
                   '<OpenPosition accountId="U1" conid="11" symbol="ABC" assetCategory="STK" '
                   'position="-100" levelOfDetail="SUMMARY"/>'
                   '<OpenPosition accountId="U1" conid="11" symbol="ABC" assetCategory="STK" '
                   'position="-100" levelOfDetail="LOT"/>'
                   '</OpenPositions></FlexStatement></FlexStatements></FlexQueryResponse>')
    rows = read_positions(xml)
    assert len(rows) == 1 and rows[0]["position"] == -100


def test_rs_journal_ledger_is_read_only_signed_short(tmp_path):
    j = Journal(tmp_path / "s.sqlite", "p", "RSLIVE|")
    with j.db:
        j.db.execute("INSERT INTO positions VALUES('s1','1',11,100,2.0,'a','b','{}')")
    j.close()
    assert ledger_quantities(tmp_path / "s.sqlite") == {11: -100}


def test_cli_exit_code_and_report(tmp_path, capsys):
    (tmp_path / "p.json").write_text(json.dumps([pos(99, "XYZ")]))
    (tmp_path / "r.json").write_text(json.dumps(RULES))
    assert main(["--positions", str(tmp_path / "p.json"), "--rules", str(tmp_path / "r.json"),
                 "--claims-dir", str(tmp_path), "--now", NOW]) == 1
    assert json.loads(capsys.readouterr().out)["unowned"][0]["conid"] == 99
