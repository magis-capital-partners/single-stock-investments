#!/usr/bin/env python3
"""Build ``dashboard/data/separations.json`` from the register, flows and quotes.

Rows are ranked only when identity and terms gates pass.  A split-off spread
is shown only when the filed formula (discount and upper limit) and both
quotes exist.  Odd-lot alerts are per owner sleeve and open a human ticket;
nothing here places or prefills an order.

Quotes: last-known-good delayed closes in
``_system/data/separations/separation_market.json``.  ``--refresh-quotes``
pulls Yahoo daily closes for active separations (fail-soft).  Market inputs
for float and ADV come from the same offline caches the index model uses.

Also writes ``{PARENT}/research/distribution_events.json`` rows of type
``spin_off`` / ``split_off`` for registered parents when the filing-locked
fair value per parent share can be computed, so the total-return panel stops
dropping the distribution.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_separation_universe import health  # noqa: E402
from index_market_inputs import load_fundamentals_cache, market_inputs_for_ticker  # noqa: E402
from separation_common import (  # noqa: E402
    CAPTION,
    DASHBOARD_PATH,
    EVENTS_PATH,
    FLOWS_PATH,
    OUTCOMES_PATH,
    RESEARCH_ONLY,
    ROOT,
    SCHEMA_VERSION,
    SEPARATION_DIR,
    end_date,
    finite,
    gate_state,
    latest_registry,
    load_jsonl,
    parse_date,
    read_json,
    utc_now,
    write_json,
)
from split_off_terms import ODD_LOT_MAX_SHARES, odd_lot_payoff, spread_snapshot, terms_summary  # noqa: E402

MARKET_PATH = SEPARATION_DIR / "separation_market.json"
SLEEVE_FILES = {"drew": ROOT / "dashboard" / "data" / "sleeves_drew.json", "michael": ROOT / "dashboard" / "data" / "sleeves_michael.json"}
YAHOO_UA = "Mozilla/5.0 (compatible; MagisSeparationMonitor/1.0)"
QUOTE_STALE_DAYS = 7

KIND_LABEL = {
    "split_off": "Split-off exchange offer",
    "spin_off": "Spin-off",
    "carve_out_ipo": "Carve-out IPO",
    "clean_up_spin": "Clean-up distribution",
    "retained_stake_sale": "Retained-stake sale",
    "reverse_morris_trust": "Reverse Morris Trust",
}
NEXT_ACTION = {
    "split_off": "Read the final-results 8-K: accepted shares, proration factor, settlement date. Then model the unwind.",
    "spin_off": "Read the Form 10: distribution ratio, record and distribution dates, SpinCo debt, insider equity. Then ask who must sell.",
    "carve_out_ipo": "Record the IPO float and the parent's stated divestment path; the overhang is dated supply.",
    "clean_up_spin": "Treat as a spin-off of the unexchanged shares: ratio, record date, index policy.",
    "retained_stake_sale": "Track the remaining stake to zero from each 10-Q and 8-K.",
    "reverse_morris_trust": "Read both the distribution ratio and the merger consideration; two sellers, two clocks.",
}


# ------------------------------------------------------------------- quotes
def fetch_close(symbol: str) -> tuple[float | None, str | None, float | None]:
    import urllib.error
    import urllib.request

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        result = payload["chart"]["result"][0]
        stamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        volumes = result["indicators"]["quote"][0].get("volume") or []
    except Exception:  # noqa: BLE001 - vendor failure keeps last-known-good
        return None, None, None
    vols = [float(v) for v in volumes if v]
    avg_vol = sum(vols) / len(vols) if vols else None
    for ts, close in zip(reversed(stamps), reversed(closes)):
        if close is not None:
            return float(close), datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(), avg_vol
    return None, None, None


def refresh_quotes(records: list[dict]) -> dict:
    market = read_json(MARKET_PATH, {"quotes": {}}) or {"quotes": {}}
    quotes = market.setdefault("quotes", {})
    for rec in records:
        if rec.get("lifecycle") != "active":
            continue
        for ticker in (rec.get("parent_ticker"), rec.get("spinco_ticker")):
            if not ticker:
                continue
            close, day, avg_vol = fetch_close(ticker)
            if close is not None:
                quotes[ticker] = {"close": close, "quote_date": day, "avg_volume_10d": avg_vol, "source": "yahoo_chart_delayed", "fetched_at": utc_now()}
    market["as_of"] = utc_now()
    write_json(MARKET_PATH, market)
    return market


def quote_for(ticker: str | None, market: dict, mi: dict, today: date) -> tuple[float | None, str | None, str | None]:
    """(price, quote_date, source). Market file first, then offline inputs."""
    if not ticker:
        return None, None, None
    q = (market.get("quotes") or {}).get(ticker) or {}
    if finite(q.get("close")) is not None:
        day = parse_date(q.get("quote_date"))
        if day and (today - day).days <= QUOTE_STALE_DAYS:
            return float(q["close"]), str(q.get("quote_date")), "separation_market"
    price = finite(mi.get("price"))
    if price is not None:
        return price, mi.get("price_as_of") or None, "market_inputs"
    if finite(q.get("close")) is not None:
        return float(q["close"]), str(q.get("quote_date")), "separation_market_stale"
    return None, None, None


# -------------------------------------------------------------------- flows
def latest_flows() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for row in load_jsonl(FLOWS_PATH):
        key = (str(row.get("separation_id")), str(row.get("side")))
        current = out.get(key)
        if current is None or str(row.get("run_date")) >= str(current.get("run_date")):
            out[key] = row
    return out


def compact_flow(flow: dict | None) -> dict | None:
    if not flow:
        return None
    legs = []
    for leg in flow.get("legs") or []:
        legs.append({k: leg.get(k) for k in ("leg", "direction", "index", "shares_base", "pct_of_float_base", "window_start", "window_end", "confidence", "source", "reason")})
    return {
        "status": flow.get("status"),
        "reason": flow.get("reason"),
        "pct_of_float_low": flow.get("pct_of_float_low"),
        "pct_of_float_base": flow.get("pct_of_float_base"),
        "pct_of_float_high": flow.get("pct_of_float_high"),
        "pct_of_adv_days": flow.get("pct_of_adv_days"),
        "net_shares_base": flow.get("net_shares_base"),
        "net_flow_usd_base": flow.get("net_flow_usd_base"),
        "window_start": flow.get("window_start"),
        "window_end": flow.get("window_end"),
        "float_flag": flow.get("float_flag"),
        "run_date": flow.get("run_date"),
        "model_version": flow.get("model_version"),
        "legs": legs,
        **RESEARCH_ONLY,
    }


# ----------------------------------------------------------------- odd lots
def sleeve_positions() -> dict[str, dict[str, float]]:
    """owner -> ticker -> quantity (filled long positions only)."""
    out: dict[str, dict[str, float]] = {}
    for owner, path in SLEEVE_FILES.items():
        doc = read_json(path, {}) or {}
        positions = doc.get("positions") or []
        book: dict[str, float] = {}
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            if str(pos.get("status") or "filled") != "filled" or str(pos.get("side") or "BUY").upper() != "BUY":
                continue
            qty = finite(pos.get("qty"))
            ticker = str(pos.get("ticker") or "").upper()
            if ticker and qty:
                book[ticker] = book.get(ticker, 0.0) + qty
        out[owner] = book
    return out


def odd_lot_alerts(rec: dict, spread: dict | None, books: dict[str, dict[str, float]], today: date) -> list[dict]:
    if rec.get("kind") != "split_off" or rec.get("lifecycle") != "active":
        return []
    exchange = (rec.get("terms") or {}).get("exchange") or {}
    if not exchange.get("odd_lot_priority"):
        return []
    expiration = parse_date((rec.get("dates") or {}).get("expiration"))
    if expiration and expiration < today:
        return []
    max_shares = int(exchange.get("odd_lot_max_shares") or ODD_LOT_MAX_SHARES)
    parent = str(rec.get("parent_ticker"))
    alerts = []
    for owner, book in books.items():
        qty = book.get(parent)
        if not qty:
            continue
        eligible = qty <= max_shares
        gain_usd = gain_pct = None
        if spread and eligible:
            payoff = odd_lot_payoff(spread["parent_price"], spread["spinco_price"], spread["implied_ratio"], shares=int(qty))
            gain_usd, gain_pct = payoff["gain_usd"], payoff["gain_pct"]
        alerts.append(
            {
                "separation_id": rec["separation_id"],
                "parent_ticker": parent,
                "spinco_ticker": rec.get("spinco_ticker"),
                "owner": owner,
                "qty": qty,
                "eligible": eligible,
                "max_shares": max_shares,
                "gain_usd": gain_usd,
                "gain_pct": gain_pct,
                "expiration": expiration.isoformat() if expiration else None,
                "action": "Human ticket. Tendering all shares in an odd lot avoids proration; nothing here places an order.",
                **RESEARCH_ONLY,
            }
        )
    return alerts


# ------------------------------------------------------- distribution events
def write_distribution_events(rec: dict, spread: dict | None, quotes: dict[str, tuple[float | None, str | None, str | None]]) -> bool:
    """Record a spin_off / split_off row for the parent's total-return ledger when lockable."""
    parent = rec.get("parent_ticker")
    if not parent:
        return False
    terms = rec.get("terms") or {}
    dates = rec.get("dates") or {}
    kind = rec.get("kind")
    ex_date = dates.get("distribution") if kind in {"spin_off", "clean_up_spin", "reverse_morris_trust"} else dates.get("settlement")
    if not ex_date:
        return False
    fair_value = None
    if kind in {"spin_off", "clean_up_spin", "reverse_morris_trust"}:
        ratio = finite(terms.get("distribution_ratio"))
        first_close = finite(terms.get("spinco_first_regular_way_close"))
        if ratio and first_close:
            fair_value = ratio * first_close
    if fair_value is None:
        return False
    path = ROOT / parent / "research" / "distribution_events.json"
    if not path.parent.exists():
        return False
    doc = read_json(path, None)
    if not isinstance(doc, dict):
        doc = {
            "schema_version": "1.0",
            "ticker": parent,
            "currency": "USD",
            "coverage": {"status": "partial", "start": None, "end": None, "note": "separation ledger rows only; dividends not reconciled here"},
            "sources": [],
            "events": [],
        }
    events = doc.setdefault("events", [])
    marker = f"separation:{rec['separation_id']}"
    if any(e.get("source") == marker for e in events):
        return False
    events.append(
        {
            "ex_date": ex_date,
            "type": "spin_off",
            "fair_value_per_parent_share": round(fair_value, 6),
            "currency": "USD",
            "source": marker,
            "source_tier": "sec_primary",
            "reconciliation_status": "reconciled",
        }
    )
    events.sort(key=lambda e: str(e.get("ex_date")))
    write_json(path, doc)
    return True


