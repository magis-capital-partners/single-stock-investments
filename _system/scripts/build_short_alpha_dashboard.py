#!/usr/bin/env python3
"""Compile the Short Alpha ledger: frameworks, names that fit, and the open book.

Positions stay in ideas.json and must point at a candidate. Activist-index
hits and always-review filing events become leads. A new lead never overwrites
a rejected, live, closed, or researching row.

Candidate rows follow Michael's Short-Selling entry contract
(_system/research/short-alpha/schema.json $defs.candidate, README.md next to
it): optional source, added_on/updated_on, tags, summary, note_ref, category
and lens_reviews. --check enforces the rules the schema cannot (date order,
desk_note required fields, framework ids) and CATEGORY_LENSES turns a
category into effective frameworks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "research" / "short-alpha"
POSITIONS = LEDGER / "ideas.json"
CANDIDATES = LEDGER / "candidates.json"
CATALOG = LEDGER / "frameworks.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_alpha.json"
BORROW = ROOT / "dashboard" / "data" / "short_alpha_borrow.json"
CROWDING = ROOT / "_system" / "reference" / "market-data" / "ownership" / "biotech_short_interest.json"
# FINRA short interest via Yahoo (fetch_float_adv.py, the daily technicals job): the
# broad days-to-cover source. The biotech file is the fallback for symbols it lacks.
FLOAT_ADV = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "index_float_adv.json"
SCREEN = ROOT / "dashboard" / "data" / "short_quant_screen.json"
SCREEN_ROWS = 25
FUGAZI = ROOT / "_system" / "reference" / "activist-reports" / "short_scorecard" / "Fugazi_Research.csv"
# Leads a human or an audit dropped, with the reason, so discovery never re-adds
# them: {"excluded": {TICKER: {"reason", "decided_on", "source_urls"?}}}. With
# source_urls only those reports are excluded (a misattribution); without, the
# ticker is (an OTC-only listing, an ETP, a split that never happened).
EXCLUDED_LEADS = LEDGER / "excluded_leads.json"
SECURITY_MASTER = ROOT / "_system" / "reference" / "securities" / "security_master.json"
EXCLUDED_TICKERS = {"ECHX"}  # Managed in the ls-algo universe, not this book.
REVIEWED_ON = "2026-10-07"
LIVE_STAGES = {"live", "closed", "researching", "ic"}
# Auto-created leads that nobody has worked on are refreshed from discovery on
# every sync (and dropped when discovery no longer produces them). A row with a
# source, summary, category, tags, note, hypothesis or frameworks is curated and
# never touched.
AUTO_LEAD_ORIGINS = {"activist_index", "fugazi_scorecard"}
CURATED_FIELDS = ("source", "summary", "category", "tags", "note_ref", "hypothesis", "lens_reviews", "frameworks")
# Gates fire on readings that matter, not on the mere presence of data. A quoted
# fee is context; a fee that can consume a short's edge, or no shares to borrow,
# is a gate. Days to cover or short interest at crowded levels is a squeeze risk.
HTB_FEE_PCT = 10.0
CROWDED_DAYS_TO_COVER = 5.0
CROWDED_SHORT_FLOAT = 0.20
_TITLE_TAIL = re.compile(r"\s*(?:Published\s+\d+\s+\w+\s+ago|Download\s+(?:the\s+)?PDF|Read\s+(?:the\s+)?(?:full\s+)?(?:report|more)|Continue\s+reading)\b.*$", re.I | re.S)
ALWAYS_REVIEW_TAGS = {
    "going_concern",
    "restatement",
    "material_weakness",
    "auditor_change",
    "related_party",
    "investigation",
    "litigation",
}
FURNACE_TAG_MAP = {
    "going_concern": "cash_burn",
    "cash_runway": "cash_burn",
    "covenant_pressure": "leverage_refinancing",
    "refinancing": "leverage_refinancing",
    "financing_gap": "leverage_refinancing",
    "serial_equity_issuance": "dilution_financing",
    "warrant_overhang": "dilution_financing",
    "revenue_recognition": "revenue_recognition",
    "capitalization": "capitalization_reserves",
    "reserve_release": "capitalization_reserves",
    "restatement": "reporting_integrity",
    "material_weakness": "reporting_integrity",
    "auditor_change": "reporting_integrity",
    "non_gaap": "acquisition_nongaap_kpi",
    "acquisition_accounting": "acquisition_nongaap_kpi",
    "margin_contraction": "margin_contraction",
    "utilization": "margin_contraction",
    "supply_build": "supply_side",
    "related_party": "governance_related_party",
    "controlling_holder": "governance_related_party",
    "compensation": "governance_related_party",
    "executive_exit": "governance_related_party",
    "investigation": "regulatory",
    "litigation": "regulatory",
    "license": "regulatory",
    "delisting": "regulatory",
    "daily_reset": "structural_decay",
    "tracking_risk": "structural_decay",
    "swap_exposure": "structural_decay",
    "reverse_split": "reverse_split_impairment",
}

# Michael's Short-Selling entry contract (schema.json $defs.candidate). The
# enums below mirror the schema; test_short_alpha_contract.py keeps them equal.
ORIGINS = {
    "position", "activist_index", "filing_furnace", "browser_draft", "fugazi_scorecard",
    "desk_note", "reverse_split_research",
}
CATEGORIES = (
    "accounting", "shitco-concept", "supply-side", "share-supply",
    "reverse-split", "activist-short", "borrow-squeeze", "playbook",
)
# Category -> lenses a row inherits when it names a category. The map is the
# one in _system/proposals/one_hub_for_humans_and_bots_2026-10-11.md and
# _system/research/short-alpha/README.md. Empty lists are deliberate:
# activist-short is an origin (activist_index), playbook is not a lens.
CATEGORY_LENSES: dict[str, list[str]] = {
    "accounting": ["accounting", "revenue_recognition", "earnings_vs_cash", "working_capital"],
    "shitco-concept": ["promotion_insider_selling", "fad_single_product"],
    "supply-side": ["supply_side", "margin_contraction", "cycle_mean_reversion"],
    "share-supply": ["dilution_financing", "share_supply"],
    "reverse-split": ["reverse_split_impairment"],
    "activist-short": [],
    "borrow-squeeze": ["borrow_and_carry", "crowding_squeeze"],
    "playbook": [],
}
# Lenses a category points at but which only a human conclusion may set. The
# category map never applies them (frameworks.json: "a publisher report cannot
# set it"); they are listed so the README and the code agree.
CATEGORY_CONCLUSION_ONLY: dict[str, list[str]] = {"shitco-concept": ["fraud_bad_actors"]}
LENS_REVIEW_STATUSES = {"unreviewed", "unresolved", "supported", "contradicted"}
# A desk note is a bot's or an author's idea entry: unattributable rows and
# rows without a narrative pointer are refused rather than rendered.
DESK_NOTE_REQUIRED = ("source", "category", "added_on", "updated_on", "summary", "tags", "note_ref")
TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$")
TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
YMD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VAULT_NOTE_RE = re.compile(
    r"^research-vault/short-research/[A-Z]{1,5}(?:[.-][A-Z]{1,2})?/\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)
SSI_PATH_RE = re.compile(r"^(?!research-vault/)(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_][A-Za-z0-9_./-]*$")
SUMMARY_MAX = 400
SOURCE_MAX = 80


class LedgerError(ValueError):
    """Raised when the source ledger would produce a misleading dashboard."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"Missing Short Alpha source: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path.name} root must be an object")
    return value


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _scan():
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import short_scan_batch

    return short_scan_batch


