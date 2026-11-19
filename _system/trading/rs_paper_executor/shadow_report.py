"""Read-only summary of live SHADOW sessions: the evidence the owner reviews
before writing the arm file (route A, stage S).

It opens the journal read-only (no writer lock, no broker connection) and
reports, per regular session:

* uptime: heartbeats inside the session and the largest gap (including the gap
  from the open to the first heartbeat and from the last one to the close);
* would-be entries (``shadow_entry``) with size, limit and the WhatIf margins;
* why proposals were refused, by reason (missing evidence shows up here);
* entry halts, inbox outages, and any order the journal holds.

Acceptance facts, not a verdict: the owner decides. ``ready_for_arm_review``
is true only when every check below holds:

* no order was transmitted (a shadow journal must hold none);
* at least ``min_sessions`` sessions were observed;
* at least ``min_entries`` would-be entries were recorded. A shadow_entry is
  written only after every live gate passed (live quote and size, WhatIf on the
  real account, SPX reserve and cushion, book-margin room), so without one the
  live entry path has never run and uptime alone proves little;
* no session's largest heartbeat gap exceeds ``max_gap_seconds``;
* the kill latch and daily-loss latch are clear.

Conditional would-be entries (``shadow_entry_conditional``, owner 2026-11-19,
option B) passed every later gate while halt/SSR state was UNKNOWN; none was
known to restrict. They are counted apart. ``downstream_gates_exercised`` says
the quote, borrow, WhatIf, reserve, cushion and book-margin gates ran on the
real account. They never count toward ``ready_for_arm_review``: an armed
executor refuses every entry whose SSR state is unknown, so arming before an
eligibility source can say "clear" would arm an executor that cannot enter.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

from .policy import Calendar
from .safety import timestamp


def _ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def shadow_report(state_path, *, calendar=None, min_sessions=5, min_entries=1,
                  max_gap_seconds=120, since=None, until=None):
    calendar = calendar or Calendar()
    db = _ro(state_path)
    db.row_factory = sqlite3.Row
    try:
        meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM meta")}
        events = [dict(r) for r in db.execute("SELECT id,at,kind,payload FROM events ORDER BY id")]
        orders = [dict(r) for r in db.execute("SELECT ref,side,shares,state FROM orders")]
    finally:
        db.close()
    lo = timestamp(since) if since else None
    hi = timestamp(until) if until else None
    sessions = []
    for row in calendar.rows:
        open_, close = timestamp(row["open"]), timestamp(row["close"])
        if (lo and close <= lo) or (hi and open_ >= hi):
            continue
        inside = [e for e in events if open_ <= timestamp(e["at"]) < close]
        if not inside:
            continue
        beats = sorted(timestamp(e["at"]) for e in inside if e["kind"] == "heartbeat")
        marks = [open_, *beats, close]
        gap = max((b - a).total_seconds() for a, b in zip(marks, marks[1:]))
        payload = [(e["kind"], json.loads(e["payload"] or "{}")) for e in inside]
        sessions.append({
            "day": row["day"],
            "heartbeats": len(beats),
            "max_heartbeat_gap_seconds": round(gap, 1),
            "shadow_entries": [p for k, p in payload if k == "shadow_entry"],
            "conditional_entries": [p for k, p in payload
                                    if k == "shadow_entry_conditional"],
            "refusals": dict(Counter(p.get("reason", "?") for k, p in payload
                                     if k == "proposal_blocked").most_common()),
            "entry_halts": [p.get("reason") for k, p in payload if k == "entry_halt"],
            "inbox_unavailable": sum(1 for k, _ in payload if k == "inbox_unavailable"),
            "orders_submitted": sum(1 for k, _ in payload if k == "paper_order_submitted"),
        })
    worst_gap = max((s["max_heartbeat_gap_seconds"] for s in sessions), default=None)
    entries = sum(len(s["shadow_entries"]) for s in sessions)
    full_ids = {e.get("id") for s in sessions for e in s["shadow_entries"]}
    # One per issuer/action: a second publisher record of the same action is
    # not a second opportunity.
    by_action = {}
    for s in sessions:
        for e in s["conditional_entries"]:
            if e.get("id") in full_ids:
                continue
            key = (e.get("cik"), e.get("action_id") or e.get("id"))
            by_action.setdefault(key, e)
    conditional = list(by_action.values())
    unknown = Counter(f for e in conditional for f in e.get("eligibility_unknown") or ["?"])
    checks = {
        "no_orders_transmitted": not orders and not any(s["orders_submitted"] for s in sessions),
        "sessions_observed": len(sessions),
        "enough_sessions": len(sessions) >= min_sessions,
        "enough_would_be_entries": entries >= min_entries,
        "downstream_gates_exercised": entries + len(conditional) >= max(1, min_entries),
        "worst_heartbeat_gap_seconds": worst_gap,
        "uptime_ok": worst_gap is not None and worst_gap <= max_gap_seconds,
        "kill_latch_clear": not meta.get("kill"),
        "daily_loss_latch_clear": not meta.get("daily_loss_day"),
        "current_entry_halt": meta.get("entry_halt"),
    }
    ready = all(checks[k] for k in ("no_orders_transmitted", "enough_sessions",
                                    "enough_would_be_entries", "uptime_ok",
                                    "kill_latch_clear", "daily_loss_latch_clear"))
    return {
        "schema": "rs_shadow_report.v1",
        "journal_prefix": meta.get("order_prefix"),
        "policy_hash": meta.get("policy_hash"),
        "endpoint": meta.get("endpoint"),
        "would_be_entries": entries,
        "conditional_would_be_entries": len(conditional),
        "conditional_issuers": len({e.get("cik") for e in conditional if e.get("cik")}),
        "conditional_unknown_inputs": dict(unknown.most_common()),
        "refusals_total": dict(sum((Counter(s["refusals"]) for s in sessions), Counter())
                               .most_common()),
        "checks": checks,
        "ready_for_arm_review": ready,
        "note": "Facts for the owner's arm decision; arming remains the owner's call.",
        "conditional_note": ("Conditional entries ran every later gate with halt/SSR "
                             "unknown. They do not count toward arm review: an armed "
                             "executor refuses every SSR-unknown entry.")
        if conditional else None,
        "sessions": sessions,
    }
