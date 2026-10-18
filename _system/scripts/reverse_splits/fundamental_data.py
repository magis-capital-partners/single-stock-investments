"""Additional reported financial evidence; no missing-value or custom-tag guesses.

The original financial score remains reproducible. This adapter adds independently
dated liquidity/debt evidence and reports coverage separately from deterioration.
"""
from __future__ import annotations

import math
import re
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .clean_data_facts import TAGS, standard_facts
from .clean_data_sources import primary_document
from .ledger import read_json
from .net_edge import moment
from .net_edge_clock import market_date
from .net_edge_evidence import ALIASES, days, digest, filing_rating, monetary_facts

EXTRA = {
    "restricted_cash": ("RestrictedCashAndCashEquivalentsCurrent", "RestrictedCashCurrent"),
    "short_term_investments": ("ShortTermInvestments", "ShortTermInvestmentsAvailableForSale"),
    "current_borrowings": ("DebtCurrent", "CurrentBorrowings"),
    "short_term_borrowings": ("ShortTermBorrowings",),
    "debt_due_one_year": ("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",),
    "long_term_debt_including_current": ("LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities",),
}
STANDARD_EXTENSIONS = {"ifrs-full:CashFlowsFromUsedInOperatingActivities": "cfo"}
EXTRA_TAGS = {**TAGS, **STANDARD_EXTENSIONS, **{ns+":"+tag: metric for metric, tags in EXTRA.items()
                        for tag in tags for ns in ("us-gaap", "ifrs-full")}}
FAMILIES = {"accrual_ratio": "earnings_quality", "profit_without_cash": "earnings_quality",
            "cash_burn": "liquidity", "leverage": "solvency",
            "revenue_turn": "operations", "margin_trend": "operations"}


def extended_document(item, cache_root):
    key, meta = item
    cik = key.split("/")[0]
    path = Path(meta["path"])
    if digest(path) != meta["source_sha256"]: raise ValueError("Financial submission changed")
    document = primary_document(path, cik)
    if not document: raise ValueError("Submission lost its issuer identity")
    mappings = meta.get("reviewed_tag_mappings", [])
    signature = digest(Path(__file__)) + digest(Path(__file__).with_name("clean_data_facts.py")) + json.dumps(mappings, sort_keys=True)
    target = Path(cache_root)/"extended_facts"/(meta["source_sha256"]+".json")
    cached = read_json(target, {})
    if cached.get("parser") == signature and cached.get("known_at") == document["known_at"]:
        return cik, cached["records"]
    custom = {}
    for mapping in mappings:
        if (str(mapping.get("cik", "")).lstrip("0") != str(cik) or mapping.get("source_sha256") != meta["source_sha256"]
                or mapping.get("metric") not in set(ALIASES) | set(EXTRA)
                or mapping.get("review_mode") != "blinded_historical_reconstruction" or mapping.get("outcome_blinded") is not True
                or not mapping.get("rationale") or not mapping.get("locator") or not moment(mapping.get("reviewed_at"))
                or mapping.get("tag", "").split(":")[0] in {"us-gaap", "ifrs-full", "dei"}
                or not re.fullmatch(r"[\w.-]+:[\w.-]+", mapping.get("tag", ""))):
            raise ValueError("Custom fact mapping lacks a blinded, filing-bound semantic review")
        custom[mapping["tag"]] = mapping["metric"]
    facts = standard_facts(document, cik, tags={**EXTRA_TAGS, **custom})
    sic = re.search(r"STANDARD INDUSTRIAL CLASSIFICATION:[^\r\n]*\[(\d{4})\]", document["text"][:15000])
    for row in facts:
        row["known_at"] = (moment(row["known_at"])+timedelta(minutes=1)).isoformat()
        row["source_published_at"] = row["known_at"]
        row["document_form"] = meta.get("form")
        if row["tag"] in custom: row["basis"] = "source_reviewed_custom_tag_mapping"
        row["dated_sic"] = int(sic[1]) if sic else None
    from .coverage_research import write_public_json
    write_public_json(target, {"parser": signature, "known_at": document["known_at"], "records": facts})
    return cik, facts