def furnace_hits(events: list) -> list[dict]:
    """Map filing-furnace events onto framework ids. Unknown tags stay visible."""
    hits: list[dict] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        tags = event.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        impact = str(event.get("short_impact") or "strengthens")
        for tag in tags:
            tag_id = str(tag)
            hits.append({
                "tag": tag_id,
                "framework_id": FURNACE_TAG_MAP.get(tag_id),
                "short_impact": impact,
                "claim": event.get("claim") or "",
                "evidence_ref": event.get("evidence_ref") or "",
                "filed_at": event.get("filed_at") or "",
            })
    return hits


def load_furnace_events(ticker: str) -> list[dict]:
    path = ROOT / ticker / "research" / "evidence" / "short_furnace_events.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    events = payload.get("events") if isinstance(payload, dict) else payload
    return [row for row in events if isinstance(row, dict)] if isinstance(events, list) else []


def load_excluded_leads(path: Path | None = None) -> dict[str, dict]:
    path = EXCLUDED_LEADS if path is None else path
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(k).upper(): (v or {}) for k, v in (doc.get("excluded") or {}).items()}


def apply_exclusions(lead: dict, excluded: dict[str, dict]) -> dict | None:
    """The lead without its excluded reports, or None when nothing is left or
    the whole ticker is excluded."""
    rule = excluded.get(str(lead.get("ticker") or "").upper())
    if rule is None:
        return lead
    urls = set(rule.get("source_urls") or [])
    if not urls:
        return None
    kept = [s for s in lead.get("sources") or [] if s.get("url") not in urls]
    if not kept:
        return None
    copy = json.loads(json.dumps(lead))
    copy["sources"] = kept
    return copy


def is_curated(row: dict) -> bool:
    """Has a human (or an audit) worked on this row? Then discovery never touches it."""
    if str(row.get("origin") or "") not in AUTO_LEAD_ORIGINS or row.get("stage") != "lead":
        return True
    if any(row.get(field) for field in CURATED_FIELDS):
        return True
    return str((row.get("research") or {}).get("status") or "lead") != "lead"


def upsert_leads(existing: list[dict], incoming: list[dict], excluded: dict[str, dict] | None = None) -> tuple[list[dict], list[str]]:
    """Append tickers that are not already tracked. Never replace an existing row."""
    excluded = load_excluded_leads() if excluded is None else excluded
    seen = {str(row.get("ticker") or "").upper() for row in existing}
    added_rows: list[dict] = []
    added_ids: list[str] = []
    for row in incoming:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in seen or ticker in EXCLUDED_TICKERS:
            continue
        row = apply_exclusions(row, excluded)
        if row is None:
            continue
        copy = json.loads(json.dumps(row))
        copy["ticker"] = ticker
        added_rows.append(copy)
        added_ids.append(ticker)
        seen.add(ticker)
    return existing + added_rows, added_ids


def refresh_auto_leads(existing: list[dict], incoming: list[dict], excluded: dict[str, dict] | None = None) -> tuple[list[dict], list[str], list[str]]:
    """Rebuild uncurated auto leads from today's discovery. A lead whose reports
    were re-attributed or excluded since it was created disappears; one whose
    sources or name improved is updated. Curated rows are returned untouched.
    Returns (rows, refreshed tickers, dropped tickers)."""
    excluded = load_excluded_leads() if excluded is None else excluded
    fresh = {}
    for lead in incoming:
        lead = apply_exclusions(lead, excluded)
        if lead is not None:
            fresh.setdefault(str(lead.get("ticker") or "").upper(), lead)
    rows, refreshed, dropped = [], [], []
    for row in existing:
        ticker = str(row.get("ticker") or "").upper()
        if is_curated(row):
            rows.append(row)
            continue
        lead = fresh.get(ticker)
        if lead is None or lead.get("origin") != row.get("origin"):
            dropped.append(ticker)
            continue
        if lead.get("sources") != row.get("sources") or lead.get("security_name") != row.get("security_name"):
            row = json.loads(json.dumps(row))
            row["sources"] = lead.get("sources") or []
            row["security_name"] = lead.get("security_name") or row.get("security_name") or ticker
            refreshed.append(ticker)
        rows.append(row)
    return rows, refreshed, dropped


