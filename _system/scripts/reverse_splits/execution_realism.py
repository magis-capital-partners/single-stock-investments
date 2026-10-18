"""Workstream A of the shorts alpha program: execution and capacity realism on
the verified ex+1 reverse-split event (H2 passive fills under Rule 201, H3
participation cost, H4 opening-cross feasibility, tiered versus fixed
commissions as declared variants).

Research only. Inputs are the frozen expansion run (per-event ex+1 outcomes
and the historical auction identity of each event), the local SQLite SSR
states, the local Databento ``statistics`` files (official auction prints and
cross sizes) and, for H2 and H3, per-session ``trades`` and ``mbp-1`` files on
the listing venue. Nothing here contacts a broker or ThetaData.

Data cost gate. Every Databento request is priced with ``metadata.get_cost``
before anything is downloaded (``quote``). The quotes are summed; if the sum
exceeds $0.00 nothing is fetched until a human passes the quoted amount back
as ``download --approved-usd``. The approval is recorded in the manifest. Raw
files stay under ``local/raw/databento/`` (gitignored).

Published output (``execution_realism.json`` + ``execution_realism_manifest.json``)
is aggregate only and covers the train and validation splits. Holdout rows
(entry sessions from 2025-01-01) are computed but written only to
``local/holdout/`` (sealed). Per-event rows stay under ``local/workstream_a/``.

From ``_system/scripts``::

    python -m reverse_splits.execution_realism quote
    python -m reverse_splits.execution_realism download --approved-usd 0.00
    python -m reverse_splits.execution_realism build --publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config, load_config
from .databento_bars import CostRefused, fetch, is_complete
from .ledger import read_json, sha256_file, write_json
from .phase0_research import (
    RUN_ID,
    VERIFIED,
    assign_split,
)

VERSION = "shorts_ws_a.v1"
HYPOTHESES = ("H2", "H3", "H4")
QUOTE_STUDY = f"{RUN_ID}__quotes_v1"

# Modeled orders (the frozen account replay's protocol, portfolio_protocol.json).
ACCOUNT_EQUITY = 50_000.0
POSITION_FRACTION = 0.025            # 2.5% of opening equity -> $1,250
ADV_PARTICIPATION = 0.001            # 0.1% of the prior 20-session split-adjusted venue ADV
PRIOR_ADV_SESSIONS = 20
MINIMUM_NOTIONAL = 100.0
# H4: the order must be at most this share of the opening cross.
CROSS_SHARE_CAP = 0.05
# H2: passive offer from the open, judged within this window; markouts after the fill.
PASSIVE_WINDOW_SECONDS = 15 * 60
ARRIVAL_OFFSET_SECONDS = 1.0         # decision one second after the scheduled open (as the quote studies)
MARKOUT_SECONDS = (60, 300, 900)
ADVERSE_SELECTION_HORIZON = 300      # the registered "adverse selection" reads the 5-minute markout
# H3: participation schedules.
PARTICIPATION_RATES = (0.01, 0.02, 0.05)
ENTRY_WINDOW_SECONDS = 60 * 60
EXIT_WINDOW_SECONDS = 60 * 60
CROSSING_FRACTIONS = (1.0, 0.5)      # share of our fills that cross the spread (1.0 is the primary, conservative case)
# Data windows (seconds around the scheduled open and close).
PRE_OPEN_SECONDS = 5
POST_WINDOW_SECONDS = 5
PRICE_BANDS = ((0.0, 1.0, "under_1"), (1.0, 2.0, "1_to_2"), (2.0, 5.0, "2_to_5"), (5.0, float("inf"), "5_and_over"))
MAX_QUOTE_PER_REQUEST = 50.0         # a single request quoted above this is a defect, not a purchase
METADATA_INTERVAL = 1 / 6            # stay well below the provider's metadata rate limit
KEY_ENV = "DATABENTO_API_KEY"
KEY_FILE = Path(r"C:\Users\drewg\Projects\quant\DC-Execution\.env")

# Commission schedules (declared variants, A4). Dollar amounts per order leg.
COMMISSIONS = {
    "fixed": {"description": "The frozen replay's schedule: $0.005 per share, $1.00 minimum, capped at 1% of the leg's notional.",
              "per_share": 0.005, "minimum": 1.0, "maximum_notional_fraction": 0.01,
              "remove_liquidity_per_share": 0.0, "add_liquidity_per_share": 0.0, "clearing_per_share": 0.0},
    "tiered": {"description": ("IBKR Pro tiered at the lowest volume tier: $0.0035 per share, $0.35 minimum, capped at 1% of the leg's "
                               "notional, plus a $0.0030 per share exchange fee when removing liquidity, a $0.0020 per share rebate when "
                               "adding liquidity (passive fills only, and only when the fill model fills) and $0.00020 per share clearing."),
               "per_share": 0.0035, "minimum": 0.35, "maximum_notional_fraction": 0.01,
               "remove_liquidity_per_share": 0.0030, "add_liquidity_per_share": -0.0020, "clearing_per_share": 0.00020},
}
# Regulatory pass-through on the sell leg, identical under both schedules (today's published rates; see limits).
SEC_FEE_PER_DOLLAR = 27.80 / 1_000_000
FINRA_TAF_PER_SHARE = 0.000166
FINRA_TAF_MAX = 8.30


# --- small helpers -----------------------------------------------------------

def price_band(price) -> str | None:
    for lo, hi, label in PRICE_BANDS:
        if price is not None and lo <= price < hi:
            return label
    return None


def whole_shares(dollars: float, price: float) -> int:
    if not price or price <= 0:
        return 0
    return int(math.floor(dollars / price))


def commission_leg(schedule: str, shares: int, price: float, *, passive: bool, sell: bool) -> dict:
    """Dollar cost of one leg under a declared schedule; regulatory fees separate."""
    s = COMMISSIONS[schedule]
    notional = shares * price
    base = max(s["minimum"], shares * s["per_share"]) if shares > 0 else 0.0
    base = min(base, s["maximum_notional_fraction"] * notional) if notional > 0 else 0.0
    venue = shares * (s["add_liquidity_per_share"] if passive else s["remove_liquidity_per_share"])
    clearing = shares * s["clearing_per_share"]
    regulatory = (SEC_FEE_PER_DOLLAR * notional + min(FINRA_TAF_MAX, FINRA_TAF_PER_SHARE * shares)) if sell else 0.0
    return {"commission": base, "venue": venue, "clearing": clearing, "regulatory": regulatory,
            "total_ex_regulatory": base + venue + clearing, "total": base + venue + clearing + regulatory}


def _load_key() -> None:
    """Put the Databento key into the process environment from the DC-Execution env file. Never printed."""
    if os.environ.get(KEY_ENV):
        return
    if not KEY_FILE.exists():
        raise SystemExit(f"{KEY_ENV} is not set and {KEY_FILE} does not exist")
    for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(KEY_ENV + "="):
            os.environ[KEY_ENV] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return
    raise SystemExit(f"{KEY_ENV} not found in {KEY_FILE}")


def _client():
    from .databento_bars import client_from_env

    _load_key()
    return client_from_env()


def _run_dir(cfg: Config) -> Path:
    return cfg.local_dir / "expansion" / "expansion_v2" / "runs" / RUN_ID


def work_dir(cfg: Config) -> Path:
    return cfg.local_dir / "workstream_a"


def _session_bounds(day: str) -> tuple[datetime, datetime]:
    """Scheduled open and close (UTC) of an exchange session, early closes included."""
    import exchange_calendars as xc

    from .execute import session_open

    cal = _session_bounds.cal if hasattr(_session_bounds, "cal") else None
    if cal is None:
        cal = xc.get_calendar("XNYS", start="2018-01-01", end="2027-01-01")
        _session_bounds.cal = cal
    opened = session_open(day).astimezone(timezone.utc)
    closed = cal.session_close(day).to_pydatetime().astimezone(timezone.utc)
    return opened, closed


# --- events ----------------------------------------------------------------------

def event_rows(cfg: Config) -> list[dict]:
    """The 671 verified ex+1 paths with their historical auction identity, SSR state and prior ADV."""
    import numpy as np

    from .universe_study import trading_calendar

    run_dir = _run_dir(cfg)
    targets = read_json(cfg.local_dir / "execution_research" / QUOTE_STUDY / "targets.local.json", [])
    targets = [t for t in targets if "primary" in t.get("cohorts", [])]
    if not targets:
        raise SystemExit("targets.local.json from the quote study is required (historical symbol and venue per event)")
    events = {}
    actions = defaultdict(set)
    for path in sorted((run_dir / "event_outcomes").glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                e = json.loads(line)
                if e.get("verification") in VERIFIED:
                    events[e["event_id"]] = e
                    actions[e.get("database_ticker", e["ticker"])].add((e["ex_date"], float(e["ratio"])))
    rows = []
    for t in targets:
        e = events.get(t["event_id"])
        if e is None:
            continue
        o = next((o for o in e.get("outcomes", []) if o.get("cohort") == "ex_plus_1_h1"), None)
        if not o or o.get("status") != "observed_price_path" or o.get("gross_short_return") is None:
            continue
        opened, closed = _session_bounds(t["date"])
        rows.append({"event_id": t["event_id"], "key": t["key"], "ticker": t["ticker"], "symbol": t["symbol"],
                     "dataset": t["dataset"], "issuer": t["issuer"], "entry_date": t["date"], "year": t["date"][:4],
                     "split": assign_split(t["date"]), "ex_date": e["ex_date"], "ratio": e.get("ratio"),
                     "open": float(t["open"]), "close": float(t["close"]),
                     "opened": opened.isoformat(), "closed": closed.isoformat(),
                     "ret": float(o["gross_short_return"]), "exchange_class": e.get("exchange_class")})
    # SSR state at the entry open (cached Nasdaq status) and the frozen replay's prior ADV.
    conn = sqlite3.connect(f"file:{cfg.db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        states = {(tk, d): r for tk, d, r in conn.execute("SELECT ticker,date,restricted FROM ssr_states")}
    finally:
        conn.close()
    prices = sqlite3.connect((run_dir / "prices.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    cal = trading_calendar("2018-03-01", "2026-10-13")
    try:
        for r in rows:
            state = states.get((r["ticker"], r["entry_date"]))
            r["ssr_state"] = "restricted" if state == 1 else "unrestricted" if state == 0 else "unknown"
            position = int(np.searchsorted(cal, r["entry_date"]))
            floor = cal[max(0, position - PRIOR_ADV_SESSIONS)]
            prior = prices.execute(
                "SELECT date,close,volume FROM prices_daily p JOIN price_provenance v USING(ticker,date) "
                "WHERE ticker=? AND date>=? AND date<? AND v.nominal=1 ORDER BY date DESC",
                (r["ticker"], floor, r["entry_date"])).fetchall()
            volume = []
            for day, p, v in prior:
                if p is not None and v is not None and p > 0 and v >= 0:
                    factor = math.prod(ratio for ex, ratio in actions[r["ticker"]] if day < ex <= r["entry_date"])
                    volume.append(v * factor)
            r["prior_sessions"] = len(volume)
            r["adv_shares"] = float(sum(volume) / PRIOR_ADV_SESSIONS) if volume else None
    finally:
        prices.close()
    return rows


# --- Databento requests, quotes and the gated download -------------------------------

def _request_id(req: dict) -> str:
    return hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]


def requests_for(rows: list[dict]) -> list[dict]:
    """One request per (listing venue, session, schema, window); symbols grouped. Two mbp-1
    windows (open + 65 min, close - 65 min) are the planned pull; a full-session mbp-1
    variant is quoted beside them so the budget decision can see both."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        opened = datetime.fromisoformat(r["opened"])
        closed = datetime.fromisoformat(r["closed"])
        windows = {
            ("trades", "session"): (opened - timedelta(seconds=PRE_OPEN_SECONDS), closed + timedelta(seconds=POST_WINDOW_SECONDS)),
            ("mbp-1", "open"): (opened - timedelta(seconds=PRE_OPEN_SECONDS),
                                opened + timedelta(seconds=ENTRY_WINDOW_SECONDS + 5 * 60 + POST_WINDOW_SECONDS)),
            ("mbp-1", "close"): (closed - timedelta(seconds=EXIT_WINDOW_SECONDS + 5 * 60 + PRE_OPEN_SECONDS),
                                 closed + timedelta(seconds=2)),
            ("mbp-1", "session_alternative"): (opened - timedelta(seconds=PRE_OPEN_SECONDS), closed + timedelta(seconds=2)),
        }
        for (schema, window), (start, end) in windows.items():
            key = (r["dataset"], r["entry_date"], schema, window, start.isoformat(), end.isoformat())
            g = groups.setdefault(key, {"symbols": set(), "splits": set(), "events": 0})
            g["symbols"].add(r["symbol"])
            g["splits"].add(r["split"])
            g["events"] += 1
    out = []
    for (dataset, day, schema, window, start, end), g in sorted(groups.items()):
        req = dict(dataset=dataset, schema=schema, symbols=sorted(g["symbols"]), start=start, end=end)
        out.append({"id": _request_id(req), "schema": schema, "window": window, "date": day,
                    "planned": window != "session_alternative",
                    "splits": sorted(g["splits"]), "events": g["events"], "request": req})
    return out


