#!/usr/bin/env python3
"""Build progressive-disclosure L0 summary feeds and L1 per-ticker agent shards.

Produces token-efficient, envelope-stamped artifacts for Grok Bot, Cursor, and
Claude agents so they never need to load multi-megabyte monoliths on startup:

L0 Summary Feeds (< 100 KB each):
  - ``dashboard/data/portfolio_summary.json``
  - ``dashboard/data/research_manifest.json``
  - ``dashboard/data/kpi_summary.json``
  - ``dashboard/data/document_catalog_summary.json``

L1 Per-Ticker Agent Shards (10-35 KB each):
  - ``dashboard/data/agent_shards/{TICKER}.json``

Usage:
  python _system/scripts/build_progressive_shards.py
  python _system/scripts/build_progressive_shards.py TPL GOOGL
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from atomic_io import (  # noqa: E402
    attach_envelope,
    now_iso,
    semantic_json_sha256,
     semantic_text_sha256,
    write_json_if_changed,
    write_text_if_changed,
)

DATA_DIR = ROOT / "dashboard" / "data"
AGENT_SHARDS_DIR = DATA_DIR / "agent_shards"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
KPI_TRENDS_PATH = DATA_DIR / "kpi_trends.json"
NEWS_PATH = DATA_DIR / "portfolio_news.json"
SPECIAL_SITUATIONS_PATH = DATA_DIR / "special_situations.json"
SEPARATIONS_PATH = DATA_DIR / "separations.json"
ACTIVIST_FEED_PATH = DATA_DIR / "activist_feed.json"
WARRANTS_PATH = DATA_DIR / "warrants.json"
DOC_REGISTRY_PATH = DATA_DIR / "document_registry.json"
DOC_CATALOG_PATH = DATA_DIR / "document_catalog.json"
CATALOG_JSONL_PATH = ROOT / "_system" / "data" / "catalog" / "documents.jsonl"

_SAFE_TICKER_RE = re.compile(r"[^A-Za-z0-9._-]")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _safe_shard_name(ticker: str) -> str:
    return _SAFE_TICKER_RE.sub("_", str(ticker).upper()) + ".json"


def _index_kpi_by_ticker(kpi_payload: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Extract compact per-ticker KPI series and top-level inflections."""
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    inflections: list[dict[str, Any]] = []

    tickers_block = (
        kpi_payload.get("by_ticker")
        or kpi_payload.get("tickers")
        or kpi_payload.get("series_by_ticker")
        or {}
    )
    if isinstance(tickers_block, dict):
        iterator = tickers_block.items()
    elif isinstance(tickers_block, list):
        iterator = [(row.get("ticker"), row) for row in tickers_block if isinstance(row, dict) and row.get("ticker")]
    else:
        iterator = []

    for tk, entry in iterator:
        ticker = str(tk).upper()
        metrics = (
            entry.get("metrics")
            or entry.get("series")
            or entry.get("kpis")
            or (entry if isinstance(entry, list) else [])
        )
        if isinstance(metrics, dict):
            metrics = [{"metric": k, **(v if isinstance(v, dict) else {"value": v})} for k, v in metrics.items()]
        if not isinstance(metrics, list):
            continue
        for m in metrics:
            if not isinstance(m, dict):
                continue
            direction = str(m.get("direction") or m.get("trend") or "steady").lower()
            name = m.get("metric") or m.get("name") or m.get("label") or "kpi"
            label = m.get("label") or name
            latest = m.get("level_latest") if "level_latest" in m else (m.get("latest") if "latest" in m else m.get("value"))
            yoy = m.get("growth_latest") if "growth_latest" in m else (m.get("yoy_pct") if "yoy_pct" in m else m.get("yoy"))
            points = m.get("points") or []
            period = (
                m.get("latest_period")
                or m.get("period")
                or m.get("as_of")
                or (points[-1].get("period") if points and isinstance(points[-1], dict) else None)
            )
            strength = float(m.get("strength") or 0.0)
            signal_tier = m.get("signal_tier")
            compact = {
                "metric": name,
                "label": label,
                "direction": direction,
                "signal_tier": signal_tier,
                "latest": latest,
                "growth_latest": yoy,
                "strength": round(strength, 3) if strength else None,
                "period": period,
                "human_summary": m.get("human_summary"),
            }
            # Extra keys only on issuer operating rows, so a later full rebuild
            # does not rewrite every fundamental compact row.
            if m.get("tier") == "operating":
                compact["unit"] = m.get("unit")
                compact["yoy_basis"] = m.get("yoy_basis")
                compact["source"] = m.get("source") or "issuer_operating"
                compact["tier"] = "operating"
            by_ticker[ticker].append(compact)
            if direction in ("accelerating", "decelerating", "inflecting", "break") and m.get("display", True):
                inflections.append({"ticker": ticker, **compact})

    inflections.sort(key=lambda r: float(r.get("strength") or 0.0), reverse=True)
    return by_ticker, inflections


