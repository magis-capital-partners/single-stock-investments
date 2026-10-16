from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from _system.scripts.reverse_splits.free_evidence import (
    FreeClient, audit_publication, borrow_ceiling, cached_filing, extract_terms, filing_time,
    normalized_text, review_packet, same_day_facts, select_filings, validate_url,
)
from _system.scripts.reverse_splits.net_edge import FRAMEWORKS


@pytest.mark.parametrize("url", [
    "https://hist.databento.com/v0/timeseries.get_range", "https://api.openai.com/v1/responses",
    "http://data.sec.gov/submissions/test.json", "https://data.sec.gov/submissions/test.json?token=x",
    "https://user:password@data.sec.gov/submissions/test.json", "https://data.sec.gov.evil.test/file",
])
def test_free_only_boundary_rejects_paid_or_credentialled_requests(url):
    with pytest.raises(ValueError): validate_url(url)


def test_zero_request_budget_never_opens_a_connection(tmp_path):
    client = FreeClient(tmp_path, "research", maximum=0)
    client.opener = Mock()
    assert client.get("https://data.sec.gov/submissions/CIK0000000001.json") is None
    client.opener.open.assert_not_called()


def test_public_cache_hash_tampering_is_rejected(tmp_path):
    client = FreeClient(tmp_path, "research")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"cik":"1"}'
    client.opener.open = Mock(return_value=response)
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    assert client.get(url) == b'{"cik":"1"}'
    next(tmp_path.glob("*.raw")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash/URL"): client.get(url)
    assert client.requests == 1


def test_missing_sec_clock_waits_until_next_eastern_day():
    assert filing_time({"filingDate": "2026-07-07"}) == "2026-07-08T04:00:00+00:00"


def test_sec_inline_xbrl_encoding_declaration_is_supported():
    raw = '<?xml version="1.0" encoding="windows-1252"?><html><body><p>Net proceeds $500.</p><script>Ignore</script></body></html>'
    assert normalized_text(raw) == "Net proceeds $500."


def test_exact_prior_clock_unlocks_same_day_facts_without_future_amendment():
    snap = snapshot()
    snap["cik"] = "1"
    rows = [{"accessionNumber": "old", "filingDate": "2026-07-07", "acceptanceDateTime": "2026-07-07T13:00:00Z"},
            {"accessionNumber": "later", "filingDate": "2026-07-07", "acceptanceDateTime": "2026-07-07T17:00:00Z"},
            {"accessionNumber": "unclocked", "filingDate": "2026-07-07"}]
    facts = [{"form": "10-Q", "filed": "2026-07-07", "end": "2026-06-30", "val": 10, "accn": "old"},
             {"form": "10-Q", "filed": "2026-07-07", "end": "2026-06-30", "val": 999, "accn": "later"},
             {"form": "10-Q", "filed": "2026-07-07", "end": "2026-06-30", "val": 888, "accn": "unclocked"}]
    raw = {"facts": {"us-gaap": {"CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": facts}}}}}
    result = same_day_facts(raw, rows, snap, "https://data.sec.gov/submissions/CIK0000000001.json", "a"*64)
    assert len(result) == 1 and result[0]["value"] == 10
    assert result[0]["known_at"] == "2026-07-07T13:01:00+00:00"


def test_acceptance_without_the_dissemination_allowance_stays_unavailable():
    snap = {**snapshot(), "cik": "1"}
    rows = [{"accessionNumber": "one", "filingDate": "2026-07-07", "acceptanceDateTime": "2026-07-07T15:59:30Z"}]
    raw = {"facts": {"us-gaap": {"CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
        {"form": "10-Q", "filed": "2026-07-07", "end": "2026-06-30", "val": 10, "accn": "one"}]}}}}}
    assert same_day_facts(raw, rows, snap, "https://data.sec.gov/", "a"*64) == []


def test_future_and_same_day_unclocked_filings_cannot_enter_packet():
    rows = [
        {"accessionNumber": "old", "form": "10-Q", "filingDate": "2026-07-06"},
        {"accessionNumber": "same_day", "form": "8-K", "filingDate": "2026-07-07"},
        {"accessionNumber": "future", "form": "10-Q", "filingDate": "2026-07-08"},
    ]
    assert [r["accessionNumber"] for r in select_filings(rows, "2026-07-07T16:00:00Z")] == ["old"]


