"""One-session research, source-backed exit audit and frozen forward cohort.

Individual prices/returns remain local. Only aggregates and evidence metadata
are published. An unresolved loan is never written off because prices stop.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import bisect
import math
import os
import shutil
import sqlite3

from .analysis import cluster_interval
from .expansion import digest, location
from .expansion_imports import evidence, validate
from .ledger import read_json, write_json
from .rerun import eligible_score


def apply_reviews(conn, events, document):
    reviews = document.get("reviews", []) + evidence(conn, "action_review")
    for row in reviews:
        validate("action_review", row)
        archived = conn.execute("SELECT sha256 FROM collection_sources WHERE url=? AND status='archived'", (row["source_url"],)).fetchone()
        if not archived or archived[0] != row["source_sha256"]:
            raise ValueError("Action review source is not archived with the claimed hash")
        matches = [e for e in events if e["event_id"] == row["event_id"] and e["ticker"] == row["ticker"] and e["ex_date"] == row["ex_date"]]
        if len(matches) != 1:
            raise ValueError("Action review must resolve exactly one catalogue event")
        matches[0]["action_review"] = {**row, "usage": "retrospective share/price reconciliation; excluded from entry signals"}


def freeze_facts(cfg, bridge, target):
    """Reuse only immutable, hash-matched files from a completed snapshot."""
    previous = read_json(location(cfg) / "latest_run.json", {})
    prior = location(cfg) / previous.get("path", "missing")
    hashes = {r["name"]: r["sha256"] for r in read_json(prior / "manifest.json", {}).get("companyfacts", [])}
    target.mkdir()
    counts = Counter()
    for source in bridge.cache.glob("CIK*.json"):
        frozen = prior / "companyfacts" / source.name
        destination = target / source.name
        if frozen.exists() and hashes.get(source.name) == digest(source) == digest(frozen):
            try:
                os.link(frozen, destination)
                counts["immutable_hardlinks"] += 1
                continue
            except OSError:
                pass
        shutil.copy2(source, destination)
        counts["copied"] += 1
    bridge.cache = target
    return dict(counts)


def summarize(rows, field="net_return"):
    if not rows:
        return {"events": 0, "issuers": 0, "mean": None, "median": None, "positive_share": None, "issuer_interval": {"low": None, "high": None}}
    values = sorted(r[field] for r in rows)
    n = len(values)
    return {"events": n, "issuers": len({r["issuer"] for r in rows}),
            "mean": sum(values) / n, "median": (values[(n-1)//2] + values[n//2]) / 2,
            "positive_share": sum(v > 0 for v in values) / n,
            "issuer_interval": cluster_interval(rows, field=field, cluster="issuer"),
            "year_interval": cluster_interval(rows, field=field, cluster="year")}


def one_day_study(observed, post, calendar, flags, frames, bridge, protocol, root):
    # Descriptive event benchmark and tradable-time eligibility are distinct.
    primary, years = [], defaultdict(list)
    for event in observed:
        if event["verification"] not in {"primary_schedule_matched", "structured_corporate_action"}:
            continue
        outcome = next(o for o in event["outcomes"] if o["cohort"] == "ex_plus_1_h1")
        if outcome["status"] == "observed_price_path":
            row = {"event_id": event["event_id"], "issuer": event["issuer"], "year": event["ex_date"][:4], "net_return": outcome["gross_short_return"]}
            primary.append(row)
            years[row["year"]].append(row)
    eligible, screened, liquid = [], [], []
    exclusions = Counter()
    for lead in post:
        day = lead["entry_date"]
        status = flags.get("states", {}).get((lead["ticker"], day))
        if (lead["ticker"], day) in flags.get("restricted", set()) or status is True:
            exclusions["SSR_skip_no_delayed_entry"] += 1
            continue
        row = lead["rows"][day]
        if not math.isfinite(row['close']) or row['close']<=0:
            exclusions['eligible_entry_exit_unavailable']+=1
            continue
        result = {"event_id": lead["id"], "issuer": "cik/" + str(lead["cik"]), "year": day[:4], "net_return": 1 - row["close"] / row["open"]}
        eligible.append(result)
        if eligible_score(lead["fundamental"], 60):
            screened.append(result)
            prior = lead["prior_row"]
            spread = max(0.0001 if row["open"] < 1 else 0.01, (prior["high"] - prior["low"]) * .25)
            size = min(1250 / row["open"], .001 * lead["adv"])
            cost = (spread + .005 * row["open"] + 2 * max(1, size * .005) / max(1, size) + math.ceil(row["open"] * 1.02) / 360) / row["open"]
            if size * row["open"] >= 100 and cost <= protocol["maximum_expected_cost_fraction"]:
                liquid.append(result)
            else:
                exclusions["pre_entry_cost_or_capacity_screen"] += 1
    write_json(root / "one_day_paths.local.json", {"primary": primary, "eligible": eligible, "fundamental": screened, "cost_capacity": liquid})
    return {"definition": "Verified split; next exchange session open to same-session close. Equal event weights. Gross = 1 - close/open.",
            "primary": summarize(primary), "available_before_entry_and_SSR_not_observed": summarize(eligible),
            "fundamental_60_fixed": summarize(screened), "cost_capacity_subset": summarize(liquid),
            "by_year": [{"year": y, **summarize(r)} for y, r in sorted(years.items())],
            "exclusions": dict(exclusions), "cost_screen_basis": "Prior high-low spread proxy, prior 20-session volume, one borrowing day at 100% annual sensitivity, commissions and 25bp slippage per side; no observed future close used for selection.",
            "limits": "Research selected from the observed price universe. Unknown SSR, approved locates and actual quotes prevent a claim of executable net profitability. Financial screen stays at 60; current industry metadata is a limitation."}


def matched_controls(post, events, frames, bridge, protocol, root, flags):
    identities, ambiguous, dates = {}, set(), defaultdict(list)
    for e in events:
        ticker = e.get("database_ticker", e["ticker"])
        if e.get("action_review", {}).get("decision") == "not_corporate_action":
            continue
        dates[ticker].append(e["ex_date"])
        if str(e.get("cik") or "").isdigit():
            cik = str(int(e["cik"]))
            if ticker in identities and identities[ticker] != cik:
                ambiguous.add(ticker)
            identities[ticker] = cik
    results, missing, chosen = [], Counter(), []
    divisions={ticker:(read_json(bridge.cache / f'CIK{int(cik):010d}.issuer.json',{}).get('sic') or (bridge.sic.get(ticker) or {}).get('sic')) for ticker,cik in identities.items()}
    feature_cache = {}
    def features(ticker, day):
        key = ticker, day
        if key in feature_cache:
            return feature_cache[key]
        f = frames.get(ticker)
        j = bisect.bisect_left(f.dates, day) if f else 0
        answer = None
        if f and j >= 20 and j < len(f.dates) and f.dates[j] == day:
            p, v = f.close[j-1], sum(f.volume[j-20:j]) / 20
            if all(math.isfinite(x) and x > 0 for x in (p, v)):
                answer = (p, p*v, j)
        feature_cache[key] = answer
        return answer
    for lead in post:
        if not eligible_score(lead["fundamental"], 60):
            continue
        day, ticker = lead["entry_date"], lead["ticker"]
        if flags.get("states", {}).get((ticker, day)) is True or (ticker, day) in flags.get("restricted", set()):
            missing["SSR_skip_no_delayed_entry"] += 1
            continue
        if not math.isfinite(lead['rows'][day]['close']) or lead['rows'][day]['close']<=0:
            missing['subject_exit_unavailable']+=1
            continue
        subject = features(ticker, day)
        if not subject:
            missing["subject_features_unavailable"] += 1
            continue
        subject = (subject[0], subject[0] * lead["adv"], subject[2])
        low = (date.fromisoformat(day) - timedelta(days=30)).isoformat()
        high = (date.fromisoformat(day) + timedelta(days=30)).isoformat()
        candidates = []
        for control, cik in sorted(identities.items()):
            if control in ambiguous or cik == str(lead["cik"]) or any(low <= d <= high for d in dates[control]):
                continue
            feat = features(control, day)
            if not feat:
                continue
            price_distance, volume_distance = abs(math.log(feat[0]/subject[0])), abs(math.log(feat[1]/subject[1]))
            if price_distance > math.log(2) or volume_distance > math.log(3):
                continue
            control_sic=divisions.get(control)
            subject_sic=lead['fundamental'].get('sic')
            if not str(control_sic or '').isdigit() or subject_sic is None or int(control_sic)//1000!=int(subject_sic)//1000:
                continue
            score = bridge.score(control, cik, day)
            if not eligible_score(score, 60) or abs(score["score"] - lead["fundamental"]["score"]) > 15:
                continue
            if score.get("sic") is None or lead["fundamental"].get("sic") is None or int(score["sic"])//1000 != int(lead["fundamental"]["sic"])//1000:
                continue
            candidates.append((price_distance + volume_distance + abs(score["score"]-lead["fundamental"]["score"])/15, control, feat[2]))
        # Select solely from pre-entry features; missing outcomes do not cause replacement.
        picked = sorted(candidates)[:3]
        returns = []
        for _, control, j in picked:
            f = frames[control]
            if all(math.isfinite(x) and x > 0 for x in (f.open[j], f.close[j])):
                returns.append(1-f.close[j]/f.open[j])
        if not picked or len(returns) != len(picked):
            missing["no_matches_or_selected_outcome_unavailable"] += 1
            continue
        row = lead["rows"][day]
        short = 1-row["close"]/row["open"]
        results.append({"issuer": "cik/"+str(lead["cik"]), "year": day[:4], "net_return": short-sum(returns)/len(returns), "subject": short, "control": sum(returns)/len(returns)})
        chosen.append({"event_id": lead["id"], "date": day, "controls": [p[1] for p in picked]})
    write_json(root / "control_matches.local.json", {"matches": chosen, "outcomes": results})
    return {"excess_gross": summarize(results), "subject_gross": summarize(results, "subject"), "control_gross": summarize(results, "control"), "exclusions": dict(missing),
            "matching": protocol["controls"], "universe": "Historical nominal ticker histories with resolved issuer in the event catalogue. Different issuer; no catalogued split within +/-30 days. Partial, event-derived control pool; not the whole market.",
            "limitations": "Uses current SIC division and retrospectively excludes future splits for a diagnostic comparison. Historical ticker/security class and unobserved actions remain incomplete. No causal or executable alpha claim."}


def exit_audit(root, previous, events, frames, reviews, conn):
    cases = read_json(previous / "plan.json", {}).get("cases", [])
    cutoff=read_json(root/'plan.json')['cutoff']
    paths = {}
    for case in cases:
        old = read_json(previous / (case["id"] + ".json"), {})
        new = read_json(root / (case["id"] + ".json"), {})
        after = {p["id"]: p for p in new.get("positions", [])}
        for p in old.get("positions", []):
            if not p["remaining"]:
                continue
            key = p["ticker"], p["entry_date"], p["planned_exit"]
            q = after.get(p["id"])
            ticker, entry, planned = key
            frame = frames.get(ticker)
            blocked = [e for e in events if e["ticker"] == ticker and entry < e["ex_date"] <= (planned or "9999") and e["verification"] not in {"primary_schedule_matched", "structured_corporate_action"} and e.get("action_review", {}).get("decision") != "not_corporate_action"]
            transitions = [r for r in reviews.get("venue_transitions", []) if r["ticker"] == ticker and entry < r["effective_date"] <= (planned or "9999")]
            category = "corrected_data_linkage" if q and not q["remaining"] else "OTC_exit_prices_unavailable" if transitions else "unverified_subsequent_action" if blocked else "fractional_obligation_requires_broker_settlement" if p.get("fractional_obligation_seen") else "partial_exit_capacity_or_later_price_gap" if p.get("partial_covers") else "official_exit_or_security_history_unavailable"
            row = paths.setdefault(key, {"ticker": ticker, "cik": p["cik"], "entry_date": entry, "planned_exit": planned,
                "historical_identity": "issuer resolved; ticker/security-class interval requires dated broker/security record",
                "old_last_mark": p["mark_date"], "category": category, "cases": [],
                "subsequent_verified_actions": [{"date": e["ex_date"], "ratio": e["ratio"], "source_url": e.get("source_url")} for e in events if e["ticker"] == ticker and entry < e["ex_date"] <= cutoff and e["verification"] in {"primary_schedule_matched", "structured_corporate_action"}],
                "exit_price_observation": bool(frame and planned in frame.dates and math.isfinite(frame.close[frame.dates.index(planned)])),
                "evidence": transitions + [e["action_review"] for e in events if e["ticker"] == ticker and e.get("action_review")],
                "actual_borrow_end": "unknown; a modeled cover is not evidence of broker loan return"})
            row["cases"].append({"case": case["id"], "old_remaining_shares": p["remaining"], "new_remaining_shares": q["remaining"] if q else None, "new_cover_date": q.get("last_cover_date") if q else None, "new_share_factor":q['factor'] if q else None, "applied_share_adjustments":q.get('share_adjustments',[]) if q else [], "status":"modeled_cover_not_actual_broker_settlement" if q and not q['remaining'] else 'unresolved_obligation'})
    return {"baseline_run_id": previous.name, "audited_paths": len(paths), "by_category": dict(Counter(r["category"] for r in paths.values())), "paths": list(paths.values()), "loan_records": len(evidence(conn, "loan_event")), "policy": "Every earlier residual path retained. Actual loan termination remains unknown without dated broker evidence; missing prices never create a zero-price cover."}


def borrow_and_forward(conn, protocol, cutoff):
    fees, loans, locates = evidence(conn, "borrow_fee"), evidence(conn, "loan_event"), evidence(conn, "borrow")
    vintages = evidence(conn, "forward_observation")
    latest = {}
    for row in vintages:
        latest[row["event_id"], row["date"]] = row
    observations = list(latest.values())
    completed = [{"issuer": r["security_id"], "year": r["date"][:4], "net_return": (r["shares"]*(r["entry_fill"]-r["exit_fill"])-r["borrow_paid"]-r["commission_paid"])/(r["shares"]*r["entry_fill"])} for r in observations if r["shares"] > 0 and protocol["validation_starts"] <= r["date"] <= cutoff]
    return ({"dated_fee_records": len(fees), "fee_records_by_class": dict(Counter(r["evidence_class"] for r in fees)), "approved_locates": sum(r["approved"] for r in locates), "loan_event_records": len(loans), "historical_actual_costs_complete": False, "basis": "Source-backed dated broker statements replace scenario fees on their effective dates. Quotes remain quoted economics; public indications never confer approval. Unsupplied dates retain explicit sensitivity assumptions."},
            {"protocol": protocol, "completed": summarize(completed), "status": "awaiting_new_events" if not completed else "collecting_frozen_cohort", "records": len(observations), "costs_basis": "Imported actual fills, borrow paid and commissions; spread/slippage embedded in fills. Locate reference required. Loan settlement separately audited."})


def refresh_forward(cfg, *, cutoff=None, offline=False):
    """Incremental public-source monitor. No broker connection or paid pull."""
    import hashlib
    from .expansion import connect, discover_history, collect_filings, utcnow
    from .borrow_archive import archive
    from .fundamentals import FundamentalBridge
    from .universe_study import trading_calendar
    cutoff = cutoff or date.today().isoformat()
    protocol = read_json(cfg.ledger_dir / "forward_protocol.json")
    collection_start = max("2026-10-01", (date.fromisoformat(cutoff)-timedelta(days=7)).isoformat())
    if not offline:
        discover_history(cfg, collection_start, cutoff)
        discover_history(cfg, collection_start, cutoff, query='"ADS ratio" OR "depositary share ratio"', forms=('6-K', '6-K/A'), job_kind='search_ads')
        collect_filings(cfg, start=collection_start, end=cutoff)
        archive(cfg)
    conn = connect(cfg)
    path = cfg.ledger_dir / "forward_status.json"
    old = read_json(path, {})
    registry = {r["event_key"]: r for r in old.get("registry", [])}
    bridge = FundamentalBridge(cfg)
    calendar = trading_calendar("2026-10-01", (date.fromisoformat(cutoff)+timedelta(days=60)).isoformat())
    try:
        for d in conn.execute("SELECT * FROM disclosures WHERE eligible=1 AND stage='scheduled_action' AND scheduled>=? AND filed_at<=? ORDER BY available_at", (protocol["validation_starts"], cutoff)):
            key = hashlib.sha256(str((d['cik'], d['ticker'], d['scheduled'], d['ratio'])).encode()).hexdigest()[:24]
            if key in registry:
                continue
            index = bisect.bisect_left(calendar, d['scheduled'])+1
            entry = calendar[index] if index < len(calendar) else None
            score = bridge.score(d['ticker'], d['cik'], cutoff)
            registry[key] = {"event_key": key, "ticker": d['ticker'], "cik": d['cik'], "ex_date": d['scheduled'], "next_session": entry,
                "first_recorded_at": utcnow(), "source_available_at": d['available_at'], "source_url": f"https://www.sec.gov/Archives/edgar/data/{d['cik']}/{d['accession']}/",
                "status": "date_outside_calendar_requires_review" if not entry else "awaiting_action_identity_quote_locate_and_margin_evidence" if entry > cutoff else "recorded_after_planned_entry_no_prospective_trade_claim",
                "fundamental_at_enrollment": {k:score.get(k) for k in ('score','evidence_count','as_of','latest_period','historical_eligible')},
                "approved_locate": False, "actual_fills_available": False}
        borrowing, forward = borrow_and_forward(conn, protocol, cutoff)
        document = {"schema_version": "reverse_split_forward.v1", "protocol_sha256": digest(cfg.ledger_dir / 'forward_protocol.json'), "as_of": cutoff, "built_at": utcnow(), "registry": sorted(registry.values(), key=lambda r:(r['ex_date'],r['ticker'] or '')), "borrow_economics": borrowing, "validation": forward,
                    "source_mode": "cached_public_sources" if offline else "incremental_SEC_and_public_IBKR_inventory",
                    "limits": "Enrollment is not an approved trade. Price benchmarks, broker approvals and actual settlements must be supplied. Missing observations do not become zero-return results."}
        write_json(path, document)
        return {"registry_events": len(registry), "completed_events": forward['completed']['events'], "path": str(path)}
    finally:
        conn.close()
