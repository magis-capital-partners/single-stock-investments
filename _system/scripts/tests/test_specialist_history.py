"""Regression checks for extending SEC history without changing current books."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ingest_specialist_13f as ingest


def test_unchanged_latest_filing_does_not_skip_missing_history(tmp_path, monkeypatch):
    records = tmp_path / "records"
    full = records / "full"
    fund_dir = full / "test"
    fund_dir.mkdir(parents=True)
    saved = {"accession":"new", "quarter":"2026Q2", "records":[{"shares":10,"ticker":"AAA","cusip":"123"}]}
    for name in ["latest.json", "2026Q2.json"]:
        (fund_dir / name).write_text(json.dumps(saved))
    (records / "latest.json").write_text('{"current_book":"preserve"}')
    original = (fund_dir / "latest.json").read_bytes()
    monkeypatch.setattr(ingest, "FULL_RECORDS_DIR", full)
    monkeypatch.setattr(ingest, "RECORDS_DIR", records)
    monkeypatch.setattr(ingest, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(ingest, "portfolio_universe", lambda: (["AAA"], {}))
    monkeypatch.setattr(ingest, "specialist_funds_for_ingest", lambda: [{"fund_id":"test","cik":"1","fund":"Test"}])
    monkeypatch.setattr(ingest, "load_cusip_map", lambda: {})
    monkeypatch.setattr(ingest, "latest_13f_filings", lambda *_args, **_kw: [])
    groups = [[{"report_date":"2026-03-31","accession":"old"}], [{"report_date":"2026-06-30","accession":"new"}]]
    monkeypatch.setattr(ingest, "periods_for_fund", lambda *_args: groups)
    calls = []
    def period(group, **_kw):
        calls.append(group[0]["accession"])
        return {"quarter":"2026Q1", "period_end":"2026-03-31", "filing_date":"2026-05-15", "accession":"old", "rows":[], "source_url":"https://www.sec.gov/example", "reconciliation":{"ok":True}, "confidential_omitted":False}
    monkeypatch.setattr(ingest, "build_period", period)
    def holdings(*_args, **kw):
        assert kw["prior_full"] == {}, "A future quarter cannot supply prior holdings"
        return [{"ticker":"AAA", "cusip":"123", "shares":5}], [], {}, {}
    monkeypatch.setattr(ingest, "holdings_from_xml", holdings)
    monkeypatch.setattr(sys, "argv", ["ingest", "--backfill-quarters", "2", "--history-only"])
    assert ingest.main() == 0
    assert calls == ["old"]
    assert (fund_dir / "2026Q1.json").is_file()
    assert (fund_dir / "latest.json").read_bytes() == original
    assert (records / "latest.json").read_text() == '{"current_book":"preserve"}'
