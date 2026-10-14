"""Sornette error diagram for the LPPLS confidence indicator.

An alarm is a sample whose positive-bubble confidence is at least the
threshold and whose critical-time ensemble is concentrated. The diagram
plots crashes missed against the fraction of sample dates spent in alarm.
The chosen threshold is the one with the least time in alarm that still
catches at least half of the tested crashes and alarms on at most a quarter
of sample dates. It is not chosen by profit.
"""
from __future__ import annotations

import bisect
from typing import Sequence

MODEL_VERSION = "lppls-error-diagram-v1"
LEAD_SESSIONS = 120
CALM_SESSIONS = 60
MIN_SAMPLES_IN_WINDOW = 3
MIN_CONCENTRATION = 25.0
MAX_MISS_RATE = 0.5
MAX_TIME_IN_ALARM = 0.25
MIN_TESTED_CRASHES = 5
THRESHOLDS = (5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80)

# Peak dates are the last session of the prior regime. 1987 is in the catalog
# because the plan names it; SPY did not exist, so the diagram marks it untested.
CATALOG = (
    {"id": "1987-10", "kind": "crash", "peak_date": "1987-10-16", "label": "October 1987", "notes": "SPY listing is 1993. This row stays untested on the SPY close series."},
    {"id": "1998-08", "kind": "crash", "peak_date": "1998-07-17", "label": "August 1998", "notes": "Peak before the Russia / LTCM drawdown."},
    {"id": "2000-03", "kind": "crash", "peak_date": "2000-03-24", "label": "2000-2002", "notes": "March 2000 peak."},
    {"id": "2007-10", "kind": "crash", "peak_date": "2007-10-09", "label": "2008-2009", "notes": "October 2007 peak."},
    {"id": "2010-05", "kind": "crash", "peak_date": "2010-05-06", "label": "May 2010", "notes": "Flash crash session. Treated as an event date; the lead window is the sessions before it."},
    {"id": "2011-08", "kind": "crash", "peak_date": "2011-04-29", "label": "August 2011", "notes": "Spring 2011 high before the summer drawdown."},
    {"id": "2015-08", "kind": "crash", "peak_date": "2015-08-21", "label": "August 2015", "notes": "Session before the 24 August break."},
    {"id": "2018-02", "kind": "crash", "peak_date": "2018-01-26", "label": "February 2018", "notes": "January 2018 high before Volmageddon."},
    {"id": "2020-03", "kind": "crash", "peak_date": "2020-02-19", "label": "March 2020", "notes": "February 2020 high."},
    {"id": "2022-01", "kind": "crash", "peak_date": "2022-01-03", "label": "2022 drawdown", "notes": "January 2022 high."},
    {"id": "2024-08", "kind": "crash", "peak_date": "2024-07-16", "label": "August 5 2024", "notes": "July 2024 high before the August break."},
    {"id": "calm-1995", "kind": "calm", "peak_date": "1995-06-30", "label": "Mid-1995 calm", "notes": "Non-event control."},
    {"id": "calm-2004", "kind": "calm", "peak_date": "2004-06-30", "label": "Mid-2004 calm", "notes": "Non-event control."},
    {"id": "calm-2006", "kind": "calm", "peak_date": "2006-06-30", "label": "Mid-2006 calm", "notes": "Non-event control."},
    {"id": "calm-2013", "kind": "calm", "peak_date": "2013-06-28", "label": "Mid-2013 calm", "notes": "Non-event control."},
    {"id": "calm-2017", "kind": "calm", "peak_date": "2017-06-30", "label": "Mid-2017 calm", "notes": "Non-event control."},
    {"id": "calm-2019", "kind": "calm", "peak_date": "2019-06-28", "label": "Mid-2019 calm", "notes": "Non-event control."},
    {"id": "calm-2023", "kind": "calm", "peak_date": "2023-06-30", "label": "Mid-2023 calm", "notes": "Non-event control."},
)


def snap_on_or_before(calendar: Sequence[str], day: str) -> str | None:
    if not calendar:
        return None
    index = bisect.bisect_right(calendar, day) - 1
    if index < 0:
        return None
    return calendar[index]


def window_dates(calendar: Sequence[str], day: str, sessions: int) -> list[str]:
    """The `sessions` trading days ending before `day`, snapped onto the calendar."""
    snapped = snap_on_or_before(calendar, day)
    if snapped is None:
        return []
    index = bisect.bisect_left(calendar, snapped)
    if index >= len(calendar) or calendar[index] != snapped:
        return []
    start = max(0, index - sessions)
    return list(calendar[start:index])


def is_positive_alarm(
    sample: dict,
    threshold: float,
    *,
    min_concentration: float = MIN_CONCENTRATION,
) -> bool:
    if sample.get("status") not in {"ready", "limited"}:
        return False
    positive = sample.get("positive")
    concentration = sample.get("concentration")
    if positive is None or concentration is None:
        return False
    return float(positive) >= threshold and float(concentration) >= min_concentration


def _coverage(samples_by_date: dict[str, dict], dates: Sequence[str]) -> list[dict]:
    return [samples_by_date[day] for day in dates if day in samples_by_date]


