#!/usr/bin/env python3
"""CI guard: cloud Marvin entrypoints must use cloud_marvin_runbook.md."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MJS = ROOT / "_system" / "scripts" / "marvin_deep_dive.mjs"
RUNBOOK = ROOT / "_system" / "prompts" / "cloud_marvin_runbook.md"
REFRESH = ROOT / "_system" / "scripts" / "marvin_cloud_refresh.py"


def main() -> int:
    errors: list[str] = []
    if not RUNBOOK.exists():
        errors.append(f"missing {RUNBOOK.relative_to(ROOT)}")
    if not REFRESH.exists():
        errors.append(f"missing {REFRESH.relative_to(ROOT)}")
    if MJS.exists():
        text = MJS.read_text(encoding="utf-8")
        if "cloud_marvin_runbook.md" not in text:
            errors.append("marvin_deep_dive.mjs must read cloud_marvin_runbook.md")
        if "marvin_cloud_refresh.py" not in text:
            errors.append("marvin_deep_dive.mjs must reference marvin_cloud_refresh.py")
        if "company-deep-dive.md" in text and "cloud_marvin_runbook" not in text:
            errors.append("marvin_deep_dive.mjs should not load legacy company-deep-dive.md alone")
    else:
        errors.append("missing marvin_deep_dive.mjs")

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 1
    print("OK: cloud Marvin prompts in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
