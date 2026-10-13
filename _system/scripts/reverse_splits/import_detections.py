"""Add price-detected reverse splits to the ledger, through SQLite and the normal export.

Rows come from the detector report (corroborated, listed, detector-only events)
and the filing checks (``reports/filing_checks.json``):

- ``ratio``: the confirming filing's ratio when it agrees with the printed jump
  (within 35%; a proxy often quotes a range), else the price-inferred ratio.
- ``status``: ``filing_ratio`` (the issuer and its ratio are confirmed),
  ``filing_confirmed`` (the issuer is confirmed, the ratio is price-inferred) or
  ``filing_not_found``.
- ``confidence``: 0.5, 0.4 and 0.3 for those three, against 0.5 for a
  yfinance-seeded row and 0.3 for an EDGAR candidate.
- ``needs_review`` is 1 on every row, ``source`` is ``databento_price_jump``,
  ``date_quality`` is null (the date is the first session that printed the new
  price), and cik, accession, form and company come from the confirming filing.

A detection is skipped when it is an existing ledger event under another name:
the rename join tied it to one, or a ledger event of the same issuer (CIK) lies
within ten days. Cohorts are recomputed per issuer, and only rows whose prior
count or cohort changes are touched, so the export does not churn every row.

The ledger is written by ``export_ledger`` from a scratch SQLite built with
``import_ledger``; nothing is appended by hand.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .utils import normalize_ticker

SOURCE = "databento_price_jump"
RATIO_AGREEMENT = 0.35
SAME_ISSUER_DAYS = 10
VENUE_NAMES = {"XNAS": "Nasdaq", "XNYS": "NYSE", "XASE": "NYSE American"}
CONFIDENCE = {"filing_ratio": 0.5, "filing_confirmed": 0.4, "filing_not_found": 0.3}


def company_from_entity(entity: str | None) -> str | None:
    """``"Callon Petroleum Co  (CPE)  (CIK 0000928022)"`` -> ``"Callon Petroleum Co"``."""
    if not entity:
        return None
    return re.sub(r"\s*\([^)]*\)", "", entity).strip() or None


def choose_ratio(inferred_k: float, filing_ratio: float | None) -> tuple[float, bool]:
    """(new/old ratio, from_filing). The filing wins when it agrees with prices."""
    if filing_ratio and 0 < filing_ratio < 1 and abs((1 / filing_ratio) / inferred_k - 1) <= RATIO_AGREEMENT:
        return filing_ratio, True
    return 1.0 / inferred_k, False


def build_rows(detections: list[dict], checks: dict, joins: list[dict], ledger: list[dict],
               filing_ratios: dict, now: str) -> tuple[list[dict], dict]:
    """Ledger rows for the detections, and counts of what was skipped and why. Pure."""
    joined = {(j["filing_time_symbol"].upper(), j["detected_day"]) for j in joins}
    by_cik: dict[str, list[date]] = {}
    for event in ledger:
        if event.get("cik"):
            by_cik.setdefault(str(event["cik"]).zfill(10), []).append(date.fromisoformat(str(event["ex_date"])[:10]))
    rows, skipped = [], {"rename_join": 0, "same_issuer_nearby": 0}
    for det in detections:
        symbol, day = det["symbol"].upper(), det["day"]
        if (symbol, day) in joined:
            skipped["rename_join"] += 1
            continue
        check = checks.get(f"confirm|{symbol}|{day}") or {"status": "not_found"}
        cik = check.get("cik")
        ex = date.fromisoformat(day)
        if cik and any(abs((ex - other).days) <= SAME_ISSUER_DAYS for other in by_cik.get(cik, [])):
            skipped["same_issuer_nearby"] += 1
            continue
        if cik:
            by_cik.setdefault(cik, []).append(ex)
        ratio, from_filing = choose_ratio(float(det["ratio_inferred"]), filing_ratios.get(check.get("accession")))
        confirmed = check.get("status") == "filing_confirmed"
        status = "filing_ratio" if confirmed and from_filing else "filing_confirmed" if confirmed else "filing_not_found"
        split_from = round(1.0 / ratio, 6)
        rows.append({
            "ticker": normalize_ticker(symbol), "cik": cik, "company": company_from_entity(check.get("entity")),
            "exchange": VENUE_NAMES.get(det.get("listing_venue")), "exchange_class": "listed",
            "split_from": split_from, "split_to": 1.0, "ratio": ratio,
            "first_proxy_date": None, "announce_date": None, "vote_date": None, "ratio_set_date": None,
            "effective_date": day, "ex_date": day, "prior_rs_count": None, "cohort": None,
            "status": status, "confidence": CONFIDENCE[status], "needs_review": 1, "source": SOURCE,
            "outcome": "effective", "vote_path": None, "accept_time": None, "announced_ex_date": None,
            "announced_ratio": None, "jump_status": None, "jump_observed": None, "date_quality": None,
            "accession": check.get("accession") if confirmed else None, "form": check.get("form") if confirmed else None,
            "created_at": now, "updated_at": now,
        })
    return rows, skipped


def filing_ratio(cfg, http, cik: str, accession: str) -> float | None:
    """The ratio stated in a filing's full submission text (exhibits included)."""
    from .enrich_edgar import _strip_html
    from .filings import ratio_new_over_old

    cache = cfg.edgar_cache / str(cik).zfill(10) / f"{accession.replace('-', '')}.full.txt"
    if cache.exists():
        text = cache.read_text(encoding="utf-8", errors="ignore")
    else:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}.txt"
        try:
            text = _strip_html(http.get(url).text)
        except Exception:  # noqa: BLE001 - a missing filing leaves the price-inferred ratio
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8", errors="ignore")
    return ratio_new_over_old(text)


