#!/usr/bin/env python3
"""Shard the dashboard payload into core.json + per-ticker / per-section files.

The SPA boots from ``dashboard/data/core.json`` (slim rows, summary, filters)
and lazy-fetches:

- ``dashboard/data/tickers/{TICKER}.json``  full ticker detail on row select
- ``dashboard/data/insights/{section}.json`` insights sub-tab shards
- existing standalone artifacts (``kpi_trends.json``, ``document_catalog.json``,
  ``research_memory.json``, ``index_membership.json``) on section open

``dashboard_data.json`` remains the pipeline contract for build scripts and
validators; the browser no longer downloads it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from reconcile_insights_event_summary import (
    is_publishable_manifest,
    reconciled_manifest,
    richer_manifest,
)

CORE_VERSION = 1

# Row fields only needed once a ticker is opened in the detail pane.
DETAIL_ONLY_FIELDS = (
    "download_script_path",
    "two_phase_watch",
    "insights",
    "insight_events",
    "letter_discussants",
    "dossier",
    "research_memory",
    "kpi_trends",
    "valuation_workbench",
    "lenses",
    "active_lenses",
    "silent_lens_count",
    "recent_files",
    "developments",
    "transcripts",
    "total_return_panel",
    "pricing_analysis",
    "compounder_monitor",
    "ssi_report",
    "properties",
    "links",
    "investment_committee",
    "human_review",
    "decision_summary",
    "classification_audit",
)

# Top-level payload keys that stay out of core.json (fetched lazily instead).
CORE_EXCLUDED_TOP_LEVEL = (
    "kpi_trends",
    "document_catalog",
    "activist_feed",
)

# Compact insight item fields kept in slim essential_insights entries.
_INSIGHT_ITEM_FIELDS = ("title", "summary", "source", "date", "quarter", "evidence_url")

# insights.json keys routed to per-section shard files.
INSIGHTS_SHARDS = {
    "letters": ("letter_index",),
    "events": ("events", "events_by_ticker"),
    "consensus": ("consensus",),
    "registry": ("fund_registry",),
    "profiles": ("fund_profiles",),
    "tickers": ("by_ticker", "ticker_discussants"),
    "podcasts": ("podcast_index", "podcast_by_show"),
    "videos": ("video_index", "video_by_channel"),
}

_SAFE_TICKER_RE = re.compile(r"[^A-Za-z0-9._-]")


def shard_filename(ticker: str) -> str:
    return _SAFE_TICKER_RE.sub("_", str(ticker)) + ".json"


def _dump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _compact_insight_item(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    return {k: item.get(k) for k in _INSIGHT_ITEM_FIELDS if item.get(k) is not None}


# component_valuation subfields the detail pane alone renders. Every one of
# these is already written in full to the per-ticker shard, and
# loadTickerDetail() does `Object.assign({}, row, full)` -- a shallow merge, so
# the shard's complete object replaces this slim one the moment a ticker is
# opened. Keeping them in core.json was pure duplication: 863 KB of the 6.01 MB
# boot payload, against a 6.0 MB budget core.json crossed on 2026-08-20.
#
# What stays is exactly what the holdings table needs before any ticker is
# opened: `status`, `total_equity_value_per_share` and `upside_downside_pct` are
# table sort keys (index.html sortKey 'component_valuation.*'), and
# `market_price_per_share` feeds the value-gap cell. Both other call sites
# (renderValuationStatusCell, renderLegacyComponentNote) only test the object
# for existence.
_COMPONENT_VALUATION_DETAIL_ONLY = (
    "economic_value",      # 561 KB -- renderComponentValuation only
    "components",          # 283 KB -- renderComponentValuation only
    "decision_rule",       #  16 KB -- renderComponentValuation only
    "review_status",       #   3 KB -- renderComponentValuation only
    "review_open_count",   #         -- rendered beside review_status
)

# The holdings table needs only the decision ledger's display and sort fields.
# The full contract proof, eligibility explanation, dated cash-flow schedule,
# and legacy audit remain available in the per-ticker shard once a row opens.
# Keeping the full object in core.json duplicates several kilobytes per ticker
# and makes the SPA pay that cost before the user has selected a security.
_VALUATION_DECISION_CORE_FIELDS = (
    "status",
    "proof_status",
    "model_level",
    "return_publishable",
    "provisional",
    "open_gap_count",
    "critical_gap_count",
    "method_profile",
    "primary_power_zone",
    "output_basis",
    "value_per_share",
    "margin_of_safety_pct",
    "upside_to_value_pct",
    "upside_downside_pct",
    "forward_return_at_price_pct",
    "forward_return_status",
    "forward_return_reason",
    "dates",
    "horizon_years",
    "price_per_share",
    "next_action",
    "next_gap_id",
    "rollout_wave",
    "in_validation_cohort",
)


def _slim_component_valuation(cv: dict) -> dict:
    """Drop the detail-pane schedule, keep the table's sort and display keys."""
    return {k: v for k, v in cv.items() if k not in _COMPONENT_VALUATION_DETAIL_ONLY}


