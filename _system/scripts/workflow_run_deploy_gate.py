#!/usr/bin/env python3
"""Decide whether a dashboard deploy has anything to publish.

Deploys used to be gated on which upstream workflow finished. Data Pipeline
had a special case, but every Power Zone and LS-algo completion deployed --
including the ~10-second runs whose main job was skipped and which changed
nothing. Between 2026-09-18 and 09-24, 73 of 98 D1 syncs came from such no-op
runs, and a cancelled deploy run still deployed.

The gate is now content-addressed:

* ``fingerprint`` hashes the git object ids of everything a deploy publishes or
  runs (the dashboard tree, the deploy scripts, the seed's inputs) at a commit.
  Identical content gives an identical fingerprint, whichever workflow ran.
* A fully successful deploy (Pages shipped and D1 synced) records its
  fingerprint as the LAST deployed one: a tiny Actions cache entry under the
  prefix ``dashboard-deploy-last-v1-``. The gate restores the newest entry of
  that prefix (actions/cache returns the most recently created match) and
  compares. "Deployed once" is not "deployed now": a revert to content that
  was synced last week differs from the last deploy, so it deploys again.
* ``decide`` turns that into a verdict. Pushes and manual dispatches always
  deploy. A workflow_run deploys only when the fingerprint differs from the
  last deployed one. The daily schedule -- the recovery path after the 00:00
  UTC quota reset -- also deploys when that day's D1 retention has not run.
  Neither retries on the day a D1 stage was deferred for these inputs: the
  budget is spent until 00:00 UTC.

A lost cache entry costs one redundant deploy, whose D1 stages skip on their
own content checks. One race remains, and heals itself: a revert that lands
while the reverted-from content is still deploying can be judged "already
deployed" by its gate; the next trigger of any kind compares against the
finished deploy and ships it.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FINGERPRINT_VERSION = "dashboard-deploy-inputs-v1"

# What a deploy publishes or executes. The build job checks out the `pages`
# profile (_system, .github, dashboard, Makefile), so nothing outside these
# paths can reach the site or D1. The seed reads per-ticker research files
# only when present, and they never are in that profile.
DEPLOY_INPUTS = (
    "dashboard",
    "_system/data/evidence_recovery_queue.json",
    "_system/scripts/build_cloudflare_pages_site.py",
    "_system/scripts/validate_portfolio_private_boundary.py",
    "_system/scripts/export_dashboard_d1_seed.py",
    "_system/scripts/export_sleeve_d1.py",
    "_system/scripts/prune_cloudflare_d1.py",
    "_system/scripts/workflow_run_deploy_gate.py",
    "_system/scripts/ci_checkout_workspace.sh",
    "_system/scripts/ci_dashboard_deploy_mode.sh",
    ".github/workflows/dashboard-pages.yml",
    ".github/actions/deploy-cloudflare-dashboard",
    ".github/actions/publish-dashboard",
)

ALWAYS_DEPLOY_EVENTS = {"push", "workflow_dispatch"}


def object_ids(rev: str = "HEAD", paths: tuple[str, ...] = DEPLOY_INPUTS, cwd: Path | None = None) -> dict[str, str]:
    """Git object id per path at ``rev`` ("absent" when the path does not exist).

    Asks only for %(objectname), which git resolves from tree objects without
    reading the object itself, so it works in a blob-less sparse clone with no
    lazy fetch.
    """
    request = "".join(f"{rev}:{path}\n" for path in paths)
    result = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname)"],
        input=request,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    if result.returncode:
        raise SystemExit(f"git cat-file failed: {result.stderr.strip()}")
    lines = result.stdout.splitlines()
    if len(lines) != len(paths):
        raise SystemExit(f"git cat-file answered {len(lines)} of {len(paths)} paths")
    out: dict[str, str] = {}
    for path, line in zip(paths, lines):
        out[path] = "absent" if line.endswith(" missing") else line.strip()
    return out


def fingerprint(rev: str = "HEAD", paths: tuple[str, ...] = DEPLOY_INPUTS, cwd: Path | None = None) -> str:
    ids = object_ids(rev, paths, cwd)
    payload = FINGERPRINT_VERSION + "\n" + "".join(f"{path} {ids[path]}\n" for path in paths)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def decide(
    event: str,
    *,
    shipped: bool,
    synced: bool,
    deferred_today: bool,
    pruned_today: bool,
) -> tuple[bool, str]:
    """(should_deploy, reason) for one run of the dashboard deploy workflow.

    ``shipped``: the last deploy that shipped Pages shipped these inputs.
    ``synced``: the last deploy that also completed D1 synced these inputs.
    Tracked apart because a deploy can ship Pages with its D1 work deferred:
    if main then reverts, the site must follow even though D1 last synced
    the reverted-to content.
    """
    if event in ALWAYS_DEPLOY_EVENTS:
        return True, f"{event} always deploys"
    if not shipped:
        return True, "deploy inputs differ from what the site last shipped"
    if not synced:
        if deferred_today:
            return False, (
                "these inputs already shipped today with a D1 stage deferred by the daily "
                "budget; the first deploy after 00:00 UTC retries it"
            )
        return True, "the site has these inputs but D1 is not yet synced for them"
    if event == "schedule" and not pruned_today:
        return True, "inputs unchanged, but today's D1 retention has not run"
    if event in {"workflow_run", "schedule"}:
        return False, "deploy inputs unchanged: the last deploy shipped and synced exactly these"
    return True, f"unrecognized event {event!r}; deploying to be safe"


def last_deployed(path: str | None) -> str | None:
    """The fingerprint restored from the newest ``dashboard-deploy-last-v1-``
    cache entry, or None when nothing was restored."""
    if not path:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def is_synced(fingerprint: str, last: str | None) -> bool:
    """True only when the LAST fully synced deploy shipped exactly these inputs.

    Having synced these inputs at some earlier point is not enough: after a
    revert, main can match a fingerprint deployed last week while the site
    and D1 hold newer content.
    """
    return bool(fingerprint) and last == fingerprint


def _flag(value: str | None) -> bool:
    return str(value or "").strip().lower() == "true"


def _write_outputs(path: str | None, values: dict[str, str]) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    sys.stdout.write(lines)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("fingerprint", help="hash the deploy inputs at a commit")
    fp.add_argument("--rev", default="HEAD")
    fp.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))

    dc = sub.add_parser("decide", help="turn cache lookups into should_deploy")
    dc.add_argument("--event", required=True)
    dc.add_argument("--fingerprint", default="", help="this run's deploy-input fingerprint")
    dc.add_argument(
        "--last-file",
        default="",
        help="file holding the last fully synced deploy's fingerprint (restored from "
             "the newest dashboard-deploy-last-v1- cache entry); missing means unknown",
    )
    dc.add_argument(
        "--shipped-file",
        default="",
        help="file holding the last deploy's fingerprint that shipped Pages, D1 synced or "
             "not (restored from the newest dashboard-deploy-shipped-v1- cache entry)",
    )
    dc.add_argument("--deferred-hit", default="false")
    dc.add_argument("--pruned-hit", default="false")
    dc.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))

    args = parser.parse_args(argv)
    if args.command == "fingerprint":
        _write_outputs(args.github_output, {
            "hash": fingerprint(args.rev),
            "utc_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
        return 0
    last = last_deployed(args.last_file)
    shipped = last_deployed(args.shipped_file)
    deploy, reason = decide(
        args.event,
        shipped=is_synced(args.fingerprint, shipped),
        synced=is_synced(args.fingerprint, last),
        deferred_today=_flag(args.deferred_hit),
        pruned_today=_flag(args.pruned_hit),
    )
    _write_outputs(args.github_output, {
        "should_deploy": "true" if deploy else "false",
        "reason": reason,
        "last_deployed": last or "none",
        "last_shipped": shipped or "none",
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
