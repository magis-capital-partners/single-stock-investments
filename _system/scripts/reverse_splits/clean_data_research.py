"""Fixed-policy data recovery, exclusion queue and trade-count attribution.

The original 46-recent/83-full-history case is reproduced before repairing
data. No filter, sizing, cost, exit, conviction or parameter optimization.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from itertools import repeat
from pathlib import Path

from .calmar_research import END, START, bind_inputs, path_metrics
from .clean_data_facts import document_bodies, standard_facts
from .clean_data_sources import (action_from_filing, collect, event_clock,
                                 identity_from_action_symbol, identity_from_filing, identity_from_scheduled_cover, issuer_from_finra_name)
from .clean_data_sources import primary_document
from .coverage_data import NY, catalogue_inputs, chart_url, parse_chart
from .coverage_research import write_public_json
from .free_evidence import extract_terms, sha
from .ledger import read_json
from .net_edge import moment
from .net_edge_evidence import ALIASES, digest, filing_rating, monetary_facts, validate_import
from .net_edge_study import (PriceStore, build_snapshots, cost_curve, cost_observations,
                             donor_rows, entry_day, make_outcomes, public_borrow_history,
                             read_evidence, simulate)
from .net_edge_v3 import Account, StudyPolicy, payoff_forecast

RECENT = "2023-10-14"
BASE_ID = "post_split_next_open_10_p20_s20_f60_fundamental_risk200"
ALLOWED_ACTIONS = {"primary_schedule_matched", "primary_schedule_only", "structured_corporate_action"}
CODE_HASHES = {name: digest(Path(__file__).with_name(name)) for name in
               ("clean_data_research.py", "clean_data_sources.py", "clean_data_facts.py", "net_edge_evidence.py",
                "net_edge_study.py", "net_edge_v3.py", "net_edge_clock.py", "coverage_data.py")}
FACT_PARSER_HASH = CODE_HASHES["clean_data_facts.py"]
TERM_PARSER_HASH = sha((FACT_PARSER_HASH+digest(Path(__file__).with_name("free_evidence.py"))).encode())


def repaired_events(original, sources):
    """Accept new issuer links only with dated primary security evidence."""
    events, rejected, duplicates = [], [], []
    for original_event in original:
        e = {k: copy.deepcopy(v) for k, v in original_event.items() if k != "outcomes"}
        key = e["event_id"]
        identity = sources.get("identities", {}).get(key)
        if identity and identity.get("status") in {"confirmed_dated_SEC_cover", "confirmed_dated_SEC_name_FINRA_action", "confirmed_primary_action_and_symbol", "confirmed_primary_action_dated_cover_symbol"}:
            e.update(cik=identity["cik"], issuer="cik/"+identity["cik"], database_ticker=identity["ticker"])
            if e["ticker"] != identity["ticker"]:
                e["original_ticker"] = e["ticker"]
                e["ticker"] = identity["ticker"]
            e["identity_evidence"] = identity
        action = sources.get("actions", {}).get(key)
        if action and action.get("status") == "confirmed_primary_scheduled_action" and str(e.get("cik", "")).lstrip("0") == action["cik"]:
            known = moment(action["known_at"])+timedelta(minutes=1)
            # An unverified original clock cannot outrank a dated filing clock.
            if e.get("verification") not in ALLOWED_ACTIONS or not moment(e.get("available_at")) or known < moment(e["available_at"]):
                e["available_at"] = known.isoformat()
                e["clock_basis"] = "SEC_acceptance_plus_one_minute"
            e.update(ratio=action["ratio"], ratio_basis="primary_filing", verification="primary_schedule_matched", action_evidence=action)
        reason = None
        company = e.get("company") or ""
        if re.search(r"\b(?:exchange.traded (?:fund|note)|ETF|ETN|warrants?|preferred stock)\b", company, re.I): reason = "instrument_outside_common_equity_sleeve"
        elif e.get("verification") not in ALLOWED_ACTIONS: reason = "primary_action_unverified"
        elif not isinstance(e.get("ratio"), (float, int)) or not 0 < e["ratio"] < 1: reason = "reverse_ratio_unverified"
        elif not moment(e.get("available_at")): reason = "announcement_clock_unverified"
        if reason: rejected.append({"key": key, "ticker": e["ticker"], "reason": reason}); continue
        events.append(e)
    grouped = defaultdict(list)
    for e in events:
        grouped[e.get("issuer", "unresolved_symbol/"+e["ticker"]), e.get("ex_date"), round(e["ratio"], 10)].append(e)
    result = []
    for rows in grouped.values():
        rows.sort(key=lambda e: (moment(e["available_at"]), e["event_id"]))
        result.append(rows[0])
        duplicates += [{"key": e["event_id"], "ticker": e["ticker"], "reason": "duplicate_issuer_action", "canonical_key": rows[0]["event_id"]} for e in rows[1:]]
    return sorted(result, key=lambda e: e["event_id"]), rejected+duplicates


def validated_price_overlay(source, destination, events):
    """Validate each price segment against >=3 original nominal closes.

    Median discrepancy <=2%, 90th percentile <=5%. Units are selected only
    from the two documented chart conventions. Historical volume remains a
    proxy and is excluded from the main repair replay.
    """
    _, frozen, _, _ = catalogue_inputs(source)
    base = PriceStore(frozen/"prices.sqlite", events)
    inputs = read_json(destination/"local/coverage_v4/inputs.json")
    overlay, audits, chart_actions = {}, [], {}
    for index, status in enumerate(inputs["price_status"]):
        ticker = status["ticker"]
        path = destination/"local/coverage_v4/price_cache"/(sha(chart_url(ticker).encode())+".raw")
        if not path.exists(): continue
        meta, raw = read_json(path.with_suffix(".json")), path.read_bytes()
        raw_sha = sha(raw)
        if meta.get("url") != chart_url(ticker) or meta.get("sha256") != raw_sha: raise ValueError("Chart provenance mismatch")
        bars, _, _ = parse_chart(raw, ticker)
        original = base.prices(ticker)
        groups = defaultdict(list)
        for day, row in bars.items(): groups[row["_future_split_factor"]].append(day)
        accepted, rejected = 0, 0
        kept = {}
        for future, days in groups.items():
            ratios = sorted(original[d]["close"]/bars[d]["close"] for d in days if original.get(d, {}).get("close"))
            if len(ratios) < 3: rejected += len(days); continue
            center = ratios[len(ratios)//2]
            factor = min((1., 1/future), key=lambda f: abs(center/f-1))
            deviations = sorted(abs(r/factor-1) for r in ratios)
            if deviations[len(deviations)//2] > .02 or deviations[int(.9*(len(deviations)-1))] > .05:
                rejected += len(days); continue
            for day in days:
                row = bars[day]
                kept[day] = {**row, **{k: row[k]*factor for k in ("open", "high", "low", "close")},
                             "volume": None, "proxy_volume": row["volume"]/factor if row.get("volume") is not None else None,
                             "nominal_units": "overlap_validated", "source_url": chart_url(ticker), "source_sha256": raw_sha}
            accepted += len(days)
        if kept:
            # Retain only the event windows already declared by the RSI-4
            # acquisition; lifetime bars are unnecessary for this replay.
            windows = inputs.get("supplemental", {}).get(ticker, {})
            overlay[ticker] = {d: r for d, r in kept.items() if d in windows}
            chart_actions[ticker] = inputs.get("chart_actions", {}).get(ticker, [])
        audits.append({"ticker": ticker, "validated_bars": accepted, "rejected_or_unmatched_bars": rejected,
                       "retained_bars": len(overlay.get(ticker, {})), "source_url": chart_url(ticker), "source_sha256": raw_sha})
        if index % 250 == 0: print(f"Validate nominal prices {index+1}/{len(inputs['price_status'])}", flush=True)
    base.connection.close()
    return overlay, chart_actions, audits


class CleanStore(PriceStore):
    def __init__(self, database, events, overlay, chart_actions=None, *, volume_proxy=False):
        super().__init__(database, events)
        self.overlay, self.volume_proxy = overlay, volume_proxy
        self.unit_conflicts = []
        for ticker, rows in (chart_actions or {}).items():
            original = dict(self.actions[ticker])
            for day, ratio in rows:
                if day in original and abs(original[day]/ratio-1) > .001:
                    self.unit_conflicts.append({"ticker": ticker, "date": day})
                    self.overlay = {k: v for k, v in self.overlay.items() if k != ticker}
                elif day not in original: self.actions[ticker].add((day, ratio))

    def prices(self, ticker):
        if ticker not in self.cache:
            original = super().prices(ticker)
            supplemental = {d: {**r, "volume": r.get("proxy_volume") if self.volume_proxy else None} for d, r in self.overlay.get(ticker, {}).items()}
            if self.volume_proxy:
                basis = dict(self.connection.execute("SELECT date,volume_basis FROM price_provenance WHERE ticker=? AND nominal=1", (ticker,)))
                original = {d: {**r, "volume": supplemental[d]["volume"], "volume_source": "public_volume_proxy"}
                            if basis.get(d) == "three_venues_not_consolidated" and supplemental.get(d, {}).get("volume", 0) and supplemental[d]["volume"] >= (r.get("volume") or 0) else r
                            for d, r in original.items()}
            self.cache[ticker] = dict(sorted({**supplemental, **original}.items()))
        return self.cache[ticker]


def price_event_universe(original, events, sources=None):
    """A corrected ticker/ratio must replace its old split-adjustment record."""
    replaced = {e["event_id"] for e in events}
    if sources:
        # A corrected duplicate can be absent from the cleaned event list.
        # Its stale symbol must still leave the corporate-action stream.
        replaced.update(sources["identities"])
        replaced.update(k for k, row in sources["actions"].items() if row.get("status") == "confirmed_primary_scheduled_action")
    return [e for e in original if e["event_id"] not in replaced]+events


def _extract_filing(item, cache_root):
    key, meta = item
    cik = key.split("/")[0]
    path = Path(meta["path"])
    if digest(path) != meta["source_sha256"]: raise ValueError("Primary filing changed")
    document = primary_document(path, cik)
    if not document: raise ValueError("Primary filing lost its identity/clock")
    parser_hash = FACT_PARSER_HASH
    cache_path = Path(cache_root)/"extracted_facts"/(meta["source_sha256"]+".json")
    cached = read_json(cache_path, {})
    if (cached.get("schema_version") == "clean_facts_cache.v2" and cached.get("parser_sha256") == parser_hash and cached.get("cik") == cik
            and cached.get("source_clock") == document["known_at"] and cached.get("filed_at") == document["filed_at"]):
        facts = cached["facts"]
    else:
        facts = standard_facts(document, cik)
        write_public_json(cache_path, {"schema_version": "clean_facts_cache.v2", "parser_sha256": parser_hash, "cik": cik,
                                       "source_clock": document["known_at"], "filed_at": document["filed_at"], "facts": facts})
    facts = copy.deepcopy(facts)
    for row in facts:
        # Separate SEC acceptance from the conservative public-use time.
        row["known_at"] = (moment(row["known_at"])+timedelta(minutes=1)).isoformat()
        validate_import(row, "facts")
    term_path = Path(cache_root)/"filing_terms"/(meta["source_sha256"]+".json")
    term_hash = TERM_PARSER_HASH
    cached_terms = read_json(term_path, {})
    if cached_terms.get("parser_sha256") == term_hash:
        terms = cached_terms["terms"]
    else:
        terms, seen = [], Counter()
        for filename, _, body in document_bodies(document["text"], prose=True):
            for term in extract_terms({**document, "text": body}):
                if seen[term["category"]] >= 2: continue
                seen[term["category"]] += 1
                terms.append({**term, "locator": "document="+filename+"; "+term["locator"]})
        write_public_json(term_path, {"parser_sha256": term_hash, "terms": terms})
    # A clock rule can become more conservative while the filing bytes and
    # passage parser stay unchanged. Rebind cached passages to this checked clock.
    terms = [{**term, "known_at": document["known_at"]} for term in terms]
    return cik, facts, {**meta, "known_at": document["known_at"], "filed_at": document["filed_at"], "terms": terms}


def filing_fact_index(sources, cache_root):
    rows, by_cik, documents = [], defaultdict(list), defaultdict(list)
    # Independent, offline files only. Executor.map preserves source order;
    # public request pacing is unaffected by these local extraction workers.
    with ProcessPoolExecutor(max_workers=4) as pool:
        for index, (cik, facts, document) in enumerate(pool.map(_extract_filing, sources["documents"].items(), repeat(cache_root))):
            rows += facts
            by_cik[cik] += facts
            documents[cik].append(document)
            if index % 50 == 0: print(f"Extract dated filing facts {index+1}/{len(sources['documents'])}", flush=True)
    return by_cik, documents, {"reported_facts": len(rows), "filings_with_extracted_facts": len({r["source_sha256"] for r in rows}),
                               "distinct_issuers": len({r["issuer"] for r in rows})}


def validate_sources(sources, events):
    """Re-derive every accepted identity/action from its hash-bound primary file."""
    by_key = {e["event_id"]: e for e in events}
    quarantined = []
    for kind in ("identities", "actions"):
        for key, row in list(sources[kind].items()):
            if row.get("status") == "conflicting_primary_actions": continue
            path = Path(row["document_path"])
            if digest(path) != row["source_sha256"]: raise ValueError("Changed primary evidence: "+key)
            document = primary_document(path, row["cik"])
            if not document: raise ValueError("Primary evidence lost CIK/clock: "+key)
            document["_audit_cache"] = str(path.parents[2]/"classifications")
            document["_classifier_hash"] = sha("".join(digest(Path(__file__).with_name(n)) for n in ("expansion.py", "event_audit.py", "filings.py")).encode())
            if kind == "identities":
                method = {"confirmed_dated_SEC_cover": identity_from_filing, "confirmed_dated_SEC_name_FINRA_action": issuer_from_finra_name,
                          "confirmed_primary_action_dated_cover_symbol": identity_from_scheduled_cover, "confirmed_primary_action_and_symbol": identity_from_action_symbol}.get(row["status"])
                expected = method(by_key[key], row["cik"], document) if method else None
            else:
                document["_audit_cache"] = str(path.parents[2]/"classifications")
                document["_classifier_hash"] = sha("".join(digest(Path(__file__).with_name(n)) for n in ("expansion.py", "event_audit.py", "filings.py")).encode())
                expected = action_from_filing(by_key[key], row["cik"], document)
            if not expected or any(row.get(k) != expected.get(k) for k in ("status", "known_at", "source_sha256", "ticker" if kind == "identities" else "ratio")):
                quarantined.append({"key": key, "kind": kind, "reason": "primary_source_recheck_requires_reconciliation", "source_url": row["source_url"]})
                sources[kind].pop(key)
                continue
            if kind == "identities" and sources["candidates"][key]["basis"] == "ambiguous_name" and not action_from_filing(by_key[key], row["cik"], document):
                quarantined.append({"key": key, "kind": kind, "reason": "ambiguous_issuer_action_not_confirmed", "source_url": row["source_url"]})
                sources[kind].pop(key)
    sources["quarantined_recoveries"] = quarantined


def apply_financials(snapshots, sources, fact_index):
    from .fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    cache = OrderedDict()
    for s in snapshots.values():
        cik = s["cik"]
        meta = sources["facts"].get(cik)
        raw = {"cik": cik, "facts": {}}
        if meta:
            if cik not in cache:
                path = Path(meta["path"])
                if digest(path) != meta["sha256"]: raise ValueError("Financial source changed")
                data = read_json(path)
                if not data.get("cik"):
                    binding = read_json(path.with_name(path.name+".identity.json"), {})
                    if binding.get("companyfacts_sha256") != meta["sha256"] or str(binding.get("cik", "")).lstrip("0") != cik: raise ValueError("Missing financial identity binding")
                    data = {**data, "cik": cik}
                cache[cik] = data
                if len(cache) > 8: cache.popitem(last=False)
            cache.move_to_end(cik)
            raw = cache[cik]
        if meta or fact_index.get(cik):
            # Add missing reported contexts without displacing an already known
            # canonical raw fact with a lower-priority alias from an exhibit.
            known_metrics, _ = monetary_facts(raw, s["known_at"])
            present = {(metric, r.get("start"), r["end"], r["unit"]) for metric, rows in known_metrics.items() for r in rows}
            additions = [r for r in fact_index.get(cik, ()) if (r["metric"], r.get("start"), r["end"], r["unit"]) not in present]
            additions.sort(key=lambda r: (moment(r["known_at"]), -ALIASES[r["metric"]].index(r["tag"].split(":")[-1])))
            fund = filing_rating(raw, s["known_at"], screen, overrides=additions, expected_cik=cik)
            s["fundamental"], s["screen_rating"] = fund, fund["score"]
            s["framework_features"] = {**{k: v for k, v in s["framework_features"].items() if not k.startswith("numeric:")},
                                       **{"numeric:"+k: v["score"] for k, v in fund["signals"].items()}}
        if s["key"] in sources["identities"]: s["identity_verified"] = True
    return snapshots


def evaluate(name, snapshots, store, evidence, costs, policy, account, sessions, output):
    scored = {k: copy.deepcopy(s) for k, s in snapshots.items() if s["screen_rating"] is not None}
    outcomes = make_outcomes(scored, store, policy, sessions, END)
    donors = donor_rows(scored, outcomes, policy)
    candidates = []
    for key, s in scored.items():
        forecast = payoff_forecast(s, donors, policy)
        curve = cost_curve({**s, "price": outcomes[key].get("entry_price") or s["price"]}, costs, policy) if forecast["status"] == "estimated" else []
        candidates.append({"snapshot": s, "forecast": forecast, "outcome": outcomes[key], "curve": curve})
    rows, results = [], {}
    for start, period in ((START, "full"), (RECENT, "recent")):
        result = simulate(copy.deepcopy(candidates), policy, account, sessions, store, evidence, variant="fundamental", keep_daily=True, start_day=start)
        write_public_json(output/(name+"_"+period+".json"), result)
        results[period] = result
        metrics = path_metrics(result["daily_equity_curve"], account.equity, start, END) if result["performance_valid"] else {"net_pnl": None, "calmar": None}
        rows.append({"period": period, "start": start, "end": END, "scored_records": len(result["journal"]),
                     "closed_trades": len(result["trade_ledger"]), "admitted_trades": sum(r.get("shares", 0) > 0 for r in result["journal"]),
                     "issuers": len({r["issuer"] for r in result["trade_ledger"]}), "unresolved": result["unresolved_admitted_names"],
                     "performance_valid": result["performance_valid"], "skipped": result["skipped"], **metrics})
    print(name, [(r["period"], r["closed_trades"]) for r in rows], flush=True)
    return {"id": name, "windows": rows}, results, outcomes, candidates


def decision_reasons(result, snapshots, outcomes):
    rows = {r["key"]: "admitted" if r.get("shares", 0) > 0 else r.get("reason") or "unresolved_decision" for r in result["journal"]}
    for key, s in snapshots.items():
        if s["screen_rating"] is None: rows[key] = s["fundamental"]["status"]
        else: rows.setdefault(key, outcomes.get(key, {}).get("status", "not_in_evaluation_window"))
    return rows


def transition_rows(before, after, previous_results, results, previous_outcomes, outcomes, previous_snapshots, snapshots):
    rows = []
    for period in ("full", "recent"):
        a = {r["key"]: r for r in previous_results[period]["trade_ledger"]}
        b = {r["key"]: r for r in results[period]["trade_ledger"]}
        old_reasons = decision_reasons(previous_results[period], previous_snapshots, previous_outcomes)
        new_reasons = decision_reasons(results[period], snapshots, outcomes)
        for key in sorted(a.keys() ^ b.keys()):
            row = b.get(key, a.get(key))
            rows.append({"from_stage": before, "to_stage": after, "period": period, "key": key, "ticker": row["ticker"],
                         "change": "added" if key in b else "removed", "before_reason": old_reasons.get(key, "outside_prior_scored_universe"),
                         "after_reason": new_reasons.get(key, "removed_or_deduplicated"), "entry_day": row["entry_day"]})
    return rows


def build_queue(original, events, rejected, snapshots, outcomes, results, sources, documents, policy, account, sessions, store):
    event_map, rejection = {e["event_id"]: e for e in events}, {r["key"]: r for r in rejected}
    reasons = decision_reasons(results["full"], snapshots, outcomes)
    groups = Counter(e.get("issuer", "unresolved_symbol/"+e["ticker"]) for e in original)
    rows = []
    for e in original:
        key = e["event_id"]
        current, s = event_map.get(key, e), snapshots.get(key)
        identity = sources["identities"].get(key)
        candidate = sources["candidates"].get(key, {})
        blockers = []
        if key in rejection: blockers.append(rejection[key]["reason"])
        if not current.get("cik"): blockers.append("historical_issuer_identity_missing")
        if s and s["screen_rating"] is None: blockers.append(s["fundamental"]["status"])
        day = entry_day(s, policy, sessions) if s else None
        outcome = outcomes.get(key, {})
        if s and day and not outcome:
            before = store.prior(s["database_ticker"], day)
            outcome = {"entry_day": day, "entry_price": store.prices(s["database_ticker"]).get(day, {}).get("open"),
                       "prior_adv": sum(r["volume"]*store.factor(s["database_ticker"], r["date"], day) for r in before if r.get("volume") is not None)/20 if before else None}
            if not outcome["entry_price"]: outcome["status"] = "entry_price_unavailable"
        if outcome.get("status") == "entry_price_unavailable": blockers.append("entry_price_unavailable")
        first = reasons.get(key, blockers[0] if blockers else "not_in_evaluation_window")
        if first == "minimum_order_or_capacity": blockers.append("verify_volume_units_and_full_market_volume")
        if s and s["screen_rating"] is not None and s["screen_rating"] < policy.fundamental_floor: blockers.append("reported_score_below_60_policy_exclusion")
        if first == "admitted": blockers = []
        rating = s.get("screen_rating") if s else None
        decision_at = datetime.fromisoformat(day).replace(tzinfo=NY, hour=9, minute=30) if day else None
        if decision_at and event_clock(current) and event_clock(current) >= decision_at:
            blockers.append("publication_after_entry_window")
        cap_shares = math.floor(outcome.get("prior_adv", 0)*account.participation) if outcome.get("prior_adv") else None
        capacity = cap_shares*outcome["entry_price"] if cap_shares is not None and outcome.get("entry_price") else None
        cik = str(current.get("cik") or "").lstrip("0")
        eligible_documents = [d for d in documents.get(cik, []) if event_clock(current) and moment(d["known_at"]) <= event_clock(current)
                              and (not decision_at or moment(d["known_at"]) < decision_at)]
        leads = [r for d in eligible_documents for r in d["terms"]]
        financial_evidence = []
        for f in s.get("fundamental", {}).get("evidence", []) if s else []:
            accession = str(f.get("accn") or "").replace("-", "")
            url = f.get("source_url") or (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/" if cik.isdigit() and len(accession) == 18 else None)
            financial_evidence.append({**{k: f.get(k) for k in ("tag", "start", "end", "filed", "known_at", "val", "unit")}, "source_url": url})
        # No outcome, P&L, target or later return participates in acquisition priority.
        recent = (e.get("ex_date") or "") >= RECENT
        tier = (0 if rating is not None and rating >= 60 and len(blockers) == 1 else
                1 if current.get("cik") and rating is None and outcome.get("entry_price") else
                2 if current.get("cik") else 3)
        if not blockers or "duplicate_issuer_action" in blockers or "instrument_outside_common_equity_sleeve" in blockers: tier = 9
        rows.append({"key": key, "ticker": current["ticker"], "company": e.get("company"), "ex_date": e.get("ex_date"),
                     "issuer": current.get("issuer"), "cik": cik or None, "candidate_cik": candidate.get("candidate_cik"),
                     "identity_status": identity["status"] if identity else "existing_catalogue_CIK" if e.get("cik") else candidate.get("basis"),
                     "identity_source": {k: identity[k] for k in ("source_url", "source_sha256", "known_at", "locator")} if identity else None,
                     "reported_score": rating, "financial_status": s["fundamental"]["status"] if s else "upstream_action_gate",
                     "first_exclusion": first, "blockers": list(dict.fromkeys(blockers)), "entry_day": day,
                     "volume_capacity_usd": capacity, "minimum_order_usd": policy.minimum_notional,
                     "priority_tier": tier, "recent": recent, "issuer_event_count": groups[e.get("issuer", "unresolved_symbol/"+e["ticker"])],
                     "financing_reconciliation": "incomplete", "full_underwriting": "incomplete",
                     "filing_sources": [{k: d[k] for k in ("source_url", "known_at", "source_sha256", "accessionNumber")} for d in eligible_documents[-4:]],
                     "financial_evidence": financial_evidence, "financing_leads": leads[:6]})
    rows.sort(key=lambda r: (r["priority_tier"], not r["recent"], -r["issuer_event_count"], r["ex_date"] or "", r["key"]))
    return rows


def publish_parts(rows, folder, url_prefix, *, size=150):
    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    for i in range(0, len(rows), size):
        path = folder/f"part-{i//size:03d}.json"
        write_public_json(path, {"schema_version": "shorts_clean_queue_part.v1", "records": rows[i:i+size]})
        parts.append({"url": url_prefix+path.name, "sha256": digest(path), "records": min(size, len(rows)-i)})
    return parts


def run(args):
    source, destination = args.source_root.resolve(), args.destination.resolve()
    output = destination/"local/clean_data_v5"
    output.mkdir(parents=True, exist_ok=True)
    if args.collect: collect(source, destination, fetch=args.fetch, maximum=args.maximum, snapshot_name=args.sources_snapshot)
    if not re.fullmatch(r"sources(?:-[a-z0-9_-]+)?\.json", args.sources_snapshot): raise ValueError("Invalid source snapshot name")
    source_bytes = (output/args.sources_snapshot).read_bytes()
    sources = json.loads(source_bytes)
    if args.publish and not sources.get("collection_complete", True): raise ValueError("An in-progress source checkpoint cannot be published")
    # Freeze the exact bytes read, even if an independent collection finishes
    # during this offline replay. No later source file can alter its binding.
    (output/"used_sources.json").write_bytes(source_bytes)
    original_snapshots, original, frozen, bindings = bind_inputs(source, destination)
    print(f"Recheck {len(sources['identities'])} primary identities and {len(sources['actions'])} actions", flush=True)
    validate_sources(sources, original)
    print("Primary source recheck complete", flush=True)
    if sources["source_manifest_sha256"] != bindings["source_manifest_sha256"]: raise ValueError("Source catalogue changed")
    summary = read_json(destination/"calmar_research.json")
    reference = next(r for r in summary["recent_cases"] if r["id"] == BASE_ID)
    policy, account = StudyPolicy(**reference["policy"]), Account(**reference["account"])
    signature = hashlib.sha256(json.dumps({"policy": asdict(policy), "account": asdict(account)}, sort_keys=True).encode()).hexdigest()
    from .universe_study import trading_calendar
    sessions = tuple(trading_calendar("2018-03-01", "2027-02-01"))
    evidence = read_evidence(destination/"local/edge_inputs")
    evidence["borrow"] += public_borrow_history(source, original)
    costs = cost_observations(source, read_json(source/"local/net_edge_v2/snapshots.json"))
    fact_index, documents, fact_coverage = filing_fact_index(sources, output)
    print("Dated filing extraction complete", fact_coverage, flush=True)
    overlay, chart_actions, price_audits = validated_price_overlay(source, destination, original)
    print("Nominal-price segment checks complete", flush=True)
    stages, transitions = [], []
    previous = None
    last_store = None
    # Clean repairs are cumulative; the last, explicitly separate row is only
    # a volume-proxy sensitivity and never counted as clean recovery.
    for stage in ("original", "scope_and_duplicates", "validated_prices", "reported_financials", "verified_actions_and_identities", "volume_proxy_sensitivity"):
        repaired = stage in {"verified_actions_and_identities", "volume_proxy_sensitivity"}
        events, rejected = repaired_events(original, sources if repaired else {"identities": {}, "actions": {}})
        if stage == "original":
            snapshots = copy.deepcopy(original_snapshots)
            store = PriceStore(frozen/"prices.sqlite", original)
        else:
            if stage == "scope_and_duplicates": store = PriceStore(frozen/"prices.sqlite", original)
            else: store = CleanStore(frozen/"prices.sqlite", price_event_universe(original, events, sources if repaired else None), overlay, chart_actions, volume_proxy=stage == "volume_proxy_sensitivity")
            snapshots, _, _ = build_snapshots(events, store, source, output, evidence)
            if stage in {"scope_and_duplicates", "validated_prices"}:
                # Retain the frozen scores/reviews exactly for existing records.
                snapshots = {k: {**copy.deepcopy(original_snapshots[k]), "price": s["price"], "prior_dollar_adv": s["prior_dollar_adv"]}
                             for k, s in snapshots.items() if k in original_snapshots}
            else: apply_financials(snapshots, sources, fact_index)
        row, results, outcomes, candidates = evaluate(stage, snapshots, store, evidence, costs, policy, account, sessions, output/"cases")
        row.update(policy_sha256=signature, clean_data=stage != "volume_proxy_sensitivity")
        stages.append(row)
        if previous:
            transitions += transition_rows(previous[0], stage, previous[1], results, previous[2], outcomes, previous[3], snapshots)
        if stage == "original":
            counts = {r["period"]: r["closed_trades"] for r in row["windows"]}
            if counts != {"full": 83, "recent": 46}: raise ValueError("Original 83/46 trade counts did not reproduce: "+str(counts))
        if stage == "verified_actions_and_identities":
            queue = build_queue(original, events, rejected, snapshots, outcomes, results, sources, documents, policy, account, sessions, store)
            strict = simulate(copy.deepcopy(candidates), policy, account, sessions, store, evidence, variant="strict", start_day=RECENT)
            strict_count = len(strict["trade_ledger"])
            clean_counts = {"prepared_actions": len(events), "reported_scores": sum(s["screen_rating"] is not None for s in snapshots.values()),
                            "financial_gaps": dict(Counter(s["fundamental"]["status"] for s in snapshots.values() if s["screen_rating"] is None)),
                            "event_exclusions": dict(Counter(r["reason"] for r in rejected))}
        previous = stage, results, outcomes, snapshots
        if last_store: last_store.connection.close()
        last_store = store
    last_store.connection.close()
    queue_parts = publish_parts(queue, destination/"clean_data_queue", "data/shorts_clean_data_queue/")
    write_public_json(destination/"clean_data_changes.json", {"schema_version": "shorts_clean_changes.v1", "records": transitions})
    document = {"schema_version": "shorts_clean_data_research.v1", "built_at": datetime.now(timezone.utc).isoformat(),
                "research_only": True, "authority": "none", "data_cost_usd": 0, "production_policy_changed": False,
                "source_collection_complete": sources.get("collection_complete", True),
                "base_case_id": BASE_ID, "policy": asdict(policy), "account": asdict(account), "policy_sha256": signature,
                "bindings": bindings, "sources_sha256": sha(source_bytes), "stages": stages,
                "code_sha256": CODE_HASHES,
                "coverage": {"catalogue_records": len(original), **clean_counts, "confirmed_identity_records": len(sources["identities"]),
                             "new_identity_records": sum(not e.get("cik") and e["event_id"] in sources["identities"] for e in original),
                             "ambiguous_identity_conflicts": len(sources.get("identity_conflicts", {})),
                             "quarantined_recoveries": len(sources.get("quarantined_recoveries", [])),
                             "primary_action_records": sum(r.get("status") == "confirmed_primary_scheduled_action" for r in sources["actions"].values()),
                             **fact_coverage, "validated_price_symbols": sum(bool(v) for v in overlay.values()), "validated_price_bars": sum(len(v) for v in overlay.values()),
                             "full_underwriting": 0, "reconciled_financing": 0, "strict_recent_trades": strict_count,
                             "actual_locate_approvals": sum(r.get("kind") == "approval" and r.get("approved") is True for r in evidence["borrow"]),
                             "observed_fills": sum(r.get("kind") == "fill" and r.get("observed") is True for r in evidence["executions"])},
                "queue": {"records": len(queue), "parts": queue_parts, "blockers": dict(Counter(b for r in queue for b in r["blockers"])),
                          "priority_rule": "Existing reported score >=60 and one data gate first, then identified issuers with a price, recent events and repeated issuers. No subsequent return or P&L."},
                "changes": {"url": "data/shorts_clean_data_changes.json", "sha256": digest(destination/"clean_data_changes.json"), "records": len(transitions)},
                "acquisition": {"requests_this_run": sources["requests_this_run"], "total_recorded_requests": sources.get("total_recorded_requests"),
                                "uncached_sources_pending": len(sources.get("uncached_sources_pending", [])), "access_stopped": sources.get("access_stopped", False),
                                "network_status": sources["network_status"], "source": "free_SEC_and_cached_public_charts"},
                "limits": ["These are simulated trades; price observations are not fills.", "The baseline reproduces the explored 46/83 case; no new parameter search.",
                           "Only overlap-validated price segments enter the main repair replay; unverified volume is a separate sensitivity.",
                           "Name-index candidates need dated SEC security evidence. Unsupported/ambiguous links remain pending.",
                           "Capital and donor-population interactions can add or remove other names during a fixed-rule replay.",
                           "Underwriting, financing reconciliation, actual locates and execution evidence remain hard gates; source leads do not complete them."]}
    write_public_json(destination/"clean_data_research.json", document)
    write_public_json(output/"price_audit.json", price_audits)
    if errors := audit(destination): raise ValueError("; ".join(errors))
    if args.publish:
        dashboard = Path(__file__).resolve().parents[3]/"dashboard/data"
        shutil.copyfile(destination/"clean_data_research.json", dashboard/"shorts_clean_data_research.json")
        shutil.copyfile(destination/"clean_data_changes.json", dashboard/"shorts_clean_data_changes.json")
        shutil.copytree(destination/"clean_data_queue", dashboard/"shorts_clean_data_queue", dirs_exist_ok=True)
    return document


def audit(root):
    document = read_json(root/"clean_data_research.json")
    errors = []
    if document["data_cost_usd"] != 0 or document["authority"] != "none" or document["production_policy_changed"]: errors.append("authority/cost/policy contract")
    if any(r["policy_sha256"] != document["policy_sha256"] for r in document["stages"]): errors.append("policy drift")
    if document["coverage"]["catalogue_records"] != document["queue"]["records"]: errors.append("catalogue/queue count")
    for spec in document["queue"]["parts"]:
        path = root/"clean_data_queue"/spec["url"].split("/")[-1]
        if digest(path) != spec["sha256"]: errors.append("queue hash "+path.name)
        for row in read_json(path)["records"]:
            for filing in row["filing_sources"]:
                if row["ex_date"] and row["entry_day"] and moment(filing["known_at"]) >= datetime.fromisoformat(row["entry_day"]).replace(tzinfo=NY, hour=9, minute=30): errors.append("future filing in queue "+row["key"])
    if sum(p["records"] for p in document["queue"]["parts"]) != document["queue"]["records"]: errors.append("part reconciliation")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--maximum", type=int, default=2400)
    parser.add_argument("--sources-snapshot", default="sources.json")
    parser.add_argument("--publish", action="store_true")
    run(parser.parse_args(argv))


if __name__ == "__main__": main()
