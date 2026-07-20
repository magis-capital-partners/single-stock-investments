#!/usr/bin/env python3
"""Placeholder IR harvest for PSH. Prefer Vicki/browser or manual PDF drop."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "PSH" / "_download_log.txt"
IR = ['https://pershingsquareholdings.com/', 'https://pershingsquareholdings.com/wp-content/uploads/']
LOG.write_text(
    f"{__import__('datetime').datetime.utcnow().isoformat()}Z placeholder; IR roots={IR}\n",
    encoding="utf-8",
)
print("IR harvest placeholder — drop PDFs under PSH/ and re-run indexes")
