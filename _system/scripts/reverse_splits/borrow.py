"""Borrow evidence: Client Portal availability CSV imports and the sizing cap.

The original package also snapshotted shortable shares over a live broker
session. That path was deleted in the SSI migration: the NY4 Gateway carries
the live SPX executor and this repository never talks to it
(``CLAUDE.md``, IB Gateway rules). Borrow enters only as a file: a CSV export
from the IBKR Client Portal Short-Securities Availability page, with the
export's own timestamp when it carries one, or IBKR's public short-stock file
(``usa.txt``), parsed by SSI's ``refresh_short_alpha_borrow`` so both desks
read one number.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import SCRIPTS_DIR, Config, load_config
from .db import init_db
from .utils import normalize_ticker


def _ssi_borrow():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import refresh_short_alpha_borrow  # noqa: PLC0415

    return refresh_short_alpha_borrow


def import_ibkr_public_ftp(path: Path, cfg: Config | None = None) -> int:
    """Import IBKR's public ``usa.txt``: one snapshot row per symbol at the
    file's own ``#BOF`` time. A ``>10000000`` floor is stored as 10000000 and
    marked in ``notes``; an ``NA`` fee stays NULL."""
    rows, meta = _ssi_borrow().parse_public_ftp(path)
    return persist_snapshots([
        {
            "asof_ts": row["as_of"],
            "ticker": normalize_ticker(row["ticker"]),
            "shortable_shares": row["available"],
            "fee_rate": row["rate_pct"] / 100.0 if row["rate_pct"] is not None else None,
            "source": meta["source"],
            "notes": Path(path).name + (" available_at_least" if row.get("at_least") else ""),
        }
        for row in rows
        if normalize_ticker(row["ticker"])
    ], cfg)


def persist_snapshots(rows: list[dict], cfg: Config | None = None) -> int:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    n = 0
    for r in rows:
        conn.execute(
            """
            INSERT INTO borrow_snapshots (asof_ts, ticker, shortable_shares, fee_rate, source, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                r["asof_ts"],
                r["ticker"],
                r.get("shortable_shares"),
                r.get("fee_rate"),
                r.get("source") or "ibkr_csv",
                r.get("notes"),
            ),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def import_ibkr_slb_csv(path: Path, cfg: Config | None = None) -> int:
    """Import a Client Portal Short-Securities Availability / SLB CSV export.

    Expected columns (flexible): Symbol/Ticker, Fee Rate / Borrow Rate,
    Available / Quantity, and optionally an ``asof_ts`` / ``timestamp`` column.
    Percent quotes are divided by 100; a decimal fraction needs a column
    labelled ``fraction`` or ``decimal``. Without a supplied timestamp the
    import time describes a current snapshot, never a historical locate.
    IBKR's public ``usa.txt`` is detected and handed to ``import_ibkr_public_ftp``.
    """
    if _ssi_borrow().is_public_ftp_file(path):
        return import_ibkr_public_ftp(path, cfg)
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    asof = datetime.now(timezone.utc).isoformat()
    n = 0
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lower = {k.lower().strip(): v for k, v in row.items() if k}
            ticker = normalize_ticker(lower.get("symbol") or lower.get("ticker") or lower.get("underlying"))
            if not ticker:
                continue
            row_asof = next(
                (str(lower[k]).strip() for k in ("asof_ts", "as_of", "asof", "as of timestamp", "timestamp") if lower.get(k)),
                asof,
            )
            avail = None
            fee = None
            for k, v in lower.items():
                if avail is None and any(x in k for x in ("avail", "quantity", "shortable", "shares")):
                    try:
                        avail = float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        pass
                if fee is None and ("fee" in k or ("borrow" in k and "rate" in k)):
                    try:
                        fee = float(str(v).replace("%", "").replace(",", ""))
                        # Portal exports quote percent even below 1.5%. Decimal
                        # rates must use an explicit fraction/decimal column.
                        if "%" in str(v) or not any(unit in k for unit in ("fraction", "decimal")):
                            fee = fee / 100.0
                    except (TypeError, ValueError):
                        pass
            conn.execute(
                """
                INSERT INTO borrow_snapshots (asof_ts, ticker, shortable_shares, fee_rate, source, notes)
                VALUES (?, ?, ?, ?, 'ibkr_csv', ?)
                """,
                (row_asof, ticker, avail, fee, Path(path).name),
            )
            n += 1
    conn.commit()
    conn.close()
    return n


def latest_borrow(conn, ticker: str):
    return conn.execute(
        """
        SELECT * FROM borrow_snapshots
        WHERE ticker=?
        ORDER BY asof_ts DESC LIMIT 1
        """,
        (ticker,),
    ).fetchone()


def position_cap_shares(
    price: float,
    target_notional: float,
    shortable_shares: float | None,
    max_participation: float,
    finra_si: float | None = None,
    adv: float | None = None,
) -> tuple[float, str, int]:
    """Return (shares, capacity_source, truncated_flag)."""
    if price <= 0:
        return 0.0, "none", 1
    desired = target_notional / price
    cap = desired
    source = "target_notional"
    truncated = 0
    if shortable_shares is not None:
        loc = shortable_shares * max_participation
        if loc < cap:
            cap = max(0.0, loc)
            source = "ibkr_shortable"
            truncated = 1
    elif adv is not None:
        # FINRA short interest is positioning, not inventory. It is recorded on
        # the trade as utilization and does not set the share count. `finra_si`
        # stays in the signature so older callers still load.
        loc = adv * max_participation
        if loc < cap:
            cap = max(0.0, loc)
            source = "adv_proxy"
            truncated = 1
    return float(cap), source, truncated