def _blank_research(next_step: str) -> dict:
    return {"status": "lead", "ic": "not_ready", "next_step": next_step}


def _lead_shell(ticker: str, company: str, origin: str, sources: list[dict], frameworks: list[str]) -> dict:
    primary = frameworks[0] if frameworks else None
    return {
        "ticker": ticker,
        "security_name": company or ticker,
        "instrument_type": "operating_company",
        "stage": "lead",
        "origin": origin,
        "frameworks": frameworks,
        "primary_framework": primary,
        "hypothesis": "",
        "catalysts": [],
        "falsifiers": [],
        "research": _blank_research(
            "Write the market belief, the variant view, one catalyst, and one falsifier before promoting this lead."
        ),
        "sources": sources,
        "gates": {"path_and_timing": "unscored", "issuer_retaliation": "unscored"},
    }


def clean_title(title: str, firm: str = "", day: str = "") -> str:
    """A report title without scraped card text, bylines or a repeated date."""
    text = _TITLE_TAIL.sub("", re.sub(r"\s+", " ", str(title or ""))).strip(" -·|")
    if not text or text.lower() in {firm.lower(), day.lower()}:
        return ""
    if re.fullmatch(r"(?:[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2})", text):
        return ""
    if len(text) > 160:
        text = text[:160].rsplit(" ", 1)[0] + "…"
    return text


def lead_from_reports(ticker: str, company: str, reports: list[dict]) -> dict:
    sources: list[dict] = []
    ordered = sorted(reports, key=lambda row: str(row.get("report_date") or ""), reverse=True)
    seen_urls: set[str] = set()
    for report in ordered:
        url = str(report.get("source_url") or "").split("?utm_")[0]
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        firm = str(report.get("firm_name") or report.get("firm_id") or "Short report")
        day = str(report.get("report_date") or "")
        if day and report.get("date_precision") == "year":
            day = day[:4]
        bits = [firm] + ([day] if day else [])
        title = clean_title(report.get("title") or "", firm, day)
        if title:
            bits.append(title)
        source = {
            "type": "activist_short_report",
            "label": " · ".join(bits),
            "firm_id": report.get("firm_id") or "",
            "report_date": report.get("report_date") or "",
        }
        if url:
            source["url"] = url
        if report.get("local_file"):
            source["ref"] = str(report["local_file"]).replace("\\", "/")
        sources.append(source)
    return _lead_shell(ticker, company, "activist_index", sources, [])


def lead_from_furnace(ticker: str, company: str, events: list[dict]) -> dict | None:
    hits = [
        hit for hit in furnace_hits(events)
        if hit["tag"] in ALWAYS_REVIEW_TAGS and hit["short_impact"] != "weakens" and hit["framework_id"]
    ]
    if not hits:
        return None
    frameworks: list[str] = []
    sources: list[dict] = []
    for hit in hits:
        if hit["framework_id"] not in frameworks:
            frameworks.append(hit["framework_id"])
        source = {
            "type": "filing_furnace",
            "label": hit["claim"] or hit["tag"],
            "tag": hit["tag"],
            "filed_at": hit["filed_at"],
        }
        if hit["evidence_ref"]:
            source["ref"] = hit["evidence_ref"]
        sources.append(source)
    return _lead_shell(ticker, company, "filing_furnace", sources, frameworks)


def _fugazi_title(url: str) -> str:
    """The post slug as a title: /p/sharplink-gaming-sbet-ethereum-dream -> Sharplink gaming sbet ethereum dream."""
    slug = str(url or "").rstrip("/").rsplit("/", 1)[-1]
    words = [w for w in re.split(r"[-_]+", slug) if w]
    return " ".join(words).capitalize() if words else ""