# ---------------------------------------------------------------------- rows
MATERIAL_PCT_OF_FLOAT = 0.25
MATERIAL_ADV_DAYS = 0.5


def _material_selling(flow: dict) -> bool:
    """A forced-seller row needs net selling that someone would notice."""
    net = finite(flow.get("net_shares_base"))
    if net is None or net >= 0:
        return False
    pct = finite(flow.get("pct_of_float_base"))
    days = finite(flow.get("pct_of_adv_days"))
    if pct is not None and abs(pct) >= MATERIAL_PCT_OF_FLOAT:
        return True
    if days is not None and days >= MATERIAL_ADV_DAYS:
        return True
    return pct is None and days is None  # shares known, denominators unknown: show, labelled


def discovery_events(limit: int = 60) -> list[dict]:
    """Unreviewed EDGAR hits for the desk's discovery book. Identity is not verified."""
    rows = [r for r in load_jsonl(EVENTS_PATH) if r.get("status") == "unreviewed" and r.get("kind_hint") in {"spin_off", "split_off", "clean_up_spin", "retained_stake_sale"}]
    rows.sort(key=lambda r: str(r.get("filed") or ""), reverse=True)
    registered_ciks: set[str] = set()
    registered_tickers: set[str] = set()
    for rec in latest_registry():
        for key in ("parent_cik", "spinco_cik"):
            if rec.get(key):
                registered_ciks.add(str(rec[key]))
        for key in ("parent_ticker", "spinco_ticker"):
            if rec.get(key):
                registered_tickers.add(str(rec[key]).upper())
    seen: set[tuple] = set()
    out = []
    for r in rows:
        if str(r.get("cik") or "") in registered_ciks or str(r.get("ticker") or "").upper() in registered_tickers:
            continue  # already on the register; the register row is the desk entry
        key = (r.get("cik"), r.get("kind_hint"))
        if key in seen:
            continue
        seen.add(key)
        out.append({k: r.get(k) for k in ("event_id", "cik", "entity_name", "ticker", "form", "accession", "filed", "url", "kind_hint", "query_family")})
        if len(out) >= limit:
            break
    return out