def slim_valuation_tier(tier: dict | None) -> dict:
    """Keep only tier identity in the boot payload.

    Assignment evidence, promotion gates, and workflow policy are detail-pane
    governance context and remain in each ticker shard.
    """
    if not isinstance(tier, dict):
        return {}
    return {
        key: tier.get(key)
        for key in ("tier", "tier_id", "label")
        if tier.get(key) is not None
    }


def slim_valuation_decision(decision: dict | None) -> dict:
    """Keep pre-selection valuation fields used by table/filter rendering."""
    if not isinstance(decision, dict):
        return {}
    slim = {
        key: decision.get(key)
        for key in _VALUATION_DECISION_CORE_FIELDS
        if key in decision
    }
    tier = slim_valuation_tier(decision.get("universe_tier"))
    if tier:
        slim["universe_tier"] = tier
    return slim


def _slim_essential_insights(essential: dict) -> dict:
    slim = {
        k: v
        for k, v in essential.items()
        if k not in ("bullets", "owner", "latest", "bull", "bear")
    }
    bullets = essential.get("bullets")
    if isinstance(bullets, list) and bullets:
        first = _compact_insight_item(bullets[0])
        slim["bullets"] = [first] if first else []
    for key in ("owner", "latest"):
        compact = _compact_insight_item(essential.get(key))
        if compact:
            slim[key] = compact
    return slim


def slim_ticker_row(row: dict) -> dict:
    """Trim a full dashboard row down to what the holdings table needs."""
    slim = {k: v for k, v in row.items() if k not in DETAIL_ONLY_FIELDS}
    readiness = row.get("irr_readiness")
    if isinstance(readiness, dict):
        slim["irr_readiness"] = {k: readiness[k] for k in
            ("as_of", "status", "blocked_count", "diagnostic_math_complete", "work_group", "next_action") if k in readiness}
    slim.pop("return_claim_audit", None)
    essential = row.get("essential_insights")
    if isinstance(essential, dict):
        slim["essential_insights"] = _slim_essential_insights(essential)
    component_valuation = row.get("component_valuation")
    if isinstance(component_valuation, dict):
        slim["component_valuation"] = _slim_component_valuation(component_valuation)
    valuation_decision = slim_valuation_decision(row.get("valuation_decision"))
    if valuation_decision:
        slim["valuation_decision"] = valuation_decision
    valuation_tier = slim_valuation_tier(row.get("valuation_tier"))
    if valuation_tier:
        slim["valuation_tier"] = valuation_tier
    # KPI badge summary keeps the table's trend hints without the series.
    kpi = row.get("kpi_trends")
    if isinstance(kpi, dict):
        slim["kpi_trends"] = {
            "summary": kpi.get("summary"),
            "business_momentum": kpi.get("business_momentum"),
            "leadership_risk": kpi.get("leadership_risk"),
            "data_tier": kpi.get("data_tier"),
            "has_trend_data": kpi.get("has_trend_data"),
        }
    membership = row.get("index_membership")
    if isinstance(membership, dict):
        compact = dict(membership)
        if isinstance(compact.get("scorecards"), list):
            compact["scorecards"] = [
                {k: s.get(k) for k in ("index", "status", "distance", "rank") if k in s}
                for s in compact["scorecards"][:6]
                if isinstance(s, dict)
            ]
        if isinstance(compact.get("confirmed_events"), list):
            compact["confirmed_events"] = compact["confirmed_events"][:3]
        compact.pop("inputs_missing", None)
        # The holdings cell does not read this. The index page loads
        # index_membership.json. Leaving it on every core row pushed core.json
        # through the 6.0 MB boot budget (6.01-6.02 MB on the 2026-10-09..11
        # intake-full rebuilds).
        compact.pop("next_calendar_event", None)
        slim["index_membership"] = compact
    slim["detail_shard"] = f"data/tickers/{shard_filename(row.get('ticker', ''))}"
    return slim


