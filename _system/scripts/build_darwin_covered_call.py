#!/usr/bin/env python3
"""Darwin Covered Call signal: which calls on S&P 500 stocks are worth selling against a long position.

For a holder, a covered call adds premium received minus whatever it owes at expiry. Over 2016-2026
(698,668 calls on point-in-time S&P 500 members) that was negative on average for monthly calls and
about zero for weeklies; the calls were fairly priced and the loss was upside handed away. Four
stock conditions, each stable across 2016-20 and 2021-26, separated the calls that paid:

  low_beta            252-day beta below the universe median
  rich_call_skew      25-delta call IV minus ATM IV (~30-day expiry) above median
  iv_above_forecast   the call's IV over the technical-fear-v3 21-day vol forecast above median
  near_52w_high       distance below the 52-week high smaller than median

and an earnings report inside the call's window is a veto. A call's expected value is the
historical average for its (tenor bucket, delta, score) cell in _system/data/darwin_cc/lookup_v1.json.

Inputs
  * chains: Cboe delayed quotes (keyless, ~15 min delayed), one request per symbol
  * stock state: dashboard/data/technical_signals.json (beta, 52-week drawdown, vol forecast)
  * earnings: Nasdaq earnings calendar, one request per business day for the next ~7 weeks
  * universe: _system/reference/market-data/index/sp500_constituents.json

Output: dashboard/data/darwin_cc.json -- derived values only (scores, flags, strikes, rounded premium
as % of price, expected value). No raw bid/ask/IV/open-interest tables are written: vendor datasets
may not be copied to public exports (_system/trading/portfolio_hub/MARKET_DATA_SOURCES.md).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOKUP = ROOT / "_system/data/darwin_cc/lookup_v1.json"
TECHNICALS = ROOT / "dashboard/data/technical_signals.json"
UNIVERSE = ROOT / "_system/reference/market-data/index/sp500_constituents.json"
OUTPUT = ROOT / "dashboard/data/darwin_cc.json"

CBOE_URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings?date={day}"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126 Safari/537.36")

TENORS = {"7d": (4, 10), "14d": (11, 17), "21d": (18, 24), "35d": (30, 38), "42d": (39, 46)}
DELTAS = (0.10, 0.20, 0.30, 0.40, 0.50)
DELTA_TOLERANCE = 0.07
MAX_REL_SPREAD = 0.50          # the backtest dropped quotes wider than this
LIQUID_OPEN_INTEREST = 500     # display flag only
LIQUID_REL_SPREAD = 0.25
MIN_CELL_MONTHS = 24           # a cell needs this much history before it is ranked
MIN_TOP_CELL_T = 1.5           # the cross-index list only shows cells that were clearly positive
MIN_TOP_SCORE = 3              # walk-forward: score 3-4 weeklies paid (t 1.9 / 3.8); score 2 did not (t 1.2)
MIN_COVERAGE = 0.80            # refuse to publish if fewer chains than this arrived
CONDITIONS = ("low_beta", "rich_call_skew", "iv_above_forecast", "near_52w_high")
OCC = re.compile(r"^(?P<root>.+?)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #

def _get_json(url: str, *, timeout: float = 45.0, attempts: int = 3) -> dict | None:
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                return None
            last = exc
            if exc.code == 429:             # Cboe rate limit: honour Retry-After, else back off hard
                wait = float(exc.headers.get("Retry-After") or 0) or 10.0 * (attempt + 1)
                time.sleep(min(wait, 60.0))
                continue
        except Exception as exc:  # network hiccup: retry with backoff
            last = exc
        time.sleep(1.5 * (attempt + 1))
    print(f"  fetch failed: {url} ({last})", file=sys.stderr)
    return None


def fetch_chains(symbols: list[str], workers: int = 3) -> dict[str, dict]:
    """Chains for every symbol. Cboe rate-limits bursts, so a modest pool does the first pass and
    whatever failed gets one slow serial retry."""
    def one(sym):
        return sym, _get_json(CBOE_URL.format(symbol=sym), attempts=4)
    out = {}
    with cf.ThreadPoolExecutor(workers) as ex:
        for sym, payload in ex.map(one, symbols):
            if payload and isinstance(payload.get("data"), dict):
                out[sym] = payload["data"]
    missing = [s for s in symbols if s not in out]
    if missing:
        print(f"  retrying {len(missing)} symbols serially", flush=True)
        for sym in missing:
            payload = _get_json(CBOE_URL.format(symbol=sym), attempts=4)
            if payload and isinstance(payload.get("data"), dict):
                out[sym] = payload["data"]
            time.sleep(1.0)
    return out


def _norm(sym: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(sym).upper())


def fetch_earnings(start: date, days: int = 50) -> tuple[dict[str, str], dict]:
    """Next report date per symbol from the Nasdaq calendar (business days only)."""
    found: dict[str, str] = {}
    requested = ok = 0
    for i in range(days):
        day = start + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        requested += 1
        payload = _get_json(NASDAQ_URL.format(day=day.isoformat()), timeout=30, attempts=2)
        rows = (((payload or {}).get("data") or {}).get("rows")) or []
        if payload is not None:
            ok += 1
        for row in rows:
            key = _norm(row.get("symbol", ""))
            if key and key not in found:
                found[key] = day.isoformat()
        time.sleep(0.2)
    return found, {"source": "nasdaq_earnings_calendar", "days_requested": requested, "days_ok": ok,
                   "symbols": len(found)}


# --------------------------------------------------------------------------- #
# pure computation (tested without the network)
# --------------------------------------------------------------------------- #

def parse_chain(chain: dict, today: date) -> tuple[float | None, list[dict]]:
    """Spot and the usable options (dte 1..50, positive IV and bid, sane spread)."""
    spot = chain.get("current_price") or chain.get("close")
    rows = []
    for o in chain.get("options") or []:
        m = OCC.match(str(o.get("option", "")))
        if not m:
            continue
        exp = date(2000 + int(m["yy"]), int(m["mm"]), int(m["dd"]))
        dte = (exp - today).days
        bid, ask, iv, delta = o.get("bid"), o.get("ask"), o.get("iv"), o.get("delta")
        if dte < 1 or dte > 50 or not bid or not ask or bid <= 0 or ask < bid or not iv or iv <= 0.01 or delta is None:
            continue
        mid = (bid + ask) / 2
        rows.append({"expiry": exp, "dte": dte, "right": m["cp"], "strike": int(m["strike"]) / 1000.0,
                     "bid": float(bid), "ask": float(ask), "mid": mid, "rel_spread": (ask - bid) / mid,
                     "iv": float(iv), "delta": float(delta), "oi": float(o.get("open_interest") or 0)})
    return (float(spot) if spot else None), rows


def name_skew(rows: list[dict], spot: float) -> tuple[float | None, float | None]:
    """ATM IV and 25-delta call skew on the expiry nearest 30 days (the backtest's definition)."""
    exps = sorted({r["dte"] for r in rows})
    if not exps or not spot:
        return None, None
    m1 = min(exps, key=lambda d: abs(d - 30))
    q = [r for r in rows if r["dte"] == m1]
    strikes = sorted({r["strike"] for r in q}, key=lambda k: abs(k - spot))
    if not strikes:
        return None, None
    atm = [r["iv"] for r in q if r["strike"] == strikes[0]]
    atm_iv = sum(atm) / len(atm)
    calls = [r for r in q if r["right"] == "C"]
    if not calls:
        return atm_iv, None
    c25 = min(calls, key=lambda r: abs(r["delta"] - 0.25))
    skew = c25["iv"] - atm_iv if abs(c25["delta"] - 0.25) < 0.08 else None
    return atm_iv, skew


def candidate_calls(rows: list[dict], spot: float) -> list[dict]:
    """One expiry per tenor bucket (nearest the bucket's centre), one call per delta target."""
    calls = [r for r in rows if r["right"] == "C" and r["rel_spread"] <= MAX_REL_SPREAD]
    out = []
    for tenor, (lo, hi) in TENORS.items():
        exps = sorted({r["dte"] for r in calls if lo <= r["dte"] <= hi})
        if not exps:
            continue
        centre = (lo + hi) / 2
        dte = min(exps, key=lambda d: abs(d - centre))
        q = [r for r in calls if r["dte"] == dte]
        for target in DELTAS:
            r = min(q, key=lambda x: abs(x["delta"] - target))
            if abs(r["delta"] - target) > DELTA_TOLERANCE:
                continue
            premium = r["mid"] - 0.25 * (r["ask"] - r["bid"])
            out.append({"tenor": tenor, "delta_target": target, "expiry": r["expiry"].isoformat(), "dte": r["dte"],
                        "strike": r["strike"], "otm_pct": (r["strike"] / spot - 1) * 100,
                        "premium_pct": premium / spot * 100, "iv": r["iv"],
                        "liquid": r["oi"] >= LIQUID_OPEN_INTEREST and r["rel_spread"] <= LIQUID_REL_SPREAD})
    return out


def _round_to(x: float, step: float) -> float:
    return round(round(x / step) * step, 4)


def build_payload(universe: list[str], technicals: dict, chains: dict[str, dict], earnings: dict[str, str],
                  lookup: dict, *, today: date, now: datetime, earnings_meta: dict | None = None) -> dict:
    cells = {(c["tenor"], round(c["delta"], 2), c["score"]): c for c in lookup["cells"]}
    names = []
    for sym in universe:
        tech = technicals.get(sym) or technicals.get(sym.replace(".", "-")) or {}
        chain = chains.get(sym)
        rec = {"symbol": sym, "status": "ok"}
        beta = ((tech.get("context") or {}).get("beta_252d"))
        dd = ((tech.get("measures") or {}).get("drawdown_1y_pct"))
        vol = (((tech.get("outlook") or {}).get("risk") or {}).get("expected_vol_21d_pct"))
        if chain is None:
            rec["status"] = "no_chain"
        elif beta is None or dd is None or not vol:
            rec["status"] = "no_technicals"
        spot, rows = parse_chain(chain, today) if chain else (None, [])
        if rec["status"] == "ok" and (not spot or not rows):
            rec["status"] = "no_chain"
        rec["_beta"], rec["_dd"] = beta, (dd / 100 if dd is not None else None)
        rec["_vol"] = vol / 100 if vol else None
        rec["next_earnings"] = earnings.get(_norm(sym))
        if rec["status"] == "ok":
            rec["_atm_iv"], rec["_skew"] = name_skew(rows, spot)
            rec["_calls"] = candidate_calls(rows, spot)
            for c in rec["_calls"]:
                c["iv_fc"] = c["iv"] / rec["_vol"]
            if not rec["_calls"]:
                rec["status"] = "no_liquid_calls"
        names.append(rec)

    live = [n for n in names if n["status"] == "ok"]
    contracts = [c for n in live for c in n["_calls"]]

    def median(values):
        values = [v for v in values if v is not None]
        return statistics.median(values) if values else None
    # Medians over every candidate contract, as in the backtest (a name counts once per contract).
    med = {"beta": median(n["_beta"] for n in live for _ in n["_calls"]),
           "skew": median(n["_skew"] for n in live for _ in n["_calls"]),
           "iv_fc": median(c["iv_fc"] for c in contracts),
           "dd": median(n["_dd"] for n in live for _ in n["_calls"])}

    top = []
    for n in live:
        flags = {"low_beta": n["_beta"] < med["beta"],
                 "rich_call_skew": n["_skew"] is not None and med["skew"] is not None and n["_skew"] > med["skew"],
                 "near_52w_high": n["_dd"] > med["dd"]}
        best = []
        for c in n["_calls"]:
            c_flags = dict(flags, iv_above_forecast=c["iv_fc"] > med["iv_fc"])
            score = sum(bool(c_flags[k]) for k in CONDITIONS)
            # Today counts: a call written before tonight's after-close report carries it.
            veto = bool(n["next_earnings"]) and today.isoformat() <= n["next_earnings"] <= c["expiry"]
            cell = cells.get((c["tenor"], round(c["delta_target"], 2), score))
            ev = cell["ev_bp"] if cell else None
            row = {"tenor": c["tenor"], "delta": c["delta_target"], "expiry": c["expiry"], "dte": c["dte"],
                   "strike": c["strike"], "otm_pct": round(c["otm_pct"], 1),
                   "premium_pct": _round_to(c["premium_pct"], 0.05), "score": score,
                   "conditions": [k for k in CONDITIONS if c_flags[k]], "earnings_veto": veto,
                   "liquid": c["liquid"], "ev_bp": ev,
                   "ev_annual_pct": round(ev / 1e4 * 365 / c["dte"] * 100, 2) if ev is not None else None,
                   "cell_t": cell["t"] if cell else None, "cell_months": cell["months"] if cell else 0}
            best.append(row)
        ranked = sorted((r for r in best if r["ev_bp"] is not None and not r["earnings_veto"]),
                        key=lambda r: r["ev_annual_pct"], reverse=True)
        # Every positive call (the screener filters by tenor and delta) plus the two best others,
        # so a stock with nothing worth selling still shows its least-bad option.
        positive = [r for r in ranked if r["ev_bp"] > 0]
        n["calls"] = positive + [r for r in ranked if r["ev_bp"] <= 0][:2]
        n["score"] = max((r["score"] for r in best), default=0)
        n["conditions"] = {k: bool(v) for k, v in flags.items()}
        n["vetoed_calls"] = sum(r["earnings_veto"] for r in best)
        for r in ranked:
            if (r["ev_bp"] > 0 and r["liquid"] and r["cell_months"] >= MIN_CELL_MONTHS
                    and (r["cell_t"] or 0) >= MIN_TOP_CELL_T and r["score"] >= MIN_TOP_SCORE):
                top.append(dict(r, symbol=n["symbol"]))
                break

    top.sort(key=lambda r: r["ev_annual_pct"], reverse=True)
    out_names = []
    for n in names:
        row = {"symbol": n["symbol"], "status": n["status"], "next_earnings": n.get("next_earnings")}
        if n["status"] == "ok":
            row.update(score=n["score"], conditions=n["conditions"], calls=n["calls"], vetoed_calls=n["vetoed_calls"])
        out_names.append(row)
    hist = {str(s): sum(1 for n in live if n.get("score") == s) for s in range(5)}
    coverage = len(live) / max(len(universe), 1)
    return {
        "schema": "darwin_cc.v1",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trading_date": today.isoformat(),
        "quote_source": "Cboe delayed quotes (about 15 minutes delayed); only derived values are published",
        "universe": {"count": len(universe), "scored": len(live), "coverage": round(coverage, 3),
                     "missing": sorted(n["symbol"] for n in names if n["status"] != "ok")},
        "earnings": earnings_meta or {},
        "medians": {k: (round(v, 4) if v is not None else None) for k, v in med.items()},
        "score_histogram": hist,
        "top": top[:40],
        "names": out_names,
        "method": {k: lookup[k] for k in ("what", "sample", "conditions", "tenor_buckets_days", "validation")},
    }


# --------------------------------------------------------------------------- #

def load_universe() -> list[str]:
    doc = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    return sorted({str(t).strip().upper() for t in doc.get("tickers") or [] if t})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default=str(OUTPUT))
    ap.add_argument("--limit", type=int, default=0, help="score only the first N symbols (smoke test)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--chains-cache", help="local development only: reuse/save raw chains at this path "
                                           "(never commit it -- raw vendor quotes)")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        today = now.astimezone(ZoneInfo("America/New_York")).date()
    except Exception:  # no tz database (bare Windows Python): EDT offset is close enough for a date
        today = (now - timedelta(hours=4)).date()
    universe = load_universe()
    if args.limit:
        universe = universe[: args.limit]
    lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
    technicals = json.loads(TECHNICALS.read_text(encoding="utf-8")).get("by_ticker") or {}
    print(f"universe {len(universe)}; fetching Cboe chains ...", flush=True)
    t0 = time.time()
    cache = Path(args.chains_cache) if args.chains_cache else None
    if cache and cache.exists():
        chains = json.loads(cache.read_text(encoding="utf-8"))
    else:
        chains = fetch_chains(universe, workers=args.workers)
        if cache:
            cache.write_text(json.dumps(chains), encoding="utf-8")
    print(f"  {len(chains)} chains in {time.time() - t0:.0f}s", flush=True)
    earnings, meta = fetch_earnings(today)
    print(f"  earnings calendar: {meta}", flush=True)
    payload = build_payload(universe, technicals, chains, earnings, lookup, today=today, now=now, earnings_meta=meta)
    cov = payload["universe"]["coverage"]
    if cov < MIN_COVERAGE and not args.limit:
        print(f"refusing to publish: only {cov:.0%} of the universe scored (need {MIN_COVERAGE:.0%})", file=sys.stderr)
        return 1
    if meta.get("days_ok", 0) < 0.8 * max(meta.get("days_requested", 1), 1):
        print("refusing to publish: the earnings calendar did not load, so the earnings veto would be blind",
              file=sys.stderr)
        return 1
    Path(args.output).write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.output}: scored {payload['universe']['scored']}, top {len(payload['top'])}, "
          f"scores {payload['score_histogram']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
