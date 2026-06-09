#!/usr/bin/env python3
"""Polygon Benzinga earnings calendar — verified-only normalization.

Mirrors etf-dashboard policy: never treat projected/unconfirmed dates or
missing actuals as reported earnings. Shared by transcript pipeline and dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import requests

from portfolio_news_common import POLYGON_MARKETS, load_holding_configs

LOGGER = logging.getLogger("polygon_earnings")

ROOT = Path(__file__).resolve().parents[2]
EARNINGS_CACHE_PATH = ROOT / "_system" / "data" / "earnings_calendar.json"

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or os.getenv("POLYGON_IO_API_KEY") or ""
POLYGON_BASES = (
    "https://api.polygon.io",
    "https://api.massive.com",
)
EARNINGS_PATH = "/benzinga/v1/earnings"
PROBE_TICKER = os.getenv("POLYGON_EARNINGS_PROBE_TICKER", "AAPL")

AccessStatus = Literal["ok", "forbidden", "no_key", "transient", "unknown"]

POLICY_VERSION = 2
HTTP_TIMEOUT_SEC = int(os.getenv("POLYGON_EARNINGS_HTTP_TIMEOUT_SEC", "30"))
HTTP_RETRY_TOTAL = int(os.getenv("POLYGON_EARNINGS_HTTP_RETRY_TOTAL", "3"))
POLYGON_REQS_PER_MIN = int(os.getenv("POLYGON_EARNINGS_REQS_PER_MIN", "5"))
DEFAULT_LOOKBACK_DAYS = int(os.getenv("POLYGON_EARNINGS_LOOKBACK_DAYS", "120"))
DEFAULT_LOOKAHEAD_DAYS = int(os.getenv("POLYGON_EARNINGS_LOOKAHEAD_DAYS", "45"))
CACHE_MAX_AGE_HOURS = int(os.getenv("POLYGON_EARNINGS_CACHE_MAX_AGE_HOURS", "36"))

_REQUEST_TIMESTAMPS: deque[float] = deque()


def _rate_limit() -> None:
    if POLYGON_REQS_PER_MIN <= 0:
        return
    now = time.monotonic()
    while _REQUEST_TIMESTAMPS and (now - _REQUEST_TIMESTAMPS[0]) >= 60.0:
        _REQUEST_TIMESTAMPS.popleft()
    if len(_REQUEST_TIMESTAMPS) < POLYGON_REQS_PER_MIN:
        return
    wait_s = max(0.05, 60.0 - (now - _REQUEST_TIMESTAMPS[0]) + 0.05)
    time.sleep(wait_s)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "marvin-transcript-pipeline/1.0 (+https://github.com/GoldmanDrew/single-stock-investments)",
        "Accept": "application/json",
    })
    return s


def _polygon_request(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    *,
    log_errors: bool = True,
) -> tuple[dict | None, int | None]:
    if not POLYGON_API_KEY:
        return None, None
    p = dict(params or {})
    p.setdefault("apiKey", POLYGON_API_KEY)
    for attempt in range(max(1, HTTP_RETRY_TOTAL + 1)):
        _rate_limit()
        try:
            resp = session.get(url, params=p, timeout=HTTP_TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001
            if log_errors:
                LOGGER.warning("polygon earnings request failed: %s", exc)
            time.sleep(0.4 * (attempt + 1))
            continue
        _REQUEST_TIMESTAMPS.append(time.monotonic())
        if resp.status_code == 429:
            time.sleep(min(20.0, 2.0 * (attempt + 1)))
            continue
        if resp.status_code >= 400:
            if log_errors:
                LOGGER.warning("polygon earnings GET %s -> %s", url, resp.status_code)
            return None, resp.status_code
        try:
            return resp.json(), resp.status_code
        except Exception:  # noqa: BLE001
            return None, resp.status_code
    return None, None


def _polygon_get(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    *,
    log_errors: bool = True,
) -> dict | None:
    payload, status_code = _polygon_request(session, url, params, log_errors=log_errors)
    if status_code == 200 and payload is not None:
        return payload
    return None


def probe_earnings_access(
    session: requests.Session | None = None,
    *,
    probe_ticker: str = PROBE_TICKER,
) -> AccessStatus:
    """Single probe before portfolio-wide fetch. Returns access status without per-ticker spam."""
    if not POLYGON_API_KEY:
        return "no_key"

    session = session or _session()
    today = date.today()
    params = {
        "ticker": probe_ticker,
        "date.gte": (today - timedelta(days=7)).isoformat(),
        "date.lte": (today + timedelta(days=7)).isoformat(),
        "limit": 1,
    }

    status_codes: list[int] = []

    def _probe_once() -> AccessStatus:
        status_codes.clear()
        for base in POLYGON_BASES:
            url = f"{base}{EARNINGS_PATH}"
            _payload, code = _polygon_request(session, url, params, log_errors=False)
            if code == 200:
                return "ok"
            if code is not None:
                status_codes.append(code)
        if status_codes and all(code == 403 for code in status_codes):
            return "forbidden"
        if any(code == 429 for code in status_codes):
            return "transient"
        if status_codes:
            return "unknown"
        return "transient"

    first = _probe_once()
    if first == "transient":
        time.sleep(1.0)
        second = _probe_once()
        return second if second != "transient" else "transient"
    return first


def _event_counts(events: list[dict]) -> dict[str, int]:
    return {
        "event_count": len(events),
        "verified_count": sum(1 for e in events if e.get("verified")),
        "reported_count": sum(1 for e in events if e.get("reported")),
    }


def _build_payload(
    events: list[dict],
    errors: list[dict],
    *,
    date_from: date,
    date_to: date,
    access_status: AccessStatus,
    fetch_skipped: bool = False,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "as_of": now,
        "policy_version": POLICY_VERSION,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "polygon_enabled": bool(POLYGON_API_KEY),
        "access_status": access_status,
        "access_checked_at": now,
        "fetch_skipped": fetch_skipped,
        "events": events,
        "errors": errors,
    }
    payload.update(_event_counts(events))
    return payload


def merge_earnings_cache_payload(existing: dict, incoming: dict) -> dict:
    """Merge fetch result with existing cache; never wipe events on access denial."""
    existing = existing or {}
    access = incoming.get("access_status", "unknown")
    fetch_skipped = bool(incoming.get("fetch_skipped"))
    existing_events = existing.get("events") or []
    incoming_events = incoming.get("events") or []

    if access == "ok" and incoming_events:
        return incoming

    if access == "ok" and not fetch_skipped:
        return incoming

    if fetch_skipped or access in ("forbidden", "no_key", "transient"):
        out = dict(incoming)
        if existing_events:
            out["events"] = existing_events
            out.update(_event_counts(existing_events))
            out["events_source"] = "cache_preserved"
            out["cache_preserved"] = True
        return out

    if not incoming_events and existing_events:
        out = dict(incoming)
        out["events"] = existing_events
        out.update(_event_counts(existing_events))
        out["events_source"] = "cache_preserved"
        out["cache_preserved"] = True
        return out

    return incoming


def resolve_earnings_events(fetch_payload: dict, cache: dict | None = None) -> list[dict]:
    """Return events for downstream use, preserving cache when fetch was skipped or denied."""
    cache = cache or {}
    merged = merge_earnings_cache_payload(cache, fetch_payload)
    events = merged.get("events") or []
    if merged.get("cache_preserved"):
        LOGGER.info(
            "Using cached earnings calendar (%d events, as_of=%s)",
            len(events),
            cache.get("as_of") or "unknown",
        )
    return events


def cache_is_fresh(cache: dict, *, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
    as_of = cache.get("as_of")
    if not as_of:
        return False
    try:
        ts = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except ValueError:
        return False
    age = datetime.now(UTC) - ts
    return age <= timedelta(hours=max_age_hours)


def _paginate(
    session: requests.Session,
    base: str,
    params: dict,
    *,
    max_pages: int = 20,
) -> list[dict]:
    url = f"{base}{EARNINGS_PATH}"
    out: list[dict] = []
    next_url: str | None = url
    next_params: dict | None = params
    for _ in range(max_pages):
        if not next_url:
            break
        payload = _polygon_get(session, next_url, next_params)
        next_params = None
        if not payload:
            break
        results = payload.get("results") or []
        out.extend(results)
        next_url = payload.get("next_url")
        if next_url and POLYGON_API_KEY and "apiKey=" not in next_url:
            sep = "&" if "?" in next_url else "?"
            next_url = f"{next_url}{sep}apiKey={POLYGON_API_KEY}"
    return out


def _has_actuals(row: dict) -> bool:
    for key in ("actual_eps", "actual_revenue", "eps", "revenue"):
        val = row.get(key)
        if val is None or val == "":
            continue
        return True
    return False


def normalize_earnings_row(row: dict, *, portfolio_ticker: str, polygon_ticker: str) -> dict:
    """Return a normalized event with explicit verified flags."""
    date_status = str(row.get("date_status") or "").strip().lower()
    reported = _has_actuals(row)
    date_str = str(row.get("date") or "")[:10]

    verified = False
    verification_reason = "unverified"
    if reported:
        verified = True
        verification_reason = "reported_actuals"
    elif date_status == "confirmed" and date_str:
        verified = True
        verification_reason = "date_confirmed_scheduled"

    fiscal_period = row.get("fiscal_period") or row.get("period")
    fiscal_year = row.get("fiscal_year") or row.get("period_year")

    return {
        "portfolio_ticker": portfolio_ticker,
        "polygon_ticker": polygon_ticker,
        "date": date_str or None,
        "fiscal_period": fiscal_period,
        "fiscal_year": fiscal_year,
        "date_status": date_status or None,
        "reported": reported,
        "verified": verified,
        "verification_reason": verification_reason,
        "actual_eps": row.get("actual_eps", row.get("eps")),
        "estimated_eps": row.get("estimated_eps", row.get("eps_est")),
        "actual_revenue": row.get("actual_revenue", row.get("revenue")),
        "estimated_revenue": row.get("estimated_revenue", row.get("revenue_est")),
        "company_name": row.get("company_name") or row.get("name"),
        "importance": row.get("importance"),
        "benzinga_id": row.get("benzinga_id") or row.get("id"),
        "source": "polygon_benzinga",
        "raw": {
            k: row.get(k)
            for k in (
                "ticker",
                "date",
                "fiscal_period",
                "fiscal_year",
                "date_status",
                "actual_eps",
                "estimated_eps",
                "actual_revenue",
                "estimated_revenue",
            )
            if k in row
        },
    }


def fetch_ticker_earnings(
    polygon_ticker: str,
    *,
    date_from: date,
    date_to: date,
    session: requests.Session | None = None,
) -> list[dict]:
    if not POLYGON_API_KEY:
        return []
    session = session or _session()
    params = {
        "ticker": polygon_ticker,
        "date.gte": date_from.isoformat(),
        "date.lte": date_to.isoformat(),
        "limit": 1000,
        "sort": "date.desc",
    }
    rows: list[dict] = []
    for base in POLYGON_BASES:
        batch = _paginate(session, base, params)
        if batch:
            rows = batch
            break
    return rows


def fetch_portfolio_earnings(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch and normalize earnings for portfolio holdings (US/CA Polygon symbols)."""
    today = date.today()
    date_from = today - timedelta(days=lookback_days)
    date_to = today + timedelta(days=lookahead_days)
    configs = load_holding_configs()
    if tickers:
        configs = {t: configs[t] for t in tickers if t in configs}

    if not POLYGON_API_KEY:
        return _build_payload(
            [],
            [],
            date_from=date_from,
            date_to=date_to,
            access_status="no_key",
            fetch_skipped=True,
        )

    session = _session()
    access = probe_earnings_access(session)

    if access == "forbidden":
        LOGGER.warning("polygon earnings access denied (403); skipping portfolio fetch")
        return _build_payload(
            [],
            [],
            date_from=date_from,
            date_to=date_to,
            access_status="forbidden",
            fetch_skipped=True,
        )

    if access == "transient":
        LOGGER.warning("polygon earnings probe transient failure; skipping portfolio fetch")
        return _build_payload(
            [],
            [],
            date_from=date_from,
            date_to=date_to,
            access_status="transient",
            fetch_skipped=True,
        )

    if access != "ok":
        LOGGER.warning("polygon earnings probe returned %s; skipping portfolio fetch", access)
        return _build_payload(
            [],
            [],
            date_from=date_from,
            date_to=date_to,
            access_status=access,
            fetch_skipped=True,
        )

    events: list[dict] = []
    errors: list[dict] = []

    for portfolio_ticker, cfg in sorted(configs.items()):
        if cfg.market not in POLYGON_MARKETS or not cfg.polygon_ticker:
            continue
        poly = cfg.polygon_ticker
        try:
            raw_rows = fetch_ticker_earnings(poly, date_from=date_from, date_to=date_to, session=session)
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": portfolio_ticker, "error": str(exc)})
            continue
        for row in raw_rows:
            poly_sym = str(row.get("ticker") or poly).upper()
            if poly_sym != poly.upper():
                continue
            events.append(
                normalize_earnings_row(row, portfolio_ticker=portfolio_ticker, polygon_ticker=poly)
            )

    events.sort(key=lambda e: (e.get("date") or "", e.get("portfolio_ticker") or ""), reverse=True)

    return _build_payload(
        events,
        errors,
        date_from=date_from,
        date_to=date_to,
        access_status="ok",
        fetch_skipped=False,
    )


