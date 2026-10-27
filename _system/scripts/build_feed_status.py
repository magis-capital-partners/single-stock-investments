#!/usr/bin/env python3
"""Write dashboard/data/feed_status.json for the operator tabs.

Display catalog only. Lanes and P6 feeds stay in graph_sources.json. This
script does not add feeds to that registry and it does not dispatch heals.
The supervisor remains the only thing that retries a lane.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from dashboard_data_coverage import surface_coverage

ROOT = Path(__file__).resolve().parents[2]
OUT_REL = Path("dashboard/data/feed_status.json")
GRAPH_REL = Path("_system/graph/graph_sources.json")
RECEIPTS_REL = Path("_system/data/lane_receipts")
SUPERVISOR_REL = Path("_system/data/repository_health_supervisor.json")

# Must match supervise_repository_health.P6_FEED_LANES. A feed heals through
# that lane, so the page names the same owner the supervisor already uses.
FEED_LANES = {
    "criticality_summary": "data-pipeline-technicals",
    "technical_summary": "data-pipeline-technicals",
    "vol_metrics": "data-pipeline-technicals",
    "spx_surface": "data-pipeline-technicals",
    "warrant_monitor": "data-pipeline-warrant-discover",
    "separations": "data-pipeline-separation-discover",
    "buyback_radar": "data-pipeline-buyback-radar",
    "desk_briefs": "data-pipeline-intake-full",
    "reverse_splits": "data-pipeline-reverse-splits",
    "short_alpha": "data-pipeline-intake-full",
    "special_situations": "data-pipeline-intake-full",
    "market_risk_components_committed": "market-risk",
    "podcast_catalog": "podcasts",
    "capitulation_daily": "data-pipeline-technicals",
}

LABELS = {
    "missing": "Missing file",
    "unreadable": "Unreadable stamp",
    "stale": "Stale",
    "fresh": "Fresh",
    "degraded": "Review required",
    "empty": "Current, no actionable rows",
    "api": "Live API",
}

# Windows below are the producer cadence plus a grace period, matching
# dashboard/ui-format.js FEED_MAX_AGE_HOURS where that table already exists.
# File feeds registered in graph_sources data_feeds take their max age from
# that registry instead. Everything else uses the owning lane's freshness_hours.
_FLEX = (
    "Wait for the next Flex report. This page does not read the Gateway."
)
_SPX = (
    "When the snapshot is stopped, unknown, or older than its cadence, "
    "spx-0dte owns the next action. This page does not probe the Gateway."
)
_LS = (
    "When the snapshot is stopped, unknown, or older than its cadence, "
    "ls-algo owns the next action. This page does not probe the Gateway."
)
_INTAKE = "Nightly intake republishes this surface. This page does not dispatch that job."

# hash is the operator route. One hash may have several rows.
SURFACES: list[dict] = [
    {"id":"buyback-radar","label":"Buyback Radar","hash":"#/research/coverage",
     "lane":"data-pipeline-buyback-radar","kind":"file","data_feed":"buyback_radar",
     "path":"dashboard/data/buyback_manifest.json","stamp_fields":["generated_at"],
     "healer":"Data Pipeline daily buyback refresh; repair with heal-buyback-radar"},
    {
        "id": "portfolio",
        "label": "Portfolio",
        "hash": "#/portfolio/all/positions",
        "lane": "deploy",
        "kind": "api",
        "api": "/api/v2/portfolio/book",
        "stamp_field": "snapshot.as_of",
        "max_age_hours": 100,
        "healer": _FLEX,
    },
    {
        "id": "spx-0dte",
        "label": "SPX 0DTE",
        "hash": "#/strategies/spx-0dte/overview",
        "lane": "data-pipeline-technicals",
        "kind": "api",
        "api": "/api/v2/portfolio/strategies?producer=spx_0dte",
        "stamp_field": "as_of",
        "max_age_hours": 100,
        "healer": _SPX,
    },
    {
        "id": "spx-surface",
        "label": "SPX surface",
        "hash": "#/strategies/spx-0dte/overview",
        "lane": "data-pipeline-technicals",
        "kind": "file",
        "data_feed": "spx_surface",
    },
    {
        "id": "ls-algo",
        "label": "LS Algo",
        "hash": "#/strategies/ls-algo/overview",
        "lane": "ls-algo",
        "kind": "api",
        "api": "/api/v2/portfolio/strategies?producer=ls_risk",
        "stamp_field": "as_of",
        "max_age_hours": 100,
        "healer": _LS,
    },
    {
        "id": "darwin",
        "label": "Darwin Covered Call",
        "hash": "#/strategies/darwin/overview",
        "lane": "darwin-covered-call",
        "kind": "file",
        "path": "dashboard/data/darwin_cc.json",
        "stamp_fields": ["generated_at"],
        "max_age_hours": 96,
        "healer": (
            "darwin-covered-call.yml rebuilds the signal from Cboe delayed chains several times "
            "each weekday (build_darwin_covered_call.py). This page does not dispatch that job."
        ),
    },
    {
        "id": "coverage",
        "label": "Coverage",
        "hash": "#/research/coverage",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/core.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "technical-summary",
        "label": "Technical summary",
        "hash": "#/research/coverage",
        "lane": "data-pipeline-technicals",
        "kind": "file",
        "data_feed": "technical_summary",
    },
    {
        "id": "valuation",
        "label": "Decision Queue",
        "hash": "#/research/valuation",
        "lane": "valuation",
        "kind": "file",
        "path": "dashboard/data/core.json",
        "stamp_fields": ["generated_at"],
        "healer": (
            "The Power Zone valuation lane refreshes decision-grade routes. "
            "The live task list is /api/v1/valuation-tasks. When that API is down, "
            "this page keeps the static queue and shows its age."
        ),
    },
    {
        "id": "ideas-inbox",
        "label": "Ideas inbox",
        "hash": "#/ideas/all",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/core.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "short-alpha",
        "label": "Shorts",
        "hash": "#/ideas/short-alpha",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "data_feed": "short_alpha",
        "path": "dashboard/data/short_alpha.json",
        "stamp_fields": ["generated_at", "as_of"],
        "healer": _INTAKE,
    },
    {
        "id": "reverse-splits",
        "label": "Reverse splits",
        "hash": "#/ideas/short-alpha",
        "lane": "data-pipeline-reverse-splits",
        "kind": "file",
        "data_feed": "reverse_splits",
    },
    {
        "id": "desk-briefs",
        "label": "Desk briefs",
        "hash": "#/ideas/all",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "data_feed": "desk_briefs",
    },
    {
        "id": "warrants",
        "label": "Warrant contracts",
        "hash": "#/ideas/situations/warrants",
        "lane": "data-pipeline-warrant-discover",
        "kind": "file",
        "data_feed": "warrant_monitor",
    },
    {
        "id": "separations",
        "label": "Separations",
        "hash": "#/ideas/situations/split-offs",
        "lane": "data-pipeline-separation-discover",
        "kind": "file",
        "data_feed": "separations",
    },
    {
        "id": "special-situations",
        "label": "Special Situations",
        "hash": "#/ideas/situations",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "data_feed": "special_situations",
        "path": "dashboard/data/special_situations.json",
        "stamp_fields": ["generated_at"],
        "healer": "python _system/scripts/build_special_situations.py",
    },
    {
        "id": "nol",
        "label": "NOL screen",
        "hash": "#/ideas/nol",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/nol_screener.json",
        "stamp_fields": ["built_at"],
        "actionable_flag": "is_actionable",
        "healer": _INTAKE,
    },
    {
        "id": "banks",
        "label": "Advantaged banks",
        "hash": "#/ideas/banks",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/advantaged_banks_screener.json",
        "stamp_fields": ["built_at"],
        "actionable_flag": "is_low_cost",
        "healer": _INTAKE,
    },
    {
        "id": "rock",
        "label": "Aggregates",
        "hash": "#/ideas/rock",
        "lane": "aggregates-screener",
        "kind": "file",
        "path": "dashboard/data/rock_aggregates_screener.json",
        "stamp_fields": ["generated_at"],
        "actionable_flag": None,
        "healer": "Aggregates Screener daily source refresh; repair with heal-aggregates",
    },
    {
        "id": "insights-events",
        "label": "Signals and synthesis",
        "hash": "#/insights/overview",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/insights/events.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "managers-13f",
        "label": "13F managers",
        "hash": "#/insights/investors/directory",
        "lane": "data-pipeline-thirteen-f",
        "kind": "file",
        "path": "dashboard/data/fund_holdings_summary.json",
        "stamp_fields": ["generated_at"],
        "max_age_hours": 54,
        "healer": (
            "The 13:29 UTC data-pipeline thirteen-f job refreshes filings. "
            "This page does not dispatch that job."
        ),
    },
    {
        "id": "activist",
        "label": "Activism",
        "hash": "#/insights/activism",
        "lane": "data-pipeline-activist",
        "kind": "file",
        "path": "dashboard/data/activist_feed.json",
        "stamp_fields": ["last_scan", "generated_at"],
        "max_age_hours": 48,
        "healer": (
            "The activist scan is the 06:00 UTC data-pipeline job. "
            "This page does not dispatch that job."
        ),
    },
    {
        "id": "data-health",
        "label": "Data status",
        "hash": "#/data-status",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/insights/manifest.json",
        "stamp_fields": ["generated_at"],
        "healer": (
            "This table is written with the dashboard build. "
            "It does not dispatch refreshes."
        ),
    },
    {
        "id": "letters",
        "label": "Letters",
        "hash": "#/insights/letters",
        "lane": "letters",
        "kind": "file",
        "path": "dashboard/data/insights/letters.json",
        "stamp_fields": ["generated_at"],
        "healer": "Letter backfill republishes the letters shard.",
    },
    {
        "id": "podcasts",
        "label": "Podcasts",
        "hash": "#/insights/podcasts",
        "lane": "podcasts",
        "kind": "file",
        "data_feed": "podcast_catalog",
    },
    {
        "id": "videos",
        "label": "Videos",
        "hash": "#/insights/videos",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/insights/videos.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "inflections",
        "label": "Inflections",
        "hash": "#/insights/inflections",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/kpi_trends.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "index-watch",
        "label": "Index Watch",
        "hash": "#/insights/index-watch",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/index_membership.json",
        "stamp_fields": ["generated", "generated_at"],
        "healer": (
            "Index membership is rebuilt by nightly intake "
            "(insights, activist, and full profiles). This page does not run that job."
        ),
    },
    {
        "id": "consensus",
        "label": "Consensus",
        "hash": "#/insights/investors/signals",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/insights/consensus.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "funds",
        "label": "Funds",
        "hash": "#/insights/funds",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/insights/registry.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "documents",
        "label": "PDF library",
        "hash": "#/insights/documents",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/document_catalog.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "memory",
        "label": "Research memory",
        "hash": "#/insights/memory",
        "lane": "data-pipeline-intake-full",
        "kind": "file",
        "path": "dashboard/data/research_memory.json",
        "stamp_fields": ["generated_at"],
        "healer": _INTAKE,
    },
    {
        "id": "market-risk",
        "label": "Market Risk",
        "hash": "#/market-risk",
        "lane": "market-risk",
        "kind": "api",
        "api": "/api/v1/market-risk/latest",
        "stamp_field": "generated_at",
        "healer": (
            "Live readings come from /api/v1/market-risk/latest. "
            "The committed fallback is market_risk_components.json."
        ),
    },
    {
        "id": "market-risk-components",
        "label": "Market risk components",
        "hash": "#/market-risk",
        "lane": "market-risk",
        "kind": "file",
        "data_feed": "market_risk_components_committed",
    },
    {
        "id": "criticality",
        "label": "Criticality summary",
        "hash": "#/market-risk",
        "lane": "data-pipeline-technicals",
        "kind": "file",
        "data_feed": "criticality_summary",
    },
    {
        "id": "vol-metrics",
        "label": "Volatility metrics",
        "hash": "#/market-risk",
        "lane": "data-pipeline-technicals",
        "kind": "file",
        "data_feed": "vol_metrics",
    },
    {
        "id": "capitulation",
        "label": "Capitulation",
        "hash": "#/market-risk",
        "lane": "data-pipeline-technicals",
        "kind": "file",
        "data_feed": "capitulation_daily",
    },
]


def surface_specs() -> list[dict]:
    return [dict(row) for row in SURFACES]


def nav_hashes(html: str) -> list[str]:
    """Primary and workspace subnav hashes, in document order, de-duplicated."""
    found: list[str] = []
    seen: set[str] = set()
    for tag in re.findall(r"<a\b[^>]*>", html):
        if not re.search(r'class="[^"]*\bview-tab\b', tag):
            continue
        match = re.search(r'href="(#/[^"]+)"', tag)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        found.append(match.group(1))
    return found


def parse_stamp(value) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime(int(text[0:4]), int(text[5:7]), int(text[8:10]), tzinfo=timezone.utc)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def classify_feed(
    exists: bool,
    stamp,
    max_age_hours,
    now: datetime | None = None,
    *,
    empty: bool = False,
) -> str:
    """missing, unreadable, and stale are three different states.

    A fresh file with nothing actionable is empty. A live API row is not
    classified here; the browser does that from the payload it actually loaded.
    """
    if not exists:
        return "missing"
    limit = None if max_age_hours is None else float(max_age_hours)
    if limit is None or limit <= 0:
        return "unreadable"
    parsed = parse_stamp(stamp)
    if parsed is None:
        return "unreadable"
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    age_hours = (moment - parsed).total_seconds() / 3600.0
    if age_hours > limit:
        return "stale"
    if empty:
        return "empty"
    return "fresh"


def feed_label(status: str) -> str:
    return LABELS.get(status, "Unknown")


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _dig(doc, path: str):
    current = doc
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (dict, list)) or current is None:
        return None
    return current


def _first_stamp(doc, fields: list[str]):
    for field in fields:
        value = _dig(doc, field)
        if parse_stamp(value) is not None:
            return value
    for field in fields:
        value = _dig(doc, field)
        if value not in (None, ""):
            return value
    return None


def _embedded_counts(doc, key: str, flag: str | None) -> tuple[bool, int]:
    """Return (published, actionable_count). Unpublished means the key is absent."""
    if not isinstance(doc, dict) or not isinstance(doc.get(key), dict):
        return False, 0
    block = doc[key]
    rows = block.get("rows") if isinstance(block.get("rows"), list) else []
    if flag:
        count = block.get("actionable_count")
        if isinstance(count, int):
            return True, count
        return True, sum(1 for row in rows if isinstance(row, dict) and row.get(flag))
    return True, len(rows)


def _lane_names(config: dict) -> dict[str, dict]:
    return {
        str(lane.get("name")): lane
        for lane in (config.get("lanes") or [])
        if isinstance(lane, dict) and lane.get("name")
    }


def _open_issue_lanes(state: dict) -> set[str]:
    found: set[str] = set()
    issues = state.get("issues") or {}
    rows = issues.values() if isinstance(issues, dict) else issues if isinstance(issues, list) else []
    for issue in rows:
        if not isinstance(issue, dict) or issue.get("state") != "open":
            continue
        lanes = issue.get("lanes") or {}
        if isinstance(lanes, dict):
            found.update(str(name) for name in lanes)
    return found


def _supervisor_clause(lane: str, lane_state: dict, open_lanes: set[str]) -> str:
    if lane in open_lanes or lane_state.get("persistent") or lane_state.get("held"):
        return "A lane-failure issue is open."
    if lane_state.get("stale"):
        return "The supervisor will retry this lane, at most three times a day."
    return ""


def _resolve_source(spec: dict, feeds: dict) -> dict:
    """Fill path, stamp fields, max age, and healer from data_feeds when registered."""
    resolved = dict(spec)
    feed_id = spec.get("data_feed")
    feed = feeds.get(feed_id) if feed_id else None
    if isinstance(feed, dict):
        resolved["path"] = feed.get("path") or resolved.get("path")
        stamp = feed.get("stamp_field") or "generated_at"
        resolved["stamp_fields"] = [stamp]
        resolved["max_age_hours"] = feed.get("max_age_hours")
        resolved["healer"] = feed.get("healer") or resolved.get("healer") or ""
        resolved["lane"] = FEED_LANES.get(feed_id) or resolved.get("lane")
    return resolved


def build_feed_status(root: Path | None = None, now: datetime | None = None) -> dict:
    root = root or ROOT
    moment = now or datetime.now(timezone.utc)
    config = _load_json(root / GRAPH_REL) or {}
    lanes = _lane_names(config)
    feeds = config.get("data_feeds") or {}
    if not isinstance(feeds, dict):
        feeds = {}
    supervisor = _load_json(root / SUPERVISOR_REL) or {}
    supervisor_lanes = supervisor.get("lanes") if isinstance(supervisor.get("lanes"), dict) else {}
    open_lanes = _open_issue_lanes(supervisor)
    cache: dict[str, object] = {}

    def load_rel(rel: str):
        if rel not in cache:
            path=root / rel
            cache[rel] = _load_json(path)
            if isinstance(cache[rel],dict) and cache[rel].get('private_snapshot') and rel.startswith('dashboard/'):
                # Read the verified archive in place; never hydrate private
                # content into public dashboard files just to inspect health.
                try:
                    from private_dashboard_assets import private_source
                    cache[rel]=_load_json(private_source(root/'dashboard',rel[len('dashboard/'):]))
                except (OSError,ValueError,RuntimeError,ImportError):
                    pass
        return cache[rel]

    surfaces = []
    for spec in SURFACES:
        resolved = _resolve_source(spec, feeds)
        lane = str(resolved.get("lane") or "")
        lane_row = lanes.get(lane) or {}
        max_age = resolved.get("max_age_hours")
        if max_age is None:
            max_age = lane_row.get("freshness_hours")
        healer = str(resolved.get("healer") or "")
        kind = resolved.get("kind") or "file"
        stamp = None
        exists = False
        empty = False
        artifact = resolved.get("path")
        coverage = None
        if kind == "api":
            exists = True
            status = "api"
        else:
            doc = load_rel(artifact) if artifact else None
            exists = doc is not None
            if exists and resolved.get("embedded_key"):
                published, actionable = _embedded_counts(
                    doc, resolved["embedded_key"], resolved.get("actionable_flag")
                )
                if not published:
                    exists = False
                else:
                    empty = actionable == 0
            elif exists and resolved.get('actionable_flag'):
                rows=doc.get('rows') or []
                empty=not any(row.get(resolved['actionable_flag']) for row in rows if isinstance(row,dict))
            if exists:
                stamp = _first_stamp(doc, list(resolved.get("stamp_fields") or ["generated_at"]))
            status = classify_feed(exists, stamp, max_age, moment, empty=empty and exists)
            coverage = surface_coverage(resolved['id'], doc) if exists else None
            if coverage and coverage['incomplete_rows'] and status in {'fresh','empty'}:
                status='degraded'
        if spec.get('id')=='rock' and exists and status in {'fresh','empty'} and (doc.get('coverage') or {}).get('failures'):
            status='degraded'
        if resolved.get("data_feed")=="buyback_radar" and exists and status in {"fresh","empty"} and doc.get("health")!="healthy":
            status="degraded"
        receipt_path = root / RECEIPTS_REL / f"{lane}.json"
        receipt = _load_json(receipt_path) if receipt_path.is_file() else None
        receipt_at = receipt.get("last_success_at") if isinstance(receipt, dict) else None
        lane_state = supervisor_lanes.get(lane) if isinstance(supervisor_lanes.get(lane), dict) else {}
        clause = _supervisor_clause(lane, lane_state, open_lanes)
        next_action = healer if not clause else f"{healer} {clause}".strip()
        if coverage and coverage['incomplete_rows']:
            next_action=f"{coverage['next_action']} {next_action}".strip()
        surfaces.append({
            "id": resolved["id"],
            "label": resolved.get("label") or resolved["id"],
            "hash": resolved.get("hash"),
            "kind": kind,
            "api": resolved.get("api"),
            "artifact": artifact,
            "stamp_field": (resolved.get("stamp_fields") or [resolved.get("stamp_field")])[0],
            "stamp": None if stamp is None else str(stamp),
            "max_age_hours": None if max_age is None else float(max_age),
            "exists": bool(exists) if kind != "api" else True,
            "status": status,
            "label_text": feed_label(status),
            "lane": lane,
            "lane_receipt_at": receipt_at,
            "healer": healer,
            "next_action": next_action,
            "coverage": coverage,
            "observation_dates": ({'borrow': (doc.get('borrow_meta') or {}).get('as_of'),
                                   'research':doc.get('as_of')}
                                  if kind!='api' and exists and resolved['id']=='short-alpha' else None),
        })
    return {
        "schema_version": "1",
        "generated_at": moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "surfaces": surfaces,
    }


def write_feed_status(root: Path | None = None, now: datetime | None = None) -> Path:
    root = root or ROOT
    payload = build_feed_status(root, now)
    path = root / OUT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path} ({len(payload['surfaces'])} surfaces)")
    return path


def main() -> None:
    write_feed_status()


if __name__ == "__main__":
    main()
