"""RS executor CLI. No network by default.

Paper connects only with --connect-paper. The live endpoint (the shared NY4
Gateway, registered reverse-split client) connects only with --connect-live and
then runs in SHADOW unless the owner arm file is valid (see arm.py).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from .arm import arm_state
from .book import PREFIX as BOOK_PREFIX, BookMargin
from .claims import ClaimBook
from .engine import Executor
from .ibkr import PaperIBKR
from .inbox import proposals, read_https, read_json, require_fresh_operations
from .journal import Journal
from .notify import deliver_alerts
from .operations_feed import read_local
from .policy import Policy
from .probe import probe, require_local_ib_listener
from .safety import LIVE_APPROVAL, RS_SYSTEM, SafetyError, endpoint_from_config, fresh

# Owner decisions a live config must state explicitly (never template defaults).
LIVE_REQUIRED_POLICY = (
    "target_notional", "max_name_notional", "max_gross_notional", "max_names",
    "spx_reserve", "cash_buffer", "daily_loss_limit", "cushion_halt",
    "cushion_flatten",
)
LIVE_REQUIRED_PATHS = ("claims_dir", "book_margin_root", "book_publish_root", "arm_file")


def check_live_config(config, endpoint):
    if not endpoint.live:
        return
    missing = [k for k in LIVE_REQUIRED_POLICY if config["policy"].get(k) is None]
    live = config.get("live") or {}
    missing += [k for k in LIVE_REQUIRED_PATHS if not live.get(k)]
    if live.get("spx_book_reserve_fraction") is None:
        missing.append("spx_book_reserve_fraction")
    if missing:
        raise SafetyError("live config must state: " + ", ".join(missing))
    if config["policy"].get("pre_action_exit") is not True:
        # Holding through the split can change the conid; SPX's ETF stock proof
        # holds entries on unidentified stock rows (2026-11-09 incident shape).
        raise SafetyError("live requires pre_action_exit: true")


def _readable_tree(root):
    """The SPX claim tree must be listable, and so must its newest day with
    every claim file in it: that proves the install's read grant reaches the
    directories SPX creates each day, not only the ones present at install."""
    root = Path(root)
    names = sorted(x.name for x in root.iterdir() if x.is_dir())
    days = [n for n in names if len(n) == 10 and n[4] == n[7] == "-"]
    if not days:
        return "readable (no day directory yet)"
    newest = root / days[-1]
    files = sorted(newest.glob(BOOK_PREFIX + "*.json"))
    for path in files:
        with path.open("rb") as fh:
            fh.read(1)
    return "readable (" + days[-1] + ": " + str(len(files)) + " claim files)"


def _writable_dir(path):
    path = Path(path)
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            raise PermissionError("no existing parent")
        probe = probe.parent
    if not probe.is_dir() or not os.access(probe, os.W_OK | os.X_OK):
        raise PermissionError("not writable: " + str(probe))
    return "writable" if probe == path else "creatable under " + str(probe)


def check_live_paths(config):
    """Filesystem preconditions of a live run, without writing anything.

    Raised as one SafetyError naming every failure, so the install evening's
    preflight shows them all at once (run as the service user)."""
    live = config.get("live") or {}
    checks, failed = {}, []
    tests = (
        ("book_margin_root", lambda: _readable_tree(live["book_margin_root"])),
        ("claims_dir", lambda: _writable_dir(live["claims_dir"])),
        ("book_publish_root", lambda: _writable_dir(live["book_publish_root"])),
    )
    for name, test in tests:
        try:
            checks[name] = test()
        except OSError as exc:
            checks[name] = "FAILED: " + type(exc).__name__ + ": " + str(exc)
            failed.append(name)
    arm = Path(live["arm_file"])
    checks["arm_file"] = "present (armed if valid)" if arm.exists() else "absent (shadow)"
    checks["approval_file"] = "present" if LIVE_APPROVAL.exists() else "absent"
    if failed:
        raise SafetyError("live paths not usable by this user: " + ", ".join(
            name + " " + checks[name] for name in failed))
    return checks


def operations_source(args):
    """One read of Box R's operations snapshot (file or private R2 URL)."""
    if args.operations_file:
        return read_json(args.operations_file)
    token = os.environ.get("RS_OPERATIONS_READ_TOKEN")
    if not token:
        raise SafetyError("RS_OPERATIONS_READ_TOKEN is not set for --operations-url")
    return read_https(args.operations_url, token)