def leads_from_fugazi_rows(rows: list[dict]) -> list[dict]:
    """One lead per tradable symbol. A publisher scorecard is a lead, not a thesis.
    A scorecard row whose company now quotes under another symbol is keyed on
    that symbol (borrow, screen and crowding all look it up), and the label keeps
    the scorecard ticker."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        listed = str(row.get("ticker") or "").upper().strip()
        quote = str(row.get("quote_symbol") or "").upper().strip()
        ticker = quote or listed
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    leads: list[dict] = []
    for ticker, reports in sorted(grouped.items()):
        reports.sort(key=lambda item: str(item.get("report_date") or ""))
        company = re.sub(r"\s*\([^)]*\)\s*$", "", str(reports[-1].get("target") or ticker)).strip() or ticker
        sources = []
        for report in reversed(reports):
            listed = str(report.get("ticker") or "").upper()
            bits = ["Fugazi Research", str(report.get("report_date") or "undated")]
            title = _fugazi_title(report.get("report_url"))
            if title:
                bits.append(title)
            label = " · ".join(bits)
            if listed and listed != ticker:
                label += f" (scorecard ticker {listed})"
            source = {"type": "activist_short_report", "label": label, "firm_id": "fugazi",
                      "report_date": report.get("report_date") or ""}
            if report.get("report_url"):
                source["url"] = report["report_url"]
            sources.append(source)
        leads.append(_lead_shell(ticker, company, "fugazi_scorecard", sources, []))
    return leads


def discover_fugazi_leads() -> list[dict]:
    if not FUGAZI.exists():
        return []
    import csv

    with FUGAZI.open(newline="", encoding="utf-8") as handle:
        return leads_from_fugazi_rows(list(csv.DictReader(handle)))


def master_names(path: Path | None = None) -> dict[str, str]:
    """Ticker -> company name from the committed security master."""
    path = SECURITY_MASTER if path is None else path
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(t).upper(): str(row.get("name")) for t, row in doc.items() if isinstance(row, dict) and row.get("name")}


def company_name(ticker: str, *sources: dict) -> str:
    """The first real name for a ticker: a name equal to the ticker is no name."""
    for names in sources:
        name = str((names or {}).get(ticker) or "").strip()
        if name and name.upper() != ticker.upper():
            return name
    return ticker


def discover_leads() -> list[dict]:
    scan = _scan()
    names = scan.company_names()
    master = master_names()
    incoming: list[dict] = []
    for ticker, reports in sorted(scan.collect_feed_shorts().items()):
        incoming.append(lead_from_reports(ticker, company_name(ticker, names, master), reports))
    for ticker in sorted(names):
        if ticker in EXCLUDED_TICKERS:
            continue
        lead = lead_from_furnace(ticker, company_name(ticker, names, master), load_furnace_events(ticker))
        if lead:
            incoming.append(lead)
    incoming.extend(discover_fugazi_leads())
    return incoming


def init_candidates() -> None:
    """One-time split of the August 2026 position file into candidates plus positions."""
    if CANDIDATES.exists():
        raise LedgerError(f"{CANDIDATES.relative_to(ROOT)} already exists; refusing to overwrite it")
    raw = _read_json(POSITIONS)
    candidates: list[dict] = []
    slim: list[dict] = []
    for idea in raw.get("ideas") or []:
        ticker = str(idea.get("ticker") or "").upper()
        if ticker in EXCLUDED_TICKERS:
            slim.append(idea)
            continue
        research = dict(idea.get("research") or {})
        research["reviewed_on"] = REVIEWED_ON
        research["review_note"] = (
            "Reviewed 2026-10-07. The price baseline remains the 2026-08-04 check-in."
        )
        candidate = {
            "ticker": ticker,
            "security_name": idea.get("security_name") or ticker,
            "instrument_type": idea.get("instrument_type") or "operating_company",
            "stage": "live",
            "origin": "position",
            "frameworks": list(idea.get("frameworks") or []),
            "primary_framework": idea.get("primary_framework"),
            "hypothesis": idea.get("hypothesis") or "",
            "catalysts": list(idea.get("catalysts") or []),
            "falsifiers": list(idea.get("falsifiers") or []),
            "research": research,
            "sources": list(idea.get("sources") or []),
            "gates": {"path_and_timing": "unscored", "issuer_retaliation": "unscored"},
        }
        if idea.get("underlying"):
            candidate["underlying"] = idea["underlying"]
        candidates.append(candidate)
        slim.append({
            "ticker": ticker,
            "position": idea.get("position") or {},
            "check_ins": idea.get("check_ins") or [],
        })
    _write_json(CANDIDATES, {
        "schema_version": "1.1",
        "as_of": REVIEWED_ON,
        "candidates": candidates,
    })
    _write_json(POSITIONS, {
        "schema_version": "1.1",
        "as_of": REVIEWED_ON,
        "currency": raw.get("currency", "USD"),
        "ideas": slim,
    })


def _framework_ids(catalog: dict) -> list[str]:
    return [str(row.get("id") or "") for row in catalog.get("frameworks") or []]


def _validate_catalog(catalog: dict) -> None:
    ids = _framework_ids(catalog)
    if not ids or len(ids) != len(set(ids)):
        raise LedgerError("Framework ids must be present and unique")
    source_ids = [str(row.get("id") or "") for row in catalog.get("source_types") or []]
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise LedgerError("Source-type ids must be present and unique")
    group_ids = {str(row.get("id") or "") for row in catalog.get("groups") or []}
    parents = set(ids)
    for row in catalog.get("frameworks") or []:
        parent = row.get("parent")
        if parent and parent not in parents:
            raise LedgerError(f"{row.get('id')}: unknown parent {parent}")
        if str(row.get("kind") or "") not in {"judgment", "screen", "gate"}:
            raise LedgerError(f"{row.get('id')}: kind must be judgment, screen, or gate")
        if row.get("group") not in group_ids:
            raise LedgerError(f"{row.get('id')}: unknown group {row.get('group')}")
        unknown = sorted(set(row.get("source_types") or []) - set(source_ids))
        if unknown:
            raise LedgerError(f"{row.get('id')}: unknown source types {unknown}")
    for category, lenses in CATEGORY_LENSES.items():
        missing = sorted(set(lenses) - parents)
        if missing:
            raise LedgerError(f"CATEGORY_LENSES[{category}] names unknown frameworks {missing}")


def _check_ymd(ticker: str, key: str, value) -> None:
    if not isinstance(value, str) or not YMD_RE.match(value):
        raise LedgerError(f"{ticker}: {key} must be a YYYY-MM-DD date, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"{ticker}: {key} is not a real date ({value})") from exc


def _validate_candidate_contract(candidate: dict) -> None:
    """Michael's entry contract on one row: attribution, dates, tags, note pointer, lens reviews."""
    ticker = str(candidate.get("ticker") or "")
    if not TICKER_RE.match(ticker):
        raise LedgerError(f"Candidate ticker fails the schema pattern: {ticker or '<blank>'}")
    origin = candidate.get("origin")
    if origin is not None and origin not in ORIGINS:
        raise LedgerError(f"{ticker}: unknown origin {origin}")
    if "category" in candidate and candidate["category"] not in CATEGORIES:
        raise LedgerError(f"{ticker}: unknown category {candidate['category']!r}")
    if "source" in candidate:
        source = candidate["source"]
        if not isinstance(source, str) or not source.strip() or len(source) > SOURCE_MAX:
            raise LedgerError(f"{ticker}: source must be a non-empty string of at most {SOURCE_MAX} characters")
    if "summary" in candidate:
        summary = candidate["summary"]
        if not isinstance(summary, str) or len(summary) > SUMMARY_MAX:
            raise LedgerError(f"{ticker}: summary must be a string of at most {SUMMARY_MAX} characters")
    if "tags" in candidate:
        tags = candidate["tags"]
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not TAG_RE.match(tag) for tag in tags):
            raise LedgerError(f"{ticker}: tags must be lowercase kebab-case strings")
        if len(set(tags)) != len(tags):
            raise LedgerError(f"{ticker}: tags must be unique")
    for key in ("added_on", "updated_on"):
        if key in candidate:
            _check_ymd(ticker, key, candidate[key])
    if "added_on" in candidate and "updated_on" in candidate and candidate["updated_on"] < candidate["added_on"]:
        raise LedgerError(f"{ticker}: updated_on must be on or after added_on")
    if "note_ref" in candidate:
        ref = candidate["note_ref"]
        if not isinstance(ref, str) or not (VAULT_NOTE_RE.match(ref) or SSI_PATH_RE.match(ref)):
            raise LedgerError(
                f"{ticker}: note_ref must be research-vault/short-research/{{TICKER}}/{{date}}-{{slug}}.md "
                f"or a repository-relative path, got {ref!r}"
            )
    reviews = candidate.get("lens_reviews")
    if reviews is not None:
        if not isinstance(reviews, list):
            raise LedgerError(f"{ticker}: lens_reviews must be a list")
        seen: set[str] = set()
        for review in reviews:
            lens_id = str((review or {}).get("lens_id") or "") if isinstance(review, dict) else ""
            if not lens_id or lens_id in seen:
                raise LedgerError(f"{ticker}: lens_reviews need unique lens_id values")
            seen.add(lens_id)
            if review.get("status") not in LENS_REVIEW_STATUSES:
                raise LedgerError(f"{ticker}: lens review {lens_id} has status {review.get('status')!r}")
    if origin == "desk_note":
        missing = [key for key in DESK_NOTE_REQUIRED if not candidate.get(key)]
        if missing:
            raise LedgerError(f"{ticker}: a desk_note row requires {missing}")


