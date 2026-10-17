#!/usr/bin/env python3
"""Structural and health checks for the reverse-split ledger and dashboard feed.

Structural errors (exit 1 unless --warn-only): unreadable JSONL, duplicate
event keys ``(ticker, ex_date, split_from, split_to)``, duplicate announcement
or FINRA keys, bad enums, a book run pointing at a missing source manifest, or
a break in the decisions hash chain.

Health (exit 1 only with --strict): the ledger manifest is older than ten days
(the Monday job stopped exporting) or ``dashboard/data/reverse_splits.json``
is more than 100 hours old (the nightly rebuild stopped). ``--warn-only``
always exits zero (the nightly rebuild lane; the Monday lane runs strict).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reverse_splits.config import DATA_DIR, REPO_ROOT  # noqa: E402
from reverse_splits.ledger import (  # noqa: E402
    ANNOUNCEMENT_OUTCOMES,
    COHORTS,
    DATE_QUALITIES,
    EVENT_OUTCOMES,
    EXCHANGE_CLASSES,
    event_key,
    latest_manifest,
    ledger_paths,
    load_jsonl,
    parse_stamp,
    read_json,
    sha256_file,
    verify_decision_chain,
)
from reverse_splits.utils import parse_date  # noqa: E402

DASHBOARD_PATH = REPO_ROOT / "dashboard" / "data" / "reverse_splits.json"
STALE_LEDGER_DAYS = 10
STALE_FEED_HOURS = 100


def _load(paths: dict[str, Path], name: str, errors: list[str]) -> list[dict]:
    try:
        return load_jsonl(paths[name])
    except ValueError as exc:
        errors.append(str(exc))
        return []


def _positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def structural_errors(ledger_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    paths = ledger_paths(ledger_dir)
    events = _load(paths, "events", errors)
    announcements = _load(paths, "announcements", errors)
    finra = _load(paths, "finra_short_interest", errors)
    runs = _load(paths, "book_runs", errors)
    manifests = _load(paths, "book_source_manifests", errors)
    decisions = _load(paths, "decisions", errors)

    seen_events: dict[tuple, int] = {}
    for index, row in enumerate(events):
        prefix = f"events[{index}]"
        if not row.get("ticker"):
            errors.append(f"{prefix}: ticker required")
        if parse_date(row.get("ex_date")) != str(row.get("ex_date") or "")[:10] or not row.get("ex_date"):
            errors.append(f"{prefix}: ex_date must be YYYY-MM-DD")
        if not _positive(row.get("split_from")) or not _positive(row.get("split_to")):
            errors.append(f"{prefix}: split_from and split_to must be positive numbers")
        key = event_key(row)
        if key in seen_events:
            errors.append(f"{prefix}: duplicate event key {key} (first at events[{seen_events[key]}])")
        else:
            seen_events[key] = index
        if row.get("exchange_class") not in EXCHANGE_CLASSES:
            errors.append(f"{prefix}: exchange_class must be one of {sorted(EXCHANGE_CLASSES)}")
        if row.get("cohort") is not None and row.get("cohort") not in COHORTS:
            errors.append(f"{prefix}: cohort must be one of {sorted(COHORTS)} or null")
        if (row.get("outcome") or "effective") not in EVENT_OUTCOMES:
            errors.append(f"{prefix}: outcome must be one of {sorted(EVENT_OUTCOMES)}")
        if row.get("date_quality") is not None and row.get("date_quality") not in DATE_QUALITIES:
            errors.append(f"{prefix}: date_quality must be one of {sorted(DATE_QUALITIES)} or null")

    seen_announcements: dict[tuple, int] = {}
    for index, row in enumerate(announcements):
        prefix = f"announcements[{index}]"
        if not row.get("ticker"):
            errors.append(f"{prefix}: ticker required")
        if not row.get("announce_date") or parse_date(row.get("announce_date")) != str(row.get("announce_date"))[:10]:
            errors.append(f"{prefix}: announce_date must be YYYY-MM-DD")
        if not row.get("accession"):
            errors.append(f"{prefix}: accession required (the filing that produced the row)")
        if (row.get("outcome") or "announced_only") not in ANNOUNCEMENT_OUTCOMES:
            errors.append(f"{prefix}: outcome must be one of {sorted(ANNOUNCEMENT_OUTCOMES)}")
        if row.get("exchange_class") not in EXCHANGE_CLASSES:
            errors.append(f"{prefix}: exchange_class must be one of {sorted(EXCHANGE_CLASSES)}")
        key = (str(row.get("ticker") or ""), str(row.get("ex_date") or row.get("announce_date") or "")[:10])
        if key in seen_announcements:
            errors.append(f"{prefix}: duplicate announcement key {key} (first at announcements[{seen_announcements[key]}])")
        else:
            seen_announcements[key] = index

    seen_finra: set[tuple] = set()
    for index, row in enumerate(finra):
        prefix = f"finra_short_interest[{index}]"
        if not row.get("ticker") or not parse_date(row.get("settlement_date")):
            errors.append(f"{prefix}: ticker and settlement_date required")
        key = (str(row.get("ticker")), str(row.get("settlement_date"))[:10])
        if key in seen_finra:
            errors.append(f"{prefix}: duplicate finra key {key}")
        seen_finra.add(key)

    manifest_hashes = {str(m.get("sha256")) for m in manifests}
    seen_runs: set[int] = set()
    for index, row in enumerate(runs):
        prefix = f"book_runs[{index}]"
        try:
            run_id = int(row.get("id"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}: integer id required")
            continue
        if run_id in seen_runs:
            errors.append(f"{prefix}: duplicate run id {run_id}")
        seen_runs.add(run_id)
        if not row.get("label"):
            errors.append(f"{prefix}: label required")
        if not isinstance(row.get("funnel"), list):
            errors.append(f"{prefix}: funnel list required")
        digest = row.get("source_manifest_sha256")
        if digest and digest not in manifest_hashes:
            errors.append(f"{prefix}: source manifest {digest[:12]} missing from book_source_manifests.jsonl")

    errors.extend(verify_decision_chain(decisions))
    summary = read_json(paths['manifest'].parent / 'expansion_summary.json',None)
    if summary is not None:
        expanded_path=paths['manifest'].parent/'expansion_events.jsonl'
        try:
            expanded=load_jsonl(expanded_path)
            ids=[r.get('event_id') for r in expanded]
            if len(set(ids))!=len(ids) or any(not i for i in ids):
                errors.append('expansion: event identities missing or duplicated')
            if len(expanded)!=summary.get('counts',{}).get('discovered_events'):
                errors.append('expansion: catalogue count differs from summary')
            if summary.get('counts',{}).get('complete_verified_price_paths',0)>summary.get('counts',{}).get('verified_actions',0):
                errors.append('expansion: complete paths exceed verified actions')
            accounts=summary.get('accounts',[])
            if len({r['case']['id'] for r in accounts})!=len(accounts):
                errors.append('expansion: repeated scenario identity')
            if any('gross_short_return' in o for r in expanded for o in r.get('outcomes',[])):
                errors.append('expansion: individual licensed price returns must remain local')
            root=paths['manifest'].parent.resolve()
            manifest=read_json(root/'expansion_manifest.json',{})
            if manifest.get('run_id')!=summary.get('run_id'):
                errors.append('expansion: publication manifest does not identify the summary run')
            for part in manifest.get('files',[]):
                target=(root/part['path']).resolve()
                if not target.is_relative_to(root) or sha256_file(target)!=part['sha256']:
                    errors.append('expansion: publication source missing or changed: '+part['path'])
        except (ValueError,KeyError,TypeError) as exc:
            errors.append('expansion: invalid derived ledger: '+str(exc))
    errors.extend(edge_v3_errors(paths["manifest"].parent))
    try:
        from reverse_splits.free_evidence import audit_publication
        errors.extend(audit_publication(paths["manifest"].parent))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors.append("Free evidence publication is invalid: " + str(exc))
    try:
        from reverse_splits.calmar_validation import audit_publication as audit_calmar
        errors.extend(audit_calmar(paths["manifest"].parent))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors.append("Calmar publication is invalid: " + str(exc))
    try:
        from reverse_splits.coverage_research import audit_artifacts
        errors.extend(audit_artifacts(paths["manifest"].parent))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors.append("Expanded coverage publication is invalid: " + str(exc))
    return errors


def edge_v3_errors(root: Path) -> list[str]:
    """Optional research publication must bind summary and policy audits."""
    manifest_path = root / "net_edge_manifest_v3.json"
    if not manifest_path.exists(): return []
    errors = []
    try:
        manifest = read_json(manifest_path)
        summary_path = root / "net_edge_research_v3.json"
        if sha256_file(summary_path) != manifest["summary_sha256"]:
            errors.append("RSI-3.0: summary hash mismatch")
        summary = read_json(summary_path)
        if summary.get("schema_version") != "shorts_net_edge.v3" or not summary.get("research_only") or summary.get("authority") != "none":
            errors.append("RSI-3.0: invalid research contract")
        ids = [r["id"] for r in summary["cases"]]
        if len(ids) != len(set(ids)) or summary["primary_case"] not in ids:
            errors.append("RSI-3.0: case identifiers do not reconcile")
        for row in summary["cases"]:
            if not row["performance_valid"] and (row["net_pnl"] is not None or row["ending_equity"] is not None):
                errors.append("RSI-3.0: invalid scenario reports performance")
        for group, spec in summary["audit_files"].items():
            target = root / "net_edge_audits_v3" / (group+".json")
            if spec["url"] != "data/net_edge_audits_v3/"+group+".json" or not target.resolve().is_relative_to(root.resolve()) or sha256_file(target) != spec["sha256"]:
                errors.append("RSI-3.0: policy audit hash mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"RSI-3.0: publication incomplete: {exc}")
    return errors


def health(
    today: date | None = None,
    *,
    ledger_dir: Path | None = None,
    dashboard_path: Path | None = None,
    check_dashboard: bool = True,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    manifest = latest_manifest(ledger_dir)
    problems: list[str] = []
    status = "healthy"
    exported = parse_stamp(manifest.get("exported_at"))
    if exported is None:
        problems.append("ledger_manifest.json missing or unstamped")
        status = "unhealthy"
    else:
        age_days = (now - exported).total_seconds() / 86400.0
        if age_days > STALE_LEDGER_DAYS:
            problems.append(f"ledger exported {age_days:.0f} days ago (limit {STALE_LEDGER_DAYS})")
            status = "unhealthy"
    if manifest and manifest.get("decisions_chain_valid") is False:
        problems.append("decisions hash chain was invalid at export")
        status = "unhealthy"
    if check_dashboard:
        target = dashboard_path or DASHBOARD_PATH
        feed = read_json(target, {}) or {}
        stamp = feed.get("generated_at")
        if not stamp:
            problems.append(f"{Path(target).name} missing or unstamped")
            status = "unhealthy"
        else:
            generated = parse_stamp(stamp)
            if generated is None:
                problems.append(f"{Path(target).name} generated_at unparseable")
                status = "unhealthy"
            else:
                age_h = (now - generated).total_seconds() / 3600.0
                if age_h > STALE_FEED_HOURS:
                    problems.append(f"{Path(target).name} is {age_h:.0f}h old (limit {STALE_FEED_HOURS}h)")
                    status = "unhealthy"
    return {
        "status": status,
        "structural_errors": structural_errors(ledger_dir),
        "problems": problems,
        "ledger_exported_at": manifest.get("exported_at"),
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="fail on an unhealthy feed as well")
    parser.add_argument("--warn-only", action="store_true", help="never fail")
    parser.add_argument("--ledger-dir", type=Path, default=None, help=f"default {DATA_DIR}")
    parser.add_argument("--dashboard", type=Path, default=None, help=f"default {DASHBOARD_PATH}")
    args = parser.parse_args(argv)
    report = health(ledger_dir=args.ledger_dir, dashboard_path=args.dashboard)
    for err in report["structural_errors"]:
        print(f"ERROR {err}")
    for problem in report["problems"]:
        print(f"WARN  {problem}")
    paths = ledger_paths(args.ledger_dir)
    counts = {name: len(load_jsonl(paths[name])) for name in ("events", "announcements", "decisions")}
    print(
        f"reverse_splits: status={report['status']} structural_errors={len(report['structural_errors'])} "
        f"events={counts['events']} announcements={counts['announcements']} decisions={counts['decisions']} "
        f"ledger_exported_at={report['ledger_exported_at']}"
    )
    if args.warn_only:
        return 0
    if report["structural_errors"]:
        return 1
    if args.strict and report["status"] != "healthy":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
