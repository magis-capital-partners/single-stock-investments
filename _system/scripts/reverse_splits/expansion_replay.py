"""Exploratory v2 experiments with complete eligibility reasons and evidence gates.

The frozen v1 output is read as a comparison only. A fresh input/source/code
manifest identifies each v2 snapshot; no published experiment is overwritten.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import bisect
import json
import math

from .adjust import PriceFrame, to_nominal
from .execute import session_open
from .expansion import (
    SecArchive,
    SourceUnavailable,
    connect,
    episodes,
    export_coverage,
    job,
    utcnow,
)
from .expansion_imports import evidence
from .filings import parse_accept_time
from .framework_plan import routes
from .rerun import eligible_score, write_json
from .run_book import load_events, load_frames, load_splits


def refresh_fundamentals(cfg, *, offline=False):
    conn = connect(cfg)
    archive = SecArchive(cfg, conn, offline)
    cache = cfg.raw_dir / "companyfacts"
    cache.mkdir(parents=True, exist_ok=True)
    ciks = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT cik FROM disclosures WHERE eligible=1 ORDER BY cik"
        )
    ]
    counts = Counter()
    for cik in ciks:
        for kind in ("facts", "issuer"):
            path = cache / (
                f"CIK{int(cik):010d}"
                + (".issuer" if kind == "issuer" else "")
                + ".json"
            )
            if path.exists():
                counts["cached"] += 1
                continue
            url = (
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
                if kind == "facts"
                else f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
            )
            try:
                data = archive.json(url)
                if int(data.get("cik", -1)) != int(cik):
                    raise ValueError("Companyfacts identity mismatch")
                if kind == "issuer":
                    data = {
                        k: data.get(k)
                        for k in (
                            "cik",
                            "name",
                            "sic",
                            "sicDescription",
                            "tickers",
                            "exchanges",
                        )
                    }
                    data["fetched_at"] = utcnow()
                if kind == "facts" and not data.get("facts"):
                    raise ValueError("Empty companyfacts")
                write_json(path, data)
                job(
                    conn,
                    "fundamentals",
                    f"{cik}/{kind}",
                    "completed",
                    {"file": path.name},
                )
                counts["downloaded"] += 1
            except (SourceUnavailable, ValueError) as exc:
                job(
                    conn,
                    "fundamentals",
                    f"{cik}/{kind}",
                    "unavailable",
                    {"error": str(exc)[:250]},
                )
                counts["unavailable"] += 1
        if archive.denied:
            break
        if sum(counts.values()) % 100 == 0:
            print(f"Fundamental source files: {dict(counts)}", flush=True)
    export_coverage(cfg, conn)
    archive.conn.close()
    conn.close()
    return {
        **dict(counts),
        "requested_issuers": len(ciks),
        "access_error": archive.denied,
    }


def prepare(
    cfg,
    conn,
    bridge,
    cutoff,
    *,
    legacy_clock=False,
    legacy_floor=False,
    strict_identity=False,
    frames_override=None,
    nominal_tickers=(),
    action_events_override=None,
    blocked_actions=None,
):
    frames = frames_override if frames_override is not None else load_frames(conn)
    import exchange_calendars as xc

    first = conn.execute(
        "SELECT min(filed_at) FROM disclosures WHERE eligible=1"
    ).fetchone()[0]
    first = min(
        first or cutoff,
        min((d for f in frames.values() for d in f.dates), default=cutoff),
    )
    exchange_calendar = xc.get_calendar("XNYS", start=first, end=cutoff)
    calendar = [str(d)[:10] for d in exchange_calendar.sessions_in_range(first, cutoff)]
    closing = {d: exchange_calendar.session_close(d).to_pydatetime() for d in calendar}
    opening = [session_open(d) for d in calendar]
    events = load_events(conn)
    splitmap = load_splits(
        action_events_override if action_events_override is not None else events
    )
    corrections = cfg.reports_dir / "corporate_action_corrections.json"
    extra = (
        json.loads(corrections.read_text(encoding="utf-8"))["actions"]
        if corrections.exists()
        else []
    )
    extra += evidence(conn, "action")
    for action in extra:
        if "verified" in action and not action["verified"]:
            continue
        ticker = action["ticker"]
        pair = (action["ex_date"], action["ratio"])
        if pair not in splitmap.setdefault(ticker, []):
            splitmap[ticker].append(pair)
    identities = defaultdict(set)
    for event in events:
        if event.get("cik") and event.get("ticker"):
            identities[str(int(event["cik"]))].add(event["ticker"])
    security = evidence(conn, "security")
    nominal_imports = defaultdict(dict)
    for p in evidence(conn, "price"):
        nominal_imports[p["ticker"]][p["date"]] = p
    quotes = defaultdict(dict)
    for q in evidence(conn, "quote"):
        at = datetime.fromisoformat(q["timestamp"])
        from zoneinfo import ZoneInfo

        local = at.astimezone(ZoneInfo("America/New_York"))
        # A label alone does not prove that the quote preceded an order.
        day = local.date().isoformat()
        boundary = (
            session_open(day)
            if q["session_point"] == "open" and day in closing
            else closing.get(day)
        )
        if boundary and 0 <= (boundary - at).total_seconds() <= 60:
            quotes[q["ticker"]][(local.date().isoformat(), q["session_point"])] = q
    theses = evidence(conn, "thesis")
    margins = evidence(conn, "margin")
    audit = []
    leads = []
    converted = {}
    seen = set()
    disclosures = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM disclosures ORDER BY available_at,accession"
        )
    ]
    epmap = {acc: ep["id"] for ep in episodes(disclosures) for acc in ep["disclosures"]}
    hitmap = {
        str(r["accession"]).replace("-", ""): dict(r)
        for r in conn.execute("SELECT accession,accept_time FROM edgar_hits")
    }
    for d in sorted(
        disclosures, key=lambda d: (d["cik"], d["available_at"], d["accession"])
    ):
        if not d["eligible"]:
            continue
        problems = []
        warnings = []
        accept = (
            parse_accept_time(hitmap.get(d["accession"], {}).get("accept_time"))
            if legacy_clock
            else parse_accept_time(d["available_at"])
        )
        if accept is not None:
            if accept.tzinfo is None:
                from zoneinfo import ZoneInfo

                accept = accept.replace(tzinfo=ZoneInfo("America/New_York"))
            expected = bisect.bisect_right(opening, accept)
        else:
            expected = bisect.bisect_right(calendar, d["filed_at"])
        if expected >= len(calendar):
            expected = None
        ticker = d.get("ticker")
        if not ticker:
            mapped = identities[d["cik"]]
            ticker = next(iter(mapped)) if len(mapped) == 1 else None
        day = calendar[expected] if expected is not None else None
        dated = [
            s
            for s in security
            if s["verified"]
            and str(int(s["cik"])) == d["cik"]
            and s["valid_from"] <= str(day or "")
            and (not s["valid_to"] or s["valid_to"] >= str(day or ""))
        ]
        if len(dated) == 1:
            ticker = dated[0]["ticker"]
            identity_basis = "verified_dated_security_master"
        elif len(dated) > 1:
            problems.append("ambiguous_security_class")
            identity_basis = "multiple_dated_securities"
        else:
            identity_basis = "provisional_ticker_from_filing_hit_or_legacy_issuer"
            warnings.append("historical_security_class_unverified")
            if strict_identity:
                problems.append("historical_security_class_unverified")
        if not ticker:
            problems.append("historical_ticker_unavailable")
        if day is None:
            problems.append("pending_after_cutoff")
        score = bridge.score(ticker or "", d["cik"], day) if day and ticker else None
        row = {
            **{
                k: d[k]
                for k in (
                    "accession",
                    "cik",
                    "filed_at",
                    "available_at",
                    "clock_basis",
                    "stage",
                    "scheduled",
                    "review_status",
                )
            },
            "id": f"{d['cik']}/{d['accession']}",
            "episode_id": epmap.get(d["accession"]),
            "ticker": ticker,
            "entry_date": day,
            "identity_basis": identity_basis,
            "fundamental": score,
            "framework_routes": routes(score) if score else None,
            "reasons": problems,
            "warnings": warnings,
        }
        if ticker not in frames and ticker not in nominal_imports:
            problems.append("no_price_history")
        series = None
        ix = None
        if ticker in frames:
            if ticker not in converted:
                f = frames[ticker]
                if ticker in nominal_tickers:
                    from .adjust import NominalSeries, SplitPrint

                    # Printed bars must never be scaled because an old proxy
                    # used its filing date as a placeholder effective date.
                    known = splitmap.get(ticker, [])
                    converted[ticker] = NominalSeries(
                        f,
                        [
                            SplitPrint(dt, ra, "raw", None, None)
                            for dt, ra in sorted(set(known))
                        ],
                    )
                else:
                    converted[ticker] = to_nominal(f, splitmap.get(ticker, []))
            series = converted[ticker]
            ix = next((i for i, v in enumerate(series.frame.dates) if v == day), None)
            if ix is None:
                problems.append("missing_first_eligible_session_price")
            elif ix in series.ambiguous:
                problems.append("ambiguous_nominal_price")
        direct = nominal_imports.get(ticker, {})
        if direct and day in direct:
            points = sorted(direct)
            f = PriceFrame(
                points,
                *[
                    [direct[x][k] for x in points]
                    for k in ("open", "high", "low", "close", "volume")
                ],
            )
            ix = points.index(day)
            from .adjust import NominalSeries, SplitPrint

            series = NominalSeries(
                f,
                [
                    SplitPrint(dt, ra, "raw", None, None)
                    for dt, ra in splitmap.get(ticker, [])
                ],
            )
            problems[:] = [
                p
                for p in problems
                if p
                not in {
                    "no_price_history",
                    "missing_first_eligible_session_price",
                    "ambiguous_nominal_price",
                }
            ]
        if series and ix is not None:
            f = series.frame
            price = f.open[ix]
            row["nominal_entry_price"] = price
            row["normalized_actions"] = [vars(s) for s in series.splits]
            if not math.isfinite(price) or price <= 0:
                problems.append("nonpositive_or_nonfinite_nominal_price")
            if legacy_floor and price < 1:
                problems.append("legacy_one_dollar_floor")
            volumes = [
                f.volume[j]
                * math.prod(
                    s.ratio
                    for s in series.splits
                    if s.status in {"raw", "continuous"}
                    and f.dates[j] < s.ex_date <= day
                )
                for j in range(max(0, ix - 20), ix)
            ]
            if len(volumes) < 20 or any(
                not math.isfinite(v) or v <= 0 for v in volumes
            ):
                problems.append("insufficient_prior_liquidity_observations")
            adv = sum(volumes) / len(volumes) if volumes else 0
            row["adv_shares"] = adv
            row["prior_dollar_turnover"] = sum(
                f.close[j] * f.volume[j] for j in range(max(0, ix - 20), ix)
            ) / max(1, len(volumes))
            if ix > 0 and (
                (ix >= 2 and f.low[ix - 1] <= 0.9 * f.close[ix - 2])
                or price <= 0.9 * f.close[ix - 1]
            ):
                row["ssr_proxy_flag"] = True
                warnings.append("SSR_status_and_order_eligibility_need_quotes")
            if d.get("scheduled") and day >= d["scheduled"]:
                problems.append("known_split_already_effective")
            if ix == 0:
                problems.append("no_prior_cost_observation")
            matches = [
                t
                for t in theses
                if t["accession"].replace("-", "") == d["accession"]
                and datetime.fromisoformat(t["available_at"]) <= session_open(day)
            ]
            row["dated_thesis"] = matches[-1] if matches else None
            row["all_gates"] = {
                "fundamental_60": bool(score and eligible_score(score, 60)),
                "historical_quote": bool(quotes[ticker].get((day, "open"))),
                "dated_thesis": bool(matches),
                "dated_security": identity_basis == "verified_dated_security_master",
                "positive_price": math.isfinite(price) and price > 0,
            }
            if not problems:
                dedup = (row["episode_id"], d["stage"])
                if dedup in seen:
                    problems.append("duplicate_episode_stage")
                else:
                    seen.add(dedup)
                    actions = [
                        s
                        for s in series.splits
                        if s.status in {"raw", "continuous"} and s.ex_date > day
                    ]
                    blocked = min(
                        (
                            s.ex_date
                            for s in series.splits
                            if s.status in {"missing", "ambiguous"} and s.ex_date > day
                        ),
                        default=None,
                    )
                    unverified = min(
                        (d for d in (blocked_actions or {}).get(ticker, []) if d > day),
                        default=None,
                    )
                    blocked = min((d for d in (blocked, unverified) if d), default=None)
                    marks = {}
                    for j in range(ix, len(f.dates)):
                        dt = f.dates[j]
                        observation_end = (
                            date.fromisoformat(day) + timedelta(days=180)
                        ).isoformat()
                        if (
                            dt > min(cutoff, observation_end)
                            or blocked
                            and dt >= blocked
                        ):
                            continue
                        vals = [f.open[j], f.high[j], f.low[j], f.close[j]]
                        if (
                            any(not math.isfinite(v) or v <= 0 for v in vals)
                            or f.low[j] > min(f.open[j], f.close[j])
                            or f.high[j] < max(f.open[j], f.close[j])
                        ):
                            continue
                        mark = dict(zip(("open", "high", "low", "close"), vals))
                        mark.update(
                            volume=f.volume[j],
                            factor=math.prod(
                                s.ratio for s in actions if s.ex_date <= dt
                            ),
                        )
                        for point in ("open", "close"):
                            quote = quotes[ticker].get((dt, point))
                            if quote:
                                mark["quote_" + point] = quote
                        marks[dt] = mark
                    if day not in marks:
                        problems.append("invalid_entry_ohlc")
                    else:
                        dated_margin = [
                            m
                            for m in margins
                            if m["ticker"] == ticker
                            and datetime.fromisoformat(m["timestamp"])
                            <= session_open(day)
                        ]
                        lead = {
                            "id": row["id"],
                            "episode_id": row["episode_id"],
                            "ticker": ticker,
                            "cik": d["cik"],
                            "entry_date": day,
                            "rows": marks,
                            "adv": adv,
                            "prior_row": {
                                k: getattr(f, k)[ix - 1]
                                / math.prod(
                                    s.ratio
                                    for s in series.splits
                                    if s.status in {"raw", "continuous"}
                                    and f.dates[ix - 1] < s.ex_date <= day
                                )
                                for k in ("high", "low")
                            },
                            "announced_ex_date": d.get("scheduled"),
                            "announcement_category": d["stage"],
                            "source_url": f"https://www.sec.gov/Archives/edgar/data/{d['cik']}/{d['accession']}/",
                            "fundamental": score,
                            "dated_thesis": row["dated_thesis"],
                            "dated_margin": dated_margin[-1] if dated_margin else None,
                        }
                        leads.append(lead)
        row["status"] = (
            "prepared_conditional"
            if not problems
            else "invalid_evidence"
            if any(
                p in {"known_split_already_effective", "duplicate_episode_stage"}
                for p in problems
            )
            else "evidence_unavailable"
        )
        row["reasons"] = list(dict.fromkeys(problems))
        audit.append(row)
    return leads, audit, calendar


def specification():
    account = dict(
        max_names=5,
        position_fraction=0.05,
        target_notional=5000,
        max_participation=0.01,
        house_margin=1,
        buffer_fraction=0.1,
    )
    conservative = {
        **account,
        "max_names": 3,
        "position_fraction": 0.025,
        "max_participation": 0.001,
        "buffer_fraction": 0.2,
        "stress_adverse_fraction": 2,
        "name_loss_fraction": 0.005,
        "stress_fee_multiple": 3,
        "stress_calendar_days": 7,
    }
    execution = {}
    for name, frac, bps in [
        ("optimistic", 0.125, 10),
        ("base", 0.25, 25),
        ("stress", 0.5, 50),
    ]:
        execution[name] = dict(
            spread_floor=0.01,
            sub_dollar_floor=0.0001,
            range_fraction=frac,
            extra_slippage_bps_per_side=bps,
        )
    execution["legacy"] = dict(
        spread_floor=0.01, range_fraction=0.25, extra_slippage_bps_per_side=25
    )
    execution["economic"] = {**execution["base"], "maximum_cost_fraction": 0.1}
    execution["quotes"] = {
        **execution["base"],
        "quote_required": True,
        "use_quotes": True,
    }
    return {
        "schema_version": "expanded_replay_plan.v2",
        "initial_equity": 50000,
        "account": account,
        "conservative_account": conservative,
        "execution": execution,
        "commission": {
            "minimum_per_side": 1,
            "per_share_per_side": 0.005,
            "maximum_trade_fraction": 0.01,
        },
        "borrow_collateral": {"day_basis": 360},
        "borrow_max_age_hours": 4,
        "quote_max_age_seconds": 60,
        "rule_basis": "Costs and risk budgets are predeclared exploratory assumptions, not historical broker quotes. Sub-dollar tick minimum is a scenario floor, not a measured spread. Commission cap follows current IBKR Pro Fixed schedule as a sensitivity, not a certified historical schedule.",
        "economic_cost_budget_fraction": 0.1,
        "public_clock": "next day after filing unless an audited release timestamp is supplied",
        "eligible_price": "positive finite nominal price; no $1 floor",
        "fundamental_floor": 60,
        "minimum_numeric_observations": 3,
    }


def borrow_imports(conn):
    result = defaultdict(list)
    for b in evidence(conn, "borrow"):
        result[b["ticker"]].append(
            (
                b["timestamp"],
                b["shares"],
                b["fee_annual_fraction"],
                {"approved": b["approved"], "reference": b["locate_reference"]},
            )
        )
    return result


def run_expanded(cfg, *, cutoff=None):
    from .universe_study import run

    return run(cfg, cutoff=cutoff)