def _index_news_by_ticker(news_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    items = news_payload.get("items") or news_payload.get("news") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        conf = float(item.get("confidence") or 0.0)
        if conf < 0.8:
            continue
        tickers = item.get("tickers") or ([item["ticker"]] if item.get("ticker") else [])
        compact = {
            "title": item.get("title") or item.get("headline"),
            "published_utc": item.get("published_utc") or item.get("date"),
            "category": item.get("category"),
            "confidence": conf,
            "url": item.get("url") or item.get("source_url"),
            "linked_filing": item.get("linked_filing"),
        }
        for tk in tickers:
            if tk:
                by_ticker[str(tk).upper()].append(compact)
    for tk in by_ticker:
        by_ticker[tk] = sorted(
            by_ticker[tk],
            key=lambda r: str(r.get("published_utc") or ""),
            reverse=True,
        )[:8]
    return by_ticker


def _index_docs_by_ticker() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    store_counts: Counter[str] = Counter()
    total_docs = 0
    total_bytes = 0

    if CATALOG_JSONL_PATH.is_file():
        for line in CATALOG_JSONL_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_docs += 1
            total_bytes += int(doc.get("size_bytes") or 0)
            stype = str(doc.get("source_type") or "pdf")
            source_counts[stype] += 1
            for st in doc.get("stores") or []:
                store_counts[str(st)] += 1
            tk = str(doc.get("ticker") or "").upper()
            if tk:
                by_ticker[tk].append(
                    {
                        "document_id": doc.get("document_id"),
                        "title": doc.get("title"),
                        "source_type": stype,
                        "local_pdf_path": doc.get("ssi_pdf_path"),
                        "text_extract_path": doc.get("text_extract_path"),
                        "drive_web_view_link": doc.get("drive_web_view_link"),
                        "modified_at": doc.get("modified_at"),
                    }
                )
    else:
        reg = _load_json(DOC_REGISTRY_PATH)
        for doc in reg.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            total_docs += 1
            total_bytes += int(doc.get("size_bytes") or 0)
            stype = str(doc.get("source_type") or "pdf")
            source_counts[stype] += 1
            if doc.get("local_pdf_path"):
                store_counts["ssi"] += 1
            if doc.get("drive_web_view_link") or doc.get("drive_file_id"):
                store_counts["drive"] += 1
            local_p = str(doc.get("local_pdf_path") or "")
            parts = local_p.split("/")
            tk = parts[0].upper() if parts and not parts[0].startswith("_") and parts[0] != "dashboard" else ""
            if tk:
                by_ticker[tk].append(
                    {
                        "document_id": doc.get("document_id"),
                        "title": doc.get("title"),
                        "source_type": stype,
                        "local_pdf_path": local_p,
                        "text_extract_path": doc.get("text_extract_path"),
                        "drive_web_view_link": doc.get("drive_web_view_link"),
                        "modified_at": doc.get("modified_at"),
                    }
                )

    for tk in by_ticker:
        by_ticker[tk] = sorted(
            by_ticker[tk],
            key=lambda d: str(d.get("modified_at") or ""),
            reverse=True,
        )[:15]

    summary = {
        "total_documents": total_docs,
        "total_size_bytes": total_bytes,
        "by_source_type": dict(source_counts.most_common()),
        "by_store": dict(store_counts.most_common()),
        "tickers_with_documents": len(by_ticker),
    }
    return by_ticker, summary


def is_active_book_ticker(ticker: str, reg_entry: dict[str, Any], val: dict[str, Any]) -> bool:
    reg_cls = reg_entry.get("classification") or {}
    val_cls = val.get("classification_inputs") or {}
    stance = (
        val.get("approved_stance")
        or (val.get("stance_proposal") or {}).get("stance")
        or reg_cls.get("stance")
        or reg_entry.get("stance")
        or "watch"
    )
    archetype = val_cls.get("archetype") or reg_cls.get("archetype") or reg_entry.get("archetype") or "unknown"
    if str(stance).lower() not in ("watch", "pass", "unrated", ""):
        return True
    if str(archetype).lower() not in ("unknown", "pending", ""):
        return True
    return False


def build_all(target_tickers: list[str] | None = None, *, build_all_shards: bool = False) -> dict[str, Any]:
    from build_thesis_card import build_card, write_card
    from operating_kpis.trends import merge_operating_series, operating_latest_rows, select_shard_series
    from refresh_core_compounders import read as read_core_state
    core_views = read_core_state(ROOT / "_system/data/core_compounder_state.json").get("views") or {}
    ts = now_iso()
    registry = _load_json(REGISTRY_PATH)
    holdings_map = registry.get("holdings") or {}
    watchlist_map = registry.get("watchlist") or {}

    kpi_payload = _load_json(KPI_TRENDS_PATH)
    news_payload = _load_json(NEWS_PATH)
    kpi_by_ticker, kpi_inflections = _index_kpi_by_ticker(kpi_payload)
    merge_operating_series(kpi_by_ticker)
    news_by_ticker = _index_news_by_ticker(news_payload)
    docs_by_ticker, doc_summary_stats = _index_docs_by_ticker()
    try:
        from build_buyback_radar import load_companies_index, shard_buyback
        buyback_index = load_companies_index()
    except Exception:
        buyback_index = {}
        shard_buyback = None  # type: ignore[assignment]

    all_universe_tickers = sorted(
        set(str(k).upper() for k in holdings_map.keys())
        | set(str(k).upper() for k in (watchlist_map.keys() if isinstance(watchlist_map, dict) else []))
    )

    explicit_targets = {t.upper() for t in target_tickers} if target_tickers else None

    portfolio_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    universe_stances: Counter[str] = Counter()
    universe_archetypes: Counter[str] = Counter()
    shards_written = 0

    AGENT_SHARDS_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in all_universe_tickers:
        tdir = ROOT / ticker
        research_dir = tdir / "research"
        val_path = research_dir / "valuation.json"
        card_path = research_dir / "thesis_card.json"

        reg_entry = holdings_map.get(ticker) or (
            watchlist_map.get(ticker) if isinstance(watchlist_map, dict) else {}
        ) or {}
        reg_cls = reg_entry.get("classification") or {}
        is_holding = ticker in holdings_map
        is_watchlist = isinstance(watchlist_map, dict) and ticker in watchlist_map

        val = _load_json(val_path)
        card = _load_json(card_path)
        active = is_active_book_ticker(ticker, reg_entry, val)
        should_build_shard = (
            (explicit_targets is not None and ticker in explicit_targets)
            or (explicit_targets is None and (build_all_shards or active))
        )

        if not card and should_build_shard and (val or research_dir.is_dir()):
            built_card = build_card(ticker)
            if built_card:
                card = built_card
                write_card(ticker)

        implied = val.get("implied_return") or {}
        results = val.get("results") or {}
        base_irr = card.get("base_irr_pct")
        if base_irr is None:
            base_irr = implied.get("base_pct", (results.get("base") or {}).get("return_pct"))

        stance = (
            card.get("stance")
            or val.get("approved_stance")
            or (val.get("stance_proposal") or {}).get("stance")
            or reg_cls.get("stance")
            or reg_entry.get("stance")
            or "watch"
        )
        cls_inputs = val.get("classification_inputs") or card.get("classification") or {}
        archetype = cls_inputs.get("archetype") or reg_cls.get("archetype") or reg_entry.get("archetype") or "unknown"
        sleeve = reg_cls.get("investment_sleeve") if reg_cls.get("investment_sleeve") not in ("-", "") else None

        universe_stances[str(stance)] += 1
        universe_archetypes[str(archetype)] += 1

        shard_rel = f"dashboard/data/agent_shards/{_safe_shard_name(ticker)}"
        ui_shard_rel = f"dashboard/data/tickers/{_safe_shard_name(ticker)}"
        evidence_dir = research_dir / "evidence"
        digest_file = evidence_dir / "filing_digest.md"
        if not digest_file.is_file():
            dated_digs = sorted(evidence_dir.glob("filing_digest_*.md")) if evidence_dir.is_dir() else []
            digest_file = dated_digs[-1] if dated_digs else digest_file

        ev_hash = None
        if active and digest_file.is_file():
            ev_hash = f"sha256:{semantic_text_sha256(digest_file.read_text(encoding='utf-8', errors='ignore'))[:16]}"

        summary_row = {
            k: v
            for k, v in {
                "ticker": ticker,
                "company": reg_entry.get("company") or val.get("company") or ticker,
                "market": reg_entry.get("market") if reg_entry.get("market") != "US" else None,
                "sleeve": sleeve,
                "archetype": archetype if archetype != "unknown" else None,
                "stance": stance if stance != "watch" else None,
                "base_irr_pct": round(float(base_irr), 2) if isinstance(base_irr, (int, float)) else None,
                "as_of": val.get("as_of"),
            }.items()
            if v is not None
        }
        if active:
            portfolio_rows.append(summary_row)
            manifest_row = {
                k: v
                for k, v in {
                    "ticker": ticker,
                    "stance": stance if stance != "watch" else None,
                    "archetype": archetype if archetype != "unknown" else None,
                    "base_irr_pct": summary_row.get("base_irr_pct"),
                    "base_irr_unit": "percent_per_year",
                    "shard_status": "built" if should_build_shard else "not_built",
                    "as_of": val.get("as_of"),
                    "has_card": True if (card or card_path.is_file()) else None,
                    "has_digest": True if digest_file.is_file() else None,
                    "evidence_sha256": ev_hash,
                }.items()
                if v is not None
            }
            manifest_rows.append(manifest_row)

        if should_build_shard:
            shard_payload: dict[str, Any] = {
                "schema_version": "magis.agent_shard.v2",
                "ticker": ticker,
                "company": summary_row["company"],
                "book": "holdings" if is_holding else ("watchlist" if is_watchlist else "research"),
                "shard_status": "built",
                "compounder_monitor": core_views.get(ticker),
                "as_of": val.get("as_of") or ts[:10],
                "registry": {
                    "market": reg_entry.get("market"),
                    "exchange": reg_entry.get("exchange"),
                    "sleeve": sleeve,
                    "moat": reg_cls.get("moat"),
                    "dhando": reg_cls.get("dhando"),
                    "payoff_lens": reg_cls.get("payoff_lens"),
                },
                "returns": {
                    "base_irr_pct": base_irr,
                    "unit": "percent_per_year",
                    "label": card.get("irr_label") or implied.get("label"),
                    "display": implied.get("display"),
                    "scenarios_pct": card.get("scenarios") or {},
                },
                "thesis_summary": {
                    "thesis": card.get("thesis") or "",
                    "why_market_wrong": card.get("why_market_wrong") or "",
                    "stance": stance,
                    "archetype": archetype,
                    "base_irr_pct": base_irr,
                    "base_irr_unit": "percent_per_year",
                    "scenarios": card.get("scenarios") or {},
                    "key_assumptions": (card.get("key_assumptions") or [])[:8],
                    "open_questions": (card.get("open_questions") or [])[:6],
                },
                "truncation": {
                    "key_assumptions": {"shown": min(len(card.get("key_assumptions") or []), 8), "total": len(card.get("key_assumptions") or [])},
                    "open_questions": {"shown": min(len(card.get("open_questions") or []), 6), "total": len(card.get("open_questions") or [])},
                    "kpi_series": {
                        "shown": len(select_shard_series(kpi_by_ticker.get(ticker) or [])),
                        "total": len(kpi_by_ticker.get(ticker) or []),
                    },
                    "documents": {"shown": len(docs_by_ticker.get(ticker) or []), "note": "capped at 15 most recent in builder"},
                },
                "kpi_series": select_shard_series(kpi_by_ticker.get(ticker) or []),
                "recent_news": news_by_ticker.get(ticker) or [],
                "documents": docs_by_ticker.get(ticker) or [],
                "l2_pointers": {
                    "valuation_json": f"{ticker}/research/valuation.json" if val_path.is_file() else None,
                    "thesis_card_json": f"{ticker}/research/thesis_card.json" if card_path.is_file() else None,
                    "filing_digest_md": digest_file.relative_to(ROOT).as_posix() if digest_file.is_file() else None,
                    "insider_signal_md": (
                        f"{ticker}/research/evidence/insider_signal.md"
                        if (evidence_dir / "insider_signal.md").is_file()
                        else None
                    ),
                    "thematic_context_md": (
                        f"{ticker}/research/evidence/thematic_context.md"
                        if (evidence_dir / "thematic_context.md").is_file()
                        else None
                    ),
                    "source_inventory_json": (
                        f"{ticker}/third-party-analyses/source_inventory.json"
                        if (tdir / "third-party-analyses" / "source_inventory.json").is_file()
                        else None
                    ),
                    "full_ui_shard_json": ui_shard_rel if (ROOT / ui_shard_rel).is_file() else None,
                    "latest_json": f"{ticker}/research/latest.json",
                    "context_pack_md": f"dashboard/data/context_packs/{ticker}.md",
                },
            }
            buyback_row = buyback_index.get(ticker)
            if buyback_row and shard_buyback:
                shard_payload["buyback"] = shard_buyback(buyback_row)
            # Volatile stamp last: stable prefix stays prompt-cache friendly.
            shard_payload["generated_at"] = ts
            attach_envelope(
                shard_payload,
                feed_id=f"agent-shard-{ticker.lower()}",
                as_of=shard_payload["as_of"],
                row_count=len(shard_payload["kpi_series"]) + len(shard_payload["recent_news"]),
            )
            shard_out = AGENT_SHARDS_DIR / _safe_shard_name(ticker)
            if write_json_if_changed(shard_out, shard_payload):
                shards_written += 1

    # 1. Write L0 portfolio_summary.json
    stance_counts = dict(Counter(str(r.get("stance") or "unrated") for r in portfolio_rows))
    portfolio_summary = attach_envelope(
        {
            "schema_version": "magis.portfolio_summary.v1",
            "generated_at": ts,
            "as_of": str((registry.get("meta") or {}).get("updated") or ts[:10]),
            "description": (
                "L0 progressive-disclosure summary of active/classified portfolio tickers (< 100 KB). "
                "Read this file first before opening L1 dashboard/data/agent_shards/{TICKER}.json."
            ),
            "counts": {
                "active_book": len(portfolio_rows),
                "total_registry_universe": len(all_universe_tickers),
                "active_by_stance": stance_counts,
                "universe_by_stance": dict(universe_stances),
                "universe_by_archetype": dict(universe_archetypes),
            },
            "defaults": {
                "market": "US",
                "stance": "watch",
                "archetype": "unknown",
                "agent_shard_template": "dashboard/data/agent_shards/{TICKER}.json",
            },
            "rows": portfolio_rows,
        },
        feed_id="dashboard-portfolio-summary",
        as_of=str((registry.get("meta") or {}).get("updated") or ts[:10]),
        row_count=len(portfolio_rows),
        upstream_inputs=[
            {
                "path": "_system/portfolio/registry.json",
                "generated_at": str((registry.get("meta") or {}).get("updated") or ts[:10]),
            }
        ],
    )
    write_json_if_changed(DATA_DIR / "portfolio_summary.json", portfolio_summary)

    # 2. Write L0 research_manifest.json
    research_manifest = attach_envelope(
        {
            "schema_version": "magis.research_manifest.v1",
            "generated_at": ts,
            "as_of": ts[:10],
            "description": (
                "L0 per-ticker research index mapping every research folder to its L1 agent_shard, "
                "thesis_card, filing_digest, and evidence hash."
            ),
            "counts": {
                "tickers": len(manifest_rows),
                "with_valuation": sum(1 for r in manifest_rows if r.get("as_of") or r.get("base_irr_pct") is not None),
                "with_digest": sum(1 for r in manifest_rows if r.get("has_digest")),
                "registry_universe": len(all_universe_tickers),
                "tickers_without_shard": max(0, len(all_universe_tickers) - shards_written),
                "shard_status_note": "Active-book tickers have built shards; other tickers resolve via {TICKER}/research/latest.json and thesis_card.json on demand.",
            },
            "path_templates": {
                "agent_shard": "dashboard/data/agent_shards/{TICKER}.json",
                "thesis_card": "{TICKER}/research/thesis_card.json",
                "latest": "{TICKER}/research/latest.json",
                "context_pack": "dashboard/data/context_packs/{TICKER}.md",
                "full_ui_shard": "dashboard/data/tickers/{TICKER}.json",
                "filing_digest": "{TICKER}/research/evidence/filing_digest.md",
            },
            "tickers": manifest_rows,
        },
        feed_id="dashboard-research-manifest",
        as_of=ts[:10],
        row_count=len(manifest_rows),
    )
    manifest_path = DATA_DIR / "research_manifest.json"
    write_json_if_changed(manifest_path, research_manifest, indent=None)
    if manifest_path.stat().st_size > 100 * 1024:
        # Compact legacy pretty-printed feeds without dropping evidence or
        # raising the L0 budget. Semantic JSON equality otherwise skips this.
        write_text_if_changed(manifest_path, json.dumps(research_manifest, separators=(",", ":"), ensure_ascii=False))

    # 3. Write L0 kpi_summary.json
    kpi_gen = kpi_payload.get("generated_at") or ts
    kpi_summary = attach_envelope(
        {
            "schema_version": "magis.kpi_summary.v1",
            "generated_at": kpi_gen,
            "as_of": str(kpi_gen)[:10],
            "description": (
                "L0 KPI inflection summary extracted from dashboard/data/kpi_trends.json. "
                "Inflections are the accelerating and decelerating series. "
                "operating_latest carries issuer operating levels even when the series is steady."
            ),
            "inflection_count": len(kpi_inflections),
            "covered_ticker_count": len(kpi_by_ticker),
            "inflections": kpi_inflections[:120],
            "operating_latest": operating_latest_rows(),
            "full_feed_path": "dashboard/data/kpi_trends.json",
        },
        feed_id="dashboard-kpi-summary",
        as_of=str(kpi_gen)[:10],
        row_count=len(kpi_inflections[:120]),
        upstream_inputs=[
            {
                "path": "dashboard/data/kpi_trends.json",
                "generated_at": kpi_gen,
                "sha256": semantic_json_sha256(kpi_payload)[:16] if kpi_payload else None,
            }
        ],
    )
    write_json_if_changed(DATA_DIR / "kpi_summary.json", kpi_summary)

    # 4. Write L0 document_catalog_summary.json
    doc_cat_summary = attach_envelope(
        {
            "schema_version": "magis.document_catalog_summary.v1",
            "generated_at": ts,
            "as_of": ts[:10],
            "description": (
                "L0 summary of the unified cross-store document catalog across SSI, Google Drive, and "
                "research-vault. Query _system/data/catalog/documents.jsonl or query_agent_index.py for full records."
            ),
            "summary": doc_summary_stats,
            "catalog_jsonl_path": "_system/data/catalog/documents.jsonl",
            "legacy_catalog_path": "dashboard/data/document_catalog.json",
            "legacy_registry_path": "dashboard/data/document_registry.json",
        },
        feed_id="dashboard-document-catalog-summary",
        as_of=ts[:10],
        row_count=doc_summary_stats["total_documents"],
    )
    write_json_if_changed(DATA_DIR / "document_catalog_summary.json", doc_cat_summary)

    return {
        "portfolio_rows": len(portfolio_rows),
        "manifest_rows": len(manifest_rows),
        "kpi_inflections": len(kpi_inflections),
        "shards_written": shards_written,
        "total_documents": doc_summary_stats["total_documents"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Optional ticker subset for L1 shard rebuild")
    args = parser.parse_args(argv)
    stats = build_all(args.tickers or None)
    print(
        f"OK progressive shards: portfolio={stats['portfolio_rows']} "
        f"manifest={stats['manifest_rows']} kpi_inflections={stats['kpi_inflections']} "
        f"shards_written={stats['shards_written']} docs={stats['total_documents']}"
    )
    return 0



def refresh_buyback_projection(folder=None):
    """Refresh canonical buyback fields while preserving all other shard contents."""
    from build_buyback_radar import load_companies_index, shard_buyback
    from atomic_io import write_json_if_changed, attach_envelope
    index=load_companies_index()
    if not index:raise ValueError("Verified buyback snapshot unavailable")
    folder=Path(folder) if folder else AGENT_SHARDS_DIR
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
        print("Refreshed buyback agent shards:",refresh_buyback_projection())
    else:
        raise SystemExit(main())