def _validate_bundle(positions: list, candidates: list, catalog: dict) -> None:
    _validate_catalog(catalog)
    framework_ids = set(_framework_ids(catalog))
    source_ids = {str(row.get("id") or "") for row in catalog.get("source_types") or []}
    by_ticker: dict[str, dict] = {}
    for candidate in candidates:
        ticker = str(candidate.get("ticker") or "").upper()
        if not ticker or ticker in by_ticker:
            raise LedgerError(f"Candidate ticker must be present and unique: {ticker or '<blank>'}")
        by_ticker[ticker] = candidate
        _validate_candidate_contract(candidate)
        tags = list(candidate.get("frameworks") or [])
        unknown = sorted(set(tags) - framework_ids)
        if unknown:
            raise LedgerError(f"{ticker}: unknown frameworks {unknown}")
        primary = candidate.get("primary_framework")
        stage = str(candidate.get("stage") or "")
        if tags and primary not in tags:
            raise LedgerError(f"{ticker}: primary framework must also be in frameworks")
        if not tags and primary not in (None, ""):
            raise LedgerError(f"{ticker}: primary framework must also be in frameworks")
        if stage in LIVE_STAGES:
            if not str(candidate.get("hypothesis") or "").strip():
                raise LedgerError(f"{ticker}: {stage} requires a hypothesis")
            if not tags:
                raise LedgerError(f"{ticker}: {stage} requires a framework")
        unknown_sources = sorted(
            {str(row.get("type") or "") for row in candidate.get("sources") or []} - source_ids
        )
        if unknown_sources:
            raise LedgerError(f"{ticker}: unknown source types {unknown_sources}")

    seen_positions: set[str] = set()
    for idea in positions:
        ticker = str(idea.get("ticker") or "").upper()
        if not ticker or ticker in seen_positions:
            raise LedgerError(f"Ticker must be present and unique: {ticker or '<blank>'}")
        seen_positions.add(ticker)
        if ticker in EXCLUDED_TICKERS:
            continue
        candidate = by_ticker.get(ticker)
        if candidate is None:
            raise LedgerError(f"{ticker}: position requires a candidate")
        if str(candidate.get("stage") or "") not in LIVE_STAGES:
            raise LedgerError(f"{ticker}: a position cannot stay in stage {candidate.get('stage')}")
        shares = float((idea.get("position") or {}).get("shares") or 0)
        opened = float((idea.get("position") or {}).get("opened_price") or 0)
        split_factor = float((idea.get("position") or {}).get("split_adjustment_factor") or 1)
        if shares >= 0 or opened <= 0 or split_factor <= 0:
            raise LedgerError(f"{ticker}: shares must be negative and opened price/split factor positive")
        check_ins = idea.get("check_ins") or []
        if not check_ins:
            raise LedgerError(f"{ticker}: at least one dated check-in is required")
        for row in check_ins:
            if float(row.get("price") or 0) <= 0:
                raise LedgerError(f"{ticker}: check-in prices must be positive")


_TRACKED: set[str] | None = None


def _tracked_files() -> set[str] | None:
    """Every path committed at HEAD, so a sparse or partial checkout (CI builds in
    one) reads the same as a full one. None when git is unavailable."""
    global _TRACKED
    if _TRACKED is None:
        import subprocess

        try:
            out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
            _TRACKED = {p for p in out.stdout.decode("utf-8", "replace").split("\0") if p}
        except (OSError, subprocess.CalledProcessError):
            _TRACKED = set()
    return _TRACKED or None


def _present(rel: str) -> bool:
    tracked = _tracked_files()
    return rel in tracked if tracked is not None else (ROOT / rel).exists()


