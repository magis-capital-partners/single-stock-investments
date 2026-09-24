"""Sleeve sync posts stay under the edge's body cap, and a failed post fails the run.

Michael's Flex-sourced sync reached the edge at 647,887 bytes against its
512,000-byte MAX_BODY_BYTES and was refused with HTTP 413 -- and main() still
exited 0, so the unit reported success while the book never arrived. The body
carried build_book's full display row once per Flex *tax lot* (name, thesis,
notes, cluster, conviction, P&L -- none of which the edge stores), plus one
audit row per lot. These tests pin the fix: rows the edge reads, folded per
contract the way the edge folds them, audit deduplicated and split into extra
posts only if it has to be; and a non-zero exit once every owner was tried.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves import sync_ib  # noqa: E402
from _system.trading.sleeves.store import SleeveStore  # noqa: E402
from _system.trading.sleeves.sync_ib import (  # noqa: E402
    IngestTooLarge,
    fold_ingest_positions,
    ingest_payloads,
    sync_holdings,
)

EDGE_MAX_BODY_BYTES = 512_000  # dashboard/functions/api/v1/sleeves/ingest.js
FIXTURE = Path(__file__).with_name("fixtures") / "flex_positions_sample.xml"


def _lots(contracts: int = 700, lots_per_contract: int = 3) -> list[dict]:
    """A Michael-sized residual book: many contracts, each reported as several lots."""
    rows = []
    for index in range(contracts):
        for lot in range(lots_per_contract):
            rows.append({
                "symbol": f"ZQ{index:04d}", "localSymbol": f"ZQ{index:04d}", "secType": "STK",
                "conId": 700_000 + index, "currency": "USD", "qty": 100 + lot, "mark": 12.5,
                "marketValue": 12.5 * (100 + lot), "costUsd": 10.0 * (100 + lot), "avgCost": 10.0,
                "name": f"RESIDUAL HOLDING NUMBER {index} WITH A LONG REGISTERED COMPANY NAME PLC",
            })
    return rows


def _post_bodies(monkeypatch, tmp_path, rows, *, fail_owner=None):
    """Run a real sync with every POST captured instead of sent."""
    bodies: list[tuple[str, bytes]] = []

    def fake_post(url, token, payload, timeout=20):
        body = json.dumps(payload, separators=(",", ":")).encode()  # exactly what post_ingest sends
        owner = (payload.get("book") or {}).get("owner") or (payload.get("audit") or [{}])[0].get("owner")
        bodies.append((owner, body))
        if owner == fail_owner:
            raise RuntimeError("HTTP Error 413: Payload Too Large")
        return {"ok": True}

    monkeypatch.setenv("SLEEVE_INGEST_TOKEN", "t" * 32)
    monkeypatch.setattr(sync_ib, "post_ingest", fake_post)
    result = sync_holdings(SleeveStore(tmp_path), positions=rows, ingest=True, write_dashboard=False)
    return result, bodies


def test_a_large_michael_book_posts_under_the_edge_cap(monkeypatch, tmp_path):
    result, bodies = _post_bodies(monkeypatch, tmp_path, _lots())
    michael = [body for owner, body in bodies if owner == "michael"]
    assert michael, "Michael's book was posted"
    assert all(len(body) < EDGE_MAX_BODY_BYTES for body in michael), [len(body) for body in michael]
    assert result["ingest"]["michael"]["ok"] is True


def test_the_edge_receives_one_row_per_contract_with_the_same_totals(monkeypatch, tmp_path):
    rows = _lots(contracts=50, lots_per_contract=4)
    result, bodies = _post_bodies(monkeypatch, tmp_path, rows)
    book = json.loads(next(body for owner, body in bodies if owner == "michael"))["book"]
    assert len(book["positions"]) == 50
    assert sum(pos["qty"] for pos in book["positions"]) == pytest.approx(sum(row["qty"] for row in rows))
    assert sum(pos["market_value"] for pos in book["positions"]) == pytest.approx(sum(row["marketValue"] for row in rows))
    # Only what the edge stores; the display row stays on the static page.
    assert set().union(*(pos.keys() for pos in book["positions"])) <= set(sync_ib._INGEST_POSITION_KEYS)
    assert "notes" not in book and "metrics" not in book


def test_folding_matches_the_edges_foldPositions():
    """Same key (local_symbol, else ticker), same sums, first lot's everything else."""
    lots = [
        {"ticker": "XSP", "local_symbol": "XSP 270129P00540000", "qty": 68, "market_value": 100.0, "cost_usd": 90.0, "mark": 1.5, "name": "x"},
        {"ticker": "XSP", "local_symbol": "XSP 270129P00540000", "qty": 12, "market_value": 20.0, "cost_usd": None, "mark": 9.9},
        {"ticker": "XSP", "local_symbol": "XSP 270129P00550000", "qty": 5, "market_value": 7.0},
        {"ticker": "CSU", "qty": 1, "market_value": 3.0, "cost_usd": 2.0},
        {"ticker": "CSU", "qty": 2, "market_value": 6.0, "cost_usd": 4.0},
    ]
    folded = {row.get("local_symbol") or row["ticker"]: row for row in fold_ingest_positions(lots)}
    assert folded["XSP 270129P00540000"]["qty"] == 80
    assert folded["XSP 270129P00540000"]["market_value"] == 120.0
    assert folded["XSP 270129P00540000"]["cost_usd"] == 90.0
    assert folded["XSP 270129P00540000"]["mark"] == 1.5, "mark is per contract: the first lot's"
    assert folded["XSP 270129P00550000"]["qty"] == 5
    assert folded["CSU"]["qty"] == 3 and folded["CSU"]["cost_usd"] == 6.0
    assert "name" not in folded["XSP 270129P00540000"]


