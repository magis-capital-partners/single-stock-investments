"""Bounded readers for the public reference files the producers use.

Network access is confined to ``https_get`` and ``ibkr_shortstock_ftp``; every
parser takes bytes/text and an observation clock, so tests never open a socket.
Nothing here logs in to a broker, a market-data vendor or NY4. No ThetaData,
Databento or IB Gateway session is ever opened.

Parsers mirror Box R's validated readers (``dashboard/cloudflare/
reverse-split-live``: ``public_borrow.py``, ``market-status-core.mjs``,
``market-status-source.mjs``) so both hosts read the same files the same way.
They never upgrade what a file proves: a positive halt or SSR listing proves a
restriction; absence from a daily restriction list proves nothing.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from _system.trading.rs_paper_executor.safety import SafetyError, timestamp

ET_ZONE = ZoneInfo("America/New_York")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,11}")
LIMIT = 8_000_000

IBKR_FTP_HOST = "ftp2.interactivebrokers.com"
IBKR_FTP_URL = "ftp://ftp2.interactivebrokers.com/usa.txt"
NASDAQ_ROOT = "https://www.nasdaqtrader.com"
HALT_URL = NASDAQ_ROOT + "/rss.aspx?feed=tradehalts"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
APPROVED_HOSTS = frozenset({"www.nasdaqtrader.com", "www.sec.gov"})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _iso(value):
    return value.astimezone(timezone.utc).isoformat()


def _eastern(day, clock):
    """``day`` is YYYY-MM-DD, ``clock`` HH:MM[:SS[.fff]] Eastern; returns UTC ISO."""
    parts = clock.split(".")[0].split(":")
    while len(parts) < 3:
        parts.append("00")
    naive = datetime.fromisoformat(day + "T" + ":".join(parts))
    return _iso(naive.replace(tzinfo=ET_ZONE))


def eastern_day(now):
    return timestamp(now).astimezone(ET_ZONE).date().isoformat()


# --------------------------------------------------------------------- network


def https_get(url, *, user_agent, limit=LIMIT, timeout=12, hosts=APPROVED_HOSTS):
    """One bounded GET to an approved public host. No redirects, no credentials."""
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise SafetyError("unapproved public source host")
    if not user_agent or "@" not in user_agent and "contact" not in user_agent.lower():
        # SEC fair access requires a declared contact; the owner supplies it via
        # config. Nothing here invents one.
        raise SafetyError("a declared User-Agent is required for public sources")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise SafetyError("public source redirect forbidden")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/plain, application/json, application/rss+xml, text/xml",
        },
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as resp:
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise SafetyError("public source exceeds its size limit")
    return data, utc_now()


def ibkr_shortstock_ftp(timeout=8):
    """IBKR's anonymous public short-stock file (user ``shortstock``, no password).

    This is a public file, not a brokerage login: no account, credential or API
    client ID is involved. The md5 sidecar must match before the bytes are used.
    """
    import ftplib

    data, checksum = bytearray(), bytearray()

    def bounded(chunk):
        if len(data) + len(chunk) > LIMIT:
            raise SafetyError("public borrow file exceeds limit")
        data.extend(chunk)

    def bounded_checksum(chunk):
        if len(checksum) + len(chunk) > 1024:
            raise SafetyError("public borrow checksum exceeds limit")
        checksum.extend(chunk)

    with ftplib.FTP() as ftp:
        ftp.connect(IBKR_FTP_HOST, timeout=timeout)
        ftp.login("shortstock", "")
        ftp.retrbinary("RETR usa.txt", bounded)
        ftp.retrbinary("RETR usa.txt.md5", bounded_checksum)
    observed = utc_now()
    expected = checksum.decode("ascii").strip().split()[0].lower()
    actual = hashlib.md5(bytes(data).replace(b"\r\n", b"\n")).hexdigest()
    if len(expected) != 32 or actual != expected:
        raise SafetyError("public borrow checksum mismatch")
    return bytes(data), observed


# ------------------------------------------------------------- IBKR shortstock


def parse_ibkr_shortstock(data, observed_at):
    """Parse ``usa.txt``: ``#BOF|YYYY.MM.DD|HH:MM:SS``, ``#SYM|...`` header,
    pipe rows, ``#EOF|<count>``. Rows are indexed by conid and by symbol.

    FEERATE is an annual percent (Box R stores it as ``apr = FEERATE / 100``);
    AVAILABLE may be ``>10000000`` meaning "at least". These are IBKR's public
    indications: availability only, never an allocated locate.
    """
    if len(data) > LIMIT:
        raise SafetyError("public borrow file exceeds limit")
    text = data.decode("utf-8-sig")
    header, as_of, declared, total = None, None, None, 0
    by_conid, by_symbol = {}, {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().split("|")]
        if line.startswith("#BOF|"):
            # Box R reads this clock as US/Eastern; kept identical on purpose.
            local = datetime.strptime(cells[1] + " " + cells[2], "%Y.%m.%d %H:%M:%S")
            as_of = _iso(local.replace(tzinfo=ET_ZONE))
        elif line.startswith("#SYM|"):
            header = [x.lstrip("#") for x in cells]
        elif line.startswith("#EOF|"):
            declared = int(cells[1])
        elif line and not line.startswith("#") and header:
            total += 1
            row = dict(zip(header, cells))
            con = row.get("CON", "")
            if not con.isdigit() or int(con) <= 0:
                continue
            available = (row.get("AVAILABLE") or "").strip()
            fee = (row.get("FEERATE") or "").strip()
            rebate = (row.get("REBATERATE") or "").strip()
            parsed = {
                "symbol": row.get("SYM", ""),
                "conid": int(con),
                "currency": row.get("CUR", ""),
                "name": row.get("NAME", ""),
                "isin": row.get("ISIN", ""),
                "apr": _percent(fee),
                "rebate_apr": _percent(rebate),
                "available_shares": int(available.lstrip(">"))
                if available.lstrip(">").isdigit()
                else None,
                "available_at_least": available.startswith(">"),
                "source_line": line.strip(),
            }
            by_conid.setdefault(parsed["conid"], []).append(parsed)
            by_symbol.setdefault(parsed["symbol"], []).append(parsed)
    if not as_of or not header or declared is None or total != declared:
        raise SafetyError("public borrow file is incomplete or has invalid metadata")
    if timestamp(as_of) > timestamp(observed_at):
        raise SafetyError("public borrow file clock is in the future")
    return {
        "as_of": as_of,
        "observed_at": observed_at,
        "source_url": IBKR_FTP_URL,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "rows": total,
        "by_conid": by_conid,
        "by_symbol": by_symbol,
    }


def _percent(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result < 0 or result > 100_000:
        return None
    return result / 100


# -------------------------------------------------------- Nasdaq halts (RSS)

NDAQ = "{http://www.nasdaqtrader.com/}"


def parse_halt_feed(data, observed_at, *, max_lag_seconds=90):
    """Nasdaq Trader's trade-halt RSS: every current halt/pause, all US markets.

    Returns the channel ``pubDate`` as ``as_of`` and each item's halt and
    resumption clocks (Eastern -> UTC). The item count must equal
    ``ndaq:numItems`` or the feed is treated as truncated.
    """
    if len(data) > 5_000_000:
        raise SafetyError("halt feed exceeds limit")
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise SafetyError("halt feed with a document type is refused")
    root = ET.fromstring(data)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SafetyError("invalid halt feed")
    try:
        as_of = _iso(parsedate_to_datetime(channel.findtext("pubDate", "")))
    except (TypeError, ValueError) as exc:
        raise SafetyError("halt feed clock missing") from exc
    lag = (timestamp(observed_at) - timestamp(as_of)).total_seconds()
    if lag < -2 or lag > max_lag_seconds:
        raise SafetyError("halt feed clock stale or future")
    declared = channel.findtext(NDAQ + "numItems", "")
    items = channel.findall("item")
    if not declared.isdigit() or int(declared) != len(items) or len(items) > 5000:
        raise SafetyError("halt feed item count mismatch")
    rows = []
    for item in items:
        ticker = (item.findtext(NDAQ + "IssueSymbol") or "").strip()
        halt_at = _feed_clock(item, "HaltDate", "HaltTime")
        resume_at = _feed_clock(item, "ResumptionDate", "ResumptionTradeTime")
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", ticker) or halt_at is None:
            raise SafetyError("invalid halt event identity")
        if timestamp(halt_at) > timestamp(as_of) + _seconds(2):
            raise SafetyError("halt event after feed clock")
        rows.append(
            {
                "ticker": ticker,
                "halt_at": halt_at,
                "resume_at": resume_at,
                "market": (item.findtext(NDAQ + "Market") or "").strip(),
                "reason": (item.findtext(NDAQ + "ReasonCode") or "").strip(),
            }
        )
    return {
        "as_of": as_of,
        "observed_at": observed_at,
        "source_url": HALT_URL,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "items": rows,
        "complete": True,
    }


def _seconds(n):
    from datetime import timedelta

    return timedelta(seconds=n)


def _feed_clock(item, day_tag, time_tag):
    day = (item.findtext(NDAQ + day_tag) or "").strip()
    clock = (item.findtext(NDAQ + time_tag) or "").strip()
    if not day or not clock:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", day)
    if not m or not re.fullmatch(r"\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?", clock):
        raise SafetyError("invalid exchange event clock")
    return _eastern(f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}", clock)


def halt_state(feed, ticker, now):
    """True/False from one fresh feed; the latest event for ``ticker`` decides."""
    events = sorted(
        (
            r
            for r in feed["items"]
            if r["ticker"] == ticker and timestamp(r["halt_at"]) <= timestamp(now)
        ),
        key=lambda r: r["halt_at"],
        reverse=True,
    )
    if not events:
        return False, None
    latest = events[0]
    halted = latest["resume_at"] is None or timestamp(latest["resume_at"]) > timestamp(
        feed["as_of"]
    )
    return halted, latest


# ------------------------------------------- Nasdaq Rule 201 restriction file


def shorthalts_url(day):
    return NASDAQ_ROOT + "/dynamic/symdir/shorthalts/shorthalts" + day.replace("-", "") + ".txt"


def parse_shorthalts(text, day, observed_at):
    """Nasdaq's dated Rule 201 file: symbols whose short-sale price test is in
    effect on ``day`` (carried in from the prior session, plus any listed
    same-day trigger). A listing proves a restriction. Absence proves nothing:
    the file is not an intraday clearance and is not used as one.
    """
    if len(text) > 5_000_000:
        raise SafetyError("restriction file exceeds limit")
    lines = text.strip().splitlines()
    expected = day.replace("-", "")
    if (
        len(lines) < 2
        or not re.fullmatch(
            r"Symbol,Security Name,Market Category,Trigger Time\s*", lines[0], re.I
        )
        or not re.fullmatch(r"\d{14}", lines[-1].strip())
        or not lines[-1].startswith(expected)
    ):
        raise SafetyError("restriction file identity or day mismatch")
    footer = lines[-1].strip()
    as_of = _eastern(day, f"{footer[8:10]}:{footer[10:12]}:{footer[12:14]}")
    if timestamp(as_of) > timestamp(observed_at) or eastern_day(observed_at) != day:
        raise SafetyError("restriction file day or clock invalid")
    symbols = {}
    for row in csv.reader(io.StringIO("\n".join(lines[1:-1]))):
        if not row:
            continue
        ticker = row[0].strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", ticker) or len(row) < 4:
            raise SafetyError("invalid restriction file row")
        symbols[ticker] = row[3].strip()
    return {
        "day": day,
        "as_of": as_of,
        "observed_at": observed_at,
        "source_url": shorthalts_url(day),
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "symbols": symbols,
        "proves": "restriction_only",
        "intraday_clearance": False,
    }


# ----------------------------------------------- Nasdaq symbol directories

# IB primary-exchange codes for otherlisted.txt's Exchange column.
OTHER_EXCHANGE = {"A": "AMEX", "N": "NYSE", "P": "ARCA", "Z": "BATS", "V": "IEX"}
NOT_COMMON = re.compile(
    r"\b(warrants?|rights?|units?|preferred|pfd|depositary|ads|adr|notes?|"
    r"debentures?|bonds?|beneficial interest|subordinated?|etf|etn|"
    r"limited partnership|partnership units?|when issued|when-issued)\b",
    re.I,
)
COMMON = re.compile(
    r"\b(common stock|common shares?|ordinary shares?|class [a-z] common|"
    r"class [a-z] ordinary|common)\b",
    re.I,
)


def parse_symbol_directory(text, name, now):
    """``nasdaqlisted.txt`` / ``otherlisted.txt`` from Nasdaq Trader's SymDir."""
    if name not in ("nasdaqlisted", "otherlisted") or len(text) > 5_000_000:
        raise SafetyError("invalid listing directory")
    lines = text.strip().splitlines()
    head = lines[0].split("|")
    footer = re.match(
        r"File Creation Time: (\d{2})(\d{2})(\d{4})(\d{2}):(\d{2})\|", lines[-1]
    )
    first = "Symbol" if name == "nasdaqlisted" else "ACT Symbol"
    if not footer or head[0] != first or "Test Issue" not in head:
        raise SafetyError("listing directory header or footer invalid")
    as_of = _eastern(
        f"{footer[3]}-{footer[1]}-{footer[2]}", f"{footer[4]}:{footer[5]}:00"
    )
    age = (timestamp(now) - timestamp(as_of)).total_seconds()
    if age < -2 or age > 36 * 3600:
        raise SafetyError("listing directory stale or future")
    col = {h: i for i, h in enumerate(head)}
    rows = {}
    for line in lines[1:-1]:
        cells = line.split("|")
        if len(cells) != len(head):
            raise SafetyError("truncated listing directory")
        symbol = cells[0]
        exchange = (
            "NASDAQ" if name == "nasdaqlisted" else OTHER_EXCHANGE.get(cells[col["Exchange"]], "")
        )
        rows[symbol] = {
            "symbol": symbol,
            "security_name": cells[col["Security Name"]],
            "test_issue": cells[col["Test Issue"]] == "Y",
            "etf": cells[col["ETF"]] == "Y",
            "financial_status": cells[col["Financial Status"]]
            if "Financial Status" in col
            else "",
            "primary_exchange": exchange,
            "directory": name,
        }
    if len(rows) < 1000:
        raise SafetyError("incomplete listing universe")
    return {
        "as_of": as_of,
        "name": name,
        "source_url": NASDAQ_ROOT + "/dynamic/SymDir/" + name + ".txt",
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "rows": rows,
    }


