#!/usr/bin/env python3
"""Build the buyback / share-cannibal feed from SEC EDGAR.

Share counts and cash figures come from XBRL companyfacts. Market value for
the buyback yield uses the committed price cache (index_float_adv), because
EDGAR does not carry a live price. The yield is repurchase cash divided by
market value. It is not a return per year.

Outputs:
  dashboard/data/buyback_radar.json          L0 summary (< 100 KB, envelope)
  dashboard/data/buyback_companies.json      per-company vector for the UI
  _system/data/buyback_radar/share_series.jsonl   annual history

Weekly job: data-pipeline.yml, Monday 13:15 UTC, beside the other discovery jobs.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic_io import attach_envelope, write_json_if_changed  # noqa: E402

REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
FLOAT_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "index_float_adv.json"
CIK_MAP_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json"
FEED_PATH = ROOT / "dashboard" / "data" / "buyback_radar.json"
COMPANIES_PATH = ROOT / "dashboard" / "data" / "buyback_companies.json"
SERIES_PATH = ROOT / "_system" / "data" / "buyback_radar" / "share_series.jsonl"
CACHE_DIR = ROOT / "_system" / "data" / "buyback_radar" / "cache"
SHARDS_DIR = ROOT / "dashboard" / "data" / "agent_shards"
L0_BUDGET_BYTES = 100 * 1024

USER_AGENT = "single-stock-investments research pipeline (contact: dag5wd@virginia.edu)"
MIN_INTERVAL_S = 0.12
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
HISTORY_START = "1999-01-01"

# Pace: last-twelve-months share change versus the company's own five-year pace.
PACE_SHRINK_5Y = -10.0          # percent, multi-year shrink
PACE_ISSUING_1Y = 2.0           # percent, material issuance after that shrink
PACE_FLAT_1Y = 1.5              # percent, "stopped"
PACE_ACCEL_1Y = -3.0            # percent, still retiring
PACE_ACCEL_MULTIPLE = 1.5       # 1y change at least this many times the 5y annual pace

# Grade: three questions, 0-2 points each, over the last ten fiscal years.
GRADE_YEARS = 10
STICK_HIGH = 0.80
STICK_MID = 0.50
FUND_HIGH = 1.0
FUND_MID = 0.50
DEBT_CAP = 0.25
PRICE_CHEAP = 0.85
PRICE_FAIR = 1.15
PROGRAM_ROW_PCT = 10.0         # percent of market value
BIG_CAP_USD = 10_000_000_000
SMALL_CAP_USD = 2_000_000_000

# 1.5 stays on a tight tolerance. Integer splits allow more slack because a buyback in the
# same year moves the observed ratio off the exact split.
FORWARD_TIGHT = (1.5,)
FORWARD_LOOSE = (2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 20.0, 25.0, 50.0, 100.0)
FORWARD_SPLITS = FORWARD_TIGHT + FORWARD_LOOSE
REVERSE_SPLITS = (1 / 3, 0.25, 0.2, 0.1, 0.125, 0.05, 1 / 25)
# A one-year 50% buyback is a round 1-for-2. Do not treat 0.5 as a reverse split.

FEED_ID = "buyback-radar"
COMPANIES_FEED_ID = "buyback-companies"

_rate_lock = threading.Lock()
_next_request_at = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def _throttle() -> None:
    global _next_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _next_request_at - now
        _next_request_at = max(now, _next_request_at) + MIN_INTERVAL_S
    if wait > 0:
        time.sleep(wait)


def fetch_bytes(url: str, *, timeout: int = 45) -> bytes | None:
    """GET one SEC URL. None on any failure. Caller owns the rate limit."""
    _throttle()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return raw
    except (urllib.error.URLError, TimeoutError, OSError, gzip.BadGzipFile):
        return None


def fetch_json(url: str) -> dict | None:
    raw = fetch_bytes(url)
    if not raw:
        return None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def fetch_text(url: str, *, limit: int = 1_500_000) -> str:
    raw = fetch_bytes(url)
    if not raw:
        return ""
    raw = raw[:limit]
    text = raw.decode("utf-8", errors="replace")
    return html_to_text(text)


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&#160;", " ")
        .replace("&quot;", '"')
    )
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))) if int(m.group(1)) < 65536 else " ", text)
    return re.sub(r"\s+", " ", text).strip()


def pad_cik(cik: object) -> str | None:
    try:
        return f"{int(str(cik).strip()):010d}"
    except (TypeError, ValueError):
        return None


def registry_universe() -> list[dict]:
    """US and OTC names from the portfolio registry. Non-US issuers have no EDGAR companyfacts."""
    reg = _load(REGISTRY_PATH, {})
    rows = []
    for book in ("holdings", "watchlist"):
        block = reg.get(book) or {}
        if not isinstance(block, dict):
            continue
        for ticker, entry in block.items():
            if not isinstance(entry, dict):
                continue
            market = str(entry.get("market") or "").upper()
            rows.append(
                {
                    "ticker": str(ticker).upper(),
                    "company": str(entry.get("company") or ticker),
                    "market": market or "US",
                    "cik": pad_cik((entry.get("download") or {}).get("cik")),
                    "in_registry": True,
                    "book": book,
                }
            )
    return rows


def sec_cik_map() -> dict[str, str]:
    doc = _load(CIK_MAP_PATH, {})
    if isinstance(doc, dict) and doc:
        return {str(k).upper(): pad_cik(v) or "" for k, v in doc.items()}
    fetched = fetch_json("https://www.sec.gov/files/company_tickers.json")
    out: dict[str, str] = {}
    if not fetched:
        return out
    for row in fetched.values():
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        cik = pad_cik(row.get("cik_str"))
        if ticker and cik:
            out[ticker] = cik
    return out


def resolve_cik(ticker: str, explicit: str | None, cik_map: dict[str, str]) -> str | None:
    if explicit:
        return explicit
    key = ticker.upper()
    return cik_map.get(key) or cik_map.get(key.replace(".", "-")) or cik_map.get(key.replace("-", "."))


def _facts(doc: dict, namespace: str, tag: str, unit: str) -> list[dict]:
    try:
        rows = doc["facts"][namespace][tag]["units"][unit]
    except (KeyError, TypeError):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("val") is not None]


def _is_annual_form(row: dict) -> bool:
    return str(row.get("form") or "") in ANNUAL_FORMS


def _duration_days(row: dict) -> int | None:
    start, end = row.get("start"), row.get("end")
    if not start or not end:
        return None
    try:
        d0 = datetime.strptime(str(start)[:10], "%Y-%m-%d")
        d1 = datetime.strptime(str(end)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return (d1 - d0).days


def _fy_key(row: dict) -> str | None:
    end = str(row.get("end") or "")[:10]
    if len(end) < 10 or end < HISTORY_START:
        return None
    fy = row.get("fy")
    if isinstance(fy, int) and 1990 <= fy <= 2100:
        return f"fy:{fy}"
    return f"end:{end[:4]}"


def _latest_filed(rows: list[dict]) -> dict:
    return max(rows, key=lambda row: (str(row.get("filed") or ""), str(row.get("end") or "")))


def annual_share_points(doc: dict) -> tuple[list[dict], str]:
    """One split-unadjusted share count per fiscal year.

    Prefer the 10-K cover-page count (dei:EntityCommonStockSharesOutstanding).
    Fall back to us-gaap common shares outstanding, then weighted diluted, then
    weighted basic. Older years from a weighted series are spliced on only when
    the overlap year agrees within 25 percent.
    """
    candidates = [
        ("instant_cover", _facts(doc, "dei", "EntityCommonStockSharesOutstanding", "shares")),
        ("instant", _facts(doc, "us-gaap", "CommonStockSharesOutstanding", "shares")),
        ("weighted_diluted", _facts(doc, "us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares")),
        ("weighted_basic", _facts(doc, "us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares")),
    ]
    series_by_basis: dict[str, list[dict]] = {}
    for basis, rows in candidates:
        points = _collapse_share_rows(rows, weighted=basis.startswith("weighted"))
        if points:
            series_by_basis[basis] = points
    if not series_by_basis:
        return [], "none"
    # Longest instant-style series wins; weighted extends it backward.
    primary_basis = next((b for b in ("instant_cover", "instant", "weighted_diluted", "weighted_basic") if b in series_by_basis), "none")
    primary = series_by_basis.get(primary_basis) or []
    extra_basis = "weighted_diluted" if "weighted_diluted" in series_by_basis else "weighted_basic"
    extra = series_by_basis.get(extra_basis) or []
    if primary_basis.startswith("weighted") or not extra or extra_basis == primary_basis:
        return _adjust_splits(primary), primary_basis
    spliced, basis = _splice(primary, primary_basis, extra, extra_basis)
    return _adjust_splits(spliced), basis


def _collapse_share_rows(rows: list[dict], *, weighted: bool) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not _is_annual_form(row):
            continue
        if str(row.get("fp") or "FY") not in {"FY", ""}:
            continue
        if weighted:
            days = _duration_days(row)
            if days is not None and not 300 <= days <= 400:
                continue
        key = _fy_key(row)
        if not key:
            continue
        try:
            value = float(row["val"])
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        grouped.setdefault(key, []).append(row)
    points = []
    review = False
    for key, facts in grouped.items():
        # Latest filing's accession. Multiple distinct values on that accession
        # are usually share classes. Sum them when they are the same order of
        # magnitude; otherwise keep the largest (a total sitting next to a class).
        latest_filed = max(str(fact.get("filed") or "") for fact in facts)
        same_filing = [fact for fact in facts if str(fact.get("filed") or "") == latest_filed]
        chosen = same_filing or facts
        values = sorted({round(float(fact["val"]), 2) for fact in chosen})
        share_review = False
        if len(values) == 1:
            shares = values[0]
        else:
            share_review = True
            small, large = values[0], values[-1]
            if large <= small * 3:
                shares = sum(values)
            else:
                shares = large
        best = _latest_filed(chosen)
        points.append(
            {
                "fy": best.get("fy"),
                "end": str(best.get("end") or "")[:10],
                "filed": str(best.get("filed") or "")[:10],
                "shares": shares,
                "share_review": share_review,
                "accn": best.get("accn"),
            }
        )
        review = review or share_review
    points.sort(key=lambda row: (row["end"], row["filed"]))
    # One point per fiscal year: the latest end date.
    by_fy: dict[str, dict] = {}
    for point in points:
        by_fy[_fy_key(point) or point["end"]] = point
    out = sorted(by_fy.values(), key=lambda row: row["end"])
    if review:
        for point in out:
            if point.get("share_review"):
                break
    return out


def _splice(primary: list[dict], primary_basis: str, extra: list[dict], extra_basis: str) -> tuple[list[dict], str]:
    if not primary:
        return extra, extra_basis
    first = primary[0]["end"]
    overlap = [row for row in extra if row["end"][:4] == first[:4] or abs(_days(row["end"], first)) < 200]
    if overlap:
        ratio = overlap[-1]["shares"] / primary[0]["shares"] if primary[0]["shares"] else 0
        if not 0.75 <= ratio <= 1.25:
            return primary, primary_basis
    older = [row for row in extra if row["end"] < first]
    # Drop an older point that lands in a year the primary already covers.
    primary_years = {row["end"][:4] for row in primary}
    older = [row for row in older if row["end"][:4] not in primary_years]
    if not older:
        return primary, primary_basis
    return older + primary, f"{primary_basis}+{extra_basis}_before_{first[:4]}"


def _days(a: str, b: str) -> int:
    try:
        d0 = datetime.strptime(a[:10], "%Y-%m-%d")
        d1 = datetime.strptime(b[:10], "%Y-%m-%d")
    except ValueError:
        return 10**9
    return abs((d1 - d0).days)


def _near(ratio: float, targets: tuple[float, ...], tolerance: float) -> float | None:
    best = None
    best_err = tolerance
    for target in targets:
        err = abs(ratio / target - 1.0)
        if err < best_err:
            best = target
            best_err = err
    return best


def _drop_spikes(points: list[dict]) -> tuple[list[dict], int]:
    """Drop a one-year count that is many times both neighbors, which then agree with each other.

    A split stays at the new level. A 1,000x figure that reverts the next year is a bad fact.
    A leading figure that is huge versus a stable series after it is the same kind of bad fact.
    """
    if len(points) < 3:
        return [dict(row) for row in points], 0
    drop = set()
    for i, point in enumerate(points):
        prev = points[i - 1]["shares"] if i else None
        nxt = points[i + 1]["shares"] if i + 1 < len(points) else None
        if prev and nxt and prev > 0 and nxt > 0:
            if point["shares"] > prev * 5 and point["shares"] > nxt * 5 and 0.5 <= (nxt / prev) <= 2:
                drop.add(i)
            elif point["shares"] * 5 < prev and point["shares"] * 5 < nxt and 0.5 <= (nxt / prev) <= 2:
                drop.add(i)
        elif prev is None and nxt and i + 2 < len(points) and nxt > 0:
            nxt2 = points[i + 2]["shares"]
            if point["shares"] > nxt * 20 and nxt2 > 0 and 0.5 <= (nxt2 / nxt) <= 2:
                drop.add(i)
    kept = [dict(row) for i, row in enumerate(points) if i not in drop]
    return kept, len(drop)


def _split_persists(points: list[dict], index: int) -> bool:
    """A forward split is kept only when the new share count is still there the next year."""
    if index + 1 >= len(points):
        return True
    newer = points[index]["shares"]
    following = points[index + 1]["shares"]
    if newer <= 0 or following <= 0:
        return False
    ratio = following / newer
    return 0.6 <= ratio <= 1.5


def _adjust_splits(points: list[dict]) -> list[dict]:
    """Put older counts on today's share basis when a later count jumps by a split ratio.

    A forward split (shares jump by 2x, 3x, ...) is adjusted when the new level persists.
    A reverse split is adjusted only for sharp ratios (1-for-3 and tighter). A halving is left
    alone: that is often a real buyback, and it is flagged for review instead.
    A one-year spike that reverts is removed before any of that.
    """
    points, dropped = _drop_spikes(points)
    out = [dict(row) for row in points]
    for row in out:
        row["split_factor"] = 1.0
    flagged = False
    for i in range(len(out) - 1, 0, -1):
        newer = out[i]
        older = out[i - 1]
        if older["shares"] <= 0 or newer["shares"] <= 0:
            continue
        if older.get("filed") and newer.get("filed") and older["filed"] > newer["filed"]:
            continue
        ratio = newer["shares"] / older["shares"]
        forward = None
        if ratio >= 1.4 and _split_persists(out, i):
            forward = _near(ratio, FORWARD_LOOSE, 0.08) or _near(ratio, FORWARD_TIGHT, 0.025)
        reverse = _near(ratio, REVERSE_SPLITS, 0.01) if ratio <= 0.4 else None
        factor = forward or reverse
        if factor is None:
            # A one-year move past these bounds is a separation, a reverse split, or a bad fact.
            # A 45 percent buyback stays inside the band and is not flagged.
            if ratio <= 0.35 or ratio >= 3:
                flagged = True
                newer["split_review"] = True
            continue
        for j in range(i):
            out[j]["shares"] = out[j]["shares"] * factor
            out[j]["split_factor"] = round(out[j]["split_factor"] * factor, 6)
        newer["split_applied_from_prior"] = factor
    if flagged:
        for row in out:
            row["split_review"] = row.get("split_review") or False
        if out:
            out[-1]["split_review"] = True
    if dropped and out:
        out[-1]["share_review"] = True
    return out


def annual_usd(doc: dict, tag: str) -> dict[str, float]:
    """Fiscal-year flow, latest filing wins. Keyed by fiscal year (or end year)."""
    rows = _facts(doc, "us-gaap", tag, "USD")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not _is_annual_form(row) or str(row.get("fp") or "") != "FY":
            continue
        days = _duration_days(row)
        if days is not None and not 300 <= days <= 400:
            continue
        key = _fy_key(row)
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    out = {}
    for key, facts in grouped.items():
        best = _latest_filed(facts)
        try:
            out[key] = float(best["val"])
        except (TypeError, ValueError):
            continue
    return out


def annual_shares_flow(doc: dict, tag: str) -> dict[str, float]:
    rows = _facts(doc, "us-gaap", tag, "shares")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not _is_annual_form(row) or str(row.get("fp") or "") != "FY":
            continue
        days = _duration_days(row)
        if days is not None and not 300 <= days <= 400:
            continue
        key = _fy_key(row)
        if key:
            grouped.setdefault(key, []).append(row)
    out = {}
    for key, facts in grouped.items():
        best = _latest_filed(facts)
        try:
            value = abs(float(best["val"]))
        except (TypeError, ValueError):
            continue
        if value > 0:
            out[key] = value
    return out


def _point_key(point: dict) -> str:
    fy = point.get("fy")
    if isinstance(fy, int):
        return f"fy:{fy}"
    return f"end:{str(point.get('end') or '')[:4]}"


def _pct(now: float, then: float) -> float | None:
    if then <= 0 or now <= 0:
        return None
    return round((now / then - 1.0) * 100.0, 2)


def _closest(points: list[dict], end: str, target_days: int, window: tuple[int, int]) -> dict | None:
    best = None
    best_gap = 10**9
    for point in points:
        gap = _days(point["end"], end)
        # signed age: point should be older
        try:
            age = (
                datetime.strptime(end[:10], "%Y-%m-%d") - datetime.strptime(point["end"][:10], "%Y-%m-%d")
            ).days
        except ValueError:
            continue
        if not window[0] <= age <= window[1]:
            continue
        delta = abs(age - target_days)
        if delta < best_gap:
            best = point
            best_gap = delta
    return best


def pace_signal(change_5y: float | None, change_1y: float | None, years_5: float | None) -> str | None:
    """Compare the last year with this company's own five-year annual pace.

    accelerating / steady / stopped / issuing_again. None when there is no
    shrink history to compare against.
    """
    if change_5y is None or change_1y is None or not years_5 or years_5 <= 0:
        return None
    shrunk = change_5y <= PACE_SHRINK_5Y
    if shrunk and change_1y >= PACE_ISSUING_1Y:
        return "issuing_again"
    if shrunk and abs(change_1y) < PACE_FLAT_1Y:
        return "stopped"
    ann = ((1.0 + change_5y / 100.0) ** (1.0 / years_5) - 1.0) * 100.0
    if change_1y <= PACE_ACCEL_1Y and ann < -1.0 and change_1y <= ann * PACE_ACCEL_MULTIPLE:
        return "accelerating"
    if change_1y <= -PACE_FLAT_1Y or change_5y <= PACE_SHRINK_5Y:
        return "steady"
    return None


def _letter(points: int, *, never_a: bool, partial: bool) -> str:
    if partial:
        # Price paid is missing, so six points is impossible. Four is a B.
        if points >= 4:
            return "B"
        if points == 3:
            return "C"
        if points == 2:
            return "D"
        return "E"
    if points >= 6:
        return "B" if never_a else "A"
    if points == 5:
        return "B"
    if points == 4:
        return "C"
    if points == 3:
        return "D"
    return "E"


def grade_window(rows: list[dict]) -> dict:
    """Score the last ten fiscal years. ``rows`` are oldest to newest.

    Each row may carry shares, repurchase_usd, shares_repurchased, cfo, capex,
    debt_issued, debt_repaid. Missing figures leave that question blank.
    """
    window = [row for row in rows if row.get("shares")][-GRADE_YEARS:]
    empty = {"grade": None, "grade_partial": False, "grade_points": None, "grade_reason": "not_enough_history"}
    if len(window) < 3:
        return empty
    start_shares = float(window[0]["shares"])
    end_shares = float(window[-1]["shares"])
    net = start_shares - end_shares
    gross_vals = [row["shares_repurchased"] for row in window if row.get("shares_repurchased")]
    gross = sum(gross_vals) if len(gross_vals) >= 3 else None
    never_a = False
    stick = None
    if gross and gross > 0:
        ratio = net / gross
        if ratio >= STICK_HIGH:
            stick = 2
        elif ratio >= STICK_MID:
            stick = 1
        else:
            stick = 0
            never_a = True
    elif net > start_shares * 0.05:
        stick = 1
    elif net <= 0:
        stick = 0
        never_a = True

    buy = 0.0
    buy_years = 0
    fcf = 0.0
    fcf_years = 0
    debt_net = 0.0
    debt_years = 0
    prices = []
    for row in window:
        rep = row.get("repurchase_usd")
        if isinstance(rep, (int, float)) and rep > 0:
            buy += float(rep)
            buy_years += 1
            shares_bought = row.get("shares_repurchased")
            if not shares_bought and row.get("share_decline") and row["share_decline"] > 0:
                shares_bought = row["share_decline"]
            if shares_bought and shares_bought > 0:
                prices.append(float(rep) / float(shares_bought))
        cfo, capex = row.get("cfo"), row.get("capex")
        if isinstance(cfo, (int, float)) and isinstance(capex, (int, float)):
            fcf += float(cfo) - abs(float(capex))
            fcf_years += 1
        issued, repaid = row.get("debt_issued"), row.get("debt_repaid")
        if isinstance(issued, (int, float)) or isinstance(repaid, (int, float)):
            debt_net += float(issued or 0) - abs(float(repaid or 0))
            debt_years += 1

    fund = None
    if buy > 0 and fcf_years >= 3:
        cover = fcf / buy
        if cover >= FUND_HIGH and (debt_years == 0 or debt_net <= DEBT_CAP * buy):
            fund = 2
        elif cover >= FUND_MID:
            fund = 1
        else:
            fund = 0
    elif buy <= 0:
        return {**empty, "grade_reason": "no_repurchase_cash_in_window"}

    price_pts = None
    recent = prices[-3:]
    earlier = prices[:-3]
    if len(recent) >= 1 and len(earlier) >= 2:
        med_recent = sorted(recent)[len(recent) // 2]
        med_earlier = sorted(earlier)[len(earlier) // 2]
        if med_earlier > 0:
            rel = med_recent / med_earlier
            if rel <= PRICE_CHEAP:
                price_pts = 2
            elif rel <= PRICE_FAIR:
                price_pts = 1
            else:
                price_pts = 0

    parts = [stick, fund, price_pts]
    if stick is None or fund is None:
        return {**empty, "grade_reason": "missing_stickiness_or_funding"}
    partial = price_pts is None
    total = stick + fund + (price_pts or 0)
    return {
        "grade": _letter(total, never_a=never_a, partial=partial),
        "grade_partial": partial,
        "grade_points": total,
        "grade_reason": None,
        "stickiness_points": stick,
        "funding_points": fund,
        "price_points": price_pts,
        "repurchase_years": buy_years,
    }


def build_company_row(
    *,
    ticker: str,
    company: str,
    cik: str | None,
    in_registry: bool,
    doc: dict | None,
    price: float | None,
    price_as_of: str | None,
) -> tuple[dict | None, list[dict] | None, str | None]:
    if not doc:
        return None, None, "no_companyfacts"
    points, basis = annual_share_points(doc)
    if len(points) < 2:
        return None, None, "fewer_than_two_annual_share_counts"
    repurchases = annual_usd(doc, "PaymentsForRepurchaseOfCommonStock")
    gross_shares = annual_shares_flow(doc, "StockRepurchasedDuringPeriodShares")
    if not gross_shares:
        gross_shares = annual_shares_flow(doc, "TreasuryStockSharesAcquired")
    cfo = annual_usd(doc, "NetCashProvidedByUsedInOperatingActivities")
    capex = annual_usd(doc, "PaymentsToAcquirePropertyPlantAndEquipment")
    if not capex:
        capex = annual_usd(doc, "PaymentsToAcquireProductiveAssets")
    debt_issued = annual_usd(doc, "ProceedsFromIssuanceOfLongTermDebt")
    debt_repaid = annual_usd(doc, "RepaymentsOfLongTermDebt")

    aligned = []
    prev_shares = None
    for point in points:
        key = _point_key(point)
        decline = None
        if prev_shares is not None and prev_shares > point["shares"]:
            decline = prev_shares - point["shares"]
        prev_shares = point["shares"]
        aligned.append(
            {
                **point,
                "repurchase_usd": abs(repurchases[key]) if key in repurchases else None,
                "shares_repurchased": gross_shares.get(key),
                "share_decline": decline,
                "cfo": cfo.get(key),
                "capex": abs(capex[key]) if key in capex else None,
                "debt_issued": debt_issued.get(key),
                "debt_repaid": abs(debt_repaid[key]) if key in debt_repaid else None,
            }
        )
    latest = aligned[-1]
    peak = max(aligned, key=lambda row: row["shares"])
    retired = None
    if peak["shares"] > 0:
        retired = round((1.0 - latest["shares"] / peak["shares"]) * 100.0, 2)
    year_ago = _closest(aligned[:-1], latest["end"], 365, (270, 500))
    five_ago = _closest(aligned[:-1], latest["end"], 365 * 5, (365 * 4, 365 * 6))
    change_1y = _pct(latest["shares"], year_ago["shares"]) if year_ago else None
    change_5y = _pct(latest["shares"], five_ago["shares"]) if five_ago else None
    years_5 = None
    if five_ago:
        try:
            years_5 = (
                datetime.strptime(latest["end"], "%Y-%m-%d") - datetime.strptime(five_ago["end"], "%Y-%m-%d")
            ).days / 365.25
        except ValueError:
            years_5 = None
    pace = pace_signal(change_5y, change_1y, years_5)
    # An unexplained jump (often a split the ratio list missed) makes the five-year change unusable.
    if any(point.get("split_review") for point in aligned) and change_5y is not None and abs(change_5y) > 100:
        pace = None
    graded = grade_window(aligned)

    # Last completed fiscal year with a repurchase fact, preferring the latest year
    # even when the cash number is zero (a company that stopped).
    last_rep_key = _point_key(latest)
    repurchase_usd = abs(repurchases[last_rep_key]) if last_rep_key in repurchases else None
    repurchase_fy = latest.get("fy") if last_rep_key in repurchases else None
    market_value = None
    if price and price > 0 and latest["shares"] > 0:
        market_value = price * latest["shares"]
    buyback_yield = None
    if market_value and repurchase_usd is not None and market_value > 0:
        buyback_yield = round(repurchase_usd / market_value * 100.0, 2)

    row = {
        "ticker": ticker,
        "company": company,
        "cik": cik,
        "in_registry": in_registry,
        "retired_since_peak_pct": retired,
        "peak_fy": peak.get("fy"),
        "peak_end": peak.get("end"),
        "peak_shares": round(peak["shares"]),
        "shares_now": round(latest["shares"]),
        "shares_end": latest.get("end"),
        "change_5y_pct": change_5y,
        "change_1y_pct": change_1y,
        "buyback_yield_pct": buyback_yield,
        "repurchase_fy": repurchase_fy,
        "repurchase_fy_usd": round(repurchase_usd) if repurchase_usd is not None else None,
        "market_value_usd": round(market_value) if market_value else None,
        "market_value_as_of": price_as_of if market_value else None,
        "market_value_source": "index_float_adv price times latest EDGAR share count" if market_value else None,
        "pace": pace,
        "grade": graded.get("grade"),
        "grade_partial": graded.get("grade_partial") or False,
        "grade_points": graded.get("grade_points"),
        "grade_reason": graded.get("grade_reason"),
        "share_basis": basis,
        "history_start": aligned[0].get("end"),
        "point_count": len(aligned),
        "split_review": any(point.get("split_review") for point in aligned),
        "share_review": any(point.get("share_review") for point in aligned),
    }
    series = [
        {
            "fy": point.get("fy"),
            "end": point.get("end"),
            "shares": round(point["shares"]),
            "split_factor": point.get("split_factor") or 1,
        }
        for point in aligned
    ]
    return row, series, None


def shard_buyback(row: dict) -> dict:
    """The four fields a ticker page and an agent shard show. Yield is not an IRR."""
    return {
        "retired_since_peak_pct": row.get("retired_since_peak_pct"),
        "buyback_yield_pct": row.get("buyback_yield_pct"),
        "pace": row.get("pace"),
        "grade": row.get("grade"),
        "change_5y_pct": row.get("change_5y_pct"),
        "change_1y_pct": row.get("change_1y_pct"),
        "as_of": row.get("shares_end"),
        "split_review": bool(row.get("split_review")),
        "note": (
            "Buyback yield is last fiscal year's common-stock repurchase cash as a percent of market value. "
            "It is not a return per year."
        ),
    }


def issuance_signals(rows: list[dict]) -> list[dict]:
    """issuing_again names, as candidate signals under dilution_financing. Not ranked shorts."""
    signals = []
    for row in rows:
        if row.get("pace") != "issuing_again":
            continue
        signals.append(
            {
                "framework_id": "dilution_financing",
                "kind": "candidate_signal",
                "ranked_short": False,
                "ticker": row.get("ticker"),
                "company": row.get("company"),
                "pace": "issuing_again",
                "retired_since_peak_pct": row.get("retired_since_peak_pct"),
                "change_5y_pct": row.get("change_5y_pct"),
                "change_1y_pct": row.get("change_1y_pct"),
                "grade": row.get("grade"),
                "shares_end": row.get("shares_end"),
                "note": (
                    "Share count rose over the last year after a multi-year shrink. "
                    "A candidate signal for the dilution / financing lens, not a ranked short."
                ),
            }
        )
    signals.sort(key=lambda row: (-(row.get("change_1y_pct") or 0), str(row.get("ticker"))))
    return signals


# --- filing events -------------------------------------------------------

MONEY_RE = re.compile(
    r"\$\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)\s*(billion|million|bn|mm)?",
    re.I,
)
MONTHS = {
    name: i
    for i, name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"],
        1,
    )
}
DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(20\d{2})",
    re.I,
)
ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _money_usd(match: re.Match) -> float:
    number = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    if unit in {"billion", "bn"}:
        return number * 1_000_000_000
    if unit in {"million", "mm"}:
        return number * 1_000_000
    return number


def _fmt_money(usd: float) -> str:
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.1f} billion"
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.1f} million"
    return f"${usd:,.0f}"


def _first_date(text: str) -> str | None:
    match = ISO_RE.search(text)
    if match:
        return match.group(1)
    match = DATE_RE.search(text)
    if not match:
        return None
    month = MONTHS[match.group(1).lower()]
    try:
        return date(int(match.group(3)), month, int(match.group(2))).isoformat()
    except ValueError:
        return None


def _window(text: str, needle: str, radius: int = 500) -> str:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    return text[max(0, idx - radius) : idx + radius]


def parse_tender(text: str) -> dict | None:
    """Issuer tender (SC TO-I). Returns price, odd-lot, dutch, and expiry when the text states them."""
    lowered = text.lower()
    if "tender offer" not in lowered and "offer to purchase" not in lowered:
        return None
    odd_lot = bool(re.search(r"odd[-\s]?lot", lowered))
    dutch = "dutch auction" in lowered
    fixed = (not dutch) and bool(re.search(r"purchase price of \$|fixed price", lowered))
    prices = [float(m.group(1).replace(",", "")) for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", text)]
    share_prices = [p for p in prices if 0.5 <= p <= 5000]
    low = high = None
    range_match = re.search(
        r"\$\s*([0-9]+(?:\.[0-9]{2})?)\s*(?:and|to|through|-|–)\s*\$\s*([0-9]+(?:\.[0-9]{2})?)",
        text,
        re.I,
    )
    if range_match:
        low, high = float(range_match.group(1)), float(range_match.group(2))
        if low > high:
            low, high = high, low
    elif share_prices and fixed:
        low = high = share_prices[0]
    expiry = None
    for match in re.finditer(r".{0,80}expir\w*.{0,80}", text, re.I):
        expiry = _first_date(match.group(0))
        if expiry:
            break
    if low is None and not dutch and not odd_lot:
        return None
    if low is not None and high is not None and low != high:
        one = f"${low:.2f}–${high:.2f}"
    elif low is not None:
        one = f"${low:.2f}"
    elif dutch:
        one = "Dutch auction, price range not read"
    elif odd_lot:
        one = "Odd-lot tender, price not read"
    else:
        one = "Price not read"
    kind = "Dutch auction" if dutch else ("fixed price" if fixed else "issuer tender")
    flags = []
    if dutch:
        flags.append("Dutch auction")
    if fixed and not dutch:
        flags.append("fixed price")
    if odd_lot:
        flags.append("odd-lot")
    return {
        "event_type": "issuer_tender",
        "odd_lot": odd_lot,
        "dutch_auction": dutch,
        "fixed_price": fixed,
        "price_low": low,
        "price_high": high,
        "ends": expiry,
        "one_number": one,
        "what": f"Issuer tender ({', '.join(flags) or kind}): {one}.",
        "ends_label": f"Expires {expiry}" if expiry else "Expiration date not stated in the excerpt",
    }


def parse_asr(text: str) -> dict | None:
    """A newly announced accelerated share repurchase, not a passing mention of an old one."""
    lowered = text.lower()
    needle = "accelerated share repurchase" if "accelerated share repurchase" in lowered else ""
    if not needle and "accelerated stock repurchase" in lowered:
        needle = "accelerated stock repurchase"
    if not needle:
        return None
    window = _window(text, needle, 450)
    if not re.search(r"\b(entered into|announces|announced|agreed to|will (?:repurchase|purchase)|aggregate (?:purchase )?price|notional)\b", window, re.I):
        return None
    # Skip pure completion notices that do not state a new agreement.
    if re.search(r"\b(completed|final settlement|settled)\b", window, re.I) and not re.search(
        r"\b(entered into|announces|announced|agreed)\b", window, re.I
    ):
        return None
    amounts = [(m, _money_usd(m)) for m in MONEY_RE.finditer(window)]
    amounts = [(m, v) for m, v in amounts if v >= 1_000_000]
    if not amounts:
        return None
    usd = max(v for _, v in amounts)
    ends = None
    done = re.search(r".{0,60}(complet\w+|final settlement|expected to).{0,80}", window, re.I)
    if done:
        ends = _first_date(done.group(0))
    return {
        "event_type": "accelerated_share_repurchase",
        "usd": round(usd),
        "ends": ends,
        "one_number": _fmt_money(usd),
        "what": f"Accelerated share repurchase: {_fmt_money(usd)}.",
        "ends_label": f"ASR completion {ends}" if ends else "ASR completion date not stated in the excerpt",
    }


def parse_program(text: str) -> dict | None:
    """A board authorization, not a report of shares already bought."""
    window = ""
    for needle in ("repurchase program", "share repurchase", "stock repurchase", "repurchase authorization"):
        if needle in text.lower():
            window = _window(text, needle, 400)
            break
    if not window:
        return None
    if not re.search(r"\b(authoriz\w+|approv\w+|board of directors)\b", window, re.I):
        return None
    if not re.search(r"\b(up to|additional|new|increas\w+)\b", window, re.I):
        return None
    amounts = [(m, _money_usd(m)) for m in MONEY_RE.finditer(window)]
    amounts = [(m, v) for m, v in amounts if v >= 1_000_000]
    if not amounts:
        return None
    usd = max(v for _, v in amounts)
    return {
        "event_type": "new_program",
        "usd": round(usd),
        "one_number": _fmt_money(usd),
        "what": f"New repurchase authorization: {_fmt_money(usd)}.",
        "ends": None,
        "ends_label": "Ends when the dollar cap is used or the board replaces the authorization",
    }


def classify_program(parsed: dict, market_value: float | None) -> dict:
    """A program becomes a situation row only at about 10% of market value. Smaller ones are a mention."""
    usd = float(parsed["usd"])
    pct = round(usd / market_value * 100.0, 1) if market_value and market_value > 0 else None
    parsed = dict(parsed)
    parsed["program_pct_of_market_value"] = pct
    parsed["market_value_usd"] = round(market_value) if market_value else None
    small = bool(market_value and market_value < SMALL_CAP_USD)
    if pct is not None and pct >= PROGRAM_ROW_PCT:
        parsed["row"] = True
        parsed["one_number"] = f"{pct:.1f}% of market value"
        cap = " Small cap." if small else ""
        parsed["what"] = f"New repurchase program: {_fmt_money(usd)}, {pct:.1f}% of market value.{cap}"
    else:
        parsed["row"] = False
        if pct is not None:
            parsed["mention"] = f"Program {_fmt_money(usd)}, {pct:.1f}% of market value. Not a situation row."
        else:
            parsed["mention"] = f"Program {_fmt_money(usd)}. Market value not on file, so the 10% test was not run."
    return parsed


def archive_url(cik: str, adsh: str, filename: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{adsh.replace('-', '')}/{filename}"
    )


def ticker_from_display(name: str) -> str | None:
    match = re.search(r"\(([A-Z][A-Z0-9.\-]{0,7})(?:,|\))", name or "")
    if not match:
        return None
    return match.group(1).upper()


def efts_search(query: str, forms: list[str], start: str, end: str, *, pages: int = 2) -> list[dict]:
    hits: list[dict] = []
    for page in range(pages):
        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": start,
            "enddt": end,
            "forms": ",".join(forms),
            "from": str(page * 100),
        }
        url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
        doc = fetch_json(url)
        if not doc:
            break
        batch = ((doc.get("hits") or {}).get("hits")) or []
        if not batch:
            break
        hits.extend(batch)
        total = (((doc.get("hits") or {}).get("total")) or {}).get("value") or 0
        if len(hits) >= total or len(batch) < 100:
            break
    return hits


def _hit_file(hit: dict) -> tuple[str, str, str, str] | None:
    source = hit.get("_source") or {}
    adsh = str(source.get("adsh") or "")
    ciks = source.get("ciks") or []
    if not adsh or not ciks:
        return None
    hid = str(hit.get("_id") or "")
    filename = hid.split(":", 1)[1] if ":" in hid else ""
    if not filename:
        return None
    names = source.get("display_names") or [""]
    return str(ciks[0]), adsh, filename, str(names[0] if names else "")


def discover_events(today: date, market_value_for: Any, *, offline_texts: list[dict] | None = None) -> tuple[list[dict], list[dict], dict]:
    """Return (rows, mentions, stats). ``offline_texts`` skips the network for tests."""
    stats = {"tender_hits": 0, "asr_hits": 0, "program_hits": 0, "documents_read": 0}
    found: list[dict] = []
    if offline_texts is None:
        start_tender = (today - timedelta(days=180)).isoformat()
        start_asr = (today - timedelta(days=120)).isoformat()
        start_prog = (today - timedelta(days=28)).isoformat()
        end = today.isoformat()
        groups = [
            ("tender", efts_search('"tender offer"', ["SC TO-I", "SC TO-I/A"], start_tender, end, pages=2)),
            ("asr", efts_search('"accelerated share repurchase"', ["8-K"], start_asr, end, pages=2)),
            ("program", efts_search('"repurchase program"', ["8-K"], start_prog, end, pages=2)),
        ]
        seen_acc = set()
        texts = []
        for kind, hits in groups:
            stats[f"{kind}_hits"] = len(hits)
            for hit in hits:
                parsed = _hit_file(hit)
                if not parsed:
                    continue
                cik, adsh, filename, display = parsed
                # One document per accession per kind. Prefer the filing itself over an exhibit
                # when several hits share an accession; the first primary form wins.
                key = (kind, adsh)
                if key in seen_acc:
                    continue
                file_type = str((hit.get("_source") or {}).get("file_type") or "")
                if kind != "tender" and file_type not in {"8-K", "EX-99.1", "EX-99", "8-K/A"} and "99" not in file_type:
                    # Still allow the matching file through: the hit is the page that contained the phrase.
                    pass
                seen_acc.add(key)
                url = archive_url(cik, adsh, filename)
                text = fetch_text(url)
                stats["documents_read"] += 1
                if not text:
                    continue
                texts.append(
                    {
                        "kind": kind,
                        "cik": pad_cik(cik),
                        "adsh": adsh,
                        "url": url,
                        "display": display,
                        "filed": str((hit.get("_source") or {}).get("file_date") or "")[:10],
                        "text": text,
                    }
                )
    else:
        texts = offline_texts

    mentions = []
    for item in texts:
        kind = item["kind"]
        text = item["text"]
        parsed = None
        if kind == "tender":
            parsed = parse_tender(text)
        elif kind == "asr":
            parsed = parse_asr(text)
        elif kind == "program":
            parsed = parse_program(text)
        if not parsed:
            continue
        ticker = item.get("ticker") or ticker_from_display(item.get("display") or "")
        if not ticker:
            continue
        event = {
            **parsed,
            "ticker": ticker,
            "cik": item.get("cik"),
            "accession": item.get("adsh"),
            "url": item.get("url"),
            "filed": item.get("filed"),
            "company": item.get("company") or (item.get("display") or ticker),
        }
        if kind == "program":
            event = classify_program(event, market_value_for(ticker))
            if not event.get("row"):
                mentions.append(
                    {
                        "ticker": ticker,
                        "filed": event.get("filed"),
                        "line": event.get("mention") or event.get("what"),
                        "url": event.get("url"),
                        "accession": event.get("accession"),
                        "usd": event.get("usd"),
                        "program_pct_of_market_value": event.get("program_pct_of_market_value"),
                    }
                )
                continue
        event["research_only"] = True
        event["book"] = "history" if event.get("ends") and event["ends"] < today.isoformat() else "ranked"
        found.append(event)
    # One live row per ticker and event type: the latest filing.
    found.sort(key=lambda row: (row.get("filed") or "", row.get("accession") or ""))
    dedup: dict[tuple, dict] = {}
    for event in found:
        dedup[(event["ticker"], event["event_type"])] = event
    rows = list(dedup.values())
    rows.sort(key=lambda row: (row.get("ends") or "9999-99-99", row.get("ticker") or ""))
    return rows, dedupe_mentions(mentions), stats


def dedupe_mentions(mentions: list[dict]) -> list[dict]:
    """One line per ticker. The latest filing wins."""
    ordered = sorted(mentions, key=lambda row: (row.get("filed") or "", row.get("accession") or ""))
    by_ticker = {}
    for mention in ordered:
        ticker = mention.get("ticker")
        if ticker:
            by_ticker[ticker] = mention
    out = list(by_ticker.values())
    out.sort(key=lambda row: (row.get("ticker") or ""))
    return out[:40]


METHODOLOGY = (
    "Share counts are read from SEC XBRL companyfacts, one number per fiscal year from 1999 forward when the filing has it. "
    "The preferred count is the 10-K cover page, dei:EntityCommonStockSharesOutstanding. "
    "If that tag is missing, the count is us-gaap common shares outstanding, then diluted weighted-average shares, then basic weighted-average shares. "
    "When several filings report the same year, the latest filing wins, which picks up the restatement a company makes after a split. "
    "Years that fell out of the comparative columns before a later split are multiplied by a forward split of 1.5, 2, 3, 4, 5, 7, 10, 20, 25, 50, or 100 when the share count jumps by that ratio, "
    "or by a reverse split of 1-for-3 or sharper. The new level has to still be there the next year, so a one-year spike that reverts is dropped instead of treated as the peak. A 7-for-1 is included because a buyback in the split year moves the observed ratio off the exact integer. A one-year halving is not treated as a split, because that is often a real buyback; those names are flagged split_review. "
    "Retired since peak is 100 minus the latest count divided by the highest fiscal-year count in the series. "
    "The five-year and one-year changes compare the latest count with the count about five years and one year earlier. "
    "Buyback yield is last fiscal year's PaymentsForRepurchaseOfCommonStock divided by market value. "
    "Market value is the price in index_float_adv.json times the latest EDGAR share count. EDGAR has no live price, so a name with no cached price has no yield. "
    "The yield is a percent of market value, not a return per year. "
    "Pace compares the last year with the company's own five-year pace. "
    f"issuing_again: the five-year change is {PACE_SHRINK_5Y:.0f}% or lower and the last year is up at least {PACE_ISSUING_1Y:.0f}%. "
    f"stopped: that same five-year shrink, and the last year moved less than {PACE_FLAT_1Y:.1f}%. "
    f"accelerating: the last year is down at least {abs(PACE_ACCEL_1Y):.0f}% and at least {PACE_ACCEL_MULTIPLE:.1f} times the company's own annual pace over five years. "
    "steady: still shrinking, but not faster than that pace. No pace is assigned when there is no shrink to compare. "
    "The A–E grade covers the last ten fiscal years and three questions, each scored 0, 1, or 2. "
    "Did the shares actually disappear, net of issuance: net decline in the share count divided by shares repurchased (StockRepurchasedDuringPeriodShares, else treasury shares acquired). "
    f"80% or more scores 2, {STICK_MID:.0%} or more scores 1, and below that scores 0 and cannot be an A. "
    "Was it paid for with cash the business earned: operating cash flow minus capital spending, against repurchase cash. "
    "Covering the buybacks without new debt above a quarter of the outlay scores 2. Covering half scores 1. "
    "What was paid versus this company's own history: repurchase cash divided by shares bought that year, latest three years against the earlier years in the window. "
    "Paying 85% or less of that history scores 2. Paying up to 115% scores 1. "
    "Six points is an A, five a B, four a C, three a D, two or fewer an E. "
    "If the price-paid figure cannot be computed, the letter is marked partial and cannot be an A. "
    "A letter is withheld when repurchase cash, the share-count path, or funding cannot be read. "
    "Banks and insurers are graded with the same arithmetic. Buyback Radar withholds their letter. Treat a financial-company letter as weaker. "
    "Situation rows are only issuer tenders (SC TO-I), accelerated share repurchases announced in an 8-K, and new programs of at least about 10% of market value. "
    "A plain big-cap authorization is one line in program_mentions, not a row. "
    "Every situation row is research_only. Nothing here is a position, a stance, or an input to the base return."
)


def _notable(companies: list[dict]) -> dict:
    ranked = [
        row for row in companies
        if (row.get("retired_since_peak_pct") or 0) > 0 and not row.get("split_review")
    ]
    ranked.sort(key=lambda row: -(row.get("retired_since_peak_pct") or 0))

    def brief(row: dict) -> dict:
        return {
            "ticker": row.get("ticker"),
            "company": row.get("company"),
            "retired_since_peak_pct": row.get("retired_since_peak_pct"),
            "change_5y_pct": row.get("change_5y_pct"),
            "change_1y_pct": row.get("change_1y_pct"),
            "buyback_yield_pct": row.get("buyback_yield_pct"),
            "pace": row.get("pace"),
            "grade": row.get("grade"),
        }

    by_pace: dict[str, list] = {"accelerating": [], "stopped": [], "issuing_again": [], "steady": []}
    for row in companies:
        pace = row.get("pace")
        if pace in by_pace and len(by_pace[pace]) < 25:
            by_pace[pace].append(brief(row))
    return {"most_retired": [brief(row) for row in ranked[:25]], "by_pace": by_pace}


def assemble_feeds(
    *,
    companies: list[dict],
    events: list[dict],
    mentions: list[dict],
    gaps: list[dict],
    stats: dict,
    generated_at: str | None = None,
) -> tuple[dict, dict]:
    generated_at = generated_at or _now()
    failures = int(stats.get("fetch_failures") or 0)
    attempted = int(stats.get("attempted") or 0)
    health = "healthy"
    if attempted and failures / attempted > 0.05:
        health = "degraded"
    if not companies and attempted:
        health = "degraded"
    l0 = {
        "schema_version": "buyback_radar.v1",
        "generated_at": generated_at,
        "as_of": generated_at[:10],
        "research_only": True,
        "in_base_irr": False,
        "authority": "none",
        "description": (
            "Share-cannibal vector for the portfolio registry, plus buyback events that create a forced seller "
            "or a neglected buyer. Full per-company rows live in companies_ref. Annual history lives in series_ref. "
            "This file stays under 100 KB."
        ),
        "methodology": METHODOLOGY,
        "companies_ref": "dashboard/data/buyback_companies.json",
        "series_ref": "_system/data/buyback_radar/share_series.jsonl",
        "counts": {
            "companies": len(companies),
            "with_yield": sum(1 for row in companies if row.get("buyback_yield_pct") is not None),
            "with_grade": sum(1 for row in companies if row.get("grade")),
            "pace": {
                pace: sum(1 for row in companies if row.get("pace") == pace)
                for pace in ("accelerating", "steady", "stopped", "issuing_again")
            },
            "events": len(events),
            "program_mentions": len(mentions),
            "gaps": len(gaps),
            "skipped_non_us": stats.get("skipped_non_us") or 0,
        },
        "notable": _notable(companies),
        "events": events,
        "program_mentions": mentions,
        "gaps_sample": gaps[:25],
        "discovery": {key: stats.get(key) for key in ("tender_hits", "asr_hits", "program_hits", "documents_read", "fetch_failures", "from_local_facts")},
    }
    l0 = attach_envelope(
        l0,
        feed_id=FEED_ID,
        as_of=l0["as_of"],
        row_count=len(companies),
        upstream_inputs=[
            {"path": "_system/portfolio/registry.json", "role": "universe"},
            {"path": "SEC EDGAR companyfacts", "role": "share counts and cash flows"},
            {"path": "_system/reference/market-data/fundamentals/index_float_adv.json", "role": "price for market value"},
        ],
        health_status=health,
        structural_errors=0,
    )
    companies_doc = attach_envelope(
        {
            "schema_version": "buyback_companies.v1",
            "generated_at": generated_at,
            "as_of": generated_at[:10],
            "research_only": True,
            "in_base_irr": False,
            "authority": "none",
            "description": "Per-company buyback vector. Not an L0 file. The summary agents should open first is dashboard/data/buyback_radar.json.",
            "unit_note": "buyback_yield_pct is a percent of market value, not percent per year. retired and change figures are percents of the share count.",
            "companies": companies,
            "issuance_signals": issuance_signals(companies),
        },
        feed_id=COMPANIES_FEED_ID,
        as_of=generated_at[:10],
        row_count=len(companies),
        health_status=health,
    )
    return l0, companies_doc


def _local_facts(ticker: str, cik: str | None) -> dict | None:
    candidates = []
    folder = ROOT / ticker / "research" / "evidence" / "sec_companyfacts.json"
    if folder.is_file():
        candidates.append(folder)
    if cik:
        cached = CACHE_DIR / f"{cik}.json"
        if cached.is_file():
            candidates.append(cached)
    if not candidates:
        return None
    path = max(candidates, key=lambda item: item.stat().st_mtime)
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    if age_days > 8:
        return None
    doc = _load(path, {})
    return doc if isinstance(doc, dict) and doc.get("facts") else None


def _store_cache(cik: str, doc: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / f"{cik}.json"
    target.write_text(json.dumps(doc), encoding="utf-8")


def _price_map() -> tuple[dict[str, float], str | None]:
    doc = _load(FLOAT_PATH, {})
    as_of = doc.get("as_of") if isinstance(doc, dict) else None
    out = {}
    for ticker, row in (doc.get("by_ticker") or {}).items():
        if isinstance(row, dict) and isinstance(row.get("price"), (int, float)) and row["price"] > 0:
            out[str(ticker).upper()] = float(row["price"])
    return out, as_of if isinstance(as_of, str) else None


def load_company_rows(*, offline: bool, tickers: set[str] | None, refresh: bool) -> tuple[list[dict], list[dict], dict[str, list], dict]:
    universe = registry_universe()
    cik_map = sec_cik_map() if not offline else _load(CIK_MAP_PATH, {})
    if not isinstance(cik_map, dict):
        cik_map = {}
    prices, price_as_of = _price_map()
    companies: list[dict] = []
    gaps: list[dict] = []
    series_out: dict[str, list] = {}
    stats = {"attempted": 0, "fetch_failures": 0, "skipped_non_us": 0, "from_local_facts": 0}
    for entry in universe:
        ticker = entry["ticker"]
        if tickers and ticker not in tickers:
            continue
        if entry["market"] not in {"US", "OTC"}:
            stats["skipped_non_us"] += 1
            continue
        cik = resolve_cik(ticker, entry.get("cik"), cik_map)
        stats["attempted"] += 1
        if stats["attempted"] % 50 == 0:
            print(
                f"buyback progress attempted={stats['attempted']} "
                f"rows={len(companies)} local={stats['from_local_facts']} failures={stats['fetch_failures']}",
                flush=True,
            )
        doc = None if refresh else _local_facts(ticker, cik)
        if doc:
            stats["from_local_facts"] += 1
        elif offline or not cik:
            gaps.append({"ticker": ticker, "reason": "no_cik" if not cik else "no_local_companyfacts"})
            continue
        else:
            doc = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
            if not doc or not doc.get("facts"):
                stats["fetch_failures"] += 1
                gaps.append({"ticker": ticker, "reason": "companyfacts_fetch_failed"})
                continue
            _store_cache(cik, doc)
        company = entry["company"]
        if doc.get("entityName"):
            company = str(doc["entityName"]).replace("\xa0", " ").strip() or company
        row, series, reason = build_company_row(
            ticker=ticker,
            company=company,
            cik=cik,
            in_registry=True,
            doc=doc,
            price=prices.get(ticker),
            price_as_of=price_as_of,
        )
        if reason or row is None or series is None:
            gaps.append({"ticker": ticker, "reason": reason or "unparsed"})
            continue
        companies.append(row)
        series_out[ticker] = series
    companies.sort(key=lambda row: (-(row.get("retired_since_peak_pct") or -999), row["ticker"]))
    return companies, gaps, series_out, stats


def add_event_companies(events: list[dict], companies: list[dict], series_out: dict, *, offline: bool) -> None:
    """A large new program outside the registry still gets a company row when companyfacts will load."""
    known = {row["ticker"] for row in companies}
    prices, price_as_of = _price_map()
    for event in events:
        ticker = str(event.get("ticker") or "")
        if not ticker or ticker in known:
            continue
        if event.get("event_type") != "new_program":
            continue
        cik = pad_cik(event.get("cik"))
        doc = _local_facts(ticker, cik)
        if doc is None and not offline and cik:
            doc = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
            if doc and doc.get("facts"):
                _store_cache(cik, doc)
        if not doc:
            continue
        row, series, reason = build_company_row(
            ticker=ticker,
            company=str(event.get("company") or ticker),
            cik=cik,
            in_registry=False,
            doc=doc,
            price=prices.get(ticker),
            price_as_of=price_as_of,
        )
        if row and series and not reason:
            companies.append(row)
            series_out[ticker] = series
            known.add(ticker)


def write_series(series_out: dict[str, list]) -> None:
    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for ticker in sorted(series_out):
        lines.append(json.dumps({"ticker": ticker, "points": series_out[ticker]}, ensure_ascii=False))
    text = "\n".join(lines) + ("\n" if lines else "")
    if SERIES_PATH.is_file() and SERIES_PATH.read_text(encoding="utf-8") == text:
        return
    SERIES_PATH.write_text(text, encoding="utf-8")


def apply_to_shards(companies: list[dict], *, drop_missing: bool) -> int:
    """Stamp the four buyback fields onto existing agent shards. Does not rebuild the shard.

    ``drop_missing`` removes the block from a shard whose ticker is absent. A partial
    ticker run leaves every other shard alone.
    """
    written = 0
    by_ticker = {row["ticker"]: row for row in companies}
    if not SHARDS_DIR.is_dir():
        return 0
    for path in sorted(SHARDS_DIR.glob("*.json")):
        try:
            shard = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(shard, dict):
            continue
        ticker = str(shard.get("ticker") or path.stem).upper()
        row = by_ticker.get(ticker)
        if row is None and not drop_missing:
            continue
        block = shard_buyback(row) if row else None
        if shard.get("buyback") == block:
            continue
        if block is None:
            shard.pop("buyback", None)
        else:
            shard["buyback"] = block
        prior = shard.get("_envelope") or {}
        attach_envelope(
            shard,
            feed_id=str(prior.get("feed_id") or f"agent-shard-{ticker.lower()}"),
            as_of=str(prior.get("as_of") or shard.get("as_of") or "")[:10] or None,
            row_count=int(prior.get("row_count") or 0),
            upstream_inputs=list(prior.get("upstream_inputs") or []),
            health_status=str((prior.get("health") or {}).get("status") or "healthy"),
            structural_errors=int((prior.get("health") or {}).get("structural_errors") or 0),
        )
        if write_json_if_changed(path, shard):
            written += 1
    return written


def stamp_short_alpha(companies: list[dict]) -> int:
    """Flag issuing_again names on the short-alpha feed. Does not rebuild candidates."""
    path = ROOT / "dashboard" / "data" / "short_alpha.json"
    doc = _load(path, {})
    if not isinstance(doc, dict) or not doc.get("schema_version"):
        return 0
    signals = issuance_signals(companies)
    note = (
        "Names whose share count rose over the last year after a multi-year shrink. "
        "Candidate signals for the dilution / financing lens. Not ranked shorts."
    )
    doc["buyback_issuance_signals"] = signals
    methodology = doc.get("methodology")
    if isinstance(methodology, dict):
        methodology["buyback_issuance"] = note
    extra = " Buyback radar flags issuing_again names here as candidate signals, not ranked shorts."
    for row in doc.get("frameworks") or []:
        if isinstance(row, dict) and row.get("id") == "dilution_financing":
            current = str(row.get("source_note") or "")
            if "issuing_again" not in current:
                row["source_note"] = current.rstrip() + extra
    text = json.dumps(doc, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return 0
    path.write_text(text, encoding="utf-8")
    return len(signals)


def load_companies_index(path: Path | None = None) -> dict[str, dict]:
    doc = _load(path or COMPANIES_PATH, {})
    rows = doc.get("companies") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return {}
    return {str(row.get("ticker") or "").upper(): row for row in rows if isinstance(row, dict) and row.get("ticker")}


def build(*, offline: bool = False, tickers: set[str] | None = None, skip_events: bool = False, refresh: bool = False, write_shards: bool = True, write: bool = True) -> dict:
    companies, gaps, series_out, stats = load_company_rows(offline=offline, tickers=tickers, refresh=refresh)
    # Market value for a program is the company row's figure. A name with no share count
    # has no market value, so its program stays a mention instead of a situation row.
    def mv(ticker: str) -> float | None:
        for row in companies:
            if row["ticker"] == str(ticker).upper() and row.get("market_value_usd"):
                return float(row["market_value_usd"])
        return None

    events: list[dict] = []
    mentions: list[dict] = []
    if not skip_events:
        events, mentions, event_stats = discover_events(date.today(), mv, offline_texts=[] if offline else None)
        # offline_texts=[] means "do not hit the network and do not parse". The CLI
        # default discovers. Tests call discover_events directly.
        if offline:
            events, mentions, event_stats = [], [], {}
        stats.update(event_stats)
        add_event_companies(events, companies, series_out, offline=offline)
        # Recompute program percent now that outside names may have a market value.
        repriced = []
        still_mentions = list(mentions)
        for event in events:
            if event.get("event_type") == "new_program" and event.get("usd"):
                event = classify_program(event, mv(event["ticker"]))
                event["research_only"] = True
                event["book"] = "ranked"
                if not event.get("row"):
                    still_mentions.append(
                        {
                            "ticker": event.get("ticker"),
                            "filed": event.get("filed"),
                            "line": event.get("mention"),
                            "url": event.get("url"),
                            "accession": event.get("accession"),
                            "usd": event.get("usd"),
                            "program_pct_of_market_value": event.get("program_pct_of_market_value"),
                        }
                    )
                    continue
            repriced.append(event)
        events = repriced
        mentions = dedupe_mentions(still_mentions)
    l0, companies_doc = assemble_feeds(companies=companies, events=events, mentions=mentions, gaps=gaps, stats=stats)
    raw = json.dumps(l0, indent=2, ensure_ascii=False)
    if len(raw.encode("utf-8")) >= L0_BUDGET_BYTES:
        # Drop the pace lists before the leaderboard. Events stay: the situations desk reads them here.
        l0["notable"]["by_pace"] = {
            key: rows[:8] for key, rows in (l0["notable"].get("by_pace") or {}).items()
        }
        l0["notable"]["most_retired"] = (l0["notable"].get("most_retired") or [])[:12]
        l0 = attach_envelope(
            {k: v for k, v in l0.items() if k != "_envelope"},
            feed_id=FEED_ID,
            as_of=l0.get("as_of"),
            row_count=len(companies),
            health_status=(l0.get("_envelope") or {}).get("health", {}).get("status") or "healthy",
        )
    encoded = json.dumps(l0, indent=2, ensure_ascii=False).encode("utf-8")
    if len(encoded) >= L0_BUDGET_BYTES:
        raise SystemExit(f"buyback_radar.json is {len(encoded)} bytes, over the 100 KB L0 budget")
    if not write:
        print(
            f"Dry run companies={len(companies)} events={len(events)} "
            f"mentions={len(mentions)} gaps={len(gaps)} bytes={len(encoded)}"
        )
        for row in companies[:12]:
            print(
                f"  {row['ticker']} retired={row.get('retired_since_peak_pct')} "
                f"yield={row.get('buyback_yield_pct')} pace={row.get('pace')} grade={row.get('grade')}"
            )
        return l0
    write_json_if_changed(FEED_PATH, l0)
    write_json_if_changed(COMPANIES_PATH, companies_doc)
    write_series(series_out)
    full_universe = tickers is None
    shards = apply_to_shards(companies, drop_missing=full_universe) if write_shards else 0
    signals = stamp_short_alpha(companies) if full_universe else 0
    print(
        f"Wrote {FEED_PATH} companies={len(companies)} events={len(events)} "
        f"mentions={len(mentions)} gaps={len(gaps)} shards={shards} "
        f"issuance_signals={signals} bytes={len(encoded)}"
    )
    return l0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="Use cached and on-disk companyfacts only. No EDGAR calls.")
    parser.add_argument("--refresh", action="store_true", help="Ignore caches and refetch companyfacts.")
    parser.add_argument("--skip-events", action="store_true", help="Do not search SC TO-I or 8-K text.")
    parser.add_argument("--no-shards", action="store_true", help="Do not stamp agent shards.")
    parser.add_argument("--write", action="store_true", help="With --tickers, also write the feeds. A partial run does not write unless this is set.")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers. Default is the registry universe.")
    parser.add_argument("--check", action="store_true", help="Validate the written L0 feed and exit.")
    args = parser.parse_args()
    if args.check:
        doc = _load(FEED_PATH, {})
        env = doc.get("_envelope") or {}
        problems = []
        if env.get("schema_version") != "magis.feed.v2":
            problems.append("envelope schema")
        if not env.get("generated_at") or not (env.get("health") or {}).get("status"):
            problems.append("envelope health")
        if not doc.get("methodology"):
            problems.append("methodology")
        size = FEED_PATH.stat().st_size if FEED_PATH.is_file() else 0
        if size >= L0_BUDGET_BYTES or size == 0:
            problems.append(f"size {size}")
        if not COMPANIES_PATH.is_file():
            problems.append("companies file missing")
        if problems:
            raise SystemExit("buyback radar check failed: " + ", ".join(problems))
        print(f"buyback radar check ok bytes={size} companies={((doc.get('counts') or {}).get('companies'))}")
        return
    tickers = {part.strip().upper() for part in args.tickers.split(",") if part.strip()} or None
    build(
        offline=args.offline,
        tickers=tickers,
        skip_events=args.skip_events,
        refresh=args.refresh,
        write_shards=not args.no_shards,
        write=args.write or tickers is None,
    )


if __name__ == "__main__":
    main()
