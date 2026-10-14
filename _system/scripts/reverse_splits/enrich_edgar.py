"""Enrich reverse-split event dates from SEC EDGAR filings."""

from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .config import Config, load_config
from .db import init_db
from .utils import REVERSE_SPLIT_RE, RateLimitedSession, looks_like_reverse_split, pad_cik, parse_date, tqdm

VOTE_RE = re.compile(r"Item\s*5\.07|Submission of Matters to a Vote", re.I)
EFFECTIVE_RE = re.compile(r"Item\s*3\.03|Item\s*5\.03|became effective|effective(?:\s+as\s+of)?\s+(?:at\s+)?", re.I)
RATIO_SET_RE = re.compile(r"Board(?: of Directors)? (?:has )?(?:approved|determined|selected).*?(?:ratio|reverse)", re.I | re.S)
ANNOUNCE_RE = re.compile(r"press release|announc(?:ed|es|ing).*reverse|intends to effect a reverse", re.I)
PROXY_FORMS = {
    "PRE 14A",
    "DEF 14A",
    "DEFA14A",
    "PRE14A",
    "DEF14A",
    "PREC14A",
    "DEFC14A",
    "PRE 14C",
    "DEF 14C",
    "PRE 14C/A",
    "DEF 14C/A",
}


def _submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{pad_cik(cik)}.json"


def fetch_company_filings(http: RateLimitedSession, cik: str, start: str, end: str) -> list[dict[str, Any]]:
    cik = pad_cik(cik) or cik
    try:
        data = http.get(_submissions_url(cik)).json()
    except Exception:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])
    out = []
    for i, form in enumerate(forms):
        filed = dates[i] if i < len(dates) else None
        if not filed or filed < start or filed > end:
            continue
        form_u = (form or "").upper()
        compact = form_u.replace(" ", "")
        proxy_compact = {f.replace(" ", "") for f in PROXY_FORMS}
        if compact not in proxy_compact and not form_u.startswith("8-K") and not form_u.startswith("6-K"):
            continue
        acc = accessions[i].replace("-", "") if i < len(accessions) else ""
        primary = primaries[i] if i < len(primaries) else ""
        out.append({"form": form, "filed_at": filed, "accession": accessions[i], "accession_nodash": acc, "primary": primary, "cik": cik})
    return out


def filing_url(cik: str, accession_nodash: str, primary: str) -> str:
    cik_n = str(int(pad_cik(cik) or cik))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_n}/{accession_nodash}/{primary}"


def load_filing_text(cfg: Config, http: RateLimitedSession, filing: dict[str, Any]) -> str:
    cache_dir = cfg.edgar_cache / (pad_cik(filing["cik"]) or "unknown")
    cache_dir.mkdir(parents=True, exist_ok=True)
    acc = filing["accession"].replace("-", "")
    cache_path = cache_dir / f"{acc}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="ignore")
    url = filing_url(filing["cik"], filing["accession_nodash"], filing["primary"])
    try:
        resp = http.get(url)
        raw = resp.text
    except Exception:
        return ""
    text = _strip_html(raw)
    cache_path.write_text(text, encoding="utf-8", errors="ignore")
    return text


def _strip_html(raw: str) -> str:
    """Filing text from an HTML body: BeautifulSoup when installed, a tag stripper otherwise."""
    lowered = raw.lower()
    if not ("<html" in lowered or "<body" in lowered or "<div" in lowered):
        return raw
    try:
        import warnings

        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\\1>", " ", raw, flags=re.I | re.S)
        text = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return html.unescape(text)
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    try:
        return BeautifulSoup(raw, "lxml").get_text("\n")
    except Exception:  # noqa: BLE001 - bs4.FeatureNotFound when lxml is missing
        return BeautifulSoup(raw, "html.parser").get_text("\n")