def status_label(rec: dict, today: date) -> str:
    dates = rec.get("dates") or {}
    kind = rec.get("kind")
    if kind == "split_off":
        exp = parse_date(dates.get("expiration"))
        settle = dates.get("settlement")
        exchange = (rec.get("terms") or {}).get("exchange") or {}
        if settle:
            return f"Settlement {settle}"
        if exp and exp < today and exchange.get("parent_shares_accepted") is None:
            return f"Expired {exp.isoformat()}; final results not yet filed"
        if exp:
            return f"Expires {exp.isoformat()}"
        return "Expiration not stated"
    dist = dates.get("distribution")
    if dist:
        return f"Distribution {dist}" if parse_date(dist) and parse_date(dist) >= today else f"Orphan window after {dist}"
    return "Distribution date not stated"


def build_rows(*, today: date, market: dict, books: dict, cache: dict, holdings: dict) -> tuple[list[dict], list[dict], list[dict], dict, dict]:
    flows = latest_flows()
    rows: list[dict] = []
    alerts: list[dict] = []
    forced: list[dict] = []
    by_ticker: dict[str, list[str]] = defaultdict(list)
    attach: dict[str, dict] = defaultdict(lambda: {"roles": [], "odd_lot": {"eligible_owners": [], "expiration": None}})
    for rec in latest_registry():
        sid = rec["separation_id"]
        gates = gate_state(rec)
        kind = rec.get("kind")
        parent, spinco = rec.get("parent_ticker"), rec.get("spinco_ticker")
        p_mi = market_inputs_for_ticker(parent, holdings_meta=holdings.get(parent) or {}, fundamentals_cache=cache) if parent else {}
        s_mi = market_inputs_for_ticker(spinco, holdings_meta=holdings.get(spinco) or {}, fundamentals_cache=cache) if spinco else {}
        p_price, p_day, p_src = quote_for(parent, market, p_mi, today)
        s_price, s_day, s_src = quote_for(spinco, market, s_mi, today)
        spread = None
        if kind == "split_off" and gates["terms"]["pass"] and p_price and s_price:
            exchange = (rec.get("terms") or {}).get("exchange") or {}
            settlement = parse_date((rec.get("dates") or {}).get("settlement")) or parse_date((rec.get("dates") or {}).get("expiration"))
            as_of = min(filter(None, [parse_date(p_day), parse_date(s_day), today])) if (p_day or s_day) else today
            spread = spread_snapshot(parent_price=p_price, spinco_price=s_price, exchange=exchange, as_of=as_of, settlement=settlement)
            if spread:
                spread["quote_sources"] = {"parent": p_src, "spinco": s_src}
        flow_parent = compact_flow(flows.get((sid, "parent")))
        flow_spinco = compact_flow(flows.get((sid, "spinco")))
        ends = end_date(rec)
        row = {
            "separation_id": sid,
            "kind": kind,
            "kind_label": KIND_LABEL.get(kind, kind),
            "status": rec.get("status"),
            "lifecycle": rec.get("lifecycle"),
            "parent_ticker": parent,
            "spinco_ticker": spinco,
            "spinco_name": rec.get("spinco_name"),
            "dates": rec.get("dates") or {},
            "ends": ends,
            "ends_label": status_label(rec, today),
            "gates": gates,
            "terms_summary": terms_summary(rec),
            "spread": spread,
            "flows": {"parent": flow_parent, "spinco": flow_spinco},
            "sources": rec.get("sources") or [],
            "next": NEXT_ACTION.get(kind, "Read the filing."),
            "notes": rec.get("notes") or "",
            **RESEARCH_ONLY,
        }
        rows.append(row)
        for t in (parent, spinco):
            if t:
                by_ticker[t].append(sid)
        for side, t, fl in (("parent", parent, flow_parent), ("spinco", spinco, flow_spinco)):
            if not t:
                continue
            role = side if not (side == "parent" and rec.get("status") == "completed") else "stub"
            attach[t]["roles"].append(
                {
                    "separation_id": sid,
                    "role": role,
                    "kind": kind,
                    "status": rec.get("status"),
                    "counterparty": spinco if side == "parent" else parent,
                    "ends": ends,
                    "ends_label": row["ends_label"],
                    "flow": {k: (fl or {}).get(k) for k in ("pct_of_float_base", "pct_of_adv_days", "window_start", "window_end", "status")} if fl else None,
                }
            )
            if fl and fl.get("status") == "ok" and _material_selling(fl):
                pct = fl.get("pct_of_float_base")
                size = (
                    f"{abs(pct):.2f}% of float" if pct is not None
                    else f"{abs(fl.get('net_shares_base') or 0) / 1e6:,.1f}M shares (float unknown)"
                )
                forced.append(
                    {
                        "separation_id": sid,
                        "ticker": t,
                        "side": side,
                        "kind": kind,
                        "what": f"{KIND_LABEL.get(kind, kind)}: modelled selling of {size}"
                        + (f", {fl['pct_of_adv_days']:.1f} days of volume" if fl.get("pct_of_adv_days") else ""),
                        "window_start": fl.get("window_start"),
                        "window_end": fl.get("window_end"),
                        "pct_of_float_base": fl.get("pct_of_float_base"),
                        "pct_of_adv_days": fl.get("pct_of_adv_days"),
                        "confidence": "estimate",
                        "evidence_url": ((rec.get("sources") or [{}])[0] or {}).get("url"),
                        "as_of": fl.get("run_date"),
                    }
                )
        for alert in odd_lot_alerts(rec, spread, books, today):
            alerts.append(alert)
            if alert["eligible"]:
                attach[parent]["odd_lot"]["eligible_owners"].append(alert["owner"])
                attach[parent]["odd_lot"]["expiration"] = alert["expiration"]
        write_distribution_events(rec, spread, {})
    rows.sort(key=lambda r: (0 if r["lifecycle"] == "active" else 1, r["ends"] or "9999-99-99", r["parent_ticker"] or ""))
    return rows, alerts, forced, dict(by_ticker), {k: dict(v) for k, v in attach.items()}


