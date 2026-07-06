#!/usr/bin/env python3
"""Build dashboard/data/activist_feed.json from per-ticker activist indexes."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from activist_common import (
    PORTFOLIO_REGISTRY,
    firm_name,
    load_global_scan,
    load_json,
    load_ticker_index,
    portfolio_tickers,
    prune_ghost_index_entries,
    resolve_report_file,
)
from activist_short_md import collect_short_markdown_reports, short_md_report_entry
from activist_date_parse import normalize_partial_date, parse_date_from_stem
from activist_link_health import check_links
from activist_materiality import materiality_score, materiality_tier
from sec_filer_parse import (
    UNRESOLVED_FIRM_ID,
    analyze_sec_filing,
    build_activist_title,
    form_from_filing_path,
    is_sec_filing_relpath,
    parse_stake_percent,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "activist_feed.json"
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "magis-capital-partners/single-stock-investments")
PROXY_DEDUP_FORMS = frozenset({"DFAN14A", "DEFC14A", "PREC14A"})
DEDUP_WINDOW_DAYS = 7
WEAK_MATCH_TICKER_THRESHOLD = 5


def github_blob(path: str | None) -> str | None:
    if not path:
        return None
    return f"https://github.com/{GITHUB_REPO}/blob/main/{path.replace(chr(92), '/')}"


def feed_eligible(report: dict) -> bool:
    if report.get("include_in_feed") is False:
        return False
    if report.get("triage_verdict") in {"auto_passive"}:
        return False
    if report.get("filing_class") == "passive_13g":
        return False
    _ref, _is_pdf, exists = resolve_report_file(report)
    if not exists and not report.get("source_url"):
        return False
    return True


def enrich_report_metadata(report: dict) -> dict:
    out = dict(report)
    iso, precision, source = normalize_partial_date(out.get("report_date"))
    if iso:
        out["report_date"] = iso
        out.setdefault("date_precision", precision)
        out.setdefault("date_source", source or out.get("date_source") or "normalized")
    if not out.get("report_date"):
        path = out.get("local_file") or out.get("local_pdf") or out.get("canonical_file") or ""
        if path:
            iso, precision, source = parse_date_from_stem(Path(path).stem)
            if iso:
                out["report_date"] = iso
                out["date_precision"] = precision
                out["date_source"] = source or "filename"
    if not out.get("title") and out.get("local_file"):
        stem = Path(out["local_file"]).stem
        firm_id = out.get("firm_id") or (stem.split("_")[0] if "_" in stem else "unknown")
        slug = stem.split("_", 2)[-1] if stem.count("_") >= 2 else stem
        out["title"] = slug.replace("_", " ").replace("-", " ")[:120] or firm_name(firm_id)
    if not out.get("firm_name") and out.get("firm_id"):
        out["firm_name"] = firm_name(out["firm_id"])
    return out


def dedupe_proxy_amendments(rows: list[dict]) -> list[dict]:
    kept: list[dict] = []
    dropped_keys: set[tuple[str, str, str, str]] = set()
    buckets: dict[tuple[str, str, str], list[dict]] = {}

    for row in rows:
        form = row.get("form") or ""
        if form not in PROXY_DEDUP_FORMS:
            kept.append(row)
            continue
        key = (row.get("ticker") or "", row.get("firm_id") or "", form)
        buckets.setdefault(key, []).append(row)

    for key, group in buckets.items():
        group.sort(key=lambda r: r.get("report_date") or "", reverse=True)
        anchor = None
        for row in group:
            date_text = row.get("report_date") or ""
            if not anchor:
                kept.append({**row, "campaign_group_size": len(group)})
                anchor = date_text
                continue
            if not date_text or not anchor:
                kept.append(row)
                continue
            try:
                row_dt = datetime.strptime(date_text[:10], "%Y-%m-%d")
                anchor_dt = datetime.strptime(anchor[:10], "%Y-%m-%d")
            except ValueError:
                kept.append(row)
                continue
            if anchor_dt - row_dt <= timedelta(days=DEDUP_WINDOW_DAYS):
                dropped_keys.add((key[0], key[1], key[2], date_text))
                continue
            kept.append({**row, "campaign_group_size": 1})
            anchor = date_text

    kept.sort(key=lambda r: (r.get("report_date") or "", r.get("ticker") or ""), reverse=True)
    return kept


def _read_filing_text(path: Path, limit: int = 120_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


_STAKE_CACHE: dict[str, float | None] = {}


def stake_for_filing(file_ref: str | None) -> float | None:
    """Parse disclosed ownership percent from a local SEC filing (cached per path)."""
    if not file_ref:
        return None
    if file_ref in _STAKE_CACHE:
        return _STAKE_CACHE[file_ref]
    path = ROOT / file_ref
    stake = None
    if path.exists():
        stake = parse_stake_percent(_read_filing_text(path, limit=400_000))
    _STAKE_CACHE[file_ref] = stake
    return stake


def enrich_filer_metadata(report: dict, *, ticker: str) -> dict:
    out = enrich_report_metadata(report)
    if out.get("firm_id") != UNRESOLVED_FIRM_ID:
        return out
    path = out.get("local_file") or out.get("local_pdf") or out.get("canonical_file") or ""
    if not is_sec_filing_relpath(path):
        return out
    full = ROOT / path
    if not full.exists():
        return out
    form = out.get("form") or form_from_filing_path(full) or "SC 13D"
    text = _read_filing_text(full)
    analysis = analyze_sec_filing(form, text)
    if analysis.get("firm_id") == UNRESOLVED_FIRM_ID:
        out["title"] = build_activist_title(
            analysis,
            form,
            ticker=ticker,
            report_date=out.get("report_date"),
        )
        return out
    out.update(
        {
            "firm_id": analysis.get("firm_id"),
            "firm_name": analysis.get("firm_name"),
            "confidence": analysis.get("confidence"),
            "filer_resolution": analysis.get("filer_resolution"),
            "reporting_persons": analysis.get("reporting_persons") or [],
            "title": build_activist_title(
                analysis,
                form,
                ticker=ticker,
                report_date=out.get("report_date"),
            ),
        }
    )
    return out


def merge_reports_by_local_file(reports: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    passthrough: list[dict] = []
    for report in reports:
        path = report.get("canonical_file") or report.get("local_file") or report.get("local_pdf")
        if not path:
            passthrough.append(report)
            continue
        existing = merged.get(path)
        if not existing:
            merged[path] = report
            continue
        existing_score = bool(existing.get("report_date")) + bool(existing.get("title"))
        report_score = bool(report.get("report_date")) + bool(report.get("title"))
        if report_score >= existing_score:
            merged[path] = {**existing, **report}
    return passthrough + list(merged.values())


def _duplicate_stem_counts(all_reports: list[tuple[str, dict]]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for ticker, report in all_reports:
        ref, _, _ = resolve_report_file(report)
        stem = Path(ref or report.get("local_file") or "").name
        if not stem:
            continue
        counts[(report.get("firm_id") or "", stem)] += 1
    return counts


def build_feed(*, prune_indexes: bool = True, link_check: bool | None = None) -> dict:
    tickers = portfolio_tickers()
    if prune_indexes:
        pruned = sum(prune_ghost_index_entries(ticker) for ticker in tickers)
        if pruned:
            print(f"Pruned {pruned} ghost activist index entries")
    else:
        pruned = 0

    all_reports: list[tuple[str, dict]] = []
    per_ticker_reports: dict[str, list[dict]] = {}

    for ticker in tickers:
        index = load_ticker_index(ticker)
        reports = merge_reports_by_local_file(
            [enrich_report_metadata(r) for r in (index.get("reports") or [])]
        )
        sr_dir = ROOT / ticker / "third-party-analyses" / "short_reports"
        indexed_paths = {
            str(r.get("local_file") or "").replace("\\", "/")
            for r in reports
            if r.get("source") == "short_reports_md"
        }
        if sr_dir.is_dir():
            for md in sorted(sr_dir.glob("*.md")):
                rel = str(md.relative_to(ROOT)).replace("\\", "/")
                if rel in indexed_paths:
                    continue
                reports.append(enrich_report_metadata(short_md_report_entry(md, ticker=ticker)))
        per_ticker_reports[ticker] = reports
        for report in reports:
            all_reports.append((ticker, report))

    duplicate_counts = _duplicate_stem_counts(all_reports)

    feed_rows: list[dict] = []
    summary = {
        "portfolio_hits": 0,
        "long_count": 0,
        "short_count": 0,
        "tickers_with_hits": 0,
        "unreconciled_count": 0,
        "passive_excluded_count": 0,
        "unresolved_filer_count": 0,
        "missing_date_count": 0,
        "missing_file_count": 0,
        "weak_match_count": 0,
        "ghost_pruned_count": pruned,
        "signal_count": 0,
        "context_count": 0,
        "noise_count": 0,
        "body_unverified_count": 0,
        "broken_link_count": 0,
        "triage_auto_signal": 0,
        "triage_auto_context": 0,
        "triage_auto_passive": 0,
        "triage_auto_noise": 0,
        "triage_human_review": 0,
    }
    per_ticker: dict[str, dict] = {}

    for ticker in tickers:
        reports = per_ticker_reports.get(ticker) or []
        visible = [
            enrich_filer_metadata(r, ticker=ticker) if r.get("firm_id") == UNRESOLVED_FIRM_ID else r
            for r in reports
            if feed_eligible(r)
        ]
        summary["passive_excluded_count"] += sum(
            1 for r in reports if r.get("filing_class") == "passive_13g" or r.get("include_in_feed") is False
        )
        if not visible:
            per_ticker[ticker] = {
                "long_count": 0,
                "short_count": 0,
                "latest": None,
                "has_unreconciled": False,
            }
            continue
        long_count = sum(1 for r in visible if r.get("side") == "long")
        short_count = sum(1 for r in visible if r.get("side") == "short")
        unreconciled = any(r.get("triage_verdict") == "human_review" for r in visible)
        latest = max(visible, key=lambda r: r.get("report_date") or "")
        per_ticker[ticker] = {
            "long_count": long_count,
            "short_count": short_count,
            "latest": {
                "firm_id": latest.get("firm_id"),
                "firm_name": latest.get("firm_name") or firm_name(latest.get("firm_id") or ""),
                "date": latest.get("report_date"),
                "side": latest.get("side"),
                "title": latest.get("title"),
            },
            "has_unreconciled": unreconciled,
        }
        summary["portfolio_hits"] += len(visible)
        summary["long_count"] += long_count
        summary["short_count"] += short_count
        summary["tickers_with_hits"] += 1
        if unreconciled:
            summary["unreconciled_count"] += 1
        for report in visible:
            file_ref, local_is_pdf, file_exists = resolve_report_file(report)
            match_reason = report.get("match_reason") or ""
            stem = Path(file_ref or report.get("local_file") or "").name
            dup_key = (report.get("firm_id") or "", stem)
            weak_match = duplicate_counts.get(dup_key, 0) >= WEAK_MATCH_TICKER_THRESHOLD or match_reason.startswith(
                "alias:"
            )
            if not file_exists:
                summary["missing_file_count"] += 1
            if weak_match:
                summary["weak_match_count"] += 1
            stake_percent = report.get("stake_percent")
            if stake_percent is None and report.get("source") == "sec_edgar" and file_exists:
                stake_percent = stake_for_filing(file_ref)
            row = {
                "ticker": ticker,
                "firm_id": report.get("firm_id"),
                "firm_name": report.get("firm_name") or firm_name(report.get("firm_id") or ""),
                "side": report.get("side"),
                "report_date": report.get("report_date"),
                "title": report.get("title"),
                "source": report.get("source"),
                "source_url": report.get("source_url"),
                "local_file": file_ref or report.get("local_file"),
                "local_pdf": report.get("local_pdf") if local_is_pdf else None,
                "canonical_file": report.get("canonical_file") or file_ref,
                "local_is_pdf": local_is_pdf,
                "file_exists": file_exists,
                "github_url": github_blob(file_ref) if file_exists and file_ref else None,
                "status": report.get("status"),
                "tier": report.get("tier", "context"),
                "confidence": report.get("confidence"),
                "match_reason": match_reason or None,
                "match_confidence": report.get("match_confidence"),
                "weak_match": weak_match,
                "body_verified": report.get("body_verified"),
                "body_match_reason": report.get("body_match_reason"),
                "stake_percent": stake_percent,
                "form": report.get("form"),
                "filing_class": report.get("filing_class"),
                "milly_verdict": report.get("milly_verdict"),
                "date_source": report.get("date_source"),
                "date_precision": report.get("date_precision"),
                "filer_resolution": report.get("filer_resolution"),
                "reporting_persons": report.get("reporting_persons") or [],
                "needs_filer_review": report.get("firm_id") == "unknown_activist"
                or (report.get("confidence") or 1) < 0.7,
                "needs_file": not file_exists and bool(report.get("source_url")),
                "triage_verdict": report.get("triage_verdict"),
                "triage_rules": report.get("triage_rules") or [],
                "materiality_floor": report.get("materiality_floor"),
                "campaign_freshness_floor": report.get("campaign_freshness_floor"),
                "campaign_group_size": report.get("campaign_group_size"),
            }
            if not row["report_date"]:
                summary["missing_date_count"] += 1
            if row["needs_filer_review"]:
                summary["unresolved_filer_count"] += 1
            feed_rows.append(row)

    feed_rows = dedupe_proxy_amendments(feed_rows)

    registry = load_json(PORTFOLIO_REGISTRY, {})
    holdings = set((registry.get("holdings") or {}).keys())
    watchlist = set((registry.get("watchlist") or {}).keys())

    link_health = check_links(
        [r["source_url"] for r in feed_rows if r.get("source_url")],
        enabled=link_check,
    )
    scored_rows: list[dict] = []
    for row in feed_rows:
        health = link_health.get(row.get("source_url") or "") or {}
        row["source_url_ok"] = health.get("ok")
        row["source_url_status"] = health.get("status")
        if row.get("file_exists") is False and (not row.get("source_url") or row.get("source_url_ok") is False):
            # No local copy and no working publisher link: nothing to show.
            summary["broken_link_count"] += 1
            continue
        score, _components = materiality_score(
            row,
            in_holdings=row.get("ticker") in holdings,
            in_watchlist=row.get("ticker") in watchlist,
        )
        row["materiality"] = score
        row["tier"] = materiality_tier(score, row)
        summary[f"{row['tier']}_count"] += 1
        verdict = row.get("triage_verdict")
        if verdict and verdict.startswith("auto_"):
            summary[f"triage_{verdict}"] = summary.get(f"triage_{verdict}", 0) + 1
        elif verdict == "human_review":
            summary["triage_human_review"] += 1
        if row.get("body_verified") is False:
            summary["body_unverified_count"] += 1
        scored_rows.append(row)
    feed_rows = scored_rows

    summary["portfolio_hits"] = len(feed_rows)
    summary["long_count"] = sum(1 for r in feed_rows if r.get("side") == "long")
    summary["short_count"] = sum(1 for r in feed_rows if r.get("side") == "short")
    summary["unreconciled_count"] = sum(
        1 for info in per_ticker.values() if info.get("has_unreconciled")
    )
    tier_total = summary["signal_count"] + summary["context_count"] + summary["noise_count"]
    if tier_total != len(feed_rows):
        raise RuntimeError(
            f"activist feed tier counts ({tier_total}) != feed rows ({len(feed_rows)})"
        )

    for info in per_ticker.values():
        info["signal_count"] = 0
        info["max_materiality"] = 0
    for row in feed_rows:
        info = per_ticker.get(row.get("ticker"))
        if not info:
            continue
        if row.get("tier") == "signal":
            info["signal_count"] += 1
        info["max_materiality"] = max(info["max_materiality"], row.get("materiality") or 0)

    global_scan = load_global_scan()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_scan": global_scan.get("generated_at"),
        "github_repo": GITHUB_REPO,
        "summary": summary,
        "by_ticker": per_ticker,
        "feed": feed_rows,
        "firms_active": len({r.get("firm_id") for r in feed_rows if r.get("firm_id")}),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build activist dashboard feed JSON.")
    parser.add_argument("--no-prune", action="store_true", help="Skip ghost index cleanup")
    parser.add_argument("--no-link-check", action="store_true", help="Skip HTTP link liveness checks")
    args = parser.parse_args()
    payload = build_feed(
        prune_indexes=not args.no_prune,
        link_check=False if args.no_link_check else None,
    )
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({payload['summary']['portfolio_hits']} feed reports, "
        f"{payload['summary']['signal_count']} signal / "
        f"{payload['summary']['context_count']} context / "
        f"{payload['summary']['noise_count']} noise, "
        f"{payload['summary']['tickers_with_hits']} tickers, "
        f"{payload['summary']['passive_excluded_count']} passive excluded, "
        f"{payload['summary']['unresolved_filer_count']} unresolved filers, "
        f"{payload['summary']['missing_date_count']} missing dates, "
        f"{payload['summary']['missing_file_count']} missing files, "
        f"{payload['summary']['broken_link_count']} broken links dropped, "
        f"{payload['summary']['weak_match_count']} weak matches)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