def security_class(listing):
    """``CS`` only for a positively named common/ordinary share, else a reason."""
    if listing is None:
        return "UNLISTED"
    if listing["test_issue"]:
        return "TEST_ISSUE"
    if listing["etf"]:
        return "ETF"
    name = listing["security_name"]
    if NOT_COMMON.search(name):
        return "NOT_COMMON"
    if not COMMON.search(name):
        return "UNRESOLVED"
    return "CS"


# ------------------------------------------------------------ SEC tickers


def parse_sec_tickers(data, observed_at):
    """``company_tickers_exchange.json``: fields [cik, name, ticker, exchange]."""
    if len(data) > LIMIT:
        raise SafetyError("SEC ticker file exceeds limit")
    loaded = json.loads(data)
    fields = loaded.get("fields")
    if fields != ["cik", "name", "ticker", "exchange"] or not isinstance(
        loaded.get("data"), list
    ):
        raise SafetyError("SEC ticker file layout changed")
    by_ticker = {}
    for cik, name, ticker, exchange in loaded["data"]:
        if isinstance(cik, int) and isinstance(ticker, str):
            by_ticker.setdefault(ticker.upper(), []).append(
                {"cik": cik, "name": name, "exchange": exchange or ""}
            )
    if len(by_ticker) < 1000:
        raise SafetyError("incomplete SEC ticker universe")
    return {
        "as_of": observed_at,
        "source_url": SEC_TICKERS_URL,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "by_ticker": by_ticker,
    }