def as_filed_extras(raw, cutoff):
    """Standard, whole-entity Company Facts only; every currency stays explicit."""
    cutoff_day = market_date(cutoff)
    for namespace in ("us-gaap", "ifrs-full"):
        for metric, aliases in EXTRA.items():
            for tag in aliases:
                for unit, rows in raw.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).items():
                    if len(unit) != 3 or not unit.isupper(): continue
                    for r in rows:
                        if (not r.get("filed") or r["filed"] >= cutoff_day or not r.get("end")
                                or r["end"] > cutoff_day or r.get("start") or not isinstance(r.get("val"), (float, int))
                                or not math.isfinite(r["val"])): continue
                        acc = r.get("accn", "")
                        yield {"metric": metric, "value": r["val"], "unit": unit, "end": r["end"],
                               "known_at": r["filed"]+"T00:00:00+00:00", "filed": r["filed"],
                               "tag": namespace+":"+tag, "accession": acc,
                               "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(raw['cik'])}/{acc.replace('-', '')}/",
                               "locator": namespace+":"+tag+"; end="+r["end"], "basis": "sec_companyfacts"}


def quarter_cashflow(metrics, anchor):
    """Use a reported quarter or subtract matched fiscal YTD; never divide YTD."""
    rows = metrics.get("cfo", [])
    for r in sorted((r for r in rows if r["end"] == anchor), key=lambda r: r["filed"], reverse=True):
        length = days(r["start"], r["end"])+1
        if 60 <= length <= 105:
            return {"value": r["val"], "days": length, "evidence": [r], "basis": "reported_quarter"}
        old = [p for p in rows if p["start"] == r["start"] and 60 <= days(p["end"], r["end"]) <= 105]
        if old:
            p = max(old, key=lambda p: (p["end"], p["filed"]))
            return {"value": r["val"]-p["val"], "days": days(p["end"], r["end"]),
                    "evidence": [r, p], "basis": "matched_fiscal_ytd_difference"}
    return None


