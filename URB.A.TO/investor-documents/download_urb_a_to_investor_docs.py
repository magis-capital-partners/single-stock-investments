#!/usr/bin/env python3
"""Placeholder IR harvest for URB.A.TO. Prefer Vicki/browser or manual PDF drop."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "URB.A.TO" / "_download_log.txt"
IR = ['https://www.urbanacorp.com/', 'https://www.urbanacorp.com/net-asset-reports/']
LOG.write_text(
    f"{__import__('datetime').datetime.utcnow().isoformat()}Z placeholder; IR roots={IR}\n",
    encoding="utf-8",
)
print("IR harvest placeholder — drop PDFs under URB.A.TO/ and re-run indexes")
