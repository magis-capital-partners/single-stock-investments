"""Full event catalogue, price study and fixed conditional account replays.

Candidate, verified-action, disclosure and executable-trade denominators are
explicit. Missing paths remain missing; a later detection is never an earlier
announcement. Public output contains derived returns and counts, not bars.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
import sqlite3
import shutil
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .adjust import PriceFrame
from .analysis import cluster_interval
from .execute import session_open
from .expansion import connect, digest, episodes, export_coverage, location, utcnow
from .expansion_replay import borrow_imports, prepare, specification
from .expansion_imports import evidence
from .fundamentals import FundamentalBridge
from .ledger import load_jsonl, read_json, write_json, write_retained_jsonl
from .replay import replay
from .rerun import eligible_score, metrics
from .run_book import load_frames
from .strategy_research import apply_reviews, freeze_facts, one_day_study, matched_controls, exit_audit, borrow_and_forward
from .borrow_research import freeze_current_rates, attach_post_evidence

VERSION = "reverse_split_universe.v4"
HORIZONS = (1, 5, 10, 20)
OFFSETS = (0, 1, 5)
VERIFIED = {"primary_schedule_matched", "structured_corporate_action"}


def issuer(row):
    cik = str(row.get("cik") or "").lstrip("0")
    return (
        "cik/" + cik
        if cik
        else "unresolved_symbol/" + str(row.get("ticker") or row.get("security_id"))
    )


def catalogue(cfg, disclosures, start, cutoff, *, detector_report=None, detector_coverage=None):
    schedules = defaultdict(list)
    for row in disclosures:
        if (
            row.get("eligible")
            and row.get("stage") == "scheduled_action"
            and row.get("scheduled")
        ):
            schedules[str(row.get("cik") or "").lstrip("0")].append(row)
    joins = read_json(cfg.reports_dir / "rename_joins.json", [])
    aliases = {(j["ticker"], j["ex_date"]): j["filing_time_symbol"] for j in joins}
    rows = []
    for event in load_jsonl(cfg.ledger_dir / "events.jsonl"):
        ex = str(event.get("ex_date") or "")[:10]
        if not start <= ex <= cutoff:
            continue
        ticker = aliases.get((event["ticker"], ex), event["ticker"])
        cik = str(event.get("cik") or "").lstrip("0")

        def matches(d):
            scheduled, printed = (
                date.fromisoformat(d["scheduled"]),
                date.fromisoformat(ex),
            )
            exact_or_weekend = scheduled == printed or (
                scheduled.weekday() >= 5
                and printed.weekday() == 0
                and 0 < (printed - scheduled).days <= 2
            )
            symbol = d.get("ticker")
            return bool(
                exact_or_weekend
                and (not symbol or symbol in {ticker, event["ticker"]})
                and d.get("ratio")
                and abs(float(d["ratio"]) / float(event["ratio"]) - 1) <= 0.05
            )

        matched = [d for d in schedules[cik] if matches(d)]
        chosen = (
            min(matched, key=lambda d: (d["available_at"], d["accession"]))
            if matched
            else None
        )
        verification = (
            "primary_schedule_matched"
            if chosen
            else "vendor_action_only"
            if event.get("source") == "yfinance"
            else "candidate_requires_verification"
        )
        accession = chosen["accession"] if chosen else event.get("accession")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/"
            if cik and accession
            else None
        )
        rows.append(
            {
                "ticker": ticker,
                "database_ticker": event["ticker"],
                "cik": cik or None,
                "security_id": f"{cik or 'unresolved'}/{ticker}",
                "ex_date": ex,
                "ratio": chosen["ratio"] if chosen else event["ratio"],
                "ratio_basis": "primary_filing"
                if chosen
                else "price_inferred"
                if event.get("source") == "databento_price_jump"
                else "vendor_action",
                "verification": verification,
                "available_at": chosen["available_at"] if chosen else None,
                "source": event.get("source"),
                "source_url": url,
                "accession": accession,
                "exchange_class": event.get("exchange_class", "unknown"),
                "security_type": "common_or_ADS_provisional",
                "company": event.get("company"),
                "historical_identity": "dated_filing_alias"
                if ticker != event["ticker"]
                else "ticker_requires_security_class_review",
            }
        )
    otc = read_json(location(cfg) / "otc_daily/actions.json", [])
    rows.extend(r for r in otc if start <= r["ex_date"] <= cutoff)
    rows.extend(
        r
        for r in read_json(location(cfg) / "reference_actions/actions.json", [])
        if start <= r["ex_date"] <= cutoff
    )
    from .detector_catalogue import candidates

    rows.extend(candidates(cfg, start, cutoff, report=detector_report, coverage=detector_coverage))
    present = {(str(r.get("cik") or "").lstrip("0"), r["ex_date"]) for r in rows}
    for d in disclosures:
        ex = d.get("scheduled")
        cik = str(d.get("cik") or "").lstrip("0")
        if (
            not d.get("eligible")
            or d.get("stage") != "scheduled_action"
            or not ex
            or not start <= ex <= cutoff
            or (cik, ex) in present
        ):
            continue
        ticker = d.get("ticker") or "CIK" + cik
        rows.append(
            {
                "ticker": ticker,
                "cik": cik,
                "security_id": cik + "/" + ticker,
                "ex_date": ex,
                "ratio": d.get("ratio"),
                "ratio_basis": "primary_filing",
                "verification": "primary_schedule_only",
                "available_at": d["available_at"],
                "source": "sec_scheduled_disclosure",
                "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{d['accession']}/",
                "accession": d["accession"],
                "exchange_class": "unknown",
                "security_type": "unknown",
                "historical_identity": "filing_symbol_requires_dated_identity_review",
            }
        )
    # A dated symbol/date/ratio match can join independent sources only when
    # it resolves to one CIK. Conflicting issuers remain separate candidates.
    ciks = defaultdict(set)
    for r in rows:
        if r.get("cik"):
            ciks[r["ticker"], r["ex_date"], r.get("ratio")].add(r["cik"])
    for r in rows:
        known = ciks[r["ticker"], r["ex_date"], r.get("ratio")]
        if not r.get("cik") and len(known) == 1:
            r["cik"] = next(iter(known))
            r["security_id"] = r["cik"] + "/" + r["ticker"]
    distinct = {}
    for row in rows:
        # Exact dates and ratios only: two distinct nearby actions never merge
        # solely because the same issuer split again within ten days.
        key = (
            issuer(row),
            row["ticker"],
            row["ex_date"],
            round(float(row["ratio"]), 12) if row.get("ratio") is not None else None,
        )
        identity = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]
        row["event_id"] = "event/" + identity
        if key not in distinct:
            row["sources"] = [row.get("source")]
            distinct[key] = row
        else:
            old = distinct[key]
            sources = sorted(set(old["sources"] + [row.get("source")]))
            rank = {
                "candidate_requires_verification": 0,
                "vendor_action_only": 1,
                "primary_schedule_only": 2,
                "primary_schedule_matched": 3,
                "structured_corporate_action": 3,
            }
            corroborated_jump = any(
                r.get("source") == "full_market_price_jump_candidate"
                and r.get("price_jump_corroborated")
                for r in (old, row)
            )
            primary = next(
                (r for r in (old, row) if r["verification"] == "primary_schedule_only"),
                None,
            )
            if rank.get(row["verification"], 0) > rank.get(old["verification"], 0):
                row["available_at"] = old.get("available_at") or row.get("available_at")
                distinct[key] = row
            if corroborated_jump and primary and distinct[key]["verification"] not in VERIFIED:
                # This key requires the same resolved issuer, ticker, exact
                # date and ratio. A weak jump or conflicting CIK cannot qualify.
                distinct[key] = {**primary, "verification": "primary_schedule_matched",
                                 "price_jump_corroborated": True}
            distinct[key]["sources"] = sources
    return sorted(distinct.values(), key=lambda r: (r["ex_date"], r["event_id"]))


def apply_imports(conn, events, frames):
    """Dated external actions and regular-session prices join the same study."""
    securities = evidence(conn, "security")
    for row in evidence(conn, "action"):
        if not row["verified"] or row["ratio"] >= 1:
            continue
        security = [
            s
            for s in securities
            if s["verified"]
            and s["security_id"] == row["security_id"]
            and s["valid_from"] <= row["ex_date"]
            and (not s["valid_to"] or row["ex_date"] <= s["valid_to"])
        ]
        if len(security) != 1:
            continue
        s = security[0]
        existing = next(
            (
                e
                for e in events
                if e["ticker"] == row["ticker"]
                and e["ex_date"] == row["ex_date"]
                and (not e.get("ratio") or abs(e["ratio"] / row["ratio"] - 1) < 0.001)
            ),
            None,
        )
        if existing:
            existing.update(
                cik=s["cik"],
                security_id=s["security_id"],
                verification="structured_corporate_action",
                ratio=row["ratio"],
                source_url=row["source_url"],
                available_at=row["announced_at"],
            )
        else:
            key = [s["security_id"], row["ticker"], row["ex_date"], row["ratio"]]
            events.append(
                {
                    **row,
                    "event_id": "import/"
                    + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24],
                    "cik": s["cik"],
                    "exchange_class": "otc"
                    if s["exchange"].lower() in {"otc", "pink", "otcqb", "otcqx"}
                    else "listed",
                    "security_type": s["kind"],
                    "verification": "structured_corporate_action",
                    "source": "dated_action_import",
                    "available_at": row["announced_at"],
                    "historical_identity": "verified_dated_security_master",
                }
            )
    imports = defaultdict(dict)
    for row in evidence(conn, "price"):
        if row.get("session_basis") not in {"regular_session", "official_auction"}:
            continue
        security = [
            s
            for s in securities
            if s["verified"]
            and s["security_id"] == row["security_id"]
            and s["ticker"] == row["ticker"]
            and s["valid_from"] <= row["date"]
            and (not s["valid_to"] or row["date"] <= s["valid_to"])
        ]
        if len(security) == 1:
            imports[row["ticker"]][row["date"]] = row
    for ticker, rows in imports.items():
        old = frames.get(ticker)
        combined = (
            {
                d: {
                    k: getattr(old, k)[i]
                    for k in ("open", "high", "low", "close", "volume")
                }
                for i, d in enumerate(old.dates)
            }
            if old
            else {}
        )
        combined.update(rows)
        days = sorted(combined)
        frames[ticker] = PriceFrame(
            days,
            *[
                [combined[d][k] for d in days]
                for k in ("open", "high", "low", "close", "volume")
            ],
        )
    return set(imports)


def trading_calendar(start, cutoff):
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS", start=start, end=cutoff)
    return [str(d)[:10] for d in cal.sessions if start <= str(d)[:10] <= cutoff]


def price_frames(cfg, db_path=None):
    """Only explicitly nominal venue rows enter the broad price study."""
    db_path = db_path or cfg.db_path
    if not db_path.exists():
        return {}, set(), {}
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "price_provenance" not in tables:
            return {}, set(), {}
        buckets = defaultdict(list)
        for r in conn.execute(
            "SELECT p.* FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE v.nominal=1 ORDER BY ticker,date"
        ):
            buckets[r["ticker"]].append(r)
        frames = {
            t: PriceFrame(
                [r["date"] for r in rows],
                *[
                    [float(r[k]) if r[k] is not None else math.nan for r in rows]
                    for k in ("open", "high", "low", "close", "volume")
                ],
            )
            for t, rows in buckets.items()
        }
        official = (
            {
                (r[0], r[1], r[2]): r[3]
                for r in conn.execute(
                    "SELECT ticker,date,point,price FROM official_auction_prices"
                )
            }
            if "official_auction_prices" in tables
            else {}
        )
        for ticker, frame in frames.items():
            for i, day in enumerate(frame.dates):
                frame.open[i] = official.get((ticker, day, "open")) or math.nan
                frame.close[i] = official.get((ticker, day, "close")) or math.nan
                observed = [
                    v
                    for v in (
                        frame.open[i],
                        frame.close[i],
                        frame.high[i],
                        frame.low[i],
                    )
                    if math.isfinite(v)
                ]
                if observed:
                    frame.high[i] = max(observed)
                    frame.low[i] = min(observed)
        restricted = (
            {(r[0], r[1]) for r in conn.execute("SELECT ticker,date FROM ssr_flags")}
            if "ssr_flags" in tables
            else set()
        )
        states = (
            {
                (r[0], r[1]): None if r[2] is None else bool(r[2])
                for r in conn.execute("SELECT ticker,date,restricted FROM ssr_states")
            }
            if "ssr_states" in tables
            else {}
        )
        return frames, set(frames), {"restricted": restricted, "states": states}
    finally:
        conn.close()


def event_outcomes(
    events,
    frames,
    calendar,
    *,
    offsets=OFFSETS,
    horizons=HORIZONS,
    entry_point="open",
    extra_actions=(),
):
    if entry_point not in {"open", "close"}:
        raise ValueError("Entry point must be open or close")
    actions = defaultdict(list)
    unknown_actions = defaultdict(list)
    for e in events:
        if e.get("action_review", {}).get("decision") == "not_corporate_action":
            continue
        table = actions if e["verification"] in VERIFIED else unknown_actions
        table[e.get("database_ticker", e["ticker"])].append(e)
    for e in extra_actions:
        if e["verified"] and (e["ex_date"], e["ratio"]) not in {
            (a["ex_date"], a["ratio"]) for a in actions[e["ticker"]]
        }:
            actions[e["ticker"]].append(e)
    result = []
    for e in events:
        ticker = e.get("database_ticker", e["ticker"])
        frame = frames.get(ticker) or frames.get(e["ticker"])
        anchor = bisect.bisect_left(calendar, e["ex_date"])
        cases = []
        for offset in offsets:
            for horizon in horizons:
                entry_i, exit_i = (
                    anchor + offset,
                    anchor + offset + horizon - (1 if entry_point == "open" else 0),
                )
                cohort = (
                    (f"ex_close_h{horizon}" if offset == 0 else f"ex_plus_{offset}_close_h{horizon}")
                    if entry_point == "close"
                    else f"ex_plus_{offset}_h{horizon}"
                )
                row = {
                    "cohort": cohort,
                    "offset_sessions": offset,
                    "horizon_sessions": horizon,
                    "entry_point": entry_point,
                    "status": "unavailable",
                    "reason": None,
                    "gross_short_return": None,
                }
                if e.get("action_review", {}).get("decision") == "not_corporate_action":
                    row["reason"] = "adjudicated_not_corporate_action"
                elif exit_i >= len(calendar):
                    row["reason"] = "holding_period_not_yet_complete"
                elif frame is None:
                    row["reason"] = "nominal_price_history_unavailable"
                else:
                    first, last = calendar[entry_i], calendar[exit_i]
                    ix, jx = (
                        bisect.bisect_left(frame.dates, first),
                        bisect.bisect_left(frame.dates, last),
                    )
                    row.update(entry_date=first, exit_date=last)
                    if (
                        ix >= len(frame.dates)
                        or jx >= len(frame.dates)
                        or frame.dates[ix] != first
                        or frame.dates[jx] != last
                    ):
                        row["reason"] = "entry_or_exit_observation_unavailable"
                    elif any(
                        first < a["ex_date"] <= last for a in unknown_actions[ticker]
                    ):
                        row["reason"] = "unverified_corporate_action_in_horizon"
                    else:
                        px, out = (
                            (
                                frame.open[ix]
                                if entry_point == "open"
                                else frame.close[ix]
                            ),
                            frame.close[jx],
                        )
                        factor = math.prod(
                            float(a["ratio"])
                            for a in actions[ticker]
                            if first < a["ex_date"] <= last
                        )
                        if not all(
                            math.isfinite(v) and v > 0 for v in (px, out, factor)
                        ):
                            row["reason"] = "invalid_price_or_share_factor"
                        else:
                            row.update(
                                status="observed_price_path",
                                gross_short_return=1 - factor * out / px,
                                share_factor=factor,
                                below_one_dollar=px < 1,
                            )
                cases.append(row)
        result.append({**e, "issuer": issuer(e), "outcomes": cases})
    return result


def outcome_summaries(rows):
    groups = defaultdict(list)
    for row in rows:
        for outcome in row["outcomes"]:
            if outcome["status"] == "observed_price_path":
                tier = (
                    "verified_actions"
                    if row["verification"] in VERIFIED
                    else "provisional_candidates"
                )
                groups[(tier, outcome["cohort"])].append(
                    {
                        "issuer": row["issuer"],
                        "year": row["ex_date"][:4],
                        "net_return": outcome["gross_short_return"],
                        "event_id": row["event_id"],
                    }
                )
    summaries = []
    for (tier, cohort), batch in sorted(groups.items()):
        values = sorted(r["net_return"] for r in batch)
        n = len(values)
        median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
        summaries.append(
            {
                "tier": tier,
                "cohort": cohort,
                "events": n,
                "issuers": len({r["issuer"] for r in batch}),
                "mean_gross_short_return": sum(values) / n,
                "median_gross_short_return": median,
                "positive_share": sum(v > 0 for v in values) / n,
                "issuer_interval": cluster_interval(batch, cluster="issuer"),
                "calendar_interval": cluster_interval(batch, cluster="year"),
                "interpretation": "Gross price behavior; assumes neither feasible borrow nor executable fills",
            }
        )
    return summaries


def account_cases():
    # Declared before replay; no winning configuration is selected afterward.
    cases = []
    for selector in ("announcement_only", "fundamental_60"):
        for horizon in HORIZONS:
            for fee in (1.0, 3.0):
                cases.append(
                    {
                        "id": f"scheduled_{selector}_h{horizon}_fee{int(fee * 100)}",
                        "selector": selector,
                        "horizon_sessions": horizon,
                        "fee_annual": fee,
                        "execution": "base",
                        "stage": "scheduled_action",
                    }
                )
    cases.extend(
        [
            {
                "id": "scheduled_fundamental_60_economic",
                "selector": "fundamental_60",
                "horizon_sessions": 5,
                "fee_annual": 1.0,
                "execution": "economic",
                "account": "conservative",
                "stage": "scheduled_action",
            },
            {
                "id": "scheduled_evidence_required",
                "selector": "fundamental_60",
                "horizon_sessions": 5,
                "fee_annual": 1.0,
                "execution": "quotes",
                "account": "conservative",
                "borrow_policy": "strict",
                "stage": "scheduled_action",
            },
        ]
    )
    for selector in ("event_only", "fundamental_60"):
        for horizon in HORIZONS:
            for fee in (1.0, 3.0):
                cases.append(
                    {
                        "id": f"post_split_{selector}_h{horizon}_fee{int(fee * 100)}",
                        "selector": selector,
                        "horizon_sessions": horizon,
                        "fee_annual": fee,
                        "execution": "base",
                        "stage": "post_split_1",
                    }
                )
    for stage in ("authorization_or_proposal", "unscheduled_board_action"):
        for selector in ("announcement_only", "fundamental_60"):
            for fee in (1.0, 3.0):
                cases.append(
                    {
                        "id": f"{stage}_{selector}_h5_fee{int(fee * 100)}",
                        "selector": selector,
                        "horizon_sessions": 5,
                        "fee_annual": fee,
                        "execution": "base",
                        "stage": stage,
                    }
                )
    for execution in ("one_day_budget", "quotes"):
        cases.append({"id": "post_split_fundamental_60_h1_" + execution,
                      "selector": "fundamental_60", "horizon_sessions": 1,
                      "fee_annual": 1.0, "execution": execution,
                      "account": "conservative", "stage": "post_split_1",
                      **({"borrow_policy": "strict"} if execution == "quotes" else {})})
    for selector in ("event_only", "fundamental_60"):
        for fee in (1.0, 3.0):
            cases.append({"id":f"post_split_{selector}_h2_fee{int(fee*100)}", "selector":selector,
                          "horizon_sessions":2, "fee_annual":fee, "execution":"base", "stage":"post_split_1",
                          "hold_label":"next-session open through following session close; one overnight"})
    return cases


def delay_restricted(lead, calendar, flags, *, max_delay=2):
    """Defer an observed restricted opening; never certify missing status."""
    item = deepcopy(lead)
    at = bisect.bisect_left(calendar, item["entry_date"])
    initial = at
    while at < len(calendar) and (item["ticker"], calendar[at]) in flags.get(
        "restricted", set()
    ):
        at += 1
        if at - initial > max_delay:
            return None, "restriction_exceeds_registered_delay"
    if at >= len(calendar) or calendar[at] not in item["rows"]:
        return None, "delayed_entry_price_unavailable"
    day = calendar[at]
    if item.get("announced_ex_date") and day >= item["announced_ex_date"]:
        return None, "scheduled_action_passed_before_delayed_entry"
    if at > initial:
        previous = item["rows"].get(calendar[at - 1])
        if previous is None:
            return None, "delayed_prior_cost_observation_unavailable"
        factor = item["rows"][day]["factor"]
        since_prior = factor / previous["factor"]
        item["prior_row"] = {k: previous[k] / since_prior for k in ("high", "low")}
        item["adv"] *= factor
        for row in item["rows"].values():
            row["factor"] /= factor
        item["original_entry_date"] = item["entry_date"]
        item["entry_date"] = day
    item["ssr_entry_status"] = flags.get("states", {}).get((item["ticker"], day))
    return item, None


def post_split_leads(events, frames, calendar, bridge, *, extra_actions=()):
    """A distinct exploratory next-session cohort, known before its entry."""
    known, unknown = defaultdict(list), defaultdict(list)
    for e in events:
        if e.get("action_review", {}).get("decision") == "not_corporate_action":
            continue
        (known if e["verification"] in VERIFIED else unknown)[
            e.get("database_ticker", e["ticker"])
        ].append(e)
    for e in extra_actions:
        if e["verified"] and (e["ex_date"], e["ratio"]) not in {
            (a["ex_date"], a["ratio"]) for a in known[e["ticker"]]
        }:
            known[e["ticker"]].append(e)
    leads, reasons = [], Counter()
    for e in events:
        if e["verification"] not in VERIFIED:
            continue
        ticker = e.get("database_ticker", e["ticker"])
        f = frames.get(ticker)
        idx = bisect.bisect_left(calendar, e["ex_date"]) + 1
        if idx >= len(calendar):
            reasons["post_split_entry_pending"] += 1
            continue
        day = calendar[idx]
        if not e.get("available_at") or datetime.fromisoformat(
            e["available_at"].replace("Z", "+00:00")
        ) > session_open(day):
            reasons["event_information_not_available_at_entry"] += 1
            continue
        if not f or day not in f.dates:
            reasons["post_split_nominal_price_unavailable"] += 1
            continue
        ix = bisect.bisect_left(f.dates, day)
        volumes = [
            f.volume[j]
            * math.prod(
                float(a["ratio"])
                for a in known[ticker]
                if f.dates[j] < a["ex_date"] <= day
            )
            for j in range(max(0, ix - 20), ix)
        ]
        if len(volumes) < 20 or any(not math.isfinite(v) or v <= 0 for v in volumes):
            reasons["post_split_prior_liquidity_unavailable"] += 1
            continue
        blocked = min(
            (a["ex_date"] for a in unknown[ticker] if a["ex_date"] > day), default=None
        )
        last = (date.fromisoformat(day) + timedelta(days=180)).isoformat()
        marks = {}
        for j in range(ix, len(f.dates)):
            d = f.dates[j]
            if d > last or blocked and d >= blocked:
                break
            values = [f.open[j], f.high[j], f.low[j], f.close[j]]
            if not any(math.isfinite(v) and v > 0 for v in (f.open[j], f.close[j])):
                continue
            marks[d] = dict(zip(("open", "high", "low", "close"), values))
            marks[d].update(
                volume=f.volume[j],
                factor=math.prod(
                    float(a["ratio"]) for a in known[ticker] if day < a["ex_date"] <= d
                ),
            )
        if day not in marks or not math.isfinite(marks[day]['open']) or marks[day]['open']<=0:
            reasons["post_split_invalid_entry_price"] += 1
            continue
        score = bridge.score(ticker, e.get("cik") or "", day)
        leads.append(
            {
                "id": e["event_id"],
                "episode_id": e["event_id"],
                "ticker": ticker,
                "cik": e.get("cik") or issuer(e),
                "entry_date": day,
                "rows": marks,
                "adv": sum(volumes) / 20,
                "prior_row": {
                    k: getattr(f, k)[ix - 1]
                    / math.prod(
                        float(a["ratio"])
                        for a in known[ticker]
                        if f.dates[ix - 1] < a["ex_date"] <= day
                    )
                    for k in ("high", "low", "close")
                },
                "announced_ex_date": None,
                "announcement_category": "post_split_1",
                "source_url": e.get("source_url"),
                "fundamental": score,
                "dated_thesis": None,
                "dated_margin": None,
            }
        )
    return leads, dict(reasons)


def run(cfg, *, start="2018-05-01", cutoff=None, frozen_from=None):
    cutoff = cutoff or date.today().isoformat()
    if start > cutoff:
        raise ValueError("Study start follows cutoff")
    snapshot_parent = Path(frozen_from).resolve() if frozen_from else None
    parent_manifest = read_json(snapshot_parent / 'manifest.json') if snapshot_parent else {}
    if snapshot_parent:
        if not snapshot_parent.is_relative_to((location(cfg)/'runs').resolve()) or not parent_manifest or not (snapshot_parent/'summary.json').exists():
            raise ValueError('Reuse requires a completed local immutable study')
        for filename,key in (('input.sqlite','input_sha256'),('prices.sqlite','prices_sha256')):
            if digest(snapshot_parent/filename)!=parent_manifest[key]:
                raise ValueError('Frozen input checksum mismatch: '+filename)
        conn=sqlite3.connect((snapshot_parent/'input.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
        conn.row_factory=sqlite3.Row
    else:
        conn = connect(cfg)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = location(cfg) / "runs" / stamp
    root.mkdir(parents=True)
    previous_pointer = read_json(location(cfg) / "latest_run.json", {})
    previous = location(cfg) / previous_pointer.get("path", "missing")
    code = [
        {"path": p.name, "sha256": digest(p)}
        for p in sorted(Path(__file__).parent.glob("*.py"))
    ]
    try:
        spec = specification()
        protocol = read_json(cfg.ledger_dir / "forward_protocol.json")
        reviews = read_json(cfg.ledger_dir / "action_reviews.json", {})
        write_json(root / "forward_protocol.json", protocol)
        write_json(root / "action_reviews.json", reviews)
        spec["execution"]["one_day_budget"] = {**spec["execution"]["base"], "maximum_cost_fraction": protocol["maximum_expected_cost_fraction"]}
        spec.update(
            version=VERSION,
            start=start,
            cutoff=cutoff,
            cases=account_cases(),
            event_cohorts={
                "offset_sessions": OFFSETS,
                "horizon_sessions": HORIZONS,
                "ex_close": True,
            },
            forward_validation_starts=protocol["validation_starts"],
            observation_window_calendar_days=180,
            ssr_policy="delay up to two sessions when observed restricted; unknown state is conditional",
        )
        write_json(root / "plan.json", spec)
        frozen_reports = {}
        for name in ("split_detections.csv", "split_detection_reconciliation.json"):
            source = (snapshot_parent or cfg.reports_dir) / name
            target = root / name
            if source.exists():
                shutil.copy2(source, target)
                frozen_reports[name] = digest(target)
        if snapshot_parent:
            os.link(snapshot_parent/'input.sqlite',root/'input.sqlite')
            os.link(snapshot_parent/'prices.sqlite',root/'prices.sqlite')
        else:
            with sqlite3.connect(root / "input.sqlite") as target:
                conn.backup(target)
        conn.close()
        conn = sqlite3.connect((root / "input.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        if not snapshot_parent:
            with sqlite3.connect(cfg.db_path.as_uri() + "?mode=ro", uri=True) as prices:
                with sqlite3.connect(root / "prices.sqlite") as target:
                    prices.backup(target)
        disclosures = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM disclosures ORDER BY available_at,accession"
            )
        ]
        collection = {
            "filing_hit_rows": conn.execute(
                "SELECT count(*) FROM edgar_hits"
            ).fetchone()[0],
            "distinct_accessions": conn.execute(
                "SELECT count(DISTINCT accession) FROM edgar_hits"
            ).fetchone()[0],
            "pending_accessions": conn.execute(
                "SELECT count(DISTINCT accession) FROM edgar_hits WHERE accession NOT IN (SELECT accession FROM disclosures)"
            ).fetchone()[0],
            "by_year": [
                dict(r)
                for r in conn.execute(
                    "SELECT substr(filed_at,1,4) AS year,count(DISTINCT accession) AS discovered,count(DISTINCT CASE WHEN accession IN (SELECT accession FROM disclosures) THEN accession END) AS processed FROM edgar_hits GROUP BY year ORDER BY year"
                )
            ],
            "jobs": [
                dict(r)
                for r in conn.execute(
                    "SELECT kind,status,count(*) AS count FROM collection_jobs GROUP BY kind,status ORDER BY kind,status"
                )
            ],
        }
        events = catalogue(
            cfg, disclosures, start, cutoff,
            detector_report=root / "split_detections.csv",
            detector_coverage=root / "split_detection_reconciliation.json",
        )
        frames, nominal, flags = price_frames(cfg, root / "prices.sqlite")
        nominal.update(apply_imports(conn, events, frames))
        events = [e for e in events if start <= e["ex_date"] <= cutoff]
        apply_reviews(conn, events, reviews)
        with sqlite3.connect(
            (root / "prices.sqlite").as_uri() + "?mode=ro", uri=True
        ) as prices:
            tables = {
                r[0]
                for r in prices.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            observations = (
                {
                    r[0]: r[1]
                    for r in prices.execute(
                        "SELECT symbol,last_seen FROM venue_symbol_observations"
                    )
                }
                if "venue_symbol_observations" in tables
                else {}
            )
        from .split_detector import normalize_symbol

        recent = (date.fromisoformat(cutoff) - timedelta(days=30)).isoformat()
        for e in events:
            last = observations.get(normalize_symbol(e["ticker"]))
            e["last_observed_venue_date"] = last
            e["recent_venue_observation"] = (
                "unknown"
                if not last
                else "observed_in_last_30_days"
                if last >= recent
                else "no_recent_venue_print"
            )
            e["terminal_status"] = "unconfirmed"
        calendar = trading_calendar(start, cutoff)
        extra_actions = [a for a in evidence(conn, "action") if a["verified"]]
        observed = event_outcomes(events, frames, calendar, extra_actions=extra_actions)
        at_close = event_outcomes(
            events,
            frames,
            calendar,
            offsets=(0, 1),
            entry_point="close",
            extra_actions=extra_actions,
        )
        for row, close in zip(observed, at_close):
            row["outcomes"].extend(close["outcomes"])
        print(
            f"Catalogue {len(events):,} events; nominal prices {len(frames):,} ticker histories",
            flush=True,
        )
        bridge = FundamentalBridge(cfg)
        if snapshot_parent:
            bridge.cache=snapshot_parent/'companyfacts'
        facts = root / "companyfacts"
        fact_storage = freeze_facts(cfg, bridge, facts)
        print(f"Frozen companyfacts: {fact_storage}", flush=True)
        # Reuse computed financial scores only when both facts and every score
        # producer match the completed snapshot. No prices/returns select them.
        if snapshot_parent and parent_manifest.get('fundamentals',{}).get('links')==bridge.manifest().get('links') and next((r['sha256'] for r in parent_manifest['code'] if r['path']=='fundamentals.py'),None)==digest(Path(__file__).parent/'fundamentals.py'):
            from .fundamentals import cik_id
            cache_rows=load_jsonl(snapshot_parent/'lead_audit.jsonl')
            for row in cache_rows:
                score=row.get('fundamental')
                if score and score.get('ticker') and score.get('as_of'):
                    bridge.scores[score['ticker'],cik_id(score['cik']),score['as_of']]=score
            del cache_rows
            for case_id in ('post_split_event_only_h1_fee100','post_split_event_only_h5_fee100','post_split_fundamental_60_h5_fee100'):
                for row in read_json(snapshot_parent/(case_id+'.json'),{}).get('positions',[]):
                    score=row.get('score')
                    if score and score.get('ticker') and score.get('as_of'):
                        bridge.scores[score['ticker'],cik_id(score['cik']),score['as_of']]=score
            print(f"Reused {len(bridge.scores):,} identical-source financial scores",flush=True)
        # Legacy histories are fallback scenarios, not printed-venue evidence.
        legacy = load_frames(conn)
        legacy.update(frames)
        known_actions = [
            {
                **e,
                "ticker": e.get("database_ticker", e["ticker"]),
                "outcome": "effective",
            }
            for e in events
            if e["verification"] in VERIFIED
        ]
        blocked = defaultdict(list)
        for e in events:
            if e["verification"] not in VERIFIED and e.get("action_review", {}).get("decision") != "not_corporate_action":
                blocked[e.get("database_ticker", e["ticker"])].append(e["ex_date"])
        leads, audit, announcement_calendar = prepare(
            cfg,
            conn,
            bridge,
            cutoff,
            frames_override=legacy,
            nominal_tickers=nominal,
            action_events_override=known_actions,
            blocked_actions=blocked,
        )
        leads = [l for l in leads if start <= l["entry_date"] <= cutoff]
        audit = [a for a in audit if start <= a["filed_at"] <= cutoff]
        announcement_calendar = [d for d in announcement_calendar if d >= start]
        post, post_reasons = post_split_leads(
            events, frames, calendar, bridge, extra_actions=extra_actions
        )
        announcement_count = len(leads)
        leads.extend(post)
        fee_records = evidence(conn, "borrow_fee")
        securities = evidence(conn, "security")
        for lead in leads:
            matches = [s for s in securities if s["verified"] and s["ticker"] == lead["ticker"] and str(s["cik"]).lstrip("0") == str(lead["cik"]).lstrip("0") and s["valid_from"] <= lead["entry_date"] and (not s["valid_to"] or lead["entry_date"] <= s["valid_to"])]
            lead["dated_security"] = matches[0] if len(matches) == 1 else None
            lead["borrow_fees"] = [r for r in fee_records if len(matches) == 1 and r["security_id"] == matches[0]["security_id"] and r["ticker"] == lead["ticker"] and r["evidence_class"] == "broker_statement"]
            share_actions={}
            for action in known_actions+extra_actions:
                if action['ticker']==lead['ticker'] and lead['entry_date']<action['ex_date']<=cutoff:
                    share_actions[action['ex_date'],action['ratio']]={'ex_date':action['ex_date'],'ratio':action['ratio'],'source_url':action.get('source_url')}
            lead['share_actions']=[share_actions[k] for k in sorted(share_actions)]
        attach_post_evidence(conn, post, events, calendar)
        current_quotes, current_rates, current_cases = freeze_current_rates(cfg, root, observed, post)
        for lead in leads:
            lead['current_borrow_indication']=current_quotes.get(lead['ticker'])
        spec['cases'].extend(current_cases)
        spec['current_borrow_rate_inputs']=current_rates
        for case in spec['cases']:
            if case.get('borrow_policy')=='strict' and case['stage']=='post_split_1' and case['horizon_sessions']==1:
                case['maximum_borrow_annual_fraction']=protocol['maximum_borrow_annual_fraction']
                spec['execution']['quotes']['maximum_cost_fraction']=protocol['maximum_expected_cost_fraction']
        # Rate formulas are fixed in code. Freeze their current source values
        # before any account replay; they never depend on historical profits.
        write_json(root / 'plan.json', spec)
        print(
            f"Prepared {len(leads):,} announcement disclosures; replaying fixed cases",
            flush=True,
        )
        borrow = borrow_imports(conn)
        results = []
        for case in spec["cases"]:
            selected, seen, case_reasons = [], set(), Counter()
            for lead in leads:
                if lead["announcement_category"] != case["stage"]:
                    continue
                if case["selector"] == "fundamental_60" and not eligible_score(
                    lead["fundamental"], 60
                ):
                    continue
                episode = lead["episode_id"] or lead["id"]
                if episode in seen:
                    continue
                seen.add(episode)
                delayed, reason = delay_restricted(lead, announcement_calendar, flags)
                if reason:
                    case_reasons[reason] += 1
                    continue
                lead = delayed
                if case["horizon_sessions"] <= 2 and "original_entry_date" in lead:
                    case_reasons["one_day_SSR_skip_no_delayed_entry"] += 1
                    continue
                if case.get("borrow_policy") == "strict":
                    item = next((a for a in audit if a["id"] == lead["id"]), {})
                    if (
                        not (item.get("all_gates", {}).get("dated_security") or lead.get("dated_security"))
                        or not lead.get("dated_margin")
                        or not lead.get("dated_thesis")
                        or lead["ssr_entry_status"] is not False
                    ):
                        case_reasons[
                            "dated_security_thesis_margin_or_status_unavailable"
                        ] += 1
                        continue
                selected.append(lead)
            replayed = replay(
                selected, announcement_calendar, deepcopy(spec), case, borrow
            )
            m = metrics(replayed, spec["initial_equity"])
            for key in (
                "annualized_volatility",
                "sharpe_zero_rf",
                "cagr",
                "daily_expected_shortfall_5pct",
            ):
                m[key] = None
            m["annualized_metrics_withheld_for_discovery_coverage"] = True
            status = (
                "evidence_unavailable"
                if case.get("borrow_policy") == "strict" and not m["taken"]
                else "unresolved_positions"
                if m["unresolved"]
                else "conditional_model"
            )
            detail = {"case": case, "metrics": m, "status": status, **replayed}
            write_json(root / (case["id"] + ".json"), detail)
            results.append(
                {
                    "case": case,
                    "metrics": m,
                    "status": status,
                    "eligible_episodes": len(selected),
                    "pre_replay_exclusions": dict(case_reasons),
                    "ssr_status_unknown": sum(
                        l["ssr_entry_status"] is None for l in selected
                    ),
                    "ssr_delayed_entries": sum(
                        "original_entry_date" in l for l in selected
                    ),
                }
            )
            print(
                f"{case['id']}: {m['taken']} trades / {m['unique_issuers']} issuers / {m['unresolved']} unresolved",
                flush=True,
            )
        ep = episodes(disclosures)
        manifest = {
            "version": VERSION,
            "run_id": stamp,
            "input_sha256": digest(root / "input.sqlite"),
            "prices_sha256": digest(root / "prices.sqlite"),
            "code": code,
            "detector_reports": frozen_reports,
            "ledger_sources": [
                {"path": name, "sha256": digest(cfg.ledger_dir / name)}
                for name in ("events.jsonl", "book_runs.jsonl", "action_reviews.json", "forward_protocol.json")
                if (cfg.ledger_dir / name).exists()
            ],
            "venue_files": [
                {"path": str(p.relative_to(cfg.databento_dir)), "sha256": digest(p)}
                for p in sorted(cfg.databento_dir.rglob("*.ok.json"))
            ],
            "fundamentals": bridge.manifest(),
            "companyfacts": [
                {"name": p.name, "sha256": digest(p)}
                for p in sorted(bridge.cache.glob("CIK*.json"))
            ],
            "fact_storage": fact_storage,
            "snapshot_parent":snapshot_parent.name if snapshot_parent else None,
            "research_documents": [{"name": name, "sha256": digest(root / name)} for name in ("action_reviews.json", "forward_protocol.json")],
            "plan_sha256":digest(root/'plan.json'),
            "current_borrow_sha256":digest(root/'current_borrow.jsonl') if (root/'current_borrow.jsonl').exists() else None,
        }
        if any(digest(Path(__file__).parent / r["path"]) != r["sha256"] for r in code):
            raise ValueError(
                "Source code changed during the study; resume with a fresh immutable run"
            )
        write_json(root / "manifest.json", manifest)
        target_cohort = "ex_plus_1_h5"
        verified = [r for r in observed if r["verification"] in VERIFIED]
        priced = [
            r
            for r in verified
            if next(o for o in r["outcomes"] if o["cohort"] == target_cohort)["status"]
            == "observed_price_path"
        ]
        counts = {
            "discovered_events": len(events),
            "unique_issuer_keys": len({issuer(e) for e in events}),
            "verified_actions": len(verified),
            "verified_issuer_keys": len({issuer(e) for e in verified}),
            "complete_verified_price_paths": len(priced),
            "complete_price_issuer_keys": len({issuer(e) for e in priced}),
            "processed_disclosures": len(disclosures),
            "provisional_episodes": len(ep),
            "prepared_disclosures": announcement_count,
            "prepared_post_split_events": len(post),
            "prepared_fundamental_60": sum(
                eligible_score(l["fundamental"], 60)
                for l in leads
                if l["announcement_category"] != "post_split_1"
            ),
            "post_split_fundamental_60": sum(
                eligible_score(l["fundamental"], 60) for l in post
            ),
            "sub_dollar_prepared": sum(
                l["rows"][l["entry_date"]]["open"] < 1 for l in leads
            ),
        }
        counts["last_nominal_observation"] = max(
            (d for f in frames.values() for d in f.dates), default=None
        )
        print("Comparing fixed one-day cohorts and matched controls", flush=True)
        one_day = one_day_study(observed, post, calendar, flags, frames, bridge, protocol, root)
        controls = matched_controls(post, events, frames, bridge, protocol, root, flags)
        published_id=read_json(cfg.ledger_dir/'expansion_summary.json',{}).get('run_id')
        audit_baseline=location(cfg)/'runs'/published_id if published_id else previous
        reconciled = exit_audit(root, audit_baseline, events, frames, reviews, conn)
        borrowing, forward = borrow_and_forward(conn, protocol, cutoff)
        summary = {
            "schema_version": VERSION,
            "run_id": stamp,
            "built_at": utcnow(),
            "start": start,
            "cutoff": cutoff,
            "counts": counts,
            "event_study": outcome_summaries(observed),
            "accounts": results,
            "one_day": one_day,
            "matched_controls": controls,
            "exit_reconciliation": reconciled,
            "borrow_economics": borrowing,
            "current_borrow_sensitivities": current_rates,
            "forward_validation": forward,
            "by_year": dict(Counter(e["ex_date"][:4] for e in events)),
            "by_market": dict(Counter(e["exchange_class"] for e in events)),
            "by_security_type": dict(
                Counter(e.get("security_type", "unknown") for e in events)
            ),
            "by_verification": dict(Counter(e["verification"] for e in events)),
            "exclusions": dict(
                Counter(
                    o["reason"] for r in observed for o in r["outcomes"] if o["reason"]
                )
            ),
            "announcement_exclusions": dict(
                Counter(reason for a in audit for reason in a["reasons"])
            ),
            "post_split_exclusions": post_reasons,
            "collection": collection,
            "by_recent_venue_observation": dict(
                Counter(e["recent_venue_observation"] for e in events)
            ),
            "otc_coverage": read_json(location(cfg) / "otc_daily/coverage.json", {}),
            "reference_coverage": read_json(
                location(cfg) / "reference_actions/coverage.json", {}
            ),
            "detector_coverage": read_json(
                location(cfg) / "detector_coverage.json", {}
            ),
            "borrow_history": read_json(
                cfg.ledger_dir / "borrow_history/latest.json", {}
            ),
            "baseline": read_json(location(cfg) / "baseline_manifest.json", {}),
            "manifest_sha256": digest(root / "manifest.json"),
            "full_universe_complete": False,
            "forward_validation_starts": spec["forward_validation_starts"],
            "limits": [
                "Automated source matching requires event and security-class adjudication; unresolved candidates stay visible",
                "OTC actions are included even when historical prices are unavailable",
                "Historical borrow permission, actual quotes, recalls, dividends and terminal obligations are incomplete",
                "Official listing-venue auctions benchmark entry/exit; missing auctions remain unavailable",
                "Historical financial facts use filing dates; issuer industry classification still uses current SEC metadata",
                "Volume covers three exchanges across all sessions; it is not consolidated regular-session liquidity",
                "No recent venue print can reflect a rename, halt or delisting; terminal status requires adjudication",
                "Conditional account results are assumptions; no performance-based threshold selection or Sharpe claim",
                "Every cohort reports its own events and issuers; multiple entry settings do not multiply the sample",
                "A missing exit is unavailable or an unresolved liability; it is never a zero-return trade",
            ],
        }
        write_json(root / "summary.json", summary)
        write_retained_jsonl(root / "event_outcomes.jsonl", observed)
        write_retained_jsonl(root / "lead_audit.jsonl", audit)
        write_json(
            location(cfg) / "latest_run.json",
            {"run_id": stamp, "path": str(root.relative_to(location(cfg)))},
        )
        export_coverage(cfg, conn)
        return {"run_id": stamp, "counts": counts, "accounts": len(results)}
    finally:
        conn.close()


def publish(cfg):
    pointer = read_json(location(cfg) / "latest_run.json", {})
    root = (location(cfg) / pointer.get("path", "")).resolve()
    if (
        not root.is_relative_to(location(cfg).resolve())
        or not (root / "summary.json").exists()
    ):
        raise ValueError("No completed local study to publish")
    summary = read_json(root / "summary.json")
    public = deepcopy(summary)
    # Remove workstation paths and raw/cache manifests from the public feed.
    public["baseline"] = {
        "version": summary["baseline"].get("version"),
        "preserved": summary["baseline"].get("preserved", []),
    }
    for name in ("action_reviews.json", "forward_protocol.json"):
        if (root / name).exists() and digest(root / name) != digest(cfg.ledger_dir / name):
            raise ValueError("Research document changed after the frozen run: " + name)
    write_json(cfg.ledger_dir / "expansion_summary.json", public)
    outcomes = load_jsonl(root / "event_outcomes.jsonl")
    public_events = [
        {
            **r,
            "outcomes": [
                {
                    k: v
                    for k, v in o.items()
                    if k not in {"gross_short_return", "share_factor"}
                }
                for o in r["outcomes"]
            ],
        }
        for r in outcomes
    ]
    # Individual price-derived returns stay licensed/local. Public metadata
    # retains dates and gaps; only aggregate research statistics travel.
    info = write_retained_jsonl(
        cfg.ledger_dir / "expansion_events.jsonl", public_events
    )
    conn = sqlite3.connect((root / "input.sqlite").as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        disclosures = [
            {
                k: r[k]
                for k in (
                    "accession",
                    "cik",
                    "ticker",
                    "form",
                    "filed_at",
                    "available_at",
                    "clock_basis",
                    "stage",
                    "ratio",
                    "scheduled",
                    "eligible",
                    "review_status",
                )
            }
            for r in conn.execute(
                "SELECT * FROM disclosures ORDER BY filed_at,accession"
            )
        ]
        write_retained_jsonl(
            cfg.ledger_dir / "expansion_disclosures.jsonl", disclosures, sparse=True
        )
        write_retained_jsonl(
            cfg.ledger_dir / "expansion_episodes.jsonl",
            episodes(disclosures),
            sparse=True,
        )
        write_retained_jsonl(
            cfg.ledger_dir / "expansion_discovery.jsonl",
            [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM edgar_hits ORDER BY filed_at,accession,form"
                )
            ],
            sparse=True,
        )
    finally:
        conn.close()
    names = (
        "action_reviews.json",
        "forward_protocol.json",
        "expansion_summary.json",
        "expansion_events.jsonl",
        "expansion_disclosures.jsonl",
        "expansion_episodes.jsonl",
        "expansion_discovery.jsonl",
    )
    files = []
    for name in names:
        path = cfg.ledger_dir / name
        index = path.with_suffix(".parts.json")
        if index.exists():
            files.append({"path": index.name, "sha256": digest(index)})
            files.extend(
                {"path": s["path"], "sha256": s["sha256"]}
                for s in read_json(index)["files"]
            )
        else:
            files.append({"path": path.name, "sha256": digest(path)})
    write_json(
        cfg.ledger_dir / "expansion_manifest.json",
        {
            "schema_version": VERSION,
            "run_id": summary["run_id"],
            "source_manifest_sha256": summary["manifest_sha256"],
            "files": files,
            "public_contains_raw_market_data": False,
        },
    )
    return {
        "run_id": summary["run_id"],
        "events": info["rows"],
        "summary": str(cfg.ledger_dir / "expansion_summary.json"),
    }