def evaluate(
    samples: Sequence[dict],
    events: Sequence[dict],
    calendar: Sequence[str],
    *,
    thresholds: Sequence[float] = THRESHOLDS,
    lead_sessions: int = LEAD_SESSIONS,
    calm_sessions: int = CALM_SESSIONS,
    min_concentration: float = MIN_CONCENTRATION,
) -> dict:
    ordered = sorted(samples, key=lambda row: row["date"])
    by_date = {row["date"]: row for row in ordered}
    curve = []
    event_rows = []
    for threshold in thresholds:
        alarms = [
            row for row in ordered
            if is_positive_alarm(row, threshold, min_concentration=min_concentration)
        ]
        time_in_alarm = (len(alarms) / len(ordered)) if ordered else None
        tested = 0
        caught = 0
        calm_tested = 0
        calm_alarm = 0
        details = []
        for event in events:
            sessions = calm_sessions if event["kind"] == "calm" else lead_sessions
            dates = window_dates(calendar, event["peak_date"], sessions)
            covered = _coverage(by_date, dates)
            hit = any(
                is_positive_alarm(row, threshold, min_concentration=min_concentration)
                for row in covered
            )
            if len(covered) < MIN_SAMPLES_IN_WINDOW:
                status = "untested"
            elif event["kind"] == "calm":
                calm_tested += 1
                status = "false_alarm" if hit else "quiet"
                if hit:
                    calm_alarm += 1
            else:
                tested += 1
                status = "caught" if hit else "missed"
                if hit:
                    caught += 1
            details.append({
                "id": event["id"],
                "kind": event["kind"],
                "label": event.get("label"),
                "peak_date": event["peak_date"],
                "status": status,
                "samples_in_window": len(covered),
            })
        miss_rate = (tested - caught) / tested if tested else None
        curve.append({
            "threshold": threshold,
            "time_in_alarm": None if time_in_alarm is None else round(time_in_alarm, 4),
            "miss_rate": None if miss_rate is None else round(miss_rate, 4),
            "crashes_tested": tested,
            "crashes_caught": caught,
            "crashes_missed": tested - caught,
            "calm_tested": calm_tested,
            "calm_false_alarms": calm_alarm,
            "alarm_samples": len(alarms),
            "sample_count": len(ordered),
        })
        event_rows.append({"threshold": threshold, "events": details})
    selection = select_threshold(curve)
    return {
        "model_version": MODEL_VERSION,
        "research_only": True,
        "in_base_irr": False,
        "min_concentration": min_concentration,
        "lead_sessions": lead_sessions,
        "calm_sessions": calm_sessions,
        "curve": curve,
        "events_by_threshold": event_rows,
        "selection": selection,
    }


def select_threshold(curve: Sequence[dict]) -> dict:
    """Least time in alarm among thresholds that separate crashes from the sample.

    Eligible thresholds miss at most half of tested crashes, alarm on at most
    a quarter of sample dates, and rest on at least five tested crashes.
    Ties take the higher threshold. If none qualify, demotion stays off.
    """
    eligible = [
        row for row in curve
        if row.get("crashes_tested", 0) >= MIN_TESTED_CRASHES
        and row.get("miss_rate") is not None
        and row["miss_rate"] <= MAX_MISS_RATE
        and row.get("time_in_alarm") is not None
        and row["time_in_alarm"] <= MAX_TIME_IN_ALARM
    ]
    rule = (
        "Lowest time-in-alarm among thresholds that miss at most half of tested "
        "crashes, alarm on at most a quarter of sample dates, and rest on at least "
        "five crashes. Ties take the higher threshold. Not chosen by profit."
    )
    if not eligible:
        return {
            "demotion_enabled": False,
            "confidence_threshold": None,
            "min_concentration": MIN_CONCENTRATION,
            "miss_rate": None,
            "time_in_alarm": None,
            "crashes_tested": None,
            "crashes_caught": None,
            "rule": rule,
            "plain_english": (
                "No confidence level caught at least half of the tested crashes "
                "while alarming on at most a quarter of sample dates. Market-path "
                "language does not use this monitor until one does."
            ),
        }
    eligible.sort(key=lambda row: (row["time_in_alarm"], -row["threshold"]))
    chosen = eligible[0]
    threshold = chosen["threshold"]
    return {
        "demotion_enabled": True,
        "confidence_threshold": threshold,
        "min_concentration": MIN_CONCENTRATION,
        "miss_rate": chosen["miss_rate"],
        "time_in_alarm": chosen["time_in_alarm"],
        "crashes_tested": chosen["crashes_tested"],
        "crashes_caught": chosen["crashes_caught"],
        "rule": rule,
        "plain_english": (
            f"Positive-bubble confidence of {threshold:g} or higher, with a "
            f"concentrated critical-time window, caught {chosen['crashes_caught']} of "
            f"{chosen['crashes_tested']} tested crashes and was in alarm on "
            f"{chosen['time_in_alarm'] * 100:.1f}% of sample dates. The same level "
            "caps market-path language when either bubble direction is that strong."
        ),
    }
