#!/usr/bin/env python3
"""Refresh CVR universe → sleeve membership → registry classification.

  # Nightly / dashboard path (sync only — no SEC)
  python _system/scripts/refresh_cvr_universe.py

  # Weekly discovery path (fail-soft SEC + CSV inbox)
  python _system/scripts/refresh_cvr_universe.py --discover --ingest-inbox --write-review --skip-sync

  python _system/scripts/refresh_cvr_universe.py --ingest-csv path/to/screener.csv

Reads `_system/reference/cvr/cvr_universe.json` and per-ticker `research/cvr_terms.json`.
Syncs `investment_sleeves.json` sleeve `cvr_contingent` for **terms-ready** names only
(context-tier candidates stay in the universe JSON / review queue until terms exist).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import (  # noqa: E402
    DEFAULT_CLASSIFICATION,
    EXCHANGE_META,
    load_registry,
    save_registry,
)

UNIVERSE_PATH = ROOT / "_system" / "reference" / "cvr" / "cvr_universe.json"
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
INBOX_DIR = ROOT / "_system" / "reference" / "cvr" / "inbox"
INBOX_PROCESSED = INBOX_DIR / "processed"
REVIEWS_PENDING = ROOT / "_system" / "reviews" / "pending"
UA = "MarvinResearchBot/1.0 (single-stock-investments; cvr-refresh; contact: local)"


def _today() -> str:
    return date.today().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_universe() -> dict:
    if not UNIVERSE_PATH.exists():
        return {
            "as_of": _today(),
            "operating_model": {},
            "pre_close_opportunities": [],
            "post_close_universe": [],
            "discovery_feeds": [],
            "discovery_state": {},
        }
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def save_universe(doc: dict) -> None:
    doc["as_of"] = _today()
    doc["last_refresh_utc"] = _utc_now()
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _iter_universe_rows(doc: dict) -> list[dict]:
    return list(doc.get("pre_close_opportunities") or []) + list(
        doc.get("post_close_universe") or []
    )


def terms_path_for(ticker: str) -> Path:
    return ROOT / ticker / "research" / "cvr_terms.json"


def row_is_sleeve_ready(row: dict) -> bool:
    """Context candidates stay off the dashboard sleeve until terms exist."""
    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return False
    if terms_path_for(ticker).exists():
        return True
    # Explicit ready flag (Part 2 stubs may set this before full terms).
    if row.get("sleeve_ready") is True:
        return True
    return False


def universe_tickers(doc: dict, *, sleeve_policy: str = "ready") -> list[str]:
    out: list[str] = []
    for row in _iter_universe_rows(doc):
        t = str(row.get("ticker") or "").strip()
        if not t or t in out:
            continue
        if sleeve_policy == "all" or row_is_sleeve_ready(row):
            out.append(t)
    return out


def sync_sleeve_membership(doc: dict, *, sleeve_policy: str = "ready") -> list[str]:
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
    SLEEVES_PATH.write_text(json.dumps(sleeves, indent=2) + "\n", encoding="utf-8")
    return tickers


def ensure_registry_entries(tickers: list[str], doc: dict) -> int:
    """Add missing holdings rows so dashboard list_tickers() includes CVR names."""
    reg = load_registry()
    holdings = reg.setdefault("holdings", {})
    by_ticker = {
        str(r.get("ticker") or "").upper(): r for r in _iter_universe_rows(doc)
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
            "onboarded": _today(),
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
    """Compute simple display metrics on cvr_terms.json when possible."""
    updated = 0
    for row in _iter_universe_rows(doc):
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
        display["as_of"] = _today()
        display["stage"] = row.get("stage") or terms.get("stage")
        display["max_payout_usd"] = max_payout
        price = terms.get("price_live") or display.get("price_live")
        if price is not None and max_payout:
            try:
                p = float(price) / float(max_payout)
                display["p_market"] = round(max(0.0, min(p, 1.0)), 4)
            except (TypeError, ValueError):
                pass
        terms["last_refresh_utc"] = _utc_now()
        path.write_text(json.dumps(terms, indent=2) + "\n", encoding="utf-8")
        updated += 1
    return updated


def _http_get_json(url: str, timeout: int = 45) -> dict | list | None:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        print(f"WARN: SEC fetch failed: {exc}")
        return None


def _existing_tickers(doc: dict) -> set[str]:
    return {
        str(r.get("ticker") or "").upper()
        for r in _iter_universe_rows(doc)
        if r.get("ticker")
    }


def _existing_accessions(doc: dict) -> set[str]:
    out: set[str] = set()
    for r in _iter_universe_rows(doc):
        adsh = str(r.get("accession") or "").strip()
        if adsh:
            out.add(adsh)
    return out


def discover_sec_cvrs(
    doc: dict, *, days: int = 30, limit: int = 25
) -> tuple[int, bool, list[dict]]:
    """Append new pre-close candidates from SEC full-text (best-effort, fail-soft).

    Returns (added_count, sec_ok, new_rows).
    """
    query = (
        '"Contingent Value Right" OR "CVR Agreement" OR "contingent value rights"'
    )
    startdt = date.fromordinal(date.today().toordinal() - days).isoformat()
    params = urllib.parse.urlencode(
        {
            "q": query,
            "dateRange": "custom",
            "startdt": startdt,
            "enddt": _today(),
            "forms": "8-K",
        }
    )
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"
    payload = _http_get_json(url)
    if not payload:
        print("WARN: SEC discovery returned no payload; skipping discover (fail-soft)")
        return 0, False, []

    hits = []
    if isinstance(payload, dict):
        hits = payload.get("hits", {}).get("hits") or payload.get("hits") or []
    if not isinstance(hits, list):
        hits = []

    existing = _existing_tickers(doc)
    seen_adsh = _existing_accessions(doc)
    added_rows: list[dict] = []
    for hit in hits[:limit]:
        src = hit.get("_source") or hit
        display_tickers = src.get("display_names") or src.get("tickers") or []
        tickers = []
        for t in display_tickers:
            t = str(t).strip().upper()
            if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{1,2})?", t):
                tickers.append(t)
        if not tickers:
            continue
        ticker = tickers[0]
        adsh = str(src.get("adsh") or src.get("file_num") or "").strip()
        if adsh and adsh in seen_adsh:
            continue
        if ticker in existing and not adsh:
            continue
        if ticker in existing:
            # Same ticker, new accession — still skip until Part 2 multi-filing support.
            continue
        file_url = None
        if src.get("file_url"):
            file_url = src["file_url"]
        elif adsh:
            file_url = (
                f"https://www.sec.gov/Archives/edgar/data/{adsh.replace('-', '')}/"
            )
        row = {
            "id": f"{ticker}.CVR_CANDIDATE",
            "ticker": ticker,
            "stage": "pre_close",
            "tradeable_vehicle": ticker,
            "role": "opportunity",
            "source": "sec_full_text",
            "source_tier": "context",
            "discovered_at": _today(),
            "accession": adsh or None,
            "sec_hint": file_url,
            "notes": (
                "Auto-discovered; agent must extract cvr_terms.json from merger "
                "exhibits before sizing. Not sleeved until terms exist."
            ),
        }
        doc.setdefault("pre_close_opportunities", []).append(row)
        existing.add(ticker)
        if adsh:
            seen_adsh.add(adsh)
        added_rows.append(row)
        time.sleep(0.15)
    return len(added_rows), True, added_rows


def ingest_screener_csv(doc: dict, csv_path: Path) -> tuple[int, list[dict]]:
    """Context-tier ingest for AlphaRank / special-sit CSV uploads."""
    if not csv_path.exists():
        print(f"WARN: CSV not found: {csv_path}")
        return 0, []
    existing = _existing_tickers(doc)
    added_rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticker = (
                row.get("ticker")
                or row.get("Ticker")
                or row.get("symbol")
                or row.get("Symbol")
                or ""
            ).strip().upper()
            if not ticker or ticker in existing:
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
                # Accept contingent / earnout rows as context (secondary feed).
                if not any(
                    k in text
                    for k in (
                        "contingent",
                        "earnout",
                        "earn-out",
                        "cv right",
                    )
                ):
                    continue
            new_row = {
                "id": f"{ticker}.CVR_CANDIDATE",
                "ticker": ticker,
                "stage": "pre_close",
                "tradeable_vehicle": ticker,
                "role": "opportunity",
                "source": "screener_csv",
                "source_tier": "context",
                "discovered_at": _today(),
                "notes": (
                    f"Ingested from {csv_path.name}; confirm with SEC primary docs. "
                    "Not sleeved until terms exist."
                ),
            }
            doc.setdefault("pre_close_opportunities", []).append(new_row)
            existing.add(ticker)
            added_rows.append(new_row)
    return len(added_rows), added_rows


def ingest_inbox(doc: dict) -> tuple[int, list[dict], list[str]]:
    """Ingest all CSVs in reference/cvr/inbox/ then move them to inbox/processed/."""
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
        dest = INBOX_PROCESSED / f"{_today()}_{csv_path.name}"
        if dest.exists():
            dest = INBOX_PROCESSED / f"{_today()}_{csv_path.stem}_{int(time.time())}{csv_path.suffix}"
        shutil.move(str(csv_path), str(dest))
        processed.append(dest.name)
        print(f"Inbox: {csv_path.name} -> processed/ ({n} new)")
    return total, all_rows, processed


def update_discovery_state(
    doc: dict,
    *,
    sec_ok: bool | None,
    sec_added: int,
    csv_added: int,
    review_path: str | None,
) -> None:
    state = doc.setdefault("discovery_state", {})
    state["last_run_utc"] = _utc_now()
    state["last_csv_added"] = csv_added
    if sec_ok is not None:
        state["last_sec_ok"] = sec_ok
        state["last_sec_added"] = sec_added
        # Count only scheduled SEC attempts toward the unhealthy streak.
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


def write_discovery_review(
    *,
    sec_added: int,
    csv_added: int,
    sec_ok: bool | None,
    new_rows: list[dict],
    processed_csvs: list[str],
    unhealthy: bool,
) -> Path | None:
    if sec_added + csv_added == 0 and not unhealthy:
        return None
    REVIEWS_PENDING.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_PENDING / f"cvr_discovery_{_today()}.md"
    lines = [
        f"# CVR discovery — {_today()}",
        "",
        f"**UTC:** {_utc_now()}  ",
        f"**SEC ok:** {sec_ok}  ",
        f"**SEC added:** {sec_added}  ",
        f"**CSV/inbox added:** {csv_added}  ",
        f"**Unhealthy streak:** {unhealthy}  ",
        "",
        "Context-tier candidates are in `cvr_universe.json` only. "
        "They appear on the **CVRs** dashboard filter after an agent writes "
        "`{TICKER}/research/cvr_terms.json`.",
        "",
    ]
    if processed_csvs:
        lines.append("## Inbox files processed")
        lines.append("")
        for name in processed_csvs:
            lines.append(f"- `{name}`")
        lines.append("")
    if new_rows:
        lines.append("## New candidates")
        lines.append("")
        lines.append("| Ticker | Source | SEC hint |")
        lines.append("|--------|--------|----------|")
        for r in new_rows:
            hint = r.get("sec_hint") or "—"
            lines.append(
                f"| `{r.get('ticker')}` | {r.get('source')} | {hint} |"
            )
        lines.append("")
        lines.append("## Next actions")
        lines.append("")
        lines.append("1. Confirm target vs acquirer ticker (Part 2: CIK resolve).")
        lines.append("2. Pull merger exhibit / CVR agreement into ticker folder.")
        lines.append("3. Fill `cvr_terms.json` (milestones, max $, outside date).")
        lines.append("4. Nightly sync will sleeve + surface on dashboard.")
        lines.append("")
    elif unhealthy:
        lines.append("## Alert")
        lines.append("")
        lines.append(
            "SEC discovery returned empty or failed for 3+ consecutive scheduled runs. "
            "Check EDGAR full-text endpoint / User-Agent / rate limits."
        )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_sync_investment_sleeves() -> None:
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "sync_investment_sleeves.py")], cwd=str(ROOT)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Query SEC for new CVR 8-K mentions (fail-soft)",
    )
    ap.add_argument("--ingest-csv", type=Path, help="Optional screener CSV (context tier)")
    ap.add_argument(
        "--ingest-inbox",
        action="store_true",
        help=f"Ingest all CSVs in {INBOX_DIR.relative_to(ROOT)}/ then move to processed/",
    )
    ap.add_argument(
        "--write-review",
        action="store_true",
        help="Write reviews/pending/cvr_discovery_*.md when candidates added or unhealthy",
    )
    ap.add_argument(
        "--skip-sync",
        action="store_true",
        help="Do not run sync_investment_sleeves.py",
    )
    ap.add_argument(
        "--sleeve-policy",
        choices=("ready", "all"),
        default="ready",
        help="ready=only tickers with cvr_terms.json (default); all=every universe ticker",
    )
    ap.add_argument("--discover-days", type=int, default=30)
    ap.add_argument("--discover-limit", type=int, default=25)
    args = ap.parse_args()

    doc = load_universe()
    sec_added = 0
    csv_added = 0
    sec_ok: bool | None = None
    new_rows: list[dict] = []
    processed_csvs: list[str] = []

    if args.discover:
        sec_added, sec_ok, sec_rows = discover_sec_cvrs(
            doc, days=args.discover_days, limit=args.discover_limit
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

    tickers = sync_sleeve_membership(doc, sleeve_policy=args.sleeve_policy)
    print(
        f"Sleeve cvr_contingent ({args.sleeve_policy}): "
        f"{len(tickers)} tickers -> {', '.join(tickers) or '(none)'}"
    )
    added = ensure_registry_entries(tickers, doc)
    print(f"Registry: +{added} holdings entries (sleeve classification refreshed)")
    refreshed = refresh_display_fields(doc)
    print(f"Terms display refresh: {refreshed} files")

    review_path_str = None
    ran_discovery = bool(args.discover or args.ingest_inbox or args.ingest_csv)
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
                unhealthy=unhealthy,
            )
            if rp:
                review_path_str = str(rp.relative_to(ROOT)).replace("\\", "/")
                print(f"Wrote review: {review_path_str}")
                doc.setdefault("discovery_state", {})["last_review_path"] = review_path_str

    save_universe(doc)

    if not args.skip_sync:
        run_sync_investment_sleeves()
        print("Ran sync_investment_sleeves.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