def _artifact_status(candidate: dict) -> dict:
    ticker = str(candidate["ticker"])
    tracked = _tracked_files()
    prefix = f"{ticker}/research/"
    if tracked is not None:
        deep_dives = sorted(p for p in tracked if p.startswith(prefix + "deep_dive_") and p.endswith(".md") and "/" not in p[len(prefix):])
        folder = any(p.startswith(f"{ticker}/") for p in tracked)
    else:
        research_dir = ROOT / ticker / "research"
        deep_dives = sorted(p.relative_to(ROOT).as_posix() for p in research_dir.glob("deep_dive_*.md")) if research_dir.is_dir() else []
        folder = (ROOT / ticker).is_dir()
    source_refs = [row.get("ref") for row in candidate.get("sources") or [] if row.get("ref")]
    missing_refs = [str(ref) for ref in source_refs if not _present(str(ref))]
    research = candidate.get("research") or {}
    valuation = _present(prefix + "valuation.json")
    workbench = _present(prefix + "valuation_workbench.json")
    dossier = _present(prefix + "dossier.json")
    score = 0
    score += 25 if deep_dives else 0
    score += 20 if valuation else 0
    score += 15 if workbench else 0
    score += 15 if dossier else 0
    score += 15 if len(source_refs) >= 3 and not missing_refs else 0
    score += 10 if str(research.get("ic") or "").lower() in {"ready", "complete", "approved"} else 0
    return {
        "ticker_folder": folder,
        "deep_dive_count": len(deep_dives),
        "latest_deep_dive": deep_dives[-1] if deep_dives else None,
        "valuation_present": valuation,
        "workbench_present": workbench,
        "dossier_present": dossier,
        "missing_source_refs": missing_refs,
        "completion_pct": score,
    }


def _gate_hits(borrow: dict, crowding: dict | None, gates: dict) -> list[str]:
    hits: list[str] = []
    rate = borrow.get("rate_pct")
    if borrow.get("status") == "none_available" or (borrow.get("status") == "available" and rate is not None and float(rate) >= HTB_FEE_PCT):
        hits.append("borrow_and_carry")
    if crowding and (float(crowding.get("days_to_cover") or 0) >= CROWDED_DAYS_TO_COVER
                     or float(crowding.get("short_percent_float") or 0) >= CROWDED_SHORT_FLOAT):
        hits.append("crowding_squeeze")
    if str((gates or {}).get("path_and_timing") or "unscored") not in {"", "unscored"}:
        hits.append("path_and_timing")
    if str((gates or {}).get("issuer_retaliation") or "unscored") not in {"", "unscored"}:
        hits.append("issuer_retaliation")
    return hits


def borrow_reading(ticker: str, rates: dict, borrow_doc: dict) -> dict:
    """One name's borrow: a quoted fee (with shares available when the file
    has them), none available, not in the file, or pending a refresh."""
    rate = rates.get(ticker)
    avail = (borrow_doc.get("availability") or {}).get(ticker)
    if rate or avail:
        out = dict(rate or {"status": "available", "source": avail.get("source"), "as_of": avail.get("as_of")})
        if avail:
            out["shares"] = avail.get("shares")
            if avail.get("at_least"):
                out["at_least"] = True
            if avail.get("status") == "none_reported" or not avail.get("shares"):
                out["status"] = "none_available"
        return out
    if ticker in set(borrow_doc.get("checked") or []):
        return {
            "status": "not_in_file",
            "source": "IBKR public short-stock availability file",
            "as_of": borrow_doc.get("as_of"),
            "message": "Not in IBKR's short-stock file: no lendable shares at IBKR, or not a US listing it lends.",
        }
    return {"status": "pending", "source": "IBKR borrow feed", "message": "Added after the last IBKR borrow refresh."}


def crowding_reading(ticker: str, float_rows: dict, biotech_rows: dict) -> dict | None:
    """FINRA short interest via the float file, else the biotech file."""
    row = float_rows.get(ticker)
    if isinstance(row, dict) and row.get("days_to_cover") is not None:
        return {
            "days_to_cover": row.get("days_to_cover"),
            "short_percent_float": row.get("short_percent_float"),
            "settlement_ymd": row.get("short_interest_date"),
            "source": "finra_short_interest_via_yahoo",
            "tier": "context",
        }
    row = biotech_rows.get(ticker)
    if isinstance(row, dict) and row.get("days_to_cover") is not None:
        return {
            "days_to_cover": row.get("days_to_cover"),
            "settlement_ymd": row.get("settlement_ymd"),
            "source": "finra_biweekly",
            "tier": "context",
        }
    return None


def _borrow_file_time(borrow_doc: dict, rates: dict) -> str | None:
    """When IBKR's file was read: the rows' own stamp, else the refresh time."""
    stamps = sorted({str(r.get("as_of")) for r in rates.values() if isinstance(r, dict) and r.get("as_of")})
    return stamps[-1] if stamps else (borrow_doc.get("as_of") or None)


def _effective_frameworks(candidate: dict, hits: list[dict]) -> list[str]:
    """Explicit frameworks, then the lenses the category implies, then furnace hits."""
    ordered: list[str] = []
    for tag in list(candidate.get("frameworks") or []):
        if tag not in ordered:
            ordered.append(tag)
    for tag in CATEGORY_LENSES.get(str(candidate.get("category") or ""), []):
        if tag not in ordered:
            ordered.append(tag)
    for hit in hits:
        framework_id = hit.get("framework_id")
        if hit.get("short_impact") == "weakens" or not framework_id:
            continue
        if framework_id not in ordered:
            ordered.append(framework_id)
    return ordered


def load_screen(path: Path = SCREEN) -> dict | None:
    """The quant screen, or None when it has not been built on this checkout."""
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except LedgerError:
        return None


def _screen_payload(screen: dict | None, tracked: set[str]) -> dict | None:
    """Top untracked screen rows plus the method, for the Shorts tab."""
    if not screen:
        return None
    rows = [row for row in screen.get("rows") or [] if row.get("score") is not None and str(row.get("ticker")).upper() not in tracked]
    rows.sort(key=lambda row: (-float(row["score"]), str(row["ticker"])))
    methodology = screen.get("methodology") or {}
    return {
        "generated_at": screen.get("generated_at"),
        "universe_count": screen.get("universe_count"),
        "scored_count": screen.get("scored_count"),
        "methodology": {key: methodology.get(key) for key in ("composite", "minimum_evidence", "reading")},
        "signals": methodology.get("signals") or {},
        "rows": rows[:SCREEN_ROWS],
    }


