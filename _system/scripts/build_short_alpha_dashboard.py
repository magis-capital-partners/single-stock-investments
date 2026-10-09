#!/usr/bin/env python3
"""Compile the Short Alpha ledger: frameworks, names that fit, and the open book.

Positions stay in ideas.json and must point at a candidate. Activist-index
hits and always-review filing events become leads. A new lead never overwrites
a rejected, live, closed, or researching row.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "research" / "short-alpha"
POSITIONS = LEDGER / "ideas.json"
CANDIDATES = LEDGER / "candidates.json"
CATALOG = LEDGER / "frameworks.json"
QUEUE = ROOT / "_system" / "data" / "short_alpha_research_queue.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_alpha.json"
BORROW = ROOT / "dashboard" / "data" / "short_alpha_borrow.json"
CROWDING = ROOT / "_system" / "reference" / "market-data" / "ownership" / "biotech_short_interest.json"
SCREEN = ROOT / "dashboard" / "data" / "short_quant_screen.json"
SCREEN_ROWS = 25
FUGAZI = ROOT / "_system" / "reference" / "activist-reports" / "short_scorecard" / "Fugazi_Research.csv"
EXCLUDED_TICKERS = {"ECHX"}  # Managed in the ls-algo universe, not this book.
REVIEWED_ON = "2026-10-07"
LIVE_STAGES = {"live", "closed", "researching", "ic"}
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
}


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


def upsert_leads(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], list[str]]:
    """Append tickers that are not already tracked. Never replace an existing row."""
    seen = {str(row.get("ticker") or "").upper() for row in existing}
    added_rows: list[dict] = []
    added_ids: list[str] = []
    for row in incoming:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in seen or ticker in EXCLUDED_TICKERS:
            continue
        copy = json.loads(json.dumps(row))
        copy["ticker"] = ticker
        added_rows.append(copy)
        added_ids.append(ticker)
        seen.add(ticker)
    return existing + added_rows, added_ids


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


def lead_from_reports(ticker: str, company: str, reports: list[dict]) -> dict:
    sources: list[dict] = []
    ordered = sorted(reports, key=lambda row: str(row.get("report_date") or ""), reverse=True)
    for report in ordered:
        bits = [str(report.get("firm_name") or report.get("firm_id") or "Short report")]
        if report.get("report_date"):
            bits.append(str(report["report_date"]))
        title = str(report.get("title") or "")
        if title and title not in bits:
            bits.append(title)
        source = {
            "type": "activist_short_report",
            "label": " · ".join(bits),
            "firm_id": report.get("firm_id") or "",
            "report_date": report.get("report_date") or "",
        }
        if report.get("source_url"):
            source["url"] = report["source_url"]
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


def leads_from_fugazi_rows(rows: list[dict]) -> list[dict]:
    """One lead per ticker. A publisher scorecard is a lead, not a thesis."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    leads: list[dict] = []
    for ticker, reports in sorted(grouped.items()):
        reports.sort(key=lambda item: str(item.get("report_date") or ""))
        company = str(reports[-1].get("target") or ticker)
        sources = []
        for report in reversed(reports):
            quote = str(report.get("quote_symbol") or "").upper()
            label = f"Fugazi Research · {report.get('report_date') or 'undated'}"
            if quote and quote != ticker:
                label += f" · quotes as {quote}"
            source = {"type": "activist_short_report", "label": label, "firm_id": "fugazi"}
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


def discover_leads() -> list[dict]:
    scan = _scan()
    names = scan.company_names()
    incoming: list[dict] = []
    for ticker, reports in sorted(scan.collect_feed_shorts().items()):
        incoming.append(lead_from_reports(ticker, names.get(ticker, ticker), reports))
    for ticker in sorted(names):
        if ticker in EXCLUDED_TICKERS:
            continue
        lead = lead_from_furnace(ticker, names.get(ticker, ticker), load_furnace_events(ticker))
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
            "Reviewed 2026-10-07. Borrow is still pending: no IBKR export was loaded, "
            "and this refresh does not contact the Gateway. The price baseline remains "
            "the 2026-08-04 check-in."
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
    if QUEUE.exists():
        queue = _read_json(QUEUE)
        notes = list(queue.get("notes") or [])
        review = (
            "2026-10-07: open book reviewed against local research files. "
            "Price check-ins stay on the 2026-08-04 baseline because no fresh quote file was loaded. "
            "Borrow stays pending: no IBKR CSV, and this refresh does not contact the Gateway."
        )
        if review not in notes:
            notes.append(review)
        queue["reviewed_on"] = REVIEWED_ON
        queue["notes"] = notes
        _write_json(QUEUE, queue)


def _framework_ids(catalog: dict) -> list[str]:
    return [str(row.get("id") or "") for row in catalog.get("frameworks") or []]


def _validate_catalog(catalog: dict) -> None:
    ids = _framework_ids(catalog)
    if not ids or len(ids) != len(set(ids)):
        raise LedgerError("Framework ids must be present and unique")
    parents = {row.get("id") for row in catalog.get("frameworks") or []}
    for row in catalog.get("frameworks") or []:
        parent = row.get("parent")
        if parent and parent not in parents:
            raise LedgerError(f"{row.get('id')}: unknown parent {parent}")
    source_ids = [str(row.get("id") or "") for row in catalog.get("source_types") or []]
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise LedgerError("Source-type ids must be present and unique")


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


