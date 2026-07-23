#!/usr/bin/env python3
"""Refresh CVR universe → sleeve membership → registry classification.

  # Nightly / dashboard path (sync only — no SEC)
  python _system/scripts/refresh_cvr_universe.py

  # Weekly discovery path (Parts 1–3)
  python _system/scripts/refresh_cvr_universe.py \\
    --discover --ingest-inbox --sync-alpharank --create-stubs \\
    --write-review --alert --skip-sync

  # Part 4 monitoring
  python _system/scripts/refresh_cvr_universe.py \\
    --refresh-prices --refresh-milestones --apply-transitions --queue-stubs

Reads `_system/reference/cvr/cvr_universe.json` and per-ticker `research/cvr_terms.json`.
Sleeves only **terms-complete** names (stubs stay off the pinned CVRs filter).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from cvr_common import (  # noqa: E402
    INBOX_DIR,
    INBOX_PROCESSED,
    REVIEWS_PENDING,
    SEC_QUERY_EXPANDED,
    SEC_QUERY_NON_SEC_FAMILY,
    SEC_QUERY_PRIMARY,
    SLEEVES_PATH,
    UNIVERSE_PATH,
    create_candidate_stub,
    enqueue_cvr_agent_task,
    fetch_yahoo_price,
    form_is_preferred,
    hit_looks_risk_factor_only,
    http_get_json,
    http_get_text,
    infer_milestone_status_from_text,
    iter_universe_rows,
    normalize_tickers,
    pick_target_ticker,
    post_slack,
    row_is_sleeve_ready,
    row_is_watch_candidate,
    terms_are_complete,
    terms_path_for,
    today,
    utc_now,
)
from portfolio_registry import (  # noqa: E402
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    load_registry,
    save_registry,
)


def load_universe() -> dict:
    if not UNIVERSE_PATH.exists():
        return {
            "as_of": today(),
            "operating_model": {},
            "pre_close_opportunities": [],
            "post_close_universe": [],
            "discovery_feeds": [],
            "discovery_state": {},
        }
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def save_universe(doc: dict) -> None:
    doc["as_of"] = today()
    doc["last_refresh_utc"] = utc_now()
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def universe_tickers(doc: dict, *, sleeve_policy: str = "ready") -> list[str]:
    out: list[str] = []
    for row in iter_universe_rows(doc):
        t = str(row.get("ticker") or "").strip()
        if not t or t in out:
            continue
        if sleeve_policy == "all" or row_is_sleeve_ready(row):
            out.append(t)
    return out


def watch_tickers(doc: dict) -> list[str]:
    out: list[str] = []
    for row in iter_universe_rows(doc):
        t = str(row.get("ticker") or "").strip()
        if t and row_is_watch_candidate(row) and t not in out:
            out.append(t)
    return out


def sync_sleeve_membership(
    doc: dict, *, sleeve_policy: str = "ready", enable_watch: bool = False
) -> list[str]:
    """Update only CVR sleeves (scoped — does not rewrite other sleeves)."""
    tickers = sorted(universe_tickers(doc, sleeve_policy=sleeve_policy), key=str.upper)
    sleeves = json.loads(SLEEVES_PATH.read_text(encoding="utf-8"))
    sleeve = (sleeves.setdefault("sleeves", {})).setdefault(
        "cvr_contingent",
        {
            "label": "CVRs",
            "description": "Pre-close contingent deals and post-close CVR claims",
            "tickers": [],
        },
    )
    sleeve["label"] = "CVRs"
    sleeve["tickers"] = tickers

    if enable_watch:
        watch = sorted(watch_tickers(doc), key=str.upper)
        w = (sleeves.setdefault("sleeves", {})).setdefault(
            "cvr_watch",
            {
                "label": "CVR watch",
                "description": "Context-tier CVR / contingent stubs awaiting terms",
                "tickers": [],
            },
        )
        w["tickers"] = watch
        print(f"Sleeve cvr_watch: {len(watch)} tickers")
    elif "cvr_watch" in (sleeves.get("sleeves") or {}):
        # Keep sleeve definition but do not grow it unless explicitly enabled.
        pass

    SLEEVES_PATH.write_text(json.dumps(sleeves, indent=2) + "\n", encoding="utf-8")
    return tickers


def ensure_registry_entries(tickers: list[str], doc: dict) -> int:
    """Add/update only the given CVR tickers (scoped registry write)."""
    reg = load_registry()
    holdings = reg.setdefault("holdings", {})
    by_ticker = {
        str(r.get("ticker") or "").upper(): r for r in iter_universe_rows(doc)
    }
    added = 0
    for ticker in tickers:
        if ticker in holdings:
            cls = holdings[ticker].setdefault("classification", {})
            if cls.get("investment_sleeve") != "cvr_contingent":
                cls["investment_sleeve"] = "cvr_contingent"
                cls.setdefault("payoff_lens", "event")
            continue
        urow = by_ticker.get(ticker.upper()) or {}
        stage = urow.get("stage") or (
            "pre_close" if ticker.upper() == "MFBP" else "post_close"
        )
        company = None
        path = terms_path_for(ticker)
        if path.exists():
            try:
                terms = json.loads(path.read_text(encoding="utf-8"))
                company = terms.get("instrument_label")
            except json.JSONDecodeError:
                company = None
        if not company:
            company = f"{ticker} CVR / contingent"
        holdings[ticker] = {
            "company": company,
            "market": "US",
            "exchange": EXCHANGE_META.get(ticker, "OTC"),
            "onboarded": today(),
            "download": {"type": "us_shared", "ir_roots": []},
            "classification": {
                **DEFAULT_CLASSIFICATION,
                "investment_sleeve": "cvr_contingent",
                "payoff_lens": "event",
                "irr_method": "binary_milestone" if stage == "post_close" else "scenario",
            },
        }
        added += 1
    save_registry(reg)
    return added


def refresh_display_fields(doc: dict) -> int:
    updated = 0
    for row in iter_universe_rows(doc):
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        path = terms_path_for(ticker)
        if not path.exists():
            continue
        try:
            terms = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        max_payout = (
            row.get("max_contingent_usd")
            or row.get("max_payout_usd")
            or terms.get("max_payout_usd")
        )
        display = terms.setdefault("display", {})
        display["as_of"] = today()
        display["stage"] = row.get("stage") or terms.get("stage")
        display["max_payout_usd"] = max_payout
        price = terms.get("price_live") or display.get("price_live")
        if price is not None and max_payout:
            try:
                p = float(price) / float(max_payout)
                display["p_market"] = round(max(0.0, min(p, 1.0)), 4)
            except (TypeError, ValueError):
                pass
        # Naive pre-close IRR @ buy limit if both price and max known.
        buy_limit = terms.get("buy_limit") or display.get("buy_limit") or price
        if buy_limit and max_payout and terms.get("stage") == "pre_close":
            try:
                bl = float(buy_limit)
                mp = float(max_payout)
                if bl > 0:
                    # Single-horizon placeholder: payoff / price - 1 (not discounted).
                    display["irr_naive_at_buy_limit"] = round((mp / bl) - 1.0, 4)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        terms["last_refresh_utc"] = utc_now()
        path.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
        updated += 1
    return updated


def _existing_tickers(doc: dict) -> set[str]:
    return {
        str(r.get("ticker") or "").upper()
        for r in iter_universe_rows(doc)
        if r.get("ticker")
    }


def _existing_accession_cik(doc: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in iter_universe_rows(doc):
        adsh = str(r.get("accession") or "").strip()
        cik = str(r.get("cik") or "").strip().zfill(10) if r.get("cik") else ""
        if adsh:
            out.add((adsh, cik))
    return out


def _extract_hits(payload: dict | list | None) -> list[dict]:
    if not payload:
        return []
    hits = []
    if isinstance(payload, dict):
        hits = payload.get("hits", {}).get("hits") or payload.get("hits") or []
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]


def _sec_search(query: str, *, days: int, forms: str) -> tuple[list[dict], bool]:
    startdt = date.fromordinal(date.today().toordinal() - days).isoformat()
    params = urllib.parse.urlencode(
        {
            "q": query,
            "dateRange": "custom",
            "startdt": startdt,
            "enddt": today(),
            "forms": forms,
        }
    )
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"
    payload = http_get_json(url)
    if payload is None:
        return [], False
    return _extract_hits(payload), True


def _row_from_sec_hit(
    src: dict, *, source: str, query_family: str
) -> dict | None:
    form = str(src.get("form") or src.get("forms") or src.get("file_type") or "")
    if not form_is_preferred(form):
        return None
    if hit_looks_risk_factor_only(src):
        return None

    display_tickers = normalize_tickers(
        src.get("display_names") or src.get("tickers") or []
    )
    filing_cik = src.get("entity_id") or src.get("ciks") or src.get("cik")
    if isinstance(filing_cik, list):
        filing_cik = filing_cik[0] if filing_cik else None
    filing_cik_s = str(filing_cik).zfill(10) if filing_cik else None

    ticker = pick_target_ticker(display_tickers, filing_cik=filing_cik_s)
    if not ticker and filing_cik_s:
        # CIK-only resolve when display_names empty / noisy
        from cvr_common import resolve_ticker_for_cik

        ticker = resolve_ticker_for_cik(filing_cik_s)
    if not ticker:
        return None

    adsh = str(src.get("adsh") or src.get("file_num") or "").strip()
    file_url = src.get("file_url")
    if not file_url and adsh:
        # Prefer CIK-based archive path when available.
        cik_path = filing_cik_s.lstrip("0") if filing_cik_s else adsh.replace("-", "")
        file_url = f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{adsh.replace('-', '')}/"

    entity_name = src.get("entity_name") or src.get("display_names")
    if isinstance(entity_name, list):
        entity_name = entity_name[0] if entity_name else None

    return {
        "id": f"{ticker}.CVR_CANDIDATE",
        "ticker": ticker,
        "cik": filing_cik_s,
        "stage": "pre_close",
        "tradeable_vehicle": ticker,
        "role": "opportunity",
        "source": source,
        "source_tier": "context",
        "query_family": query_family,
        "form": form or None,
        "discovered_at": today(),
        "accession": adsh or None,
        "sec_hint": file_url,
        "entity_name": entity_name,
        "notes": (
            "Auto-discovered; extract cvr_terms.json from merger exhibits before sizing. "
            "Stub folder may exist; not sleeved until terms_complete=true."
        ),
    }


def discover_sec_cvrs(
    doc: dict,
    *,
    days: int = 30,
    limit: int = 25,
    expanded: bool = True,
    non_sec_family: bool = False,
) -> tuple[int, bool, list[dict]]:
    """SEC full-text discovery with CIK target resolve + form filters (fail-soft)."""
    forms_primary = "8-K,DEFM14A,PREM14A,S-4"
    searches: list[tuple[str, str, str]] = [
        (SEC_QUERY_PRIMARY, forms_primary, "primary_cvr"),
    ]
    if expanded:
        searches.append((SEC_QUERY_EXPANDED, forms_primary, "expanded_contingent"))
    if non_sec_family:
        searches.append((SEC_QUERY_NON_SEC_FAMILY, "8-K,DEFM14A,PREM14A", "non_sec_family"))

    existing = _existing_tickers(doc)
    seen_keys = _existing_accession_cik(doc)
    added_rows: list[dict] = []
    any_ok = False
    any_payload = False

    for query, forms, family in searches:
        hits, ok = _sec_search(query, days=days, forms=forms)
        if ok:
            any_ok = True
            any_payload = True
        else:
            continue
        for hit in hits:
            if len(added_rows) >= limit:
                break
            src = hit.get("_source") or hit
            row = _row_from_sec_hit(src, source="sec_full_text", query_family=family)
            if not row:
                continue
            adsh = row.get("accession") or ""
            cik = row.get("cik") or ""
            key = (adsh, cik)
            if adsh and key in seen_keys:
                continue
            ticker = row["ticker"]
            # Allow same ticker with new accession (multi-filing), else skip dup ticker.
            if ticker in existing and not adsh:
                continue
            if ticker in existing and adsh:
                # Update existing row's accession list rather than duplicating ticker.
                updated = False
                for er in doc.get("pre_close_opportunities") or []:
                    if str(er.get("ticker") or "").upper() == ticker:
                        prior = er.get("accessions") or []
                        if adsh not in prior and adsh != er.get("accession"):
                            prior = list(prior)
                            if er.get("accession"):
                                prior.append(er["accession"])
                            prior.append(adsh)
                            er["accessions"] = sorted(set(prior))
                            er["sec_hint"] = row.get("sec_hint") or er.get("sec_hint")
                            er["last_seen_at"] = today()
                            updated = True
                        break
                if updated:
                    seen_keys.add(key)
                continue
            doc.setdefault("pre_close_opportunities", []).append(row)
            existing.add(ticker)
            if adsh:
                seen_keys.add(key)
            added_rows.append(row)
            time.sleep(0.12)
        time.sleep(0.25)

    if not any_payload:
        print("WARN: SEC discovery returned no payload; skipping discover (fail-soft)")
        return 0, False, []
    return len(added_rows), any_ok, added_rows


def ingest_screener_csv(doc: dict, csv_path: Path) -> tuple[int, list[dict]]:
    """Context-tier ingest; reject rows without ticker (Part 3 contract)."""
    if not csv_path.exists():
        print(f"WARN: CSV not found: {csv_path}")
        return 0, []
    existing = _existing_tickers(doc)
    added_rows: list[dict] = []
    rejected = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            print(f"WARN: CSV has no header: {csv_path}")
            return 0, []
        for row in reader:
            ticker = (
                row.get("ticker")
                or row.get("Ticker")
                or row.get("symbol")
                or row.get("Symbol")
                or ""
            ).strip().upper()
            if not ticker:
                rejected += 1
                continue
            if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{1,2})?", ticker):
                rejected += 1
                continue
            if ticker in existing:
                continue
            cvr_flag = (
                row.get("cvr")
                or row.get("CVR")
                or row.get("has_cvr")
                or row.get("consideration")
                or ""
            )
            text = " ".join(str(v) for v in row.values()).lower()
            if "cvr" not in text and str(cvr_flag).lower() not in (
                "1",
                "true",
                "yes",
                "y",
            ):
                if not any(
                    k in text
                    for k in (
                        "contingent",
                        "earnout",
                        "earn-out",
                        "cv right",
                        "ecip",
                    )
                ):
                    continue
            company = (row.get("company") or row.get("Company") or "").strip() or None
            new_row = {
                "id": f"{ticker}.CVR_CANDIDATE",
                "ticker": ticker,
                "stage": "pre_close",
                "tradeable_vehicle": ticker,
                "role": "opportunity",
                "source": "screener_csv",
                "source_tier": "context",
                "discovered_at": today(),
                "entity_name": company,
                "notes": (
                    f"Ingested from {csv_path.name}; confirm with SEC primary docs. "
                    "Not sleeved until terms_complete=true."
                ),
            }
            doc.setdefault("pre_close_opportunities", []).append(new_row)
            existing.add(ticker)
            added_rows.append(new_row)
    if rejected:
        print(f"CSV {csv_path.name}: rejected {rejected} rows (missing/invalid ticker)")
    return len(added_rows), added_rows


def sync_alpharank_drop(drop_path: Path | None = None) -> list[str]:
    """Copy AlphaRank / special-sit CSVs from optional drop path into inbox/."""
    path = drop_path
    if path is None:
        env = (
            os.environ.get("CVR_ALPHARANK_DROP_PATH")
            or os.environ.get("ALPHARANK_CSV_PATH")
            or ""
        ).strip()
        path = Path(env) if env else None
    if path is None:
        return []
    path = path.expanduser()
    if not path.exists():
        print(f"WARN: AlphaRank drop path missing: {path}")
        return []
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    sources = [path] if path.is_file() else sorted(path.glob("*.csv"))
    for src in sources:
        if not src.is_file() or not src.name.lower().endswith(".csv"):
            continue
        dest = INBOX_DIR / f"alpharank_{today()}_{src.name}"
        if dest.exists():
            dest = INBOX_DIR / f"alpharank_{today()}_{src.stem}_{int(time.time())}.csv"
        shutil.copy2(src, dest)
        copied.append(dest.name)
        print(f"AlphaRank drop: {src} -> inbox/{dest.name}")
    return copied


def ingest_inbox(doc: dict) -> tuple[int, list[dict], list[str]]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_PROCESSED.mkdir(parents=True, exist_ok=True)
    total = 0
    all_rows: list[dict] = []
    processed: list[str] = []
    for csv_path in sorted(INBOX_DIR.glob("*.csv")):
        if csv_path.name.lower().startswith("sample"):
            continue
        n, rows = ingest_screener_csv(doc, csv_path)
        total += n
        all_rows.extend(rows)
        dest = INBOX_PROCESSED / f"{today()}_{csv_path.name}"
        if dest.exists():
            dest = (
                INBOX_PROCESSED
                / f"{today()}_{csv_path.stem}_{int(time.time())}{csv_path.suffix}"
            )
        shutil.move(str(csv_path), str(dest))
        processed.append(dest.name)
        print(f"Inbox: {csv_path.name} -> processed/ ({n} new)")
    return total, all_rows, processed


def create_stubs_for_rows(rows: list[dict]) -> list[str]:
    created: list[str] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        ok = create_candidate_stub(
            ticker,
            accession=row.get("accession"),
            sec_hint=row.get("sec_hint"),
            source=str(row.get("source") or "discovery"),
            company=row.get("entity_name"),
        )
        if ok:
            row["stub_created"] = True
            row["stub_path"] = f"{ticker}/research/cvr_terms.json"
            created.append(ticker)
            enqueue_cvr_agent_task(ticker, reason="new_discovery_stub")
    return created


def update_discovery_state(
    doc: dict,
    *,
    sec_ok: bool | None,
    sec_added: int,
    csv_added: int,
    review_path: str | None,
) -> None:
    state = doc.setdefault("discovery_state", {})
    state["last_run_utc"] = utc_now()
    state["last_csv_added"] = csv_added
    if sec_ok is not None:
        state["last_sec_ok"] = sec_ok
        state["last_sec_added"] = sec_added
        empty_or_fail = (not sec_ok) or sec_added == 0
        if empty_or_fail:
            state["consecutive_sec_empty_or_fail"] = int(
                state.get("consecutive_sec_empty_or_fail") or 0
            ) + 1
        else:
            state["consecutive_sec_empty_or_fail"] = 0
    if review_path:
        state["last_review_path"] = review_path
    unhealthy = int(state.get("consecutive_sec_empty_or_fail") or 0) >= 3
    state["unhealthy"] = unhealthy
    if unhealthy:
        print(
            "WARN: discovery_state.unhealthy=true "
            f"(consecutive_sec_empty_or_fail={state['consecutive_sec_empty_or_fail']})"
        )


def outside_dates_within(doc: dict, days: int = 90) -> list[dict]:
    alerts: list[dict] = []
    horizon = date.fromordinal(date.today().toordinal() + days)
    for row in iter_universe_rows(doc):
        od = row.get("outside_date")
        ticker = row.get("ticker")
        if not od and ticker:
            terms = None
            try:
                p = terms_path_for(str(ticker))
                if p.exists():
                    terms = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                terms = None
            if terms:
                od = terms.get("outside_date")
                for ms in terms.get("milestones") or []:
                    for key in ("deadline", "deadline_primary", "outside_date"):
                        if ms.get(key) and not od:
                            od = ms.get(key)
        if not od or not ticker:
            continue
        try:
            d = date.fromisoformat(str(od)[:10])
        except ValueError:
            continue
        if date.today() <= d <= horizon:
            alerts.append({"ticker": ticker, "outside_date": d.isoformat()})
    return alerts


def write_discovery_review(
    *,
    sec_added: int,
    csv_added: int,
    sec_ok: bool | None,
    new_rows: list[dict],
    processed_csvs: list[str],
    stubs_created: list[str],
    unhealthy: bool,
    outside_alerts: list[dict],
) -> Path | None:
    if (
        sec_added + csv_added == 0
        and not unhealthy
        and not outside_alerts
        and not stubs_created
    ):
        return None
    REVIEWS_PENDING.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_PENDING / f"cvr_discovery_{today()}.md"
    lines = [
        f"# CVR discovery — {today()}",
        "",
        f"**UTC:** {utc_now()}  ",
        f"**SEC ok:** {sec_ok}  ",
        f"**SEC added:** {sec_added}  ",
        f"**CSV/inbox added:** {csv_added}  ",
        f"**Stubs created:** {len(stubs_created)}  ",
        f"**Unhealthy streak:** {unhealthy}  ",
        "",
        "Context-tier candidates / stubs stay off the **CVRs** filter until "
        "`cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout "
        "or milestones.",
        "",
    ]
    if processed_csvs:
        lines += ["## Inbox files processed", ""]
        lines += [f"- `{name}`" for name in processed_csvs]
        lines.append("")
    if stubs_created:
        lines += ["## Stub folders created", ""]
        lines += [f"- `{t}/` (+ skeleton terms / evidence / manifest)" for t in stubs_created]
        lines.append("")
    if new_rows:
        lines += [
            "## New candidates",
            "",
            "| Ticker | Source | Form | CIK | SEC hint |",
            "|--------|--------|------|-----|----------|",
        ]
        for r in new_rows:
            hint = r.get("sec_hint") or "—"
            lines.append(
                f"| `{r.get('ticker')}` | {r.get('source')} | {r.get('form') or '—'} | "
                f"{r.get('cik') or '—'} | {hint} |"
            )
        lines += [
            "",
            "## Next actions",
            "",
            "1. Confirm target vs acquirer (CIK resolve already preferred target).",
            "2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.",
            "3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).",
            "4. Nightly sync will sleeve + surface on dashboard.",
            "",
        ]
    if outside_alerts:
        lines += ["## Outside dates < 90d", ""]
        for a in outside_alerts:
            lines.append(f"- `{a['ticker']}` outside_date={a['outside_date']}")
        lines.append("")
    if unhealthy:
        lines += [
            "## Alert",
            "",
            "SEC discovery returned empty or failed for 3+ consecutive scheduled runs. "
            "Check EDGAR full-text endpoint / User-Agent / rate limits.",
            "",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def refresh_prices(doc: dict) -> int:
    updated = 0
    for row in iter_universe_rows(doc):
        ticker = str(row.get("ticker") or "").strip()
        vehicle = str(row.get("tradeable_vehicle") or ticker).strip()
        if not ticker:
            continue
        # Post-close non-tradeable CVRs usually have no quote.
        if row.get("tradeable") is False or ".CVR" in ticker.upper():
            continue
        path = terms_path_for(ticker)
        if not path.exists():
            continue
        try:
            terms = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        quote_sym = str(terms.get("tradeable_vehicle") or vehicle).split()[0]
        quote_sym = quote_sym.replace("OTC:", "").replace(":", "")
        price = fetch_yahoo_price(quote_sym)
        if price is None:
            continue
        display = terms.setdefault("display", {})
        terms["price_live"] = price
        display["price_live"] = price
        display["price_as_of"] = utc_now()
        max_payout = (
            row.get("max_contingent_usd")
            or row.get("max_payout_usd")
            or terms.get("max_payout_usd")
        )
        if max_payout:
            try:
                display["p_market"] = round(
                    max(0.0, min(float(price) / float(max_payout), 1.0)), 4
                )
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        terms["last_refresh_utc"] = utc_now()
        path.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
        row["price_live"] = price
        updated += 1
        time.sleep(0.1)
    return updated


def refresh_milestones(doc: dict) -> int:
    """Re-read linked local/remote SEC HTML for paid/failed/extended cues."""
    updated = 0
    for row in iter_universe_rows(doc):
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        path = terms_path_for(ticker)
        if not path.exists():
            continue
        try:
            terms = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if terms.get("stub"):
            continue
        milestones = terms.get("milestones") or []
        if not milestones:
            continue
        texts: list[str] = []
        for link in terms.get("sec_links") or []:
            local = link.get("local")
            if local:
                lp = ROOT / local
                if lp.exists():
                    texts.append(lp.read_text(encoding="utf-8", errors="ignore")[:200_000])
                    continue
            url = link.get("url")
            if url and str(url).startswith("http"):
                remote = http_get_text(str(url))
                if remote:
                    texts.append(remote[:200_000])
                time.sleep(0.15)
        if not texts:
            continue
        blob = "\n".join(texts)
        changed = False
        for ms in milestones:
            if ms.get("status") in ("paid", "failed"):
                continue
            status = infer_milestone_status_from_text(blob)
            if status and status != ms.get("status"):
                ms["status"] = status
                ms["status_inferred_at"] = utc_now()
                ms["status_source"] = "sec_html_heuristic"
                changed = True
        if changed:
            terms["last_refresh_utc"] = utc_now()
            path.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
            updated += 1
    return updated


def apply_stage_transitions(doc: dict) -> int:
    """Move pre_close → post_close when close_date set or delisted flag."""
    pre = list(doc.get("pre_close_opportunities") or [])
    post = list(doc.get("post_close_universe") or [])
    remain: list[dict] = []
    moved = 0
    for row in pre:
        ticker = str(row.get("ticker") or "").strip()
        terms = None
        tp = terms_path_for(ticker) if ticker else None
        if tp and tp.exists():
            try:
                terms = json.loads(tp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                terms = None
        close_date = (terms or {}).get("parent_deal", {}).get("close_date") or row.get(
            "close_date"
        )
        delisted = bool(row.get("delisted") or (terms or {}).get("delisted"))
        stage_force = (terms or {}).get("stage") == "post_close"
        if not (close_date or delisted or stage_force):
            remain.append(row)
            continue
        hist = list(row.get("stage_history") or [])
        hist.append(
            {
                "from": "pre_close",
                "to": "post_close",
                "at": utc_now(),
                "close_date": close_date,
                "delisted": delisted,
            }
        )
        row["stage_history"] = hist
        row["stage"] = "post_close"
        row["role"] = "claim_inventory"
        if close_date:
            row["close_date"] = close_date
        post.append(row)
        if terms is not None and tp is not None:
            terms["stage"] = "post_close"
            terms.setdefault("display", {})["stage"] = "post_close"
            terms["last_refresh_utc"] = utc_now()
            tp.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
        moved += 1
    doc["pre_close_opportunities"] = remain
    doc["post_close_universe"] = post
    return moved


def queue_ready_stubs(doc: dict) -> list[str]:
    """Queue Marvin handoff when a stub folder exists but terms incomplete."""
    queued: list[str] = []
    for row in iter_universe_rows(doc):
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        terms = None
        p = terms_path_for(ticker)
        if p.exists():
            try:
                terms = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                terms = None
        if terms is None:
            continue
        if terms_are_complete(terms):
            continue
        if terms.get("stub") or row.get("stub_created"):
            enqueue_cvr_agent_task(ticker, reason="stub_awaiting_terms")
            queued.append(ticker)
    return queued


def run_sync_investment_sleeves(*, scoped_tickers: list[str] | None = None) -> None:
    """Run sleeve sync; optionally restrict registry sleeve stamps to CVR names.

    Full sync_investment_sleeves.py still refreshes classification.json globally
    (needed for dashboard), but we only *add* CVR membership here beforehand.
    """
    if scoped_tickers:
        # Ensure sleeve JSON already limited to CVR ready set before sync.
        pass
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "sync_investment_sleeves.py")], cwd=str(ROOT)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--discover", action="store_true", help="SEC full-text discover (fail-soft)")
    ap.add_argument("--no-expanded-queries", action="store_true", help="Skip earnout/contingent OR query")
    ap.add_argument(
        "--discover-non-sec-family",
        action="store_true",
        help="Also run ECIP/bank contingent heuristic SEC query",
    )
    ap.add_argument("--ingest-csv", type=Path, help="Optional screener CSV (context tier)")
    ap.add_argument("--ingest-inbox", action="store_true", help="Ingest inbox/*.csv")
    ap.add_argument(
        "--sync-alpharank",
        action="store_true",
        help="Copy CSVs from CVR_ALPHARANK_DROP_PATH / ALPHARANK_CSV_PATH into inbox/",
    )
    ap.add_argument(
        "--alpharank-path",
        type=Path,
        help="Override AlphaRank drop file or directory",
    )
    ap.add_argument(
        "--create-stubs",
        action="store_true",
        help="Create ticker stub folders + skeleton terms for new candidates",
    )
    ap.add_argument("--write-review", action="store_true")
    ap.add_argument(
        "--alert",
        action="store_true",
        help="Slack notify when SLACK_WEBHOOK_URL set (new candidates / unhealthy / outside<90d)",
    )
    ap.add_argument("--skip-sync", action="store_true")
    ap.add_argument(
        "--sleeve-policy",
        choices=("ready", "all"),
        default="ready",
        help="ready=terms_complete only (default)",
    )
    ap.add_argument(
        "--enable-watch-sleeve",
        action="store_true",
        help="Maintain optional cvr_watch sleeve for context stubs",
    )
    ap.add_argument("--discover-days", type=int, default=30)
    ap.add_argument("--discover-limit", type=int, default=25)
    ap.add_argument("--refresh-prices", action="store_true")
    ap.add_argument("--refresh-milestones", action="store_true")
    ap.add_argument("--apply-transitions", action="store_true")
    ap.add_argument(
        "--queue-stubs",
        action="store_true",
        help="Enqueue incomplete stubs to _system/data/cvr_agent_queue.json",
    )
    args = ap.parse_args()

    doc = load_universe()
    sec_added = 0
    csv_added = 0
    sec_ok: bool | None = None
    new_rows: list[dict] = []
    processed_csvs: list[str] = []
    stubs_created: list[str] = []

    if args.sync_alpharank or args.alpharank_path:
        sync_alpharank_drop(args.alpharank_path)

    if args.discover:
        sec_added, sec_ok, sec_rows = discover_sec_cvrs(
            doc,
            days=args.discover_days,
            limit=args.discover_limit,
            expanded=not args.no_expanded_queries,
            non_sec_family=args.discover_non_sec_family,
        )
        new_rows.extend(sec_rows)
        print(f"SEC discover: +{sec_added} pre-close candidates (ok={sec_ok})")
    if args.ingest_csv:
        n, rows = ingest_screener_csv(doc, args.ingest_csv)
        csv_added += n
        new_rows.extend(rows)
        print(f"CSV ingest: +{n} pre-close candidates")
    if args.ingest_inbox:
        n, rows, processed_csvs = ingest_inbox(doc)
        csv_added += n
        new_rows.extend(rows)
        print(f"Inbox ingest: +{n} pre-close candidates ({len(processed_csvs)} files)")

    if args.create_stubs and new_rows:
        stubs_created = create_stubs_for_rows(new_rows)
        print(f"Stubs created: {len(stubs_created)} -> {', '.join(stubs_created) or '(none)'}")

    if args.apply_transitions:
        moved = apply_stage_transitions(doc)
        print(f"Stage transitions pre→post: {moved}")

    if args.refresh_prices:
        n = refresh_prices(doc)
        print(f"Prices refreshed: {n}")

    if args.refresh_milestones:
        n = refresh_milestones(doc)
        print(f"Milestone heuristic updates: {n}")

    if args.queue_stubs:
        q = queue_ready_stubs(doc)
        print(f"Agent queue stubs: {len(q)}")

    tickers = sync_sleeve_membership(
        doc,
        sleeve_policy=args.sleeve_policy,
        enable_watch=args.enable_watch_sleeve,
    )
    print(
        f"Sleeve cvr_contingent ({args.sleeve_policy}): "
        f"{len(tickers)} tickers -> {', '.join(tickers) or '(none)'}"
    )
    # Scoped registry: only CVR sleeve members (+ newly created stubs for watch).
    reg_tickers = list(tickers)
    if args.enable_watch_sleeve:
        reg_tickers = sorted(set(reg_tickers) | set(watch_tickers(doc)), key=str.upper)
    added = ensure_registry_entries(reg_tickers, doc)
    print(f"Registry: +{added} holdings entries (scoped CVR refresh)")
    refreshed = refresh_display_fields(doc)
    print(f"Terms display refresh: {refreshed} files")

    outside_alerts = outside_dates_within(doc, days=90)
    review_path_str = None
    ran_discovery = bool(
        args.discover or args.ingest_inbox or args.ingest_csv or args.sync_alpharank
    )
    if ran_discovery or args.write_review:
        if ran_discovery:
            update_discovery_state(
                doc,
                sec_ok=sec_ok,
                sec_added=sec_added,
                csv_added=csv_added,
                review_path=None,
            )
        unhealthy = bool((doc.get("discovery_state") or {}).get("unhealthy"))
        if args.write_review:
            rp = write_discovery_review(
                sec_added=sec_added,
                csv_added=csv_added,
                sec_ok=sec_ok,
                new_rows=new_rows,
                processed_csvs=processed_csvs,
                stubs_created=stubs_created,
                unhealthy=unhealthy,
                outside_alerts=outside_alerts,
            )
            if rp:
                review_path_str = str(rp.relative_to(ROOT)).replace("\\", "/")
                print(f"Wrote review: {review_path_str}")
                doc.setdefault("discovery_state", {})["last_review_path"] = review_path_str

        if args.alert:
            unhealthy = bool((doc.get("discovery_state") or {}).get("unhealthy"))
            parts = []
            if new_rows:
                parts.append(
                    f"CVR discovery +{len(new_rows)}: "
                    + ", ".join(str(r.get('ticker')) for r in new_rows[:12])
                )
            if stubs_created:
                parts.append(f"stubs: {', '.join(stubs_created[:12])}")
            if unhealthy:
                parts.append("SEC discovery unhealthy (3+ empty/fail runs)")
            if outside_alerts:
                parts.append(
                    "outside<90d: "
                    + ", ".join(f"{a['ticker']}@{a['outside_date']}" for a in outside_alerts[:8])
                )
            if parts:
                ok = post_slack(" | ".join(parts))
                print(f"Slack alert: {'sent' if ok else 'skipped (no webhook or failed)'}")

    save_universe(doc)

    if not args.skip_sync:
        run_sync_investment_sleeves(scoped_tickers=tickers)
        print("Ran sync_investment_sleeves.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