def build(
    positions: list | None = None,
    candidates: list | None = None,
    catalog: dict | None = None,
    borrow_rows: dict | None = None,
    crowding_rows: dict | None = None,
    furnace_by_ticker: dict | None = None,
    screen: dict | None = None,
    float_rows: dict | None = None,
) -> dict:
    position_doc = _read_json(POSITIONS) if positions is None else {"ideas": positions}
    candidate_doc = _read_json(CANDIDATES) if candidates is None else {"candidates": candidates, "as_of": REVIEWED_ON}
    catalog_doc = _read_json(CATALOG) if catalog is None else catalog
    position_rows = list(position_doc.get("ideas") or [])
    candidate_rows = list(candidate_doc.get("candidates") or [])
    _validate_bundle(position_rows, candidate_rows, catalog_doc)

    borrow_doc: dict = {}
    if borrow_rows is None:
        borrow_doc = _read_json(BORROW) if BORROW.exists() else {}
        borrow_rows = borrow_doc.get("rates") or {}
    if float_rows is None and crowding_rows is None and FLOAT_ADV.exists():
        float_rows = _read_json(FLOAT_ADV).get("by_ticker") or {}
    float_rows = float_rows or {}
    if crowding_rows is None and CROWDING.exists():
        crowding_rows = _read_json(CROWDING).get("by_ticker") or {}
    crowding_rows = crowding_rows or {}

    by_candidate = {str(row["ticker"]).upper(): row for row in candidate_rows}
    if screen is None:
        screen = load_screen()
    screen_by_ticker = {
        str(row.get("ticker")).upper(): {key: value for key, value in row.items() if key not in {"company", "tracked"}}
        for row in (screen or {}).get("rows") or []
        if row.get("ticker")
    }
    position_by_ticker = {
        str(row["ticker"]).upper(): row
        for row in position_rows
        if str(row.get("ticker") or "").upper() not in EXCLUDED_TICKERS
    }
    compiled_positions: list[dict] = []
    compiled_candidates: list[dict] = []
    framework_names: Counter[str] = Counter()
    framework_positions: Counter[str] = Counter()
    complete = 0

    for source in candidate_rows:
        candidate = json.loads(json.dumps(source))
        ticker = str(candidate["ticker"]).upper()
        candidate["ticker"] = ticker
        if furnace_by_ticker is None:
            events = load_furnace_events(ticker)
        else:
            events = furnace_by_ticker.get(ticker) or []
        hits = furnace_hits(events)
        candidate["furnace_hits"] = hits
        candidate["effective_frameworks"] = _effective_frameworks(candidate, hits)
        candidate["artifact_status"] = _artifact_status(candidate)
        borrow = borrow_reading(ticker, borrow_rows, borrow_doc)
        candidate["borrow"] = borrow
        candidate["crowding"] = crowding_reading(ticker, float_rows, crowding_rows)
        candidate["gate_hits"] = _gate_hits(borrow, candidate.get("crowding"), candidate.get("gates") or {})
        candidate["quant"] = screen_by_ticker.get(ticker)
        position = position_by_ticker.get(ticker)
        candidate["has_position"] = position is not None
        if position is not None:
            check_ins = sorted(position.get("check_ins") or [], key=lambda row: str(row.get("date") or ""))
            latest = check_ins[-1]
            opened_price = float(position["position"]["opened_price"])
            split_factor = float(position["position"].get("split_adjustment_factor") or 1)
            merged = json.loads(json.dumps(candidate))
            merged["position"] = json.loads(json.dumps(position["position"]))
            merged["position"]["split_adjusted_open_price"] = round(opened_price / split_factor, 6)
            merged["check_ins"] = check_ins
            merged["outcome"] = {
                "latest_date": latest["date"],
                "latest_price": float(latest["price"]),
                "hypothesis_state": latest.get("hypothesis_state") or "open",
                "check_in_count": len(check_ins),
            }
            merged["borrow"] = borrow
            merged["position_status"] = "closed" if candidate.get("stage") == "closed" else "open"
            if merged["position_status"] == "open" and merged["artifact_status"]["completion_pct"] >= 85:
                complete += 1
            compiled_positions.append(merged)
        scored = set(candidate["effective_frameworks"]) | set(candidate["gate_hits"])
        for framework_id in scored:
            framework_names[framework_id] += 1
            if position is not None:
                framework_positions[framework_id] += 1
        compiled_candidates.append(candidate)

    coverage = {}
    unscored = []
    for row in catalog_doc.get("frameworks") or []:
        framework_id = row["id"]
        names = int(framework_names[framework_id])
        status = "scored" if names else str(row.get("empty_label") or "Unscored")
        coverage[framework_id] = {
            "names": names,
            "positions": int(framework_positions[framework_id]),
            "status": status,
        }
        if names == 0:
            unscored.append(framework_id)

    quant_screen = _screen_payload(screen, set(by_candidate))
    open_positions = [row for row in compiled_positions if row.get("position_status") == "open"]
    statuses = Counter(str((row.get("borrow") or {}).get("status")) for row in compiled_candidates)
    settlements = Counter((row.get("crowding") or {}).get("settlement_ymd") for row in compiled_candidates if row.get("crowding"))
    return {
        "schema_version": "1.2",
        "generated_at": date.today().isoformat(),
        "as_of": candidate_doc.get("as_of") or position_doc.get("as_of"),
        "currency": position_doc.get("currency", "USD"),
        "summary": {
            "position_count": len(open_positions),
            "closed_position_count": len(compiled_positions) - len(open_positions),
            "candidate_count": len(compiled_candidates),
            "lead_count": sum(1 for row in compiled_candidates if row.get("stage") == "lead"),
            "research_complete_count": complete,
            "origin_counts": dict(sorted(Counter(str(row.get("origin") or "") for row in compiled_candidates).items())),
            "category_counts": dict(sorted(Counter(str(row["category"]) for row in compiled_candidates if row.get("category")).items())),
            "framework_counts": {key: coverage[key]["names"] for key in sorted(coverage)},
            "framework_coverage": coverage,
            "unscored_frameworks": unscored,
        },
        "groups": catalog_doc.get("groups") or [],
        "frameworks": catalog_doc.get("frameworks") or [],
        "source_types": catalog_doc.get("source_types") or [],
        "candidates": compiled_candidates,
        "positions": compiled_positions,
        "ideas": compiled_positions,
        "quant_screen": quant_screen,
        "borrow_meta": {
            "source": borrow_doc.get("source") or "",
            "label": next((r.get("source") for r in borrow_rows.values() if isinstance(r, dict) and r.get("source")), ""),
            "as_of": _borrow_file_time(borrow_doc, borrow_rows),
            "quoted": statuses.get("available", 0) + statuses.get("none_available", 0),
            "hard_to_borrow": sum(1 for row in compiled_candidates if "borrow_and_carry" in row.get("gate_hits", [])),
            "not_in_file": statuses.get("not_in_file", 0),
            "pending": statuses.get("pending", 0),
            "htb_fee_pct": HTB_FEE_PCT,
        },
        "crowding_meta": {
            "source": "FINRA short interest via Yahoo (index_float_adv.json); biotech short-interest file as fallback",
            "settlement": settlements.most_common(1)[0][0] if settlements else None,
            "covered": sum(settlements.values()),
            "crowded_days_to_cover": CROWDED_DAYS_TO_COVER,
            "crowded_short_float": CROWDED_SHORT_FLOAT,
        },
        "methodology": {
            "quant": "The quant screen scores SEC fundamentals, the tape, crowding and insider sales against the lens catalog. A score is a reason to open a file, not a thesis.",
            "entry_price": "Opened price is adjusted by the cumulative split factor so it stays comparable to the current share basis.",
            "borrow": "Borrow is IBKR's public short-stock file (fee in % a year, shares available), read on the date shown. A reading is not a locate. A name the file does not list has no IBKR lendable shares or is not a US listing IBKR lends; a name added after the last refresh is pending. Missing is never a zero fee. The borrow gate fires at a fee of 10% or more or with no shares available.",
            "leads": "An activist report attributed to the ticker, an always-review filing event, a Fugazi scorecard row, or the reverse-split engine creates a lead. A lead is not a thesis, never creates a position, and never overwrites a curated row. Uncurated activist and Fugazi leads are rebuilt from discovery on every sync, so a report re-attributed or excluded later drops out.",
            "crowding": "Days to cover and short interest as a share of float are FINRA short-interest readings (via Yahoo, settlement date shown), with the biotech short-interest file as a fallback. They are context, not a reason to short; the squeeze gate fires at 5 or more days to cover or 20% or more of float.",
            "excluded": "ECHX is managed in the ls-algo universe and is omitted from this book. Leads dropped by a human or an audit are listed with their reason in excluded_leads.json and are never re-added.",
            "desk_notes": "A desk_note row is a bot's or an author's idea entry: it names its source, category, dates and tags here, and its narrative lives in the private research vault behind note_ref. The category adds lenses; it never adds the fraud tag.",
            "reverse_splits": "A reverse_split_research row is a discovery lead from the reverse-split engine with its six dated lens reviews carried as lens_reviews. Impairment is not reviewed until a lens review says so.",
            "buyback_issuance": "Names whose share count rose over the last year after a multi-year shrink. Candidate signals for the dilution / financing lens. Not ranked shorts.",
        },
        "buyback_issuance_signals": _buyback_issuance_signals(),
        "category_lenses": CATEGORY_LENSES,
    }


