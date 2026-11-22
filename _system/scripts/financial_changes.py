"""Comparable fiscal changes used by both the stock list and company overview."""

from __future__ import annotations

import calendar
import json
import math
from bisect import bisect_right
from datetime import date
from itertools import pairwise
from pathlib import Path
from statistics import median

from build_stock_research_explorer import metric_ttm
from stock_research_share_basis import SHARE_IDS, align_series
from stock_valuation_aliases import research_aliases

PROFILES = {
    "operating": ["revenue", "operating_margin", "fcf_per_share", "fcf_yield"],
    "bank": ["net_interest_income", "deposits", "credit_provision", "roe", "ptbv"],
    "property": ["core_ffo_per_share", "occupancy", "same_store_noi_growth", "revenue", "long_term_debt"],
    "fund": ["total_return", "relative_return", "drawdown", "expense_ratio"],
    "insurance": ["net_income", "book_value_per_share", "roe", "pb"],
    "holding": ["equity", "book_value_per_share", "cash", "pb"],
    "infrastructure": ["revenue", "operating_margin", "capex", "fcf_yield"],
    "development": ["cash", "ocf", "diluted_shares"],
    "cyclical": ["revenue", "operating_margin", "free_cash_flow", "net_debt"],
    "preferred": ["liquidation_preference", "dividend_rate", "claim_price"],
    "debenture": ["coupon_rate", "claim_price"],
    "claim": ["claim_payout", "claim_price"],
}
LABELS = {
    "revenue": "Revenue",
    "operating_margin": "Operating margin",
    "fcf_per_share": "Free cash flow / diluted share",
    "fcf_yield": "FCF yield",
    "net_interest_income": "Net interest income",
    "deposits": "Deposits",
    "credit_provision": "Credit loss provision",
    "roe": "Return on equity",
    "ptbv": "Price / tangible book",
    "core_ffo_per_share": "Core FFO / diluted share",
    "occupancy": "Period-end occupancy",
    "same_store_noi_growth": "Cash same-store NOI growth",
    "debt": "Debt",
    "total_return": "Total return",
    "relative_return": "Return minus benchmark",
    "drawdown": "Maximum drawdown",
    "expense_ratio": "Gross expense ratio",
    "net_income": "Net income",
    "book_value_per_share": "Book value / share",
    "pb": "Price / book",
    "equity": "Common equity",
    "cash": "Cash",
    "capex": "Capital expenditure",
    "ocf": "Operating cash flow",
    "diluted_shares": "Diluted shares",
    "free_cash_flow": "Free cash flow",
    "net_debt": "Net debt",
    "long_term_debt": "Long-term debt",
    "liquidation_preference": "Liquidation preference / share",
    "dividend_rate": "Stated dividend rate",
    "coupon_rate": "Annual coupon rate",
    "claim_payout": "Maximum contingent payout / claim",
    "claim_price": "Security price",
}
MARKET = {"fcf_yield", "ptbv", "pb", "claim_price"}
FUND_MARKET = {"total_return", "relative_return", "drawdown"}
DAY = date.fromisoformat


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def profile_for(doc, listing):
    ticker = doc["ticker"]
    instrument = str(doc.get("instrument_type") or listing.get("instrument_type") or "").lower()
    preferred = "(preferred)" in listing.get("company", "").lower()
    if preferred or doc.get("instrument_method") == "preferred":
        return "preferred"
    if ticker.endswith(".DB"):
        return "debenture"
    if ticker.endswith((".CVR", ".PS1", ".PS2", ".PS3")) or doc.get("instrument_method") == "payoff":
        return "claim"
    if instrument in {"etf", "mutualfund", "closed_end_fund", "fund"}:
        return "fund"
    return doc.get("profile") if doc.get("profile") in PROFILES else "operating"


def fiscal_gap(a, b):
    return (DAY(a) - DAY(b)).days


def point_sources(point):
    refs = [point.get("source"), *(point.get("source_refs") or []), point.get("price_source")]
    return sorted(
        {
            url
            for ref in refs
            if ref
            for url in [ref if isinstance(ref, str) else ref.get("url") or ref.get("ref") or ""]
            if url.startswith("https://")
        }
    )


