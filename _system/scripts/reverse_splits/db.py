"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS issuers (
    cik TEXT PRIMARY KEY,
    name TEXT,
    primary_ticker TEXT,
    exchange_class TEXT CHECK (exchange_class IN ('listed', 'otc', 'unknown')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reverse_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cik TEXT,
    ticker TEXT NOT NULL,
    exchange TEXT,
    exchange_class TEXT CHECK (exchange_class IN ('listed', 'otc', 'unknown')),
    split_from REAL NOT NULL,
    split_to REAL NOT NULL,
    ratio REAL NOT NULL,
    first_proxy_date TEXT,
    announce_date TEXT,
    vote_date TEXT,
    ratio_set_date TEXT,
    effective_date TEXT,
    ex_date TEXT NOT NULL,
    prior_rs_count INTEGER DEFAULT 0,
    cohort TEXT CHECK (cohort IN ('first', 'second', 'third_plus')),
    status TEXT DEFAULT 'seeded',
    confidence REAL DEFAULT 0.5,
    needs_review INTEGER DEFAULT 0,
    source TEXT,
    notes TEXT,
    outcome TEXT DEFAULT 'effective',
    vote_path TEXT,
    accept_time TEXT,
    announced_ex_date TEXT,
    announced_ratio REAL,
    jump_status TEXT,
    jump_observed REAL,
    date_quality TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE (ticker, ex_date, split_from, split_to)
);

CREATE INDEX IF NOT EXISTS idx_rs_cik ON reverse_splits(cik);
CREATE INDEX IF NOT EXISTS idx_rs_ex_date ON reverse_splits(ex_date);
CREATE INDEX IF NOT EXISTS idx_rs_ticker ON reverse_splits(ticker);

CREATE TABLE IF NOT EXISTS filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES reverse_splits(id) ON DELETE CASCADE,
    accession TEXT,
    form TEXT,
    filed_at TEXT,
    url TEXT,
    role TEXT CHECK (role IN ('proxy', 'announce', 'vote', 'ratio_set', 'effective', 'other')),
    excerpt TEXT,
    UNIQUE (event_id, accession, role)
);

CREATE TABLE IF NOT EXISTS prices_daily (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    adj_close REAL,
    unadj_close REAL,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices_daily(date);

-- Reg SHO Rule 201 state at the open, per (ticker, day): rows exist only for
-- restricted days (databento_prices.load_ssr).
CREATE TABLE IF NOT EXISTS ssr_flags (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    source TEXT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS finra_short_interest (
    ticker TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    short_interest REAL,
    avg_daily_volume REAL,
    days_to_cover REAL,
    source_file TEXT,
    PRIMARY KEY (ticker, settlement_date)
);

CREATE TABLE IF NOT EXISTS borrow_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asof_ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    shortable_shares REAL,
    fee_rate REAL,
    source TEXT DEFAULT 'ibkr',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_borrow_ticker ON borrow_snapshots(ticker, asof_ts);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    label TEXT,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES reverse_splits(id) ON DELETE CASCADE,
    entry_signal TEXT NOT NULL,
    entry_date TEXT,
    exit_date TEXT,
    horizon_days INTEGER,
    entry_price REAL,
    exit_price REAL,
    shares REAL,
    notional REAL,
    gross_return REAL,
    fee_scenario REAL,
    net_return REAL,
    capacity_source TEXT,
    short_interest REAL,
    shortable_shares REAL,
    truncated INTEGER DEFAULT 0,
    cohort TEXT,
    exchange_class TEXT
);

CREATE INDEX IF NOT EXISTS idx_bt_run ON backtest_trades(run_id);

CREATE TABLE IF NOT EXISTS edgar_hits (
    accession TEXT NOT NULL,
    form TEXT NOT NULL,
    cik TEXT,
    ticker TEXT,
    name TEXT,
    filed_at TEXT,
    accept_time TEXT,
    substantive INTEGER DEFAULT 0,
    cancelled INTEGER DEFAULT 0,
    parsed_ratio REAL,
    parsed_ex_date TEXT,
    vote_path TEXT,
    text_parsed INTEGER DEFAULT 0,
    PRIMARY KEY (accession, form)
);

CREATE INDEX IF NOT EXISTS idx_hits_cik ON edgar_hits(cik);

CREATE TABLE IF NOT EXISTS book_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    label TEXT,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS book_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES book_runs(id) ON DELETE CASCADE,
    event_id INTEGER,
    ticker TEXT,
    name TEXT,
    cohort TEXT,
    exchange_class TEXT,
    outcome TEXT,
    signal TEXT,
    entry_date TEXT,
    exit_date TEXT,
    entry_fill REAL,
    exit_fill REAL,
    shares REAL,
    notional REAL,
    gross_pnl REAL,
    fee_pnl REAL,
    net_pnl REAL,
    net_return REAL,
    forced_cover INTEGER,
    jump_status TEXT,
    hold_days INTEGER,
    adv_shares REAL,
    exit_breach INTEGER,
    borrow_policy TEXT,
    fee_annual REAL,
    peer_ticker TEXT,
    peer_return REAL,
    control_ticker TEXT,
    control_return REAL,
    date_quality TEXT
);

CREATE INDEX IF NOT EXISTS idx_book_trades_run ON book_trades(run_id);

CREATE TABLE IF NOT EXISTS book_equity (
    run_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    equity REAL,
    cash REAL,
    open_names INTEGER,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE IF NOT EXISTS book_funnel (
    run_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    n INTEGER,
    PRIMARY KEY (run_id, stage)
);

CREATE TABLE IF NOT EXISTS control_prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (ticker, date)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_SPLIT_COLUMNS = {
    "outcome": "TEXT DEFAULT 'effective'",
    "vote_path": "TEXT",
    "accept_time": "TEXT",
    "announced_ex_date": "TEXT",
    "announced_ratio": "REAL",
    "jump_status": "TEXT",
    "jump_observed": "REAL",
    "date_quality": "TEXT",
}


def migrate(conn: sqlite3.Connection) -> None:
    have = {row[1] for row in conn.execute("PRAGMA table_info(reverse_splits)")}
    for name, decl in _SPLIT_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE reverse_splits ADD COLUMN {name} {decl}")
    conn.executescript(SCHEMA)
    for table, columns in {
        "book_runs": {"analysis_json": "TEXT", "source_manifest_json": "TEXT"},
        "book_trades": {"evidence_json": "TEXT"},
        "book_equity": {"margin_required": "REAL", "gross_exposure": "REAL", "margin_breach": "INTEGER"},
    }.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    migrate(conn)
    return conn


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