def build_core_payload(payload: dict) -> dict:
    core = {
        k: v for k, v in payload.items() if k not in CORE_EXCLUDED_TOP_LEVEL
    }
    core["tickers"] = [slim_ticker_row(r) for r in payload.get("tickers") or []]
    core["core_version"] = CORE_VERSION
    core["shards"] = {
        "tickers_dir": "data/tickers/",
        "insights_dir": "data/insights/",
        "kpi_trends": "data/kpi_trends.json",
        "document_catalog": "data/document_catalog.json",
        "research_memory": "data/research_memory.json",
        "index_membership": "data/index_membership.json",
        "activist_feed": "data/activist_feed.json",
        "separations": "data/separations.json",
        "desk_briefs": "data/desk_briefs.json",
        "reverse_splits": "data/reverse_splits.json",
    }
    doc_catalog = payload.get("document_catalog")
    if isinstance(doc_catalog, dict):
        core["document_catalog_ref"] = {
            "path": "dashboard/data/document_catalog.json",
            "generated_at": doc_catalog.get("generated_at"),
            "document_count": len(doc_catalog.get("documents") or []),
        }
    kpi = payload.get("kpi_trends")
    if isinstance(kpi, dict):
        core["kpi_trends_ref"] = {
            "path": "dashboard/data/kpi_trends.json",
            "generated_at": kpi.get("generated_at"),
            "inflection_count": kpi.get("inflection_count", 0),
        }
    return core


def write_ticker_shards(payload: dict, data_dir: Path) -> int:
    tickers_dir = data_dir / "tickers"
    tickers_dir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for row in payload.get("tickers") or []:
        name = shard_filename(row.get("ticker", ""))
        (tickers_dir / name).write_text(_dump(row), encoding="utf-8")
        written.add(name)
    # Prune shards for tickers no longer in the universe.
    removed = 0
    for stale in tickers_dir.glob("*.json"):
        if stale.name not in written:
            stale.unlink()
            removed += 1
    if removed:
        print(f"Pruned {removed} stale ticker shard(s)")
    return len(written)


def _read_json_object(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _repo_insight_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "dashboard" / "data" / "insights"


def _git_manifest(spec: str) -> dict | None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "show", spec],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def recover_insight_manifest(insights_dir: Path) -> dict | None:
    """On-disk manifest, or the last publishable copy still in the git index.

    Conflict regeneration deletes the worktree file before the dashboard
    builder runs. Reading stage 2/3 puts that copy back. A temp directory
    outside this repo does not consult git, so tests cannot pick up main.
    """
    on_disk = _read_json_object(insights_dir / "manifest.json")
    best = on_disk if isinstance(on_disk, dict) else None
    try:
        insights_dir.resolve().relative_to(_repo_insight_dir().resolve())
    except ValueError:
        return best
    rel = "dashboard/data/insights/manifest.json"
    for spec in (f":2:{rel}", f":3:{rel}", f"HEAD:{rel}"):
        best = richer_manifest(best, _git_manifest(spec))
    return best


def merge_insight_shards(shard_dir: Path) -> dict | None:
    """Manifest metadata, overlaid with each shard's own keys.

    Alphabetical ``*.json`` merging let ``videos.json`` (last) replace
    ``generated_at``, and a deleted manifest disappeared entirely. Shard
    stamps stay on the shards.
    """
    manifest = recover_insight_manifest(shard_dir)
    merged: dict = dict(manifest) if isinstance(manifest, dict) else {}
    stamp = merged.get("generated_at")
    for name, keys in INSIGHTS_SHARDS.items():
        shard = _read_json_object(shard_dir / f"{name}.json")
        if not isinstance(shard, dict):
            continue
        for key in keys:
            if key in shard and shard[key] is not None:
                merged[key] = shard[key]
    if stamp is not None:
        merged["generated_at"] = stamp
    return merged or None