def observation(points, as_of, unit, sources, *, max_age, share=False, valuation=False):
    usable = [
        p
        for p in points
        if p.get("period", "") <= as_of
        and isinstance(p.get("value"), (float, int))
        and all(
            (r.get("filed") or "")[:10] <= as_of
            for r in [p.get("source"), *(p.get("source_refs") or [])]
            if isinstance(r, dict)
        )
        and math.isfinite(p["value"])
        and point_sources(p)
        and not (share and p.get("share_basis_status") == "unverified")
    ]
    if not usable:
        return {"status": "missing"}
    usable.sort(key=lambda p: p["period"])
    latest = usable[-1]
    end = latest["period"]
    year_ago = [
        p
        for p in usable
        if 350 <= fiscal_gap(end, p["period"]) <= 380
        and (
            not latest.get("start")
            or not p.get("start")
            or abs(fiscal_gap(end, latest["start"]) - fiscal_gap(p["period"], p["start"])) <= 15
        )
    ]
    prior = min(year_ago, key=lambda p: abs(fiscal_gap(end, p["period"]) - 365), default=None)

    def links(p):
        ids = []
        for url in point_sources(p):
            if url not in sources:
                sources.append(url)
            ids.append(sources.index(url))
        return ids

    item = {
        "period": end,
        "value": latest["value"],
        "unit": unit,
        "sources": links(latest),
        "status": "stale" if fiscal_gap(as_of, end) > max_age else "ok",
        "trend": [[p["period"], p["value"]] for p in usable[-8:]],
    }
    if prior:
        item.update(prior=prior["value"], prior_period=prior["period"], prior_sources=links(prior))
    if valuation:
        history = {p["period"][:7]: p["value"] for p in usable if fiscal_gap(end, p["period"]) <= 1826}
        if len(history) >= 12:
            vals = list(history.values())
            item["range"] = [min(vals), median(vals), max(vals), len(vals)]
    return item


def fund_series(record, benchmark, as_of):
    """Completed calendar quarters, same-session benchmarks, reinvested distributions."""
    result = {mode: {} for mode in ("quarter", "ttm")}
    if not record.get("points") or not record.get("source_url"):
        return result
    comparable = (
        bool(benchmark.get("ticker"))
        and record.get("benchmark_ref") == benchmark["ticker"]
        and record.get("currency") == benchmark.get("currency")
        and record.get("ticker") != benchmark["ticker"]
    )
    bench = {p[0]: p[2] for p in benchmark.get("points", []) if p[0] <= as_of} if comparable else {}
    points = [
        (DAY(d), v) for d, _, v in record["points"] if d <= as_of and isinstance(v, (float, int)) and v > 0
    ]
    if not points:
        return result
    dates = [p[0] for p in points]
    ends = []
    for year in range(dates[-1].year - 4, dates[-1].year + 1):
        for month in (3, 6, 9, 12):
            end = date(year, month, calendar.monthrange(year, month)[1])
            ix = bisect_right(dates, end) - 1
            ends.append(ix if end <= DAY(as_of) and ix >= 0 and (end - dates[ix]).days <= 6 else None)
    for mode, lag in (("quarter", 1), ("ttm", 4)):
        values = {k: [] for k in FUND_MARKET}
        for j in range(lag, len(ends)):
            start, end = ends[j - lag], ends[j]
            if start is None or end is None or end <= start:
                continue
            window = points[start : end + 1]
            if any((b[0] - a[0]).days > 10 for a, b in pairwise(window)):
                continue
            first, last = window[0][1], window[-1][1]
            change = (last / first - 1) * 100
            peak = first
            drawdown = 0
            for _, v in window:
                peak = max(peak, v)
                drawdown = min(drawdown, (v / peak - 1) * 100)
            source = {"url": record["source_url"]}
            p = {"period": dates[end].isoformat(), "source": source}
            values["total_return"].append({**p, "value": change})
            values["drawdown"].append({**p, "value": drawdown})
            a, b = bench.get(dates[start].isoformat()), bench.get(p["period"])
            if a and b and a > 0 and b > 0 and benchmark.get("source_url"):
                values["relative_return"].append(
                    {
                        **p,
                        "value": change - (b / a - 1) * 100,
                        "source_refs": [{"url": benchmark["source_url"]}],
                    }
                )
        result[mode] = values
    return result


