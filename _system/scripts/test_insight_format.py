#!/usr/bin/env python3
from insight_format import format_letter_position, is_letter_table_debris, split_insight_rows


def test_debris_detection():
    text = "(18%) (34%) (47%) MSFT TSX:CSU NOW INTU WDAY APP"
    assert is_letter_table_debris(text)


def test_format_letter_position_debris():
    title, summary = format_letter_position(
        ticker="CSU",
        fund="Cat Rock",
        action="discussed",
        quarter="2026Q1",
        commentary="(18%) (34%) (47%) MSFT TSX:CSU NOW INTU WDAY APP MNDY TEAM",
    )
    assert "Cat Rock" in title
    assert "CSU" in title
    assert "table" in summary.lower()


def test_split_rows():
    rows = [
        {"source": "macro", "claim": "x"},
        {"source": "superinvestor_letter", "claim": "y"},
    ]
    specific, portfolio = split_insight_rows(rows)
    assert len(specific) == 1
    assert len(portfolio) == 1


if __name__ == "__main__":
    test_debris_detection()
    test_format_letter_position_debris()
    test_split_rows()
    print("ok")
