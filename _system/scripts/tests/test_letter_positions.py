"""Named ownership claims must not depend on a stock symbol or PDF line breaks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import global_disclosures as disclosures


def test_an_empty_text_extraction_cannot_erase_archived_disclosed_positions():
    old = {
        "manager_id": "manager",
        "id": "letter",
        "vehicle_id": "fund",
        "quarter": "2020Q1",
        "source_kind": "fund_disclosure",
        "scope": "explicitly_disclosed_positions",
        "positions": [{"issuer": "Example", "weight_pct": 4.2}],
    }
    current = {**old, "positions": [], "scope": "no_explicit_positions_identified"}
    retained = disclosures.merge_disclosure_snapshots([old], [current])[0]
    assert retained["positions"] == old["positions"]
    assert retained["scope"] == old["scope"]
    assert retained["source_review"]
    other_vehicle = {**current, "vehicle_id": "other-fund"}
    assert (
        disclosures.merge_disclosure_snapshots([old], [other_vehicle])[0]["positions"]
        == []
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Our Delta Equipment position remains attractive.", {"Delta Equipment"}),
        (
            "Our largest holding, Foreign Industrial PLC, remains undervalued.",
            {"Foreign Industrial PLC"},
        ),
        ("We own shares in Continental Components.", {"Continental Components"}),
        (
            "Our position in Northern\nManufacturing remains unchanged.",
            {"Northern Manufacturing"},
        ),
        (
            "We have three businesses in our portfolio:\n\n1. Delta Equipment\n2. Continental Components\n3. Northern Manufacturing\n\nMarket outlook\nExample Corporation",
            {"Delta Equipment", "Continental Components", "Northern Manufacturing"},
        ),
        (
            "We added Continental Components this quarter. We own a small fraction of this business.",
            {"Continental Components"},
        ),
        (
            "Besides Delta Equipment and Continental Components, we own other businesses.",
            {"Delta Equipment", "Continental Components"},
        ),
        (
            "GROW2 Investors:\n\nGROW2 is our smaller fund but has the largest position in Foreign Industrial PLC.",
            {"Foreign Industrial PLC"},
        ),
    ],
)
def test_named_current_holdings_keep_unknown_symbols_and_weights(text, expected):
    rows = disclosures.extract_document_positions(text)
    assert {row["issuer"] for row in rows} == expected
    assert all(not row.get("ticker") and row["weight_pct"] is None for row in rows)
    assert all(row["weight_basis"] is None for row in rows)
    assert all(row.get("evidence_quote") for row in rows)


@pytest.mark.parametrize(
    "text",
    [
        "We sold our Delta Equipment position.",
        "We previously held shares in Continental Components.",
        "Our hypothetical Delta Equipment position would have performed well.",
        "The benchmark owns Delta Equipment.",
        "We are considering a position in Delta Equipment.",
        "We own fractions of wonderful businesses managed by great people.",
        "Our personal investment in Delta Equipment remains attractive.",
        "Our Delta Equipment position is short.",
        "EXAMPLE is a company that has a position in Delta Equipment.",
        "Our Featured Position will be discussed in the next letter.",
        "Our Private Investment Group has hired an analyst.",
        "We initiated our position in October 2018.",
        "Our position in Q1 performed well.",
        "We own Greek equities and foreign bonds.",
        "We began unloading our Delta Equipment position last year and are fully out.",
        "I regret our Delta Equipment stake. We received proceeds. Had we held on, it would be worth more today.",
        "Our watchlist contains:\n1. Delta Equipment\n2. Continental Components",
        "Our portfolio returns:\n1. Delta Equipment 10%\n2. Continental Components 9%",
        "We bought Delta Equipment years ago and later sold it. We own something else now.",
    ],
)
def test_named_holdings_do_not_promote_other_contexts(text):
    assert disclosures.extract_document_positions(text) == []


def test_symbol_metadata_and_named_claim_produce_one_position():
    text = "Our largest holding, Delta Equipment, remains undervalued."
    rows = disclosures.extract_document_positions(
        text,
        [
            {
                "ticker": "DELT",
                "action": "hold",
                "commentary": text,
            }
        ],
    )
    assert len(rows) == 1
    assert rows[0]["ticker"] == "DELT"
    assert rows[0]["issuer"] == "Delta Equipment"


def test_named_claim_keeps_the_disclosed_table_weight_and_does_not_restart_a_list():
    rows = disclosures.extract_document_positions(
        "Our Delta Equipment position remains unchanged.\n\n"
        "Top ten holdings\nDelta Equipment (DELT) 4.2%"
    )
    assert len(rows) == 1 and rows[0]["ticker"] == "DELT"
    assert rows[0]["weight_pct"] == 4.2
    assert rows[0]["weight_basis"] == "unspecified_disclosed_weight"
    rows = disclosures.extract_document_positions(
        "Businesses in our portfolio:\n1. Delta Equipment\n\n"
        "Research candidates\n1. Example Corporation"
    )
    assert [row["issuer"] for row in rows] == ["Delta Equipment"]