class ComparisonIndex:
    def __init__(self, root: Path, as_of):
        self.as_of = as_of
        self.registry = read(root / "_system/portfolio/registry.json").get("holdings", {})
        self.aliases = research_aliases(root)
        self.sic = read(root / "_system/reference/market-data/fundamentals/_sic_map.json")
        self.config = read(Path(__file__).with_name("financial_change_sources.json"))
        self.reference_benchmark = read(root / "_system/reference/stock-research/SPY_total_return.json")
        self.root = root
        self.issuers = {}
        self.rows = {}

    def add(self, doc, performance=None, benchmark=None):
        ticker = doc["ticker"]
        listing = self.registry.get(ticker, {})
        profile = profile_for(doc, listing)
        if profile == "fund":
            performance = performance or doc.get("comparison_performance") or {}
            benchmark = benchmark or self.reference_benchmark
            if ticker == "SPY" and not performance:
                performance = self.reference_benchmark
        cik = (doc.get("identity") or {}).get("cik") or self.sic.get(ticker, {}).get("cik")
        self.issuers[ticker] = str(cik).lstrip("0") if cik else ticker
        sources = []
        metrics = {s["id"]: s for s in doc.get("series", [])}
        supplemental = self.config.get("facts", {}).get(ticker, {})
        terms = (
            read(self.root / ticker / "research/cvr_terms.json")
            if ticker.endswith(".CVR") and ticker in self.registry
            else {}
        )
        quote = doc.get("quote") or {}
        gate = self.config.get("identity_checks", {}).get(ticker)
        blocked = (
            gate and gate["issuer"].lower() not in (listing.get("company") or doc.get("company", "")).lower()
        )
        market = fund_series(performance or {}, benchmark or {}, self.as_of) if profile == "fund" else {}
        row = {"profile": profile, "sources": sources, "quarter": {}, "ttm": {}}
        if profile == "fund":
            row["benchmark"] = (performance or {}).get("benchmark_ref")
            row["distribution_status"] = (performance or {}).get("status")
        for key in PROFILES[profile]:
            s = align_series(doc, metrics[key]) if key in metrics else {}
            extra = supplemental.get(key, {})
            for mode in ("quarter", "ttm"):
                points = s.get("quarterly", []) if mode == "quarter" else metric_ttm(doc, key)
                unit = s.get("unit")
                if mode == "ttm" and key == "fcf_per_share":
                    shares = metric_ttm(doc, "diluted_shares")
                    verified = {p["period"] for p in shares if p.get("share_basis_status") == "aligned"}
                    points = [p for p in points if p["period"] in verified]
                if key in MARKET:
                    points = s.get("monthly", [])
                if key in FUND_MARKET:
                    points = market.get(mode, {}).get(key, [])
                    unit = "percent"
                if extra and (extra.get("basis") == "instant" or mode == "quarter"):
                    supplement = [
                        {"period": d, "value": v, "source": {"url": u}}
                        for d, v, u, available in extra["points"]
                        if available <= self.as_of
                    ]
                    points = sorted(
                        {p["period"]: p for p in [*supplement, *points]}.values(),
                        key=lambda p: p["period"],
                    )
                    unit = extra["unit"]
                if key == "claim_payout" and terms.get("cvr_id") == ticker and terms.get("as_of"):
                    points = [
                        {
                            "period": terms["as_of"],
                            "value": terms.get("max_payout_usd"),
                            "source_refs": terms.get("sec_links") or [],
                        }
                    ]
                    unit = "USD/claim"
                if key == "claim_price" and quote.get("symbol") == ticker and quote.get("as_of"):
                    points = [
                        {
                            "period": quote["as_of"],
                            "value": quote.get("value"),
                            "source": quote.get("source_url"),
                        }
                    ]
                    unit = quote.get("currency")
                annual_only = mode == "ttm" and not s.get("quarterly") and bool(s.get("annual"))
                cadence = "monthly" if key in MARKET else "annual" if annual_only else "quarterly"
                age = (
                    45
                    if key in MARKET
                    else 550
                    if annual_only
                    or key
                    in {
                        "expense_ratio",
                        "claim_payout",
                        "coupon_rate",
                        "liquidation_preference",
                        "dividend_rate",
                    }
                    else 200
                )
                if key in SHARE_IDS and not (doc.get("share_basis") or {}).get("eligible"):
                    points = []
                cell = observation(
                    points,
                    self.as_of,
                    unit,
                    sources,
                    max_age=age,
                    share=key in SHARE_IDS,
                    valuation=key in MARKET,
                )
                if "value" in cell:
                    cell["cadence"] = cadence
                if key == "relative_return" and row.get("benchmark") == ticker:
                    cell = {"status": "na", "reason": "This fund is the reference benchmark."}
                elif key == "claim_price" and terms.get("tradeable") is False:
                    cell = {"status": "na", "reason": "This claim has no tradeable listing."}
                elif blocked:
                    if gate["source"] not in sources:
                        sources.append(gate["source"])
                    cell = {
                        "status": "missing",
                        "reason": "Issuer identity conflict. Registry and security filing identify different issuers.",
                        "sources": [sources.index(gate["source"])],
                    }
                elif (
                    cell["status"] == "missing"
                    and key in SHARE_IDS
                    and not (doc.get("share_basis") or {}).get("eligible")
                ):
                    cell["reason"] = "A verified, comparable share basis is required."
                elif cell["status"] == "missing" and s.get("gap"):
                    cell["reason"] = s["gap"]
                row[mode][key] = cell
        dates = [(performance or {}).get("as_of"), quote.get("price_date") or quote.get("as_of")]
        dates.extend(p["period"] for s in metrics.values() for p in s.get("monthly", []))
        row["price_date"] = max((d for d in dates if d and d <= self.as_of), default=None)
        row["fiscal_date"] = max(
            (
                cell["period"]
                for window in ("quarter", "ttm")
                for key, cell in row[window].items()
                if cell.get("period") and key not in MARKET and profile != "fund"
            ),
            default=None,
        )
        if profile in {"claim", "preferred", "debenture"}:
            row["fiscal_date"] = None
            if blocked:
                row["price_date"] = None
        self.rows[ticker] = row

    def finish(self, index_rows):
        index = {r["ticker"]: r for r in index_rows}
        for ticker, row in self.rows.items():
            listed = index[ticker]
            profile = row["profile"]
            peers = {}
            for group in self.config.get("peer_groups", []):
                if ticker in group["members"]:
                    peers.update(
                        {
                            t: group["label"]
                            for t in group["members"]
                            if t in self.rows and self.rows[t]["profile"] == profile and t != ticker
                        }
                    )
            for t in (
                listed.get("peers", [])
                if profile not in {"claim", "preferred", "debenture", "holding", "fund"}
                else []
            ):
                if isinstance(t, str):
                    t = self.aliases.get(t, {}).get("ticker", t)
                    if t in self.rows and self.rows[t]["profile"] == profile and t != ticker:
                        peers.setdefault(t, "Company research peer")
            # Only precise industries with comparable reporting markets and scale qualify.
            sic = str(self.sic.get(ticker, {}).get("sic", ""))
            if (
                not peers
                and len(sic) == 4
                and not sic.endswith(("00", "99"))
                and sic != "6798"
                and profile not in {"claim", "preferred", "debenture", "fund", "holding"}
            ):
                measure = "assets" if profile in {"bank", "insurance"} else "revenue"
                ref = listed.get("latest", {}).get(measure, {})
                candidates = []
                for t, other in index.items():
                    p = other.get("latest", {}).get(measure, {})
                    if (
                        t != ticker
                        and self.rows[t]["profile"] == profile
                        and str(self.sic.get(t, {}).get("sic", "")) == sic
                        and self.registry.get(ticker, {}).get("market")
                        and self.registry.get(t, {}).get("market") == self.registry[ticker]["market"]
                        and p.get("unit") == ref.get("unit")
                        and p.get("value", 0) > 0
                        and ref.get("value", 0) > 0
                        and p.get("frequency") == ref.get("frequency")
                        and abs(fiscal_gap(p["period"], ref["period"])) <= 100
                    ):
                        ratio = p["value"] / ref["value"]
                        if 0.25 <= ratio <= 4:
                            candidates.append((abs(math.log(ratio)), t))
                peers.update({t: "Same industry, market and size range" for _, t in sorted(candidates)[:8]})
            seen = {self.issuers[ticker]}
            row["peers"] = {}
            for t, reason in peers.items():
                if self.issuers[t] not in seen:
                    row["peers"][t] = reason
                    seen.add(self.issuers[t])
        registered = {self.aliases.get(t, {}).get("ticker", t) for t in self.registry}
        missing = {
            t: self.registry.get(t, {}).get("company", t) for t in sorted(registered - self.rows.keys())
        }
        return {
            "version": 1,
            "as_of": self.as_of,
            "labels": LABELS,
            "profiles": PROFILES,
            "rows": self.rows,
            "aliases": {k: v["ticker"] for k, v in self.aliases.items()},
            "missing": missing,
            "registered": sorted(self.registry),
            "registered_count": len(self.registry),
        }