def add_new_issuers(conn, rows: list[dict]) -> int:
    """Issuer names for CIKs the ledger does not know yet. An existing name is
    never replaced: EDGAR's display name is the current one, and the ledger's
    may be the name at the time (the export copies it onto every row of that
    CIK, announcements included)."""
    n = 0
    for row in rows:
        if row.get("cik") and row.get("company"):
            cur = conn.execute("INSERT OR IGNORE INTO issuers (cik, name, primary_ticker, exchange_class) VALUES (?, ?, ?, ?)",
                               (row["cik"], row["company"], row.get("ticker"), row.get("exchange_class") or "unknown"))
            n += cur.rowcount
    return n


def retag_cohorts(conn) -> int:
    """prior_rs_count and cohort per issuer (CIK, else ticker) over effective
    events; only rows that change are updated."""
    rows = conn.execute(
        "SELECT id, cik, ticker, ex_date, prior_rs_count, cohort FROM reverse_splits "
        "WHERE COALESCE(outcome, 'effective') = 'effective' ORDER BY COALESCE(cik, ticker), ex_date, id"
    ).fetchall()
    counters: dict[str, int] = {}
    changed = 0
    for row in rows:
        key = f"cik:{str(row['cik']).zfill(10)}" if row["cik"] else f"t:{row['ticker']}"
        prior = counters.get(key, 0)
        cohort = "first" if prior == 0 else "second" if prior == 1 else "third_plus"
        counters[key] = prior + 1
        if row["prior_rs_count"] != prior or row["cohort"] != cohort:
            conn.execute("UPDATE reverse_splits SET prior_rs_count=?, cohort=?, updated_at=datetime('now') WHERE id=?",
                         (prior, cohort, row["id"]))
            changed += 1
    conn.commit()
    return changed


def append_detections(cfg, ledger_dir: Path, work_dir: Path, fetch_ratios: bool = True, log=print) -> dict:
    from .db import init_db
    from .export_ledger import export_ledger
    from .import_ledger import _event_values, _upsert_split, import_ledger
    from .utils import RateLimitedSession

    reports = cfg.reports_dir
    detections = [r for r in csv.DictReader((reports / "split_detections.csv").open(encoding="utf-8"))
                  if r["listed_equity"] == "True" and r["corroborated"] == "True" and r["status"] == "detector_only"]
    checks = json.loads((reports / "filing_checks.json").read_text(encoding="utf-8"))
    joins = json.loads((reports / "rename_joins.json").read_text(encoding="utf-8")) if (reports / "rename_joins.json").exists() else []
    ledger = [json.loads(line) for line in (ledger_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ratios: dict[str, float | None] = {}
    if fetch_ratios:
        edgar = cfg.raw.get("edgar") or {}
        http = RateLimitedSession(edgar.get("user_agent", "ReverseSplitResearch research@localhost"), 0.25)
        wanted = (checks.get(f"confirm|{d['symbol'].upper()}|{d['day']}") for d in detections)
        confirmed = [c for c in wanted if isinstance(c, dict) and c.get("status") == "filing_confirmed" and c.get("accession") and c.get("cik")]
        for i, check in enumerate(confirmed, 1):
            ratios[check["accession"]] = filing_ratio(cfg, http, check["cik"], check["accession"])
            if i % 100 == 0:
                log(f"filing ratios {i}/{len(confirmed)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows, skipped = build_rows(detections, checks, joins, ledger, ratios, now)
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path, decisions = work_dir / "ledger_work.db", work_dir / "decisions_work.sqlite"
    for path in (db_path, decisions):
        path.unlink(missing_ok=True)
    import_ledger(ledger_dir, db_path, decisions, replace=True)
    conn = init_db(db_path)
    before = conn.execute("SELECT COUNT(*) FROM reverse_splits WHERE COALESCE(outcome,'effective')='effective'").fetchone()[0]
    add_new_issuers(conn, rows)
    for row in rows:
        _upsert_split(conn, _event_values(row))
    conn.commit()
    retagged = retag_cohorts(conn)
    after = conn.execute("SELECT COUNT(*) FROM reverse_splits WHERE COALESCE(outcome,'effective')='effective'").fetchone()[0]
    conn.close()
    export_ledger(db_path, ledger_dir, decisions)
    summary = {"candidates": len(detections), "added": after - before, "rows_built": len(rows), "skipped": skipped,
               "by_status": {s: sum(1 for r in rows if r["status"] == s) for s in CONFIDENCE},
               "cohorts_changed": retagged, "events_before": before, "events_after": after}
    log(json.dumps(summary))
    return summary