def _buyback_issuance_signals() -> list[dict]:
    """issuing_again names from the buyback companies file. Empty when that file is absent."""
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from build_buyback_radar import issuance_signals, load_companies_index
    except Exception:
        return []
    return issuance_signals(list(load_companies_index().values()))


def sync_leads() -> list[str]:
    doc = _read_json(CANDIDATES)
    incoming = discover_leads()
    excluded = load_excluded_leads()
    rows, refreshed, dropped = refresh_auto_leads(list(doc.get("candidates") or []), incoming, excluded)
    merged, added = upsert_leads(rows, incoming, excluded)
    if added or refreshed or dropped:
        doc["candidates"] = merged
        doc["as_of"] = date.today().isoformat()
        _write_json(CANDIDATES, doc)
    if refreshed or dropped:
        print(f"Refreshed {len(refreshed)} auto leads, dropped {len(dropped)}: {', '.join(dropped) or '-'}")
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate and print summary without writing")
    parser.add_argument("--init-candidates", action="store_true", help="Split ideas.json into candidates once")
    parser.add_argument("--skip-scan", action="store_true", help="Do not write the activist scan markdown")
    args = parser.parse_args()
    if args.init_candidates:
        init_candidates()
        print(f"Wrote {CANDIDATES.relative_to(ROOT)}")
    if not args.check:
        added = sync_leads()
        if added:
            print(f"Added {len(added)} short leads")
        if not args.skip_scan:
            _scan().write_scan()
    payload = build()
    if args.check:
        print(json.dumps(payload["summary"], indent=2))
        return
    _write_json(OUTPUT, payload)
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({payload['summary']['position_count']} positions, {payload['summary']['candidate_count']} names)"
    )


if __name__ == "__main__":
    main()