def excerpt_around(text: str, pattern: re.Pattern[str], radius: int = 280) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    start = max(0, m.start() - radius)
    end = min(len(text), m.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()[:800]


def classify_filing(form: str, text: str) -> list[tuple[str, str | None]]:
    """Return list of (role, excerpt)."""
    roles: list[tuple[str, str | None]] = []
    if not looks_like_reverse_split(text):
        return roles
    form_u = (form or "").upper().replace(" ", "")
    if form_u in {f.replace(" ", "") for f in PROXY_FORMS}:
        roles.append(("proxy", excerpt_around(text, REVERSE_SPLIT_RE)))
    if VOTE_RE.search(text) and looks_like_reverse_split(text):
        roles.append(("vote", excerpt_around(text, VOTE_RE)))
    if RATIO_SET_RE.search(text):
        roles.append(("ratio_set", excerpt_around(text, RATIO_SET_RE)))
    if EFFECTIVE_RE.search(text) and looks_like_reverse_split(text):
        roles.append(("effective", excerpt_around(text, EFFECTIVE_RE)))
    if ANNOUNCE_RE.search(text):
        roles.append(("announce", excerpt_around(text, ANNOUNCE_RE)))
    # Current report with reverse-split language but no other role -> announce
    if (form or "").upper().startswith(("8-K", "6-K")) and not roles:
        roles.append(("announce", excerpt_around(text, REVERSE_SPLIT_RE)))
    return roles


def upsert_filing(conn: sqlite3.Connection, event_id: int, filing: dict[str, Any], role: str, excerpt: str | None, url: str) -> None:
    conn.execute(
        """
        INSERT INTO filings (event_id, accession, form, filed_at, url, role, excerpt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, accession, role) DO UPDATE SET
            excerpt = COALESCE(excluded.excerpt, filings.excerpt),
            url = COALESCE(excluded.url, filings.url)
        """,
        (event_id, filing.get("accession"), filing.get("form"), filing.get("filed_at"), url, role, excerpt),
    )


def apply_dates_from_filings(conn: sqlite3.Connection, event_id: int) -> None:
    rows = conn.execute(
        "SELECT role, MIN(filed_at) AS d FROM filings WHERE event_id=? GROUP BY role",
        (event_id,),
    ).fetchall()
    by_role = {r["role"]: r["d"] for r in rows}
    conn.execute(
        """
        UPDATE reverse_splits SET
            first_proxy_date = COALESCE(?, first_proxy_date),
            announce_date = COALESCE(?, announce_date),
            vote_date = COALESCE(?, vote_date),
            ratio_set_date = COALESCE(?, ratio_set_date),
            effective_date = COALESCE(effective_date, ?),
            status = 'enriched',
            confidence = CASE WHEN ? IS NOT NULL THEN 0.8 ELSE confidence END,
            updated_at = datetime('now')
        WHERE id=?
        """,
        (
            by_role.get("proxy"),
            by_role.get("announce"),
            by_role.get("vote"),
            by_role.get("ratio_set"),
            by_role.get("effective"),
            by_role.get("proxy") or by_role.get("announce"),
            event_id,
        ),
    )


def _iter_submission_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source = payload
    if "accessionNumber" not in payload:
        source = (payload.get("filings") or {}).get("recent") or {}
    forms = source.get("form") or []
    dates = source.get("filingDate") or []
    accessions = source.get("accessionNumber") or []
    primaries = source.get("primaryDocument") or []
    accepts = source.get("acceptanceDateTime") or []
    rows = []
    for i, form in enumerate(forms):
        accession = accessions[i] if i < len(accessions) else ""
        rows.append(
            {
                "form": form,
                "filed_at": dates[i] if i < len(dates) else None,
                "accession": accession,
                "accession_nodash": accession.replace("-", ""),
                "primary": primaries[i] if i < len(primaries) else "",
                "accept_time": accepts[i] if i < len(accepts) else None,
            }
        )
    return rows


def _submission_index(http: RateLimitedSession, cik: str, not_before: str | None = None) -> dict[str, dict[str, Any]]:
    try:
        data = http.get(_submissions_url(cik)).json()
    except Exception:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in _iter_submission_rows(data):
        if row["accession_nodash"]:
            index[row["accession_nodash"]] = row
    for extra in (data.get("filings") or {}).get("files") or []:
        name = extra.get("name")
        filing_to = str(extra.get("filingTo") or "")
        if not name:
            continue
        if not_before and filing_to and filing_to < not_before:
            continue
        try:
            payload = http.get(f"https://data.sec.gov/submissions/{name}").json()
        except Exception:
            continue
        for row in _iter_submission_rows(payload):
            if row["accession_nodash"]:
                index[row["accession_nodash"]] = row
    return index


def _remember_parse(conn: sqlite3.Connection, hit: dict[str, Any], announcement: dict[str, Any]) -> None:
    hit["text_parsed"] = 1
    hit["substantive"] = 1 if announcement.get("substantive") else 0
    hit["cancelled"] = 1 if announcement.get("cancelled") else 0
    hit["parsed_ratio"] = announcement.get("ratio")
    hit["parsed_ex_date"] = announcement.get("announced_ex_date")
    hit["vote_path"] = announcement.get("vote_path")
    conn.execute(
        """
        UPDATE edgar_hits SET
            text_parsed=1, substantive=?, cancelled=?, parsed_ratio=?,
            parsed_ex_date=?, vote_path=COALESCE(?, vote_path)
        WHERE accession=? AND form=?
        """,
        (
            hit["substantive"],
            hit["cancelled"],
            hit["parsed_ratio"],
            hit["parsed_ex_date"],
            hit["vote_path"],
            hit["accession"],
            hit["form"],
        ),
    )


def _hit_in_window(hit: dict[str, Any], ex_date: str, lookback: int, lookahead: int) -> bool:
    form = str(hit.get("form") or "").upper()
    if not (form.startswith("8-K") or form.startswith("6-K")):
        return False
    filed = str(hit.get("filed_at") or "")[:10]
    ex = str(ex_date or "")[:10]
    if len(filed) != 10 or len(ex) != 10:
        return False
    from datetime import datetime as dt
    from datetime import timedelta

    fd = dt.strptime(filed, "%Y-%m-%d").date()
    exd = dt.strptime(ex, "%Y-%m-%d").date()
    return exd - timedelta(days=lookback) <= fd <= exd + timedelta(days=lookahead)


def _parse_candidate_filings(
    cfg: Config,
    http: RateLimitedSession,
    conn: sqlite3.Connection,
    by_cik: dict[str, list[dict]],
    lookback: int,
    lookahead: int,
    text_limit: int | None,
    parse_announcement,
) -> int:
    """Parse the filings that can change an event, not every phrase hit.

    For each completed split, read up to four 8-Ks in the window and stop when
    one is a real announcement. Also read the newest 400 listed phrase-only
    hits so cancellations are not only a code path.
    """
    parsed = 0
    seen: set[tuple[str, str]] = set()
    events = conn.execute(
        "SELECT id, cik, ticker, ex_date, outcome, exchange_class, announce_date FROM reverse_splits"
    ).fetchall()

    def parse_hit(hit: dict) -> bool:
        nonlocal parsed
        if text_limit is not None and parsed >= text_limit:
            return False
        key = (str(hit.get("accession")), str(hit.get("form")))
        if key in seen:
            return bool(hit.get("substantive"))
        if not hit.get("primary"):
            return False
        filing = {
            "cik": hit.get("cik"),
            "accession": hit.get("accession"),
            "accession_nodash": str(hit.get("accession") or "").replace("-", ""),
            "primary": hit.get("primary"),
        }
        text = load_filing_text(cfg, http, filing)
        seen.add(key)
        parsed += 1
        _remember_parse(conn, hit, parse_announcement(text))
        if parsed % 25 == 0:
            conn.commit()
        return bool(hit.get("substantive"))

    for event in tqdm(events, desc="parse effective 8-Ks"):
        if (event["outcome"] or "effective") != "effective":
            continue
        window = [
            hit
            for hit in by_cik.get(event["cik"] or "", [])
            if _hit_in_window(hit, event["ex_date"], lookback, lookahead)
        ]
        window.sort(key=lambda hit: str(hit.get("filed_at") or ""))
        for hit in window[:4]:
            if text_limit is not None and parsed >= text_limit:
                break
            if parse_hit(hit):
                break
    listed_mentions = [
        event
        for event in events
        if event["outcome"] == "announced_only" and event["exchange_class"] == "listed"
    ]
    listed_mentions.sort(key=lambda event: event["ex_date"] or "", reverse=True)
    for event in tqdm(listed_mentions[:400], desc="parse listed phrase hits"):
        if text_limit is not None and parsed >= text_limit:
            break
        filed = (event["announce_date"] or event["ex_date"] or "")[:10]
        match = next(
            (
                hit
                for hit in by_cik.get(event["cik"] or "", [])
                if str(hit.get("filed_at") or "")[:10] == filed
                and str(hit.get("form") or "").upper().startswith(("8-K", "6-K"))
            ),
            None,
        )
        if match is not None:
            parse_hit(match)
    conn.commit()
    return parsed


def enrich_clocks(
    cfg: Config | None = None,
    download_text: bool = True,
    text_limit: int | None = None,
    since: str | None = None,
) -> dict[str, int]:
    """Attach EDGAR accept times and, when text is on, parse the announcement.

    Search hits are phrase matches. Text parsing is what marks a hit as the
    actual reverse-split announcement versus a passing mention.

    ``since`` (ISO date) limits the work to hits filed on or after that date.
    Effective events whose announcement already predates ``since`` are left
    alone: the earliest-filing rule means no newer hit can replace them.
    """
    from .filings import choose_announce, parse_announcement, vote_path_from_form

    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    edgar_cfg = cfg.section("edgar")
    http = RateLimitedSession(
        edgar_cfg.get("user_agent", "ReverseSplitResearch research@localhost"),
        float(edgar_cfg.get("request_delay_seconds", 0.12)),
    )
    lookback = int(edgar_cfg.get("lookback_days", 365))
    lookahead = int(edgar_cfg.get("lookahead_days", 30))
    from .utils import years_ago

    not_before = years_ago(int(cfg.section("universe").get("years_back", 5)) + 1).isoformat()
    hits = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM edgar_hits WHERE ? IS NULL OR filed_at >= ?", (since, since)
        ).fetchall()
    ]
    by_cik: dict[str, list[dict]] = {}
    for hit in hits:
        if hit.get("cik"):
            by_cik.setdefault(hit["cik"], []).append(hit)

    indexed = 0
    parsed = 0
    for cik, group in tqdm(by_cik.items(), desc="EDGAR clocks"):
        index = _submission_index(http, cik, not_before=not_before)
        indexed += 1
        for hit in group:
            acc = (hit.get("accession") or "").replace("-", "")
            meta = index.get(acc)
            if not meta:
                continue
            hit["accept_time"] = meta.get("accept_time") or hit.get("accept_time")
            hit["primary"] = meta.get("primary")
            hit["accession_nodash"] = meta.get("accession_nodash")
            conn.execute(
                "UPDATE edgar_hits SET accept_time=? WHERE accession=? AND form=?",
                (hit["accept_time"], hit["accession"], hit["form"]),
            )
        conn.commit()

    if download_text:
        parsed = _parse_candidate_filings(
            cfg, http, conn, by_cik, lookback, lookahead, text_limit, parse_announcement
        )

    events = conn.execute(
        """
        SELECT id, cik, ticker, ex_date, outcome, announce_date
        FROM reverse_splits
        """
    ).fetchall()
    updated = 0
    for event in events:
        group = by_cik.get(event["cik"] or "", [])
        ticker_hits = [
            hit
            for hit in group
            if not hit.get("ticker") or hit.get("ticker") == event["ticker"] or event["cik"]
        ]
        if (event["outcome"] or "effective") == "effective":
            if since and event["announce_date"] and str(event["announce_date"])[:10] < since:
                continue
            chosen = choose_announce(ticker_hits, event["ex_date"], lookback, lookahead)
            if not chosen:
                continue
            quality = "search_hit"
            if chosen.get("text_parsed"):
                quality = "filing_text"
            elif chosen.get("accept_time"):
                quality = "acceptance_time"
            proxy_path = None
            proxy_dates = []
            for hit in ticker_hits:
                path = vote_path_from_form(hit.get("form"))
                if path and hit.get("filed_at"):
                    proxy_dates.append(hit["filed_at"][:10])
                    proxy_path = proxy_path or path
            conn.execute(
                """
                UPDATE reverse_splits SET
                    announce_date=?,
                    accept_time=?,
                    date_quality=?,
                    first_proxy_date=COALESCE(?, first_proxy_date),
                    vote_path=COALESCE(?, vote_path),
                    announced_ratio=COALESCE(?, announced_ratio),
                    announced_ex_date=COALESCE(?, announced_ex_date),
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    chosen.get("filed_at"),
                    chosen.get("accept_time"),
                    quality,
                    min(proxy_dates) if proxy_dates else None,
                    chosen.get("vote_path") or proxy_path,
                    chosen.get("parsed_ratio"),
                    chosen.get("parsed_ex_date"),
                    event["id"],
                ),
            )
            updated += 1
            continue
        # Announcement that never printed: follow the hit that created it.
        match = next(
            (
                hit
                for hit in ticker_hits
                if (hit.get("filed_at") or "")[:10] == (event["announce_date"] or event["ex_date"] or "")[:10]
                and (hit.get("ticker") in (None, "", event["ticker"]))
            ),
            None,
        )
        if match is None:
            continue
        outcome = event["outcome"] or "announced_only"
        if match.get("text_parsed"):
            if match.get("cancelled"):
                outcome = "cancelled"
            elif match.get("substantive"):
                outcome = "announced_only"
            else:
                outcome = "mention"
        quality = "filing_text" if match.get("text_parsed") else ("acceptance_time" if match.get("accept_time") else "search_hit")
        conn.execute(
            """
            UPDATE reverse_splits SET
                accept_time=?,
                date_quality=?,
                outcome=?,
                vote_path=COALESCE(?, vote_path),
                announced_ratio=COALESCE(?, announced_ratio),
                announced_ex_date=COALESCE(?, announced_ex_date),
                updated_at=datetime('now')
            WHERE id=?
            """,
            (
                match.get("accept_time"),
                quality,
                outcome,
                match.get("vote_path"),
                match.get("parsed_ratio"),
                match.get("parsed_ex_date"),
                event["id"],
            ),
        )
        updated += 1
    conn.commit()
    conn.close()
    return {"ciks": indexed, "filings_parsed": parsed, "events_updated": updated, "hits": len(hits)}


def enrich_events(cfg: Config | None = None, limit: int | None = None) -> dict[str, int]:
    cfg = cfg or load_config()
    conn = init_db(cfg.db_path)
    edgar_cfg = cfg.section("edgar")
    http = RateLimitedSession(
        edgar_cfg.get("user_agent", "ReverseSplitResearch research@localhost"),
        float(edgar_cfg.get("request_delay_seconds", 0.12)),
    )
    lookback = int(edgar_cfg.get("lookback_days", 365))
    lookahead = int(edgar_cfg.get("lookahead_days", 30))

    q = """
        SELECT id, cik, ticker, ex_date
        FROM reverse_splits
        WHERE cik IS NOT NULL
        ORDER BY ex_date DESC
    """
    events = conn.execute(q).fetchall()
    if limit:
        events = events[:limit]

    # Group by CIK so submissions JSON is fetched once
    by_cik: dict[str, list] = {}
    for ev in events:
        by_cik.setdefault(ev["cik"], []).append(ev)

    enriched = 0
    filings_saved = 0
    for cik, evs in tqdm(by_cik.items(), desc="EDGAR enrich"):
        # Window covering all events for this issuer
        dates = [datetime.strptime(e["ex_date"][:10], "%Y-%m-%d").date() for e in evs]
        start = (min(dates) - timedelta(days=lookback)).isoformat()
        end = (max(dates) + timedelta(days=lookahead)).isoformat()
        filings = fetch_company_filings(http, cik, start, end)
        # Cache filing texts for this CIK batch
        text_cache: dict[str, str] = {}
        classified: list[tuple[dict, list[tuple[str, str | None]], str]] = []
        for f in filings:
            key = f["accession"]
            if key not in text_cache:
                text_cache[key] = load_filing_text(cfg, http, f)
            text = text_cache[key]
            if not text:
                continue
            roles = classify_filing(f["form"], text)
            if not roles:
                continue
            url = filing_url(f["cik"], f["accession_nodash"], f["primary"])
            classified.append((f, roles, url))

        for ev in evs:
            ex = datetime.strptime(ev["ex_date"][:10], "%Y-%m-%d").date()
            matched = False
            for f, roles, url in classified:
                filed = parse_date(f.get("filed_at"))
                if not filed:
                    continue
                fd = datetime.strptime(filed, "%Y-%m-%d").date()
                if fd < ex - timedelta(days=lookback) or fd > ex + timedelta(days=lookahead):
                    continue
                for role, excerpt in roles:
                    upsert_filing(conn, ev["id"], f, role, excerpt, url)
                    filings_saved += 1
                    matched = True
            if matched:
                apply_dates_from_filings(conn, ev["id"])
                enriched += 1
        conn.commit()
    conn.close()
    return {"events_considered": len(events), "events_enriched": enriched, "filings_saved": filings_saved, "ciks": len(by_cik)}


if __name__ == "__main__":
    print(enrich_events())
