"""The analysis half of workstream A (see ``execution_realism.py`` for the data
gate). Everything here reads local files only.

H4 reads the official opening (and closing) cross size from the venue
``statistics`` files already local. H18 and H19 read the free one-second
``ohlcv-1s`` session bars plus the opening and closing books the earlier quote
study cached for every event (arrival midpoint, spread, displayed queue ahead).
Events without a bar file or a cached book are counted as "no data", never
dropped silently.

The book-level models (``simulate_passive_offer`` on mbp-1 and
``participation_leg`` on prints) are kept, tested, as the reference design for
H2 and H3; they are not run, because those schemas are not free on this plan.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .analysis import cluster_interval
from .config import Config
from .databento_bars import is_complete
from .hypotheses import declared_before, load_registry, mark_measured
from .ledger import read_json, sha256_file, write_json
from .phase0_research import HOLDOUT_START, HOLDOUT_YEARS, RUN_ID, SPLITS, seal
from .split_detector import _symbol_spans

from . import execution_realism as er

F_LAST, F_BAD_TS, F_BAD_BOOK = 128, 8, 4
ACCOUNT_ORDERS = {"account_50k": er.ACCOUNT_EQUITY * er.POSITION_FRACTION,
                  "account_250k": 250_000.0 * er.POSITION_FRACTION,
                  "account_1m": 1_000_000.0 * er.POSITION_FRACTION}
PRIMARY_ORDER = "account_50k"
ARRIVAL_SEARCH_SECONDS = 60
EXIT_ARRIVAL_SEARCH_SECONDS = 300
CANCEL_MODELS = ("conservative", "pro_rata")     # the book-level reference model only
PRIMARY_CANCEL_MODEL = "conservative"
PRIMARY_FILL_MODEL = "bars"                      # what the published study runs
ALL_SPLITS = ("train", "validate", "holdout")
REPORTED_SPLITS = ALL_SPLITS + ("pooled_train_validate",)
BOOK_LABELS = {"open_1": "bbo-1s/open/1", "open_30": "bbo-1s/open/30", "close": "bbo-1s/close/-1"}


def _members(split: str) -> tuple[str, ...]:
    return ("train", "validate") if split == "pooled_train_validate" else (split,)


def _quarter(day: str) -> str:
    y, m = int(day[:4]), int(day[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def tick_size(price: float) -> float:
    return 0.01 if price >= 1.0 else 0.0001


def _mean(values):
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return float(sum(vals) / len(vals)) if vals else None


def _median(values):
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return None
    n = len(vals)
    return float((vals[(n - 1) // 2] + vals[n // 2]) / 2)


def _quantile(values, q):
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return None
    at = (len(vals) - 1) * q
    lo = math.floor(at)
    return float(vals[lo] + (vals[min(lo + 1, len(vals) - 1)] - vals[lo]) * (at - lo))


def _dist(values) -> dict:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return {"n": len(vals), "mean": _mean(vals), "median": _median(vals), "p10": _quantile(vals, .1),
            "p25": _quantile(vals, .25), "p75": _quantile(vals, .75), "p90": _quantile(vals, .9)}


def _share(rows: list[dict], field: str) -> dict:
    """Share of rows with a truthy field, with an issuer-clustered interval."""
    have = [{"issuer": r["issuer"], "flag": 1.0 if r.get(field) else 0.0} for r in rows if r.get(field) is not None]
    if not have:
        return {"events": 0, "share": None}
    return {"events": len(have), "issuers": len({r["issuer"] for r in have}),
            "share": float(sum(r["flag"] for r in have) / len(have)),
            "issuer_interval": cluster_interval(have, field="flag", cluster="issuer")}


# --- H4: the opening cross -------------------------------------------------------------

def statistics_crosses(cfg: Config, rows: list[dict], log=print) -> tuple[dict, list[dict]]:
    """Official opening and closing cross price and size per event from the listing venue's statistics file."""
    import databento as db
    import numpy as np
    import pandas as pd

    wanted = defaultdict(list)
    for r in rows:
        wanted[(r["dataset"], _quarter(r["entry_date"]))].append(r)
    out, files = {}, []
    for (dataset, label), group in sorted(wanted.items()):
        path = cfg.databento_dir / dataset / "statistics" / f"{label}.dbn.zst"
        if not is_complete(path) or not path.with_name(f"{label}.symbology.json").exists():
            log(f"{dataset} {label}: statistics file missing; {len(group)} events without a cross")
            continue
        files.append({"path": str(path.relative_to(cfg.local_dir).as_posix()), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        arr = db.DBNStore.from_file(str(path)).to_ndarray()
        arr = arr[np.isin(arr["stat_type"], [1, 11]) & (arr["update_action"] == 1)]
        spans = _symbol_spans(path)
        spans["d0"] = spans["d0"].astype(str)
        spans["d1"] = spans["d1"].astype(str)
        symbols = {r["symbol"] for r in group}
        sp = spans[spans["symbol"].isin(symbols)]
        sub = arr[np.isin(arr["instrument_id"], sp["instrument_id"].to_numpy())]
        if not len(sub):
            continue
        ts = pd.to_datetime(sub["ts_event"].astype("int64"), unit="ns", utc=True).tz_convert("America/New_York")
        f = pd.DataFrame({"instrument_id": sub["instrument_id"].astype("int64"),
                          "day": ts.normalize().tz_localize(None).strftime("%Y-%m-%d"),
                          "point": np.where(sub["stat_type"] == 1, "open", "close"),
                          "price": sub["price"].astype(np.float64) / 1e9, "quantity": sub["quantity"].astype("int64"),
                          "ts": sub["ts_event"].astype("int64")})
        f = f.merge(sp, on="instrument_id")
        f = f[(f["day"] >= f["d0"]) & (f["day"] < f["d1"])]
        f = f[(f["price"] > 0) & (f["price"] < 1e8)].sort_values("ts")
        for r in group:
            m = f[(f["symbol"] == r["symbol"]) & (f["day"] == r["entry_date"])]
            rec = {}
            for point in ("open", "close"):
                p = m[m["point"] == point]
                if p.empty:
                    continue
                last = p.iloc[-1]
                rec[f"{point}_cross_price"] = float(last["price"])
                rec[f"{point}_cross_shares"] = int(last["quantity"])
                rec[f"{point}_cross_rows"] = int(len(p))
                rec[f"{point}_cross_ts"] = int(last["ts"])
            out[r["key"]] = rec
    return out, files


def h4_rows(rows: list[dict], crosses: dict) -> list[dict]:
    out = []
    for r in rows:
        c = crosses.get(r["key"], {})
        row = {k: r[k] for k in ("key", "issuer", "entry_date", "year", "split", "ssr_state", "dataset", "open", "close", "adv_shares", "ret")}
        row["price_band"] = er.price_band(r["open"])
        row.update({k: v for k, v in c.items() if not k.endswith("_ts")})
        qty = c.get("open_cross_shares")
        row["cross_available"] = qty is not None and qty > 0
        row["cross_price_matches_official"] = (abs(c["open_cross_price"] - r["open"]) <= 1e-6) if c.get("open_cross_price") else None
        account = er.whole_shares(er.ACCOUNT_EQUITY * er.POSITION_FRACTION, r["open"])
        adv_cap = er.whole_shares(er.ADV_PARTICIPATION * r["adv_shares"], 1.0) if r.get("adv_shares") else None
        replay = min(account, adv_cap) if adv_cap is not None else None
        row["order_account_shares"] = account
        row["order_adv_cap_shares"] = adv_cap
        row["order_replay_shares"] = replay
        row["account_below_minimum_notional"] = bool(account * r["open"] < er.MINIMUM_NOTIONAL)
        row["replay_below_minimum_notional"] = bool(replay is not None and replay * r["open"] < er.MINIMUM_NOTIONAL)
        for name, shares in (("account", account), ("replay", replay)):
            if not row["cross_available"] or shares is None:
                row[f"{name}_order_to_cross"] = None
                row[f"{name}_feasible"] = None
                continue
            row[f"{name}_order_to_cross"] = shares / qty
            row[f"{name}_feasible"] = bool(shares >= 1 and shares <= er.CROSS_SHARE_CAP * qty)
        cq = c.get("close_cross_shares")
        row["close_cross_available"] = cq is not None and cq > 0
        row["account_close_feasible"] = bool(account >= 1 and account <= er.CROSS_SHARE_CAP * cq) if cq else None
        row["open_cross_usd"] = qty * c["open_cross_price"] if qty else None
        out.append(row)
    return out


def h4_results(rows: list[dict]) -> dict:
    def block(subset):
        with_cross = [r for r in subset if r["cross_available"]]
        out = {"events": len(subset), "events_with_cross": len(with_cross),
               "cross_price_equals_official_open": sum(1 for r in with_cross if r["cross_price_matches_official"]),
               "open_cross_usd": _dist(r["open_cross_usd"] for r in with_cross),
               "open_cross_shares": _dist(r["open_cross_shares"] for r in with_cross)}
        for name in ("account", "replay"):
            have = [r for r in with_cross if r[f"{name}_feasible"] is not None]
            out[name] = {"feasible": _share(have, f"{name}_feasible"),
                         "order_to_cross": _dist(r[f"{name}_order_to_cross"] for r in have),
                         "order_shares": _dist(r[f"order_{name}_shares"] for r in have),
                         "below_minimum_notional": sum(1 for r in subset if r[f"{name}_below_minimum_notional"])}
            if name == "account":
                out[name]["feasible_and_at_least_minimum_notional"] = _share(
                    [{**r, "both": r["account_feasible"] and not r["account_below_minimum_notional"]} for r in have], "both")
        out["account_close_cross_feasible"] = _share([r for r in subset if r["account_close_feasible"] is not None], "account_close_feasible")
        return out

    by_split = {}
    for split in REPORTED_SPLITS:
        subset = [r for r in rows if r["split"] in _members(split)]
        by_split[split] = {"all": block(subset)}
        for state in ("restricted", "unrestricted"):
            by_split[split][state] = block([r for r in subset if r["ssr_state"] == state])
    by_year = {y: block([r for r in rows if r["year"] == y]) for y in sorted({r["year"] for r in rows})}
    by_band = {}
    for band in [b[2] for b in er.PRICE_BANDS]:
        sub = [r for r in rows if r["price_band"] == band and r["split"] in ("train", "validate")]
        if sub:
            by_band[band] = block(sub)
    by_venue = {}
    for ds in sorted({r["dataset"] for r in rows}):
        sub = [r for r in rows if r["dataset"] == ds and r["split"] in ("train", "validate")]
        by_venue[ds] = block(sub)
    return {"definition": ("Official opening cross on the listing venue (statistics stat_type 1: price and matched shares). "
                           f"An order is feasible when it is at least one whole share and at most {er.CROSS_SHARE_CAP:.0%} of the cross. "
                           f"account: {er.POSITION_FRACTION:.1%} of a ${er.ACCOUNT_EQUITY:,.0f} account in whole shares at the official open. "
                           f"replay: the account order capped at {er.ADV_PARTICIPATION:.1%} of the prior {er.PRIOR_ADV_SESSIONS}-session "
                           "split-adjusted venue ADV, the frozen replay's sizing. The closing cross is read the same way for the cover."),
            "by_split": by_split, "by_year": by_year, "by_price_band_train_validate": by_band, "by_venue_train_validate": by_venue}


# --- local market data: free bars and the cached books --------------------------------------

def _window_items(cfg: Config, rows: list[dict]) -> dict:
    """Planned bar requests keyed by (event key, schema, window)."""
    by_group = {}
    for item in er.requests_for(rows):
        if item["planned"]:
            by_group[(item["request"]["dataset"], item["date"], item["schema"], item["window"])] = item
    out = {}
    for r in rows:
        item = by_group.get((r["dataset"], r["entry_date"], er.FREE_SCHEMA, "session"))
        if item:
            out[(r["key"], er.FREE_SCHEMA, "session")] = item
    return out


KEEP_COLUMNS = {"mbp-1": ["symbol", "action", "side", "price", "size", "flags", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"],
                "trades": ["symbol", "side", "price", "size"],
                "ohlcv-1s": ["symbol", "open", "high", "low", "close", "volume"]}


class WindowCache:
    """Decoded DBN windows, pruned to the columns the models read. A file holds every
    event of one venue-session, so events are processed in venue-session order and
    only the current session's files stay decoded."""

    def __init__(self, cfg: Config, keep: int = 3):
        self.cfg = cfg
        self.keep = keep
        self.frames: dict[str, object] = {}
        self.files: dict[str, dict] = {}
        self.cost_usd = 0.0

    def frame(self, item: dict):
        import databento as db

        path = er.raw_path(self.cfg, item)
        if item["id"] in self.frames:
            return self.frames[item["id"]]
        if not is_complete(path):
            return None
        ok = read_json(path.with_name(path.name.replace(".dbn.zst", ".ok.json")), {})
        if item["id"] not in self.files:
            self.files[item["id"]] = {"path": str(path.relative_to(self.cfg.local_dir).as_posix()), "bytes": path.stat().st_size,
                                      "quoted_usd": float(ok.get("quoted_usd") or 0.0), "sha256": sha256_file(path)}
            self.cost_usd += float(ok.get("quoted_usd") or 0.0)
        if path.stat().st_size == 0:
            frame = None
        else:
            frame = db.DBNStore.from_file(str(path)).to_df(pretty_ts=False)
            cols = [c for c in KEEP_COLUMNS[item["request"]["schema"]] if c in frame.columns]
            frame = frame[cols]
        while len(self.frames) >= self.keep:
            self.frames.pop(next(iter(self.frames)))
        self.frames[item["id"]] = frame
        return frame


def cached_books(cfg: Config) -> tuple[dict, dict | None]:
    """The opening (1 s and 30 s) and closing (-1 s) listing-venue books the quote study
    cached per event: bid, ask, mid, displayed sizes and the record's timestamp."""
    path = cfg.local_dir / "execution_research" / er.QUOTE_STUDY / "observations.local.json"
    if not path.exists():
        return {}, None
    obs = read_json(path, {})
    out = {}
    for key, labels in obs.items():
        out[key] = {name: ((labels.get(label) or {}).get("book")) for name, label in BOOK_LABELS.items()}
    return out, {"path": f"execution_research/{er.QUOTE_STUDY}/observations.local.json", "sha256": sha256_file(path), "events": len(out)}


def _bar_arrays(frame, symbol: str) -> dict | None:
    """Numpy columns for one symbol from a one-second bar frame, in time order."""
    if frame is None or frame.empty:
        return None
    f = frame[frame["symbol"] == symbol] if "symbol" in frame.columns else frame
    if f.empty:
        return None
    f = f.sort_index(kind="stable")
    return {"ts": f.index.to_numpy(dtype="int64"), "open": f["open"].to_numpy(dtype=float), "high": f["high"].to_numpy(dtype=float),
            "low": f["low"].to_numpy(dtype=float), "close": f["close"].to_numpy(dtype=float), "volume": f["volume"].to_numpy(dtype=float)}


def _book_arrays(frame, symbol: str) -> dict | None:
    """Numpy columns for one symbol from an mbp-1 frame (book-level reference model)."""
    if frame is None or frame.empty:
        return None
    f = frame[frame["symbol"] == symbol] if "symbol" in frame.columns else frame
    if f.empty:
        return None
    f = f.sort_index(kind="stable")
    ts = f.index.to_numpy(dtype="int64")
    return {"ts": ts, "action": f["action"].astype(str).to_numpy(), "side": f["side"].astype(str).to_numpy(),
            "price": f["price"].to_numpy(dtype=float), "size": f["size"].to_numpy(dtype="int64"),
            "flags": f["flags"].to_numpy(dtype="int64"),
            "bid": f["bid_px_00"].to_numpy(dtype=float), "ask": f["ask_px_00"].to_numpy(dtype=float),
            "bid_sz": f["bid_sz_00"].to_numpy(dtype="int64"), "ask_sz": f["ask_sz_00"].to_numpy(dtype="int64")}


AUCTION_GUARD_NS = 2 * 10**9


def _print_arrays(frame, symbol: str, *, opened_ns: int | None = None, closed_ns: int | None = None, cross: dict | None = None) -> dict | None:
    """Continuous prints from a trades frame (book-level reference model). The official opening
    and closing crosses are removed by matching their printed price and matched shares, with a
    two-second guard around the scheduled open and close for unsided prints as a backstop."""
    import numpy as np

    if frame is None or frame.empty:
        return None
    f = frame[frame["symbol"] == symbol] if "symbol" in frame.columns else frame
    if f.empty:
        return None
    f = f.sort_index(kind="stable")
    ts = f.index.to_numpy(dtype="int64")
    side = f["side"].astype(str).to_numpy()
    price = f["price"].to_numpy(dtype=float)
    size = f["size"].to_numpy(dtype="int64")
    unsided = side == "N"
    drop = np.zeros(len(ts), dtype=bool)
    for point in ("open", "close"):
        cp, cq = (cross or {}).get(f"{point}_cross_price"), (cross or {}).get(f"{point}_cross_shares")
        if cp and cq:
            drop |= unsided & (np.abs(price - cp) <= 1e-9) & (size == cq)
    for boundary in (opened_ns, closed_ns):
        if boundary is not None:
            drop |= unsided & (np.abs(ts - boundary) <= AUCTION_GUARD_NS)
    keep = ~drop
    if not keep.any():
        return None
    return {"ts": ts[keep], "price": price[keep], "size": size[keep], "side": side[keep], "crosses_removed": int(drop.sum())}


def valid_book_mask(book: dict):
    import numpy as np

    b = book
    return ((b["flags"] & F_LAST) != 0) & ((b["flags"] & (F_BAD_TS | F_BAD_BOOK)) == 0) & np.isfinite(b["bid"]) & np.isfinite(b["ask"]) \
        & (b["bid"] > 0) & (b["ask"] > 0) & (b["ask"] > b["bid"]) & (b["bid_sz"] > 0) & (b["ask_sz"] > 0)


def book_at(book: dict, valid, t_ns: int):
    """Index of the last valid book record at or before ``t_ns``, or None."""
    import numpy as np

    j = int(np.searchsorted(book["ts"], t_ns, side="right")) - 1
    while j >= 0 and not valid[j]:
        j -= 1
    return j if j >= 0 else None


def arrival(book: dict, valid, t0_ns: int, search_ns: int):
    """First valid book at or after t0 within the search window."""
    import numpy as np

    j = int(np.searchsorted(book["ts"], t0_ns, side="left"))
    while j < len(book["ts"]) and book["ts"][j] <= t0_ns + search_ns:
        if valid[j]:
            return j
        j += 1
    return None


# --- the passive offer under Rule 201 -------------------------------------------------------

def simulate_passive_offer(book: dict, t0_ns: int, shares: int, *, horizon_ns: int, cancel_model: str = PRIMARY_CANCEL_MODEL,
                           ssr: bool = True, search_ns: int = ARRIVAL_SEARCH_SECONDS * 10**9) -> dict:
    """Book-level reference model (mbp-1): rest ``shares`` at the venue best offer from the
    first valid book at or after ``t0``.

    Fills come only from buyer-initiated prints (a tagged buy aggressor, or an unsided
    print at or through the displayed ask) at or above our price after the
    displayed queue ahead of us is consumed (price-time priority; cancellations are
    assumed behind us under ``conservative`` and proportional under ``pro_rata``;
    the displayed size at our price is an upper bound on the queue ahead either way).
    Under SSR the order may never rest at or below the bid: when the bid reaches our
    price it is re-priced to the best offer (or one tick above the bid) and joins the
    back of that queue, as the exchanges' re-pricing does.
    """
    valid = valid_book_mask(book)
    i0 = arrival(book, valid, t0_ns, search_ns)
    if i0 is None:
        return {"status": "no_valid_book_at_arrival"}
    if shares <= 0:
        return {"status": "order_below_one_share"}
    ts = book["ts"]
    placed = int(ts[i0])
    arrival_bid, arrival_ask = float(book["bid"][i0]), float(book["ask"][i0])
    arrival_mid = (arrival_bid + arrival_ask) / 2
    P = arrival_ask
    ahead = int(book["ask_sz"][i0])
    remaining = shares
    filled_value = 0.0
    fills = 0
    repriced = 0
    completed = None
    deadline = placed + horizon_ns
    prev_level_size = ahead          # displayed size at our price on the last valid book (None while not at the top)
    unexplained_traded = 0           # shares traded at our price whose removal the displayed size has not yet shown
    eps = 1e-9
    n = len(ts)
    j = i0 + 1
    buyer_volume_at_or_above = 0
    while j < n and ts[j] <= deadline and remaining > 0:
        action, side, price, size = book["action"][j], book["side"][j], float(book["price"][j]), int(book["size"][j])
        if action == "T" and side == "N":
            # No aggressor side (Pillar prints, ITCH hidden executions): a print at or through
            # the displayed ask took the offer; a print inside the spread or at the bid did not.
            ask_now = float(book["ask"][j])
            side = "B" if ask_now > 0 and price >= ask_now - eps else "A"
        if action == "T" and side == "B" and price >= P - eps and size > 0:
            buyer_volume_at_or_above += size
            take = min(size, ahead)
            ahead -= take
            if abs(price - P) <= eps:
                unexplained_traded += size
            rem = size - take
            if rem > 0:
                fill = min(rem, remaining)
                remaining -= fill
                filled_value += fill * P
                fills += 1
                if remaining == 0:
                    completed = int(ts[j])
                    break
        if valid[j]:
            bid, ask, ask_sz = float(book["bid"][j]), float(book["ask"][j]), int(book["ask_sz"][j])
            if ssr and bid >= P - eps:
                # Our offer would now sit at or below the bid: slide to the best offer, back of the queue.
                P = max(ask, bid + tick_size(bid))
                ahead = ask_sz if abs(ask - P) <= eps else 0
                prev_level_size = ahead
                unexplained_traded = 0
                repriced += 1
            elif abs(ask - P) <= eps:
                if prev_level_size is not None and ask_sz < prev_level_size:
                    decrease = prev_level_size - ask_sz
                    explained = min(decrease, unexplained_traded)
                    unexplained_traded -= explained
                    cancelled = decrease - explained
                    if cancel_model == "pro_rata" and cancelled > 0 and prev_level_size > 0:
                        ahead -= int(round(cancelled * ahead / prev_level_size))
                ahead = max(0, min(ahead, ask_sz))
                prev_level_size = ask_sz
            elif ask > P + eps:
                ahead = 0
                prev_level_size = 0
                unexplained_traded = 0
            else:
                prev_level_size = None
        j += 1
    filled = shares - remaining
    out = {"status": "simulated", "model": "mbp-1", "placed_at": placed, "arrival_mid": arrival_mid, "arrival_bid": arrival_bid,
           "arrival_ask": arrival_ask, "arrival_half_spread": (arrival_ask - arrival_bid) / 2 / arrival_mid, "initial_offer": arrival_ask,
           "final_offer": P, "shares": shares, "filled_shares": int(filled), "fill_fraction": filled / shares, "fully_filled": remaining == 0,
           "fill_vwap": filled_value / filled if filled else None, "fills": fills, "repriced": repriced,
           "completed_at": completed, "time_to_fill_seconds": (completed - placed) / 1e9 if completed else None,
           "buyer_volume_at_or_above_offer": int(buyer_volume_at_or_above)}

    def mid_at(t):
        k = book_at(book, valid, t)
        return (float(book["bid"][k]) + float(book["ask"][k])) / 2 if k is not None else None

    if completed:
        for tau in er.MARKOUT_SECONDS:
            m = mid_at(completed + tau * 10**9) if ts[-1] >= completed + tau * 10**9 else None
            out[f"markout_{tau}s"] = (m - out["fill_vwap"]) / arrival_mid if m is not None else None
            out[f"mid_change_from_arrival_{tau}s"] = (m - arrival_mid) / arrival_mid if m is not None else None
        out["improvement_vs_arrival_mid"] = (out["fill_vwap"] - arrival_mid) / arrival_mid
    else:
        m = mid_at(deadline) if ts[-1] >= deadline else None
        out["unfilled_drift"] = (m - arrival_mid) / arrival_mid if m is not None else None
    return out


def ticks_at_or_above(low: float, high: float, price: float, tick: float) -> float:
    """Share of a bar's volume attributed to prices at or above ``price`` when the volume is
    spread evenly over the bar's tick prices from low to high inclusive."""
    eps = tick * 1e-6
    if high < price - eps:
        return 0.0
    if low >= price - eps:
        return 1.0
    total = int(round((high - low) / tick)) + 1
    above = int(round((high - price) / tick)) + 1
    return max(0.0, min(1.0, above / total))


def bar_close_at(bars: dict, t_ns: int):
    """Close of the last bar that starts at or before ``t_ns``."""
    import numpy as np

    j = int(np.searchsorted(bars["ts"], t_ns, side="right")) - 1
    return float(bars["close"][j]) if j >= 0 else None


def simulate_passive_offer_bars(bars: dict, book: dict, placed_ns: int, shares: int, *, horizon_ns: int) -> dict:
    """Bar fill model (H18): rest ``shares`` at the cached venue best offer behind that level's
    displayed size. Each later second's volume is spread evenly over the bar's tick prices;
    the part at or above the offer depletes the queue ahead, then fills the order at the
    offer price. No cancellations are credited and no re-pricing is modeled, so the fill
    rate is an upper bound relative to the book-level model and the fill price a lower one.
    """
    bid, ask = float(book["bid"]), float(book["ask"])
    if not (bid > 0 and ask > bid):
        return {"status": "invalid_arrival_book"}
    if shares <= 0:
        return {"status": "order_below_one_share"}
    arrival_mid = (bid + ask) / 2
    P = ask
    ahead = float(book.get("ask_size") or 0)
    tick = tick_size(P)
    deadline = placed_ns + horizon_ns
    remaining = float(shares)
    cum = 0.0
    fills = 0
    completed = None
    market_above = False
    ts = bars["ts"]
    for j in range(len(ts)):
        t = int(ts[j])
        if t < placed_ns:
            continue
        if t > deadline:
            break
        frac = ticks_at_or_above(float(bars["low"][j]), float(bars["high"][j]), P, tick)
        v = float(bars["volume"][j]) * frac
        if v <= 0:
            continue
        cum += v
        take = min(v, ahead)
        ahead -= take
        rem = v - take
        if rem > 0 and remaining > 0:
            fill = min(rem, remaining)
            remaining -= fill
            fills += 1
            if float(bars["low"][j]) > P + tick * 1e-6:
                market_above = True
            if remaining <= 1e-9:
                remaining = 0.0
                completed = t + 10**9     # the end of that second
                break
    filled = shares - remaining
    out = {"status": "simulated", "model": "bars", "placed_at": placed_ns, "arrival_mid": arrival_mid, "arrival_bid": bid, "arrival_ask": ask,
           "arrival_half_spread": (ask - bid) / 2 / arrival_mid, "initial_offer": P, "final_offer": P, "queue_ahead_shares": float(book.get("ask_size") or 0),
           "shares": shares, "filled_shares": int(round(filled)), "fill_fraction": filled / shares, "fully_filled": completed is not None,
           "fill_vwap": P if filled > 0 else None, "fills": fills, "repriced": 0,
           "completed_at": completed, "time_to_fill_seconds": (completed - placed_ns) / 1e9 if completed else None,
           "buyer_volume_at_or_above_offer": cum, "fills_with_market_above_offer": market_above}
    if completed:
        for tau in er.MARKOUT_SECONDS:
            m = bar_close_at(bars, completed + tau * 10**9) if ts[-1] >= completed else None
            out[f"markout_{tau}s"] = (m - P) / arrival_mid if m is not None else None
            out[f"mid_change_from_arrival_{tau}s"] = (m - arrival_mid) / arrival_mid if m is not None else None
        out["improvement_vs_arrival_mid"] = (P - arrival_mid) / arrival_mid
    else:
        m = bar_close_at(bars, deadline)
        out["unfilled_drift"] = (m - arrival_mid) / arrival_mid if m is not None else None
    return out


def _h2_event(r: dict, bars: dict | None, books: dict | None, frame_missing: bool) -> dict:
    row = {k: r[k] for k in ("key", "issuer", "entry_date", "year", "split", "ssr_state", "dataset", "open", "close", "adv_shares", "ret")}
    row["price_band"] = er.price_band(r["open"])
    if bars is None:
        row["status"] = "no_window" if frame_missing else "symbol_absent_from_window"
        return row
    book, offset = None, None
    for name, off in (("open_1", 1), ("open_30", 30)):
        b = (books or {}).get(name)
        if b and b.get("bid") and b.get("ask") and b["ask"] > b["bid"]:
            book, offset = b, off
            break
    if book is None:
        row["status"] = "no_arrival_book"
        return row
    placed = int(datetime.fromisoformat(book["timestamp"]).timestamp() * 1e9)
    row["status"] = "simulated"
    row["placement_offset_seconds"] = offset
    mid = book["mid"]
    orders = {name: er.whole_shares(dollars, mid) for name, dollars in ACCOUNT_ORDERS.items()}
    adv_cap = er.whole_shares(er.ADV_PARTICIPATION * r["adv_shares"], 1.0) if r.get("adv_shares") else None
    orders["replay"] = min(orders[PRIMARY_ORDER], adv_cap) if adv_cap is not None else 0
    row["orders"] = orders
    row["sims"] = {f"{name}/{PRIMARY_FILL_MODEL}": simulate_passive_offer_bars(bars, book, placed, shares, horizon_ns=er.PASSIVE_WINDOW_SECONDS * 10**9)
                   for name, shares in orders.items()}
    return row


def h2_results(rows: list[dict]) -> dict:
    primary = f"{PRIMARY_ORDER}/{PRIMARY_FILL_MODEL}"

    def block(subset, sim_key):
        sims = [(r, r["sims"][sim_key]) for r in subset if r.get("sims") and sim_key in r["sims"]]
        simulated = [(r, s) for r, s in sims if s["status"] == "simulated"]
        reasons = Counter()
        for r in subset:
            if r.get("status") != "simulated":
                reasons[r.get("status") or "unknown"] += 1
            else:
                s = r["sims"].get(sim_key)
                if not s or s["status"] != "simulated":
                    reasons[(s or {}).get("status") or "order_not_simulated"] += 1
        filled = [(r, s) for r, s in simulated if s["fully_filled"]]
        flag_rows = [{"issuer": r["issuer"], "filled": s["fully_filled"]} for r, s in simulated]
        as_rows = [{"issuer": r["issuer"], "as": s.get(f"markout_{er.ADVERSE_SELECTION_HORIZON}s")} for r, s in filled
                   if s.get(f"markout_{er.ADVERSE_SELECTION_HORIZON}s") is not None]
        out = {"events": len(subset), "simulated": len(simulated), "not_simulated": dict(reasons),
               "issuers": len({r["issuer"] for r, _ in simulated}),
               "fill_rate": _share(flag_rows, "filled"),
               "fill_fraction_mean": _mean(s["fill_fraction"] for _, s in simulated),
               "partially_filled": sum(1 for _, s in simulated if 0 < s["fill_fraction"] < 1),
               "repriced_under_ssr": sum(1 for _, s in simulated if s["repriced"]),
               "fills_with_market_above_offer": sum(1 for _, s in filled if s.get("fills_with_market_above_offer")),
               "placed_at_30s": sum(1 for r, _ in simulated if r.get("placement_offset_seconds") == 30),
               "order_shares": _dist(s["shares"] for _, s in simulated),
               "queue_ahead_shares": _dist(s.get("queue_ahead_shares") for _, s in simulated),
               "arrival_half_spread": _dist(s["arrival_half_spread"] for _, s in simulated),
               "time_to_fill_seconds": _dist(s["time_to_fill_seconds"] for _, s in filled),
               "improvement_vs_arrival_mid": _dist(s.get("improvement_vs_arrival_mid") for _, s in filled),
               "adverse_selection_5m": {"definition": "last bar close five minutes after the fill minus the fill price, over the arrival midpoint; positive is adverse to the short",
                                        **_dist(r["as"] for r in as_rows),
                                        "issuer_interval": cluster_interval(as_rows, field="as", cluster="issuer") if as_rows else None},
               "markouts": {f"{tau}s": _dist(s.get(f"markout_{tau}s") for _, s in filled) for tau in er.MARKOUT_SECONDS},
               "unfilled_drift_to_deadline": _dist(s.get("unfilled_drift") for _, s in simulated if not s["fully_filled"]),
               "realized_short_return_fill_to_official_close": _dist((s["fill_vwap"] - r["close"]) / s["fill_vwap"] for r, s in filled)}
        return out

    sim_keys = sorted({k for r in rows if r.get("sims") for k in r["sims"]})
    by_state = {}
    for state in ("restricted", "unrestricted"):
        sub_state = [r for r in rows if r["ssr_state"] == state]
        by_state[state] = {"by_split": {split: {k: block([r for r in sub_state if r["split"] in _members(split)], k) for k in sim_keys}
                                        for split in REPORTED_SPLITS},
                           "by_year": {y: block([r for r in sub_state if r["year"] == y], primary) for y in sorted({r["year"] for r in sub_state})},
                           "by_price_band_train_validate": {band: block([r for r in sub_state if r["price_band"] == band and r["split"] in ("train", "validate")], primary)
                                                            for band in [b[2] for b in er.PRICE_BANDS]}}
    return {"definition": ("Restricted sessions (cached Nasdaq SSR state at the entry open): a short-sale offer of the modeled size rests at the "
                           "listing-venue best offer of the cached book one second after the scheduled open (thirty seconds when the one-second "
                           f"book is missing), behind that level's displayed size, judged within {er.PASSIVE_WINDOW_SECONDS // 60} minutes. Each later "
                           "one-second bar's volume is spread evenly over its tick prices; the part at or above the offer depletes the queue ahead and "
                           "then fills the order at the offer price. Unrestricted sessions are run the same way as a comparison only."),
            "primary": primary, "orders": {k: f"{v:,.0f} USD at the arrival midpoint, whole shares" for k, v in ACCOUNT_ORDERS.items()} | {"replay": "the $50k order capped at 0.1% of prior ADV"},
            "fill_models": {"bars": "one-second bars; no cancellations credited, no re-pricing; fills at or above the offer count (upper bound on the fill rate)"},
            "by_ssr_state": by_state}


# --- participation over time ------------------------------------------------------------------

def participation_leg(prints: dict | None, book: dict | None, t_start: int, t_end: int, rate: float, *,
                      order_shares: float | None, arrival_mid: float) -> dict:
    """Book-level reference model: take ``rate`` of every continuous print in [t_start, t_end]
    until ``order_shares`` are done. Fill prices are the print prices; the volume-weighted
    half-spread at the fill times (from the last valid book at or before each print) is the
    spread-crossing cost."""
    import numpy as np

    if prints is None:
        return {"status": "no_prints", "taken_shares": 0.0}
    m = (prints["ts"] >= t_start) & (prints["ts"] <= t_end)
    ts, px, sz = prints["ts"][m], prints["price"][m], prints["size"][m].astype(float)
    if not len(ts):
        return {"status": "no_prints_in_window", "taken_shares": 0.0, "window_volume": 0.0}
    take = rate * sz
    cum = np.cumsum(take)
    if order_shares is not None and order_shares > 0:
        k = int(np.searchsorted(cum, order_shares, side="left"))
        if k < len(cum):
            take = take[:k + 1].copy()
            take[-1] -= cum[k] - order_shares
            ts, px = ts[:k + 1], px[:k + 1]
            completed_at = int(ts[-1])
        else:
            completed_at = None
    else:
        completed_at = int(ts[-1])
    taken = float(take.sum())
    vwap = float((take * px).sum() / taken) if taken > 0 else None
    hs = None
    crossed = None
    if book is not None and taken > 0:
        valid = valid_book_mask(book)
        vts = book["ts"][valid]
        vbid, vask = book["bid"][valid], book["ask"][valid]
        idx = np.searchsorted(vts, ts, side="right") - 1
        ok = idx >= 0
        half = np.where(ok, (vask[np.maximum(idx, 0)] - vbid[np.maximum(idx, 0)]) / 2, 0.0)
        hs = float((take * half).sum() / taken / arrival_mid)
        crossed = float(take[ok].sum() / taken)
    return {"status": "priced", "window_volume": float(sz.sum()), "prints": int(len(sz)), "taken_shares": taken, "vwap": vwap,
            "half_spread_vw": hs, "fills_with_book": crossed, "completed": completed_at is not None, "completed_at": completed_at,
            "time_to_complete_seconds": (completed_at - t_start) / 1e9 if completed_at else None,
            "residual_shares": max(0.0, (order_shares or taken) - taken)}


def remove_cross(bars: dict, cross_price, cross_shares, after_ns: int) -> tuple[object, bool]:
    """Volume per bar with the official cross print removed from the first bar at or after
    ``after_ns`` whose range contains the cross price and that is large enough to hold it."""

    vol = bars["volume"].astype(float).copy()
    if not cross_price or not cross_shares:
        return vol, False
    for j in range(len(vol)):
        if bars["ts"][j] < after_ns:
            continue
        if bars["ts"][j] > after_ns + 15 * 60 * 10**9:
            break
        if bars["low"][j] - 1e-9 <= cross_price <= bars["high"][j] + 1e-9 and vol[j] >= 0.5 * cross_shares:
            vol[j] = max(0.0, vol[j] - cross_shares)
            return vol, True
    return vol, False


def participation_leg_bars(bars: dict, volume, t_start: int, t_end: int, rate: float, *, order_shares: float | None) -> dict:
    """Bar model (H19): take ``rate`` of every one-second bar's volume in [t_start, t_end] at
    the bar's range midpoint until ``order_shares`` are done."""
    import numpy as np

    m = (bars["ts"] >= t_start) & (bars["ts"] <= t_end) & (volume > 0)
    ts, vol = bars["ts"][m], volume[m]
    px = (bars["high"][m] + bars["low"][m]) / 2
    if not len(ts):
        return {"status": "no_bars_in_window", "taken_shares": 0.0, "window_volume": 0.0}
    take = rate * vol
    cum = np.cumsum(take)
    if order_shares is not None and order_shares > 0:
        k = int(np.searchsorted(cum, order_shares, side="left"))
        if k < len(cum):
            take = take[:k + 1].copy()
            take[-1] -= cum[k] - order_shares
            ts, px = ts[:k + 1], px[:k + 1]
            completed_at = int(ts[-1]) + 10**9
        else:
            completed_at = None
    else:
        completed_at = int(ts[-1]) + 10**9
    taken = float(take.sum())
    return {"status": "priced", "window_volume": float(vol.sum()), "bars": int(len(vol)), "taken_shares": taken,
            "vwap": float((take * px).sum() / taken) if taken > 0 else None,
            "completed": completed_at is not None, "completed_at": completed_at,
            "time_to_complete_seconds": (completed_at - t_start) / 1e9 if completed_at else None,
            "residual_shares": max(0.0, (order_shares or taken) - taken)}


def _half_spread(book: dict | None, over: float) -> float | None:
    if not book or not book.get("bid") or not book.get("ask") or book["ask"] <= book["bid"] or not over:
        return None
    return (book["ask"] - book["bid"]) / 2 / over


def _h3_event(r: dict, bars: dict | None, books: dict | None, cross: dict, frame_missing: bool) -> dict:
    row = {k: r[k] for k in ("key", "issuer", "entry_date", "year", "split", "ssr_state", "dataset", "open", "close", "adv_shares", "ret")}
    row["price_band"] = er.price_band(r["open"])
    if bars is None:
        row["status"] = "no_window" if frame_missing else "symbol_absent_from_window"
        return row
    books = books or {}
    arrival_book = next((books.get(n) for n in ("open_1", "open_30") if books.get(n) and books[n].get("ask", 0) > books[n].get("bid", 0) > 0), None)
    if arrival_book is None:
        row["status"] = "no_arrival_book"
        return row
    m0 = arrival_book["mid"]
    opened = int(datetime.fromisoformat(r["opened"]).timestamp() * 1e9)
    closed = int(datetime.fromisoformat(r["closed"]).timestamp() * 1e9)
    placed = int(datetime.fromisoformat(arrival_book["timestamp"]).timestamp() * 1e9)
    entry_end = opened + er.ENTRY_WINDOW_SECONDS * 10**9
    x_start, x_end = closed - er.EXIT_WINDOW_SECONDS * 10**9, closed - 1
    import numpy as np

    k = int(np.searchsorted(bars["ts"], x_start, side="left"))
    if k >= len(bars["ts"]) or bars["ts"][k] > x_start + EXIT_ARRIVAL_SEARCH_SECONDS * 10**9:
        row["status"] = "no_exit_arrival_bar"
        return row
    m1 = (float(bars["high"][k]) + float(bars["low"][k])) / 2
    volume, cross_removed = remove_cross(bars, cross.get("open_cross_price"), cross.get("open_cross_shares"), opened)
    close_px = cross.get("close_cross_price") or r["close"]
    hs_open = [h for h in (_half_spread(books.get("open_1"), m0), _half_spread(books.get("open_30"), m0)) if h is not None]
    hs_entry = float(sum(hs_open) / len(hs_open))
    hs_close = _half_spread(books.get("close"), m0)
    row.update(status="priced", arrival_mid=m0, exit_arrival_mid=m1, official_close=close_px, cross_removed_from_bars=cross_removed,
               exit_arrival_offset_seconds=(int(bars["ts"][k]) - x_start) / 1e9,
               entry_half_spread=hs_entry, exit_half_spread=hs_close if hs_close is not None else hs_entry,
               exit_spread_from="close_book" if hs_close is not None else "open_books",
               first_hour_volume=float(volume[(bars["ts"] >= opened) & (bars["ts"] <= entry_end)].sum()),
               session_volume=float(volume.sum()),
               timing_open_vs_arrival=(r["open"] - m0) / m0, timing_exit_mid_vs_close=(m1 - close_px) / m0)
    row["legs"] = {}
    for rate in er.PARTICIPATION_RATES:
        specs = {"capacity": None}
        specs.update({name: er.whole_shares(dollars, m0) for name, dollars in ACCOUNT_ORDERS.items()})
        for name, order in specs.items():
            entry = participation_leg_bars(bars, volume, placed, entry_end, rate, order_shares=order)
            if entry["status"] != "priced" or entry["taken_shares"] <= 0:
                row["legs"][f"{name}/{rate}"] = {"status": entry.get("status", "no_fill"), "entry": entry}
                continue
            position = entry["taken_shares"]
            exit_ = participation_leg_bars(bars, volume, x_start, x_end, rate, order_shares=position)
            exit_taken = exit_.get("taken_shares") or 0.0
            residual = position - exit_taken
            buy_vwap = (((exit_.get("vwap") or 0.0) * exit_taken) + residual * close_px) / position
            leg = {"status": "priced", "entry": entry, "exit": exit_, "position_shares": position, "position_usd": position * entry["vwap"],
                   "residual_at_close_share": residual / position,
                   "entry_shortfall": (m0 - entry["vwap"]) / m0, "exit_shortfall": (buy_vwap - m1) / m0,
                   "entry_half_spread": row["entry_half_spread"],
                   "exit_half_spread": row["exit_half_spread"] * (exit_taken / position),
                   "realized_gross_short_return": (entry["vwap"] - buy_vwap) / entry["vwap"]}
            for c in er.CROSSING_FRACTIONS:
                spread = c * (leg["entry_half_spread"] + leg["exit_half_spread"])
                leg[f"round_trip_cost_c{c}"] = leg["entry_shortfall"] + leg["exit_shortfall"] + spread
                leg[f"realized_short_return_c{c}"] = leg["realized_gross_short_return"] - spread
            row["legs"][f"{name}/{rate}"] = leg
    return row


def window_rows(cfg: Config, rows: list[dict], items: dict, cache: WindowCache, crosses: dict, books: dict, log=print) -> tuple[list[dict], list[dict]]:
    """One pass over the events in venue-session order: each session's bar file is decoded once."""
    h2, h3 = [], []
    ordered = sorted(rows, key=lambda r: (r["dataset"], r["entry_date"], r["key"]))
    for n, r in enumerate(ordered, 1):
        item = items.get((r["key"], er.FREE_SCHEMA, "session"))
        frame = cache.frame(item) if item else None
        bars = _bar_arrays(frame, r["symbol"]) if frame is not None else None
        event_books = books.get(r["key"])
        h2.append(_h2_event(r, bars, event_books, frame is None))
        h3.append(_h3_event(r, bars, event_books, crosses.get(r["key"], {}), frame is None))
        if n % 50 == 0:
            log(f"windows: {n}/{len(ordered)} events ({sum(1 for x in h2 if x.get('status') == 'simulated')} simulated, "
                f"{sum(1 for x in h3 if x.get('status') == 'priced')} priced)")
    return h2, h3


def h3_results(rows: list[dict]) -> dict:
    primary_c = er.CROSSING_FRACTIONS[0]

    def block(subset, leg_key):
        priced = [(r, r["legs"][leg_key]) for r in subset if r.get("legs") and r["legs"].get(leg_key, {}).get("status") == "priced"]
        reasons = Counter(r.get("status") if r.get("status") != "priced" else (r["legs"].get(leg_key) or {}).get("status", "missing") for r in subset)
        reasons.pop("priced", None)
        cost_rows = [{"issuer": r["issuer"], "cost": leg[f"round_trip_cost_c{primary_c}"], "net": leg[f"realized_short_return_c{primary_c}"],
                      "bench": r["ret"]} for r, leg in priced]
        out = {"events": len(subset), "priced": len(priced), "not_priced": dict(reasons), "issuers": len({r["issuer"] for r, _ in priced}),
               "entry_completed_within_window": _share([{"issuer": r["issuer"], "done": leg["entry"]["completed"]} for r, leg in priced], "done"),
               "time_to_complete_entry_seconds": _dist(leg["entry"]["time_to_complete_seconds"] for _, leg in priced if leg["entry"]["completed"]),
               "position_usd": _dist(leg["position_usd"] for _, leg in priced),
               "residual_covered_at_close_share": _dist(leg["residual_at_close_share"] for _, leg in priced),
               "entry_shortfall": _dist(leg["entry_shortfall"] for _, leg in priced),
               "exit_shortfall": _dist(leg["exit_shortfall"] for _, leg in priced),
               "half_spread_round_trip": _dist(leg["entry_half_spread"] + leg["exit_half_spread"] for _, leg in priced)}
        for c in er.CROSSING_FRACTIONS:
            crows = [{"issuer": r["issuer"], "cost": leg[f"round_trip_cost_c{c}"]} for r, leg in priced]
            nrows = [{"issuer": r["issuer"], "net": leg[f"realized_short_return_c{c}"]} for r, leg in priced]
            out[f"round_trip_cost_c{c}"] = {**_dist(x["cost"] for x in crows),
                                            "issuer_interval": cluster_interval(crows, field="cost", cluster="issuer") if crows else None}
            out[f"realized_short_return_c{c}"] = {**_dist(x["net"] for x in nrows),
                                                  "issuer_interval": cluster_interval(nrows, field="net", cluster="issuer") if nrows else None}
        out["benchmark_open_to_close_same_events"] = {**_dist(x["bench"] for x in cost_rows),
                                                      "issuer_interval": cluster_interval(cost_rows, field="bench", cluster="issuer") if cost_rows else None}
        diff = [{"issuer": x["issuer"], "d": x["bench"] - x["cost"]} for x in cost_rows]
        out["benchmark_minus_cost"] = {**_dist(x["d"] for x in diff), "issuer_interval": cluster_interval(diff, field="d", cluster="issuer") if diff else None}
        return out

    leg_keys = sorted({k for r in rows if r.get("legs") for k in r["legs"]})
    primary_leg = f"capacity/{er.PARTICIPATION_RATES[0]}"
    priced_rows = [r for r in rows if r.get("status") == "priced"]
    out = {"definition": ("Sell by taking a fixed share of every one-second listing-venue bar's volume (the opening cross removed) at the bar's range "
                          "midpoint, from the cached arrival book after the open for 60 minutes; cover the same way over the last 60 minutes with any "
                          "residual at the official closing print. Cost = (entry arrival mid - sell VWAP) + (buy VWAP - exit arrival price) + crossing "
                          "fraction x the cached half-spreads (open books for the entry leg, the close book for the cover), all over the entry arrival "
                          "mid. capacity: the order is the rate times the window's volume. account_*: a fixed order of 2.5% of the account at the "
                          "arrival mid; completion within the window is reported."),
           "primary": primary_leg, "crossing_fractions": list(er.CROSSING_FRACTIONS), "rates": list(er.PARTICIPATION_RATES),
           "by_split": {split: {k: block([r for r in rows if r["split"] in _members(split)], k) for k in leg_keys} for split in REPORTED_SPLITS},
           "by_year": {y: {k: block([r for r in rows if r["year"] == y], k) for k in leg_keys if k.startswith("capacity/")}
                       for y in sorted({r["year"] for r in rows})},
           "by_price_band_train_validate": {band: {k: block([r for r in rows if r["price_band"] == band and r["split"] in ("train", "validate")], k)
                                                   for k in leg_keys if k.startswith("capacity/")} for band in [b[2] for b in er.PRICE_BANDS]},
           "by_venue_train_validate": {ds: {k: block([r for r in rows if r["dataset"] == ds and r["split"] in ("train", "validate")], k)
                                            for k in leg_keys if k.startswith("capacity/")} for ds in sorted({r["dataset"] for r in rows})},
           "timing": {split: {"open_print_vs_arrival_mid": _dist(r.get("timing_open_vs_arrival") for r in priced_rows if r["split"] in _members(split)),
                              "exit_arrival_price_vs_close_print": _dist(r.get("timing_exit_mid_vs_close") for r in priced_rows if r["split"] in _members(split)),
                              "first_hour_volume_usd_at_arrival": _dist(r["first_hour_volume"] * r["arrival_mid"] for r in priced_rows
                                                                        if r["split"] in _members(split) and r.get("first_hour_volume") is not None),
                              "cross_removed_from_bars": sum(1 for r in priced_rows if r["split"] in _members(split) and r.get("cross_removed_from_bars")),
                              "exit_spread_from_open_books": sum(1 for r in priced_rows if r["split"] in _members(split) and r.get("exit_spread_from") == "open_books")}
                      for split in REPORTED_SPLITS}}
    return out


# --- commissions ----------------------------------------------------------------------------

def _round_trip(schedule: str, shares: int, sell_px: float, buy_px: float, *, passive_entry: bool) -> dict:
    entry = er.commission_leg(schedule, shares, sell_px, passive=passive_entry, sell=True)
    exit_ = er.commission_leg(schedule, shares, buy_px, passive=False, sell=False)
    gross = shares * sell_px
    return {"usd": entry["total_ex_regulatory"] + exit_["total_ex_regulatory"],
            "fraction": (entry["total_ex_regulatory"] + exit_["total_ex_regulatory"]) / gross,
            "regulatory_fraction": entry["regulatory"] / gross}


def commission_rows(h4: list[dict], h2: list[dict], h3: list[dict]) -> list[dict]:
    """Round-trip commissions under both schedules for the modeled orders, as a fraction of gross exposure."""
    h2_by = {r["key"]: r for r in h2}
    h3_by = {r["key"]: r for r in h3}
    out = []
    for r in h4:
        row = {k: r[k] for k in ("key", "issuer", "year", "split", "ssr_state", "price_band", "open", "close")}
        legs = {}
        for name, shares in (("auction_account", r["order_account_shares"]), ("auction_replay", r["order_replay_shares"])):
            if shares:
                legs[name] = {s: _round_trip(s, shares, r["open"], r["close"], passive_entry=False) for s in er.COMMISSIONS}
                legs[name]["shares"] = shares
        s2 = (h2_by.get(r["key"], {}).get("sims") or {}).get(f"{PRIMARY_ORDER}/{PRIMARY_FILL_MODEL}")
        if s2 and s2.get("status") == "simulated" and s2.get("fully_filled"):
            legs["passive_fill_then_close"] = {s: _round_trip(s, s2["shares"], s2["fill_vwap"], r["close"], passive_entry=True) for s in er.COMMISSIONS}
            legs["passive_fill_then_close"]["shares"] = s2["shares"]
        l3 = (h3_by.get(r["key"], {}).get("legs") or {}).get(f"capacity/{er.PARTICIPATION_RATES[0]}")
        if l3 and l3.get("status") == "priced":
            q = max(1, int(round(l3["position_shares"])))
            buy = l3["exit"].get("vwap") or r["close"]
            legs["participation_1pct"] = {s: _round_trip(s, q, l3["entry"]["vwap"], buy, passive_entry=False) for s in er.COMMISSIONS}
            legs["participation_1pct"]["shares"] = q
        row["legs"] = legs
        out.append(row)
    return out


def commission_results(rows: list[dict]) -> dict:
    def block(subset, leg):
        have = [r["legs"][leg] for r in subset if leg in r.get("legs", {})]
        out = {"events": len(have), "shares": _dist(x["shares"] for x in have)}
        for s in er.COMMISSIONS:
            out[s] = {"round_trip_fraction": _dist(x[s]["fraction"] for x in have), "round_trip_usd": _dist(x[s]["usd"] for x in have)}
        if have:
            out["tiered_minus_fixed_fraction"] = _dist(x["tiered"]["fraction"] - x["fixed"]["fraction"] for x in have)
            out["tiered_cheaper_share"] = float(sum(x["tiered"]["fraction"] < x["fixed"]["fraction"] for x in have) / len(have))
            out["regulatory_pass_through_fraction_both_schedules"] = _dist(x["fixed"]["regulatory_fraction"] for x in have)
        return out

    legs = sorted({k for r in rows for k in r.get("legs", {})})
    return {"schedules": {k: v["description"] for k, v in er.COMMISSIONS.items()},
            "regulatory": f"SEC Section 31 at ${er.SEC_FEE_PER_DOLLAR * 1e6:.2f} per million of sell notional and FINRA TAF at ${er.FINRA_TAF_PER_SHARE} per share sold (max ${er.FINRA_TAF_MAX}); identical under both schedules and reported separately",
            "by_split": {split: {leg: block([r for r in rows if r["split"] in _members(split)], leg) for leg in legs} for split in REPORTED_SPLITS},
            "by_price_band_train_validate": {band: {leg: block([r for r in rows if r["price_band"] == band and r["split"] in ("train", "validate")], leg) for leg in legs}
                                             for band in [b[2] for b in er.PRICE_BANDS]}}


# --- assessments against the registered criteria -----------------------------------------------

def assessments(h4: dict, h2: dict, h3: dict) -> dict:
    out = {}
    # H4: >= 80% on validation; kill under 50%. Primary reading: the account order, all SSR states.
    v = h4["by_split"]["validate"]["all"]["account"]["feasible"]
    t = h4["by_split"]["train"]["all"]["account"]["feasible"]
    share = v.get("share")
    if share is None:
        verdict = "Not measurable: no validation events with a cross."
    elif share >= 0.8:
        verdict = f"Success criterion met on validation: {share:.1%} of events (account order, all SSR states) are at most 5% of the opening cross."
    elif share < 0.5:
        verdict = f"Kill criterion met on validation: only {share:.1%} of events support the account order at 5% of the cross."
    else:
        verdict = f"Between the registered thresholds on validation ({share:.1%}): neither success (>= 80%) nor kill (< 50%)."
    out["H4"] = {"registered_success": ">= 80% on validation", "registered_kill": "under 50%", "assessment": verdict,
                 "validate": {k: v.get(k) for k in ("events", "share", "issuer_interval")}, "train": {k: t.get(k) for k in ("events", "share", "issuer_interval")},
                 "validate_restricted": {k: h4["by_split"]["validate"]["restricted"]["account"]["feasible"].get(k) for k in ("events", "share")},
                 "validate_replay_order": {k: h4["by_split"]["validate"]["all"]["replay"]["feasible"].get(k) for k in ("events", "share")}}
    # H18: fill rate >= 50% and adverse selection < 0.5% on validation; kill under 25%. Restricted sessions, primary order, bar fill model.
    key = h2.get("primary") or f"{PRIMARY_ORDER}/{PRIMARY_FILL_MODEL}"
    blocks = {split: h2["by_ssr_state"]["restricted"]["by_split"][split].get(key) for split in ("train", "validate")}
    vb = blocks["validate"]
    if not vb or not vb["simulated"]:
        verdict = "Not measured: no restricted validation session has a bar file and a cached arrival book."
    else:
        fr, asel = vb["fill_rate"]["share"], vb["adverse_selection_5m"].get("mean")
        if fr is not None and fr < 0.25:
            verdict = f"Kill criterion met on validation: fill rate {fr:.1%} is under 25%."
        elif fr is not None and fr >= 0.5 and asel is not None and asel < 0.005:
            verdict = f"Success criterion met on validation: fill rate {fr:.1%} and 5-minute adverse selection {asel:.2%}."
        else:
            verdict = (f"Between the registered thresholds on validation: fill rate {fr:.1%}" if fr is not None else "fill rate unavailable") + \
                      (f", 5-minute adverse selection {asel:.2%}." if asel is not None else ", adverse selection unavailable.")
    out["H18"] = {"registered_success": "fill rate >= 50% and adverse selection < 0.5% on validation", "registered_kill": "fill rate under 25%",
                  "assessment": verdict,
                  **{split: ({"simulated": b["simulated"], "fill_rate": b["fill_rate"], "adverse_selection_5m": b["adverse_selection_5m"],
                              "time_to_fill_seconds": b["time_to_fill_seconds"], "fills_with_market_above_offer": b.get("fills_with_market_above_offer")} if b else None)
                     for split, b in blocks.items()}}
    # H19: under 1.5% round trip on validation at 1% participation; kill if the cost exceeds the open-to-close benchmark.
    leg = h3["primary"]
    c = er.CROSSING_FRACTIONS[0]
    hb = {split: h3["by_split"][split].get(leg) for split in ("train", "validate")}
    vb = hb["validate"]
    detail = {split: ({"priced": b["priced"], "round_trip_cost": b[f"round_trip_cost_c{c}"], "benchmark": b["benchmark_open_to_close_same_events"],
                       "benchmark_minus_cost": b["benchmark_minus_cost"], "realized_short_return": b[f"realized_short_return_c{c}"]}
                      if b and b["priced"] else None) for split, b in hb.items()}
    if not vb or not vb["priced"]:
        verdict = "Not measured: no validation session has a bar file and a cached arrival book."
    else:
        cost = vb[f"round_trip_cost_c{c}"]["mean"]
        bench = vb["benchmark_open_to_close_same_events"]["mean"]
        if cost is not None and bench is not None and cost > bench:
            verdict = f"Kill criterion met on validation: round-trip cost {cost:.2%} exceeds the same events' open-to-close benchmark {bench:.2%}."
        elif cost is not None and cost < 0.015:
            verdict = f"Success criterion met on validation: round-trip cost {cost:.2%} at 1% participation (benchmark {bench:.2%})."
        else:
            verdict = f"Between the registered thresholds on validation: round-trip cost {cost:.2%} against a benchmark of {bench:.2%}."
    out["H19"] = {"registered_success": "under 1.5% round trip on validation", "registered_kill": "cost exceeds the open-to-close benchmark",
                  "assessment": verdict, **detail}
    for old, new in er.SUPERSEDED.items():
        out[old] = {"assessment": f"Superseded by {new}: the registered cost model needs mbp-1 and trade prints, which are not free on this plan and are not bought."}
    return out


# --- assembly -------------------------------------------------------------------------------------

def build(cfg: Config, *, log=print) -> dict:
    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    registry = load_registry(cfg.ledger_dir)
    if not declared_before(registry, list(er.HYPOTHESES), built_at):
        raise SystemExit(f"hypotheses {', '.join(er.HYPOTHESES)} must be registered before the study is built")
    rows = er.event_rows(cfg)
    log(f"events: {len(rows)}; splits { {s: sum(1 for r in rows if r['split'] == s) for s in ALL_SPLITS} }; "
        f"ssr { dict(Counter(r['ssr_state'] for r in rows)) }")
    crosses, stat_files = statistics_crosses(cfg, rows, log=log)
    log(f"opening crosses: {sum(1 for v in crosses.values() if v.get('open_cross_shares'))} of {len(rows)} events")
    h4r = h4_rows(rows, crosses)
    h4 = h4_results(h4r)
    books, books_file = cached_books(cfg)
    log(f"cached books: {sum(1 for b in books.values() if b.get('open_1'))} one-second, {sum(1 for b in books.values() if b.get('open_30'))} "
        f"thirty-second, {sum(1 for b in books.values() if b.get('close'))} close")
    items = _window_items(cfg, rows)
    cache = WindowCache(cfg)
    h2r, h3r = window_rows(cfg, rows, items, cache, crosses, books, log=log)
    h2 = h2_results(h2r)
    h3 = h3_results(h3r)
    comm_rows = commission_rows(h4r, h2r, h3r)
    comm = commission_results(comm_rows)
    quotes = read_json(er.work_dir(cfg) / "quotes.json", {})
    downloads = read_json(er.work_dir(cfg) / "downloads.json", [])
    coverage = {"policy": "free data only: every request quoted first; nothing priced above $0.00 is fetched",
                "events": len(rows),
                "bar_files_planned": len({v["id"] for v in items.values()}),
                "bar_files_local": len(cache.files),
                "events_with_bars_and_arrival_book": sum(1 for r in h2r if r.get("status") == "simulated"),
                "events_priced_for_participation": sum(1 for r in h3r if r.get("status") == "priced"),
                "not_simulated": dict(Counter(r.get("status") for r in h2r if r.get("status") != "simulated")),
                "by_split_simulated": {s: sum(1 for r in h2r if r.get("status") == "simulated" and r["split"] == s) for s in ALL_SPLITS},
                "data_cost_incurred_usd": round(cache.cost_usd, 6),
                "quoted_planned_total_usd": ((quotes.get("summary") or {}).get("planned_total") or {}).get("usd"),
                "quoted_refused_above_zero": ((quotes.get("summary") or {}).get("priced_above_zero_refused") or {}).get("requests"),
                "downloads": [{k: d.get(k) for k in ("downloaded_at", "files", "bytes", "quoted_usd", "refused_priced_above_zero", "refused_usd")} for d in downloads]}
    doc = {"schema_version": er.VERSION, "built_at": built_at, "research_only": True, "authority": "none", "aggregate_only": True,
           "hypothesis_ids": list(er.HYPOTHESES), "superseded": dict(er.SUPERSEDED), "source_run_id": RUN_ID,
           "splits": {k: list(v) for k, v in SPLITS.items()},
           "holdout_policy": {"start": HOLDOUT_START, "status": "sealed",
                              "location": "local/holdout/execution_realism_holdout.json (not committed, not read until the program's final review)"},
           "data": coverage,
           "h4_opening_cross": h4, "h18_passive_offer_under_ssr": h2, "h19_participation_cost": h3, "commissions": comm}
    doc["assessments"] = assessments(h4, h2, h3)
    doc["definitions"] = {
        "short_return_convention": "1 - exit price / entry price; positive means the short gained.",
        "split": "By the entry session date. Train 2018-05-01 to 2022-12-31, validate 2023-01-01 to 2024-12-31, holdout from 2025-01-01 (sealed).",
        "issuer_interval": "95% percentile interval from 2,000 whole-issuer (CIK) bootstrap draws; events of one issuer move together.",
        "feasible_share": "Share of events whose order is at least one whole share and at most 5% of the matched cross shares.",
        "fill_rate": "Share of simulated orders fully filled within 15 minutes of placement; partial fills are reported separately.",
        "adverse_selection_5m": "Last one-second bar close five minutes after completion minus the fill price, over the arrival midpoint; positive is adverse to the short.",
        "round_trip_cost": "Entry shortfall + exit shortfall + crossing fraction x the cached half-spreads, over the entry arrival midpoint; positive is a cost.",
        "benchmark_minus_cost": "The same events' official open-to-close gross short return minus the round-trip cost; H19's kill branch reads this below zero.",
        "commission_fraction": "Round-trip commission, venue fees and clearing (regulatory pass-through excluded) over the entry notional.",
    }
    doc["limits"] = [
        "Free data only: one-second listing-venue bars and the opening and closing books cached by the earlier quote study; not consolidated volume or NBBO, and no intraday quotes between those books.",
        "The bar fill model spreads each second's volume evenly over the bar's tick prices and credits no cancellations and no re-pricing; fills counted on bars that traded entirely above the offer may in reality have been re-priced orders, so the fill rate is an upper bound and the fill price a lower bound against the book-level model that was not run.",
        "Hidden and midpoint liquidity ahead of the order is invisible in displayed size, which also pushes the fill rate up.",
        "The participation model follows printed volume with no market impact beyond the spread term; at 5% of volume that is optimistic, and the spread term uses the open and close books rather than the spread at each fill time.",
        "Arrival is the cached book one second after the scheduled open (thirty seconds where that record is missing); the exit arrival is the first bar at or after 15:00, up to five minutes later for names that did not print at 15:00.",
        "Halts inside a window simply contribute no bars; LULD and news halts are not modeled as events.",
        "Commission schedules are declared constants (IBKR fixed and tiered at the lowest tier with representative exchange fees); regulatory pass-through uses today's published rates for every year.",
        "The opening-cross feasibility is a size test at the printed price; it does not establish that an auction order of that size would not have moved the cross price.",
        "No borrow, locate or margin assumption enters any number here; H18's realized return to the close is gross of borrow and commissions.",
        "Holdout results exist only under local/holdout and were not read while writing this document; nothing here was selected on them.",
    ]
    local = {"h4": h4r, "h18": h2r, "h19": h3r, "commissions": comm_rows}
    manifest_inputs = {"statistics_files": stat_files, "cached_books": books_file,
                       "bar_files": sorted(cache.files.values(), key=lambda f: f["path"])}
    return {"doc": doc, "local": local, "built_at": built_at, "manifest_inputs": manifest_inputs}


def _holdout_view(doc: dict) -> dict:
    def pick(node):
        if isinstance(node, dict):
            keep = {}
            for k, v in node.items():
                if k == "holdout" or k in HOLDOUT_YEARS:
                    keep[k] = v
                elif isinstance(v, (dict, list)):
                    sub = pick(v)
                    if sub:
                        keep[k] = sub
            return keep
        if isinstance(node, list):
            return [v for v in node if isinstance(v, dict) and str(v.get("year", "")) in HOLDOUT_YEARS]
        return None
    return pick(doc)


def write_outputs(cfg: Config, result: dict, *, publish: bool, log=print) -> dict:
    doc, local = result["doc"], result["local"]
    wdir = er.work_dir(cfg)
    wdir.mkdir(parents=True, exist_ok=True)
    holdout_dir = cfg.local_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    full_path = wdir / "execution_realism_full.local.json"
    write_json(full_path, {"doc": doc, "rows": local})
    holdout_path = holdout_dir / "execution_realism_holdout.json"
    write_json(holdout_path, {"schema_version": er.VERSION, "built_at": doc["built_at"], "sealed": True, "results": _holdout_view(doc)})
    public = seal(doc)
    outputs = {"full": str(full_path), "holdout": str(holdout_path)}
    if publish:
        out_path = cfg.ledger_dir / "execution_realism.json"
        write_json(out_path, public)
        run_dir = er._run_dir(cfg)
        inputs = {"run_id": RUN_ID,
                  "run_inputs": [{"path": str(p.relative_to(cfg.local_dir).as_posix()), "sha256": sha256_file(p)}
                                 for p in sorted((run_dir / "event_outcomes").glob("*.jsonl")) + [run_dir / "prices.sqlite"] if p.exists()],
                  "targets": {"path": f"execution_research/{er.QUOTE_STUDY}/targets.local.json",
                              "sha256": sha256_file(cfg.local_dir / "execution_research" / er.QUOTE_STUDY / "targets.local.json")},
                  "ssr_states_db": {"path": str(cfg.db_path.relative_to(cfg.local_dir).as_posix()), "sha256": sha256_file(cfg.db_path)},
                  "quotes": {"path": "workstream_a/quotes.json", "sha256": sha256_file(wdir / "quotes.json")} if (wdir / "quotes.json").exists() else None,
                  "downloads": {"path": "workstream_a/downloads.json", "sha256": sha256_file(wdir / "downloads.json")} if (wdir / "downloads.json").exists() else None,
                  **result["manifest_inputs"]}
        measured = [h for h in er.HYPOTHESES if not str(doc["assessments"].get(h, {}).get("assessment", "")).startswith("Not me")]
        mark_measured(cfg.ledger_dir, measured, out_path.name)
        manifest = {"schema_version": er.VERSION, "built_at": doc["built_at"], "hypothesis_ids": list(er.HYPOTHESES), "aggregate_only": True,
                    "hypotheses_measured": measured, "superseded": dict(er.SUPERSEDED),
                    "output": {"path": out_path.name, "sha256": sha256_file(out_path)},
                    "registry": {"path": "hypotheses.jsonl", "sha256": sha256_file(cfg.ledger_dir / "hypotheses.jsonl")},
                    "code": [{"path": f"_system/scripts/reverse_splits/{name}", "sha256": sha256_file(Path(__file__).with_name(name))}
                             for name in ("execution_realism.py", "execution_realism_build.py")],
                    "data_policy": doc["data"]["policy"],
                    "data_cost_incurred_usd": doc["data"]["data_cost_incurred_usd"],
                    "inputs": inputs,
                    "holdout": {"path": "local/holdout/execution_realism_holdout.json", "sha256": sha256_file(holdout_path), "sealed": True},
                    "raw_market_data_public": False}
        write_json(cfg.ledger_dir / "execution_realism_manifest.json", manifest)
        outputs["published"] = str(out_path)
        outputs["manifest"] = str(cfg.ledger_dir / "execution_realism_manifest.json")
        log(f"published {out_path} and manifest")
    return outputs


def run_build(cfg: Config, *, publish: bool) -> int:
    result = build(cfg)
    outputs = write_outputs(cfg, result, publish=publish)
    print(json.dumps({"outputs": outputs, "assessments": {k: v.get("assessment") for k, v in result["doc"]["assessments"].items()},
                      "data": result["doc"]["data"]}, indent=1))
    return 0
