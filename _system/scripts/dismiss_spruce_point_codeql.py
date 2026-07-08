#!/usr/bin/env python3
"""Dismiss open CodeQL alerts in archived Spruce Point HTML."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = "magis-capital-partners/single-stock-investments"
BODY = json.dumps(
    {
        "state": "dismissed",
        "dismissed_reason": "won't fix",
        "dismissed_comment": "Archived Spruce Point reference HTML; not live application code.",
    }
).encode()


def main() -> int:
    dismissed = 0
    failed = 0
    page = 1
    while True:
        out = subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{REPO}/code-scanning/alerts?state=open&per_page=100&page={page}",
            ]
        )
        alerts = json.loads(out)
        if not alerts:
            break
        for alert in alerts:
            path = alert.get("most_recent_instance", {}).get("location", {}).get("path", "")
            if "spruce_point" not in path:
                continue
            num = alert["number"]
            proc = subprocess.run(
                [
                    "gh",
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{REPO}/code-scanning/alerts/{num}",
                    "--input",
                    "-",
                ],
                input=BODY,
                capture_output=True,
            )
            if proc.returncode == 0:
                dismissed += 1
            else:
                failed += 1
                print(proc.stderr.decode(), file=sys.stderr)
        if len(alerts) < 100:
            break
        page += 1
    print(f"Dismissed {dismissed}, failed {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