def test_audit_that_does_not_fit_follows_in_audit_only_posts():
    book = {"owner": "michael", "as_of": "2026-09-24", "header": {}, "positions": [{"ticker": "A", "qty": 1}]}
    audit = [{"ticker": f"T{index}", "bucket": "michael", "reason": "residual", "owner": "michael"} for index in range(400)]
    audit += audit[:50]  # lot-level duplicates collapse
    payloads = ingest_payloads("michael", book, audit, budget=4_000)
    assert len(payloads) > 1
    assert payloads[0]["book"]["positions"], "the book travels whole, in the first post"
    assert all("book" not in payload for payload in payloads[1:]), "later posts never replace the book"
    sent = [json.dumps(row, sort_keys=True) for payload in payloads for row in payload["audit"]]
    assert len(sent) == len(set(sent)) == 400
    assert all(len(json.dumps(payload, separators=(",", ":")).encode()) <= 4_000 for payload in payloads)


def test_a_book_that_cannot_fit_is_refused_rather_than_split():
    book = {"owner": "michael", "as_of": "2026-09-24", "header": {},
            "positions": [{"ticker": f"T{index}", "local_symbol": f"T{index}", "qty": 1} for index in range(500)]}
    with pytest.raises(IngestTooLarge):
        ingest_payloads("michael", book, [], budget=2_000)


def test_a_failed_owner_does_not_stop_the_next_and_fails_the_run(monkeypatch, tmp_path, capsys):
    posted: list[str] = []

    def fake_post(url, token, payload, timeout=20):
        owner = (payload.get("book") or {}).get("owner")
        posted.append(owner)
        if owner == "michael":
            raise RuntimeError("HTTP Error 413: Payload Too Large")
        return {"ok": True}

    monkeypatch.setenv("SLEEVE_INGEST_TOKEN", "t" * 32)
    monkeypatch.setattr(sync_ib, "post_ingest", fake_post)
    monkeypatch.setattr(sync_ib, "SleeveStore", lambda: SleeveStore(tmp_path))
    monkeypatch.setattr(sync_ib, "export_static_books", lambda *args, **kwargs: None)

    code = sync_ib.main(["--flex", str(FIXTURE)])

    assert posted[:2] == ["michael", "drew"], "Drew is still attempted after Michael fails"
    assert code != 0, "a failed POST must fail the unit"
    assert "michael" in capsys.readouterr().err


def test_a_clean_run_still_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("SLEEVE_INGEST_TOKEN", "t" * 32)
    monkeypatch.setattr(sync_ib, "post_ingest", lambda url, token, payload, timeout=20: {"ok": True})
    monkeypatch.setattr(sync_ib, "SleeveStore", lambda: SleeveStore(tmp_path))
    monkeypatch.setattr(sync_ib, "export_static_books", lambda *args, **kwargs: None)
    assert sync_ib.main(["--flex", str(FIXTURE)]) == 0