def outcomes_summary() -> dict:
    outcomes = load_jsonl(OUTCOMES_PATH)
    by_h: dict[int, list[float]] = defaultdict(list)
    for row in outcomes:
        ex = finite(row.get("excess_return_pct"))
        if ex is not None:
            by_h[int(row.get("horizon_sessions") or 0)].append(ex)
    return {
        "matured": len(outcomes),
        "by_horizon": {
            str(h): {"n": len(v), "median_excess_return_pct": round(sorted(v)[len(v) // 2], 3)} for h, v in sorted(by_h.items()) if v
        },
    }


def build(*, today: date | None = None, refresh: bool = False) -> dict:
    today = today or date.today()
    records = latest_registry()
    market = refresh_quotes(records) if refresh else (read_json(MARKET_PATH, {"quotes": {}}) or {"quotes": {}})
    books = sleeve_positions()
    cache = load_fundamentals_cache()
    holdings = (read_json(ROOT / "_system" / "portfolio" / "registry.json", {}) or {}).get("holdings") or {}
    rows, alerts, forced, by_ticker, attach = build_rows(today=today, market=market, books=books, cache=cache, holdings=holdings)
    counts = {
        "ranked": sum(1 for r in rows if r["gates"]["status"] == "ranked" and r["lifecycle"] != "closed"),
        "discovery": sum(1 for r in rows if r["gates"]["status"] == "discovery" and r["lifecycle"] != "closed"),
        "closed": sum(1 for r in rows if r["lifecycle"] == "closed"),
        "by_kind": dict(Counter(r["kind"] for r in rows)),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "as_of": today.isoformat(),
        "caption": CAPTION,
        "definition": (
            "A separation hands a security to holders who did not choose it, or offers one at a discount to holders who must "
            "decide. The register holds the filed terms; the flow model says who must sell, how much, and until when."
        ),
        "counts": counts,
        "rows": rows,
        "by_ticker": by_ticker,
        "ticker_attach": attach,
        "odd_lot_alerts": alerts,
        "forced_seller_rows": forced,
        "discovery_events": discovery_events(),
        "outcomes_summary": outcomes_summary(),
        "market_as_of": market.get("as_of"),
        "health": health(today),
        **RESEARCH_ONLY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-quotes", action="store_true", help="fetch delayed Yahoo closes for active separations")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    payload = build(refresh=args.refresh_quotes)
    target = Path(args.out) if args.out else DASHBOARD_PATH
    write_json(target, payload)
    c = payload["counts"]
    print(
        f"Wrote {target} rows={len(payload['rows'])} ranked={c['ranked']} discovery={c['discovery']} "
        f"closed={c['closed']} odd_lot_alerts={len(payload['odd_lot_alerts'])} forced_rows={len(payload['forced_seller_rows'])} "
        f"health={payload['health']['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
