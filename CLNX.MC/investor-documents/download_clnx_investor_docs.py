#!/usr/bin/env python3
"""Download Cellnex Telecom, S.A. (CLNX.MC) IR PDFs. Scaffold; URL list not yet configured."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKER = "CLNX.MC"
IR_DIR = Path(__file__).resolve().parent / "ir-cellnex"
LOG_FILE = ROOT / TICKER / "_download_log.txt"


def main() -> None:
    IR_DIR.mkdir(parents=True, exist_ok=True)
    line = (
        f"{datetime.now(timezone.utc).isoformat()} "
        f"{TICKER} uk_ir scaffold; no PDF URLs configured"
    )
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


if __name__ == "__main__":
    main()
