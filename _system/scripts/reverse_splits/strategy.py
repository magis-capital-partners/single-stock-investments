"""Original, versioned paper strategy and an append-only decision journal.

No orders or broker connections. Historical examples never become prospective
decisions merely because a user fills in today's research form.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .realism import maintenance, rounded_collateral
from .research_lens import LENSES

VERSION = "RSI-1.0"
STRATEGY_ID = "reverse_split_impairment"
RULES = {
    "score_floor": 60, "fundamental_max_age_days": 200,
    "announcement_max_age_days": 7, "max_hold_sessions": 5,
    "carry_calendar_days": 7, "max_names": 3,
    "name_loss_fraction": .005, "sleeve_loss_fraction": .02,
    "notional_fraction": .025, "participation": .001,
    "stress_price_increase": 2.0, "margin_buffer": .20,
    "net_downside_floor": .20, "gross_downside_floor": .30,
    "carry_fraction_ceiling": .10, "minimum_notional": 100,
    "locate_max_age_hours": 4, "quote_max_age_minutes": 15,
}
# The entry gates ``evaluate`` checks, in order, for readers that never run it
# (the hosted dashboard). ``test_rs_strategy`` keeps the ids aligned.
GATES = [
    {"id": "fundamentals", "label": "Point-in-time fundamentals",
     "requires": "Raw filing-availability-filtered SSI score of at least 60, three numeric signals, an operating-company profile and a latest period no more than 200 days old"},
    {"id": "announcement", "label": "Fresh verified announcement",
     "requires": "Substantive parsed announcement no more than seven calendar days old, before any known effective split; accession, ratio, identity and schedule reconciled by the reviewer"},
    {"id": "research", "label": "Six evidence lenses",
     "requires": "All six lenses reviewed with dated primary evidence, a locator, the mechanism, contrary evidence and a falsifier; two impairment lenses supported including cash/financing or operating impairment; valuation and catalyst supported; no contradicted lens"},
    {"id": "payoff", "label": "Net payoff and carry",
     "requires": "At least 30% gross downside to a reachable common-equity target, at least 20% after round-trip costs and seven-day carry, carry no more than 10% of notional"},
    {"id": "catalyst", "label": "Catalyst within hold window",
     "requires": "A dated catalyst within seven calendar days and before a known split; exit after five sessions"},
    {"id": "borrow", "label": "Fresh quote and locate",
     "requires": "Executable quote within 15 minutes, approved locate within four hours with fee, size and reference, and an SSR execution check"},
    {"id": "risk", "label": "Shared-account survival",
     "requires": "Notional of at least $100; all-account stressed margin and existing sleeve loss reconciled; three-name and joint squeeze limits"},
    {"id": "prospective", "label": "Prospective decision",
     "requires": "Evidence date equals the current Eastern date; historical reviews are tagged retrospective and excluded from forward validation"},
]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def policy():
    return {"id": STRATEGY_ID, "version": VERSION, "name": "Reverse Split Impairment",
        "adopted_on": "2026-10-09", "mode": "paper research", "parameters": dict(RULES),
        "rules_hash": hashlib.sha256(_canonical(RULES).encode()).hexdigest(),
        "hypothesis": "A newly announced reverse split can expose financing or operating impairment. Short only when filed deterioration, an equity valuation gap and a near-term catalyst align, and borrow and joint squeeze risk are affordable.",
        "origin": "Original proposal informed by Short Alpha and selected library sections. No reconstruction of Michael's selections; thresholds were chosen after inspecting this historical dataset.",
        "entry": "Review a substantive announcement within seven calendar days. Enter only after all gates pass and a fresh locate and executable quote are recorded. Paper entry is a plan; it is not an order or a simulated fill. Expired announcements require a new independently sourced event.",
        "exit": "Cover after five sessions including entry, before a known split effective date, or when the catalyst resolves, the falsifier occurs or borrow is recalled. A 50% adverse price move triggers a cover instruction at the next executable opportunity; gaps and halts can exceed the loss budget. Never average into a losing short.",
        "selection": "Raw as-of score ≥60, at least three numeric signals, latest period ≤200 days old. Review all six lenses; at least two of the first four must be supported, including cash/financing or operating impairment. Valuation and catalyst/path must both be supported. Contradicted lenses block entry.",
        "sizing": "Whole shares limited by a 0.5% equity name loss budget under a +200% price shock, stressed carry and costs; 2% joint sleeve loss, three names, 2.5% notional, 0.1% prior 20-session ADV, locate size and stressed margin with a 20% equity buffer. These are chosen research limits, not guaranteed maximum losses.",
        "payoff": "Require ≥30% gross valuation downside and ≥20% after entered round-trip costs and seven-day carry, with carry ≤10% of notional. Stress carry at triple the quoted fee and collateral at triple the entry price. Target value must be plausibly attainable within the five-session catalyst window.",
        "validation": [
            "Freeze this version before collecting future outcomes; log every lead, pass and review, including missing data and unavailable borrow.",
            "Use actual paper fill observations and daily marked equity after all costs; a ready decision is not performance. Preserve deposits/withdrawals separately to calculate time-weighted returns.",
            "Compare split-only, fundamentals-only and combined portfolios using the same eligible point-in-time universe and capital rules. Current historical examples remain exploratory.",
            "Report net TWR, drawdown, expected shortfall, worst issuer, carry drag, fill/locate rejection rate, uncertainty clustered by issuer and calendar, and incremental whole-portfolio drawdown and risk. No Sharpe is available until a valid daily equity series exists.",
            "At 30 closed paper trades across ≥20 issuers and ≥6 months, review evidence rather than automatically approve deployment. Keep a later untouched cohort and disclose every version change.",
        ],
        "links": {"margin": "https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210",
                  "rule_201": "https://www.sec.gov/files/rules/final/2010/34-61595-secg.htm"}}


def triage(score, asof):
    issues = []
    if not score.get("historical_eligible") or score.get("source") != "raw_companyfacts":
        issues.append("Raw point-in-time fundamentals unavailable")
    if score.get("score") is None or score.get("score", 0) < RULES["score_floor"]:
        issues.append("Deterioration score below 60 or unscored")
    if score.get("evidence_count", 0) < 3:
        issues.append("Fewer than three numeric fundamental signals")
    period = score.get("latest_period")
    if not period or (date.fromisoformat(asof) - date.fromisoformat(period)).days > RULES["fundamental_max_age_days"]:
        issues.append("Fundamental period missing or more than 200 days old")
    return {"eligible": not issues, "reasons": issues}


def build_strategy(snapshot, verified, bridge):
    from .framework_plan import plan, routes
    asof = snapshot["research"]["as_of"]
    # Every parsed announcement stays visible; never require future completion,
    # a price path, or a historically profitable trade to enter the queue.
    latest = {}
    for event in verified:
        key = event["ticker"]
        if key not in latest or event.get("announce_date", "") > latest[key].get("announce_date", ""):
            latest[key] = event
    for candidate in snapshot["research"]["candidates"]:
        latest.setdefault(candidate["ticker"], {"ticker": candidate["ticker"], "name": candidate["name"],
                           "cik": candidate["current"].get("cik"), "announce_date": None})
    leads = []
    for ticker, event in latest.items():
        score = bridge.score(ticker, event.get("cik"), asof)
        screen = triage(score, asof)
        announced = event.get("announce_date")
        fresh = bool(announced and 0 <= (date.fromisoformat(asof) - date.fromisoformat(announced[:10])).days <= 7)
        leads.append({"ticker": ticker, "name": event.get("name", ticker), "cik": event.get("cik"),
            "announcement_date": announced, "announcement_url": event.get("source_url") or event.get("filing_url"),
            "announced_ex_date": event.get("announced_ex_date"), "announced_ratio": event.get("announced_ratio"),
            "verified_announcement": bool(announced), "fresh_announcement": fresh,
            "score": score["score"], "signals": score["evidence_count"], "lenses": score["lenses"],
            "latest_period": score["latest_period"], "score_as_of": asof, "triage": screen,
            "status": "Research priority" if screen["eligible"] and fresh else "Archive · research example" if not fresh else "Insufficient fundamentals",
            "fundamental": score, "framework_routes": routes(score)})
    leads.sort(key=lambda r: (not r["fresh_announcement"], not r["triage"]["eligible"], r["score"] is None, -(r["score"] or 0), r["ticker"]))
    return {"policy": policy(), "research_plan": plan(), "as_of": asof, "candidates": leads, "verified_announcements": len(verified),
        "coverage": {"leads": len(leads), "triage_pass": sum(r["triage"]["eligible"] for r in leads),
                     "fresh_announcements": sum(r["fresh_announcement"] for r in leads)},
        "historical_proxy": {"book_id": "fundamental_60", "usage": "Quantitative screen only. It omits the analyst, valuation, catalyst and borrow gates and does not measure this strategy."},
        "portfolio_contract": {"strategy_id": STRATEGY_ID, "version": VERSION,
            "position_fields": ["owner", "strategy_id", "ticker", "issuer_cik", "entry_time", "shares", "price", "fees", "borrow", "decision_id"],
            "daily_fields": ["date", "owner", "strategy_id", "opening_nav", "closing_nav", "external_flows_with_times", "realized_pnl", "unrealized_pnl", "borrow", "commissions", "dividends_owed", "gross_exposure", "margin_required"],
            "status": "SSI mapping prepared; live portfolio data are not connected. Owner, cash-flow and strategy tagging must reconcile before incremental portfolio performance is calculated."}}


def _number(payload, key, default=0, low=0, high=1e12):
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"{key}: enter a number") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key}: value outside allowed range")
    return value


def _moment(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment if moment.tzinfo else None
    except ValueError:
        return None


def _url(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def evaluate(lead, payload, now=None):
    from .framework_plan import summarize
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    asof = str(payload.get("as_of") or today.isoformat())
    try:
        day = date.fromisoformat(asof)
    except ValueError:
        raise ValueError("as_of must be YYYY-MM-DD") from None
    if day > today:
        raise ValueError("A decision cannot use a future evidence date")
    current_score = lead["fundamental"]
    if asof != current_score["as_of"]:
        raise ValueError("Evidence date must match the frozen fundamental snapshot; refresh the dashboard for a new date")
    equity = _number(payload, "equity", 50000, low=1)
    price = _number(payload, "price", 0)
    adv = _number(payload, "adv", 0)
    fee = _number(payload, "fee_annual", 1, high=100)
    cost = _number(payload, "round_trip_cost_fraction", .02, high=1)
    target = _number(payload, "target_price", 0)
    available = _number(payload, "locate_shares", 0)
    existing_loss = _number(payload, "existing_sleeve_stress_loss", 0)
    existing_margin = _number(payload, "existing_margin", 0)
    other_account_loss = _number(payload, "other_account_stress_loss", 0)
    existing_names = _number(payload, "existing_names", 0, high=10000)
    if int(existing_names) != existing_names:
        raise ValueError("existing_names must be a whole number")
    stress = RULES["stress_price_increase"]
    # Stressed broker requirement for the rest of the account is user-supplied.
    # Reserve borrowing at 3x fee and 3x price; rounded collateral matters most
    # at low prices. Include commission floors before flooring the share count.
    carry_days = RULES["carry_calendar_days"]
    carry_unit = rounded_collateral(1, price) * fee * carry_days / 360 if price else 0
    stress_carry_unit = rounded_collateral(1, price * (1 + stress)) * fee * 3 * carry_days / 360 if price else 0
    unit_loss = price * (stress + cost) + stress_carry_unit
    remaining = max(0, min(equity * RULES["name_loss_fraction"], equity * RULES["sleeve_loss_fraction"] - existing_loss))
    limits = {"name_and_sleeve_loss": max(0, remaining - 2) / (unit_loss + .01) if unit_loss else 0,
              "notional": equity * RULES["notional_fraction"] / price if price else 0,
              "liquidity": adv * RULES["participation"], "locate": available}
    stress_margin_unit = maintenance(1, price * 3) if price else 0
    # Require remaining equity AFTER the joint squeeze to meet stressed margin.
    available_equity = equity * (1 - RULES["margin_buffer"])
    capacity = max(0, available_equity - existing_margin - existing_loss - other_account_loss - 2)
    limits["stressed_margin"] = capacity / (stress_margin_unit + unit_loss + .01) if price else 0
    shares = max(0, math.floor(min(limits.values()))) if price >= 1 and existing_names < RULES["max_names"] else 0
    commission = 2 * max(1, .005 * shares)
    # Include commissions above their minimum in the final dollar-budget check.
    while shares and (shares * unit_loss + commission > remaining or
                      shares * (stress_margin_unit + unit_loss) + existing_loss + other_account_loss + existing_margin + commission > available_equity):
        shares -= 1
        commission = 2 * max(1, .005 * shares)
    notional = shares * price
    carry_fraction = carry_unit / price if price else None
    gross_downside = 1 - target / price if price and target else None
    net_downside = gross_downside - (carry_fraction or 0) - cost - commission / notional if gross_downside is not None and notional else None
    reviews = payload.get("lens_reviews") or []
    if not isinstance(reviews, list) or len(reviews) > 6:
        raise ValueError("lens_reviews must contain at most six lenses")
    by_id = {}
    for review in reviews:
        if not isinstance(review, dict) or review.get("lens_id") in by_id:
            raise ValueError("Each review lens must appear once")
        by_id[review.get("lens_id")] = review
    complete, supported, review_issues, grades = [], [], [], []
    for lens in LENSES:
        review = by_id.get(lens["id"], {})
        state = review.get("status", "unreviewed")
        if state not in {"unreviewed", "unresolved", "supported", "contradicted"}:
            raise ValueError("Invalid lens review status")
        known = str(review.get("known_at") or "")[:10]
        valid = bool(state != "unreviewed" and known and known <= asof and _url(review.get("source_url"))
                     and all(str(review.get(k, "")).strip() for k in ("locator", "mechanism", "contradictory_evidence", "falsifier")))
        if known:
            try:
                valid = valid and date.fromisoformat(known) <= day
            except ValueError:
                valid = False
        if valid:
            complete.append(lens["id"])
            grades.append({"contradicted": 0, "unresolved": 1, "supported": 2}[state])
            if state == "supported":
                supported.append(lens["id"])
        else:
            review_issues.append(lens["label"] + ": dated evidence, locator, contrary evidence and falsifier required")
        if state == "contradicted":
            review_issues.append(lens["label"] + ": original short mechanism contradicted")
    # This is a documentation grade, never a probability or fitted alpha score.
    quality = round(sum(grades) / 12 * 100, 1) if len(complete) == 6 else None
    mechanism = set(supported) & {"earnings_quality", "cash_and_financing", "operating_impairment", "disclosures_and_control"}
    lens_pass = len(complete) == 6 and not review_issues and len(mechanism) >= 2 and bool(mechanism & {"cash_and_financing", "operating_impairment"}) and {"valuation_and_payoff", "catalyst_and_path"} <= set(supported)
    locate_time, quote_time = _moment(payload.get("locate_at")), _moment(payload.get("quote_at"))
    locate_fresh = bool(locate_time and 0 <= (now - locate_time).total_seconds() <= RULES["locate_max_age_hours"] * 3600 and available >= shares > 0)
    quote_fresh = bool(quote_time and 0 <= (now - quote_time).total_seconds() <= RULES["quote_max_age_minutes"] * 60 and price >= 1)
    announcement = lead.get("announcement_date")
    fresh = bool(announcement and 0 <= (day - date.fromisoformat(announcement[:10])).days <= RULES["announcement_max_age_days"])
    schedule = lead.get("announced_ex_date")
    before_split = not schedule or day < date.fromisoformat(schedule[:10])
    catalyst = str(payload.get("catalyst_date") or "")
    catalyst_ok = False
    if catalyst:
        try:
            catalyst_day = date.fromisoformat(catalyst)
            catalyst_ok = 0 <= (catalyst_day - day).days <= carry_days and (not schedule or catalyst_day < date.fromisoformat(schedule[:10]))
        except ValueError:
            pass
    screen = triage(current_score, asof)
    gates = [
        {"id": "fundamentals", "label": "Point-in-time fundamentals", "pass": screen["eligible"], "detail": "; ".join(screen["reasons"]) or "Raw score and freshness meet v1 rules"},
        {"id": "announcement", "label": "Fresh verified announcement", "pass": fresh and before_split and payload.get("identity_verified") is True,
         "detail": "No substantive parsed announcement in this queue" if not announcement else "Announcement is outside the seven-day entry window" if not fresh else "Known split is already effective; entry blocked" if not before_split else "Fresh parsed lead; reconcile accession, ratio, identity and schedule"},
        {"id": "research", "label": "Six evidence lenses", "pass": lens_pass, "detail": "; ".join(review_issues) or "Two impairment mechanisms plus valuation and catalyst support required"},
        {"id": "payoff", "label": "Net payoff and carry", "pass": bool(gross_downside is not None and gross_downside >= RULES["gross_downside_floor"] and net_downside is not None and net_downside >= RULES["net_downside_floor"] and carry_fraction <= RULES["carry_fraction_ceiling"]), "detail": "≥30% gross downside, ≥20% after costs, carry ≤10%; target reachable inside hold window"},
        {"id": "catalyst", "label": "Catalyst within hold window", "pass": catalyst_ok and bool(str(payload.get("catalyst", "")).strip()), "detail": "Dated catalyst within seven calendar days and before a known split; exit after five sessions"},
        {"id": "borrow", "label": "Fresh quote and locate", "pass": locate_fresh and quote_fresh and bool(str(payload.get("borrow_reference", "")).strip()) and payload.get("ssr_checked") is True,
         "detail": "Quote ≤15 min; approved locate ≤4 hours; fee, size, approval reference and SSR execution check"},
        {"id": "risk", "label": "Shared-account survival", "pass": notional >= RULES["minimum_notional"] and payload.get("portfolio_reconciled") is True,
         "detail": "Reconcile all-account stressed margin and existing sleeve loss; size ≥$100; three-name and joint squeeze limits"},
        {"id": "prospective", "label": "Prospective decision", "pass": day == today, "detail": "Historical reviews are tagged retrospective and excluded from forward validation"},
    ]
    return {"strategy_id": STRATEGY_ID, "version": VERSION, "ticker": lead["ticker"], "as_of": asof,
        "status": "paper_ready" if all(g["pass"] for g in gates) else "review_required",
        "research_quality": quality, "framework_plan": summarize(current_score, payload),
        "quality_note": "Equal-weight documentation grade: contradicted=0, unresolved=1, supported=2; unknown stays unscored. Not a probability of profit or proof of fraud.",
        "gates": gates, "sizing": {"shares": shares, "notional": notional,
        "limiting_constraint": min(limits, key=limits.get), "gross_downside": gross_downside, "net_downside": net_downside,
        "carry_fraction": carry_fraction, "stress_loss": shares * unit_loss + commission if shares else 0,
        "name_loss_budget": equity * RULES["name_loss_fraction"], "joint_stress_loss": existing_loss + (shares * unit_loss + commission if shares else 0),
        "sleeve_loss_budget": equity * RULES["sleeve_loss_fraction"], "stressed_position_margin": shares * stress_margin_unit,
        "remaining_equity_after_joint_stress": equity - existing_loss - other_account_loss - (shares * unit_loss + commission if shares else 0),
        "commission": commission if shares else 0}, "prospective": day == today,
        "warning": "Sizing uses entered assumptions. Actual auction spreads, recalls, gaps and margin changes can exceed this stress. Readiness is not an executed position."}


def portfolio_stress(payload):
    equity = _number(payload, "equity", 50000, low=1)
    long_notional = _number(payload, "long_notional", 0)
    other_short = _number(payload, "other_short_notional", 0)
    sleeve = _number(payload, "sleeve_notional", 0)
    base_loss = _number(payload, "base_stress_loss", 0)
    result = []
    # Joint scenarios, not beta estimates or a claim that this sleeve hedges SSI.
    for label, lm, sm, rs in [("Broad risk-off", -.20, -.10, -.15),
                               ("Speculative squeeze", .05, .50, 2.0),
                               ("Portfolio loss + short squeeze", -.20, .50, 2.0)]:
        before = long_notional * lm - other_short * sm - base_loss
        added = -sleeve * rs
        result.append({"scenario": label, "base_pnl": before, "sleeve_pnl": added,
                       "combined_pnl": before + added, "combined_return": (before + added) / equity})
    return {"scenarios": result, "net_exposure": (long_notional - other_short - sleeve) / equity,
        "gross_exposure": (long_notional + other_short + sleeve) / equity,
        "sleeve_price_stress_loss": sleeve * RULES["stress_price_increase"],
        "sleeve_stress_budget": equity * RULES["sleeve_loss_fraction"],
        "within_sleeve_budget_before_costs": sleeve * RULES["stress_price_increase"] <= equity * RULES["sleeve_loss_fraction"],
        "note": "Manual exposures and chosen joint shocks; no live SSI holdings, estimated correlation, borrow costs or portfolio-return series. This is a stress illustration, not a risk-adjusted return estimate."}


def _connect(cfg):
    path = getattr(cfg, "decisions_db_path", None) or Path(cfg.data_dir) / "strategy_decisions.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, ticker TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)")
    return conn


def decisions(cfg):
    with closing(_connect(cfg)) as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT payload FROM decisions ORDER BY rowid DESC")]


def record_decision(cfg, lead, payload, now=None):
    from .framework_plan import furnace_drafts, plan
    now = now or datetime.now(timezone.utc)
    result = evaluate(lead, payload, now)
    state = payload.get("decision", "review")
    if state not in {"review", "pass", "paper_ready"}:
        raise ValueError("Decision must be review, pass or paper_ready")
    if not str(payload.get("reason", "")).strip():
        raise ValueError("Record why you are reviewing, passing or preparing this candidate")
    if state == "paper_ready" and result["status"] != "paper_ready":
        raise ValueError("All entry gates must pass before recording paper readiness")
    record = {"id": str(uuid.uuid4()), "recorded_at": now.isoformat(), "ticker": lead["ticker"],
        "decision": state, "reason": str(payload["reason"]), "supersedes": payload.get("supersedes") or None,
        "prospective": result["prospective"], "policy": policy(), "fundamental_snapshot": lead["fundamental"],
        "announcement_snapshot": {k: lead.get(k) for k in ("announcement_date", "announcement_url", "cik")},
        "inputs": payload, "evaluation": result, "research_plan": plan(),
        "furnace_drafts": furnace_drafts(lead["ticker"], lead["fundamental"], payload),
        "source_system": "reverse_split_research", "usage": "research decision; not an order or realized return"}
    with closing(_connect(cfg)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if record["supersedes"]:
            prior = conn.execute("SELECT ticker FROM decisions WHERE id=?", (record["supersedes"],)).fetchone()
            if not prior or prior[0] != lead["ticker"]:
                raise ValueError("Correction must reference an existing decision for this issuer")
        prior = conn.execute("SELECT record_hash FROM decisions ORDER BY rowid DESC LIMIT 1").fetchone()
        record["previous_hash"] = prior[0] if prior else ""
        record["record_hash"] = hashlib.sha256(_canonical(record).encode()).hexdigest()
        conn.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?)", (record["id"], record["recorded_at"], lead["ticker"], _canonical(record), record["previous_hash"], record["record_hash"]))
    return record


def handoff(cfg, strategy):
    from .framework_plan import plan
    records = decisions(cfg)
    return {"schema_version": "reverse_split_strategy_handoff.v1", "policy": strategy["policy"],
        "portfolio_contract": strategy["portfolio_contract"], "research_plan": strategy.get("research_plan") or plan(), "decisions": records,
        "review_queue": [{"ticker": r["ticker"], "cik": r.get("cik"), "stage": "lead",
                          "source_system": "reverse_split_research", "strategy_id": STRATEGY_ID,
                          "frameworks": r["lenses"], "hypothesis": "", "sources": [r.get("announcement_url")],
                          "announcement_date": r.get("announcement_date"), "fundamental_score": r["score"],
                          "score_as_of": r["score_as_of"], "triage": r["triage"],
                          "framework_routes": r.get("framework_routes"),
                          "research": {"status": "requires_analyst_review"}, "fraud_bad_actors": "unscored"}
                         for r in strategy.get("candidates", []) if r["fresh_announcement"]],
        "performance": {"status": "not_measured", "closed_paper_trades": 0, "net_twr": None, "sharpe": None,
                        "reason": "Research decisions contain no executed fills or daily cash-flow-adjusted equity."},
        "usage": "Read-only SSI import draft. Reconcile owner allocation and accepted positions separately; never infer trades from readiness decisions."}
