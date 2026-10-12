"""Explain economics, tail risk, data defects and predeclared execution stresses."""
from __future__ import annotations

import json
import hashlib
import platform
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from statistics import mean, median
from zoneinfo import ZoneInfo

import numpy as np

from .book import Settings
from .config import PACKAGE_DIR
from .fundamentals import FundamentalBridge, relative_path
from .realism import Realism, prepare, scenario_specs, simulate_daily, verified_announcements


def _groups(rows, key):
    buckets = defaultdict(list)
    for row in rows:
        buckets[key(row)].append(row)
    return [{"group": group, "n": len(bucket), "pnl": sum(r["net_pnl"] for r in bucket),
             "mean_return": mean(r["net_return"] for r in bucket),
             "median_return": median(r["net_return"] for r in bucket),
             "hit_rate": mean(r["net_pnl"] > 0 for r in bucket)} for group, bucket in sorted(buckets.items())]


def cluster_interval(rows, field="net_return", cluster="ticker"):
    """Resample whole issuers, not independent trades; conditional on observed sample."""
    buckets = defaultdict(list)
    for row in rows:
        if row.get(field) is not None:
            buckets[row[cluster]].append(row[field])
    keys = sorted(buckets)
    if len(keys) < 5:
        return {"clusters": len(keys), "low": None, "high": None, "method": "too few issuer clusters"}
    sums = np.array([sum(buckets[k]) for k in keys])
    counts = np.array([len(buckets[k]) for k in keys])
    rng = np.random.default_rng(20261009)
    samples = rng.integers(0, len(keys), size=(2000, len(keys)))
    draws = sums[samples].sum(axis=1) / counts[samples].sum(axis=1)
    return {"clusters": len(keys), "low": float(np.quantile(draws, .025)),
            "high": float(np.quantile(draws, .975)), "draws": 2000,
            "method": "95% percentile interval; whole-issuer bootstrap; observed trades only, not future book returns"}