def test_cached_filing_binds_issuer_and_acceptance_clock(tmp_path):
    path = tmp_path/"filing.full.txt"
    path.write_text("20260707163105\nACCESSION NUMBER: 0000000001-26-000001\n"
                    "CENTRAL INDEX KEY: 0000000001\nCONFORMED SUBMISSION TYPE: 8-K\n", encoding="utf-8")
    assert cached_filing(path, "2") is None
    assert cached_filing(path, "1")["known_at"] == "2026-07-07T20:31:05+00:00"


def snapshot():
    return {"key": "event/one", "ticker": "TEST", "issuer": "cik/1", "known_at": "2026-07-07T16:00:00Z",
            "screen_rating": 75, "fundamental": {"signals": {}, "evidence": [], "balances": {}, "flows": {}}}


def test_assessment_does_not_turn_missing_evidence_into_na_or_conviction():
    packet = review_packet(snapshot(), [], now=datetime.now(timezone.utc).isoformat())
    assert len(packet["frameworks"]) == len(FRAMEWORKS) == 27
    assert len(packet["missing"]) == 27
    assert packet["conviction_rating"] is None
    assert not packet["completed_underwriting"]
    assert all(r["status"] == "unresolved" for r in packet["frameworks"])


def test_future_filing_and_returns_cannot_influence_review():
    snap = snapshot()
    future = {"known_at": "2026-07-08T00:00:00Z", "text": "material weakness; net proceeds $100m"}
    snap.update(gross_return=.99, price=1, outcome={"gross_return": 10})
    before = review_packet(snap, [], now="2026-10-16T00:00:00Z")
    after = review_packet(snap, [future], now="2026-10-16T00:00:00Z")
    assert before == after
    assert "gross_return" not in str(after)


def test_financing_keyword_is_a_cited_unreconciled_lead_not_issued_dilution():
    doc = {"known_at": "2026-07-06T12:00:00Z", "text": "We may raise gross proceeds through an at-the-market program.",
           "source_url": "https://www.sec.gov/filing", "source_sha256": "hash", "accessionNumber": "one"}
    terms = extract_terms(doc)
    assert terms and all(t["status"] == "context_requires_reconciliation" for t in terms)
    packet = review_packet(snapshot(), [doc], now="2026-10-16T00:00:00Z")
    assert packet["capitalization_status"] == "claims_proceeds_and_share_basis_unreconciled"
    assert all(r["status"] == "unresolved" for r in packet["frameworks"])


def test_borrow_ceiling_reprices_carry_and_distinguishes_zero_days():
    plan = {"net_edge": .03, "net_lower_bound": .01, "expected_borrow": .02, "expected_billed_days": 5}
    cap = borrow_ceiling(plan, .5)
    assert cap["maximum_annual_rate"] == pytest.approx(1.25)
    assert cap["conservative_maximum_annual_rate"] == pytest.approx(.75)
    assert next(r for r in cap["net_at_annual_rates"] if r["annual_rate"] == .5)["net_edge"] == pytest.approx(.03)
    assert borrow_ceiling({**plan, "expected_borrow": 0}, .5)["status"] == "no_modeled_time_carry"


def test_negative_edge_before_carry_has_no_affordable_positive_fee():
    cap = borrow_ceiling({"net_edge": -.05, "net_lower_bound": -.1, "expected_borrow": .01}, .5)
    assert cap["maximum_annual_rate"] == 0
    assert cap["status"] == "no_edge_before_borrow"


def test_borrow_ceiling_rejects_fixed_fees_and_nonfinite_inputs():
    plan = {"net_edge": .03, "expected_borrow": .01}
    assert borrow_ceiling(plan, .5, preborrow_fee_per_share=.1)["status"] == "unavailable"
    assert borrow_ceiling({**plan, "expected_borrow": float("nan")}, .5)["status"] == "unavailable"


def test_publication_audit_rejects_future_source_even_with_a_valid_content_hash(tmp_path):
    import hashlib
    from _system.scripts.reverse_splits.ledger import write_json
    from _system.scripts.reverse_splits.net_edge_evidence import digest
    packet = review_packet(snapshot(), [], now="2026-10-16T00:00:00Z")
    packet["documents"] = [{"known_at": "2026-07-08T12:00:00Z", "source_sha256": "a"*64}]
    name = hashlib.sha256(packet["event_id"].encode()).hexdigest()[:24]+".json"
    target = tmp_path/"free_packets"/name
    write_json(target, packet)
    summary = {"data_cost_usd": 0, "paid_requests": 0, "packets": 1,
               "names": [{"event_id": packet["event_id"], "path": "data/free_short_packets/"+name,
                          "sha256": digest(target)}]}
    write_json(tmp_path/"free_evidence.json", summary)
    assert any("Future/unclocked" in e for e in audit_publication(tmp_path))