def _shard_payload(insights_doc: dict, insights_dir: Path, name: str, keys: tuple[str, ...], stamp) -> dict | None:
    """Rows this doc actually has. Missing keys must not null an existing shard."""
    existing = _read_json_object(insights_dir / f"{name}.json") or {}
    if any(key not in insights_doc or insights_doc[key] is None for key in keys):
        if not any(key in insights_doc and insights_doc[key] is not None for key in keys):
            return None
        if not existing:
            return None
        shard = {key: existing.get(key) for key in keys}
        for key in keys:
            if key in insights_doc and insights_doc[key] is not None:
                shard[key] = insights_doc[key]
    else:
        shard = {key: insights_doc[key] for key in keys}
    for extra in ("video_status_counts", "video_newest_published", "episode_count"):
        if extra not in shard and extra in existing and extra not in insights_doc:
            shard[extra] = existing[extra]
    if stamp is not None:
        shard["generated_at"] = stamp
    elif existing.get("generated_at"):
        shard["generated_at"] = existing["generated_at"]
    return shard


def write_insights_shards(insights_doc: dict | None, data_dir: Path) -> int:
    insights_dir = data_dir / "insights"
    insights_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(insights_doc, dict):
        return 0
    from refresh_research_integrity import reconcile_insight_payload
    insights_doc = reconcile_insight_payload(insights_doc)
    sharded_keys = {k for keys in INSIGHTS_SHARDS.values() for k in keys}
    existing = recover_insight_manifest(insights_dir)
    if is_publishable_manifest(insights_doc):
        base = dict(insights_doc)
    elif is_publishable_manifest(existing):
        # A partial rebuild (deleted manifest, video stamp only) keeps the
        # corpus and health already on disk or in the index.
        base = dict(existing)
        for key, value in insights_doc.items():
            # shards and the stamp belong to the publishable manifest. A
            # partial doc's copy of either one is how a stub erased
            # video_details and the intake timestamp.
            if key in sharded_keys or key in {"generated_at", "shards"} or value is None:
                continue
            base[key] = value
    else:
        base = None
        print(
            "refusing to write an insight manifest stub; no publishable manifest to keep",
            file=sys.stderr,
        )

    events = insights_doc.get("events") if isinstance(insights_doc.get("events"), list) else None
    if events is None:
        on_disk_events = _read_json_object(insights_dir / "events.json")
        if isinstance(on_disk_events, dict) and isinstance(on_disk_events.get("events"), list):
            events = on_disk_events["events"]
    if base is not None and isinstance(events, list):
        base = reconciled_manifest(base, events)

    count = 0
    if is_publishable_manifest(base):
        manifest = {k: v for k, v in base.items() if k not in sharded_keys}
        try:
            from check_media_analysis_freshness import note_observed_counts
            note_observed_counts(manifest)
        except Exception as exc:  # noqa: BLE001 - the shard must still publish if the clock cannot
            print(f"media analysis clock not updated: {exc}", file=sys.stderr)
        manifest["shards"] = {
            name: f"data/insights/{name}.json" for name in INSIGHTS_SHARDS
        }
        previous_shards = base.get("shards") if isinstance(base.get("shards"), dict) else {}
        for key, value in previous_shards.items():
            manifest["shards"].setdefault(key, value)
        (insights_dir / "manifest.json").write_text(_dump(manifest), encoding="utf-8")
        count += 1
        stamp = base.get("generated_at")
    else:
        stamp = None

    # Every shard carries the parent doc's stamp. Without it a shard cannot be
    # registered as a P6 data feed at all: podcasts.json held 3,561 episodes and
    # no date, so nothing could tell that its newest episode was 2026-07-28 and
    # the pipeline had not run since. A feed with no stamp cannot go stale --
    # it can only be noticed by a human reading the page.
    for name, keys in INSIGHTS_SHARDS.items():
        shard = _shard_payload(insights_doc, insights_dir, name, keys, stamp)
        if shard is None:
            continue
        (insights_dir / f"{name}.json").write_text(_dump(shard), encoding="utf-8")
        count += 1
    return count


# These already have their own files. Embedding them in dashboard_data.json
# pushed that gitignored monolith through GitHub's 100MB hard limit
# (100.4-100.5MB on 2026-10-09, 10-10, and 10-11) and failed intake-full after
# the rebuild had otherwise finished. core.json already omits them.
STANDALONE_EMBED_KEYS = (
    "kpi_trends",
    "activist_feed",
    "document_catalog",
)


