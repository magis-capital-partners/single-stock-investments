"""Halt/SSR producer: one row per watched conid, at most ``max_age`` seconds old.

The executor admits an entry only on ``complete: true``,
``source_verified: true``, ``halted: false`` and ``ssr: false``, all at most
30 s old. This producer may only write a value that a fresh approved source
states for that symbol:

* ``True`` (restricted) may come from any fresh source that lists the symbol:
  the Nasdaq halt feed, Nasdaq's dated Rule 201 file, or a licensed handler.
* ``False`` (clear) may only come from a source that reports per-symbol state
  and that the owner approved for clearing:

  - halts: a licensed handler, or the Nasdaq halt feed if
    ``halt_feed_clears`` is set (a complete current list of every US halt and
    LULD pause; absence from it is "not halted" only while it is fresh);
  - SSR: a licensed handler only. Nasdaq's daily file lists restricted names;
    absence from it is never clearance. No free per-symbol intraday SSR
    source is wired today, so until the owner picks one every row is
    ``ssr: None, complete: false`` and every entry is refused here.

Anything else is ``None``. ``at`` is the oldest source clock among the values
that decided the row, so a row is never fresher than its weakest input.
Being alive proves nothing: a producer heartbeat never sets a value.
"""

from __future__ import annotations

from _system.trading.rs_paper_executor.safety import timestamp

from .sources import halt_state

VERSION = "rs_eligibility_producer.v1"


def _age(now, at):
    return (timestamp(now) - timestamp(at)).total_seconds()


def _fresh(now, at, max_age):
    age = _age(now, at)
    return -2 <= age <= max_age


def build_eligibility(watch, now, *, max_age=30, halt_feed=None, halt_feed_clears=False,
                      restrictions=(), status=None):
    """``watch``: conid -> ticker. ``restrictions``: parsed dated Rule 201 files
    (restriction-only). ``status``: a parsed licensed handler file or None."""
    rows, summary = {}, {"complete": 0, "incomplete": 0}
    feed_fresh = halt_feed is not None and _fresh(now, halt_feed["as_of"], max_age)
    status_fresh = status is not None and _fresh(now, status["as_of"], max_age)
    for conid, ticker in sorted(watch.items()):
        missing, components = [], []

        halts = []  # (value, at, source)
        if status_fresh and status["symbols"].get(ticker, {}).get("halted") is not None:
            halts.append((status["symbols"][ticker]["halted"], status["as_of"], status["source"]))
        if feed_fresh:
            value, event = halt_state(halt_feed, ticker, now)
            if value or halt_feed_clears:
                halts.append((value, halt_feed["as_of"], "nasdaqtrader_halt_rss"))
            else:
                missing.append("halt_clearance_source_not_approved")
            if event:
                components.append({"kind": "halt_event", **event})
        else:
            missing.append("halt_feed_stale_or_unavailable")
        halted, halt_at = _decide(halts)
        if halted is None and not missing:
            missing.append("halt_state_unknown")

        ssrs = []
        for listing in restrictions:
            if ticker in listing["symbols"]:
                ssrs.append((True, listing["as_of"], "nasdaq_rule201_file"))
                components.append(
                    {
                        "kind": "ssr_listing",
                        "trigger": listing["symbols"][ticker],
                        "source_url": listing["source_url"],
                        "source_sha256": listing["source_sha256"],
                        "as_of": listing["as_of"],
                    }
                )
        if status_fresh and status["symbols"].get(ticker, {}).get("ssr") is not None:
            ssrs.append((status["symbols"][ticker]["ssr"], status["as_of"], status["source"]))
        ssr, ssr_at = _decide(ssrs)
        if ssr is None:
            missing.append(
                "intraday_ssr_clearance_source_absent"
                if status is None
                else "intraday_ssr_state_unknown_or_stale"
            )

        complete = halted is not None and ssr is not None
        at = min(halt_at, ssr_at, key=timestamp) if complete else now
        rows[str(conid)] = {
            "conid": conid,
            "ticker": ticker,
            "at": at,
            "complete": complete,
            # Every non-None value above came from a fresh source the owner
            # approved for exactly that statement; None is never verified.
            "source_verified": complete,
            "halted": halted,
            "ssr": ssr,
            # Halt state alone, for a BUY cover that needs no SSR clearance.
            # The executor does not read these yet (see the design note): its
            # exit fallback still requires ``complete``.
            "halt_complete": halted is not None,
            "halt_at": halt_at,
            "missing": sorted(set(missing)) if not complete else [],
            "deciding_sources": {
                "halted": _sources(halts, halted),
                "ssr": _sources(ssrs, ssr),
            },
            "components": components,
            "observed_at": now,
            "producer": VERSION,
        }
        summary["complete" if complete else "incomplete"] += 1
    return rows, summary


def _decide(values):
    """Restriction wins; clear needs a clearing source; else unknown."""
    restricted = [at for value, at, _ in values if value is True]
    if restricted:
        return True, max(restricted, key=timestamp)
    clear = [at for value, at, _ in values if value is False]
    if clear:
        return False, max(clear, key=timestamp)
    return None, None


def _sources(values, decided):
    return sorted({source for value, _, source in values if value is decided and decided is not None})
