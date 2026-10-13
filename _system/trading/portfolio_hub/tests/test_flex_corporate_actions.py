"""Flex ``CorporateAction`` rows: spin receipts, exchange-offer acceptances.

A SpinCo line lands in the book with no Trade row and the parent's share count
falls with no sale; the corporate-action section is the only broker record of
that. The parser reads it over HTTPS Flex like everything else -- no Gateway.
"""
from _system.trading.portfolio_hub.flex import parse_flex_xml

HEAD = b'<FlexQueryResponse><FlexStatements><FlexStatement accountId="TEST_ACCOUNT" fromDate="%s" toDate="%s">'
TAIL = b'</FlexStatement></FlexStatements></FlexQueryResponse>'


def test_corporate_actions_parse_spin_receipt_and_exchange_acceptance() -> None:
    xml = HEAD % (b"20260801", b"20260816") + b'''
      <OpenPositions><OpenPosition conid="101" symbol="PRNT" assetCategory="STK" currency="USD" position="40" costBasisMoney="4000" positionValue="4100" reportDate="20260816" /></OpenPositions>
      <CorporateActions>
        <CorporateAction actionID="ca-1" type="SO" actionDescription="PRNT(US0000000001) SPINOFF  1 FOR 10 (SPIN, SPINCO INC, US0000000002)" symbol="SPIN" conid="202" quantity="4" amount="0" value="120.5" reportDate="20260815" dateTime="20260815;202000" currency="USD" />
        <CorporateAction transactionID="ca-2" code="TO" description="PRNT(US0000000001) TENDERED TO US0000000002 1 FOR 8.0525" symbol="PRNT" conid="101" quantity="-60" proceeds="-6000" value="-6000" reportDate="20260816" currency="USD" />
      </CorporateActions>
      <ChangeInNAV currency="USD" total="1000" cash="100" stock="900" options="0" />
    ''' + TAIL
    result = parse_flex_xml(xml, account_alias="paper-primary")
    actions = result["corporate_actions"]
    assert len(actions) == 2
    spin, tender = actions
    assert spin == {
        "action_id": "ca-1", "type": "SO",
        "description": "PRNT(US0000000001) SPINOFF  1 FOR 10 (SPIN, SPINCO INC, US0000000002)",
        "symbol": "SPIN", "conid": 202, "quantity": "4", "amount": "0", "value": "120.5",
        "date": "20260815;202000",
    }
    # Alternate attribute spellings: transactionID / code / description / proceeds.
    assert tender["action_id"] == "ca-2"
    assert tender["type"] == "TO"
    assert tender["description"].startswith("PRNT(US0000000001) TENDERED")
    assert tender["symbol"] == "PRNT" and tender["conid"] == 101
    assert tender["quantity"] == "-60"
    assert tender["amount"] == "-6000"
    assert tender["date"] == "20260816"
    # The rest of the statement is untouched by the new section.
    assert result["positions"][0]["symbol"] == "PRNT"
    assert result["session_date"] == "2026-08-16"


def test_corporate_actions_absent_gives_an_empty_list() -> None:
    xml = HEAD % (b"20260801", b"20260816") + b'<ChangeInNAV currency="USD" total="1000" cash="100" stock="900" options="0" />' + TAIL
    result = parse_flex_xml(xml, account_alias="paper-primary")
    assert result["corporate_actions"] == []


def test_corporate_action_dates_settle_the_slash_date_order() -> None:
    # Only the corporate-action row carries a day over 12, so without it the
    # statement's 09/10/2026 session date would be ambiguous and left unread.
    xml = HEAD % (b"09/01/2026", b"09/10/2026") + b'''
      <CorporateActions>
        <CorporateAction actionID="ca-3" type="SO" actionDescription="SPINOFF" symbol="SPIN" conid="202" quantity="4" amount="0" value="100" reportDate="09/25/2026" dateTime="09/25/2026;202000" />
      </CorporateActions>
    ''' + TAIL
    result = parse_flex_xml(xml, account_alias="paper-primary")
    assert result["date_order"] == "mdy"
    assert result["session_date"] == "2026-09-10"
    assert result["corporate_actions"][0]["conid"] == 202


def test_corporate_action_without_conid_is_none_not_zero() -> None:
    xml = HEAD % (b"20260801", b"20260816") + b'''
      <CorporateActions><CorporateAction actionID="ca-4" type="DW" actionDescription="CASH IN LIEU" symbol="SPIN" quantity="0" amount="12.34" reportDate="20260816" /></CorporateActions>
    ''' + TAIL
    result = parse_flex_xml(xml, account_alias="paper-primary")
    row = result["corporate_actions"][0]
    assert row["conid"] is None
    assert row["amount"] == "12.34"
    assert row["value"] is None
