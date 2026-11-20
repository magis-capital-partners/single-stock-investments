"""Borrow producer: IBKR's public short-stock indications, keyed by conid.

Source: IBKR's anonymous public file (``usa.txt``), the same one Box R polls.
Each row carries the file's own ``#BOF`` clock as ``at``, so the executor's
``borrow_age_seconds`` (1800 s) is measured from IBKR's publication, not from
when we downloaded it. A conid absent from the file gets no row: missing
inventory is never written as zero shares or a zero rate.

These are indications, not a locate. On NY4 the executor also caps
``available_shares`` by the live shortable-shares tick (generic tick 236) in
``PaperIBKR.borrow``, and WhatIf remains the margin proof.
"""

from __future__ import annotations

VERSION = "rs_borrow_producer.v1"


def build_borrow(ibkr, watch, now):
    """``watch`` maps conid -> ticker. Returns ``(rows, report)``."""
    rows, report = {}, []
    for conid, ticker in sorted(watch.items()):
        matches = [r for r in ibkr["by_conid"].get(conid, []) if r["currency"] == "USD"]
        if len(matches) != 1:
            report.append(
                {
                    "conid": conid,
                    "ticker": ticker,
                    "missing": "not_in_public_file" if not matches else "ambiguous",
                }
            )
            continue
        r = matches[0]
        if r["symbol"] != ticker:
            report.append({"conid": conid, "ticker": ticker, "missing": "symbol_differs"})
            continue
        if r["apr"] is None or r["available_shares"] is None:
            report.append({"conid": conid, "ticker": ticker, "missing": "rate_or_inventory_na"})
            continue
        rows[str(conid)] = {
            "conid": conid,
            "at": ibkr["as_of"],
            "apr": r["apr"],
            "available_shares": r["available_shares"],
            "available_at_least": r["available_at_least"],
            "rebate_apr": r["rebate_apr"],
            "ticker": ticker,
            "source": "ibkr_public_shortstock_file",
            "source_url": ibkr["source_url"],
            "source_sha256": ibkr["source_sha256"],
            "source_line": r["source_line"],
            "observed_at": ibkr["observed_at"],
            "availability_only": True,
            "locate_approved": False,
            "producer": VERSION,
        }
        report.append({"conid": conid, "ticker": ticker, "apr": r["apr"]})
    return rows, report
