from datetime import datetime, timezone
from io import BytesIO
import sqlite3

import pytest

from _system.trading.rs_paper_executor.execution_feed import paper_snapshot, publish
from _system.trading.rs_paper_executor.journal import Journal


NOW = datetime(2026, 11, 23, 15, tzinfo=timezone.utc)
SESSION = "a" * 32


def test_paper_projection_preserves_order_history_and_reconnect_execution_identity(tmp_path):
    path = tmp_path / "paper.sqlite"
    journal = Journal(path, "policy")
    try:
        journal.set("endpoint", {"account": "DU12345"})
        signal = {
            "id": "control", "ticker": "AAPL", "conid": 1, "cik": "1",
            "planned_exit_at": NOW.isoformat(),
        }
        entry = journal.intent(signal, "SELL", 2, 101, NOW.isoformat())
        journal.acknowledge(entry, 12)
        journal.fill(entry, "entry-a", 1, 101, NOW.isoformat(), 1, "estimate")
        cancel = journal.intent({**signal, "id": "cancel"}, "SELL", 1, 200, NOW.isoformat())
        journal.acknowledge(cancel, 13)
        journal.set("cancel_requested:" + cancel, NOW.isoformat())
        with journal.db:
            journal.db.execute("UPDATE orders SET state='cancelled' WHERE ref=?", (cancel,))
        journal.execution_mark(signal["id"], 99, NOW.isoformat(), "live_ask")
        first = paper_snapshot(path, SESSION, NOW)
        assert first["positions"][0]["shares_short"] == 1
        assert first["pnl"]["marked_before_borrow"] == 1
        assert first["pnl"]["commission_final"] is False
        assert first["orders"][0]["filled"] == 1
        assert first["orders"][0]["state"] == "working"

        journal.fill(entry, "entry-b", 1, 103, NOW.isoformat(), 1, "broker")
        assert not journal.fill(entry, "entry-a", 1, 101, NOW.isoformat(), .5, "broker")
        cover = journal.intent(signal, "BUY", 2, 100, NOW.isoformat())
        journal.acknowledge(cover, 14)
        journal.fill(cover, "cover", 2, 100, NOW.isoformat(), .5, "broker")

        final = paper_snapshot(path, SESSION, NOW, ended=True)
        assert len(final["orders"]) == 3 and len(final["fills"]) == 3
        assert {event["kind"] for event in final["events"]} >= {
            "order_submitting", "order_working", "order_cancelled", "cancel_requested",
            "order_filled", "short_fill", "cover_fill",
        }
        assert final["pnl"] == {
            "currency": "USD", "realized_gross": 4, "unrealized_gross": 0,
            "commission": 2, "commission_final": True, "marked_before_borrow": 2,
        }
        assert final["positions"] == []
        assert "DU12345" not in repr(final)
    finally:
        journal.close()


def test_live_journal_refused(tmp_path):
    path = tmp_path / "live.sqlite"
    journal = Journal(path, "policy", prefix="RSLIVE|")
    try:
        journal.set("endpoint", {"account": "U12345"})
        with pytest.raises(ValueError, match="DU-only"):
            paper_snapshot(path, SESSION, NOW)
        with sqlite3.connect(path) as db:
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='execution_order_states'").fetchone()
    finally:
        journal.close()


def test_publisher_identifies_itself_to_cloudflare_pages():
    class Response(BytesIO):
        status = 200
        headers = {"content-type": "application/json"}

    class Opener:
        @staticmethod
        def open(request, timeout):
            assert request.get_header("User-agent") == "Magis-RS-Paper/1.0"
            assert request.get_header("X-ssi-ingest-purpose") == "rs_execution_paper"
            return Response(b'{"available":true}')

    assert publish(
        "https://single-stock-investments-2wt.pages.dev/api/v2/portfolio/ingest",
        "synthetic-test-key" * 4, {"schema": "rs_execution_probe.v1"}, opener=Opener(),
    ) == {"available": True}