def account_guards(config, endpoint, policy):
    live = config.get("live") or {}
    if not live.get("claims_dir"):
        return None, None
    claims = ClaimBook(live["claims_dir"], RS_SYSTEM, endpoint.account)
    book = BookMargin(
        live["book_margin_root"], live["book_publish_root"], policy,
        live["spx_book_reserve_fraction"],
        limit_fraction=live.get("book_margin_limit_fraction", 1.0),
    )
    return claims, book


async def run(args, endpoint, policy, config):
    if endpoint.live and not args.connect_live:
        raise SafetyError("--connect-live is required; no connection was opened")
    if not endpoint.live and not args.connect_paper:
        raise SafetyError("--connect-paper is required; no connection was opened")
    if not args.evidence or not (args.operations_file or args.operations_url):
        raise SafetyError("evidence and Box R operations source required")
    if endpoint.live and args.operations_url:
        # A blocking HTTPS read inside this loop stalls ib_insync, and position
        # protection with it. Live reads the copy operations-fetch maintains.
        raise SafetyError("live reads Box R's feed only from the local copy that "
                          "operations-fetch writes (--operations-file)")
    if args.operations_url and not os.environ.get("RS_OPERATIONS_READ_TOKEN"):
        # Otherwise every cycle would log inbox_unavailable for a whole session.
        raise SafetyError("RS_OPERATIONS_READ_TOKEN is not set for --operations-url")
    if args.shadow and not endpoint.live:
        raise SafetyError("--shadow is a live-endpoint mode")
    role = ("shadow" if args.shadow else "live") if endpoint.live else "paper"
    with_context = lambda: read_json(args.evidence)
    claims, book = account_guards(config, endpoint, policy)
    start = datetime.now(ZoneInfo("UTC")).isoformat()
    if role == "shadow" and claims is not None and claims.held(start):
        # Genuine RS positions are protected by the journal that holds them; a
        # shadow journal never manages positions, so it must not run instead.
        raise SafetyError("RS holds live names (" + ", ".join(sorted(claims.held(start)))
                          + "): run the live journal so their protection continues")
    if claims is not None:
        claims.publish_current(start)
    arm_file = (config.get("live") or {}).get("arm_file")
    journal = Journal(args.state, policy.digest, endpoint.prefix)
    if journal.get("journal_role", role) != role:
        found = journal.get("journal_role")
        journal.close()
        raise SafetyError("this is a " + str(found) + " journal; a " + role
                          + " run needs its own --state")
    journal.set("journal_role", role)
    if role == "shadow":
        transmit = lambda: (False, "shadow journal: entries are never transmitted")
    else:
        transmit = lambda: arm_state(arm_file, endpoint, policy, broker.now())
    broker = PaperIBKR(endpoint, with_context)
    broker.known_refs = {x["ref"] for x in journal.rows("orders")}

    async def connect_budgeted():
        # Persistent connect-event budget; supervisor restarts cannot reset it.
        day = (
            datetime.fromisoformat(broker.now())
            .astimezone(ZoneInfo("America/New_York"))
            .date()
            .isoformat()
        )
        key = "connection_attempts:" + day
        attempts = journal.get(key, 0)
        if attempts >= 3:
            raise SafetyError("daily paper connection budget exhausted")
        journal.set(key, attempts + 1)
        # A loopback port may be an SSH forward; prove the listener first.
        require_local_ib_listener(endpoint.port)
        await broker.connect()

    try:
        await connect_budgeted()
        # Qualify saved position identities before recovery/quote subscriptions.
        for pos in journal.rows("positions"):
            if pos["shares"]:
                await broker.qualify(json.loads(pos["payload"]))
        executor = Executor(
            endpoint,
            policy,
            journal,
            broker,
            kill_switch=lambda: Path(args.kill_file).exists(),
            transmit=transmit,
            claims=claims,
            book=book,
        )
        if args.resume_entries:
            await executor.resume_entries(broker.now())
        while True:
            now = broker.now()
            if not broker.ib.isConnected():
                executor.halt(now, "paper_connection_lost")
                await asyncio.sleep(30)
                await connect_budgeted()
                now = broker.now()
            # Position protection runs even if the research snapshot is absent.
            await executor.tick([], now)
            if Path(args.kill_file).exists():
                journal.set("kill", True)
                await executor.tick([], broker.now())
            try:
                if args.operations_file:
                    data, meta = read_local(args.operations_file)
                else:
                    data, meta = operations_source(args), {}
                # Producer clock and download clock, kept apart for shadow-report.
                executor.source_status = {
                    "operations_generated_at": data.get("generated_at"),
                    "operations_state_at": data.get("state_at", data.get("generated_at")),
                    "operations_downloaded_at": meta.get("downloaded_at"),
                }
                await executor.tick(
                    proposals(data, with_context(), broker.now()), broker.now()
                )
            except Exception as exc:
                executor.source_status = dict(
                    executor.source_status, operations_error=type(exc).__name__)
                journal.event(
                    broker.now(), "inbox_unavailable", {"type": type(exc).__name__}
                )
            wanted = {x["conid"] for x in journal.rows("positions") if x["shares"]}
            wanted |= {
                x["conid"]
                for x in journal.rows("orders")
                if x["state"] not in ("filled", "cancelled", "rejected")
            }
            broker.retain_quotes(wanted)
            if os.environ.get("RS_PAPER_SLACK_WEBHOOK"):
                try:
                    deliver_alerts(
                        journal, os.environ["RS_PAPER_SLACK_WEBHOOK"], broker.now()
                    )
                except Exception:
                    # Notification delivery cannot prevent position protection.
                    pass
            if args.once:
                break
            await asyncio.sleep(5)
    finally:
        broker.close()
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "run", "status", "probe", "integration-test",
                                            "shadow-report", "operations-check",
                                            "operations-fetch", "operations-cadence",
                                            "claims-init"])
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--state",
        default=str(Path.home() / ".local/state/rs-paper-executor/state.sqlite"),
    )
    parser.add_argument("--connect-paper", action="store_true")
    parser.add_argument(
        "--connect-live",
        action="store_true",
        help="shared NY4 Gateway as the registered reverse-split client; shadow unless armed",
    )
    parser.add_argument("--operations-file")
    parser.add_argument("--operations-url")
    parser.add_argument("--evidence")
    parser.add_argument("--kill-file", default="RS_PAPER_FLATTEN")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--symbol", help="probe: reviewed common-share symbol")
    parser.add_argument("--conid", type=int, help="probe: reviewed IB conid")
    parser.add_argument("--shares", type=int, help="probe WhatIf size (1); mechanics size (10)")
    parser.add_argument("--report", help="probe/integration-test: write the JSON report here")
    parser.add_argument(
        "--journal", help="integration-test: a NEW *.integration.sqlite file"
    )
    parser.add_argument(
        "--mechanics-only",
        action="store_true",
        help="integration-test without live quotes (route A step P): order mechanics only",
    )
    parser.add_argument(
        "--reference-price", type=float, help="mechanics: price if no delayed quote arrives"
    )
    parser.add_argument(
        "--shadow", action="store_true",
        help="run (live): a dedicated shadow journal that never transmits an entry",
    )
    parser.add_argument("--feed-dir", help="operations-fetch/-cadence: the fetcher's directory")
    parser.add_argument("--poll-seconds", type=float, default=5, help="operations-fetch")
    parser.add_argument("--day", help="operations-cadence: ET date (default today)")
    parser.add_argument("--min-sessions", type=int, default=5,
                        help="shadow-report: complete operating sessions")
    parser.add_argument("--min-feed-coverage", type=float, default=0.95, help="shadow-report")
    parser.add_argument("--min-opportunities", type=int, default=3, help="shadow-report")
    parser.add_argument("--min-issuers", type=int, default=3, help="shadow-report")
    parser.add_argument("--min-opportunity-sessions", type=int, default=2, help="shadow-report")
    parser.add_argument("--mechanics-report", help="shadow-report: the stage-P report")
    parser.add_argument("--mechanics-journal", help="shadow-report: the stage-P journal")
    parser.add_argument("--max-gap-seconds", type=int, default=120, help="shadow-report")
    parser.add_argument("--since", help="shadow-report: UTC ISO start")
    parser.add_argument("--until", help="shadow-report: UTC ISO end")
    parser.add_argument(
        "--resume-entries",
        action="store_true",
        help="operator acknowledgement after proven recovery",
    )
    args = parser.parse_args(argv)
    try:
        config = read_json(args.config)
        endpoint = endpoint_from_config(config["endpoint"])
        check_live_config(config, endpoint)
        policy = Policy(**config["policy"]).validate()
        if args.command == "preflight":
            report = {
                "paper_only": not endpoint.live,
                "live_orders_allowed": False,
                "mode": endpoint.mode,
                "connection_opened": False,
                "policy_hash": policy.digest,
                "policy": asdict(policy),
            }
            if endpoint.live:
                report["paths"] = check_live_paths(config)
            print(json.dumps(report))
        elif args.command == "operations-check":
            # One read of the proposal feed; no broker connection, no journal.
            if not (args.operations_file or args.operations_url):
                raise SafetyError("--operations-file or --operations-url required")
            try:
                data = operations_source(args)
            except OSError as exc:  # network or file error: report, never a traceback
                raise SafetyError("operations read failed: " + type(exc).__name__ + ": " + str(exc))
            now = datetime.now(ZoneInfo("UTC")).isoformat()
            try:
                require_fresh_operations(data, now)
                ok = True
            except SafetyError:
                ok = False
            print(json.dumps({
                "generated_at": data.get("generated_at"), "state_at": data.get("state_at"), "checked_at": now,
                "fresh_within_120s": ok,
                "candidates": len(data.get("candidates") or []),
                "broker_connection_opened": False,
            }))
            return 0 if ok else 3
        elif args.command == "status":
            # A read-only status process does not compete for the writer lock.
            import sqlite3

            db = sqlite3.connect(
                Path(args.state).resolve().as_uri() + "?mode=ro", uri=True
            )
            count = db.execute(
                "SELECT count(*)FROM orders WHERE state NOT IN('filled','cancelled','rejected')"
            ).fetchone()[0]
            positions = db.execute(
                "SELECT count(*)FROM positions WHERE shares>0"
            ).fetchone()[0]
            print(
                json.dumps(
                    {
                        "paper_only": True,
                        "live_orders_allowed": False,
                        "unresolved_orders": count,
                        "open_paper_positions": positions,
                        "broker_connection_opened": False,
                    }
                )
            )
            db.close()
        elif args.command == "probe":
            if not (args.connect_live if endpoint.live else args.connect_paper):
                raise SafetyError("--connect-paper/--connect-live is required; no connection was opened")
            broker = PaperIBKR(endpoint, lambda: {"borrow": {}, "eligibility": {}})
            report = asyncio.run(
                probe(endpoint, policy, broker, symbol=args.symbol,
                      conid=args.conid, shares=args.shares or 1)
            )
            text = json.dumps(report, indent=1, sort_keys=True)
            if args.report:
                Path(args.report).write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0 if report["pass"] else 3
        elif args.command == "operations-fetch":
            # The feed's network reads live here, in their own process, never in
            # the executor's position loop. Holds the only feed credential.
            from .operations_feed import R2Object, fetch_once, run_fetcher, utc_now

            if not args.feed_dir:
                raise SafetyError("--feed-dir required")
            source = R2Object.from_env()
            if not args.once:
                run_fetcher(source, args.feed_dir, poll_seconds=args.poll_seconds)
                return 0
            now = utc_now()
            try:
                result = fetch_once(source, args.feed_dir, now)
            except OSError as exc:
                raise SafetyError("operations fetch failed: " + type(exc).__name__ + ": " + str(exc))
            try:
                downloaded, _ = read_local(Path(args.feed_dir) / "operations.json")
                require_fresh_operations(downloaded, utc_now())
                ok = True
            except SafetyError:
                ok = False
            print(json.dumps({**result, "fetched_at": now, "fresh_within_120s": ok,
                              "broker_connection_opened": False}))
            return 0 if ok else 3
        elif args.command == "claims-init":
            # Install step: create RS's (empty) claims file so the spx user's read
            # can be verified BEFORE ls-algo's claims reader is deployed. No socket.
            if not endpoint.live:
                raise SafetyError("claims-init is for the live endpoint")
            claims, _ = account_guards(config, endpoint, policy)
            now = datetime.now(ZoneInfo("UTC")).isoformat()
            claims.publish_current(now)
            print(json.dumps({"claims_file": str(claims.path), "held": sorted(claims.held(now)),
                              "broker_connection_opened": False}))
        elif args.command == "operations-cadence":
            from .operations_feed import cadence_report

            if not args.feed_dir:
                raise SafetyError("--feed-dir required")
            day = args.day or datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            print(json.dumps(cadence_report(args.feed_dir, day), indent=1, sort_keys=True))
        elif args.command == "shadow-report":
            from .shadow_report import shadow_report, verify_mechanics

            mechanics = None
            if args.mechanics_report or args.mechanics_journal:
                if not (args.mechanics_report and args.mechanics_journal):
                    raise SafetyError("--mechanics-report and --mechanics-journal go together")
                mechanics = verify_mechanics(args.mechanics_report, args.mechanics_journal)
            report = shadow_report(
                args.state, min_sessions=args.min_sessions,
                max_gap_seconds=args.max_gap_seconds,
                min_feed_coverage=args.min_feed_coverage,
                min_opportunities=args.min_opportunities, min_issuers=args.min_issuers,
                min_opportunity_sessions=args.min_opportunity_sessions,
                entry_window_seconds=policy.entry_window_seconds, mechanics=mechanics,
                since=args.since, until=args.until,
            )
            text = json.dumps(report, indent=1, sort_keys=True)
            if args.report:
                Path(args.report).write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0 if report["ready_for_arm_review"] else 3
        elif args.command == "integration-test":
            if endpoint.live or not args.connect_paper:
                raise SafetyError("integration-test needs a paper endpoint and --connect-paper")
            if not (args.symbol and args.conid and args.journal):
                raise SafetyError("integration-test needs --symbol, --conid and --journal")
            from .integration import dumps, run_integration, run_mechanics

            async def stage6():
                broker = PaperIBKR(endpoint, lambda: {"borrow": {}, "eligibility": {}})
                require_local_ib_listener(endpoint.port)
                await broker.connect()
                try:
                    if args.mechanics_only:
                        return await run_mechanics(
                            endpoint, policy, broker, args.journal,
                            symbol=args.symbol, conid=args.conid,
                            shares=args.shares or 10,
                            reference=args.reference_price,
                        )
                    return await run_integration(
                        endpoint, policy, broker, args.journal,
                        symbol=args.symbol, conid=args.conid,
                    )
                finally:
                    broker.close()

            report = asyncio.run(stage6())
            if args.report:
                Path(args.report).write_text(dumps(report) + "\n", encoding="utf-8")
            print(dumps(report))
            return 0 if report["pass"] else 3
        else:
            asyncio.run(run(args, endpoint, policy, config))
    except (SafetyError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc), "live_orders_allowed": False}
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
