#!/usr/bin/env python3
"""Join the special-situations book into one dashboard feed.

Greenblatt workouts (spinoffs, split-off exchange offers, merger securities,
warrants and rights, restructurings) plus the Manual of Ideas forced-seller
set (index deletes, dividend cuts, and modelled separation selling from
dashboard/data/separations.json). Register-backed separations rank; a
headline alone stays in discovery. A row is ranked only when a holder is forced
to sell, or the security is too odd for the usual buyer. Unverified SEC
text matches stay in discovery.

Reads committed dashboard artifacts. Missing inputs skip the write so a
sparse checkout cannot replace a full book with a thin one.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "dashboard" / "data" / "special_situations.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
WARRANTS_PATH = ROOT / "dashboard" / "data" / "warrants.json"
ACTIVIST_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"
INDEX_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
NOL_PATH = ROOT / "dashboard" / "data" / "nol_382_facts.json"
CVR_PATH = ROOT / "_system" / "reference" / "cvr" / "cvr_universe.json"
SEPARATIONS_PATH = ROOT / "dashboard" / "data" / "separations.json"
BUYBACK_PATH = ROOT / "dashboard" / "data" / "buyback_radar.json"

SCHEMA = "special_situations.v1"
MIN_NEWS_CONFIDENCE = 0.8

LANES = [
    {"id": "spinoffs", "label": "Spinoffs", "source": "Greenblatt"},
    {"id": "split_offs", "label": "Split-offs and exchange offers", "source": "Greenblatt"},
    {"id": "mergers", "label": "Merger securities", "source": "Greenblatt"},
    {"id": "warrants", "label": "Warrants and rights", "source": "Greenblatt"},
    {"id": "restructurings", "label": "Restructurings", "source": "Greenblatt"},
    {"id": "forced_sellers", "label": "Forced sellers", "source": "Manual of Ideas"},
    {"id": "buyback_events", "label": "Buyback events", "source": "EDGAR"},
]
LANE_ORDER = {row["id"]: index for index, row in enumerate(LANES)}

DEAL_FORMS = {
    "SC TO-T",
    "SC TO-T/A",
    "SC TO-C",
    "SC TO-I",
    "SC TO-I/A",
    "DEFM14A",
    "PREM14A",
    "S-4",
    "S-4/A",
    "425",
}
RANKED_CVR_FORMS = {"S-4", "S-4/A", "DEFM14A", "PREM14A"}

MERGER_SECURITY = re.compile(
    r"\b(cvr|contingent value right|contingent consideration|earn-?out|"
    r"tender offer|go-shop|stub stock|tracking stock)\b",
    re.I,
)
RESTRUCTURING_EVENT = re.compile(
    r"\b(chapter 11|bankruptcy|recapitali[sz]|leveraged stub|emergence from)\b",
    re.I,
)
RIGHTS_EVENT = re.compile(
    r"\b(rights offering|odd-?lot tender|subscription rights?)\b",
    re.I,
)
DIVIDEND_CUT = re.compile(
    r"\b(cuts?|cutting|suspends?|suspended|omits?|omitted|cancels?|cancelled|"
    r"eliminates?|eliminated|slashes?|slashed)\b.{0,40}\bdividends?\b"
    r"|\bdividends?\b.{0,40}\b(cut|cuts|cutting|suspended|suspension|omitted|"
    r"cancelled|eliminated|slashed)\b",
    re.I,
)
DIVIDEND_CUT_OPINION = re.compile(r"\b(cut risk|risk of)\b", re.I)
# An explicit separation cue. A bare "spin" admitted "GEV dips" headlines.
SPIN_WORD = re.compile(
    r"spin[\s-]?offs?\b|spinoffs?\b|spun[\s-]off|\bseparation of\b|\bdistribution of shares\b|"
    r"\bsplit[\s-]off\b|\bexchange offer\b",
    re.I,
)
SPIN_COMPLETED = re.compile(
    r"\bcomplet|\bpost[\s-]?(?:spin|separation)|\bafter the (?:spin|separation)|\bsince the spin", re.I
)


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sid(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return "ss:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _clean_entity(name: object) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return re.split(r"\s{2,}|\(", text, maxsplit=1)[0].strip()


def _money(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number >= 100:
        return f"${number:,.0f}"
    return f"${number:,.2f}"


def _row(
    *,
    lane: str,
    lanes: list[str] | None = None,
    book: str,
    ticker: str,
    company: str,
    what: str,
    ends: str | None,
    ends_label: str,
    evidence_url: str | None,
    evidence_label: str,
    evidence_kind: str,
    source_feed: str,
    as_of: str | None,
    next_action: str,
    headline_count: int = 1,
    extra_id: str = "",
) -> dict:
    lane_ids = lanes or [lane]
    return {
        "id": _sid(book, lane, ticker, source_feed, extra_id or what[:80]),
        "lane": lane,
        "lanes": lane_ids,
        "book": book,
        "ticker": ticker,
        "company": company,
        "what": what,
        "ends": ends or None,
        "ends_label": ends_label,
        "annualized_spread": None,
        "evidence_url": evidence_url or None,
        "evidence_label": evidence_label,
        "evidence_kind": evidence_kind,
        "source_feed": source_feed,
        "as_of": as_of,
        "desk": "special_situations",
        "status": "open" if book != "history" else "ended",
        "next": next_action,
        "headline_count": headline_count,
        "inbox": book == "ranked" and "Terms are not extracted" not in what,
    }


def _news_items(news: dict) -> list[dict]:
    items = news.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _confident(item: dict) -> bool:
    try:
        return float(item.get("confidence") or 0) >= MIN_NEWS_CONFIDENCE
    except (TypeError, ValueError):
        return False


def _ticker_of(item: dict) -> str:
    tickers = item.get("tickers") or []
    if isinstance(tickers, list) and tickers:
        return str(tickers[0])
    return str(item.get("ticker") or "")


def _text(item: dict) -> str:
    return f"{item.get('title') or ''} {item.get('summary') or ''}"


def _separation_rows(separations: dict) -> list[dict]:
    return [r for r in (separations.get("rows") or []) if isinstance(r, dict)]


def _separation_tickers(separations: dict) -> set[str]:
    out: set[str] = set()
    for row in _separation_rows(separations):
        for key in ("parent_ticker", "spinco_ticker"):
            if row.get(key):
                out.add(str(row[key]).upper())
    return out


def _compact_flow(row: dict, side: str) -> dict | None:
    flow = ((row.get("flows") or {}).get(side)) or None
    if not flow or flow.get("status") != "ok":
        return None
    return {
        "pct_of_float_base": flow.get("pct_of_float_base"),
        "pct_of_adv_days": flow.get("pct_of_adv_days"),
        "window_start": flow.get("window_start"),
        "window_end": flow.get("window_end"),
        "confidence": "estimate",
        "legs": flow.get("legs") or [],
    }


def _separation_desk_row(row: dict, *, lane: str) -> dict:
    """One desk row from a separations.json row (register-backed)."""
    gates = row.get("gates") or {}
    ranked = gates.get("status") == "ranked" and row.get("lifecycle") != "closed"
    book = "history" if row.get("lifecycle") == "closed" else ("ranked" if ranked else "discovery")
    spread = row.get("spread") if ranked else None
    missing = list((gates.get("terms") or {}).get("missing") or []) + list(
        (gates.get("identity") or {}).get("missing") or []
    )
    what = f"{row.get('kind_label') or row.get('kind')}: {row.get('spinco_name') or row.get('spinco_ticker') or 'SpinCo'}."
    summary = row.get("terms_summary")
    if summary and summary != "Terms are not extracted.":
        what = f"{what} {summary}"
    elif not ranked:
        what = f"{what} Terms are not extracted."
    source = (row.get("sources") or [{}])[0] or {}
    out = _row(
        lane=lane,
        book=book,
        ticker=str(row.get("parent_ticker") or ""),
        company=str(row.get("spinco_name") or ""),
        what=what,
        ends=row.get("ends"),
        ends_label=str(row.get("ends_label") or "Not stated"),
        evidence_url=source.get("url"),
        evidence_label=str(source.get("form") or "SEC"),
        evidence_kind="filing" if source else "screen",
        source_feed="separations",
        as_of=str((row.get("dates") or {}).get("filed") or source.get("filed") or "") or None,
        next_action=str(row.get("next") or "Read the filing."),
        extra_id=str(row.get("separation_id")),
    )
    out["separation_id"] = row.get("separation_id")
    out["spinco_ticker"] = row.get("spinco_ticker")
    out["terms_summary"] = summary
    out["spread"] = spread
    out["flow"] = _compact_flow(row, "spinco")
    out["missing_terms"] = missing
    if spread and spread.get("annualized_spread_pct") is not None:
        out["annualized_spread"] = (
            f"{spread['annualized_spread_pct']:.1f}% annualized on the odd-lot gain of "
            f"{spread['odd_lot_payoff_per_99']['gain_pct']:.2f}% ({str(spread['basis']).replace('_', ' ')})"
        )
    return out


SPLIT_LANE_KINDS = {"split_off", "clean_up_spin", "retained_stake_sale", "carve_out_ipo"}


def separation_event_rows(separations: dict) -> list[dict]:
    """Unreviewed EDGAR hits (Form 10, exchange-offer prospectus) as discovery rows."""
    rows = []
    registered = _separation_tickers(separations)
    for ev in separations.get("discovery_events") or []:
        if not isinstance(ev, dict):
            continue
        ticker = str(ev.get("ticker") or "").upper()
        if ticker and ticker in registered:
            continue
        lane = "spinoffs" if ev.get("kind_hint") == "spin_off" else "split_offs"
        form = str(ev.get("form") or "SEC")
        rows.append(
            _row(
                lane=lane,
                book="discovery",
                ticker=ticker or "Unresolved",
                company=str(ev.get("entity_name") or ""),
                what=f"{form} filing matched {str(ev.get('kind_hint') or 'separation').replace('_', '-')} language. Identity and terms are not verified.",
                ends=None,
                ends_label="Terms unknown",
                evidence_url=ev.get("url"),
                evidence_label=form,
                evidence_kind="filing",
                source_feed="separation_events",
                as_of=ev.get("filed"),
                next_action="Read the filing. Link it to a register record with the parent, the ratio or the formula, and the dates.",
                extra_id=str(ev.get("event_id") or ev.get("accession") or ""),
            )
        )
    return rows
SPIN_LANE_KINDS = {"spin_off", "reverse_morris_trust"}


def split_off_rows(separations: dict) -> list[dict]:
    rows = []
    for row in _separation_rows(separations):
        if row.get("kind") not in SPLIT_LANE_KINDS:
            continue
        rows.append(_separation_desk_row(row, lane="split_offs"))
    return rows


def spinoff_rows(news: dict, separations: dict | None = None) -> list[dict]:
    """Register-backed spins rank; headlines stay in discovery unless the ticker is registered."""
    separations = separations or {}
    rows = []
    registered = _separation_tickers(separations)
    for row in _separation_rows(separations):
        if row.get("kind") not in SPIN_LANE_KINDS:
            continue
        rows.append(_separation_desk_row(row, lane="spinoffs"))
    grouped: dict[str, list[dict]] = {}
    for item in _news_items(news):
        if item.get("category") != "spinoff" or not _confident(item):
            continue
        if not SPIN_WORD.search(_text(item)):
            continue
        ticker = _ticker_of(item)
        if not ticker or ticker.upper() in registered:
            continue
        grouped.setdefault(ticker, []).append(item)
    for ticker, items in grouped.items():
        items.sort(key=lambda item: str(item.get("published_utc") or ""), reverse=True)
        latest = items[0]
        title = str(latest.get("title") or "Spinoff")
        completed = bool(SPIN_COMPLETED.search(title))
        rows.append(
            _row(
                lane="spinoffs",
                book="discovery",
                ticker=ticker,
                company=str(latest.get("company") or ticker),
                what=f"{title} Terms are not extracted.",
                ends=None,
                ends_label=(
                    "Orphan window after the distribution"
                    if completed
                    else "Distribution window"
                ),
                evidence_url=latest.get("url"),
                evidence_label=str(latest.get("publisher") or "News"),
                evidence_kind="news",
                source_feed="portfolio_news",
                as_of=str(latest.get("published_utc") or "")[:10] or None,
                next_action="Find the Form 10. Name the parent, the spun company, the ratio, and who must sell.",
                headline_count=len(items),
                extra_id=ticker,
            )
        )
    return rows


def merger_news_rows(news: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in _news_items(news):
        if item.get("category") != "m_and_a" or not _confident(item):
            continue
        text = _text(item)
        if not MERGER_SECURITY.search(text):
            continue
        ticker = _ticker_of(item)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(
            _row(
                lane="mergers",
                book="ranked",
                ticker=ticker,
                company=str(item.get("company") or ticker),
                what=str(item.get("title") or "Merger security"),
                ends=None,
                ends_label="Deal clock not stated in the headline",
                evidence_url=item.get("url"),
                evidence_label=str(item.get("publisher") or "News"),
                evidence_kind="news",
                source_feed="portfolio_news",
                as_of=str(item.get("published_utc") or "")[:10] or None,
                next_action="Open the merger agreement and record the milestone, the cap, and the expiry.",
                extra_id=str(item.get("id") or ticker),
            )
        )
    return rows


def rights_news_rows(news: dict) -> list[dict]:
    rows = []
    for item in _news_items(news):
        if not _confident(item):
            continue
        text = _text(item)
        if not RIGHTS_EVENT.search(text):
            continue
        ticker = _ticker_of(item)
        if not ticker:
            continue
        rows.append(
            _row(
                lane="warrants",
                lanes=["warrants"],
                book="ranked",
                ticker=ticker,
                company=str(item.get("company") or ticker),
                what=str(item.get("title") or "Rights offering"),
                ends=None,
                ends_label="Subscription window not stated in the headline",
                evidence_url=item.get("url"),
                evidence_label=str(item.get("publisher") or "News"),
                evidence_kind="news",
                source_feed="portfolio_news",
                as_of=str(item.get("published_utc") or "")[:10] or None,
                next_action="Read the rights terms: ratio, transferability, and any insider backstop.",
                extra_id=str(item.get("id") or ticker),
            )
        )
    return rows


def restructuring_news_rows(news: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in _news_items(news):
        if not _confident(item):
            continue
        text = _text(item)
        if not RESTRUCTURING_EVENT.search(text):
            continue
        ticker = _ticker_of(item)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(
            _row(
                lane="restructurings",
                book="ranked",
                ticker=ticker,
                company=str(item.get("company") or ticker),
                what=str(item.get("title") or "Restructuring"),
                ends=None,
                ends_label="Case clock not stated in the headline",
                evidence_url=item.get("url"),
                evidence_label=str(item.get("publisher") or "News"),
                evidence_kind="news",
                source_feed="portfolio_news",
                as_of=str(item.get("published_utc") or "")[:10] or None,
                next_action="Confirm the filing. A segment reshuffle is not a restructuring workout.",
                extra_id=str(item.get("id") or ticker),
            )
        )
    return rows


def dividend_cut_rows(news: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in _news_items(news):
        if item.get("category") != "dividend_policy" or not _confident(item):
            continue
        text = _text(item)
        if not DIVIDEND_CUT.search(text):
            continue
        if DIVIDEND_CUT_OPINION.search(text) and not re.search(
            r"\b(suspend|omit|cancel|eliminat|slash)", text, re.I
        ):
            continue
        ticker = _ticker_of(item)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(
            _row(
                lane="forced_sellers",
                book="ranked",
                ticker=ticker,
                company=str(item.get("company") or ticker),
                what=str(item.get("title") or "Dividend cut"),
                ends=None,
                ends_label="Income-mandate selling after the cut",
                evidence_url=item.get("url"),
                evidence_label=str(item.get("publisher") or "News"),
                evidence_kind="news",
                source_feed="portfolio_news",
                as_of=str(item.get("published_utc") or "")[:10] or None,
                next_action="Confirm the company announcement. A yield article is not a cut.",
                extra_id=str(item.get("id") or ticker),
            )
        )
    return rows


def _cvr_evidence(candidate: dict) -> tuple[str | None, str]:
    url = candidate.get("sec_hint") or candidate.get("news_link")
    label = "SEC filing" if candidate.get("sec_hint") else "News"
    return (str(url) if url else None, label)


def cvr_rows(cvr: dict) -> tuple[list[dict], list[dict]]:
    ranked: list[dict] = []
    discovery: list[dict] = []
    as_of = str(cvr.get("as_of") or "") or None
    for candidate in cvr.get("post_close_universe") or []:
        if not isinstance(candidate, dict):
            continue
        ticker = str(candidate.get("ticker") or "")
        if not ticker:
            continue
        acquirer = candidate.get("acquirer") or "the buyer"
        payout = _money(candidate.get("max_payout_usd"))
        payout_bit = f" Maximum payout {payout}." if payout else ""
        ends = candidate.get("outside_date") or None
        url, label = _cvr_evidence(candidate)
        ranked.append(
            _row(
                lane="mergers",
                book="ranked",
                ticker=ticker,
                company=_clean_entity(candidate.get("entity_name")) or ticker,
                what=f"Contingent value right. Acquirer {acquirer}.{payout_bit}",
                ends=str(ends) if ends else None,
                ends_label=str(ends) if ends else "Expiry not stated",
                evidence_url=url,
                evidence_label=label if url else "CVR universe",
                evidence_kind="filing" if url else "screen",
                source_feed="cvr_universe",
                as_of=as_of,
                next_action="Read the milestone, the cap, and whether the right trades.",
                extra_id=str(candidate.get("id") or ticker),
            )
        )
    for candidate in cvr.get("pre_close_opportunities") or []:
        if not isinstance(candidate, dict):
            continue
        ticker = str(candidate.get("ticker") or "")
        if not ticker:
            continue
        form = str(candidate.get("form") or "").upper()
        priced = candidate.get("max_contingent_usd") not in (None, "")
        deal_doc = form in RANKED_CVR_FORMS
        url, label = _cvr_evidence(candidate)
        company = _clean_entity(candidate.get("entity_name")) or ticker
        if priced or deal_doc:
            if priced:
                what = (
                    f"Contingent cash of {_money(candidate.get('max_contingent_usd'))}."
                )
                catalyst = candidate.get("catalyst")
                if catalyst:
                    what = f"{what} {catalyst}."
            else:
                what = (
                    f"Merger filing ({form}) matched contingent consideration. "
                    "Terms are not extracted."
                )
            ends = candidate.get("expected_close") or candidate.get("outside_date")
            ranked.append(
                _row(
                    lane="mergers",
                    book="ranked",
                    ticker=ticker,
                    company=company,
                    what=what,
                    ends=str(ends) if ends else None,
                    ends_label=str(ends) if ends else "Close date not stated",
                    evidence_url=url,
                    evidence_label=label if url else "CVR universe",
                    evidence_kind="filing" if candidate.get("sec_hint") else "screen",
                    source_feed="cvr_universe",
                    as_of=str(candidate.get("last_seen_at") or candidate.get("discovered_at") or as_of or "")
                    or None,
                    next_action="Extract the milestone, the cap, and the expiry before sizing.",
                    extra_id=str(candidate.get("id") or ticker),
                )
            )
            continue
        if not url and not candidate.get("accession"):
            continue
        discovery.append(
            _row(
                lane="mergers",
                book="discovery",
                ticker=ticker,
                company=company,
                what="SEC text matched contingent consideration. Terms are not extracted.",
                ends=None,
                ends_label="Terms unknown",
                evidence_url=url,
                evidence_label=label if url else "Accession",
                evidence_kind="filing" if candidate.get("sec_hint") else "news",
                source_feed="cvr_universe",
                as_of=str(candidate.get("last_seen_at") or candidate.get("discovered_at") or "")
                or None,
                next_action="Confirm the exhibit. Do not size a candidate whose terms are unknown.",
                extra_id=str(candidate.get("id") or ticker),
            )
        )
    return ranked, discovery


def tender_rows(activist: dict) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in list(activist.get("feed") or []) + list(activist.get("review_queue") or []):
        if not isinstance(item, dict):
            continue
        form = str(item.get("form") or "").upper()
        if item.get("filing_class") != "tender_offer" and form not in DEAL_FORMS:
            continue
        ticker = str(item.get("ticker") or "")
        url = item.get("source_url") or item.get("document_url")
        key = f"{ticker}|{form}|{url}"
        if key in seen:
            continue
        seen.add(key)
        firm = item.get("firm_name") or "the filer"
        rows.append(
            _row(
                lane="mergers",
                book="ranked",
                ticker=ticker or "—",
                company=str(item.get("target_company") or ticker or ""),
                what=f"{form or 'Deal filing'} by {firm}.",
                ends=None,
                ends_label=str(item.get("report_date") or "Filing date on the document"),
                evidence_url=str(url) if url else None,
                evidence_label=form or "SEC",
                evidence_kind="filing",
                source_feed="activist_feed",
                as_of=str(item.get("report_date") or "") or None,
                next_action="Read the offer price, the minimum, and whether a vote is still open.",
                extra_id=str(item.get("report_id") or key),
            )
        )
    return rows


def warrant_rows(warrants: dict) -> tuple[list[dict], list[dict], list[dict]]:
    ranked: list[dict] = []
    history: list[dict] = []
    for item in warrants.get("rows") or []:
        if not isinstance(item, dict):
            continue
        lifecycle = str(item.get("lifecycle") or "")
        lane_name = str(item.get("lane") or "")
        chapter = lane_name == "chapter_11"
        primary = "restructurings" if chapter else "warrants"
        lanes = ["restructurings", "warrants"] if chapter else ["warrants"]
        terms = item.get("terms") or {}
        clock = item.get("contract_clock") or {}
        expiry = terms.get("expiry") or clock.get("expiry")
        source = item.get("source") or {}
        book = "ranked" if lifecycle == "active" else "history"
        row = _row(
            lane=primary,
            lanes=lanes,
            book=book,
            ticker=str(item.get("warrant_ticker") or item.get("common_ticker") or ""),
            company=str(item.get("issuer") or ""),
            what=(
                f"{'Post-reorganization' if chapter else 'Warrant'} on "
                f"{item.get('common_ticker') or 'the common'}. "
                f"Strike {_money(terms.get('strike')) or 'not stated'}."
            ),
            ends=str(expiry) if expiry else None,
            ends_label=str(expiry) if expiry else "Expiry not stated",
            evidence_url=source.get("url"),
            evidence_label="Warrant exhibit",
            evidence_kind="filing" if source.get("url") else "screen",
            source_feed="warrants",
            as_of=str(source.get("latest_terms_as_of") or source.get("as_of") or "") or None,
            next_action=str(item.get("next_action") or "Verify strike, expiry, and transferability."),
            extra_id=str(item.get("warrant_id") or item.get("warrant_ticker") or ""),
        )
        if book == "ranked":
            ranked.append(row)
        else:
            history.append(row)
    discovery = []
    events = [event for event in (warrants.get("events") or []) if isinstance(event, dict)]
    events.sort(key=lambda event: str(event.get("filed_at") or ""), reverse=True)
    for event in events[:40]:
        hint = str(event.get("lane_hint") or "warrant")
        discovery.append(
            _row(
                lane="warrants",
                book="discovery",
                ticker=str(event.get("ticker") or event.get("issuer") or "Unresolved"),
                company=str(event.get("issuer") or ""),
                what=f"SEC warrant-language filing. Lane hint {hint}. Identity is not verified.",
                ends=None,
                ends_label="Not a listed series yet",
                evidence_url=event.get("source_url"),
                evidence_label=str(event.get("form") or "SEC"),
                evidence_kind="filing",
                source_feed="warrants",
                as_of=str(event.get("filed_at") or "")[:10] or None,
                next_action="Promote only after identity and transferability are verified.",
                extra_id=str(event.get("accession") or event.get("source_url") or hint),
            )
        )
    return ranked, discovery, history


def index_delete_rows(index_doc: dict) -> list[dict]:
    rows = []
    by_ticker = index_doc.get("by_ticker") or {}
    if not isinstance(by_ticker, dict):
        return rows
    for ticker, payload in by_ticker.items():
        if not isinstance(payload, dict):
            continue
        for event in payload.get("confirmed_events") or []:
            if not isinstance(event, dict):
                continue
            if event.get("action") != "delete":
                continue
            if event.get("style_subset"):
                continue
            headline = event.get("confidence") == "news_unconfirmed"
            ends = event.get("effective") or None
            rows.append(
                _row(
                    lane="forced_sellers",
                    book="ranked",
                    ticker=str(event.get("ticker") or ticker),
                    company=str(ticker),
                    what=(
                        f"Deletion from {event.get('index') or 'an index'}."
                        + (
                            " The source is a headline, not a provider notice."
                            if headline
                            else ""
                        )
                    ),
                    ends=str(ends) if ends else None,
                    ends_label=(
                        str(ends)
                        if ends
                        else f"Announced {event.get('announced') or 'date missing'}"
                    ),
                    evidence_url=event.get("source_url"),
                    evidence_label="Index note",
                    evidence_kind="news" if headline else "filing",
                    source_feed="index_membership",
                    as_of=str(event.get("announced") or "") or None,
                    next_action="Confirm the provider notice before treating the selling as mechanical.",
                    extra_id=f"{event.get('index')}|{event.get('announced')}",
                )
            )
    return rows


def separation_forced_seller_rows(separations: dict) -> list[dict]:
    """Modelled separation selling (dated window, % of float, days of volume)."""
    rows = []
    for item in separations.get("forced_seller_rows") or []:
        if not isinstance(item, dict) or not item.get("ticker"):
            continue
        start, end = item.get("window_start"), item.get("window_end")
        row = _row(
            lane="forced_sellers",
            book="ranked",
            ticker=str(item["ticker"]),
            company=str(item.get("ticker")),
            what=str(item.get("what") or "Modelled separation selling"),
            ends=end,
            ends_label=(
                f"Selling window {start or '?'} to {end or '?'}" if (start or end) else "Window not dated"
            ),
            evidence_url=item.get("evidence_url"),
            evidence_label="Separation filing",
            evidence_kind="filing" if item.get("evidence_url") else "screen",
            source_feed="separations",
            as_of=item.get("as_of"),
            next_action="A modelled flow is a timing input, not a value. Confirm float and volume before leaning on the window.",
            extra_id=f"{item.get('separation_id')}|{item.get('side')}",
        )
        row["separation_id"] = item.get("separation_id")
        row["flow"] = {
            "pct_of_float_base": item.get("pct_of_float_base"),
            "pct_of_adv_days": item.get("pct_of_adv_days"),
            "window_start": start,
            "window_end": end,
            "confidence": item.get("confidence") or "estimate",
        }
        rows.append(row)
    return rows


def nol_rows(nol: dict, live_tickers: set[str]) -> list[dict]:
    rows = []
    for item in nol.get("rows") or []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "")
        if not ticker:
            continue
        bankruptcy = (item.get("bankruptcy_382_exception") or {}).get("mentioned")
        prior = (item.get("prior_ownership_change") or {}).get("occurred")
        if bankruptcy:
            evidence = (item.get("bankruptcy_382_exception") or {}).get("evidence") or {}
            rows.append(
                _row(
                    lane="restructurings",
                    book="ranked",
                    ticker=ticker,
                    company=ticker,
                    what="Filing mentions a bankruptcy exception for the tax attributes.",
                    ends=None,
                    ends_label="Case clock is in the filing",
                    evidence_url=evidence.get("url") if isinstance(evidence, dict) else None,
                    evidence_label="Tax footnote",
                    evidence_kind="filing",
                    source_feed="nol_382_facts",
                    as_of=str(evidence.get("filed") or "") if isinstance(evidence, dict) else None,
                    next_action="Quote the filing. Do not treat the exception as available until the document says so.",
                    extra_id="bankruptcy",
                )
            )
        elif prior and ticker in live_tickers:
            evidence = (item.get("prior_ownership_change") or {}).get("evidence") or {}
            rows.append(
                _row(
                    lane="restructurings",
                    book="ranked",
                    ticker=ticker,
                    company=ticker,
                    what="A live deal sits on an issuer whose filing already records a Section 382 ownership change.",
                    ends=None,
                    ends_label="Annual limit is in the filing if stated",
                    evidence_url=evidence.get("url") if isinstance(evidence, dict) else None,
                    evidence_label="Tax footnote",
                    evidence_kind="filing",
                    source_feed="nol_382_facts",
                    as_of=str(evidence.get("filed") or "") if isinstance(evidence, dict) else None,
                    next_action="The NOL does not shelter an outside holder. Read the annual limit before treating it as consideration.",
                    extra_id="ownership-change",
                )
            )
    return rows


def buyback_event_rows(doc: dict | None) -> list[dict]:
    """Issuer tenders, accelerated repurchases, and large new programs. Research only."""
    rows = []
    for event in (doc or {}).get("events") or []:
        if not isinstance(event, dict):
            continue
        ticker = str(event.get("ticker") or "").upper()
        if not ticker:
            continue
        if event.get("book") == "mentions":
            continue
        book = event.get("book") if event.get("book") in {"ranked", "discovery", "history"} else "discovery"
        if (doc or {}).get("schema_version") == "buyback_radar.v2" and book == "ranked" and not event.get("terms_verified"):
            book = "discovery"
        row = _row(
            lane="buyback_events",
            book=book,
            ticker=ticker,
            company=str(event.get("company") or ticker),
            what=str(event.get("what") or "Buyback event"),
            ends=event.get("ends") or None,
            ends_label=str(event.get("ends_label") or "End date not stated"),
            evidence_url=event.get("url"),
            evidence_label="SEC filing",
            evidence_kind="filing",
            source_feed="buyback_radar",
            as_of=str(event.get("filed") or "")[:10] or None,
            next_action=event.get("next") or "Verify the current terms and status.",
            extra_id=str(event.get("accession") or event.get("event_type") or ""),
        )
        row["event_type"] = event.get("event_type")
        row["accession"] = event.get("accession")
        row["one_number"] = event.get("one_number")
        row["id"] = event.get("id") or row["id"]
        row["status"] = event.get("status") or "needs_review"
        row["buyback_event"] = event
        row["snapshot_id"] = (doc or {}).get("snapshot_id")
        row["research_only"] = True
        row["annualized_spread"] = None
        rows.append(row)
    return rows


def _sort_key(row: dict) -> tuple:
    ends = str(row.get("ends") or "9999-99-99")
    return (LANE_ORDER.get(row.get("lane"), 99), ends, str(row.get("ticker") or ""))


def build_book(
    *,
    news: dict | None = None,
    warrants: dict | None = None,
    activist: dict | None = None,
    index_doc: dict | None = None,
    cvr: dict | None = None,
    nol: dict | None = None,
    separations: dict | None = None,
    buyback: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    news = news or {}
    separations = separations or {}
    warrants = warrants or {}
    activist = activist or {}
    index_doc = index_doc or {}
    cvr = cvr or {}
    nol = nol or {}
    buyback = buyback or {}
    cvr_ranked, cvr_discovery = cvr_rows(cvr)
    warrant_ranked, warrant_discovery, history = warrant_rows(warrants)
    restructuring_news = restructuring_news_rows(news)
    separation_spins = spinoff_rows(news, separations)
    separation_splits = split_off_rows(separations)
    ranked = [
        *[r for r in separation_spins if r["book"] == "ranked"],
        *[r for r in separation_splits if r["book"] == "ranked"],
        *merger_news_rows(news),
        *cvr_ranked,
        *tender_rows(activist),
        *rights_news_rows(news),
        *warrant_ranked,
        *restructuring_news,
        *dividend_cut_rows(news),
        *index_delete_rows(index_doc),
        *separation_forced_seller_rows(separations),
        *[row for row in buyback_event_rows(buyback) if row["book"] == "ranked"],
    ]
    live = {
        row["ticker"]
        for row in ranked
        if row["lane"] in {"mergers", "restructurings"} and row["ticker"] not in {"", "—"}
    }
    ranked.extend(nol_rows(nol, live))
    ranked.sort(key=_sort_key)
    discovery = [
        *[r for r in separation_spins if r["book"] == "discovery"],
        *[r for r in separation_splits if r["book"] == "discovery"],
        *separation_event_rows(separations),
        *cvr_discovery,
        *warrant_discovery,
        *[row for row in buyback_event_rows(buyback) if row["book"] == "discovery"],
    ]
    history.extend(r for r in separation_spins + separation_splits if r["book"] == "history")
    history.extend(row for row in buyback_event_rows(buyback) if row["book"] == "history")
    discovery.sort(key=_sort_key)
    history.sort(key=_sort_key)

    def counts(rows: list[dict]) -> dict[str, int]:
        tally = {lane["id"]: 0 for lane in LANES}
        for row in rows:
            for lane in row.get("lanes") or [row.get("lane")]:
                if lane in tally:
                    tally[lane] += 1
        return tally

    return {
        "schema_version": SCHEMA,
        "generated_at": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "definition": (
            "A usual holder is forced to sell, or the security is too odd for the usual buyer, "
            "and the situation has a date when it ends. Spinoffs, merger securities, warrants, "
            "and restructurings follow Greenblatt. Forced sellers follow the Manual of Ideas. "
            "Buyback events are issuer tenders, accelerated share repurchases, and new programs "
            "of at least about 10 percent of market value. A plain authorization is a one-line mention."
        ),
        "caption": separations.get("caption"),
        "lanes": LANES,
        "counts": {
            "ranked": counts(ranked),
            "discovery": counts(discovery),
            "history": counts(history),
        },
        "rows": ranked,
        "discovery": discovery,
        "history": history,
        "buyback_mentions": list(buyback.get("program_mentions") or []),
        "buyback_snapshot": {"snapshot_id": buyback.get("snapshot_id"), "as_of": buyback.get("as_of")},
    }


def sources_present() -> list[Path]:
    required = [NEWS_PATH, WARRANTS_PATH, ACTIVIST_PATH, INDEX_PATH, CVR_PATH, SEPARATIONS_PATH]
    return [path for path in required if not path.is_file()]


def write_book(path: Path | None = None) -> Path | None:
    missing = sources_present()
    if missing:
        print("skip special situations; missing " + ", ".join(str(item) for item in missing))
        return None
    payload = build_book(
        news=_load(NEWS_PATH),
        warrants=_load(WARRANTS_PATH),
        activist=_load(ACTIVIST_PATH),
        index_doc=_load(INDEX_PATH),
        cvr=_load(CVR_PATH),
        nol=_load(NOL_PATH),
        separations=_load(SEPARATIONS_PATH),
        buyback=__import__("build_buyback_radar").load_buyback_projection(),
    )
    target = path or OUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    ranked = payload["counts"]["ranked"]
    print(
        f"Wrote {target} ranked={sum(ranked.values())} "
        f"discovery={len(payload['discovery'])} history={len(payload['history'])}"
    )
    return target


def refresh_buyback_projection(path=None):
    """Update this producer's buyback lane without rebuilding unrelated research."""
    from build_buyback_radar import load_buyback_projection
    from atomic_io import write_json_if_changed
    target=path or OUT_PATH
    doc=_load(target)
    if not doc:raise ValueError("Existing Special Situations book is required")
    projection=load_buyback_projection()
    if not projection.get("snapshot_id"):raise ValueError("Verified buyback snapshot unavailable")
    for key,book in (("rows","ranked"),("discovery","discovery"),("history","history")):
        rows=[r for r in doc.get(key,[]) if r.get("lane")!="buyback_events"]
        rows.extend(r for r in buyback_event_rows(projection) if r["book"]==book)
        doc[key]=sorted(rows,key=_sort_key)
        counts=doc.setdefault("counts",{}).setdefault(book,{})
        counts["buyback_events"]=sum(r.get("lane")=="buyback_events" for r in rows)
    doc["buyback_mentions"]=projection.get("program_mentions",[])
    doc["buyback_snapshot"]={k:projection.get(k) for k in ("snapshot_id","as_of","generated_at")}
    write_json_if_changed(target,doc)
    return doc

def main() -> None:
    import sys
    if sys.argv[1:]==["--refresh-buyback-projection"]:
        refresh_buyback_projection()
    else:
        write_book()


if __name__ == "__main__":
    main()
