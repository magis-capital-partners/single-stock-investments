"""Archive public IBKR availability indications with their actual timestamps.

Public FTP is unrelated to TWS/Gateway connections. Inventory and fee quotes
are never promoted to an approved locate or backdated into historical trades.
"""

from __future__ import annotations

import argparse
import ftplib
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .borrow import _ssi_borrow
from .config import load_config
from .ledger import load_jsonl, read_json, write_json, write_jsonl

HOST = "ftp2.interactivebrokers.com"


def archive(cfg, *, input_path=None, ftp_factory=ftplib.FTP):
    raw_dir = cfg.raw_dir / "borrow"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if input_path is None:
        data, checksum = bytearray(), bytearray()
        ftp = ftp_factory()
        try:
            ftp.connect(HOST, timeout=45)
            ftp.login("shortstock", "")
            ftp.retrbinary("RETR usa.txt", data.extend)
            ftp.retrbinary("RETR usa.txt.md5", checksum.extend)
        finally:
            ftp.close()
        expected = checksum.decode("ascii").strip().split()[0].lower()
        if (
            len(expected) != 32
            or hashlib.md5(bytes(data).replace(b"\r\n", b"\n")).hexdigest() != expected
        ):
            raise ValueError("IBKR public file failed its published MD5 checksum")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        input_path = raw_dir / ("usa_" + stamp + ".txt")
        input_path.write_bytes(bytes(data))
    else:
        input_path = Path(input_path)
    rows, metadata = _ssi_borrow().parse_public_ftp(input_path)
    source_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    tickers = {r["ticker"] for r in load_jsonl(cfg.ledger_dir / "events.jsonl")}
    tickers.update(
        r["ticker"] for r in load_jsonl(cfg.ledger_dir / "announcements.jsonl")
    )
    tickers.update(_ssi_borrow().ledger_tickers())
    for row in load_jsonl(cfg.ledger_dir / "expansion_events.jsonl"):
        tickers.update(
            t
            for t in (
                row.get("ticker"),
                row.get("new_ticker"),
                row.get("database_ticker"),
            )
            if t
        )
    for row in read_json(
        cfg.local_dir / "expansion/expansion_v2/otc_daily/actions.json", []
    ):
        tickers.update(t for t in (row.get("ticker"), row.get("new_ticker")) if t)
    when = datetime.fromisoformat(metadata["as_of"].replace("Z", "+00:00"))
    recorded = datetime.now(timezone.utc).isoformat()
    selected = [
        {
            "ticker": r["ticker"],
            "as_of": r["as_of"],
            "archived_at": recorded,
            "available_shares": r["available"],
            "available_at_least": r.get("at_least", False),
            "fee_annual_fraction": r["rate_pct"] / 100
            if r["rate_pct"] is not None
            else None,
            "source": metadata["source"],
            "source_url": "ftp://" + HOST + "/usa.txt",
            "source_sha256": source_hash,
            "availability_only": True,
            "locate_approved": False,
        }
        for r in rows
        if r["ticker"] in tickers
    ]
    folder = cfg.ledger_dir / "borrow_history" / str(when.year)
    path = folder / (when.strftime("%Y-%m-%dT%H%M%SZ") + ".jsonl")
    if path.exists():
        old = load_jsonl(path)
        vintage = read_json(path.with_suffix(".meta.json"), {})
        old_hash = vintage.get("source_sha256") or (
            old[0]["source_sha256"] if old else None
        )
        if old_hash != source_hash:
            raise ValueError("An existing borrow vintage has different source bytes")
        return {"rows": len(old), "as_of": metadata["as_of"], "already_archived": True}
    write_jsonl(path, selected)
    write_json(
        path.with_suffix(".meta.json"),
        {
            "as_of": metadata["as_of"],
            "source_sha256": source_hash,
            "rows": len(selected),
            "archived_at": recorded,
            "availability_only": True,
            "locate_approved": False,
        },
    )
    write_json(
        cfg.ledger_dir / "borrow_history/latest.json",
        {
            "as_of": metadata["as_of"],
            "rows": len(selected),
            "path": path.relative_to(cfg.ledger_dir).as_posix(),
            "availability_only": True,
            "locate_approved": False,
        },
    )
    return {
        "rows": len(selected),
        "as_of": metadata["as_of"],
        "path": str(path),
        "availability_only": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    print(archive(load_config(args.config), input_path=args.input))


if __name__ == "__main__":
    main()
