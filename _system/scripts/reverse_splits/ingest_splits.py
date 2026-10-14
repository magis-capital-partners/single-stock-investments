"""Seed reverse split events from EDGAR discovery + yfinance corporate actions."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from .config import Config, load_config
from .db import init_db
from .utils import (
    RATIO_RE,
    RateLimitedSession,
    normalize_ticker,
    pad_cik,
    parse_date,
    tqdm,
    years_ago,
)


def fetch_sec_ticker_maps(cfg: Config, http: RateLimitedSession) -> tuple[dict[str, dict], dict[str, str]]:
    """Return (cik -> meta, ticker -> cik)."""
    cache = cfg.raw_dir / "sec_company_tickers.json"
    data = None
    if cache.exists() and (date.today() - datetime.fromtimestamp(cache.stat().st_mtime).date()).days < 7:
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        urls = [
            "https://www.sec.gov/files/company_tickers.json",
            "https://www.sec.gov/files/company_tickers_exchange.json",
        ]
        last_err: Exception | None = None
        for url in urls:
            try:
                resp = http.get(url)
                data = resp.json()
                # company_tickers_exchange.json has different shape
                if isinstance(data, dict) and "data" in data and "fields" in data:
                    fields = data["fields"]
                    rows = data["data"]
                    converted = {}
                    for i, row in enumerate(rows):
                        rec = dict(zip(fields, row))
                        converted[str(i)] = {
                            "cik_str": rec.get("cik"),
                            "ticker": rec.get("ticker"),
                            "title": rec.get("name"),
                            "exchange": rec.get("exchange"),
                        }
                    data = converted
                cache.write_text(json.dumps(data), encoding="utf-8")
                break
            except Exception as e:
                last_err = e
                continue
        if data is None:
            raise RuntimeError(f"Failed to download SEC ticker map: {last_err}")

    by_cik: dict[str, dict] = {}
    by_ticker: dict[str, str] = {}
    for row in data.values():
        cik = pad_cik(row.get("cik_str"))
        ticker = normalize_ticker(row.get("ticker"))
        name = row.get("title")
        if not cik:
            continue
        by_cik[cik] = {"ticker": ticker, "name": name, "cik": cik}
        if ticker:
            by_ticker[ticker] = cik
    return by_cik, by_ticker


def classify_exchange(exchange: str | None, ticker: str | None = None) -> str:
    if not exchange:
        # Heuristic: 5-letter tickers ending in Y/F often OTC; keep unknown
        return "unknown"
    e = exchange.upper()
    listed = {"NYSE", "NASDAQ", "AMEX", "NYSEARCA", "BATS", "ARCA", "NGM", "NMS", "NCM", "NYQ", "ASE"}
    otc = {"OTC", "OTCQX", "OTCQB", "PINK", "PNK", "GREY", "OBB", "OOTC", "EXPM"}
    if e in listed or any(x in e for x in ("NYSE", "NASDAQ", "AMEX")):
        return "listed"
    if e in otc or "OTC" in e or "PINK" in e:
        return "otc"
    return "unknown"


def parse_ratio_from_text(text: str) -> tuple[float, float] | None:
    m = RATIO_RE.search(text or "")
    if not m:
        return None
    n = m.group(1) or m.group(2)
    if not n:
        return None
    try:
        old = float(n)
    except ValueError:
        return None
    if old <= 1:
        return None
    return old, 1.0


# EDGAR full-text search (efts) rejects from+size above this window and
# reports the total as {"value": 10000, "relation": "gte"} once a query is larger.
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_RESULT_WINDOW = 10_000
EDGAR_PAGE_SIZE = 100

EDGAR_REVERSE_SPLIT_FORMS = [
    "8-K",
    "8-K/A",
    "6-K",
    "6-K/A",
    "PRE 14A",
    "DEF 14A",
    "DEFA14A",
    "PRE14A",
    "DEF14A",
    "PRE 14C",
    "DEF 14C",
    "PRE 14C/A",
    "DEF 14C/A",
]

EDGAR_REVERSE_SPLIT_QUERY = (
    '"reverse stock split" OR "reverse split" OR "reverse share split" '
    'OR "share consolidation" OR "consolidation of shares"'
)

_DISPLAY_TICKER_RE = re.compile(r"\(([^)]+)\)")
_BEFORE_CIK_RE = re.compile(r"\(([^)]+)\)\s*\(\s*CIK\s+\d+\s*\)", re.IGNORECASE)
_TICKER_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
# Parentheticals that show up in legal names, not on the tape.
_NON_TICKER_TOKENS = {
    "ADR",
    "ADS",
    "AG",
    "AND",
    "BERMUDA",
    "BVI",
    "CAYMAN",
    "CLASS",
    "CO",
    "COMMON",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "GROUP",
    "HOLDINGS",
    "INC",
    "ISLANDS",
    "LIMITED",
    "LLC",
    "LP",
    "LTD",
    "NV",
    "ORDINARY",
    "PLC",
    "SA",
    "THE",
    "VIRGIN",
}


def _first_ticker_token(inner: str) -> str | None:
    tokens = [tok for tok in re.split(r"[\s,;/]+", inner.strip()) if tok]
    if not tokens or any(not _TICKER_TOKEN_RE.match(tok) for tok in tokens):
        return None
    if any(tok in _NON_TICKER_TOKENS for tok in tokens):
        return None
    return normalize_ticker(tokens[0])


def _ticker_from_display(tickers: Any) -> str | None:
    """Trading symbol from an EDGAR display name.

    Display names look like ``Issuer (TICKER) (CIK 0001234567)`` and sometimes
    list several symbols: ``Issuer (ABCD, ABCDW)``. A legal name can also
    contain a parenthetical (``Intercont (Cayman) Ltd (NCT)``); the symbol
    group is the one immediately before the CIK.
    """
    if isinstance(tickers, list):
        text = str(tickers[0]) if tickers else ""
    else:
        text = str(tickers or "")
    before_cik = _BEFORE_CIK_RE.search(text)
    if before_cik:
        ticker = _first_ticker_token(before_cik.group(1))
        if ticker:
            return ticker
    for match in _DISPLAY_TICKER_RE.finditer(text):
        ticker = _first_ticker_token(match.group(1))
        if ticker:
            return ticker
    return None


def _hit_total(payload: dict[str, Any]) -> tuple[int, str]:
    total = (payload.get("hits") or {}).get("total")
    if isinstance(total, dict):
        try:
            value = int(total.get("value") or 0)
        except (TypeError, ValueError):
            value = 0
        return value, str(total.get("relation") or "eq")
    if total is None:
        return 0, "eq"
    try:
        return int(total), "eq"
    except (TypeError, ValueError):
        return 0, "eq"


def _needs_date_split(total_n: int, relation: str) -> bool:
    if total_n > EDGAR_RESULT_WINDOW:
        return True
    # "gte" at the window means the index stopped counting; paging cannot see the rest.
    return relation == "gte" and total_n >= EDGAR_RESULT_WINDOW


def _fetch_search_page(
    http: RateLimitedSession,
    form: str,
    start: date,
    end: date,
    from_idx: int,
) -> dict[str, Any] | None:
    params = {
        "q": EDGAR_REVERSE_SPLIT_QUERY,
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
        "forms": form,
        "from": from_idx,
        "size": EDGAR_PAGE_SIZE,
    }
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = http.get(EDGAR_SEARCH_URL, params=params)
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
            last_err = ValueError("EDGAR search returned a non-object payload")
        except Exception as exc:
            last_err = exc
        if attempt < 3:
            time.sleep(1.0 * (attempt + 1))
    print(
        f"EDGAR search failed for {form} {start.isoformat()}..{end.isoformat()} from={from_idx}: {last_err}",
        file=sys.stderr,
    )
    return None


def _hits_from_rows(rows: list[dict[str, Any]], form: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for hit in rows:
        src = hit.get("_source") or {}
        entity_raw = src.get("entity_name")
        if isinstance(entity_raw, list):
            entity = entity_raw[0] if entity_raw else None
        else:
            entity = entity_raw
        cik_list = src.get("ciks") or []
        cik = pad_cik(cik_list[0]) if cik_list else None
        accession = (src.get("adsh") or src.get("accession_no") or "").replace("-", "")
        parsed.append(
            {
                "cik": cik,
                "name": entity,
                "ticker": _ticker_from_display(src.get("display_names") or src.get("tickers") or []),
                "filed_at": parse_date(src.get("file_date") or src.get("period_ending")),
                "form": src.get("form") or form,
                "accession": accession,
                "raw": src,
            }
        )
    return parsed


def _paginate_form(
    http: RateLimitedSession,
    form: str,
    start: date,
    end: date,
    first_payload: dict[str, Any],
    total_n: int,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    payload: dict[str, Any] | None = first_payload
    from_idx = 0
    while payload is not None:
        rows = (payload.get("hits") or {}).get("hits") or []
        if not rows:
            break
        hits.extend(_hits_from_rows(rows, form))
        from_idx += EDGAR_PAGE_SIZE
        if from_idx >= total_n or from_idx >= EDGAR_RESULT_WINDOW or len(rows) < EDGAR_PAGE_SIZE:
            break
        payload = _fetch_search_page(http, form, start, end, from_idx)
        if payload is None:
            print(
                f"EDGAR search for {form} {start.isoformat()}..{end.isoformat()} stopped early at offset {from_idx}",
                file=sys.stderr,
            )
            break
    return hits


def _search_form_range(
    http: RateLimitedSession,
    form: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    if start > end:
        return []
    payload = _fetch_search_page(http, form, start, end, 0)
    if payload is None:
        return []
    rows = (payload.get("hits") or {}).get("hits") or []
    total_n, relation = _hit_total(payload)
    if total_n <= 0 or not rows:
        return []
    if _needs_date_split(total_n, relation):
        if start >= end:
            print(
                f"EDGAR search for {form} on {start.isoformat()} still exceeds "
                f"the {EDGAR_RESULT_WINDOW}-hit window ({total_n} {relation}); "
                "filings past that window are omitted",
                file=sys.stderr,
            )
            return _paginate_form(http, form, start, end, payload, min(total_n, EDGAR_RESULT_WINDOW))
        mid = start + timedelta(days=(end - start).days // 2)
        print(
            f"  {form} {start.isoformat()}..{end.isoformat()} has {total_n} ({relation}); splitting date range",
            file=sys.stderr,
        )
        right = mid + timedelta(days=1)
        return _search_form_range(http, form, start, mid) + _search_form_range(http, form, right, end)
    return _paginate_form(http, form, start, end, payload, total_n)


def edgar_search_reverse_splits(
    cfg: Config,
    http: RateLimitedSession,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Discover reverse-split filings via EDGAR full-text search.

    ``end`` is inclusive. Callers that want filings through the current day
    should pass ``date.today()``. Result sets larger than the EDGAR window are
    split into non-overlapping date ranges and each piece is paged in full.
    """
    hits: list[dict[str, Any]] = []
    for form in EDGAR_REVERSE_SPLIT_FORMS:
        form_hits = _search_form_range(http, form, start, end)
        print(f"  {form}: {len(form_hits)} filings")
        hits.extend(form_hits)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for hit in hits:
        key = (hit.get("accession"), hit.get("form"), hit.get("cik"), hit.get("filed_at"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def yfinance_reverse_splits(ticker: str, start: date, end: date) -> list[dict[str, Any]]:
    import yfinance as yf  # deferred: network command only

    out: list[dict[str, Any]] = []
    try:
        t = yf.Ticker(ticker)
        # Prefer .splits; fall back to actions['Stock Splits']
        splits = None
        try:
            splits = t.splits
        except Exception:
            splits = None
        if splits is None or len(splits) == 0:
            try:
                actions = t.actions
                if actions is not None and not actions.empty and "Stock Splits" in actions.columns:
                    splits = actions["Stock Splits"]
                    splits = splits[splits != 0]
            except Exception:
                return out
        if splits is None or len(splits) == 0:
            return out
        # Avoid t.info (very slow / rate-limited); classify exchange later if needed
        exchange = None
        exchange_class = "unknown"
        for ts, factor in splits.items():
            d = parse_date(ts)
            if not d:
                continue
            dd = datetime.strptime(d, "%Y-%m-%d").date()
            if dd < start or dd > end:
                continue
            factor = float(factor)
            if factor >= 1.0:
                continue  # forward split
            split_to = 1.0
            split_from = round(1.0 / factor, 6) if factor else None
            if not split_from or split_from <= 1:
                continue
            out.append(
                {
                    "ticker": normalize_ticker(ticker),
                    "ex_date": d,
                    "effective_date": d,
                    "split_from": split_from,
                    "split_to": split_to,
                    "ratio": factor,
                    "exchange": exchange,
                    "exchange_class": exchange_class,
                    "source": "yfinance",
                }
            )
    except Exception:
        return out
    return out


def upsert_issuer(conn: sqlite3.Connection, cik: str | None, name: str | None, ticker: str | None, exchange_class: str) -> None:
    if not cik:
        return
    conn.execute(
        """
        INSERT INTO issuers (cik, name, primary_ticker, exchange_class)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cik) DO UPDATE SET
            name = COALESCE(excluded.name, issuers.name),
            primary_ticker = COALESCE(excluded.primary_ticker, issuers.primary_ticker),
            exchange_class = CASE
                WHEN excluded.exchange_class != 'unknown' THEN excluded.exchange_class
                ELSE issuers.exchange_class
            END,
            updated_at = datetime('now')
        """,
        (cik, name, ticker, exchange_class or "unknown"),
    )


def upsert_split(conn: sqlite3.Connection, row: dict[str, Any]) -> int | None:
    ticker = normalize_ticker(row.get("ticker"))
    ex_date = parse_date(row.get("ex_date"))
    if not ticker or not ex_date:
        return None
    split_from = float(row["split_from"])
    split_to = float(row["split_to"])
    ratio = float(row.get("ratio") or (split_to / split_from))
    conn.execute(
        """
        INSERT INTO reverse_splits (
            cik, ticker, exchange, exchange_class, split_from, split_to, ratio,
            first_proxy_date, announce_date, vote_date, ratio_set_date,
            effective_date, ex_date, prior_rs_count, cohort, status, confidence,
            needs_review, source, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, ex_date, split_from, split_to) DO UPDATE SET
            cik = COALESCE(excluded.cik, reverse_splits.cik),
            exchange = COALESCE(excluded.exchange, reverse_splits.exchange),
            exchange_class = CASE
                WHEN excluded.exchange_class != 'unknown' THEN excluded.exchange_class
                ELSE reverse_splits.exchange_class
            END,
            effective_date = COALESCE(excluded.effective_date, reverse_splits.effective_date),
            source = CASE
                WHEN reverse_splits.source IS NULL THEN excluded.source
                WHEN instr(reverse_splits.source, excluded.source) > 0 THEN reverse_splits.source
                ELSE reverse_splits.source || '+' || excluded.source
            END,
            updated_at = datetime('now')
        """,
        (
            pad_cik(row.get("cik")),
            ticker,
            row.get("exchange"),
            row.get("exchange_class") or "unknown",
            split_from,
            split_to,
            ratio,
            parse_date(row.get("first_proxy_date")),
            parse_date(row.get("announce_date")),
            parse_date(row.get("vote_date")),
            parse_date(row.get("ratio_set_date")),
            parse_date(row.get("effective_date")) or ex_date,
            ex_date,
            int(row.get("prior_rs_count") or 0),
            row.get("cohort"),
            row.get("status") or "seeded",
            float(row.get("confidence") or 0.5),
            int(row.get("needs_review") or 0),
            row.get("source") or "unknown",
            row.get("notes"),
        ),
    )
    cur = conn.execute(
        "SELECT id FROM reverse_splits WHERE ticker=? AND ex_date=? AND split_from=? AND split_to=?",
        (ticker, ex_date, split_from, split_to),
    )
    r = cur.fetchone()
    return int(r["id"]) if r else None


def seed_from_edgar_and_yfinance(
    cfg: Config | None = None,
    max_tickers: int | None = None,
    full_scan: bool = False,
    since: date | None = None,
) -> dict[str, int]:
    """Discover splits from EDGAR phrase hits and yfinance corporate actions.

    ``since`` narrows the EDGAR search (and the announcement rebuild) to filings
    on or after that date, so the weekly job does not re-scan ``years_back``.
    """
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    edgar_cfg = cfg.section("edgar")
    http = RateLimitedSession(edgar_cfg.get("user_agent", "ReverseSplitResearch research@localhost"), float(edgar_cfg.get("request_delay_seconds", 0.12)))
    start = since or years_ago(int(cfg.section("universe").get("years_back", 5)))
    end = date.today()

    by_cik, by_ticker = fetch_sec_ticker_maps(cfg, http)
    for cik, meta in by_cik.items():
        upsert_issuer(conn, cik, meta.get("name"), meta.get("ticker"), "unknown")
    conn.commit()

    print(f"Searching EDGAR for reverse splits {start} .. {end} ...")
    hits = edgar_search_reverse_splits(cfg, http, start, end)
    print(f"EDGAR hits: {len(hits)}")
    store_edgar_hits(conn, hits)

    tickers: set[str] = set()
    for h in hits:
        cik = h.get("cik")
        ticker = h.get("ticker") or (by_cik.get(cik or "", {}) or {}).get("ticker")
        ticker = normalize_ticker(ticker)
        if ticker:
            tickers.add(ticker)
        if cik:
            upsert_issuer(conn, cik, h.get("name"), ticker, "unknown")
            # placeholder event from filing date if we can parse ratio later
            if ticker and h.get("filed_at"):
                ratio = parse_ratio_from_text(json.dumps(h.get("raw") or {}))
                if ratio:
                    sf, st = ratio
                    upsert_split(
                        conn,
                        {
                            "cik": cik,
                            "ticker": ticker,
                            "ex_date": h["filed_at"],
                            "effective_date": h["filed_at"],
                            "split_from": sf,
                            "split_to": st,
                            "ratio": st / sf,
                            "exchange_class": "unknown",
                            "source": "edgar_search",
                            "confidence": 0.3,
                            "needs_review": 1,
                            "status": "edgar_candidate",
                            "notes": f"form={h.get('form')} accession={h.get('accession')}",
                        },
                    )
    conn.commit()

    # Default: only EDGAR-discovered tickers. Optional full SEC ticker scan (slow).
    if full_scan:
        for t in by_ticker:
            tickers.add(t)

    ticker_list = sorted(t for t in tickers if t)
    if max_tickers:
        ticker_list = ticker_list[:max_tickers]

    print(f"Scanning yfinance splits for {len(ticker_list)} tickers ...")
    n_events = 0
    workers = 8 if len(ticker_list) > 24 else 1

    def _one(ticker: str) -> tuple[str, list[dict[str, Any]]]:
        return ticker, yfinance_reverse_splits(ticker, start, end)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        scanned = pool.map(_one, ticker_list)
        for ticker, events in tqdm(scanned, total=len(ticker_list), desc="yfinance splits"):
            cik = by_ticker.get(ticker)
            for ev in events:
                ev["cik"] = cik
                upsert_issuer(conn, cik, by_cik.get(cik or "", {}).get("name"), ticker, ev.get("exchange_class") or "unknown")
                if upsert_split(conn, ev):
                    n_events += 1
            if n_events and n_events % 50 == 0:
                conn.commit()
    conn.commit()

    # Drop low-confidence edgar_candidate rows that duplicate a yfinance event nearby same ticker/week
    conn.execute(
        """
        DELETE FROM reverse_splits
        WHERE source = 'edgar_search' AND needs_review = 1 AND EXISTS (
            SELECT 1 FROM reverse_splits y
            WHERE y.ticker = reverse_splits.ticker
              AND y.source LIKE '%yfinance%'
              AND abs(julianday(y.ex_date) - julianday(reverse_splits.ex_date)) <= 45
        )
        """
    )
    conn.commit()
    announced = create_announced_only(conn, since=start.isoformat() if since else None)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) AS n FROM reverse_splits").fetchone()["n"]
    conn.close()
    return {
        "edgar_hits": len(hits),
        "tickers_scanned": len(ticker_list),
        "announced_only": announced,
        "events": int(total),
    }


def store_edgar_hits(conn: sqlite3.Connection, hits: list[dict[str, Any]]) -> int:
    n = 0
    for hit in hits:
        accession = (hit.get("accession") or "").strip()
        form = hit.get("form") or ""
        if not accession:
            accession = f"nofile-{hit.get('cik')}-{hit.get('filed_at')}-{form}"
        conn.execute(
            """
            INSERT INTO edgar_hits (accession, form, cik, ticker, name, filed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(accession, form) DO UPDATE SET
                cik = COALESCE(excluded.cik, edgar_hits.cik),
                ticker = COALESCE(excluded.ticker, edgar_hits.ticker),
                name = COALESCE(excluded.name, edgar_hits.name),
                filed_at = COALESCE(excluded.filed_at, edgar_hits.filed_at)
            """,
            (
                accession,
                form,
                hit.get("cik"),
                normalize_ticker(hit.get("ticker")),
                hit.get("name"),
                parse_date(hit.get("filed_at")),
            ),
        )
        n += 1
    conn.commit()
    return n


def create_announced_only(conn: sqlite3.Connection, since: str | None = None) -> int:
    """8-K / 6-K phrase hits that never become a Yahoo split.

    These stay in the book as announcements that did not print. Hits within
    180 days of an effective split are the announcement of that split, not a
    second event.

    With ``since`` only announcements filed on or after that date are rebuilt.
    Older rows come from the committed ledger, whose phrase hits are not kept
    locally, so a full rebuild would erase them.
    """
    if since:
        conn.execute(
            "DELETE FROM reverse_splits WHERE outcome IN ('announced_only', 'mention', 'cancelled') AND announce_date >= ?",
            (since,),
        )
    else:
        conn.execute(
            "DELETE FROM reverse_splits WHERE outcome IN ('announced_only', 'mention', 'cancelled')"
        )
    effective = conn.execute(
        """
        SELECT ticker, cik, ex_date FROM reverse_splits
        WHERE COALESCE(outcome, 'effective') = 'effective'
        """
    ).fetchall()
    by_ticker: dict[str, list[str]] = {}
    by_cik: dict[str, list[str]] = {}
    for row in effective:
        if row["ticker"]:
            by_ticker.setdefault(row["ticker"], []).append(row["ex_date"])
        if row["cik"]:
            by_cik.setdefault(row["cik"], []).append(row["ex_date"])

    hits = conn.execute(
        """
        SELECT * FROM edgar_hits
        WHERE (upper(form) LIKE '8-K%' OR upper(form) LIKE '6-K%')
          AND (? IS NULL OR filed_at >= ?)
        """,
        (since, since),
    ).fetchall()
    n = 0
    for hit in hits:
        ticker = normalize_ticker(hit["ticker"])
        filed = parse_date(hit["filed_at"])
        if not ticker or not filed:
            continue
        filed_dt = datetime.strptime(filed, "%Y-%m-%d").date()
        near = False
        for ex in by_ticker.get(ticker, []) + by_cik.get(hit["cik"] or "", []):
            ex_dt = datetime.strptime(ex[:10], "%Y-%m-%d").date()
            delta = (ex_dt - filed_dt).days
            if -30 <= delta <= 180:
                near = True
                break
        if near:
            continue
        conn.execute(
            """
            INSERT INTO reverse_splits (
                cik, ticker, exchange_class, split_from, split_to, ratio,
                announce_date, ex_date, effective_date, outcome, status,
                confidence, needs_review, source, date_quality, notes
            ) VALUES (?, ?, 'unknown', 1, 1, 1, ?, ?, ?, 'announced_only',
                      'announced_only', 0.4, 1, 'edgar_search', 'search_hit', ?)
            ON CONFLICT(ticker, ex_date, split_from, split_to) DO NOTHING
            """,
            (
                hit["cik"],
                ticker,
                filed,
                filed,
                filed,
                f"accession={hit['accession']} form={hit['form']}",
            ),
        )
        n += 1
    return n


def tag_repeat_splits(cfg: Config | None = None) -> int:
    """Compute prior_rs_count and cohort per event (by CIK, else ticker)."""
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    rows = conn.execute(
        """
        SELECT id, cik, ticker, ex_date
        FROM reverse_splits
        WHERE COALESCE(outcome, 'effective') = 'effective'
        ORDER BY COALESCE(cik, ticker), ex_date, id
        """
    ).fetchall()
    counters: dict[str, int] = {}
    updated = 0
    for r in rows:
        key = f"cik:{(r['cik'] or '').zfill(10)}" if r["cik"] else f"t:{r['ticker']}"
        prior = counters.get(key, 0)
        if prior == 0:
            cohort = "first"
        elif prior == 1:
            cohort = "second"
        else:
            cohort = "third_plus"
        conn.execute(
            "UPDATE reverse_splits SET prior_rs_count=?, cohort=?, updated_at=datetime('now') WHERE id=?",
            (prior, cohort, r["id"]),
        )
        counters[key] = prior + 1
        updated += 1
    conn.commit()
    conn.close()
    return updated


if __name__ == "__main__":
    stats = seed_from_edgar_and_yfinance()
    print(stats)
    print("tagged", tag_repeat_splits())
