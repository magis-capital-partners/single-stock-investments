"""Assemble and audit sourced company profiles and listing-level price series."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
from bisect import bisect_left
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from statistics import median
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from fetch_equity_prices import yahoo_symbol_for
from stock_valuation_aliases import research_aliases

SCHEMA = "stock-summary.v1"
SOURCE_FILE = Path(__file__).with_name("stock_summary_sources.json")
CALENDAR_FILE = Path(__file__).with_name("stock_summary_calendars.json")
NO_COMMON_PRICE = (".CVR", ".DB", ".PS1", ".PS2", ".PS3")
MARKETS = {
    "NYQ": "XNYS",
    "NMS": "XNYS",
    "NGM": "XNYS",
    "NCM": "XNYS",
    "ASE": "XNYS",
    "PCX": "XNYS",
    "PNK": "XNYS",
    "OQB": "XNYS",
    "OQX": "XNYS",
    "TOR": "XTSE",
    "VAN": "XTSE",
    "LSE": "XLON",
    "JPX": "XTKS",
    "HKG": "XHKG",
    "STO": "XSTO",
    "ASX": "XASX",
    "PAR": "XPAR",
    "AMS": "XAMS",
    "GER": "XETR",
    "FRA": "XFRA",
    "OSL": "XOSL",
    "PHP": "XPHS",
    "EBS": "XSWX",
    "MIL": "XMIL",
    "MCE": "XMAD",
    "NSI": "XNSE",
    "BTS": "XNYS",
    "CNQ": "XTSE",
    "BRU": "XBRU",
    "VIE": "XWBO",
    "MEX": "XMEX",
    "WSE": "XWAR",
    "CPH": "XCSE",
    "ISE": "XDUB",
    "HEL": "XHEL",
    "SES": "XSES",
    "OID": "XNYS",
    "BUD": "XBUD",
    "SAO": "BVMF",
    "NZE": "XNZE",
    "BUE": "XBUE",
    "KLS": "XKLS",
    "TLV": "XTAE",
    "ATH": "XATH",
}
EXCHANGES = {
    "US": {
        "NYQ",
        "NMS",
        "NGM",
        "NCM",
        "ASE",
        "PCX",
        "BTS",
        "BTT",
        "PNK",
        "OQB",
        "OQX",
        "OTC",
        "YHD",
        "NYS",
        "NAS",
    },
    "OTC": {"PNK", "OQB", "OQX", "OTC", "YHD"},
    "CA": {"TOR", "VAN", "CNQ", "NEO"},
    "UK": {"LSE", "IOB"},
    "JP": {"JPX", "TYO"},
    "AU": {"ASX"},
    "SE": {"STO"},
    "IN": {"NSI", "BSE"},
}
UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


def read(path):
    return json.loads(path.read_bytes()) if path and path.is_file() else {}


def write(path, obj):
    path.parent.mkdir(exist_ok=True, parents=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(obj, stream, separators=(",", ":"), ensure_ascii=False)
        stream.write("\n")
    tmp.replace(path)


def captured(path):
    return gzip.decompress(path.read_bytes()) if path and path.is_file() else b""


def symbol_for(ticker, row, override=None):
    if override and override.get("quote_symbol"):
        return override["quote_symbol"]
    return yahoo_symbol_for(
        row.get("quote_ticker") or ticker, row.get("market") or "US", row.get("exchange") or ""
    )


def quote_currency(meta):
    currency = meta.get("currency")
    if currency in {"GBp", "GBX"}:
        return "GBP", 0.01
    if currency == "ILA":
        return "ILS", 0.01
    return (currency, 1) if re.fullmatch("[A-Z]{3}", currency or "") else (None, 1)


def exchange_day(timestamp, zone):
    return (UTC + timedelta(seconds=int(timestamp))).astimezone(zone).date().isoformat()


def price_capture(path, symbol, row, as_of, source_details):
    raw = captured(path)
    if not raw:
        return None
    data = json.loads(raw)
    quote_data = data.get("data") or {}
    meta = quote_data.get("meta") or {}
    if meta.get("dataGranularity") != "1d":
        return None
    venue = meta.get("exchangeName")
    market = row.get("market") or "US"
    if (
        data.get("symbol") != symbol
        or meta.get("symbol") != symbol
        or (venue not in source_details.get("venues", EXCHANGES.get(market, {venue})))
    ):
        return None
    currency, scale = quote_currency(meta)
    if not currency:
        return None
    zone = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    first = source_details.get("first_session")
    if not first and meta.get("firstTradeDate"):
        first = exchange_day(meta["firstTradeDate"], zone)
    session = lambda t: exchange_day(t, zone)
    candles = (quote_data.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    closes = {
        session(t): round(v * scale, 6)
        for t, v in zip(quote_data.get("timestamp") or [], candles, strict=False)
        if isinstance(v, (int, float))
        and math.isfinite(v)
        and v > 0
        and session(t) <= as_of
        and (not first or session(t) >= first)
    }
    return {
        "currency": currency,
        "scale": scale,
        "points": closes,
        "first_session": first,
        "source": "https://finance.yahoo.com/quote/" + quote(symbol, safe="") + "/history/",
        "exchange": venue,
        "name": meta.get("longName") or meta.get("shortName"),
        "type": meta.get("instrumentType"),
        "timezone": str(zone),
        "previous_close": meta.get("chartPreviousClose"),
        "verified_split": source_details.get("split"),
        "basis": "Split-adjusted daily close in trading currency",
    }


def combine_captures(prior, fresh, *, prefer_prior=False):
    """A shorter vendor response can extend a verified series without shrinking it."""
    if not prior or not fresh:
        return fresh or prior
    a, b = prior["points"], fresh["points"]
    if not a or not b:
        return fresh if b else prior
    common = sorted(a.keys() & b.keys())[-30:]
    if (prior["currency"], prior["exchange"]) != (fresh["currency"], fresh["exchange"]):
        return {**prior, "issue": "Listing currency or exchange changed between captures."}
    split = fresh.get("verified_split")
    if split and common:
        factor = split["factor"]
        if all(abs(b[day] / a[day] * (factor if day < split["date"] else 1) - 1) < 0.002 for day in common):
            a = {day: round(close / factor, 6) if day < split["date"] else close for day, close in a.items()}
    if len(common) < 3 and a.keys() - b.keys() and b.keys() - a.keys():
        return {
            **max((prior, fresh), key=lambda c: len(c["points"])),
            "issue": "Captures lack enough overlapping trading sessions to join.",
        }
    ratios = [b[d] / a[d] for d in common]
    if ratios and (abs(median(ratios) - 1) > 0.015 or any(abs(r - 1) > 0.04 for r in ratios)):
        return {
            **max((prior, fresh), key=lambda c: len(c["points"])),
            "issue": "Price basis changed on overlapping sessions. Corporate action review is required.",
        }
    if prefer_prior:
        prior, fresh = fresh, prior
        a, b = b, a
    sources = list(dict.fromkeys([
        fresh["source"], prior["source"], *fresh.get("sources", []), *prior.get("sources", []),
    ]))
    return {**fresh, "points": {**a, **b}, "sources": sources}


@lru_cache(maxsize=64)
def market_schedule(name, end):
    rules = calendar_overrides().get(name, {})
    if name == "XATH":
        first = date.fromisoformat(rules["first"])
        last = date.fromisoformat(min(end, rules["through"]))
        closed = set(rules["closed"])
        days = (first + timedelta(days=n) for n in range((last - first).days + 1))
        return tuple(day.isoformat() for day in days if day.weekday() < 5 and day.isoformat() not in closed)

    if name in {"XNSE", "XTAE"}:
        import pandas_market_calendars as calendars

        calendar = calendars.get_calendar("NSE" if name == "XNSE" else "TASE")
        return tuple(day.date().isoformat() for day in calendar.valid_days("1980-01-01", end))

    import exchange_calendars as calendars

    if name not in calendars.get_calendar_names():
        return ()
    bound = str(date.fromisoformat(end) + timedelta(days=10))
    try:
        cal = calendars.get_calendar(name, start="1980-01-01", end=bound)
    except ValueError:
        cal = calendars.get_calendar(name, start="2005-01-01", end=bound)
    latest = cal.date_to_session(end, direction="previous")
    sessions = tuple(str(d.date()) for d in cal.sessions_in_range(cal.first_session, latest))
    if not rules:
        return sessions
    return tuple(sorted(
        (set(sessions) - set(rules["closed"])) | {day for day in rules.get("opened", []) if day <= end}
    ))


@lru_cache(maxsize=1)
def calendar_overrides():
    return read(CALENDAR_FILE)


def expected_sessions(venue, first, end):
    name = MARKETS.get(venue)
    if not name:
        return None, []
    try:
        sessions = market_schedule(name, end)
    except (ValueError, KeyError, ImportError, TypeError):
        return None, []
    return (sessions[-1], sessions[bisect_left(sessions, first or end) :]) if sessions else (None, [])


def add_verified_close(capture, latest):
    if not capture or not latest or len(latest["points"]) != 1:
        return capture
    day, close = next(iter(latest["points"].items()))
    prior = max(capture["points"], default=None)
    anchor = latest.get("previous_close")
    if (
        prior
        and prior < day
        and anchor
        and capture["exchange"] == latest["exchange"]
        and capture["currency"] == latest["currency"]
        and abs(anchor * capture["scale"] / capture["points"][prior] - 1) < 0.001
    ):
        return {**capture, "points": {**capture["points"], day: close}}
    return capture


def normalize_archive_prices(capture, archive):
    """Move official unadjusted closes onto the same share basis as the older archive."""
    adjustments = archive.get("adjustments")
    if not capture or not adjustments or capture["basis"] == archive["basis"]:
        return capture
    points = {
        day: round(close / math.prod(action["factor"] for action in adjustments if day < action["date"]), 6)
        for day, close in capture["points"].items()
    }
    return {
        **capture,
        "basis": archive["basis"],
        "points": points,
        "sources": list(dict.fromkeys([
            *capture.get("sources", [capture["source"]]), *(action["source"] for action in adjustments),
        ])),
    }


def alternate_capture(path, override):
    record = read(path)
    if not record:
        return None
    source = record.get("source", "")
    archive = override.get("price_archive") or {}
    archive_sources = [archive.get("source"), *archive.get("supplemental_sources", [])]
    if source in archive_sources:
        currency, venue = archive["currency"], archive["venue"]
    elif source.startswith(("https://stockanalysis.com/stocks/", "https://stockanalysis.com/quote/otc/")):
        currency, venue = "USD", (override.get("venues") or ["NMS"])[0]
    else:
        return None
    columns = record.get("headers", [])
    if "Date" not in columns or "Close" not in columns:
        return None
    date_column, close_column = columns.index("Date"), columns.index("Close")
    points = {}
    for row in record["rows"]:
        try:
            day = datetime.strptime(row[date_column], "%b %d, %Y").date().isoformat()
            value = float(row[close_column].replace(",", ""))
        except (ValueError, IndexError):
            continue
        if math.isfinite(value) and value > 0:
            points[day] = value
    basis = archive.get("basis", "Daily close as reported by the source")
    if archive.get("adjustments") and source == archive["source"] and record.get("basis") != basis:
        basis = "Daily close as reported by the source"
    capture = {
        "points": points,
        "currency": currency,
        "exchange": venue,
        "source": source,
        "sources": list(dict.fromkeys([
            source, *(url for url in record.get("sources", []) if url in archive_sources),
        ])),
        "scale": 1,
        "basis": basis,
    }
    return normalize_archive_prices(capture, archive)


def price_record(capture, as_of, override, row):
    if not capture or len(capture["points"]) < 2:
        if override.get("ended"):
            return {
                "status": "ended_missing",
                "reason": "This listing ceased trading. Its historical closes await a source.",
                "source": override["source"],
                "ended": override["ended"],
            }
        return {
            "status": "unavailable",
            "reason": override.get("price_reason") or "Daily closes were unavailable for the exact listing.",
        }
    end = min(as_of, override.get("ended", as_of))
    lower = override.get("first_session") or capture.get("first_session") or ""
    name = MARKETS.get(capture["exchange"])
    rules = calendar_overrides().get(name)
    expected, sessions = expected_sessions(capture["exchange"], min(capture["points"]), end)
    session_set = set(sessions)
    points = sorted(
        (day, v) for day, v in capture["points"].items()
        if lower <= day <= end and (
            not rules or not expected or day in session_set
            or not rules.get("first", "") <= day <= rules.get("through", end)
        )
    )
    if len(points) < 2:
        return {
            "status": "unavailable",
            "reason": "Fewer than two completed daily closes were verified.",
            "source": capture["source"],
        }
    first, last = points[0][0], points[-1][0]
    prior = override.get("first_session") or capture.get("first_session")
    missing_count = sum(1 for day in sessions if first <= day <= last and day not in capture["points"])
    stale = expected and last < expected
    started_late = prior and (date.fromisoformat(first) - date.fromisoformat(prior)).days > 21
    gap = missing_count > max(2, 0.015 * len(points))
    status, reason = "complete", None
    ended = override.get("ended") or row.get("listing_status") in {"delisted", "inactive", "acquired"}
    unknown_start = capture["basis"] == "Daily close as reported by the source" and not prior
    if ended and (unknown_start or started_late or gap or override.get("ended") and last < override["ended"]):
        status, reason = "ended_partial", "The listing ended and its chart shows only the verified part of its history."
    elif ended:
        status, reason = "ended", "Trading history ends on the last verified session."
    elif capture.get("issue"):
        status, reason = "review", capture["issue"]
    elif stale:
        status, reason = "stale", "Closes after the last verified session are pending."
    elif not expected or rules and rules.get("through", end) < end:
        status, reason = "review", "The exchange calendar still needs verification."
    elif unknown_start:
        status, reason = (
            "partial",
            "Earlier history is pending. The chart starts with the first verified close.",
        )
    elif started_late:
        status, reason = "partial", "Earlier sessions are missing from the source."
    elif gap:
        status, reason = (
            "partial",
            "Some expected exchange sessions are missing. Suspensions and price gaps are under review.",
        )
    return {
        "status": status,
        "reason": " ".join(x for x in (reason, override.get("price_note")) if x) or None,
        "currency": capture["currency"],
        "exchange": capture["exchange"],
        "source": capture["source"],
        "sources": capture.get("sources", [capture["source"]]),
        "basis": capture["basis"],
        "split": override.get("split"),
        "ended": override.get("ended"),
        "listing_source": override.get("listing_source"),
        **({"calendar_sources": rules["sources"]} if rules else {}),
        "first_session": prior,
        "first": first,
        "last": last,
        "expected_last": expected,
        "missing_sessions": missing_count,
        "points": points,
    }


def short_excerpt(value):
    parts = re.split(
        r"(?<!\b[A-Z])(?<!\bInc)(?<!\bLtd)(?<!\bCorp)(?<!\bCo)(?<!\bS\.A)(?<!\bU\.S)[.!?]\s+(?=[A-Z])",
        value.strip(),
        maxsplit=1,
    )
    words = parts[0].split()
    return (
        (" ".join(words[:24]).rstrip(" ,;:.") + (" …" if len(words) > 24 else "."))
        if len(words) >= 5
        else None
    )


def vendor_profile(path, symbol):
    raw = captured(path)
    if not raw:
        return {}
    html = raw.decode("utf-8", errors="replace").replace(r"\"", '"')
    canonical = re.search(r'<link rel="canonical" href="https://finance.yahoo.com/quote/([^/"]+)', html)
    if not canonical or unquote(canonical[1]).casefold() != symbol.casefold():
        return {}
    field = re.search(r'"longBusinessSummary"\s*:\s*(?=")', html)
    if not field:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(html[field.end() :])
    except ValueError:
        return {}
    text = short_excerpt(value) if isinstance(value, str) else None
    if not text:
        return {}
    return {
        "status": "sourced",
        "text": text,
        "source": "https://finance.yahoo.com/quote/" + quote(symbol, safe="") + "/profile/",
        "observed": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
        "excerpt": True,
    }


def claim_profile(root, ticker):
    terms = read(root / ticker / "research/cvr_terms.json")
    links = [x["url"] for x in terms.get("sec_links", []) if str(x.get("url", "")).startswith("https://")]
    if terms.get("cvr_id") != ticker or not links or not terms.get("instrument_label"):
        return {}
    cap = terms.get("max_payout_usd")
    deadline = next((m.get("deadline") for m in terms.get("milestones", []) if m.get("deadline")), None)
    terms_text = (
        f"The contract caps the payment at ${cap:g} per right."
        if isinstance(cap, (float, int))
        else "Payment depends on the agreement’s milestones."
    )
    if deadline:
        terms_text += f" The first listed milestone has a {deadline} deadline."
    return {
        "status": "sourced",
        "text": terms["instrument_label"] + ". " + terms_text,
        "source": links[0],
        "observed": terms.get("as_of"),
        "nontraded": terms.get("tradeable") is False,
    }


def describe(root, ticker, override, profile_file, symbol, has_identity, alternate):
    if override.get("identity_exception"):
        return {
            "status": "identity_review",
            "reason": override["identity_exception"],
            "source": override["source"],
        }
    if override.get("description"):
        return {
            "status": "sourced",
            "text": override["description"],
            "source": override["source"],
            "source_date": override.get("source_date"),
        }
    if ticker.endswith(".CVR"):
        result = claim_profile(root, ticker)
    elif ticker.endswith(NO_COMMON_PRICE):
        result = {}
    else:
        result = vendor_profile(profile_file, symbol) if has_identity else {}
    if not result and alternate.get("source", "").startswith("https://stockanalysis.com/"):
        text = short_excerpt(alternate.get("description", ""))
        if text:
            result = {"status": "sourced", "text": text, "source": alternate["source"], "excerpt": True}
    return result or {
        "status": "source_needed",
        "reason": "An issuer or security description with a verified source is pending.",
    }


def build(root, cache, raw_backup, as_of, core=None, previous=None, return_backup=None, *, tickers=None):
    registry = read(root / "_system/portfolio/registry.json")["holdings"]
    aliases = {k: v["ticker"] for k, v in research_aliases(root).items()}
    identity = read(SOURCE_FILE)
    rows = {r["ticker"]: r for r in read(core).get("tickers", [])}
    result = {}
    previous = previous or {}
    for ticker in sorted({aliases.get(t, t) for t in registry}):
        if tickers is not None and ticker not in tickers and ticker in previous:
            result[ticker] = previous[ticker]
            continue
        row = {**registry.get(ticker, {}), **rows.get(ticker, {})}
        override = identity.get(ticker, {})
        archive = override.get("price_archive") or {}
        symbol = symbol_for(ticker, row, override)
        encoded = quote(ticker, safe="")
        fresh = prior = None
        if not override.get("identity_exception") and not ticker.endswith(NO_COMMON_PRICE):
            fresh = price_capture(cache / "daily" / (encoded + ".gz"), symbol, row, as_of, override)
            if ticker == "SNDK":
                last_quote = price_capture(cache / "daily/SNDK-last.gz", symbol, row, as_of, override)
                fresh = add_verified_close(fresh, last_quote)
            prior = price_capture(
                raw_backup / (encoded + ".json.gz") if raw_backup else None, symbol, row, as_of, override
            )
        old = previous.get(ticker, {})
        saved = old.get("price") or {}
        if (
            not prior
            and saved.get("points")
            and saved.get("symbol") == symbol
            and not override.get("identity_exception")
        ):
            currency, scale = quote_currency({"currency": saved["currency"]})
            prior = {
                **saved,
                "currency": currency,
                "points": {day: round(close * scale, 6) for day, close in saved["points"]},
                "scale": fresh["scale"] if fresh and fresh["currency"] == currency else scale,
            }
            prior = normalize_archive_prices(prior, archive)
        capture = combine_captures(prior, fresh)
        if (
            prior
            and fresh
            and prior["basis"] == "Daily close as reported by the source"
            and prior["source"].startswith("https://stockanalysis.com/")
            and prior["points"].keys() <= fresh["points"].keys()
            and (fresh["exchange"] in override.get("venues", []))
        ):
            # The old archive used a placeholder venue. An exact-listing
            # vendor capture with all previously covered dates supersedes it.
            capture = fresh
        alternate = alternate_capture(cache / "alternate" / (ticker + "-price.json"), override)
        if alternate and capture and (
            alternate["source"] == capture["source"] or override.get("supplement_history")
        ):
            # The fallback can fill gaps without replacing a confirmed TMX close.
            use_primary = alternate["source"] == archive.get("ft_source") and capture["source"] == archive["source"]
            capture = combine_captures(capture, alternate, prefer_prior=use_primary)
        elif alternate and (not capture or len(alternate["points"]) > len(capture["points"])):
            # A replacement archive must cover the prior date range before it
            # can supersede a previously verified chart.
            if not capture or not (capture["points"].keys() - alternate["points"].keys()):
                capture = alternate
        description = describe(
            root,
            ticker,
            override,
            cache / "profiles" / (encoded + ".gz"),
            symbol,
            bool(capture),
            read(cache / "alternate" / (ticker + "-profile.json")),
        )
        if description["status"] == "source_needed" and old.get("description", {}).get("status") == "sourced":
            description = old["description"]
        if (
            not capture
            and saved.get("points")
            and saved.get("basis") == "Daily close as reported by the source"
        ):
            capture = {**saved, "points": dict(saved["points"])}
        price = price_record(capture, as_of, override, row)
        price["symbol"] = symbol
        if description.get("nontraded"):
            price = {
                "status": "not_traded",
                "reason": "The agreement identifies this contingent right as non-traded.",
                "source": description["source"],
            }
        if description["status"] == "identity_review":
            price = {
                "status": "identity_review",
                "reason": description["reason"],
                "source": description["source"],
            }
        result[ticker] = {
            "schema": SCHEMA,
            "ticker": ticker,
            "company": override.get("company") or row.get("company") or ticker,
            "description": description,
            "price": price,
        }
        return_stats = old.get("returns") or {}
        if return_backup:
            saved_return = read(return_backup / (encoded + ".json"))
            observed_return = (saved_return.get("one_pager") or {}).get("performance") or saved_return
            return_stats = {
                "status": observed_return.get("status", "unavailable"),
                "as_of": observed_return.get("as_of"),
            }
        if ticker == "SNDK" and price.get("points"):
            # The daily provider price and adjusted-close series are equal
            # across the newly listed security's observed history.
            raw = captured(cache / "daily" / (encoded + ".gz"))
            quotes = json.loads(raw).get("data", {}).get("indicators", {}) if raw else {}
            adjusted = (quotes.get("adjclose") or [{}])[0].get("adjclose", [])
            closes = (quotes.get("quote") or [{}])[0].get("close", [])
            paired = [(a, b) for a, b in zip(adjusted, closes, strict=False) if a is not None and b]
            if len(paired) > 20 and all(abs(a / b - 1) < 0.00001 for a, b in paired):
                base = price["points"][0][1]
                result[ticker]["performance"] = {
                    "ticker": ticker,
                    "method_version": "split-cash-basis.v2",
                    "currency": price["currency"],
                    "status": "partial",
                    "source_url": price["source"],
                    "as_of": price["last"],
                    "basis": "Vendor adjusted-close history. Distribution verification is tracked separately.",
                    "points": [
                        [day, round(100 * v / base, 6), round(100 * v / base, 6)]
                        for day, v in price["points"]
                    ],
                }
                return_stats = {"status": "partial", "as_of": price["last"]}
        if not result[ticker].get("performance") and old.get("performance"):
            result[ticker]["performance"] = old["performance"]
        result[ticker]["returns"] = return_stats
        if ticker in aliases.values():
            result[ticker]["former_tickers"] = [a for a, t in aliases.items() if t == ticker]
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "registered": sorted(registry),
        "aliases": aliases,
        "listings": result,
    }


def audit(document):
    listings = document["listings"]
    aliases = document["aliases"]
    expected = {aliases.get(t, t) for t in document["registered"]}
    if set(listings) != expected:
        raise ValueError("Published Summary listing set differs from the registry")
    coverage = {}
    for t, row in listings.items():
        desc, price = row["description"], row["price"]
        if (
            row["ticker"] != t
            or desc.get("status") == "sourced"
            and (not desc.get("text") or not desc.get("source", "").startswith("https://"))
        ):
            raise ValueError("Invalid description identity or source for " + t)
        points = price.get("points", [])
        if points and (
            price["first"] != points[0][0]
            or price["last"] != points[-1][0]
            or any(a[0] >= b[0] for a, b in pairwise(points))
        ):
            raise ValueError("Invalid price bounds for " + t)
        coverage[t] = {
            "description": desc["status"],
            "price": price["status"],
            "price_reason": price.get("reason"),
            "first": price.get("first"),
            "last": price.get("last"),
            "sessions": len(points),
            "expected_last": price.get("expected_last"),
            "total_return": (row.get("returns") or {}).get("status", "unknown"),
            "total_return_as_of": (row.get("returns") or {}).get("as_of"),
        }
    return {
        "schema": SCHEMA,
        "as_of": document["as_of"],
        "registered": document["registered"],
        "aliases": aliases,
        "counts": {
            "descriptions": dict(Counter(v["description"] for v in coverage.values())),
            "prices": dict(Counter(v["price"] for v in coverage.values())),
            "total_returns": dict(Counter(v["total_return"] for v in coverage.values())),
        },
        "listings": coverage,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--raw-backup", type=Path)
    parser.add_argument("--return-backup", type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(
        args.root, args.cache, args.raw_backup, args.as_of, args.core, return_backup=args.return_backup
    )
    report = audit(document)
    write(args.output, document)
    write(args.output.with_name("coverage.json"), report)
    print(json.dumps(report["counts"]), flush=True)