def raw_path(cfg: Config, item: dict) -> Path:
    req = item["request"]
    return cfg.databento_dir / req["dataset"] / req["schema"] / "sessions" / f"{item['id']}.dbn.zst"


def quote_requests(cfg: Config, items: list[dict], *, client=None, log=print) -> dict:
    """Price every request (free metadata). Writes quotes.json; downloads nothing."""
    client = client or _client()
    quotes = []
    next_at = 0.0
    errors = Counter()
    for n, item in enumerate(items, 1):
        path = raw_path(cfg, item)
        if is_complete(path):
            saved = read_json(path.with_name(path.name.replace(".dbn.zst", ".ok.json")), {})
            quotes.append({**item, "quoted_usd": float(saved.get("quoted_usd") or 0.0), "status": "have",
                           "bytes": int(saved.get("bytes") or 0)})
            continue
        time.sleep(max(0.0, next_at - time.monotonic()))
        next_at = time.monotonic() + METADATA_INTERVAL
        try:
            q = float(client.metadata.get_cost(**item["request"]))
            if not math.isfinite(q) or q < 0:
                raise ValueError("invalid cost quote")
            quotes.append({**item, "quoted_usd": q, "status": "quoted"})
        except Exception as exc:  # noqa: BLE001 - recorded, never retried with another key
            errors[type(exc).__name__] += 1
            quotes.append({**item, "quoted_usd": None, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        if n % 100 == 0 or n == len(items):
            log(f"quoted {n}/{len(items)}; running total ${sum(q['quoted_usd'] or 0 for q in quotes):.4f}")
    summary = quote_summary(quotes)
    out = {"quoted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "requests": quotes,
           "summary": summary, "errors": dict(errors)}
    work_dir(cfg).mkdir(parents=True, exist_ok=True)
    write_json(work_dir(cfg) / "quotes.json", out)
    return out


def quote_summary(quotes: list[dict]) -> dict:
    def total(pred):
        sel = [q for q in quotes if pred(q) and q.get("quoted_usd") is not None]
        return {"requests": len(sel), "usd": float(sum(q["quoted_usd"] for q in sel)),
                "events": int(sum(q["events"] for q in sel))}
    planned = lambda q: q["planned"]  # noqa: E731
    out = {"planned_total": total(planned),
           "planned_by_schema_window": {f"{s}/{w}": total(lambda q, s=s, w=w: q["planned"] and q["schema"] == s and q["window"] == w)
                                        for s, w in (("trades", "session"), ("mbp-1", "open"), ("mbp-1", "close"))},
           "planned_by_split": {sp: total(lambda q, sp=sp: q["planned"] and q["splits"] == [sp]) for sp in ("train", "validate", "holdout")},
           "planned_mixed_split_requests": total(lambda q: q["planned"] and len(q["splits"]) > 1),
           "planned_train_validate_only": total(lambda q: q["planned"] and "holdout" not in q["splits"]),
           "alternative_full_session_mbp1": total(lambda q: q["window"] == "session_alternative"),
           "alternative_trades_plus_full_session_mbp1": total(lambda q: q["window"] == "session_alternative" or q["schema"] == "trades"),
           "not_yet_downloaded_planned_usd": float(sum(q["quoted_usd"] or 0 for q in quotes if q["planned"] and q["status"] == "quoted")),
           "errors": int(sum(1 for q in quotes if q["status"] == "error")),
           "max_single_request_usd": max((q["quoted_usd"] for q in quotes if q.get("quoted_usd") is not None), default=0.0)}
    return out


def download(cfg: Config, *, approved_usd: float, splits: tuple[str, ...] | None = None, client=None, log=print) -> dict:
    """Fetch the planned requests. Refuses unless quotes exist and their sum for the
    files still missing is within the approved amount. Each fetch is capped at its own quote."""
    saved = read_json(work_dir(cfg) / "quotes.json", {})
    if not saved:
        raise SystemExit("run `quote` first; nothing is downloaded without a stored quote")
    items = [q for q in saved["requests"] if q["planned"] and q["status"] == "quoted"]
    if splits:
        items = [q for q in items if set(q["splits"]) <= set(splits)]
    wanted = [q for q in items if not is_complete(raw_path(cfg, q))]
    total = float(sum(q["quoted_usd"] for q in wanted))
    if any(q["quoted_usd"] > MAX_QUOTE_PER_REQUEST for q in wanted):
        raise SystemExit("a single request is quoted above the per-request ceiling; inspect quotes.json")
    if total > approved_usd + 1e-9:
        raise SystemExit(f"quoted total ${total:.4f} for {len(wanted)} files exceeds the approved ${approved_usd:.4f}; nothing downloaded")
    client = client or _client()
    done = {"files": 0, "bytes": 0, "quoted_usd": 0.0, "errors": 0}
    for n, item in enumerate(wanted, 1):
        path = raw_path(cfg, item)
        try:
            record = fetch(client, path, max_cost=item["quoted_usd"] + 1e-6, quoted_cost=item["quoted_usd"], **item["request"])
        except CostRefused as exc:
            done["errors"] += 1
            log(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            done["errors"] += 1
            log(f"{item['id']}: {type(exc).__name__}: {str(exc)[:200]}")
            message = str(exc)
            if any(s in message for s in ("401", "403", "license", "permission", "429")):
                break
            continue
        done["files"] += 1
        done["bytes"] += int(record.get("bytes") or 0)
        done["quoted_usd"] += float(record.get("quoted_usd") or 0.0)
        if n % 50 == 0 or n == len(wanted):
            log(f"downloaded {n}/{len(wanted)} ({done['bytes'] / 1e6:.1f} MB, ${done['quoted_usd']:.4f})")
    approval = {"approved_usd": approved_usd, "approved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "splits": list(splits) if splits else ["train", "validate", "holdout"], "quoted_total_usd": total,
                "quotes_sha256": sha256_file(work_dir(cfg) / "quotes.json"), **done}
    approvals = read_json(work_dir(cfg) / "approvals.json", [])
    approvals.append(approval)
    write_json(work_dir(cfg) / "approvals.json", approvals)
    return approval


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("quote", help="price every planned request; download nothing")
    q.add_argument("--config", type=Path, default=None)
    d = sub.add_parser("download", help="fetch the planned requests within an approved amount")
    d.add_argument("--approved-usd", type=float, required=True)
    d.add_argument("--splits", nargs="*", default=None, help="restrict to requests whose events all fall in these splits")
    d.add_argument("--config", type=Path, default=None)
    b = sub.add_parser("build", help="H2/H3/H4 from local files; --publish writes the aggregate JSON beside the ledger")
    b.add_argument("--publish", action="store_true")
    b.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.command == "quote":
        rows = event_rows(cfg)
        items = requests_for(rows)
        print(f"events {len(rows)}; requests {len(items)} ({sum(i['planned'] for i in items)} planned)")
        out = quote_requests(cfg, items)
        print(json.dumps(out["summary"], indent=1))
        return 0
    if args.command == "download":
        print(json.dumps(download(cfg, approved_usd=args.approved_usd, splits=tuple(args.splits) if args.splits else None), indent=1))
        return 0
    from .execution_realism_build import run_build  # noqa: WPS433 - the analysis half of the workstream

    return run_build(cfg, publish=args.publish)


if __name__ == "__main__":
    raise SystemExit(main())
