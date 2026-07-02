#!/usr/bin/env python3
"""Build dashboard/data/activist_feed.json from per-ticker activist indexes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from activist_common import (
    firm_name,
    load_global_scan,
    load_ticker_index,
    portfolio_tickers,
)
from activist_date_parse import normalize_partial_date, parse_date_from_stem
from sec_filer_parse import (
    UNRESOLVED_FIRM_ID,
    analyze_sec_filing,
    build_activist_title,
    form_from_filing_path,
    is_sec_filing_relpath,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "activist_feed.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"
PROXY_DEDUP_FORMS = frozenset({"DFAN14A", "DEFC14A", "PREC14A"})
DEDUP_WINDOW_DAYS = 7


def github_blob(path: str | None) -> str | None:
    if not path:
        return None
    return f"https://github.com/{GITHUB_REPO}/blob/main/{path.replace(chr(92), '/')}"


def feed_eligible(report: dict) -> bool:
    if report.get("include_in_feed") is False:
        return False
    if report.get("filing_class") == "passive_13g":
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
        path = out.get("local_file") or out.get("local_pdf") or ""
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


def enrich_filer_metadata(report: dict, *, ticker: str) -> dict:
    out = enrich_report_metadata(report)
    if out.get("firm_id") != UNRESOLVED_FIRM_ID:
        return out
    path = out.get("local_file") or out.get("local_pdf") or ""
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
        path = report.get("local_file") or report.get("local_pdf")
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


def build_feed() -> dict:
    tickers = portfolio_tickers()
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
    }
    per_ticker: dict[str, dict] = {}

    for ticker in tickers:
        index = load_ticker_index(ticker)
        reports = merge_reports_by_local_file(
            [enrich_report_metadata(r) for r in (index.get("reports") or [])]
        )
        sr_dir = ROOT / ticker / "third-party-analyses" / "short_reports"
        if sr_dir.is_dir():
            for md in sorted(sr_dir.glob("*.md")):
                firm_id = md.stem.split("_")[0] if "_" in md.stem else md.stem
                raw_date = md.stem.split("_")[-1] if "_" in md.stem else ""
                reports.append(
                    enrich_report_metadata(
                        {
                            "firm_id": firm_id,
                            "firm_name": firm_name(firm_id),
                            "side": "short",
                            "report_date": raw_date,
                            "title": md.stem.replace("_", " "),
                            "source": "short_reports_md",
                            "local_file": str(md.relative_to(ROOT)).replace("\\", "/"),
                            "status": "cached",
                            "tier": "context",
                            "include_in_feed": True,
                            "filing_class": "short_markdown",
                        }
                    )
                )
        visible = [enrich_filer_metadata(r, ticker=ticker) if r.get("firm_id") == UNRESOLVED_FIRM_ID else r for r in reports if feed_eligible(r)]
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
        unreconciled = any(r.get("status") in ("new", "cached") for r in visible)
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
            local = report.get("local_pdf") or report.get("local_file")
            row = {
                "ticker": ticker,
                "firm_id": report.get("firm_id"),
                "firm_name": report.get("firm_name") or firm_name(report.get("firm_id") or ""),
                "side": report.get("side"),
                "report_date": report.get("report_date"),
                "title": report.get("title"),
                "source": report.get("source"),
                "source_url": report.get("source_url"),
                "local_pdf": local,
                "github_url": github_blob(local),
                "status": report.get("status"),
                "tier": report.get("tier", "context"),
                "confidence": report.get("confidence"),
                "form": report.get("form"),
                "filing_class": report.get("filing_class"),
                "milly_verdict": report.get("milly_verdict"),
                "date_source": report.get("date_source"),
                "date_precision": report.get("date_precision"),
                "filer_resolution": report.get("filer_resolution"),
                "reporting_persons": report.get("reporting_persons") or [],
                "needs_filer_review": report.get("firm_id") == "unknown_activist"
                or (report.get("confidence") or 1) < 0.7,
            }
            if not row["report_date"]:
                summary["missing_date_count"] += 1
            if row["needs_filer_review"]:
                summary["unresolved_filer_count"] += 1
            feed_rows.append(row)

    feed_rows = dedupe_proxy_amendments(feed_rows)
    summary["portfolio_hits"] = len(feed_rows)
    summary["long_count"] = sum(1 for r in feed_rows if r.get("side") == "long")
    summary["short_count"] = sum(1 for r in feed_rows if r.get("side") == "short")

    global_scan = load_global_scan()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_scan": global_scan.get("generated_at"),
        "summary": summary,
        "by_ticker": per_ticker,
        "feed": feed_rows,
        "firms_active": len({r.get("firm_id") for r in feed_rows if r.get("firm_id")}),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = build_feed()
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({payload['summary']['portfolio_hits']} feed reports, "
        f"{payload['summary']['tickers_with_hits']} tickers, "
        f"{payload['summary']['passive_excluded_count']} passive excluded, "
        f"{payload['summary']['unresolved_filer_count']} unresolved filers, "
        f"{payload['summary']['missing_date_count']} missing dates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