def _artifact_status(candidate: dict) -> dict:
    ticker = str(candidate["ticker"])
    research_dir = ROOT / ticker / "research"
    deep_dives = sorted(research_dir.glob("deep_dive_*.md")) if research_dir.is_dir() else []
    source_refs = [row.get("ref") for row in candidate.get("sources") or [] if row.get("ref")]
    missing_refs = [str(ref) for ref in source_refs if not (ROOT / str(ref)).exists()]
    research = candidate.get("research") or {}
    valuation = research_dir / "valuation.json"
    workbench = research_dir / "valuation_workbench.json"
    dossier = research_dir / "dossier.json"
    score = 0
    score += 25 if deep_dives else 0
    score += 20 if valuation.exists() else 0
    score += 15 if workbench.exists() else 0
    score += 15 if dossier.exists() else 0
    score += 15 if len(source_refs) >= 3 and not missing_refs else 0
    score += 10 if str(research.get("ic") or "").lower() in {"ready", "complete", "approved"} else 0
    return {
        "ticker_folder": (ROOT / ticker).is_dir(),
        "deep_dive_count": len(deep_dives),
        "latest_deep_dive": deep_dives[-1].relative_to(ROOT).as_posix() if deep_dives else None,
        "valuation_present": valuation.exists(),
        "workbench_present": workbench.exists(),
        "dossier_present": dossier.exists(),
        "missing_source_refs": missing_refs,
        "completion_pct": score,
    }


def _gate_hits(borrow: dict, crowding: dict | None, gates: dict) -> list[str]:
    hits: list[str] = []
    if borrow.get("status") == "available" and borrow.get("rate_pct") is not None:
        hits.append("borrow_and_carry")
    if crowding and crowding.get("days_to_cover") is not None:
        hits.append("crowding_squeeze")
    if str((gates or {}).get("path_and_timing") or "unscored") not in {"", "unscored"}:
        hits.append("path_and_timing")
    if str((gates or {}).get("issuer_retaliation") or "unscored") not in {"", "unscored"}:
        hits.append("issuer_retaliation")
    return hits


def _effective_frameworks(candidate: dict, hits: list[dict]) -> list[str]:
    ordered: list[str] = []
    for tag in list(candidate.get("frameworks") or []):
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
) -> dict:
    position_doc = _read_json(POSITIONS) if positions is None else {"ideas": positions}
    candidate_doc = _read_json(CANDIDATES) if candidates is None else {"candidates": candidates, "as_of": REVIEWED_ON}
    catalog_doc = _read_json(CATALOG) if catalog is None else catalog
    position_rows = list(position_doc.get("ideas") or [])
    candidate_rows = list(candidate_doc.get("candidates") or [])
    _validate_bundle(position_rows, candidate_rows, catalog_doc)

    if borrow_rows is None:
        borrow_rows = _read_json(BORROW).get("rates") or {} if BORROW.exists() else {}
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
        borrow = borrow_rows.get(ticker) or {
            "status": "pending",
            "source": "IBKR borrow feed",
            "message": "Awaiting the next IBKR borrow refresh.",
        }
        candidate["borrow"] = borrow
        crowding = crowding_rows.get(ticker)
        if isinstance(crowding, dict) and crowding.get("days_to_cover") is not None:
            candidate["crowding"] = {
                "days_to_cover": crowding.get("days_to_cover"),
                "settlement_ymd": crowding.get("settlement_ymd"),
                "source": "finra_biweekly",
                "tier": "context",
            }
        else:
            candidate["crowding"] = None
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
            if merged["artifact_status"]["completion_pct"] >= 85:
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
    return {
        "schema_version": "1.2",
        "generated_at": date.today().isoformat(),
        "as_of": candidate_doc.get("as_of") or position_doc.get("as_of"),
        "currency": position_doc.get("currency", "USD"),
        "summary": {
            "position_count": len(compiled_positions),
            "candidate_count": len(compiled_candidates),
            "lead_count": sum(1 for row in compiled_candidates if row.get("stage") == "lead"),
            "research_complete_count": complete,
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
        "methodology": {
            "quant": "The quant screen scores SEC fundamentals, the tape, crowding and insider sales against the lens catalog. A score is a reason to open a file, not a thesis.",
            "entry_price": "Opened price is adjusted by the cumulative split factor so it stays comparable to the current share basis.",
            "borrow": "Borrow is supplied by the IBKR refresh feed. Unavailable is not a zero rate.",
            "leads": "An activist-index hit, an always-review filing event, or a Fugazi scorecard row creates a lead. It does not create a position and does not overwrite a rejected, live, closed, or researching row.",
            "crowding": "Days to cover is FINRA context from the biotech short-interest file when that symbol is present. It is not a reason to short.",
            "excluded": "ECHX is managed in the ls-algo universe and is omitted from this book.",
        },
    }


def sync_leads() -> list[str]:
    doc = _read_json(CANDIDATES)
    merged, added = upsert_leads(list(doc.get("candidates") or []), discover_leads())
    if added:
        doc["candidates"] = merged
        doc["as_of"] = date.today().isoformat()
        _write_json(CANDIDATES, doc)
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
