"""``--since`` scoping: a weekly run must never erase the announcements it imported from the ledger.

The original ``seed`` rebuilt every announcement row from ``edgar_hits``. The
ledger does not carry those hits, so in a clean clone that rebuild would have
wiped 22.9k rows and recreated only the current window. These tests pin the
scoped behaviour of ``create_announced_only`` and the ``since`` plumbing in the
CLI.
"""
from __future__ import annotations

from datetime import date, timedelta

from reverse_splits.cli import _since, build_parser
from reverse_splits.db import init_db
from reverse_splits.ingest_splits import create_announced_only, tag_repeat_splits


def _seed(db):
    conn = init_db(db)
    conn.executemany(
        """INSERT INTO reverse_splits (cik, ticker, exchange_class, split_from, split_to, ratio, announce_date, ex_date, effective_date,
           outcome, status, confidence, needs_review, source, date_quality, notes)
           VALUES (?, ?, 'listed', 1, 1, 1, ?, ?, ?, ?, 'announced_only', 0.4, 1, 'edgar_search', 'acceptance_time', ?)""",
        [
            ("0000000001", "OLD", "2024-01-10", "2024-01-10", "2024-01-10", "announced_only", "accession=old form=8-K"),
            ("0000000002", "MID", "2026-09-01", "2026-09-01", "2026-09-01", "mention", "accession=mid form=8-K"),
            ("0000000003", "NEW", "2026-10-01", "2026-10-01", "2026-10-01", "announced_only", "accession=stale form=8-K"),
        ],
    )
    # Only hits inside the window exist locally (the weekly search), plus one old
    # hit that happens to be cached: it must not resurrect OLD a second time.
    conn.executemany(
        "INSERT INTO edgar_hits (accession, form, cik, ticker, name, filed_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("fresh", "8-K", "0000000003", "NEW", "New Co", "2026-10-01"),
            ("fresh2", "6-K", "0000000004", "NEWER", "Newer Co", "2026-10-05"),
            ("old", "8-K", "0000000001", "OLD", "Old Co", "2024-01-10"),
        ],
    )
    conn.commit()
    return conn


def test_scoped_rebuild_keeps_announcements_outside_the_window(tmp_path):
    conn = _seed(tmp_path / "rs.db")
    created = create_announced_only(conn, since="2026-09-20")
    conn.commit()
    rows = {r[0]: r for r in conn.execute("SELECT ticker, outcome, notes FROM reverse_splits WHERE status='announced_only'")}
    assert created == 2
    assert set(rows) == {"OLD", "MID", "NEW", "NEWER"}
    assert rows["OLD"][1] == "announced_only" and rows["OLD"][2] == "accession=old form=8-K"  # untouched
    assert rows["MID"][1] == "mention"  # enrichment outside the window survives
    assert rows["NEW"][2] == "accession=fresh form=8-K"  # rebuilt from the fresh hit
    assert rows["NEWER"][2] == "accession=fresh2 form=6-K"
    conn.close()


def test_unscoped_rebuild_still_rebuilds_everything(tmp_path):
    conn = _seed(tmp_path / "rs.db")
    created = create_announced_only(conn)
    conn.commit()
    tickers = sorted(r[0] for r in conn.execute("SELECT ticker FROM reverse_splits WHERE status='announced_only'"))
    assert created == 3
    assert tickers == ["NEW", "NEWER", "OLD"]  # MID had no local hit and is gone, as before the migration
    conn.close()


def test_announcements_near_an_effective_split_are_not_duplicated(tmp_path):
    conn = _seed(tmp_path / "rs.db")
    conn.execute(
        """INSERT INTO reverse_splits (cik, ticker, exchange_class, split_from, split_to, ratio, announce_date, ex_date, effective_date,
           outcome, status, source) VALUES ('0000000004', 'NEWER', 'listed', 10, 1, 0.1, '2026-10-05', '2026-11-01', '2026-11-01', 'effective', 'seeded', 'yfinance')"""
    )
    conn.commit()
    create_announced_only(conn, since="2026-09-20")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM reverse_splits WHERE ticker='NEWER' AND status='announced_only'").fetchone()[0] == 0
    assert tag_repeat_splits.__name__ == "tag_repeat_splits"
    conn.close()


def test_cli_since_days_becomes_a_date_and_defaults_to_none():
    parser = build_parser()
    assert _since(parser.parse_args(["seed"])) is None
    scoped = parser.parse_args(["seed", "--since-days", "21"])
    assert _since(scoped) == date.today() - timedelta(days=21)
    for command in ("clocks", "prices", "pipeline"):
        assert _since(parser.parse_args([command, "--since-days", "7"])) == date.today() - timedelta(days=7)