# --------------------------------------- licensed market-status handler file

STATUS_SCHEMA = "rs_market_status.v1"


def parse_market_status(data, now, *, allowed_sources, max_age_seconds):
    """Read the local file a licensed feed handler writes (none exists yet).

    This is the plug point for whichever intraday halt/SSR source the owner
    buys. The handler, not this reader, is responsible for a gapless session;
    it states so with ``gapless: true`` and ``current_as_of`` (its last
    sequenced message or heartbeat). Each symbol's state is the latest status
    message the venue sent, e.g. a Reg SHO ``no price test in place``. A symbol
    the file does not list is unknown, never clear. A source the owner has not
    approved in config is ignored.
    """
    loaded = json.loads(data)
    if loaded.get("schema") != STATUS_SCHEMA:
        raise SafetyError("market status schema mismatch")
    source = loaded.get("source")
    if source not in allowed_sources:
        raise SafetyError("market status source not approved by the owner")
    if loaded.get("gapless") is not True:
        raise SafetyError("market status handler does not assert a gapless session")
    current = loaded.get("current_as_of")
    age = (timestamp(now) - timestamp(current)).total_seconds()
    if age < -2 or age > max_age_seconds:
        raise SafetyError("market status handler is stale")
    symbols = {}
    for ticker, row in (loaded.get("symbols") or {}).items():
        if not SYMBOL.fullmatch(ticker) or not isinstance(row, dict):
            raise SafetyError("invalid market status row")
        state = {}
        for field in ("halted", "ssr"):
            value = row.get(field)
            if value is not None and not isinstance(value, bool):
                raise SafetyError("market status flags must be boolean or null")
            state[field] = value
        symbols[ticker] = state
    return {
        "source": source,
        "as_of": _iso(timestamp(current)),
        "coverage": loaded.get("coverage", []),
        "symbols": symbols,
        "source_sha256": hashlib.sha256(data).hexdigest(),
    }