def diagnostics(book):
    rows = book["trades"]
    pnls = [r["net_pnl"] for r in rows]
    rets = [r["net_return"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    worst = sorted(rows, key=lambda r: r["net_pnl"])[:5]
    gross = sum(r.get("gross_pnl", r["net_pnl"]) for r in rows)
    borrow = sum(r.get("fee_pnl", 0) for r in rows)
    commission = sum(r.get("commission", 0) for r in rows)
    raw_gross = sum(r.get("raw_price_pnl", r.get("gross_pnl", r["net_pnl"])) for r in rows)
    annual = book["assumptions"].get("fee_annual") or 0
    fee_unit = borrow / annual if annual else None
    groups = {
        "year": _groups(rows, lambda r: r["entry_date"][:4]),
        "cohort": _groups(rows, lambda r: r["cohort"] or "unknown"),
        "price": _groups(rows, lambda r: "$1–2.50" if r["entry_fill"] < 2.5 else "$2.50–5" if r["entry_fill"] < 5 else "$5+"),
        "date_quality": _groups(rows, lambda r: r.get("date_quality") or "unknown"),
        "exit_liquidity": _groups(rows, lambda r: "capacity breach" if r.get("exit_breach") else "within daily cap"),
        "sample_period": _groups(rows, lambda r: "2021–2023" if r["entry_date"] < "2024-01-01" else "2024 onward"),
        "entry_fundamental": _groups(rows, lambda r: "unscored / limited vintage" if not r.get("fundamental", {}).get("historical_eligible")
                                     else "below 40" if r["fundamental"]["score"] < 40 else "40–59" if r["fundamental"]["score"] < 60 else "60+"),
    }
    peer_interval = cluster_interval(rows, "excess_vs_peer")
    control_rows = [{**r, "control_excess": r["net_return"] - r["control_return"]}
                    for r in rows if r.get("control_return") is not None]
    return {
        "waterfall": {"raw_price_pnl": raw_gross, "spread_and_slippage": raw_gross - gross,
                      "gross_after_fills": gross, "borrow": borrow, "commission": commission, "net": sum(pnls)},
        "profit_factor": sum(wins) / -sum(losses) if losses else None,
        "average_win": mean(wins) if wins else None, "average_loss": mean(losses) if losses else None,
        "payoff_ratio": mean(wins) / -mean(losses) if wins and losses else None,
        "breakeven_hit_rate": -mean(losses) / (mean(wins) - mean(losses)) if wins and losses else None,
        "mean_trade_pnl": mean(pnls) if pnls else None,
        "weighted_return": sum(pnls) / sum(r["notional"] for r in rows) if rows else None,
        "quantiles": {str(q): float(np.quantile(rets, q)) if rets else None for q in (.01, .05, .10, .25, .5, .75, .90, .95, .99)},
        "tail_mean_5pct": mean(sorted(rets)[:max(1, int(np.ceil(len(rets) * .05)))]) if rets else None,
        "losses_over_50pct": sum(r < -.5 for r in rets), "losses_over_100pct": sum(r < -1 for r in rets),
        "worst_five": [{k: r.get(k) for k in ("ticker", "entry_date", "event_id", "net_pnl", "net_return", "mae", "audit_flags")} for r in worst],
        "worst_five_pnl": sum(r["net_pnl"] for r in worst),
        "without_worst_five_pnl": sum(pnls) - sum(r["net_pnl"] for r in worst),
        "tail_note": "Removing known losers is an attribution illustration, not a tradable filter.",
        "zero_borrow_pnl_same_trades": gross - commission,
        "breakeven_fee_annual_same_trades": (gross - commission) / fee_unit if fee_unit else None,
        "fee_note": "Fixed executed trades and quantities; a different fee can change margin and admissions.",
        "mean_return_interval": cluster_interval(rows), "peer_interval": peer_interval,
        "control_interval": cluster_interval(control_rows, "control_excess"),
        "peer_match_coverage": mean(r.get("peer_return") is not None for r in rows) if rows else 0,
        "control_match_coverage": len(control_rows) / len(rows) if rows else 0,
        "groups": groups,
        "max_margin_required": max((r.get("margin_required", 0) for r in book["equity"]), default=0),
        "margin_breach_days": sum(r.get("margin_breach", False) for r in book["equity"]),
        "comparison_note": "Peer/control differences are conditional descriptive comparisons. Present-day universe, repeated peers, missing paths and unmatched squeeze losers prevent causal alpha claims.",
        "cost_sensitivity": [{"spread_multiple": multiple, "fee_annual": fee,
                              "pnl_same_trades": raw_gross - (raw_gross - gross) * multiple
                                - (borrow * fee / annual if annual else 0) - commission}
                             for multiple in (0, .25, .5, 1, 2) for fee in (0, .20, 1, 3)] if annual else [],
        "cost_sensitivity_note": "Attribution with fixed trades and quantities; no shared-capital replay. Multipliers scale the assumed spread/slippage cost, not measured bid-ask spreads. This is not a tradable performance estimate.",
    }


def enrich_trade(row, candidate, event, bridge):
    info = candidate.extra
    shares, factor = candidate.shares, candidate.share_factor
    row.update(gross_pnl=candidate.gross_pnl, fee_pnl=candidate.fee_pnl,
               commission=info.get("commission", 0),
               raw_price_pnl=shares * (info["entry_price"] - factor * info["exit_price"]),
               exit_reason=info.get("exit_reason", "scheduled"),
               adv_shares=candidate.adv_shares, participation=shares / candidate.adv_shares,
               entry_margin=info.get("entry_margin"), source_url=info.get("source_url"),
               cik=info.get("cik"), announced_ex_date=info.get("announced_ex_date"),
               ex_date=info.get("ex_date"), announce_date=info.get("announce_date"))
    path = [p for day, p in info["path"].items() if day <= candidate.exit_date]
    row["mae"] = max((p["high"] * p["factor"] / candidate.entry_fill - 1 for p in path), default=None)
    row["mfe"] = max((1 - p["low"] * p["factor"] / candidate.entry_fill for p in path), default=None)
    flags = []
    if event:
        if event.get("announce_date") and event.get("ex_date") and event["announce_date"] > event["ex_date"]:
            flags.append("filing_after_effective_date")
        if event.get("announced_ex_date") and event.get("ex_date") and event["announced_ex_date"] != event["ex_date"]:
            flags.append("parsed_schedule_disagrees_with_event")
        if event.get("announce_date") and event.get("ex_date"):
            gap = (date.fromisoformat(event["ex_date"][:10]) - date.fromisoformat(event["announce_date"][:10])).days
            if gap > 60:
                flags.append("filing_over_60_days_before_split")
        if not event.get("announced_ratio"):
            flags.append("no_ratio_in_selected_filing")
    if candidate.exit_breach:
        flags.append("exit_capacity_breach")
    row["audit_flags"] = flags
    score = bridge.score(candidate.ticker, info.get("cik"), candidate.entry_date)
    row["fundamental"] = {k: score[k] for k in ("score", "evidence_count", "source", "historical_eligible", "latest_period", "lenses")}
    return row


def extend_snapshot(cfg, snapshot, events, frames, borrows, candidates_by_book, hits):
    from .run_book import _book_dict
    from .research_lens import playbook
    bridge = FundamentalBridge(cfg)
    event_map = {e["id"]: e for e in events}
    for book in snapshot["books"]:
        candidates = candidates_by_book[book["id"]]
        for row, candidate in zip(book["trades"], candidates):
            enrich_trade(row, candidate, event_map.get(candidate.event_id), bridge)
        book["analysis"] = diagnostics(book)

    verified, evidence_funnel = verified_announcements(events, hits)
    scenarios, all_prepared = [], []
    for label, title, model, fee, participation, borrow_policy in scenario_specs():
        settings = Settings(signal="announce", horizon=5, min_price=1, force_cover=True,
                            target_notional=5000, max_book=50000, max_names=5,
                            max_participation=participation, fee_annual=fee, borrow_policy=borrow_policy)
        prepared, funnel = prepare(verified, frames, settings, split_events=events, exclude_ssr=model.exclude_ssr)
        if label == "verified_daily_100":
            all_prepared = prepared
        taken, skipped, equity = simulate_daily(prepared, settings, model, borrows)
        book = _book_dict(label, settings, taken, skipped, equity, funnel)
        book["label"] = title
        book["assumptions"]["realism"] = asdict(model)
        book["assumptions"]["horizon_definition"] = "five sessions including entry, exit at fifth close or earlier scheduled cover"
        book["assumptions"]["universe"] = "parsed substantive announcement with ratio; no later-completion filter"
        for row, c in zip(book["trades"], taken):
            enrich_trade(row, c, None, bridge)
        book["analysis"] = diagnostics(book)
        scenarios.append(book)

    # A predeclared hypothesis; raw vintage coverage is mandatory. It is exploratory,
    # never promoted because its in-sample result beats the unscreened scenario.
    screened = [c for c in all_prepared if (s := bridge.score(c.ticker, c.extra.get("cik"), c.entry_date))["historical_eligible"] and s["score"] >= 60]
    settings = Settings(horizon=5, max_names=5, max_participation=.01)
    taken, skipped, equity = simulate_daily(screened, settings, Realism(), borrows)
    screen_book = _book_dict("fundamental_60", settings, taken, skipped, equity,
                            {"evidence_pool": len(all_prepared), "raw_asof_score_at_least_60": len(screened)})
    screen_book["label"] = "Exploratory · fundamental score ≥60"
    screen_book["assumptions"]["realism"] = asdict(Realism())
    screen_book["assumptions"]["universe"] = "same verified pool; raw pre-entry fundamentals only"
    for row, c in zip(screen_book["trades"], taken):
        enrich_trade(row, c, None, bridge)
    screen_book["analysis"] = diagnostics(screen_book)
    scenarios.append(screen_book)

    main_book = next((b for b in snapshot["books"] if b["id"] == "assumed_100_h5_effective"), snapshot["books"][0])
    sources = list(candidates_by_book.get(main_book["id"], [])) + all_prepared
    review_names = {}
    review_dates = defaultdict(set)
    for c in sources:
        review_dates[c.ticker].add(c.entry_date)
        prior = review_names.get(c.ticker)
        if prior is None or c.entry_date > prior.entry_date:
            review_names[c.ticker] = c
    current_day = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    bridge_manifest = bridge.manifest()
    candidates = []
    for ticker, c in review_names.items():
        now = bridge.score(ticker, c.extra.get("cik"), current_day)
        historical = bridge.score(ticker, c.extra.get("cik"), c.entry_date)
        candidates.append({"ticker": ticker, "name": c.name, "last_event_entry": c.entry_date,
                           "historical": historical, "current": now,
                           "entry_history": [bridge.score(ticker, c.extra.get("cik"), day) for day in sorted(review_dates[ticker])],
                           "current_context": bridge.current_context(ticker),
                           "links": {"ssi": bridge_manifest["short_alpha"],
                                     "issuer": f"https://www.sec.gov/edgar/browse/?CIK={c.extra.get('cik') or ''}&owner=exclude"},
                           "next_step": "Reconcile filing and corporate-action identity, write the impairment mechanism, valuation, dated catalyst and a falsifier; verify borrow and squeeze budget before conviction."})
    candidates.sort(key=lambda r: (r["current"]["score"] is None, -(r["current"]["score"] or 0), r["ticker"]))
    audit_counts = Counter(flag for r in main_book["trades"] for flag in r.get("audit_flags", []))
    snapshot["realism"] = {"books": scenarios, "evidence_funnel": evidence_funnel,
        "notes": [
            "These are daily-bar scenarios, not a verified live strategy or historical broker reconstruction.",
            "The original completed-split book remains unchanged; its outcome selection is hindsight and its 5-session setting spans six observed bars.",
            f"Verified inputs use parsed substantive filings with a ratio, including announcements that never completed. Only {sum(bool(h.get('text_parsed')) for h in hits):,} of {len(hits):,} filing hits were parsed; discovery and verification coverage remain incomplete.",
            "One shared $50k equity account. Entries precede same-day scheduled closes. Prior unrealized losses, accrued fees, and required margin reduce buying power.",
            "Position cap 5% of current equity, five names, 1% of prior 20-session ADV; house margin 100% plus FINRA minimum and 10% capital buffer.",
            "Borrow fee scenario accrues calendar days on 102% of the last observed price rounded up to $1, using a 360-day basis. This approximates collateral billing and does not reconstruct settlement or daily broker quotes.",
            "Whole shares, prior-range spread, 25bp additional slippage each side, $0.005/share commission with $1 minimum per side. These are assumptions, not measured auction fills.",
            "SSR proxy excludes prior-day 10% low breaches and opening 10% gaps. Daily bars cannot reconstruct the national best bid, exemptions or actual restriction list.",
            "Stops and margin deficits schedule cover at the next observed open, retaining overnight gap risk. Intraday margin liquidation can be worse.",
            "Only a schedule present in the announcement causes advance cover. Other observed splits change shares on their ex-date; fractional obligations, recalls, cash in lieu, dividends and buy-ins remain unresolved.",
            "Missing bars, halts, delisted securities, historical ticker reuse and current listing classifications remain research limitations. Rejected/missing paths are not zero returns.",
            "All scenario settings were declared for sensitivity analysis. Score ≥60 is an exploratory research hypothesis; no held-out validation or optimized threshold claim.",
        ]}
    snapshot["audit"] = {"headline_trade_flags": dict(audit_counts),
        "flagged_trades": sum(bool(r.get("audit_flags")) for r in main_book["trades"]),
        "total_trades": len(main_book["trades"]),
        "historical_locates": sum(len(rows) for rows in borrows.values()),
        "priorities": [
            {"issue": "Event and filing association", "impact": "The selected filing may describe an earlier split, a historical mention, or arrive after the effective date.", "action": "Reconcile accession, exact clause, announced date and ratio for every event; expand filing/exhibit coverage before a production signal."},
            {"issue": "Completion and survivorship bias", "impact": "A completed-split filter at announcement uses future outcomes. Present-day ticker/exchange maps omit dead names.", "action": "Freeze all verified announcements at publication, add contemporaneous security master and delisting outcomes."},
            {"issue": "Borrow and forced exits", "impact": "No historical locate snapshots. Flat fees omit re-rates, recalls, buy-ins and liquidity freezes.", "action": "Import timestamped pre-order availability and fee, daily borrow rates, recall/buy-in notices and auction quotes."},
            {"issue": "Squeeze loss dominates typical trade", "impact": "Median returns do not measure account survival; quote gaps and margin demands matter.", "action": "Budget adverse dollar loss per issuer, apply size/margin stress and evaluate walk-forward portfolios."},
        ]}
    snapshot["research"] = {"bridge": bridge_manifest, "playbook": playbook(), "as_of": current_day, "candidates": candidates,
        "coverage": {"candidates": len(candidates),
                     "current_scored": sum(r["current"]["score"] is not None for r in candidates),
                     "historical_raw_scored": sum(r["historical"]["historical_eligible"] for r in candidates),
                     "historical_fallback_scored": sum(r["historical"]["score"] is not None and not r["historical"]["historical_eligible"] for r in candidates)},
        "review_contract": {"required": ["identity", "mechanism", "valuation", "dated_catalyst", "falsifier", "borrow", "squeeze_budget", "source_locator", "review_status"],
                            "fraud_rule": "Conclusion only after regulator, court, admitted misconduct/restatement or evidence-backed analyst determination; publisher reports are leads."}}
    from .strategy import build_strategy
    snapshot["strategy"] = build_strategy(snapshot, verified, bridge)
    source_files = sorted(PACKAGE_DIR.glob("*.py")) + [cfg.config_path]
    cache_files = sorted(bridge.cache.glob("CIK*.json")) if bridge.cache.exists() else []
    snapshot["provenance"] = {"python": platform.python_version(), "numpy": np.__version__,
        "source_files": [{"path": relative_path(p, cfg.repo_root), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_files if p.exists()],
        "ssi_sources": bridge_manifest["links"],
        "sec_cache_files": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in cache_files],
        "events_sha256": hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest(),
        "filing_hits_sha256": hashlib.sha256(json.dumps(hits, sort_keys=True, default=str).encode()).hexdigest(),
        "price_rows_sha256": hashlib.sha256(json.dumps({ticker: vars(frame) for ticker, frame in sorted(frames.items())}, sort_keys=True).encode()).hexdigest(),
        "note": "Preserve SQLite input tables and SEC caches for reproduction. Book output tables change on export. Price hashes cover loaded OHLCV; missing fields substituted by the legacy loader remain a data-quality limit."}
    return snapshot


def write_analysis_report(cfg, snapshot):
    from .research_lens import empty_lens_reviews
    book = next((b for b in snapshot["books"] if b["id"] == "assumed_100_h5_effective"), snapshot["books"][0])
    a, s = book["analysis"], book["stats"]
    lines = ["# Reverse split research audit", "", f"Built {snapshot['built_at']}. All results below use cached data.", "",
        f"Original comparator: **${s['dollar_pnl']:,.0f}** on **{s['taken']} trades**, median **{s['median_return']:.1%}**. This is a completed-split, assumed-borrow scenario, not a deployable strategy.", "",
        f"Worst five trades total **${a['worst_five_pnl']:,.0f}**. Excluding them leaves ${a['without_worst_five_pnl']:,.0f}; this is an attribution illustration and cannot be used as a trading filter.", "",
        f"Profit factor {a['profit_factor'] or 0:.2f}; average win ${a['average_win'] or 0:,.0f}; average loss ${a['average_loss'] or 0:,.0f}. Required hit rate at that observed payoff is {a['breakeven_hit_rate'] or 0:.1%}.", "",
        "## Economics of the executed comparator", "", "| Component | Dollars |", "|---|---:|"]
    lines += [f"| {key} | ${value:,.0f} |" for key, value in a["waterfall"].items()]
    lines += ["", "Spread stress uses a fraction of the previous day's high-low range, not a measured bid-ask quote. It can become very large after a squeeze. The fee/spread sensitivity table in the dashboard is fixed-trade attribution; real admissions, fills and liquidation costs require replay or auction quotes."]
    ci = a["mean_return_interval"]
    if ci["low"] is not None:
        lines += ["", f"Mean trade return {s['mean_return']:.1%}; conditional whole-issuer bootstrap interval {ci['low']:.1%} to {ci['high']:.1%} ({ci['clusters']} issuers). This interval does not remove discovery bias or forecast account returns."]
    lines += ["", "## Event and execution audit", "", "| Observed flag | Trades |", "|---|---:|"]
    lines += [f"| {key} | {value} |" for key, value in snapshot["audit"]["headline_trade_flags"].items()]
    lines += ["", "## Predeclared daily-bar scenarios", "", "These change the verified universe and execution assumptions together; their difference from the original is not an isolated causal attribution.", "", "| Scenario | Trades | P&L | Drawdown |", "|---|---:|---:|---:|"]
    lines += [f"| {b['label']} | {b['stats']['taken']} | ${b['stats']['dollar_pnl']:,.0f} | {b['stats']['max_drawdown']:.1%} |" for b in snapshot["realism"]["books"]]
    lines += ["", "## Year stability of original trades", "", "| Entry year | Trades | P&L | Mean |", "|---|---:|---:|---:|"]
    lines += [f"| {r['group']} | {r['n']} | ${r['pnl']:,.0f} | {r['mean_return']:.1%} |" for r in a["groups"]["year"]]
    lines += ["", "## Fundamental bridge", "", snapshot["research"]["bridge"]["method"], "",
              f"Coverage: {snapshot['research']['coverage']}. Missing data stay unscored. Current context is kept separate from entry-time evidence.", ""]
    lines += [f"- [{r['label']}]({r['url']})" for r in snapshot["research"]["bridge"]["links"]]
    lines += ["", "## What conviction must establish", "", "A high decay score opens a research file. It does not establish fraud, valuation downside, catalyst timing or borrow. Record the impairment mechanism, bear/base/bull equity payoff, dated catalyst, explicit falsifier, source locator, borrow cost, adverse-loss budget and analyst review. Reverse splits alone earn no fundamental points.", "",
              "## Limits and next experiments", ""]
    lines += [f"- {note}" for note in snapshot["realism"]["notes"]]
    lines += ["", "Freeze thresholds before future data arrive. Evaluate all verified leads and unscored names in a dated paper ledger; use issuer-separated chronological walk-forward tests with an embargo at least as long as the maximum hold, realistic capital competition, and a contemporaneous matched control universe. Compare fundamentals-only, split-only and combined screens without selecting the best in-sample horizon.", "",
              "Sources: [FINRA short margin](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210), [SEC Rule 201](https://www.sec.gov/files/rules/final/2010/34-61595-secg.htm), [IBKR collateral convention](https://www.interactivebrokers.com/campus/glossary-terms/collateral-short-sale/), [SEC companyfacts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).", ""]
    report = cfg.reports_dir / "analysis_audit.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    # User-reviewable handoff; no write into SSI's live candidate ledger.
    handoff = {"schema_version": "1.1", "as_of": snapshot["research"]["as_of"], "usage": "research review queue, not positions",
        "playbook": snapshot["research"]["playbook"],
        "candidates": [{"ticker": r["ticker"], "stage": "lead", "origin": "browser_draft", "source_system": "reverse_split_research",
                        "frameworks": r["current"]["lenses"], "hypothesis": "", "sources": [],
                        "catalysts": [], "falsifiers": [], "research": {"status": "requires_analyst_review"},
                        "lens_reviews": empty_lens_reviews(),
                        "decision": {"state": "unrecorded", "known_at": None, "original_hypothesis": "", "trade_or_pass_reason": ""},
                        "fundamental_score": r["current"]["score"], "score_as_of": r["current"]["as_of"],
                        "gates": {"borrow_and_carry": "pending", "path_and_timing": "unscored", "fraud_bad_actors": "unscored"}}
                       for r in snapshot["research"]["candidates"]]}
    (cfg.reports_dir / "short_alpha_review_queue.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    return str(report)