def save_earnings_cache(payload: dict, *, existing: dict | None = None) -> Path:
    existing = load_earnings_cache() if existing is None else existing
    merged = merge_earnings_cache_payload(existing, payload)
    EARNINGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EARNINGS_CACHE_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return EARNINGS_CACHE_PATH


def load_earnings_cache() -> dict:
    if not EARNINGS_CACHE_PATH.exists():
        return {}
    return json.loads(EARNINGS_CACHE_PATH.read_text(encoding="utf-8"))


def latest_reported_earnings(events: list[dict], portfolio_ticker: str) -> dict | None:
    """Most recent *reported* (actuals present) earnings for a ticker."""
    reported = [
        e
        for e in events
        if e.get("portfolio_ticker") == portfolio_ticker and e.get("reported") and e.get("verified")
    ]
    if not reported:
        return None
    reported.sort(key=lambda e: e.get("date") or "", reverse=True)
    return reported[0]


def earnings_needing_transcript(
    events: list[dict],
    *,
    portfolio_ticker: str,
    has_transcript_for_period,
    post_earnings_days: int = 14,
) -> list[dict]:
    """Return reported earnings in the post-earnings window missing a local transcript."""
    today = date.today()
    out: list[dict] = []
    for e in events:
        if e.get("portfolio_ticker") != portfolio_ticker:
            continue
        if not e.get("reported") or not e.get("verified"):
            continue
        d_str = e.get("date")
        if not d_str:
            continue
        try:
            ed = date.fromisoformat(d_str[:10])
        except ValueError:
            continue
        age = (today - ed).days
        if age < 0 or age > post_earnings_days:
            continue
        fp = e.get("fiscal_period")
        fy = e.get("fiscal_year")
        if has_transcript_for_period(fp, fy, ed):
            continue
        out.append(e)
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def verified_display_events(events: list[dict]) -> list[dict]:
    """Subset safe for dashboard display — verified only, no projected guesses."""
    return [e for e in events if e.get("verified")]


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Fetch verified Polygon Benzinga earnings calendar")
    parser.add_argument("--tickers", nargs="*", help="Portfolio tickers (default: all)")
    parser.add_argument("--write", action="store_true", help="Write _system/data/earnings_calendar.json")
    args = parser.parse_args()
    payload = fetch_portfolio_earnings(tickers=args.tickers)
    print(json.dumps({"event_count": payload["event_count"], "verified_count": payload["verified_count"]}, indent=2))
    if args.write:
        path = save_earnings_cache(payload)
        print(f"Wrote {path}")
