#!/usr/bin/env python3
"""Tell Slack that a dashboard deploy shipped the site but deferred D1 work.

Called by the deploy workflow after the static Pages deploy, when a D1 stage
was deferred by the daily budget guard or the free-tier quota. The workflow
fails the job right after this runs; this script only reports. A Slack outage
or a missing webhook must never hide the failure, so posting problems become
warnings and the exit code is always 0.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Callable

Opener = Callable[[urllib.request.Request], object]


def build_message(
    *,
    repository: str,
    run_url: str,
    stages: str,
    reason: str,
    utc_date: str,
    rows_read: str = "",
    rows_written: str = "",
) -> dict:
    stage_list = ", ".join(part.strip() for part in stages.split(",") if part.strip()) or "unknown"
    lines = [
        f":warning: *Dashboard deploy deferred D1 work* ({repository}, {utc_date} UTC)",
        f"Deferred: {stage_list}",
        f"Why: {reason or 'not reported'}",
        "The static site deployed. The deferred stages retry on the first deploy after "
        "00:00 UTC (the daily schedule guarantees one); dashboard API data stays at the "
        "last successful sync until then.",
    ]
    if rows_read or rows_written:
        lines.append(f"This deploy used {rows_read or '?'} rows read / {rows_written or '?'} rows written.")
    lines.append(f"Run: {run_url}")
    text = "\n".join(lines)
    return {"text": text.encode("ascii", "replace").decode("ascii")}


def post(webhook: str, payload: dict, opener: Opener | None = None) -> str | None:
    """Post to a Slack incoming webhook; returns an error description or None."""
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = (opener or (lambda req: urllib.request.urlopen(req, timeout=15)))(request)  # noqa: S310
        status = getattr(response, "status", 200)
        return None if 200 <= int(status) < 300 else f"HTTP {status}"
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}"
    except (OSError, ValueError) as error:
        return type(error).__name__


def main(argv: list[str] | None = None, opener: Opener | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--stages", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--utc-date", default="")
    parser.add_argument("--rows-read", default="")
    parser.add_argument("--rows-written", default="")
    args = parser.parse_args(argv)

    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    payload = build_message(
        repository=repository,
        run_url=f"{server}/{repository}/actions/runs/{run_id}",
        stages=args.stages,
        reason=args.reason,
        utc_date=args.utc_date,
        rows_read=args.rows_read,
        rows_written=args.rows_written,
    )
    print(payload["text"])
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print("::warning::SLACK_WEBHOOK_URL is not set; the deferral alert was not posted.")
        return 0
    error = post(webhook, payload, opener)
    if error:
        print(f"::warning::Slack alert was not delivered ({error}).")
    else:
        print("Slack alert posted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
