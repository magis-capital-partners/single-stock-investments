#!/usr/bin/env python3
"""Build dashboard/data/index_membership.json — eligibility scorecards + confirmed events."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys_path_insert = str(ROOT / "_system" / "scripts")
import sys

sys.path.insert(0, sys_path_insert)

from index_market_inputs import load_fundamentals_cache, market_inputs_for_ticker  # noqa: E402

DATA_DIR = ROOT / "_system" / "data"
REF_INDEX = ROOT / "_system" / "reference" / "market-data" / "index"
OUT_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
DOCS_OUT = ROOT / "docs" / "data" / "index_membership.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
ANNOUNCEMENTS = DATA_DIR / "index_announcements.jsonl"

STATUS_ENUM = {"member", "inclusion_candidate", "deletion_risk", "ineligible", "n_a"}
CONF_ENUM = {"rules_only", "news_unconfirmed", "provider_confirmed"}

INDEX_ALIASES = {
    "s&p 500": "sp500",
    "s&p500": "sp500",
    "sp 500": "sp500",
    "sp500": "sp500",
    "s&p midcap 400": "sp400",
    "s&p 400": "sp400",
    "sp400": "sp400",
    "s&p smallcap 600": "sp600",
    "s&p 600": "sp600",
    "sp600": "sp600",
    "russell 1000": "russell_1000",
    "russell1000": "russell_1000",
    "russell 2000": "russell_2000",
    "russell2000": "russell_2000",
    "nasdaq 100": "nasdaq_100",
    "nasdaq-100": "nasdaq_100",
    "nasdaq100": "nasdaq_100",
    "msci": "msci_acwi",
    "msci usa": "msci_usa",
    "msci acwi": "msci_acwi",
    "tsx": "tsx_composite",
    "s&p/tsx": "tsx_composite",
    "topix": "topix",
    "ftse 100": "ftse_100",
    "ftse 250": "ftse_250",
    "stoxx": "stoxx_europe_600",
    "asx 200": "asx_200",
    "nzx 50": "nzx_50",
    "hang seng": "hang_seng",
    "nifty": "nifty_500",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(value).strip())
    if not m:
        return None
    return date.fromisoformat(m.group(1))


def days_until(d: date | None, today: date) -> int | None:
    if d is None:
        return None
    return (d - today).days


def load_announcements() -> list[dict]:
    if not ANNOUNCEMENTS.exists():
        return []
    rows = []
    for line in ANNOUNCEMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_announcement(row: dict) -> None:
    ANNOUNCEMENTS.parent.mkdir(parents=True, exist_ok=True)
    key = (
        row.get("ticker"),
        row.get("index"),
        row.get("action"),
        row.get("effective") or row.get("announced"),
    )
    existing = load_announcements()
    for e in existing:
        ek = (e.get("ticker"), e.get("index"), e.get("action"), e.get("effective") or e.get("announced"))
        if ek == key:
            return
    with ANNOUNCEMENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def detect_index_in_text(text: str) -> str | None:
    low = (text or "").lower()
    # longer keys first
    for alias in sorted(INDEX_ALIASES.keys(), key=len, reverse=True):
        if alias in low:
            return INDEX_ALIASES[alias]
    if "russell" in low:
        return "russell_2000"
    if "s&p" in low or "s and p" in low:
        return "sp500"
    return None


def detect_action(text: str) -> str | None:
    low = (text or "").lower()
    if re.search(r"\b(removed|deleted|dropped|deletion|exclusion|to be removed)\b", low):
        return "delete"
    if re.search(r"\b(added|joins|joining|inclusion|addition|to be added|will replace|replaces)\b", low):
        return "add"
    if re.search(r"\b(under review|index review)\b", low):
        return "review"
    return None


def harvest_news_announcements(news_doc: dict, today: date) -> list[dict]:
    harvested = []
    for item in news_doc.get("items") or news_doc.get("articles") or news_doc.get("news") or []:
        cat = item.get("category") or ""
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        text = f"{title} {summary}"
        if cat not in {"index_inclusion", "index_addition", "index_deletion", "market_structure"}:
            if not detect_action(text) or not detect_index_in_text(text):
                continue
            if "index" not in text.lower() and "russell" not in text.lower() and "s&p" not in text.lower():
                continue
        tickers = item.get("tickers") or ([item.get("ticker")] if item.get("ticker") else [])
        tickers = [t for t in tickers if t]
        if not tickers:
            continue
        index_id = detect_index_in_text(text) or "sp500"
        action = detect_action(text) or ("delete" if cat == "index_deletion" else "add")
        if action == "review":
            continue
        announced = item.get("published_utc") or item.get("published") or item.get("date") or today.isoformat()
        announced = str(announced)[:10]
        for ticker in tickers:
            row = {
                "ticker": ticker,
                "index": index_id,
                "action": action,
                "announced": announced,
                "effective": None,
                "source_url": item.get("url") or item.get("link"),
                "source_type": "news",
                "confidence": "news_unconfirmed",
                "title": title,
            }
            append_announcement(row)
            harvested.append(row)
    return harvested


def applicable_indices(meta: dict, rules: dict) -> list[str]:
    market = meta.get("market") or ""
    exchange = (meta.get("exchange") or "").upper()
    out = []
    for index_id, spec in (rules.get("indices") or {}).items():
        markets = spec.get("markets") or []
        exchanges = [e.upper() for e in (spec.get("exchanges") or [])]
        if markets and market not in markets:
            # allow US OTC only for ineligible path via security type, not scorecards
            continue
        if exchanges and exchange and exchange not in exchanges:
            # still allow if market matches and exchanges list is advisory for home indices
            if index_id in {"msci_acwi", "msci_usa", "stoxx_europe_600", "russell_1000", "russell_2000"}:
                pass
            elif market in markets and not exchanges:
                pass
            elif exchange not in exchanges:
                continue
        out.append(index_id)
    # Always attach russell + sp families for US listed
    if market == "US" and exchange not in {"OTC PINK", "PRIVATE", "OTC"}:
        for idx in ("sp500", "sp400", "sp600", "russell_1000", "russell_2000", "msci_usa", "msci_acwi"):
            if idx not in out:
                out.append(idx)
        if exchange == "NASDAQ":
            if "nasdaq_100" not in out:
                out.append("nasdaq_100")
    return out


def check_result(passed: bool | None, value, threshold, reason: str | None = None) -> dict:
    return {
        "pass": passed,
        "value": value,
        "threshold": threshold,
        "reason": reason,
    }


def scorecard_sp(
    index_id: str,
    spec: dict,
    mi: dict,
    is_member: bool,
) -> dict:
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    missing = list(mi.get("missing") or [])
    dist: float | None = None

    if index_id == "sp500":
        thr = spec.get("min_company_mcap_usd")
        if mcap is None:
            checks["market_cap"] = check_result(None, None, thr, "missing market_cap")
        else:
            checks["market_cap"] = check_result(mcap >= thr, mcap, thr)
            dist = ((mcap - thr) / thr) * 100.0 if thr else None
    else:
        band = spec.get("band_usd") or [0, 0]
        lo, hi = band[0], band[1]
        if mcap is None:
            checks["market_cap"] = check_result(None, None, band, "missing market_cap")
        else:
            in_band = lo <= mcap <= hi
            checks["market_cap"] = check_result(in_band, mcap, band)
            if mcap < lo:
                dist = ((mcap - lo) / lo) * 100.0
            elif mcap > hi:
                dist = ((mcap - hi) / hi) * 100.0
            else:
                # distance to nearer edge, negative means inside
                dist = -min(abs(mcap - lo), abs(hi - mcap)) / ((hi - lo) or 1) * 100.0

    float_pct = mi.get("float_pct")
    min_float = spec.get("min_float_pct")
    if float_pct is None:
        checks["float"] = check_result(None, None, min_float, "missing float_pct")
    else:
        checks["float"] = check_result(float_pct >= min_float, float_pct, min_float)

    ep = mi.get("earnings_positive")
    if ep is None:
        checks["earnings_positive"] = check_result(None, mi.get("earnings_note"), True, "missing earnings")
    else:
        checks["earnings_positive"] = check_result(bool(ep), ep, True, mi.get("earnings_note"))

    exch = (mi.get("exchange") or "").upper()
    allowed = [e.upper() for e in (spec.get("exchanges") or [])]
    if not exch:
        checks["exchange"] = check_result(None, None, allowed, "missing exchange")
    else:
        checks["exchange"] = check_result(exch in allowed, exch, allowed)

    # liquidity: dollar ADV / float mcap
    adv = mi.get("adv_dollar")
    if adv is None or mcap is None or float_pct is None:
        checks["liquidity"] = check_result(None, None, spec.get("liquidity_ratio_min"), "missing adv or float")
    else:
        float_mcap = mcap * float_pct
        ratio = (adv * 252) / float_mcap if float_mcap else None
        checks["liquidity"] = check_result(
            ratio is not None and ratio >= float(spec.get("liquidity_ratio_min") or 1.0),
            ratio,
            spec.get("liquidity_ratio_min"),
        )

    return finalize_scorecard(index_id, checks, is_member, dist, missing)


def scorecard_mcap_min(index_id: str, spec: dict, mi: dict, is_member: bool, key: str = "min_mcap_usd") -> dict:
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    thr = spec.get(key)
    dist = None
    if thr is None:
        checks["market_cap"] = check_result(None, mcap, None, "no public cutoff encoded; membership-seed only")
    elif mcap is None:
        checks["market_cap"] = check_result(None, None, thr, "missing market_cap")
    else:
        checks["market_cap"] = check_result(mcap >= thr, mcap, thr)
        dist = ((mcap - thr) / thr) * 100.0
    exch = (mi.get("exchange") or "").upper()
    allowed = [e.upper() for e in (spec.get("exchanges") or [])]
    if allowed:
        if not exch:
            checks["exchange"] = check_result(None, None, allowed, "missing exchange")
        else:
            checks["exchange"] = check_result(exch in allowed, exch, allowed)
    return finalize_scorecard(index_id, checks, is_member, dist, mi.get("missing") or [])


def scorecard_russell(
    index_id: str,
    spec: dict,
    mi: dict,
    is_member: bool,
    universe_ranks: dict[str, int],
) -> dict:
    checks: dict[str, dict] = {}
    mcap = mi.get("market_cap_usd")
    ticker = mi.get("ticker")
    rank = universe_ranks.get(ticker)
    dist = None
    if mcap is None:
        checks["market_cap"] = check_result(None, None, "total_market_cap rank", "missing market_cap")
    else:
        checks["market_cap"] = check_result(True, mcap, "ranked among US holdings with mcap")
    if rank is None:
        checks["rank"] = check_result(None, None, spec.get("breakpoint_rank") or spec.get("breakpoint_rank_low"), "rank unavailable")
    else:
        if index_id == "russell_1000":
            bp = int(spec.get("breakpoint_rank") or 1000)
            band = float(spec.get("band_pct") or 0.025)
            # Within our universe we only have ~117 US names; treat rank vs portfolio as relative signal
            # Map: lower rank number = larger. Candidate if rank near bp among full market — here use mcap vs median of members heuristic
            passed = rank <= bp if is_member or rank <= max(bp, len(universe_ranks)) else rank <= bp
            # Distance: how far rank is from breakpoint as pct of breakpoint
            dist = ((bp - rank) / bp) * 100.0
            within_band = abs(dist) <= band * 100
            checks["rank"] = check_result(passed, rank, bp, f"within_band={within_band}")
        else:
            lo = int(spec.get("breakpoint_rank_low") or 1001)
            hi = int(spec.get("breakpoint_rank_high") or 3000)
            passed = lo <= rank <= hi
            mid = (lo + hi) / 2
            dist = ((mid - rank) / mid) * 100.0
            checks["rank"] = check_result(passed, rank, [lo, hi])
    sc = finalize_scorecard(index_id, checks, is_member, dist, mi.get("missing") or [])
    sc["rank_estimate"] = rank
    return sc


def finalize_scorecard(
    index_id: str,
    checks: dict,
    is_member: bool,
    distance_pct: float | None,
    missing: list[str],
) -> dict:
    gating = None
    known = []
    # Addition gates (earnings, mcap band, liquidity) do not force deletion for existing members.
    member_hard_fails = {"exchange", "security_type", "float"}
    for name, c in checks.items():
        if c.get("pass") is False:
            if not is_member or name in member_hard_fails:
                gating = gating or name
        if c.get("pass") is not None:
            known.append(c.get("pass"))
    if is_member:
        if gating:
            status = "deletion_risk"
        else:
            status = "member"
    else:
        if mi_ineligible_from_missing(missing) and not known:
            status = "n_a"
        elif gating and all(c.get("pass") is not True for c in checks.values() if c.get("pass") is not None):
            # far from eligibility
            if distance_pct is not None and distance_pct > -40:
                status = "inclusion_candidate" if not gating else "n_a"
            else:
                status = "n_a" if any(c.get("pass") is None for c in checks.values()) else "ineligible"
        elif distance_pct is not None and distance_pct >= -15 and (not gating or gating == "earnings_positive"):
            status = "inclusion_candidate"
        elif known and all(known) and distance_pct is not None and distance_pct >= -25:
            status = "inclusion_candidate"
        elif any(c.get("pass") is None for c in checks.values()) and not known:
            status = "n_a"
        else:
            status = "n_a" if any(c.get("pass") is None for c in checks.values()) else "ineligible"

    # Soften: if member, keep member/deletion_risk only
    if is_member and status not in {"member", "deletion_risk"}:
        status = "deletion_risk" if gating else "member"

    # If not member and all hard gates pass and close to boundary
    if not is_member:
        fails = [n for n, c in checks.items() if c.get("pass") is False]
        unknowns = [n for n, c in checks.items() if c.get("pass") is None]
        passes = [n for n, c in checks.items() if c.get("pass") is True]
        if not fails and passes and distance_pct is not None and distance_pct >= -20:
            status = "inclusion_candidate"
            gating = None
        elif not fails and not passes and unknowns:
            status = "n_a"
            gating = unknowns[0]

    return {
        "index": index_id,
        "status": status,
        "checks": checks,
        "gating_check": gating,
        "distance_to_boundary_pct": round(distance_pct, 2) if distance_pct is not None else None,
        "confidence": "rules_only",
    }


def mi_ineligible_from_missing(missing: list[str]) -> bool:
    return "market_cap" in missing


def build_universe_ranks(inputs_by_ticker: dict[str, dict]) -> dict[str, int]:
    """Rank US names by market cap (1 = largest). Portfolio-relative proxy for Russell."""
    rows = []
    for t, mi in inputs_by_ticker.items():
        if mi.get("market") != "US":
            continue
        if mi.get("security_type") in {"cvr", "preferred", "debenture", "rights", "otc_pink", "private"}:
            continue
        mcap = mi.get("market_cap_usd")
        if mcap is None:
            continue
        rows.append((t, mcap))
    rows.sort(key=lambda x: x[1], reverse=True)
    # Scale portfolio ranks into a pseudo full-market rank so breakpoint 1000 is meaningful:
    # map position i of n → approx rank = 1 + i * (3000 / max(n,1))
    n = max(len(rows), 1)
    ranks = {}
    for i, (t, _) in enumerate(rows):
        ranks[t] = int(1 + i * (3000 / n))
    return ranks


def inclusion_probability_band(scorecard: dict, days_out: int | None, rules: dict) -> str:
    if scorecard.get("status") in {"ineligible", "n_a"}:
        return "n_a"
    if scorecard.get("status") == "member":
        return "n_a"
    dist = scorecard.get("distance_to_boundary_pct")
    if dist is None:
        return "n_a"
    checks = scorecard.get("checks") or {}
    known = [c for c in checks.values() if c.get("pass") is not None]
    if not known:
        return "n_a"
    pass_pct = sum(1 for c in known if c.get("pass")) / len(known)
    bands = (rules.get("scoring") or {}).get("inclusion_probability") or {}
    for name in ("high", "medium", "low"):
        b = bands.get(name) or {}
        if abs(dist) <= float(b.get("max_abs_distance_pct") or 999) and pass_pct >= float(
            b.get("min_gates_pass_pct") or 0
        ):
            max_days = b.get("max_days_to_event")
            if days_out is None or max_days is None or days_out <= int(max_days):
                return name
    return "low"


def priority_score(
    scorecards: list[dict],
    mi: dict,
    days_out: int | None,
    rules: dict,
    confirmed_soon: bool,
) -> tuple[float, float | None]:
    weights = (rules.get("scoring") or {}).get("weights") or {}
    w_b = float(weights.get("boundary_closeness") or 0.35)
    w_c = float(weights.get("calendar_proximity") or 0.25)
    w_d = float(weights.get("demand_shock") or 0.30)
    w_i = float(weights.get("illiquidity") or 0.10)

    # Best absolute distance among candidate/deletion scorecards
    dists = [
        abs(sc["distance_to_boundary_pct"])
        for sc in scorecards
        if sc.get("distance_to_boundary_pct") is not None
        and sc.get("status") in {"inclusion_candidate", "deletion_risk", "member"}
    ]
    if dists:
        best = min(dists)
        boundary = max(0.0, 1.0 - best / 40.0)
    else:
        boundary = 0.0

    if days_out is None:
        cal = 0.0
    elif days_out < 0:
        cal = 0.1
    else:
        cal = max(0.0, 1.0 - days_out / 180.0)

    # Demand shock proxy: assumed weight * mcap / ADV
    mcap = mi.get("market_cap_usd")
    adv = mi.get("adv_dollar")
    bps = float((rules.get("scoring") or {}).get("assumed_index_weight_bps_add") or 5.0)
    shock = None
    if mcap and adv and adv > 0:
        assumed_notional = mcap * (bps / 10000.0)
        shock = (assumed_notional / adv) * 100.0  # pct of one-day ADV
        cap = float((rules.get("scoring") or {}).get("demand_shock_adv_cap") or 50.0)
        demand = min(1.0, shock / cap)
    else:
        demand = 0.15 if any(sc.get("status") == "inclusion_candidate" for sc in scorecards) else 0.0

    if adv and adv > 0 and mcap:
        # lower ADV / mcap → higher illiquidity score
        turnover = adv / mcap
        illiq = max(0.0, min(1.0, 1.0 - turnover * 50))
    else:
        illiq = 0.4

    score = w_b * boundary + w_c * cal + w_d * demand + w_i * illiq
    if confirmed_soon:
        score = min(1.0, score + 0.15)
    if any(sc.get("status") == "deletion_risk" for sc in scorecards):
        score = min(1.0, score + 0.1)
    return round(score, 4), round(shock, 3) if shock is not None else None


def next_calendar_for_indices(calendar: dict, index_ids: list[str], today: date) -> dict | None:
    best = None
    best_days = None
    for ev in calendar.get("events") or []:
        indices = ev.get("indices") or []
        if index_ids and not any(i in indices for i in index_ids):
            continue
        eff = parse_date(ev.get("effective"))
        d = days_until(eff, today)
        if d is None:
            continue
        if best_days is None or (d >= 0 and (best_days < 0 or d < best_days)) or (best_days is not None and best_days < 0 and d > best_days):
            # prefer soonest future; else least-negative past
            if best is None:
                best, best_days = ev, d
            elif d >= 0 and (best_days < 0 or d < best_days):
                best, best_days = ev, d
            elif best_days is not None and best_days < 0 and d < 0 and d > best_days:
                best, best_days = ev, d
    if not best:
        return None
    return {
        "id": best.get("id"),
        "index_family": best.get("index_family"),
        "indices": best.get("indices"),
        "kind": best.get("kind"),
        "effective": best.get("effective"),
        "label": best.get("label"),
        "days_out": best_days,
    }


def apply_confirmed_to_seed(seed: dict, announcements: list[dict], today: date) -> dict:
    by_ticker = dict(seed.get("by_ticker") or {})
    for ann in announcements:
        if ann.get("confidence") != "provider_confirmed":
            continue
        eff = parse_date(ann.get("effective"))
        if eff is None or eff > today:
            continue
        t = ann.get("ticker")
        idx = ann.get("index")
        action = ann.get("action")
        if not t or not idx:
            continue
        entry = dict(by_ticker.get(t) or {"memberships": [], "source": "provider_confirmed", "as_of": today.isoformat()})
        mem = list(entry.get("memberships") or [])
        if action == "add" and idx not in mem:
            mem.append(idx)
        if action == "delete" and idx in mem:
            mem = [m for m in mem if m != idx]
        entry["memberships"] = sorted(set(mem))
        entry["as_of"] = today.isoformat()
        entry["source"] = "provider_confirmed"
        by_ticker[t] = entry
    seed = dict(seed)
    seed["by_ticker"] = by_ticker
    return seed


def corporate_action_tickers(news_doc: dict) -> set[str]:
    """Tickers that appear to be acquisition targets or going private (deletion risk)."""
    out: set[str] = set()
    target_pat = re.compile(
        r"\b(to\s+be\s+acquired|agrees\s+to\s+be\s+acquired|going\s+private|take[- ]private|"
        r"buyout\s+of|will\s+be\s+acquired|accepts\s+buyout)\b",
        re.I,
    )
    for item in news_doc.get("items") or []:
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        text = f"{title} {summary}"
        if not target_pat.search(text):
            continue
        # Only flag tickers named in the title (primary subject), not co-mentions
        title_up = title.upper()
        for t in item.get("tickers") or ([item.get("ticker")] if item.get("ticker") else []):
            if not t:
                continue
            # Require ticker or company-ish token in title
            bare = str(t).split(".")[0].upper()
            if bare in title_up or str(t).upper() in title_up:
                out.add(t)
    return out


def build_for_ticker(
    ticker: str,
    meta: dict,
    rules: dict,
    calendar: dict,
    seed_entry: dict,
    mi: dict,
    universe_ranks: dict[str, int],
    announcements: list[dict],
    today: date,
    mna_tickers: set[str] | None = None,
) -> dict:
    memberships = list((seed_entry or {}).get("memberships") or [])
    sec_type = mi.get("security_type")
    ineligible_types = set(rules.get("ineligible_security_types") or [])

    scorecards: list[dict] = []
    if sec_type and sec_type in ineligible_types:
        scorecards.append(
            {
                "index": "_security",
                "status": "ineligible",
                "checks": {
                    "security_type": check_result(False, sec_type, list(ineligible_types), "excluded security type")
                },
                "gating_check": "security_type",
                "distance_to_boundary_pct": None,
                "confidence": "rules_only",
            }
        )
    else:
        for index_id in applicable_indices(meta, rules):
            spec = (rules.get("indices") or {}).get(index_id) or {}
            is_member = index_id in memberships
            family = spec.get("family")
            if family == "sp_dji":
                sc = scorecard_sp(index_id, spec, mi, is_member)
            elif family == "russell":
                sc = scorecard_russell(index_id, spec, mi, is_member, universe_ranks)
            elif family in {"nasdaq", "msci", "tsx", "ftse", "stoxx", "asx", "nzx", "hsi", "nse", "sgx", "b3", "bmv", "jpx"}:
                key = "min_mcap_usd"
                if "min_mcap_cad" in spec:
                    key = "min_mcap_cad"
                elif "min_mcap_gbp" in spec:
                    key = "min_mcap_gbp"
                elif "min_mcap_eur" in spec:
                    key = "min_mcap_eur"
                sc = scorecard_mcap_min(index_id, spec, mi, is_member, key=key)
                if family in {"jpx", "hsi", "nse", "sgx", "b3", "bmv", "asx", "nzx"} and not spec.get(key):
                    # membership-seed primary
                    if is_member:
                        sc["status"] = "member"
                    else:
                        sc["status"] = "n_a"
                        sc["gating_check"] = sc.get("gating_check") or "membership_seed_only"
            else:
                sc = {
                    "index": index_id,
                    "status": "member" if is_member else "n_a",
                    "checks": {},
                    "gating_check": None if is_member else "unsupported_family",
                    "distance_to_boundary_pct": None,
                    "confidence": "rules_only",
                }
            # If member from seed, force member unless deletion_risk already set
            if is_member and sc.get("status") not in {"deletion_risk"}:
                sc["status"] = "member"
            scorecards.append(sc)

    t_anns = [a for a in announcements if a.get("ticker") == ticker]
    confirmed_events = []
    for a in t_anns:
        confirmed_events.append(
            {
                "index": a.get("index"),
                "action": a.get("action"),
                "announced": a.get("announced"),
                "effective": a.get("effective"),
                "source_url": a.get("source_url"),
                "source_type": a.get("source_type"),
                "confidence": a.get("confidence"),
                "title": a.get("title"),
            }
        )
        # Mark matching scorecard confidence
        for sc in scorecards:
            if sc.get("index") == a.get("index"):
                conf = a.get("confidence") or "news_unconfirmed"
                if conf == "provider_confirmed" or sc.get("confidence") != "provider_confirmed":
                    sc["confidence"] = conf

    index_ids = [sc["index"] for sc in scorecards if sc.get("index") != "_security"]
    next_ev = next_calendar_for_indices(calendar, index_ids, today)
    days_out = next_ev.get("days_out") if next_ev else None

    # Primary watch scorecard for probability
    watch_sc = None
    for sc in scorecards:
        if sc.get("status") in {"inclusion_candidate", "deletion_risk"}:
            watch_sc = sc
            break
    if watch_sc is None and scorecards:
        watch_sc = scorecards[0]
    prob = inclusion_probability_band(watch_sc or {}, days_out, rules) if watch_sc else "n_a"

    confirmed_soon = False
    for ev in confirmed_events:
        eff = parse_date(ev.get("effective"))
        d = days_until(eff, today)
        if d is not None and 0 <= d <= 30:
            confirmed_soon = True

    # Deletion risk from M&A-ish titles in announcements
    for ev in confirmed_events:
        if ev.get("action") == "delete":
            for sc in scorecards:
                if sc.get("index") == ev.get("index") and sc.get("status") == "member":
                    sc["status"] = "deletion_risk"

    if mna_tickers and ticker in mna_tickers:
        for sc in scorecards:
            if sc.get("status") == "member":
                sc["status"] = "deletion_risk"
                sc["gating_check"] = sc.get("gating_check") or "corporate_action_news"

    pscore, shock = priority_score(scorecards, mi, days_out, rules, confirmed_soon)

    # Display badge: worst/most actionable status
    badge = "n_a"
    for pref in ("deletion_risk", "inclusion_candidate", "member", "ineligible", "n_a"):
        if any(sc.get("status") == pref for sc in scorecards):
            badge = pref
            break

    return {
        "ticker": ticker,
        "company": meta.get("company"),
        "market": meta.get("market"),
        "exchange": meta.get("exchange"),
        "current_memberships": memberships,
        "scorecards": scorecards,
        "badge_status": badge,
        "impact_proxy": {
            "demand_shock_pct_of_adv": shock,
            "priority_score": pscore,
        },
        "confirmed_events": confirmed_events,
        "prediction": {
            "next_calendar_event": next_ev,
            "inclusion_probability_band": prob,
        },
        "inputs_missing": mi.get("missing") or [],
        "security_type": sec_type,
    }


def build(today: date | None = None) -> dict:
    today = today or date.today()
    rules = load_json(DATA_DIR / "index_rules.json", {})
    calendar = load_json(DATA_DIR / "index_calendar.json", {})
    seed = load_json(DATA_DIR / "index_memberships_seed.json", {"by_ticker": {}})
    registry = load_json(REGISTRY, {"holdings": {}})
    news = load_json(NEWS_PATH, {})
    fund_cache = load_fundamentals_cache()

    harvest_news_announcements(news, today)
    announcements = load_announcements()
    seed = apply_confirmed_to_seed(seed, announcements, today)
    # Persist seed updates from provider-confirmed
    save_json(DATA_DIR / "index_memberships_seed.json", seed)
    mna_tickers = corporate_action_tickers(news)

    holdings = registry.get("holdings") or {}
    inputs_by_ticker = {}
    for ticker, meta in holdings.items():
        inputs_by_ticker[ticker] = market_inputs_for_ticker(
            ticker, holdings_meta=meta, fundamentals_cache=fund_cache
        )
    universe_ranks = build_universe_ranks(inputs_by_ticker)

    by_ticker = {}
    for ticker, meta in sorted(holdings.items()):
        by_ticker[ticker] = build_for_ticker(
            ticker,
            meta,
            rules,
            calendar,
            (seed.get("by_ticker") or {}).get(ticker) or {},
            inputs_by_ticker[ticker],
            universe_ranks,
            announcements,
            today,
            mna_tickers=mna_tickers,
        )

    inclusion_candidates = sorted(
        t
        for t, row in by_ticker.items()
        if any(sc.get("status") == "inclusion_candidate" for sc in row.get("scorecards") or [])
    )
    deletion_risks = sorted(
        t
        for t, row in by_ticker.items()
        if any(sc.get("status") == "deletion_risk" for sc in row.get("scorecards") or [])
    )
    confirmed_next_30d = []
    for t, row in by_ticker.items():
        for ev in row.get("confirmed_events") or []:
            d = days_until(parse_date(ev.get("effective")), today)
            if d is not None and 0 <= d <= 30:
                confirmed_next_30d.append(t)
                break
    high_priority = sorted(
        by_ticker.keys(),
        key=lambda t: (by_ticker[t].get("impact_proxy") or {}).get("priority_score") or 0,
        reverse=True,
    )
    high_priority_watch = [
        t
        for t in high_priority
        if (by_ticker[t].get("impact_proxy") or {}).get("priority_score", 0) >= 0.35
        or by_ticker[t].get("badge_status") in {"inclusion_candidate", "deletion_risk"}
    ][:40]

    # Calendar strip with day counts
    cal_strip = []
    for ev in calendar.get("events") or []:
        eff = parse_date(ev.get("effective"))
        cal_strip.append(
            {
                **{k: ev.get(k) for k in ("id", "index_family", "indices", "kind", "effective", "label")},
                "days_out": days_until(eff, today),
            }
        )
    cal_strip.sort(key=lambda e: (e["days_out"] is None, e["days_out"] if e["days_out"] is not None else 9999))

    payload = {
        "generated": now_iso(),
        "rules_as_of": rules.get("as_of"),
        "as_of": today.isoformat(),
        "caption": (
            "The average large-cap S&P 500 index effect has fallen to near zero since 2010; "
            "treat these as research triggers, weighted by demand-shock size, not mechanical trades."
        ),
        "by_ticker": by_ticker,
        "portfolio_summary": {
            "inclusion_candidates": inclusion_candidates,
            "deletion_risks": deletion_risks,
            "confirmed_next_30d": sorted(set(confirmed_next_30d)),
            "high_priority_watch": high_priority_watch,
            "ticker_count": len(by_ticker),
        },
        "calendar": cal_strip,
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="As-of date YYYY-MM-DD")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else date.today()
    payload = build(today=today)
    save_json(OUT_PATH, payload)
    if DOCS_OUT.parent.exists():
        save_json(DOCS_OUT, payload)
    summary = payload["portfolio_summary"]
    print(
        f"Wrote {OUT_PATH} tickers={summary['ticker_count']} "
        f"candidates={len(summary['inclusion_candidates'])} "
        f"deletion_risks={len(summary['deletion_risks'])} "
        f"high_priority={len(summary['high_priority_watch'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
