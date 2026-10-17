"""Point-in-time and identity regressions for clean-data coverage recovery."""
import hashlib

from _system.scripts.reverse_splits.clean_data_facts import numeric, standard_facts
from _system.scripts.reverse_splits.clean_data_sources import company_key, identity_from_filing, index_candidates, issuer_from_finra_name
from _system.scripts.reverse_splits.clean_data_research import CleanStore, repaired_events


def document(symbol="OLD", title="Common Stock", known="2023-10-01T13:00:00+00:00", facts=""):
    text = f'''CENTRAL INDEX KEY: 0000001234
<DOCUMENT><TYPE>10-Q
<FILENAME>quarter.htm
<TEXT><html><body>
<xbrli:context id="whole"><xbrli:entity><xbrli:identifier>0000001234</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="duration"><xbrli:entity><xbrli:identifier>0000001234</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="segment"><xbrli:entity><xbrli:identifier>0000001234</xbrli:identifier><xbrli:segment><xbrldi:explicitMember>Subsidiary</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
<ix:nonNumeric name="dei:Security12bTitle" contextRef="whole">{title}</ix:nonNumeric>
<ix:nonNumeric name="dei:TradingSymbol" contextRef="whole">{symbol}</ix:nonNumeric>
{facts}</body></html></TEXT></DOCUMENT>'''
    return {"text": text, "known_at": known, "source_url": "https://www.sec.gov/Archives/edgar/data/1234/000000123423000001/quarter.htm",
            "source_sha256": hashlib.sha256(text.encode()).hexdigest(), "accessionNumber": "0000001234-23-000001", "path": "fixture_only"}


def event(ticker="OLD", **kwargs):
    return {"event_id": "fixture_only", "ticker": ticker, "company": "Example Holdings, Inc. Common Stock", "ex_date": "2023-10-17",
            "available_at": "2023-10-16T12:00:00+00:00", "issuer": "unresolved_symbol/"+ticker,
            "ratio": .1, "verification": "structured_corporate_action", **kwargs}


def fact(tag, text, context="whole", **attrs):
    extra = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f'<ix:nonFraction name="{tag}" contextRef="{context}" unitRef="usd" {extra}>{text}</ix:nonFraction>'


def test_name_candidates_remain_ambiguous_and_preserve_holdings():
    assert company_key("Example Holdings Inc. Common Stock") != company_key("Example Inc.")
    rows = index_candidates(b"EXAMPLE HOLDINGS INC:0000001234:\nEXAMPLE HOLDINGS, LTD:0000005678:\n", [event()], [])
    assert {r["cik"] for r in rows[company_key(event()["company"]) ]} == {"1234", "5678"}


def test_current_ticker_does_not_confirm_historical_security():
    assert identity_from_filing(event(), "1234", document("NEW")) is None
    assert identity_from_filing(event(), "1234", document(known="2023-10-17T12:00:00+00:00")) is None
    assert identity_from_filing(event(), "5678", document()) is None
    assert identity_from_filing(event(), "1234", document())["ticker"] == "OLD"


def test_placeholder_requires_unique_common_class():
    assert identity_from_filing(event("CIK1234"), "1234", document())["ticker"] == "OLD"
    assert identity_from_filing(event("CIK1234"), "1234", document("OLDW", "Warrants")) is None


def test_dated_entity_name_requires_official_finra_security_record():
    e = event(source="finra_otc_daily_list", security_type="common", security_id="finra_action/12345", source_url="https://otce.finra.org/otce/dailyList")
    d = document(symbol="UNRELATED")
    d["text"] = "COMPANY CONFORMED NAME: Example Holdings Inc.\n"+d["text"]
    assert issuer_from_finra_name(e, "1234", d) is None
    d["text"] = d["text"].replace('<ix:nonNumeric name="dei:TradingSymbol" contextRef="whole">UNRELATED</ix:nonNumeric>', '')
    assert issuer_from_finra_name(e, "1234", d)["ticker"] == "OLD"
    assert issuer_from_finra_name({**e, "security_type": "unknown"}, "1234", d) is None
    assert issuer_from_finra_name({**e, "company": "Example Group, Inc. Common Stock"}, "1234", d) is None
    assert issuer_from_finra_name({**e, "source": "current_symbol_directory"}, "1234", d) is None


def test_standard_facts_reject_segments_custom_tags_and_other_issuer():
    doc = document(facts=fact("us-gaap:Assets", "1,250", scale="3")+fact("us-gaap:Assets", "999", context="segment")+fact("example:Revenue", "100", context="duration"))
    rows = standard_facts(doc, "1234")
    assert len(rows) == 1
    assert rows[0]["value"] == 1250000
    assert rows[0]["end"] == "2023-09-30"
    assert rows[0]["unit"] == "USD"
    assert standard_facts(doc, "5678") == []


