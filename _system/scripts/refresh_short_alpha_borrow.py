#!/usr/bin/env python3
"""Refresh Short Alpha borrow from an IBKR borrow file. File in, file out.

Three inputs are accepted and detected from the file itself:

* the simple normalized export ``symbol,borrow_rate_pct,as_of`` (unchanged);
* the IBKR Client Portal Short-Securities-Availability (SLB) CSV, with any of
  ``symbol``/``ticker``, ``fee``/``borrow_rate``/``rate``/``indicative fee``,
  ``available``/``shortable``/``quantity`` and ``asof_ts``/``timestamp``/``as_of``
  (headers matched case-insensitively);
* IBKR's public short-stock availability file, ``usa.txt`` on
  ``ftp2.interactivebrokers.com`` (user ``shortstock``, empty password; no
  account), pipe-delimited between ``#BOF|YYYY.MM.DD|HH:MM:SS`` and
  ``#EOF|<records>``. It is the same SLB inventory the Portal shows, refreshed
  intraday. ``#BOF`` is US/Eastern and becomes every row's UTC ``as_of``;
  ``FEERATE`` is percent per year; ``AVAILABLE`` of ``>10000000`` is a floor,
  kept as 10000000 with ``at_least``. A record count that disagrees with
  ``#EOF`` is a truncated download and is refused. Fetch it with
  ``curl --user shortstock: -o usa.txt ftp://ftp2.interactivebrokers.com/usa.txt``
  (``usa.txt.md5`` is the MD5 of the file with LF line endings).

Rate convention (the rsdb ``ibkr_borrow.py`` CSV importer, kept identical so
the two desks read one number): the Portal quotes percent even below 1.5%, so a
rate column is a percent, ``1.2%`` included; a decimal fraction is read only
from a column whose header says ``fraction`` or ``decimal``. Output is always
``rate_pct`` in percent. A supplied ``asof_ts``/``timestamp``/``as_of`` is
retained per row; otherwise the import time describes a current snapshot.

The export can contain any universe; this writer retains the Short Alpha
tickers (candidates plus the open book), so new names are picked up on the
next refresh without a code change. Missing names are pending, never zero.

This script never contacts the IB Gateway, TWS, or any API socket, and it
downloads nothing. Borrow arrives as a file: a Client Portal export or the
public FTP file (CLAUDE.md rules 9 and 10).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = ROOT / "_system" / "research" / "short-alpha"
POSITIONS = LEDGER_DIR / "ideas.json"
CANDIDATES = LEDGER_DIR / "candidates.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_alpha_borrow.json"
EXCLUDED = {"ECHX"}
SOURCE_CLIENT_PORTAL = "ibkr_client_portal_csv"
SOURCE_NORMALIZED = "ibkr_normalized_csv"
SOURCE_PUBLIC_FTP = "ibkr_public_ftp"
SOURCE_LABELS = {
    SOURCE_CLIENT_PORTAL: "IBKR Client Portal availability CSV",
    SOURCE_NORMALIZED: "IBKR borrow export",
    SOURCE_PUBLIC_FTP: "IBKR public short-stock availability file",
}
FTP_CLOCK = ZoneInfo("America/New_York")

SYMBOL_KEYS = ("symbol", "ticker", "underlying")
LEGACY_RATE_KEY = "borrow_rate_pct"
RATE_KEYS = ("indicative fee", "indicative_fee", "fee rate", "fee_rate", "borrow rate", "borrow_rate", "fee", "rate")
AVAILABLE_KEYS = ("available", "shortable", "quantity", "available quantity", "shares available", "shares")
ASOF_KEYS = ("asof_ts", "as_of", "asof", "as of timestamp", "as of", "timestamp")
FRACTION_UNITS = ("fraction", "decimal")


class BorrowCsvError(ValueError):
    """The CSV header does not describe a borrow file we can read."""


def _norm(header: str) -> str:
    return re.sub(r"\s+", " ", str(header or "").replace("﻿", "").strip().lower())


def _pick(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    """First header equal to a candidate, then first header containing one."""
    normalized = {_norm(h): h for h in headers if h}
    for key in candidates:
        if key in normalized:
            return normalized[key]
    for key in candidates:
        for norm, raw in normalized.items():
            if key in norm:
                return raw
    return None


def _number(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").replace("%", "").strip()
    if not text or text.lower() in {"n/a", "na", "none", "null", "-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def rate_pct_from(value, header: str) -> float | None:
    """Percent from a rate cell. A ``%`` or an ordinary rate header means percent; only a
    column labelled fraction/decimal carries a decimal fraction (0.012 -> 1.2%)."""
    number = _number(value)
    if number is None:
        return None
    text = str(value)
    if "%" in text:
        return number
    if any(unit in _norm(header) for unit in FRACTION_UNITS):
        return number * 100.0
    return number


def detect_columns(headers: list[str]) -> dict:
    symbol = _pick(headers, SYMBOL_KEYS)
    if not symbol:
        raise BorrowCsvError(f"No symbol/ticker column in {headers}")
    legacy = _pick(headers, (LEGACY_RATE_KEY,))
    rate = legacy or _pick(headers, RATE_KEYS)
    if not rate:
        raise BorrowCsvError(f"No fee/borrow_rate/rate column in {headers}")
    return {
        "symbol": symbol,
        "rate": rate,
        "legacy": bool(legacy) and _norm(legacy) == LEGACY_RATE_KEY,
        "available": _pick(headers, AVAILABLE_KEYS),
        "as_of": _pick(headers, ASOF_KEYS),
    }


def parse_borrow_csv(path: Path, imported_at: str | None = None) -> tuple[list[dict], dict]:
    """Rows of ``{ticker, rate_pct, available, as_of}`` plus the detected column map."""
    imported_at = imported_at or datetime.now(timezone.utc).isoformat()
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        columns = detect_columns(headers)
        rows: list[dict] = []
        for raw in reader:
            ticker = str(raw.get(columns["symbol"]) or "").upper().strip()
            if not ticker:
                continue
            if columns["legacy"]:
                rate = _number(raw.get(columns["rate"]))
            else:
                rate = rate_pct_from(raw.get(columns["rate"]), columns["rate"])
            available = _number(raw.get(columns["available"])) if columns["available"] else None
            as_of = str(raw.get(columns["as_of"]) or "").strip() if columns["as_of"] else ""
            rows.append({
                "ticker": ticker,
                "rate_pct": rate,
                "available": int(available) if available is not None else None,
                "as_of": as_of or imported_at,
            })
    columns["source"] = SOURCE_NORMALIZED if columns["legacy"] else SOURCE_CLIENT_PORTAL
    return rows, columns


def is_public_ftp_file(path: Path) -> bool:
    with Path(path).open(encoding="utf-8-sig", errors="replace") as handle:
        return handle.readline().startswith("#BOF|")


def parse_public_ftp(path: Path) -> tuple[list[dict], dict]:
    """Rows of ``{ticker, rate_pct, available, as_of}`` (plus ``at_least`` on a
    floored availability) from IBKR's public ``usa.txt``."""
    as_of = None
    header: list[str] | None = None
    declared: int | None = None
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            line = line.rstrip("\r\n")
            if line.startswith("#BOF|"):
                day, clock = line.split("|")[1:3]
                stamp = datetime.strptime(f"{day} {clock}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=FTP_CLOCK)
                as_of = stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            elif line.startswith("#SYM|"):
                header = line[1:].rstrip("|").split("|")
            elif line.startswith("#EOF|"):
                declared = int(line.split("|")[1])
            elif line and header:
                record = dict(zip(header, line.rstrip("|").split("|")))
                ticker = str(record.get("SYM") or "").upper().strip()
                if not ticker:
                    continue
                shares = str(record.get("AVAILABLE") or "").strip()
                available = _number(shares.lstrip(">"))
                row = {
                    "ticker": ticker,
                    "rate_pct": _number(record.get("FEERATE")),
                    "available": int(available) if available is not None else None,
                    "as_of": as_of,
                }
                if shares.startswith(">"):
                    row["at_least"] = True
                rows.append(row)
    if as_of is None or header is None:
        raise BorrowCsvError(f"{path} has no #BOF/#SYM header; not an IBKR short-stock file")
    if declared is None or declared != len(rows):
        raise BorrowCsvError(f"{path}: {len(rows)} records but #EOF declares {declared}; the download is truncated")
    return rows, {"source": SOURCE_PUBLIC_FTP, "as_of": as_of, "declared": declared}


def parse_borrow_file(path: Path) -> tuple[list[dict], dict]:
    return parse_public_ftp(path) if is_public_ftp_file(path) else parse_borrow_csv(path)


def ledger_tickers() -> set[str]:
    tickers: set[str] = set()
    for path, key in ((POSITIONS, "ideas"), (CANDIDATES, "candidates")):
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        tickers.update(str(row.get("ticker") or "").upper() for row in doc.get(key) or [] if row.get("ticker"))
    return tickers - EXCLUDED


def build_payload(rows: list[dict], tickers: set[str] | None, source: str, input_name: str, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat()
    label = SOURCE_LABELS.get(source, SOURCE_LABELS[SOURCE_NORMALIZED])
    rates: dict[str, dict] = {}
    availability: dict[str, dict] = {}
    for row in rows:
        ticker = row["ticker"]
        if tickers is not None and ticker not in tickers:
            continue
        if row.get("rate_pct") is not None:
            rates[ticker] = {"rate_pct": float(row["rate_pct"]), "as_of": row.get("as_of"), "status": "available", "source": label}
        if row.get("available") is not None:
            shares = int(row["available"])
            availability[ticker] = {"shares": shares, "as_of": row.get("as_of"), "status": "available" if shares > 0 else "none_reported", "source": label}
            if row.get("at_least"):
                availability[ticker]["at_least"] = True
    return {
        "schema_version": "1.1",
        "provider": "IBKR",
        "source": source,
        "input": input_name,
        "as_of": now,
        "rates": rates,
        "availability": availability,
        # The ledger names this file was checked against: one absent from rates
        # and availability is not in IBKR's file (no lendable shares there), as
        # opposed to a name added after this refresh, which is still pending.
        "checked": sorted(tickers) if tickers is not None else [],
        "note": (
            "A checked name missing from the file has no IBKR lendable shares or is not a US listing IBKR lends; "
            "a name added later is pending. Neither is a zero fee. Availability is a reading on a date, not a locate. "
            "Rates are percent per year."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="IBKR public usa.txt, Client Portal availability CSV, or normalized borrow CSV")
    parser.add_argument("--output", type=Path, default=OUTPUT, help=f"Default {OUTPUT.relative_to(ROOT).as_posix()}")
    parser.add_argument("--all", action="store_true", help="Keep every symbol instead of only the Short Alpha ledger")
    args = parser.parse_args()
    rows, columns = parse_borrow_file(args.input)
    payload = build_payload(rows, None if args.all else ledger_tickers(), columns["source"], args.input.name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output} ({len(payload['rates'])} rates, {len(payload['availability'])} availability rows "
        f"from {len(rows)} input rows; source {columns['source']})"
    )


if __name__ == "__main__":
    main()
