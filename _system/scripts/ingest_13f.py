#!/usr/bin/env python3
"""Download 13F books for registry managers and write positions, changes, and dashboard files.

Overlap-only advisers stay in the filtered overlap file. This command writes full
books for tracked, biotech, and active managers. A watchlist manager reports every
new position, every exit, and share adds or trims at or above the watchlist
threshold. Other managers keep SSI-book changes, plus any new position.
Holdings are context only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from cvr_common import post_slack  # noqa: E402
from ownership_common import (  # noqa: E402
    cik_padded,
    filing_document_urls,
    latest_13f_filings,
    list_13f_filings,
    load_cusip_map,
    portfolio_universe,
    sec_fetch_bytes,
)
from thirteenf_core import (  # noqa: E402
    HOLDINGS_FORMS,
    aggregate_positions,
    annotate_weights,
    book_source_for_latest_period,
    diff_positions,
    normalize_date,
    other_managers_from_primary,
    quarter_from_period,
)
from thirteenf_period import build_period, periods_for_fund  # noqa: E402
from build_managers_json import distinctive_tokens  # noqa: E402

OWNERSHIP = ROOT / "_system" / "reference" / "market-data" / "ownership"
MANAGERS_PATH = OWNERSHIP / "managers.json"
POSITIONS = OWNERSHIP / "13f" / "positions"
CHANGES = OWNERSHIP / "13f" / "changes"
FILINGS_PATH = OWNERSHIP / "13f" / "filings.jsonl"
CACHE = OWNERSHIP / "cache" / "13f"
SUMMARY_PATH = ROOT / "dashboard" / "data" / "fund_holdings_summary.json"
BY_TICKER = ROOT / "dashboard" / "data" / "holdings" / "by_ticker"
BY_MANAGER = ROOT / "dashboard" / "data" / "holdings" / "by_manager"
MANAGERS_INDEX_PATH = ROOT / "dashboard" / "data" / "holdings" / "managers_index.json"
FEED_PATH = ROOT / "dashboard" / "data" / "holdings" / "feed.json"
CONTEXT = (
    "13F filings are long US-listed positions only, and they arrive about 45 days after quarter end. "
    "They are context. They are not an input to the base return."
)
DEFAULT_WATCHLIST_THRESHOLD_PCT = 5.0
CSV_FIELDS = [
    "manager_id",
    "quarter",
    "period_end",
    "filed_at",
    "accession",
    "cusip",
    "issuer",
    "title_of_class",
    "sh_prn",
    "put_call",
    "shares",
    "value_usd",
    "weight_pct",
    "rank",
    "ticker",
    "ssi_ticker",
    "discretion",
    "source_url",
    "in_base_irr",
]


def load_registry() -> dict:
    return json.loads(MANAGERS_PATH.read_text(encoding="utf-8"))


def load_managers() -> list[dict]:
    document = load_registry()
    return [row for row in document.get("managers") or [] if row.get("book") == "full" and row.get("cik")]


def watchlist_threshold_pct(document: dict | None, override: float | None = None) -> float:
    """Share-change percent that a watchlist add or trim must reach."""
    if override is not None:
        return float(override)
    raw = (document or {}).get("watchlist_share_change_pct")
    if raw is None or raw == "":
        return DEFAULT_WATCHLIST_THRESHOLD_PCT
    return float(raw)


def is_watchlist(manager: dict) -> bool:
    return "watchlist" in (manager.get("roles") or [])


def reported_changes(
    manager: dict,
    changes: list[dict],
    universe: set[str],
    threshold_pct: float,
) -> list[dict]:
    """Changes worth writing.

    A watchlist manager reports the whole book: every new position, every exit,
    and adds or trims at or above the threshold. Any other manager keeps the
    SSI book, plus a new position even when that ticker is outside the book.
    """
    if not is_watchlist(manager):
        return [
            change
            for change in changes
            if (change.get("ssi_ticker") or "").upper() in universe or change.get("change_type") == "new"
        ]
    kept = []
    for change in changes:
        kind = change.get("change_type")
        if kind in {"new", "exit"}:
            kept.append(change)
            continue
        if kind not in {"add", "trim"}:
            continue
        pct = change.get("shares_delta_pct")
        if pct is None or abs(float(pct)) >= float(threshold_pct):
            kept.append(change)
    return kept


def select_successor_filings(filings: list[dict], current_cik: str, history: list[dict] | None) -> list[dict]:
    """Keep one filer per quarter when the book moves to a new CIK.

    A prior CIK keeps every quarter it still filed as a holdings report on or
    before its through date. The current CIK supplies later quarters, including
    a quarter the prior CIK filed only as a notice.
    """
    current = cik_padded(current_cik)
    through_by_cik: dict[str, str] = {}
    for item in history or []:
        cik = cik_padded(item.get("cik") or "")
        if cik and cik != current:
            through_by_cik[cik] = (item.get("through") or "")[:10]

    def allowed(filing: dict) -> bool:
        cik = cik_padded(filing.get("cik") or "")
        if not cik or cik == current:
            return True
        if cik not in through_by_cik:
            return False
        through = through_by_cik[cik]
        filed = (filing.get("filing_date") or "")[:10]
        return not through or not filed or filed <= through

    allowed_rows = [row for row in filings if allowed(row)]
    claimed: set[str] = set()
    for filing in allowed_rows:
        cik = cik_padded(filing.get("cik") or "")
        if cik not in through_by_cik or filing.get("form") not in HOLDINGS_FORMS:
            continue
        period = normalize_date(filing.get("report_date")) or ""
        if period:
            claimed.add(period)
    kept = []
    for filing in allowed_rows:
        cik = cik_padded(filing.get("cik") or "")
        period = normalize_date(filing.get("report_date")) or ""
        if period in claimed and cik == current:
            continue
        kept.append(filing)
    return kept


def filings_for_manager(manager: dict, limit: int) -> list[dict]:
    """Current CIK plus prior CIKs, tagged so a successor quarter is not mixed."""
    current = cik_padded(manager.get("cik") or "")
    rows: list[dict] = []
    if current:
        for filing in list_13f_filings(current, limit=limit):
            copied = dict(filing)
            copied["cik"] = current
            rows.append(copied)
    for item in manager.get("cik_history") or []:
        cik = cik_padded(item.get("cik") or "")
        if not cik or cik == current:
            continue
        through = (item.get("through") or "")[:10]
        for filing in list_13f_filings(cik, limit=limit):
            filed = (filing.get("filing_date") or "")[:10]
            if through and filed and filed > through:
                continue
            copied = dict(filing)
            copied["cik"] = cik
            rows.append(copied)
    rows.sort(key=lambda filing: (filing.get("filing_date") or "", filing.get("accession") or ""), reverse=True)
    deduped = []
    seen: set[str] = set()
    for row in rows:
        accession = row.get("accession") or ""
        if not accession or accession in seen:
            continue
        seen.add(accession)
        deduped.append(row)
    return deduped


def registry_ciks_for(managers: list[dict]) -> set[str]:
    found: set[str] = set()
    for row in managers:
        if row.get("cik"):
            found.add(cik_padded(row["cik"]))
        for item in row.get("cik_history") or []:
            if item.get("cik"):
                found.add(cik_padded(item["cik"]))
    return found


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def position_rows(manager: dict, built: dict, cusip_map: dict[str, str], names: dict[str, str]) -> list[dict]:
    from thirteenf_core import bridge_local_listing

    weighted = annotate_weights(built.get("rows") or [])
    out = []
    for row in weighted:
        cusip = (row.get("cusip") or "").upper()
        ticker = cusip_map.get(cusip) or ""
        bridged = bridge_local_listing(row.get("issuer") or "", ticker or None, names)
        ssi_value = bridged if bridged and bridged in names else ""
        out.append(
            {
                "manager_id": manager["manager_id"],
                "quarter": built.get("quarter") or "",
                "period_end": built.get("period_end") or "",
                "filed_at": built.get("filing_date") or "",
                "accession": built.get("accession") or "",
                "cusip": cusip,
                "issuer": row.get("issuer") or "",
                "title_of_class": row.get("title_of_class") or "",
                "sh_prn": row.get("sh_prn") or "SH",
                "put_call": row.get("put_call") or "",
                "shares": "" if row.get("shares") is None else int(row["shares"]),
                "value_usd": "" if row.get("value_usd") is None else int(row["value_usd"]),
                "weight_pct": "" if row.get("weight_pct") is None else row.get("weight_pct"),
                "rank": "" if row.get("rank") is None else row.get("rank"),
                "ticker": ticker,
                "ssi_ticker": ssi_value,
                "discretion": row.get("discretion") or "",
                "source_url": built.get("source_url") or "",
                "in_base_irr": False,
            }
        )
    return out


def write_positions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["shares"] = int(row["shares"]) if row.get("shares") else None
        row["value_usd"] = int(row["value_usd"]) if row.get("value_usd") else None
        row["weight_pct"] = float(row["weight_pct"]) if row.get("weight_pct") else None
        row["rank"] = int(row["rank"]) if row.get("rank") else None
        row["put_call"] = row.get("put_call") or None
    return rows


def filing_record(manager: dict, built: dict) -> dict:
    report = built.get("reconciliation") or {}
    return {
        "manager_id": manager["manager_id"],
        "cik": built.get("cik") or manager.get("cik"),
        "accession": built.get("accession"),
        "member_accessions": built.get("member_accessions") or [],
        "form": (built.get("forms") or ["13F-HR"])[-1],
        "period_end": built.get("period_end"),
        "quarter": built.get("quarter"),
        "filed_at": built.get("filing_date"),
        "source_url": built.get("source_url"),
        "confidential_omitted": bool(built.get("confidential_omitted")),
        "reconciliation_ok": bool(report.get("ok", True)),
        "may_be_incomplete": bool(report.get("may_be_incomplete")),
        "in_base_irr": False,
    }


def saved_signature(manager_id: str, quarter: str) -> str | None:
    if not FILINGS_PATH.exists():
        return None
    found = None
    for line in FILINGS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("manager_id") == manager_id and row.get("quarter") == quarter:
            found = row
    if not found:
        return None
    members = found.get("member_accessions") or []
    return "|".join([found.get("accession") or "", *members])


def upsert_filings(records: list[dict]) -> None:
    FILINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if FILINGS_PATH.exists():
        for line in FILINGS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    keys = {(row["manager_id"], row.get("quarter")) for row in records}
    kept = [row for row in existing if (row.get("manager_id"), row.get("quarter")) not in keys]
    kept.extend(records)
    kept.sort(key=lambda row: (row.get("period_end") or "", row.get("manager_id") or ""))
    FILINGS_PATH.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in kept), encoding="utf-8")


def _signature(built: dict) -> str:
    return "|".join([built.get("accession") or "", *(built.get("member_accessions") or [])])


def notice_member_shares_name(parent_names: str, member_name: str) -> bool:
    """A notice may point at another filer. Copy that book only when the names agree.

    MIG Capital's notice names Exchange Traded Concepts. Those are different firms.
    Robotti's notice names Robert Robotti. That is the same manager.
    """
    tokens = distinctive_tokens(parent_names)
    if not tokens or not (member_name or "").strip():
        return False
    compact = re.sub(r"[^a-z0-9]", "", member_name.lower())
    return any(token in compact for token in tokens)


def notice_book(manager: dict, notice: dict, period: str, registry_ciks: set[str], offline: bool) -> dict | None:
    if offline:
        return None
    urls = filing_document_urls(notice)
    if not urls.get("primary"):
        return None
    managers = other_managers_from_primary(sec_fetch_bytes(urls["primary"]))
    parts = []
    members = []
    parent_names = " ".join(part for part in (manager.get("display_name"), manager.get("sec_name")) if part)
    for member in managers:
        if cik_padded(member["cik"]) in registry_ciks and cik_padded(member["cik"]) != cik_padded(manager.get("cik") or ""):
            continue
        if not notice_member_shares_name(parent_names, member.get("name") or ""):
            continue
        filings = [
            row for row in latest_13f_filings(member["cik"], limit=8)
            if row.get("report_date") == period and row.get("form") in {"13F-HR", "13F-HR/A"}
        ]
        decision = book_source_for_latest_period(filings)
        if decision.get("mode") != "direct":
            continue
        built = build_period(
            decision["filings"],
            fund_id=f"{manager['manager_id']}_{member['cik']}",
            cache_dir=CACHE,
            offline=False,
        )
        if built is None:
            continue
        parts.append(built)
        members.append(built.get("accession") or "")
    if not parts:
        return None
    rows = aggregate_positions([row for part in parts for row in (part.get("rows") or [])])
    ok = all((part.get("reconciliation") or {}).get("ok") for part in parts)
    return {
        "period_end": period,
        "quarter": quarter_from_period(period) or "unknown",
        "filing_date": notice.get("filing_date"),
        "accession": notice.get("accession"),
        "member_accessions": [item for item in members if item],
        "source_url": urls.get("primary"),
        "rows": rows,
        "reconciliation": {"ok": ok, "may_be_incomplete": any(part.get("confidential_omitted") for part in parts)},
        "confidential_omitted": any(part.get("confidential_omitted") for part in parts),
        "forms": ["13F-NT"],
    }


def books_for_manager(manager: dict, periods: int, registry_ciks: set[str], offline: bool) -> list[dict]:
    if offline:
        return []
    filings = filings_for_manager(manager, max(16, periods * 4))
    filings = select_successor_filings(filings, manager.get("cik") or "", manager.get("cik_history") or [])
    direct = []
    for group in periods_for_fund(filings, periods):
        built = build_period(group, fund_id=manager["manager_id"], cache_dir=CACHE, offline=False)
        if built:
            built["cik"] = cik_padded(group[-1].get("cik") or manager.get("cik") or "")
            direct.append(built)
    decision = book_source_for_latest_period(filings)
    if decision.get("mode") == "notice":
        period = decision.get("period")
        if period and period not in {item.get("period_end") for item in direct}:
            extra = notice_book(manager, decision["notice"], period, registry_ciks, offline=False)
            if extra:
                direct.append(extra)
    direct.sort(key=lambda item: item.get("period_end") or "")
    return direct[-periods:]


def alert_lines(changes: list[dict], universe: set[str], *, today: str, window_days: int = 10) -> list[str]:
    """SSI ticker changes worth a Slack line. Older filings stay in the change file."""
    cutoff = datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=window_days)
    lines = []
    for change in changes:
        ticker = (change.get("ssi_ticker") or change.get("ticker") or "").upper()
        if ticker not in universe:
            continue
        kind = change.get("change_type")
        pct = change.get("shares_delta_pct")
        material = kind in {"new", "exit"} or (pct is not None and abs(float(pct)) >= 25)
        filed = (change.get("filed_at") or "")[:10]
        if not material or not filed:
            continue
        try:
            filed_on = datetime.strptime(filed, "%Y-%m-%d").date()
        except ValueError:
            continue
        if filed_on < cutoff:
            continue
        if kind == "new":
            verb = "new"
        elif kind == "exit":
            verb = "exit"
        else:
            verb = f"{float(pct):+.1f}%"
        lines.append(f"{change.get('manager_name') or change.get('manager_id')}: {verb} {ticker}")
    return lines


def _prior_quarter_path(manager_id: str, quarter: str) -> Path | None:
    folder = POSITIONS
    if not folder.exists():
        return None
    quarters = sorted(path.name for path in folder.iterdir() if path.is_dir() and (path / f"{manager_id}.csv").exists())
    earlier = [name for name in quarters if name < quarter]
    if not earlier:
        return None
    return folder / earlier[-1] / f"{manager_id}.csv"


def diff_book(manager: dict, rows: list[dict], quarter: str, period_end: str) -> list[dict]:
    prior_path = _prior_quarter_path(manager["manager_id"], quarter)
    if prior_path is None:
        return []
    prior_rows = read_positions(prior_path)
    prior_period = prior_rows[0].get("period_end") if prior_rows else None
    changes = diff_positions(rows, prior_rows, manager_id=manager["manager_id"], period=period_end, prior_period=prior_period)
    filed = rows[0].get("filed_at") if rows else ""
    kept = []
    for change in changes:
        if change.get("change_type") == "unchanged":
            continue
        change["manager_name"] = manager.get("display_name") or manager["manager_id"]
        change["quarter"] = quarter
        change["filed_at"] = filed
        change["in_base_irr"] = False
        kept.append(change)
    return kept


def write_changes(
    quarter: str,
    period_end: str,
    manager_changes: dict[str, list[dict]],
    threshold_pct: float | None = None,
) -> None:
    path = CHANGES / f"{quarter}.json"
    current = {"changes": []}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {"changes": []}
    kept = [row for row in current.get("changes") or [] if row.get("manager_id") not in manager_changes]
    for rows in manager_changes.values():
        kept.extend(rows)
    payload = {
        "schema_version": 1,
        "in_base_irr": False,
        "quarter": quarter,
        "period_end": period_end,
        "generated_at": _iso_now(),
        "context": CONTEXT,
        "changes": kept,
    }
    if threshold_pct is not None:
        payload["watchlist_share_change_pct"] = threshold_pct
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def build_dashboard(names: dict[str, str], threshold_pct: float | None = None) -> None:
    """Latest book per manager, joined to SSI tickers."""
    if not POSITIONS.exists():
        return
    latest: dict[str, tuple[str, list[dict]]] = {}
    for quarter_dir in sorted(path for path in POSITIONS.iterdir() if path.is_dir()):
        for csv_path in quarter_dir.glob("*.csv"):
            rows = read_positions(csv_path)
            if rows:
                latest[csv_path.stem] = (quarter_dir.name, rows)
    changes_by_key: dict[tuple[str, str, str], dict] = {}
    reported_by_manager: dict[tuple[str, str], list[dict]] = {}
    if CHANGES.exists():
        for path in sorted(CHANGES.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for change in payload.get("changes") or []:
                ticker = (change.get("ssi_ticker") or change.get("ticker") or "").upper()
                owner = change.get("manager_id") or ""
                quarter_key = change.get("quarter") or ""
                if ticker:
                    changes_by_key[(owner, ticker, quarter_key)] = change
                if owner and quarter_key:
                    reported_by_manager.setdefault((owner, quarter_key), []).append(change)
    managers = {
        row["manager_id"]: row
        for row in json.loads(MANAGERS_PATH.read_text(encoding="utf-8")).get("managers") or []
    }
    by_ticker: dict[str, list[dict]] = {}
    for manager_id, (_quarter, rows) in latest.items():
        manager = managers.get(manager_id) or {"display_name": manager_id}
        equity = [row for row in rows if not row.get("put_call") and (row.get("sh_prn") or "SH") == "SH"]
        for row in equity:
            ticker = (row.get("ssi_ticker") or "").upper()
            if ticker not in names:
                continue
            change = changes_by_key.get((manager_id, ticker, _quarter)) or {}
            by_ticker.setdefault(ticker, []).append(
                {
                    "manager_id": manager_id,
                    "name": manager.get("display_name") or manager_id,
                    "shares": row.get("shares"),
                    "value_usd": row.get("value_usd"),
                    "weight_pct": row.get("weight_pct"),
                    "rank": row.get("rank"),
                    "change_type": change.get("change_type"),
                    "shares_delta_pct": change.get("shares_delta_pct"),
                    "period_end": row.get("period_end"),
                    "filed_at": row.get("filed_at"),
                    "source_url": row.get("source_url") or None,
                    "in_base_irr": False,
                }
            )
    summary = {}
    if BY_TICKER.exists():
        for stale in BY_TICKER.glob("*.json"):
            stale.unlink()
    BY_TICKER.mkdir(parents=True, exist_ok=True)
    for ticker, holders in sorted(by_ticker.items()):
        holders.sort(key=lambda row: -(row.get("value_usd") or 0))
        counted = {}
        for row in holders:
            counted[row.get("period_end") or ""] = counted.get(row.get("period_end") or "", 0) + 1
        period = sorted(counted, key=lambda key: (counted[key], key), reverse=True)[0]
        deltas = [row.get("shares_delta_pct") for row in holders if row.get("change_type") in {"new", "add", "trim", "exit"}]
        net = "flat"
        if any(row.get("change_type") in {"new", "add"} for row in holders) and not any(
            row.get("change_type") in {"trim", "exit"} for row in holders
        ):
            net = "add"
        elif any(row.get("change_type") in {"trim", "exit"} for row in holders) and not any(
            row.get("change_type") in {"new", "add"} for row in holders
        ):
            net = "trim"
        elif deltas:
            score = 0
            for row in holders:
                kind = row.get("change_type")
                if kind in {"new", "add"}:
                    score += 1
                elif kind in {"trim", "exit"}:
                    score -= 1
            net = "add" if score > 0 else "trim" if score < 0 else "flat"
        summary[ticker] = {"holder_count": len(holders), "net": net, "period_end": period}
        payload = {
            "schema_version": 1,
            "in_base_irr": False,
            "ticker": ticker,
            "period_end": period,
            "context": CONTEXT,
            "holders": holders,
        }
        (BY_TICKER / f"{ticker}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "in_base_irr": False,
                "generated_at": _iso_now(),
                "context": CONTEXT,
                "tickers": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_manager_views(latest, managers, names, changes_by_key, reported_by_manager, threshold_pct)


def _change_view(change: dict) -> dict:
    return {
        "ticker": (change.get("ssi_ticker") or change.get("ticker") or ""),
        "issuer": change.get("issuer") or "",
        "cusip": change.get("cusip") or "",
        "change_type": change.get("change_type"),
        "shares_delta_pct": change.get("shares_delta_pct"),
    }


def _write_manager_views(
    latest: dict,
    managers: dict,
    names: dict[str, str],
    changes_by_key: dict,
    reported_by_manager: dict,
    threshold_pct: float | None = None,
) -> None:
    """Manager pages, a changes feed, and ideas that are not in the SSI book."""
    if BY_MANAGER.exists():
        for stale in BY_MANAGER.glob("*.json"):
            stale.unlink()
    BY_MANAGER.mkdir(parents=True, exist_ok=True)
    quarter_counts: dict[str, int] = {}
    for quarter, _rows in latest.values():
        quarter_counts[quarter] = quarter_counts.get(quarter, 0) + 1
    feed_quarter = sorted(quarter_counts, key=lambda key: (quarter_counts[key], key), reverse=True)[0] if quarter_counts else ""
    index = []
    outside: dict[str, dict] = {}
    consensus: dict[str, list[str]] = {}
    feed_changes = []
    watchlist_feed = []
    for manager_id, (quarter, rows) in sorted(latest.items()):
        manager = managers.get(manager_id) or {"display_name": manager_id}
        name = manager.get("display_name") or manager_id
        watchlist = is_watchlist(manager)
        equity = [row for row in rows if not row.get("put_call") and (row.get("sh_prn") or "SH") == "SH"]
        equity.sort(key=lambda row: -(row.get("value_usd") or 0))
        ssi_rows = [row for row in equity if (row.get("ssi_ticker") or "").upper() in names]
        top = equity[0] if equity else {}
        index.append(
            {
                "manager_id": manager_id,
                "name": name,
                "quarter": quarter,
                "period_end": (equity[0].get("period_end") if equity else "") or "",
                "positions": len(equity),
                "ssi_overlap": len(ssi_rows),
                "top_issuer": top.get("issuer") or "",
                "top_ticker": top.get("ticker") or "",
                "top_weight_pct": top.get("weight_pct"),
                "watchlist": watchlist,
            }
        )
        all_changes = []
        for (owner, ticker, quarter_key), change in changes_by_key.items():
            if owner != manager_id or quarter_key != quarter or not ticker:
                continue
            all_changes.append(
                {
                    "ticker": ticker,
                    "change_type": change.get("change_type"),
                    "shares_delta_pct": change.get("shares_delta_pct"),
                    "issuer": change.get("issuer") or "",
                }
            )
        own_changes = [change for change in all_changes if change["ticker"] in names]
        reported = [_change_view(change) for change in reported_by_manager.get((manager_id, quarter), [])]
        page = {
            "schema_version": 1,
            "in_base_irr": False,
            "manager_id": manager_id,
            "name": name,
            "cik": manager.get("cik"),
            "quarter": quarter,
            "context": CONTEXT,
            "watchlist": watchlist,
            "positions": [
                {
                    "issuer": row.get("issuer") or "",
                    "ticker": row.get("ticker") or "",
                    "ssi_ticker": row.get("ssi_ticker") or "",
                    "shares": row.get("shares"),
                    "value_usd": row.get("value_usd"),
                    "weight_pct": row.get("weight_pct"),
                    "rank": row.get("rank"),
                }
                for row in equity[:20]
            ],
            "ssi_changes": own_changes[:40],
        }
        if watchlist:
            page["changes"] = reported
        (BY_MANAGER / f"{manager_id}.json").write_text(json.dumps(page) + "\n", encoding="utf-8")
        if quarter != feed_quarter:
            continue
        for change in own_changes:
            feed_changes.append({"manager_id": manager_id, "name": name, **change})
            if change.get("change_type") in {"new", "add"}:
                consensus.setdefault(change["ticker"], []).append(name)
        if watchlist:
            for change in reported:
                watchlist_feed.append({"manager_id": manager_id, "name": name, **change})
        new_outside = {change["ticker"] for change in all_changes if change.get("change_type") == "new" and change["ticker"] not in names}
        for row in equity:
            ticker = (row.get("ticker") or "").upper()
            ssi = (row.get("ssi_ticker") or "").upper()
            weight = row.get("weight_pct") or 0
            if not ticker or ticker not in new_outside or ssi in names or weight < 3:
                continue
            bucket = outside.setdefault(ticker, {"issuer": row.get("issuer") or "", "managers": []})
            bucket["managers"].append({"manager_id": manager_id, "name": name, "weight_pct": weight})
    ideas = [
        {"ticker": ticker, **payload}
        for ticker, payload in sorted(outside.items())
        if len(payload["managers"]) >= 2
    ]
    agreed = [
        {"ticker": ticker, "managers": names_list}
        for ticker, names_list in sorted(consensus.items())
        if len(names_list) >= 3
    ]
    feed_changes.sort(key=lambda row: (row.get("ticker") or "", row.get("name") or ""))
    watchlist_feed.sort(key=lambda row: (row.get("name") or "", row.get("ticker") or "", row.get("change_type") or ""))
    MANAGERS_INDEX_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "in_base_irr": False,
                "generated_at": _iso_now(),
                "context": CONTEXT,
                "managers": index,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    FEED_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "in_base_irr": False,
                "quarter": feed_quarter,
                "generated_at": _iso_now(),
                "context": CONTEXT,
                "changes": feed_changes[:400],
                "watchlist_share_change_pct": threshold_pct,
                "watchlist_changes": watchlist_feed[:400],
                "consensus": agreed,
                "outside_book": ideas[:80],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def run(
    periods: int,
    alerts: bool,
    offline: bool,
    only: str | None,
    threshold_override: float | None = None,
) -> int:
    document = load_registry()
    managers = [row for row in document.get("managers") or [] if row.get("book") == "full" and row.get("cik")]
    if only:
        wanted = {item.strip() for item in only.split(",") if item.strip()}
        managers = [row for row in managers if row["manager_id"] in wanted]
    threshold = watchlist_threshold_pct(document, threshold_override)
    _tickers, names = portfolio_universe()
    cusip_map = load_cusip_map()
    registry_ciks = registry_ciks_for(managers)
    failures = []
    fresh_changes: list[dict] = []
    for manager in managers:
        try:
            built_rows = books_for_manager(manager, periods, registry_ciks, offline)
        except Exception as error:  # noqa: BLE001
            failures.append(f"{manager['manager_id']}: {error}")
            print(f"{manager['manager_id']}: FAILED {error}", flush=True)
            continue
        if not built_rows:
            print(f"{manager['manager_id']}: no book", flush=True)
            continue
        records = []
        quarter_changes: dict[str, list[dict]] = {}
        for built in built_rows:
            quarter = built.get("quarter") or "unknown"
            signature = _signature(built)
            path = POSITIONS / quarter / f"{manager['manager_id']}.csv"
            if saved_signature(manager["manager_id"], quarter) == signature and path.exists():
                print(f"{manager['manager_id']} {quarter}: unchanged", flush=True)
                continue
            rows = position_rows(manager, built, cusip_map, names)
            write_positions(path, rows)
            report = built.get("reconciliation") or {}
            flag = "ok" if report.get("ok", True) else "reconcile"
            print(f"{manager['manager_id']} {quarter}: {flag} rows={len(rows)}", flush=True)
            records.append(filing_record(manager, built))
            changes = reported_changes(
                manager,
                diff_book(manager, rows, quarter, built.get("period_end") or ""),
                set(names),
                threshold,
            )
            quarter_changes.setdefault(quarter, []).extend(changes)
            fresh_changes.extend(changes)
        if records:
            upsert_filings(records)
        for quarter, changes in quarter_changes.items():
            period_end = next((item.get("period_end") for item in built_rows if item.get("quarter") == quarter), "")
            write_changes(quarter, period_end or "", {manager["manager_id"]: changes}, threshold)
    build_dashboard(names, threshold)
    if alerts and fresh_changes:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = alert_lines(fresh_changes, set(names), today=today)
        if lines:
            text = "13F holder changes (context only, not a valuation input)\n" + "\n".join(lines[:40])
            if len(lines) > 40:
                text += f"\n and {len(lines) - 40} more"
            post_slack(text)
    if failures:
        print(f"{len(failures)} managers failed", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods", type=int, default=2)
    parser.add_argument("--alerts", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--manager", default=None, help="One manager id, or a comma-separated list.")
    parser.add_argument(
        "--watchlist-threshold",
        type=float,
        default=None,
        help="Share-change percent for watchlist adds and trims. Default is managers.json, or 5.",
    )
    args = parser.parse_args()
    return run(args.periods, args.alerts, args.offline, args.manager, args.watchlist_threshold)


if __name__ == "__main__":
    raise SystemExit(main())