def test_fact_tail_and_footnote_cannot_change_amount():
    doc = document(facts=fact("us-gaap:NetIncomeLoss", '1,<b>234</b><ix:exclude>7</ix:exclude>', context="duration", sign="-")+" unrelated 99")
    rows = standard_facts(doc, "1234")
    assert rows[0]["value"] == -1234


def test_conflicting_fact_values_are_not_chosen():
    doc = document(facts=fact("us-gaap:Assets", "100")+fact("us-gaap:Assets", "200"))
    assert standard_facts(doc, "1234") == []
    assert numeric("-", format_name="numdotdecimal") is None
    assert numeric("-", format_name="zerodash") == 0
    assert numeric("1.234,5", format_name="numcommadecimal", scale="3") == 1234500


def test_name_lead_cannot_repair_identity_or_clock():
    e = event(available_at=None, verification="candidate_requires_verification")
    events, rejected = repaired_events([e], {"identities": {}, "actions": {}, "candidates": {e["event_id"]: {"candidate_cik": "1234"}}})
    assert events == []
    assert rejected[0]["reason"] == "primary_action_unverified"


def test_repaired_action_waits_for_its_source_and_deduplicates():
    a, b = event(cik="1234", issuer="cik/1234", available_at=None, verification="candidate_requires_verification"), event(cik="1234", issuer="cik/1234")
    b["event_id"] = "later_duplicate"
    sources = {"identities": {}, "actions": {a["event_id"]: {"status": "confirmed_primary_scheduled_action", "cik": "1234", "known_at": "2023-10-01T13:00:00+00:00", "ratio": .1}}}
    events, rejected = repaired_events([a, b], sources)
    assert len(events) == 1
    assert events[0]["available_at"] == "2023-10-01T13:01:00+00:00"
    assert rejected[0]["canonical_key"] == a["event_id"]


def test_late_primary_filing_cannot_unlock_an_earlier_entry():
    from _system.scripts.reverse_splits.net_edge_study import make_outcomes
    from _system.scripts.reverse_splits.net_edge_v3 import StudyPolicy
    e = event(cik="1234", issuer="cik/1234", available_at=None, verification="candidate_requires_verification")
    sources = {"identities": {}, "actions": {e["event_id"]: {"status": "confirmed_primary_scheduled_action", "cik": "1234", "known_at": "2023-10-19T13:00:00+00:00", "ratio": .1}}}
    events, _ = repaired_events([e], sources)
    s = {"known_at": events[0]["available_at"], "ex_date": e["ex_date"]}
    outcome = make_outcomes({"x": s}, None, StudyPolicy(entry="post_split_next_open"), ("2023-10-17", "2023-10-18", "2023-10-19"), "2023-10-19")
    assert outcome["x"]["status"] == "no_future_entry_in_sample"


def test_sec_later_filing_day_clamps_acceptance_clock(tmp_path):
    from _system.scripts.reverse_splits.clean_data_sources import primary_document
    path = tmp_path/"filing.txt"
    path.write_text('<ACCEPTANCE-DATETIME>20231016180000\nACCESSION NUMBER: 0000001234-23-000001\nCENTRAL INDEX KEY: 0000001234\nCONFORMED SUBMISSION TYPE: 8-K\nFILED AS OF DATE: 20231017\n', encoding='utf-8')
    doc = primary_document(path, "1234")
    assert doc["known_at"] == "2023-10-18T04:00:00+00:00"
    assert doc["accepted_at"] == "2023-10-16T22:00:00+00:00"
    assert doc["filed_at"] == "2023-10-17"


def test_primary_clean_store_never_imports_proxy_volume(tmp_path):
    import sqlite3
    path = tmp_path/"prices.sqlite"
    db = sqlite3.connect(path)
    db.executescript('CREATE TABLE prices_daily(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL); CREATE TABLE price_provenance(ticker TEXT,date TEXT,nominal INTEGER,volume_basis TEXT);')
    db.execute('INSERT INTO prices_daily VALUES(?,?,?,?,?,?,?)', ("OLD", "2023-10-02", 10, 11, 9, 10, 100))
    db.execute('INSERT INTO price_provenance VALUES(?,?,?,?)', ("OLD", "2023-10-02", 1, "three_venues_not_consolidated"))
    db.commit(); db.close()
    bars = {"OLD": {"2023-10-02": {"open": 10, "high": 11, "low": 9, "close": 10, "proxy_volume": 100000}, "2023-10-03": {"open": 10, "high": 11, "low": 9, "close": 10, "proxy_volume": 200000}}}
    clean = CleanStore(path, [], bars)
    assert clean.prices("OLD")["2023-10-02"]["volume"] == 100
    assert clean.prices("OLD")["2023-10-03"]["volume"] is None
    proxy = CleanStore(path, [], bars, volume_proxy=True)
    assert proxy.prices("OLD")["2023-10-02"]["volume"] == 100000
    clean.connection.close(); proxy.connection.close()
