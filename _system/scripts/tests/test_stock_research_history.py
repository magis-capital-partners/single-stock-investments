"""History ingestion preserves listing sessions, units and unavailable evidence."""
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_stock_research_history as history


def test_vendor_bars_and_events_use_the_exchange_date_and_listing_currency(monkeypatch):
    from datetime import datetime, timezone
    stamp = lambda day: int(datetime(1962, 1, day, 23, tzinfo=timezone.utc).timestamp())
    payload = {"chart": {"result": [{
        "meta": {"currency": "AUD", "exchangeTimezoneName": "Australia/Sydney"},
        "timestamp": [stamp(1), stamp(2), stamp(3)],
        "indicators": {"quote": [{"close": [10, 11, 12]}]},
        "events": {"dividends": {"cash": {"date": stamp(2), "amount": 1}}},
    }]}}
    monkeypatch.setattr(history, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps(payload).encode()))
    monkeypatch.setattr(history.time, "sleep", lambda _: None)
    monkeypatch.setattr(history, "load_event_ledger", lambda ticker, events: (events, {"status": "vendor_only"}))
    record = history.fetch_performance("TEST.AX", {"market": "AU"})
    assert record["points"][0][0] == "1962-01-02"
    assert record["points"][-1][0] == "1962-01-04"
    assert record["currency"] == "AUD"
    assert record["benchmark_ref"] is None
    assert record["points"][-1][2] > record["points"][-1][1]
    assert record["status"] == "partial"


def test_a_missing_listing_is_an_explicit_gap_not_a_synthetic_return(monkeypatch):
    def missing(*args, **kwargs):
        raise OSError("Listing unavailable")
    monkeypatch.setattr(history, "urlopen", missing)
    monkeypatch.setattr(history.time, "sleep", lambda _: None)
    record = history.fetch_performance("MISSING", {"market": "US"})
    assert record["status"] == "unavailable"
    assert not record.get("points")


def test_contingent_rights_and_debentures_never_inherit_common_share_returns(monkeypatch):
    monkeypatch.setattr(history, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Unexpected parent equity request")))
    for ticker in ("ABMD.CVR", "CSU.DB"):
        assert history.fetch_performance(ticker, {})["status"] == "unavailable"


def test_materially_conflicting_vendor_returns_require_source_reconciliation(tmp_path):
    import gzip
    from datetime import datetime, timezone
    source = tmp_path / "source.json.gz"
    data = {"timestamp": [int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()), int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())],
            "meta": {"exchangeTimezoneName": "UTC"}, "indicators": {"adjclose": [{"adjclose": [100, 110]}]}}
    source.write_bytes(gzip.compress(json.dumps({"data": data}).encode()))
    record = {"points": [["2020-01-01", 100, 100], ["2021-01-01", 110, 300]], "coverage": {"status": "vendor_only"}}
    result = history.reconcile_performance(record, source)
    assert result["status"] == "evidence_blocked"
    assert result["points"] == []
    assert result["reconciliation"]["status"] == "requires_review"
    record["points"][-1][2] = 110
    assert history.reconcile_performance(record, source)["reconciliation"]["status"] == "consistent"