def enrich(snapshot, raw, facts, screen):
    """Preserve the score, add independently sourced fields and a narrow route.

    Annual periods older than 200 days remain a separate research sensitivity;
    they do not silently qualify for the main three policies.
    """
    cutoff = snapshot["known_at"]
    extension_facts = []
    for name, metric in STANDARD_EXTENSIONS.items():
        namespace, tag = name.split(":")
        for unit, rows in raw.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).items():
            if len(unit) != 3 or not unit.isupper(): continue
            for r in rows:
                if (not r.get("filed") or r["filed"] >= market_date(cutoff) or not r.get("accn")
                        or not r.get("start") or not r.get("end") or r["end"] > market_date(cutoff)
                        or not isinstance(r.get("val"), (float, int)) or not math.isfinite(r["val"])): continue
                extension_facts.append({"issuer": "cik/"+snapshot["cik"], "metric": metric, "value": r["val"],
                    "unit": unit, "start": r["start"], "end": r["end"], "filed": r["filed"], "known_at": r["filed"],
                    "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(snapshot['cik'])}/{r['accn'].replace('-', '')}/",
                    "locator": name+"; period="+r["start"]+"/"+r["end"], "accession": r["accn"]})
    facts = facts+extension_facts
    known_metrics, _ = monetary_facts(raw, cutoff)
    present = {(m, r.get("start"), r["end"], r["unit"]) for m, rows in known_metrics.items() for r in rows}
    additions = [r for r in facts if r["metric"] in ALIASES and
                 (r["metric"], r.get("start"), r["end"], r["unit"]) not in present]
    base = filing_rating(raw, cutoff, screen, overrides=additions, expected_cik=snapshot["cik"])
    metrics, currency = monetary_facts(raw, cutoff, additions)
    anchor = base.get("period")
    extra = list(as_filed_extras(raw, cutoff)) if raw.get("cik") else []
    extra += [r for r in facts if r["metric"] in EXTRA and moment(r["known_at"]) < moment(cutoff)]
    selected = {}
    if anchor:
        for metric in EXTRA:
            rows = [r for r in extra if r["metric"] == metric and r["unit"] == currency
                    and 0 <= days(r["end"], anchor) <= 105]
            if rows:
                end = max(r["end"] for r in rows)
                latest = [r for r in rows if r["end"] == end]
                filed = max(r.get("filed", r["known_at"][:10]) for r in latest)
                latest = [r for r in latest if r.get("filed", r["known_at"][:10]) == filed]
                if len({r["value"] for r in latest}) == 1: selected[metric] = latest[0]
    quarter = quarter_cashflow(metrics, anchor) if anchor else None
    cash = base.get("balances", {}).get("cash")
    cfo = base.get("flows", {}).get("cfo")
    ttm_runway = cash/-cfo if cash is not None and cash >= 0 and cfo is not None and cfo < 0 else None
    quarterly_runway = cash/(-quarter["value"]*365.25/quarter["days"]) if cash is not None and cash >= 0 and quarter and quarter["value"] < 0 else None
    # A reported twelve-month maturity is the catalyst. Current debt components
    # and a financing passage cannot substitute for a reconciled amount/date.
    due = selected.get("debt_due_one_year")
    oi = base.get("flows", {}).get("operating_income")
    fresh = bool(anchor and 0 <= days(anchor, market_date(cutoff)) <= 200)
    profiles = [r for r in facts if r.get("dated_sic") and moment(r["known_at"]) < moment(cutoff)
                and (moment(cutoff)-moment(r["known_at"])).days <= 550]
    latest_profile = max(profiles, key=lambda r: r["known_at"], default=None)
    profile = screen.profile_for(latest_profile["dated_sic"]) if latest_profile else "unknown"
    cash_current = any(r["end"] == anchor and r["val"] == cash for r in metrics.get("cash", []))
    route = bool(profile == "operating" and fresh and cash_current and ttm_runway is not None and ttm_runway <= 1 and
                 quarterly_runway is not None and quarterly_runway <= 1 and
                 oi is not None and oi < 0 and due and due["end"] == anchor and due["value"] > cash and due["value"] > 0)
    signals = base.get("signals", {})
    # The legacy score adds an unreported current debt component as zero.
    # Preserve that original separately; the new policies leave it unknown.
    base["legacy_score"] = base.get("score")
    debt = None
    current = selected.get("current_borrowings")
    noncurrent = [r for r in metrics.get("long_term_debt", []) if
                  any(tag in r["tag"] for tag in ("LongTermDebtNoncurrent", "NoncurrentBorrowings"))
                  and current and r["end"] == current["end"] == anchor]
    if noncurrent:
        r = max(noncurrent, key=lambda r: r["filed"])
        if r["val"] >= 0 and current["value"] >= 0: debt = r["val"]+current["value"]
    signals.pop("leverage", None)
    assets = base.get("balances", {}).get("total_assets")
    assets_current = any(r["end"] == anchor and r["val"] == assets for r in metrics.get("total_assets", []))
    if not cash_current: signals.pop("cash_burn", None)
    if not assets_current: signals.pop("accrual_ratio", None)
    if debt is not None and assets_current and assets and assets > 0:
        value = debt/assets
        score = screen.ramp(value, **screen.THRESHOLDS["debt_to_assets"])
        if oi is not None and oi < 0 and debt > 0: score = min(1., score+.5)
        if base.get("balances", {}).get("stockholders_equity", 0) < 0: score = 1.
        signals["leverage"] = {"value": value, "score": score}
    base["leverage_evidence"] = {"complete_reported_debt": debt,
                                  "basis": "same_period_reported_noncurrent_and_total_current_borrowings" if debt is not None else "unknown_component_not_zero"}
    rules = screen.PROFILE_RULES.get(profile, {})
    for name in list(signals):
        if rules.get("skip") or name in rules.get("disable", set()): signals.pop(name)
    weights = sum(screen.FUNDAMENTAL_SIGNALS[k][1] for k in signals)
    base["score"] = round(100*sum(v["score"]*screen.FUNDAMENTAL_SIGNALS[k][1] for k, v in signals.items())/weights, 1) if len(signals) >= 3 and weights else None
    if base.get("period") and fresh: base["status"] = "scored" if base["score"] is not None else "fewer_than_three_independent_signals"
    families = sorted({FAMILIES[k] for k in signals if k in FAMILIES})
    base["coverage"] = {"signal_count": len(signals), "independent_family_count": len(families),
                        "families": families, "missing_is_healthy": False,
                        "dated_operating_profile": profile,
                        "profile_known_at": latest_profile["known_at"] if latest_profile else None,
                        "current_debt_complete": debt is not None,
                        "cash_matches_flow_period": cash_current,
                        "assets_match_flow_period": assets_current,
                        "restricted_cash_reported": "restricted_cash" in selected,
                        "short_term_investments_reported": "short_term_investments" in selected}
    base["supplemental"] = {k: {f: r.get(f) for f in ("value", "unit", "end", "known_at", "source_url", "locator", "source_sha256")} for k, r in selected.items()}
    base["liquidity"] = {"ttm_runway_years": ttm_runway, "quarter_runway_years": quarterly_runway,
                         "quarter_cashflow": quarter, "cash_distress_route": route,
                         "route_basis": "cash_and_two_burn_windows_plus_reported_twelve_month_debt_maturity_and_operating_loss"}
    # Frequency-aware diagnostic only: no projected cash and no stale admission.
    if base["status"] == "stale_or_missing_period" and anchor and days(anchor, market_date(cutoff)) <= 400:
        old = filing_rating(raw, cutoff, screen, overrides=additions, expected_cik=snapshot["cik"], max_age_days=400)
        base["older_period_diagnostic"] = {"score": old.get("score"), "age_days": days(anchor, market_date(cutoff)),
                                          "eligible": False, "reason": "intervening_results_and_financing_need_reconciliation"}
    snapshot["fundamental"], snapshot["screen_rating"] = base, base["score"]
    for r in base.get("evidence", []):
        if not r.get("source_url") and r.get("accn"):
            r["source_url"] = f"https://www.sec.gov/Archives/edgar/data/{int(snapshot['cik'])}/{r['accn'].replace('-', '')}/"
    snapshot["cash_distress_route"] = route
    return snapshot