def release_standalone_embeds(payload: dict) -> list[str]:
    """Replace bulky standalone blobs with path refs. Mutates payload.

    Call after write_shards, which still needs the full objects to build
    core refs.
    """
    removed: list[str] = []
    catalog = payload.get("document_catalog")
    if isinstance(catalog, dict):
        payload["document_catalog_ref"] = {
            "path": "dashboard/data/document_catalog.json",
            "generated_at": catalog.get("generated_at"),
            "document_count": len(catalog.get("documents") or []),
        }
        payload.pop("document_catalog", None)
        removed.append("document_catalog")
    kpi = payload.get("kpi_trends")
    if isinstance(kpi, dict):
        payload.setdefault(
            "kpi_trends_ref",
            {
                "path": "dashboard/data/kpi_trends.json",
                "generated_at": kpi.get("generated_at"),
                "inflection_count": kpi.get("inflection_count", 0),
            },
        )
        payload.pop("kpi_trends", None)
        removed.append("kpi_trends")
    feed = payload.get("activist_feed")
    if isinstance(feed, dict):
        payload["activist_feed_ref"] = {
            "path": "dashboard/data/activist_feed.json",
            "generated_at": feed.get("generated_at"),
        }
        payload.pop("activist_feed", None)
        removed.append("activist_feed")
    return removed


def write_shards(payload: dict, insights_doc: dict | None, data_dir: Path) -> dict:
    # Direct callers can bypass build_dashboard_data.main(), and its monolith
    # may already have been replaced. Compare against the still-published
    # shards before writing or pruning any asset.
    core_path = data_dir / "core.json"
    if core_path.exists():
        from build_dashboard_data import (  # late import: the builder uses this writer
            refuse_infra_collapse,
            refuse_research_collapse,
            refuse_valuation_collapse,
        )

        prior = json.loads(core_path.read_text(encoding="utf-8"))
        prior_rows = {
            str(row["ticker"]): dict(row)
            for row in prior.get("tickers") or [] if row.get("ticker")
        }
        for ticker, row in prior_rows.items():
            path = data_dir / "tickers" / shard_filename(ticker)
            if path.exists():
                row.update(json.loads(path.read_text(encoding="utf-8")))
        refuse_infra_collapse(payload, prior_rows)
        refuse_research_collapse(payload, prior_rows)
        refuse_valuation_collapse(payload, prior_rows)
    from research_integrity import gate_return_claims
    for row in payload.get("tickers") or []:
        gate_return_claims(row)
    companies = [r["irr_readiness"] for r in payload.get("tickers") or [] if (r.get("irr_readiness") or {}).get("requirements")]
    if companies and len(companies) == len(payload.get("tickers") or []):
        from datetime import date
        from build_irr_readiness import report_for_companies
        report = report_for_companies(companies, date.fromisoformat(companies[0]["as_of"]))
        (data_dir / "irr_readiness.json").write_text(_dump(report), encoding="utf-8")
        payload.setdefault("summary", {})["irr_readiness"] = report["summary"]
    core = build_core_payload(payload)
    core_path.write_text(_dump(core), encoding="utf-8")
    ticker_count = write_ticker_shards(payload, data_dir)
    insight_count = write_insights_shards(insights_doc, data_dir)
    core_mb = core_path.stat().st_size / 1e6
    print(
        f"Wrote {core_path} ({core_mb:.2f} MB), {ticker_count} ticker shard(s), "
        f"{insight_count} insights shard(s)"
    )
    return {
        "core_bytes": core_path.stat().st_size,
        "ticker_shards": ticker_count,
        "insights_shards": insight_count,
    }


def refresh_buyback_projection(folder=None):
    """Refresh canonical buyback fields while preserving all other shard contents."""
    from build_buyback_radar import load_companies_index, shard_buyback
    from atomic_io import write_json_if_changed, attach_envelope
    index=load_companies_index()
    if not index:raise ValueError("Verified buyback snapshot unavailable")
    folder=Path(folder) if folder else Path(__file__).resolve().parents[2] / "dashboard/data/tickers"
    updated=0
    for path in sorted(folder.glob("*.json")):
        try:doc=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        ticker=doc.get("ticker") or path.stem
        row=index.get(ticker)
        doc["buyback"]=shard_buyback(row) if row else {"schema_version":"buyback.v2","ticker":ticker,"data_status":"unavailable","data_reason":"issuer_outside_snapshot","rank_eligible":False,"metrics":{}}
        if doc.get("_envelope"):
            env=doc["_envelope"]
            doc=attach_envelope(doc,feed_id=env.get("feed_id","ticker-shard"),as_of=env.get("as_of"),row_count=env.get("row_count"))
        if write_json_if_changed(path,doc):updated+=1
    return updated


if __name__ == "__main__":
    import sys
    if sys.argv[1:]==["--refresh-buyback-projection"]:
        print("Refreshed buyback ticker shards:",refresh_buyback_projection())
