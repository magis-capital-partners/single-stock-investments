"""Read-only summary of live SHADOW sessions: the evidence the owner reviews
before writing the arm file (route A, stage S).

It opens the journal read-only (no writer lock, no broker connection). Per
regular session it reports, each separately:

* **process**: heartbeats inside the session and the largest gap, including
  the gap from the open to the first heartbeat and from the last one to the close;
* **source freshness**: the share of heartbeats whose operations snapshot was
  within its 120 s rule by the producer's own clock, the longest stale stretch,
  and the download lag (fetch time minus producer time);
* **quotes, per security**: every name that reached the live quote check,
  with whether a live share-size quote was available and why not;
* would-be entries (``shadow_entry``), refusals by reason, entry halts, and
  inbox outages.

Acceptance (owner, 2026-11-19). These are engineering facts, not proof of
profitability, and arming remains the owner's call. ``ready_for_arm_review``
is true only when every check holds:

* the journal is a dedicated shadow journal (``journal_role: shadow``) and
  holds no order, no position and no cover. A run that manages genuine RS
  positions is protection, not zero-order shadow validation;
* at least ``min_sessions`` COMPLETE operating sessions. Complete means the
  process gap is within ``max_gap_seconds`` AND the feed was fresh for at least
  ``min_feed_coverage`` of the heartbeats;
* at least ``min_opportunities`` fully gated opportunities, deduplicated by
  issuer (CIK) and action, from at least ``min_issuers`` issuers across at
  least ``min_opportunity_sessions`` sessions. Synthetic controls, repeated
  evaluations, duplicate publisher records (the same issuer/action under
  another candidate id) and catch-up announcements (first seen more than the
  entry window after publication) never count. A shadow_entry is written only
  after every live gate has passed;
* no current entry halt, and the kill and daily-loss latches are clear;
* the stage-P paper-mechanics report verifies against its own journal (see
  ``verify_mechanics``).

``conditional`` is a separate, NON-gating fact (owner 2026-11-19, option B).
``shadow_entry_conditional`` events passed every later gate while halt/SSR
state was unknown. They get the same exclusions and dedup, but are never
counted as opportunities and never affect ``ready_for_arm_review``.
``downstream_gates_exercised`` says the quote, borrow, WhatIf, reserve, cushion
and book-margin gates ran on the real account.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from .policy import Calendar
from .safety import SafetyError, timestamp

MECHANICS_STEPS = ("delayed_quote_refused", "whatif_preview", "entry_fill",
                   "duplicate_prevented", "reconnect_recovery", "cancel_confirmed",
                   "scoped_cover", "kill_latch_holds")


def _ro(path):
    if not Path(path).exists():
        raise SafetyError("journal not found: " + str(path))
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _synthetic(payload):
    return bool(payload.get("synthetic_control")) or any(
        str(payload.get(k) or "").startswith("synthetic-control:") for k in ("id", "action_id"))


def verify_mechanics(report_path, journal_path):
    """Check the stage-P report against the integration journal it names.

    The report is not taken on its word. The journal must show the same
    mechanics: an RSPAPER| namespace on a DU account, a filled SELL entry, a
    broker-confirmed cancel, a filled BUY cover, every position flat at the end,
    and the kill latch set. Partial fills are reported; they cannot be forced
    on IBKR's simulator, so they are a fact here, not a gate (the SimBroker unit
    tests cover them deterministically)."""
    out = {"report": str(report_path), "journal": str(journal_path), "problems": []}
    problems = out["problems"]
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        out["report_sha256"] = _sha256(report_path)
    except (OSError, ValueError) as exc:
        return {**out, "pass": False, "problems": ["report unreadable: " + type(exc).__name__]}
    if report.get("mode") != "mechanics_only" or report.get("paper_only") is not True:
        problems.append("not a paper mechanics-only report")
    if report.get("pass") is not True:
        problems.append("report did not pass")
    steps = report.get("steps") or {}
    for name in MECHANICS_STEPS:
        if not (steps.get(name) or {}).get("pass"):
            problems.append("step missing or failed: " + name)
    try:
        db = _ro(journal_path)
        out["journal_sha256"] = _sha256(journal_path)
    except (OSError, SafetyError) as exc:
        return {**out, "pass": False, "problems": problems + ["journal unreadable: " + str(exc)]}
    try:
        meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM meta")}
        orders = [dict(r) for r in db.execute("SELECT ref,side,shares,filled,state FROM orders")]
        fills = [dict(r) for r in db.execute("SELECT exec_id,ref,shares FROM fills")]
        held = [dict(r) for r in db.execute("SELECT signal_id,shares FROM positions")]
    finally:
        db.close()
    if meta.get("order_prefix") != "RSPAPER|":
        problems.append("journal is not in the RSPAPER| namespace")
    account = str((meta.get("endpoint") or {}).get("account") or "")
    if not account.startswith("DU"):
        problems.append("journal is not a DU paper account")
    if Path(journal_path).resolve() != Path(report.get("journal") or "").resolve():
        problems.append("report names a different journal")
    per_ref = Counter(f["ref"] for f in fills)
    if not any(o["side"] == "SELL" and o["filled"] > 0 for o in orders):
        problems.append("no filled SELL entry in the journal")
    if not any(o["state"] == "cancelled" for o in orders):
        problems.append("no broker-confirmed cancel in the journal")
    if not any(o["side"] == "BUY" and o["filled"] > 0 for o in orders):
        problems.append("no filled BUY cover in the journal")
    if any(p["shares"] for p in held):
        problems.append("journal is not flat")
    if not meta.get("kill"):
        problems.append("kill latch not set in the journal")
    entry = steps.get("entry_fill") or {}
    if entry.get("ref") and entry.get("fills") is not None and per_ref[entry["ref"]] != entry["fills"]:
        problems.append("report's entry fill count differs from the journal")
    out["partial_fills"] = {"observed_on_paper": any(n > 1 for n in per_ref.values()),
                            "unit_tested": True}
    out["pass"] = not problems
    return out


def _feed(beats, fresh_seconds):
    """(coverage, longest stale stretch in s, median download lag)."""
    if not beats:
        return 0.0, None, None
    fresh, stale_since, worst, lags = 0, None, 0.0, []
    for at, payload in beats:
        gen = payload.get("operations_generated_at")
        ok = False
        if gen:
            try:
                age = (at - timestamp(gen)).total_seconds()
                ok = -2 <= age <= fresh_seconds
                if payload.get("operations_downloaded_at"):
                    lags.append((timestamp(payload["operations_downloaded_at"])
                                 - timestamp(gen)).total_seconds())
            except SafetyError:
                ok = False
        if ok:
            fresh += 1
            if stale_since is not None:
                worst = max(worst, (at - stale_since).total_seconds())
                stale_since = None
        elif stale_since is None:
            stale_since = at
    if stale_since is not None:
        worst = max(worst, (beats[-1][0] - stale_since).total_seconds())
    lags.sort()
    return fresh / len(beats), round(worst, 1), (lags[len(lags) // 2] if lags else None)


def _dedupe(entries, entry_window_seconds):
    """One per (cik, action_id); synthetic, catch-up and repeats excluded."""
    seen, excluded = {}, Counter()
    for day, at, p in sorted(entries, key=lambda x: x[1]):
        if _synthetic(p):
            excluded["synthetic_control"] += 1
            continue
        if not p.get("cik") or not p.get("action_id"):
            excluded["missing_issuer_or_action"] += 1
            continue
        try:
            late = (timestamp(p["first_seen_at"]) - timestamp(p["published_at"])).total_seconds()
        except (KeyError, SafetyError):
            excluded["missing_clocks"] += 1
            continue
        if late > entry_window_seconds:
            excluded["catch_up_announcement"] += 1
            continue
        key = (str(p["cik"]), str(p["action_id"]))
        if key in seen:
            excluded["duplicate_issuer_action"] += 1
            continue
        seen[key] = {"day": day, "at": at.isoformat(), "cik": p["cik"],
                     "action_id": p["action_id"], "ticker": p.get("ticker"),
                     "candidate_id": p.get("id")}
    return seen, excluded


def shadow_report(state_path, *, calendar=None, min_sessions=5, max_gap_seconds=120,
                  min_feed_coverage=0.95, feed_fresh_seconds=120, min_opportunities=3,
                  min_issuers=3, min_opportunity_sessions=2, entry_window_seconds=900,
                  mechanics=None, since=None, until=None):
    calendar = calendar or Calendar()
    db = _ro(state_path)
    try:
        meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM meta")}
        events = [dict(r) for r in db.execute("SELECT id,at,kind,payload FROM events ORDER BY id")]
        orders = [dict(r) for r in db.execute("SELECT ref,side,shares,state FROM orders")]
        positions = [dict(r) for r in db.execute("SELECT signal_id,shares FROM positions")]
    finally:
        db.close()
    lo = timestamp(since) if since else None
    hi = timestamp(until) if until else None
    sessions, entries, conditional_entries = [], [], []
    for row in calendar.rows:
        open_, close = timestamp(row["open"]), timestamp(row["close"])
        if (lo and close <= lo) or (hi and open_ >= hi):
            continue
        inside = [(timestamp(e["at"]), e["kind"], json.loads(e["payload"] or "{}"))
                  for e in events if open_ <= timestamp(e["at"]) < close]
        if not inside:
            continue
        beats = sorted((at, p) for at, k, p in inside if k == "heartbeat")
        marks = [open_, *(at for at, _ in beats), close]
        gap = max((b - a).total_seconds() for a, b in zip(marks, marks[1:]))
        coverage, feed_gap, lag = _feed(beats, feed_fresh_seconds)
        quotes = {}
        for at, kind, p in inside:
            if kind == "quote_check":
                q = quotes.setdefault(str(p.get("conid")), {
                    "ticker": p.get("ticker"), "checks": 0, "available": False, "reasons": []})
                q["checks"] += 1
                q["available"] = q["available"] or bool(p.get("available"))
                if p.get("reason") and p["reason"] not in q["reasons"]:
                    q["reasons"].append(p["reason"])
            elif kind == "shadow_entry":
                entries.append((row["day"], at, p))
            elif kind == "shadow_entry_conditional":
                conditional_entries.append((row["day"], at, p))
        complete = gap <= max_gap_seconds and coverage >= min_feed_coverage
        sessions.append({
            "day": row["day"],
            "complete": complete,
            "process": {"heartbeats": len(beats), "max_gap_seconds": round(gap, 1)},
            "source": {"feed_fresh_share": round(coverage, 4),
                       "max_stale_seconds": feed_gap, "median_download_lag_seconds": lag,
                       "inbox_unavailable": sum(1 for _, k, _ in inside if k == "inbox_unavailable")},
            "quotes": quotes,
            "shadow_entries": [p for _, k, p in inside if k == "shadow_entry"],
            "conditional_entries": [p for _, k, p in inside if k == "shadow_entry_conditional"],
            "refusals": dict(Counter(p.get("reason", "?") for _, k, p in inside
                                     if k == "proposal_blocked").most_common()),
            "entry_halts": [p.get("reason") for _, k, p in inside if k == "entry_halt"],
            "orders_submitted": sum(1 for _, k, _ in inside if k == "paper_order_submitted"),
            "covers": sum(1 for _, k, _ in inside if k == "cover_trigger"),
        })
    seen, excluded = _dedupe(entries, entry_window_seconds)
    opportunities = list(seen.values())
    cond_seen, cond_excluded = _dedupe(conditional_entries, entry_window_seconds)
    for key in [k for k in cond_seen if k in seen]:  # a fully gated entry supersedes it
        del cond_seen[key]
        cond_excluded["has_fully_gated_entry"] += 1
    cond = list(cond_seen.values())
    unknown = Counter(f for _, _, p in conditional_entries
                      for f in (p.get("eligibility_unknown") or ["?"]))
    complete = [s for s in sessions if s["complete"]]
    worst_gap = max((s["process"]["max_gap_seconds"] for s in sessions), default=None)
    checks = {
        "dedicated_shadow_journal": meta.get("journal_role") == "shadow",
        "zero_orders": (not orders and not any(p["shares"] for p in positions)
                        and not any(s["orders_submitted"] or s["covers"] for s in sessions)),
        "sessions_observed": len(sessions),
        "complete_sessions": len(complete),
        "enough_complete_sessions": len(complete) >= min_sessions,
        "worst_process_gap_seconds": worst_gap,
        "opportunities": len(opportunities),
        "opportunity_issuers": len({o["cik"] for o in opportunities}),
        "opportunity_sessions": len({o["day"] for o in opportunities}),
        "kill_latch_clear": not meta.get("kill"),
        "daily_loss_latch_clear": not meta.get("daily_loss_day"),
        "current_entry_halt": meta.get("entry_halt"),
        "mechanics_verified": bool(mechanics and mechanics.get("pass")),
    }
    checks["enough_opportunities"] = (
        checks["opportunities"] >= min_opportunities
        and checks["opportunity_issuers"] >= min_issuers
        and checks["opportunity_sessions"] >= min_opportunity_sessions)
    checks["entry_halt_clear"] = not checks["current_entry_halt"]
    gates = ("dedicated_shadow_journal", "zero_orders", "enough_complete_sessions",
             "enough_opportunities", "kill_latch_clear", "daily_loss_latch_clear",
             "entry_halt_clear", "mechanics_verified")
    return {
        "schema": "rs_shadow_report.v2",
        "journal_prefix": meta.get("order_prefix"),
        "journal_role": meta.get("journal_role"),
        "policy_hash": meta.get("policy_hash"),
        "endpoint": meta.get("endpoint"),
        "thresholds": {"min_complete_sessions": min_sessions, "max_gap_seconds": max_gap_seconds,
                       "min_feed_coverage": min_feed_coverage,
                       "feed_fresh_seconds": feed_fresh_seconds,
                       "min_opportunities": min_opportunities, "min_issuers": min_issuers,
                       "min_opportunity_sessions": min_opportunity_sessions,
                       "entry_window_seconds": entry_window_seconds},
        "opportunities": opportunities,
        "excluded_entries": dict(excluded),
        "conditional": {
            "counts_toward_readiness": False,
            "would_be_entries": len(cond),
            "issuers": len({c["cik"] for c in cond}),
            "sessions": len({c["day"] for c in cond}),
            "entries": cond,
            "excluded_entries": dict(cond_excluded),
            "unknown_inputs": dict(unknown.most_common()),
            "downstream_gates_exercised": bool(cond or opportunities),
            "note": ("Every later gate passed with halt/SSR unknown. Not an opportunity: an "
                     "armed executor refuses every SSR-unknown entry."),
        },
        "refusals_total": dict(sum((Counter(s["refusals"]) for s in sessions), Counter())
                               .most_common()),
        "mechanics": mechanics,
        "checks": checks,
        "failed_checks": [g for g in gates if not checks[g]],
        "ready_for_arm_review": all(checks[g] for g in gates),
        "note": "Engineering acceptance facts, not proof of profitability; arming remains "
                "the owner's call.",
        "sessions": sessions,
    }