def gate(snapshot, policy):
    score = snapshot.get("screen_rating")
    if policy == "unfiltered": return True
    if policy == "score60": return score is not None and score >= 60
    if policy == "score50": return score is not None and score >= 50
    if policy == "score60_or_distress": return score is not None and score >= 60 or snapshot.get("cash_distress_route") is True
    raise ValueError("Unknown fundamental policy")


def read_market_evidence(path):
    """Only provider-bound, reviewed nominal bars / full-market share volume.

    The raw JSON receipt must independently contain the exact reported values.
    Unverified public chart volume is deliberately not an acceptable receipt.
    """
    accepted, rejected, conflicts = defaultdict(dict), Counter(), set()
    if not Path(path).exists(): return {}, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        try:
            if r.get("kind") not in {"price", "volume"}: raise ValueError("market_evidence_kind_unverified")
            if r.get("provider") not in {"databento", "nyse", "nasdaq", "crsp", "massive"}: raise ValueError("provider_unverified")
            parsed = urlsplit(r.get("source_url", ""))
            domains = {"databento": ("databento.com",), "nyse": ("nyse.com",), "nasdaq": ("nasdaq.com",),
                       "crsp": ("crsp.org", "crsp.com"), "massive": ("massive.com", "polygon.io")}[r["provider"]]
            if parsed.scheme != "https" or parsed.username or parsed.password or not any(parsed.hostname == h or (parsed.hostname or "").endswith("."+h) for h in domains): raise ValueError("provider_source_mismatch")
            if not r.get("identity_verified") or not r.get("split_units_verified"): raise ValueError("identity_or_split_units_unverified")
            if r.get("basis") != "nominal_as_traded": raise ValueError("nominal_units_unverified")
            datetime.fromisoformat(r["date"])
            path = Path(r["receipt_path"])
            if digest(path) != r.get("receipt_sha256"): raise ValueError("receipt_hash_mismatch")
            receipt = read_json(path)
            if receipt.get("ticker") != r["ticker"] or receipt.get("date") != r["date"] or receipt.get("source_url") != r.get("source_url"): raise ValueError("receipt_identity_mismatch")
            if not str(r.get("source_url", "")).startswith("https://"): raise ValueError("source_missing")
            if not moment(r.get("known_at")): raise ValueError("availability_missing")
            fields = ("volume",) if r.get("kind") == "volume" else ("open", "high", "low", "close")
            if fields == ("volume",) and (r.get("scope") != "US_consolidated" or receipt.get("scope") != r["scope"]): raise ValueError("volume_scope_unverified")
            if any(not isinstance(r.get(k), (int, float)) or not math.isfinite(r[k]) or r[k] <= 0 or receipt.get(k) != r[k] for k in fields): raise ValueError("receipt_values_mismatch")
            key = r["ticker"], r["date"]
            if key in conflicts: raise ValueError("conflicting_market_evidence")
            old = accepted[key[0]].get(key[1], {})
            if any(k in old and old[k] != r[k] for k in fields):
                accepted[key[0]].pop(key[1], None)
                conflicts.add(key)
                raise ValueError("conflicting_market_evidence")
            accepted[key[0]][key[1]] = {**old, **{k: r[k] for k in fields}, "known_at": r["known_at"],
                                      ("volume_known_at" if fields == ("volume",) else "price_known_at"): r["known_at"]}
        except (KeyError, ValueError, OSError, TypeError) as exc:
            rejected[str(exc)] += 1
    return {ticker: rows for ticker, rows in accepted.items() if rows}, dict(rejected)
