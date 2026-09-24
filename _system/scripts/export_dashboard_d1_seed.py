#!/usr/bin/env python3
"""Export the sharded dashboard snapshot as an incremental, idempotent D1 seed.

D1 runs on the Workers Free plan: 100k rows written and 5M rows read per UTC
day, account-wide. Until 2026-09-24 this exporter stamped the rebuild time
(``generated_at``) into ``run_id``, ``valuation_run_id`` and ``fact_id``, so
every rebuild of core.json -- even one that changed nothing D1 stores --
re-inserted every fact, valuation run and component, deleted the previous
generation with full-table ``DELETE ... WHERE run_id <> ?`` scans, and
restamped ``latest_run_id`` on every security, valuation and task. That was
~20.5k rows written per rebuild; five rebuilds exhausted the daily quota
(2026-09-23 21:52 UTC, 2026-09-24 18:36 UTC).

The seed is now incremental:

* Row identities are content-stable. ``run_id`` is derived from the content
  hash; ``valuation_run_id`` from the ticker and model hash; ``fact_id`` from
  the ticker, component, node and source. No identity contains a timestamp.
* Change detection compares content. ``updated_at``, ``imported_at``,
  ``latest_run_id`` and ``run_id`` are bookkeeping: they are written when a
  row's content changes but never cause a write on their own.
* Every ticker's rows hash to one per-ticker digest. The seed persists those
  digests in ``ops_state`` (inside the same import, so they are atomic with the
  rows). The next export emits only tickers whose digest changed, and the
  deploy skips the import entirely when the whole-content hash is unchanged.
* Removed rows are garbage-collected by key set, per changed ticker, through
  index-backed deletes (``ticker = ? AND id NOT IN (...)``). No statement scans
  a whole table except the one-time sweep of a full export.

Without a readable previous state (first run, format change, ``--full``) the
export is FULL: every ticker is emitted, each upsert still writes only rows
whose content differs, and one sweep deletes securities that no longer exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORE = ROOT / "dashboard" / "data" / "core.json"
DEFAULT_OUTPUT = ROOT / "dashboard" / "cloudflare" / "generated" / "dashboard_seed.sql"
DEFAULT_EVIDENCE_QUEUE = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
DEFAULT_TECHNICAL_SUMMARY = ROOT / "dashboard" / "data" / "technical_summary.json"
DEFAULT_CRITICALITY_SUMMARY = ROOT / "dashboard" / "data" / "criticality_summary.json"
DONE_STATUSES = {"evidence_ready", "closed", "complete", "resolved"}
PROFILE_DEFAULT_METHOD = {
    "quality_reinvestment": "owner_earnings_reinvestment_dcf",
    "scarce_asset_optionality": "component_owner_cash_and_unit_nav",
    "predictable_cash_flow": "owner_cash_or_dividend_discount",
    "capital_cycle": "midcycle_capacity_value",
    "catalyst_asset_value": "probability_weighted_catalyst_nav",
    "binary_milestone": "risk_adjusted_milestone_value",
    "credit_and_normalized_returns": "capital_structure_and_excess_return",
}

# Bump when the row mapping or identity scheme changes: a different format in
# the persisted state forces one FULL export, which re-keys every row.
SEED_FORMAT = 2
STATE_PREFIX = "seed:state:"
STATE_RANGE_END = "seed:state;"  # ';' sorts right after ':' -- a PK range
STATE_CHUNK_CHARS = 50_000       # D1 caps one SQL statement at 100 KB
TICKER_HASH_CHARS = 16
MAX_STATEMENT_BYTES = 100_000    # D1's documented statement limit
KEY_LIST_CHUNK = 400             # keeps IN (...) lists far below that limit

# Written when a row changes, never compared: a new rebuild time or run id on
# otherwise identical content must not cost a write.
BOOKKEEPING_COLUMNS = frozenset({"updated_at", "imported_at", "latest_run_id", "run_id"})

# Parent before child, so foreign keys resolve inside one import.
TICKER_TABLES = (
    ("securities", "security", ("ticker",)),
    ("valuation_current", "valuation", ("ticker",)),
    ("evidence_tasks", "tasks", ("ticker", "task_id")),
    ("source_documents", "documents", ("document_id",)),
    ("valuation_runs", "runs", ("valuation_run_id",)),
    ("valuation_components", "components", ("valuation_run_id", "component_id")),
    ("facts", "facts", ("fact_id",)),
)
RUN_ID_COLUMNS = {
    "securities": "latest_run_id",
    "valuation_current": "latest_run_id",
    "evidence_tasks": "latest_run_id",
    "valuation_runs": "run_id",
    "facts": "run_id",
}


def stable_id(*parts: Any) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result and result not in {float("inf"), float("-inf")} else None
    except (TypeError, ValueError):
        return None


def upsert(
    table: str,
    columns: list[str],
    values: list[Any],
    conflict: list[str],
    *,
    ignore_changes: set[str] | frozenset[str] = frozenset(),
) -> str:
    """INSERT, or UPDATE only when a compared column differs.

    ``ignore_changes`` columns are still assigned when the row changes, but a
    difference in them alone never triggers the UPDATE (so never a write).
    """
    assignments = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column not in conflict
    )
    compared = [
        column
        for column in columns
        if column not in conflict and column not in ignore_changes
    ]
    head = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
        f"({', '.join(quote(value) for value in values)}) "
        f"ON CONFLICT ({', '.join(conflict)}) "
    )
    if not compared or not assignments:
        return head + "DO NOTHING;"
    changed = " OR ".join(
        f"{table}.{column} IS NOT excluded.{column}" for column in compared
    )
    return head + f"DO UPDATE SET {assignments} WHERE {changed};"


def _fallback_tasks(ticker: str, row: dict, queue_item: dict, route: dict) -> list[dict]:
    decision = row.get("valuation_decision") or {}
    if str(decision.get("status") or "evidence_blocked") == "decision_grade":
        return []
    if (
        str(route.get("status") or "") == "default_needs_review"
        or not (route.get("primary_methods") or [])
        or float(route.get("score") or 0) <= 0
    ):
        return [{
            "id": "valuation_route_classification_required",
            "priority": "critical",
            "field_id": "valuation_route",
            "method_id": ((route.get("primary_methods") or [None])[0]),
            "question": "Supply source-backed classification for a non-default Power Zone valuation route.",
            "evidence_required": "security archetype, economic ownership map, investment sleeve, and component categories",
            "acceptance_test": "The canonical route has a positive score and is not default_needs_review.",
            "collector": "primary_documents_then_classification",
            "status": "pending_collection",
            "attempts": 0,
            "max_attempts": 5,
            "evidence_refs": [],
        }]
    return [{
        "id": queue_item.get("next_gap_id") or decision.get("next_gap_id") or "complete_component_model_required",
        "priority": "critical",
        "field_id": "component_model",
        "method_id": ((route.get("primary_methods") or [None])[0]),
        "question": (
            queue_item.get("next_gap_question")
            or decision.get("next_action")
            or "Build a complete primary-sourced component valuation."
        ),
        "evidence_required": "; ".join(route.get("required_evidence") or []),
        "acceptance_test": "Every material economic claim is valued exactly once using an approved deterministic proof.",
        "collector": "primary_documents_then_model",
        "status": "pending_collection",
        "attempts": 0,
        "max_attempts": 5,
        "evidence_refs": [],
    }]


def _dedupe_last(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    """Keep the last row per primary key -- what sequential upserts leave."""
    latest: dict[tuple, dict] = {}
    for row in rows:
        latest[tuple(row[column] for column in key)] = row
    return list(latest.values())


def _route_for(ticker: str, row: dict, decision: dict, root: Path = ROOT) -> dict:
    route = read_json(root / ticker / "research" / "valuation_route.json")
    if route:
        return route
    route = dict(((row.get("power_zones") or {}).get("valuation_route") or {}))
    profile_id = route.get("profile_id") or decision.get("method_profile")
    if profile_id:
        route["profile_id"] = profile_id
        route.setdefault(
            "primary_methods",
            [PROFILE_DEFAULT_METHOD.get(profile_id)]
            if PROFILE_DEFAULT_METHOD.get(profile_id)
            else [],
        )
    route.setdefault(
        "score",
        1 if route.get("status") and route.get("status") != "default_needs_review" else 0,
    )
    return route


def _model_rows(
    ticker: str, row: dict, decision: dict, route: dict, root: Path = ROOT,
) -> dict[str, list[dict]]:
    """valuation_runs / components / source_documents / facts from the shard."""
    out: dict[str, list[dict]] = {"documents": [], "runs": [], "components": [], "facts": []}
    shard_ref = str(row.get("detail_shard") or "")
    shard_path = root / "dashboard" / shard_ref
    if not shard_ref or not shard_path.is_file():
        shard_path = root / "dashboard" / "data" / "tickers" / f"{ticker}.json"
    detail = read_json(shard_path)
    workbench = detail.get("valuation_workbench") or {}
    wb_valuation = workbench.get("valuation") or {}
    valuation_body = wb_valuation.get("valuation") or {}
    wb_decision = workbench.get("decision") or decision
    wb_method = workbench.get("method_fit") or {}
    proof_summary = wb_valuation.get("calculation_proof_summary") or {}
    wb_components = wb_valuation.get("components") or []
    if not (workbench and wb_components):
        return out

    # The model hash is the run identity. Without one, hash the workbench
    # itself -- never the core.json bytes, which change on every rebuild.
    model_hash = str(
        wb_decision.get("model_hash")
        or (wb_valuation.get("change_control") or {}).get("model_hash")
        or hashlib.sha256(compact_json(workbench).encode("utf-8")).hexdigest()
    )
    valuation_run_id = stable_id(ticker, model_hash)
    primary_methods = wb_method.get("primary_methods") or []
    primary_method = str(
        primary_methods[0] if primary_methods
        else (route.get("primary_methods") or ["unknown"])[0]
    )
    values = valuation_body.get("value_per_share") or wb_decision.get("value_per_share") or {}
    output_unit = next(
        (
            (component.get("calculation_proof") or {}).get("output_unit")
            for component in wb_components
            if isinstance(component.get("calculation_proof"), dict)
            and (component.get("calculation_proof") or {}).get("output_unit")
        ),
        "USD per share",
    )
    out["runs"].append({
        "valuation_run_id": valuation_run_id,
        "ticker": ticker,
        "method_id": primary_method,
        "method_version": "1.0",
        "power_zone_profile": wb_method.get("profile_id") or route.get("profile_id"),
        "as_of_date": workbench.get("as_of"),
        "status": wb_decision.get("status") or "evidence_blocked",
        "input_hash": model_hash,
        "proof_hash": proof_summary.get("aggregate_proof_hash"),
        "value_low": number(values.get("low")),
        "value_base": number(values.get("base")),
        "value_high": number(values.get("high")),
        "output_unit": output_unit,
        "payload_json": compact_json({
            "decision": wb_decision,
            "method_fit": {
                "profile_id": wb_method.get("profile_id"),
                "primary_methods": primary_methods,
                "routing_reasons": wb_method.get("routing_reasons") or [],
            },
            "calculation_proof_summary": proof_summary,
        }),
    })
    document_ids: set[str] = set()
    for component in wb_components:
        component_id = str(component.get("component_id") or component.get("id") or "")
        if not component_id:
            continue
        component_values = component.get("range_per_share") or {}
        proof = component.get("calculation_proof") or {}
        out["components"].append({
            "valuation_run_id": valuation_run_id,
            "component_id": component_id,
            "label": component.get("label"),
            "category": component.get("category"),
            "treatment": component.get("treatment") or "additive",
            "method_id": component.get("method"),
            "method_version": component.get("method_version") or proof.get("method_version"),
            "value_low": number(component_values.get("low")),
            "value_base": number(component_values.get("base")),
            "value_high": number(component_values.get("high")),
            "overlap_key": component.get("overlap_key"),
            "proof_hash": proof.get("proof_hash"),
            "payload_json": compact_json({
                key: component.get(key)
                for key in (
                    "evidence_tier", "evidence", "falsifier", "valuation_status",
                    "ownership_claim", "ownership_percentage", "assumption_type",
                )
                if component.get(key) is not None
            }),
        })
        traces = proof.get("traces") or {}
        base_trace = {
            str(trace.get("id") or ""): trace
            for trace in (traces.get("base") or [])
            if isinstance(trace, dict)
        }
        for lineage in proof.get("source_lineage") or []:
            if not isinstance(lineage, dict) or not lineage.get("ref"):
                continue
            node_id = str(lineage.get("node_id") or "")
            source_id = str(lineage.get("source_id") or stable_id(
                ticker, lineage.get("ref"), lineage.get("locator"), lineage.get("as_of")
            ))
            document_id = stable_id(ticker, source_id)
            if document_id not in document_ids:
                out["documents"].append({
                    "document_id": document_id,
                    "ticker": ticker,
                    "source_type": "valuation_primary_evidence",
                    "source_ref": lineage.get("ref"),
                    "source_locator": lineage.get("locator"),
                    "as_of_date": lineage.get("as_of"),
                    "content_sha256": source_id,
                    "metadata_json": compact_json({"component_id": component_id, "source_id": source_id}),
                })
                document_ids.add(document_id)
            trace = base_trace.get(node_id) or {}
            out["facts"].append({
                "fact_id": stable_id(ticker, component_id, node_id, source_id),
                "ticker": ticker,
                "field_id": node_id or "source_lineage",
                "value_number": number(trace.get("value")),
                "value_text": None if number(trace.get("value")) is not None else trace.get("value"),
                "unit": trace.get("unit"),
                "currency": None,
                "as_of_date": lineage.get("as_of"),
                "confidence": "source_locked",
                "locked": True,
                "source_document_id": document_id,
                "source_locator": lineage.get("locator"),
                "derivation_json": compact_json({
                    "component_id": component_id,
                    "kind": trace.get("kind"),
                    "operation": trace.get("operation"),
                    "dependencies": trace.get("dependencies") or [],
                }),
                "method_version": component.get("method_version") or proof.get("method_version") or "1.0",
            })
    out["components"] = _dedupe_last(out["components"], ("valuation_run_id", "component_id"))
    out["facts"] = _dedupe_last(out["facts"], ("fact_id",))
    return out


def build_model(
    core: dict,
    evidence_queue_path: Path = DEFAULT_EVIDENCE_QUEUE,
    technical_summary: dict | None = None,
    criticality_summary: dict | None = None,
    root: Path = ROOT,
) -> dict:
    """Every D1 row the dashboard publishes, as plain dicts (no run ids yet)."""
    generated_at = str(core.get("generated_at") or datetime.now(timezone.utc).isoformat())
    technical_summary = technical_summary if technical_summary is not None else read_json(DEFAULT_TECHNICAL_SUMMARY)
    criticality_summary = (
        criticality_summary if criticality_summary is not None else read_json(DEFAULT_CRITICALITY_SUMMARY)
    )
    queue_by_ticker = {
        str(item.get("ticker") or ""): item
        for item in ((core.get("valuation_queue") or {}).get("items") or [])
    }
    aggregate_task_packets = {
        str(item.get("ticker") or "").upper(): item.get("task_packet") or {}
        for item in (read_json(evidence_queue_path).get("items") or [])
        if item.get("task_packet")
    }

    criticality: list[dict] = []
    for symbol, snapshot in sorted((criticality_summary.get("by_symbol") or {}).items()):
        confidence = snapshot.get("confidence") or {}
        critical_time = snapshot.get("critical_time") or {}
        criticality.append({
            "scope": snapshot.get("scope") or "market",
            "symbol": symbol,
            "as_of": snapshot.get("as_of"),
            "horizon": "multi",
            "model_version": snapshot.get("model_version") or criticality_summary.get("model_version"),
            "direction": snapshot.get("direction") or "none",
            "criticality_score": number(snapshot.get("score")) or 0,
            "positive_confidence": number(confidence.get("positive")) or 0,
            "negative_confidence": number(confidence.get("negative")) or 0,
            "qualified_confidence": number(confidence.get("qualified")) or 0,
            "tc_p10_days": number(critical_time.get("p10")),
            "tc_median_days": number(critical_time.get("median")),
            "tc_p90_days": number(critical_time.get("p90")),
            "fit_count": int(snapshot.get("fit_count") or 0),
            "qualified_count": int(snapshot.get("qualified_count") or 0),
            "source": snapshot.get("source"),
            "entitlement_mode": snapshot.get("entitlement_mode") or "eod",
            "quality_state": snapshot.get("quality_state") or snapshot.get("status") or "limited",
            "payload_json": compact_json(snapshot),
        })

    # Detailed technical, OHLCV, capitulation, market-context, and market-
    # structure snapshots are already published as immutable static shards.
    # No live D1 route reads them, so only retain the flow aggregate used by
    # the market-risk API.
    flow: list[dict] = []
    internal_market = (technical_summary.get("market_context") or {}).get("internal") or {}
    if internal_market.get("as_of"):
        internal_scores = internal_market.get("scores") or {}
        flow.append({
            "scope": "market",
            "symbol": "SPY",
            "as_of": internal_market.get("as_of"),
            "model_version": internal_market.get("model_version") or "capitulation-v1",
            "state": internal_market.get("state") or "normal",
            "pressure_score": number(internal_scores.get("pressure")),
            "panic_score": number(internal_scores.get("panic")),
            "exhaustion_score": number(internal_scores.get("exhaustion")),
            "liquidity_score": None,
            "breadth_score": None,
            "vol_target_pressure_low": None,
            "vol_target_pressure_high": None,
            "source": internal_market.get("source") or "technical_summary",
            "entitlement_mode": "eod",
            "quality_state": "ready" if internal_scores else "limited",
            "payload_json": compact_json(internal_market),
        })

    tickers: dict[str, dict] = {}
    blocked_without_source_task = 0
    for row in core.get("tickers") or []:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        classification = row.get("classification") or {}
        decision = row.get("valuation_decision") or {}
        values = decision.get("value_per_share") or {}
        # Only the dated forward-return contract is rankable.  The deprecated
        # annualized column below receives the same canonical value (or NULL)
        # for compatibility; it must never receive the legacy PV-gap number.
        returns = (
            decision.get("forward_return_at_price_pct") or {}
            if decision.get("return_publishable")
            else {}
        )
        margins = decision.get("margin_of_safety_pct") or {}
        dates = decision.get("dates") or {}
        tier = row.get("valuation_tier") or decision.get("universe_tier") or {}
        route = _route_for(ticker, row, decision, root)
        queue_item = queue_by_ticker.get(ticker) or {}

        security = {
            "ticker": ticker,
            "company": row.get("company") or ticker,
            "market": row.get("market"),
            "exchange_code": row.get("exchange"),
            "investment_sleeve": classification.get("investment_sleeve"),
            "stance": classification.get("stance"),
            "archetype": classification.get("archetype"),
            "last_research_at": row.get("last_research"),
            "updated_at": generated_at,
        }
        valuation = {
            "ticker": ticker,
            "decision_status": decision.get("status") or "evidence_blocked",
            "provisional": bool(decision.get("provisional", True)),
            "method_profile": decision.get("method_profile") or route.get("profile_id"),
            "primary_power_zone": decision.get("primary_power_zone") or route.get("label"),
            "price_per_share": number(decision.get("price_per_share")),
            "value_low": number(values.get("low")),
            "value_base": number(values.get("base")),
            "value_high": number(values.get("high")),
            "annualized_return_base_pct": number(returns.get("base")),
            "model_level": decision.get("model_level"),
            "output_basis": decision.get("output_basis"),
            "present_value_base": number((decision.get("present_value_today_per_share") or values).get("base")),
            "margin_of_safety_base_pct": number(margins.get("base")),
            "forward_return_base_pct": number(returns.get("base")),
            "required_return_pct": number(decision.get("required_return_pct")),
            "return_publishable": bool(decision.get("return_publishable")),
            "valuation_tier": int(tier.get("tier")) if tier.get("tier") is not None else None,
            "model_as_of": dates.get("model_as_of"),
            "latest_fact_as_of": dates.get("latest_fact_as_of"),
            "price_as_of": dates.get("price_as_of"),
            "open_gap_count": int(decision.get("open_gap_count") or 0),
            "critical_gap_count": int(decision.get("critical_gap_count") or 0),
            "next_gap_id": decision.get("next_gap_id") or queue_item.get("next_gap_id"),
            "next_gap_question": queue_item.get("next_gap_question"),
            "source_as_of": classification.get("analysis_as_of") or row.get("last_research"),
            "payload_json": compact_json(decision),
            "updated_at": generated_at,
        }
        task_doc = (
            read_json(root / ticker / "research" / "evidence_task_queue.json")
            or aggregate_task_packets.get(ticker)
            or {}
        )
        source_tasks = task_doc.get("tasks") or _fallback_tasks(ticker, row, queue_item, route)
        if (
            str(decision.get("status") or "evidence_blocked") != "decision_grade"
            and not (task_doc.get("tasks") or [])
        ):
            blocked_without_source_task += 1
        tasks = []
        for task in source_tasks:
            task_id = str(task.get("id") or "")
            if not task_id:
                continue
            tasks.append({
                "ticker": ticker,
                "task_id": task_id,
                "priority": task.get("priority") or "critical",
                "field_id": task.get("field_id"),
                "method_id": task.get("method_id") or task_doc.get("method_id"),
                "question": task.get("question"),
                "evidence_required": task.get("evidence_required"),
                "acceptance_test": task.get("acceptance_test"),
                "collector": task.get("collector"),
                "status": task.get("status") or "pending_collection",
                "attempts": int(task.get("attempts") or 0),
                "max_attempts": int(task.get("max_attempts") or 5),
                "last_attempt_at": task.get("last_attempt_at"),
                "next_attempt_at": task.get("next_attempt_at"),
                "last_error": task.get("last_error"),
                "evidence_refs_json": compact_json(task.get("evidence_refs") or []),
                "updated_at": task_doc.get("updated_at") or generated_at,
            })
        sections = {
            "security": [security],
            "valuation": [valuation],
            "tasks": _dedupe_last(tasks, ("ticker", "task_id")),
        }
        sections.update(_model_rows(ticker, row, decision, route, root))
        tickers[ticker] = sections

    return {
        "generated_at": generated_at,
        "summary": core.get("summary") or {},
        "tickers": tickers,
        "criticality": criticality,
        "flow": flow,
        "blocked_without_source_task": blocked_without_source_task,
    }


def _content(table: str, row: dict) -> str:
    return compact_json([table, {k: v for k, v in row.items() if k not in BOOKKEEPING_COLUMNS}])


def _digest(parts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def content_hashes(model: dict) -> tuple[dict[str, str], str, str]:
    """(per-ticker digests, globals digest, whole-content sha256)."""
    per_ticker = {
        ticker: _digest(
            _content(table, row)
            for table, section, _key in TICKER_TABLES
            for row in sections.get(section) or []
        )[:TICKER_HASH_CHARS]
        for ticker, sections in model["tickers"].items()
    }
    globals_hash = _digest(
        [_content("criticality_snapshots", row) for row in model["criticality"]]
        + [_content("flow_stress_snapshots", row) for row in model["flow"]]
    )[:TICKER_HASH_CHARS]
    content_sha256 = _digest(
        [f"format:{SEED_FORMAT}", f"globals:{globals_hash}"]
        + [f"{ticker}:{digest}" for ticker, digest in sorted(per_ticker.items())]
    )
    return per_ticker, globals_hash, content_sha256


def load_previous_state(ops_state: dict[str, str] | None) -> dict | None:
    """Reassemble the persisted seed state from ops_state rows, or None."""
    if not ops_state:
        return None
    chunks = [value for key, value in sorted(ops_state.items()) if key.startswith(STATE_PREFIX)]
    if not chunks:
        return None
    try:
        state = json.loads("".join(chunks))
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or state.get("format") != SEED_FORMAT:
        return None
    if not isinstance(state.get("tickers"), dict) or not state.get("content_sha256"):
        return None
    return state


def _in_list(values: Iterable[str]) -> str:
    return ", ".join(quote(value) for value in values)


def _chunks(values: list[str], size: int = KEY_LIST_CHUNK) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _row_upsert(table: str, key: tuple[str, ...], row: dict, run_id: str) -> str:
    row = dict(row)
    run_column = RUN_ID_COLUMNS.get(table)
    if run_column:
        row[run_column] = run_id
    columns = list(row)
    return upsert(
        table,
        columns,
        [row[column] for column in columns],
        list(key),
        ignore_changes=BOOKKEEPING_COLUMNS,
    )


def _delete_not_in(table: str, where: str, id_column: str, keep: list[str]) -> str:
    if not keep:
        return f"DELETE FROM {table} WHERE {where};"
    return f"DELETE FROM {table} WHERE {where} AND {id_column} NOT IN ({_in_list(keep)});"


def _ticker_statements(ticker: str, sections: dict, run_id: str) -> list[str]:
    sql = [
        _row_upsert(table, key, row, run_id)
        for table, section, key in TICKER_TABLES
        for row in sections.get(section) or []
    ]
    # Garbage collection by key set, child before parent. Every delete seeks
    # by an index that leads with its WHERE column (idx_facts_lookup,
    # the valuation_components primary key, idx_valuation_runs_ticker,
    # idx_documents_ticker, the evidence_tasks primary key) -- see
    # test_seed_statements_never_scan_a_table.
    who = f"ticker = {quote(ticker)}"
    sql.append(_delete_not_in(
        "facts", who, "fact_id", [row["fact_id"] for row in sections.get("facts") or []],
    ))
    for run in sections.get("runs") or []:
        run_key = run["valuation_run_id"]
        sql.append(_delete_not_in(
            "valuation_components",
            f"valuation_run_id = {quote(run_key)}",
            "component_id",
            [
                row["component_id"]
                for row in sections.get("components") or []
                if row["valuation_run_id"] == run_key
            ],
        ))
    sql.append(_delete_not_in(
        "valuation_runs", who, "valuation_run_id",
        [row["valuation_run_id"] for row in sections.get("runs") or []],
    ))
    sql.append(_delete_not_in(
        "source_documents", who, "document_id",
        [row["document_id"] for row in sections.get("documents") or []],
    ))
    sql.append(_delete_not_in(
        "evidence_tasks", who, "task_id",
        [row["task_id"] for row in sections.get("tasks") or []],
    ))
    return sql


def state_statements(state: dict, imported_at: str) -> list[str]:
    payload = compact_json(state)
    chunks = [
        payload[start:start + STATE_CHUNK_CHARS]
        for start in range(0, len(payload), STATE_CHUNK_CHARS)
    ] or [""]
    keys = [f"{STATE_PREFIX}{index:03d}" for index in range(len(chunks))]
    sql = [
        "INSERT INTO ops_state (key, value, updated_at) VALUES "
        f"({quote(key)}, {quote(chunk)}, {quote(imported_at)}) "
        "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at "
        "WHERE ops_state.value IS NOT excluded.value;"
        for key, chunk in zip(keys, chunks)
    ]
    sql.append(
        f"DELETE FROM ops_state WHERE key >= {quote(STATE_PREFIX)} "
        f"AND key < {quote(STATE_RANGE_END)} AND key NOT IN ({_in_list(keys)});"
    )
    return sql


def render(
    model: dict,
    previous: dict | None,
    *,
    source_sha256: str,
    full: bool = False,
    imported_at: str | None = None,
) -> tuple[list[str], dict]:
    """SQL statements for everything that changed since ``previous``."""
    imported_at = imported_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    per_ticker, globals_hash, content_sha256 = content_hashes(model)
    run_id = f"dashboard:{content_sha256[:16]}"
    previous = None if full else previous
    info = {
        "run_id": run_id,
        "content_sha256": content_sha256,
        "mode": "full" if previous is None else "incremental",
        "changed_ticker_count": 0,
        "removed_ticker_count": 0,
        "globals_changed": False,
        "skip": False,
    }
    if previous is not None and previous.get("content_sha256") == content_sha256:
        info["mode"] = "skip"
        info["skip"] = True
        return [], info

    previous_tickers = (previous or {}).get("tickers") or {}
    changed = [
        ticker for ticker in model["tickers"]
        if previous is None or previous_tickers.get(ticker) != per_ticker[ticker]
    ]
    removed = sorted(set(previous_tickers) - set(model["tickers"])) if previous else []
    globals_changed = previous is None or previous.get("globals") != globals_hash
    info.update({
        "changed_ticker_count": len(changed),
        "removed_ticker_count": len(removed),
        "globals_changed": globals_changed,
    })

    # run_id is derived from the content hash, so an existing row describes
    # identical content: DO NOTHING. (A DO UPDATE branch would also plan
    # foreign-key scans of every table that references pipeline_runs.)
    pipeline_columns = [
        "run_id", "generated_at", "source_sha256", "status", "ticker_count", "summary_json", "imported_at",
    ]
    pipeline_values = [
        run_id, model["generated_at"], source_sha256, "complete",
        len(model["tickers"]), compact_json(model["summary"]), imported_at,
    ]
    sql = [
        "PRAGMA foreign_keys = ON;",
        f"INSERT INTO pipeline_runs ({', '.join(pipeline_columns)}) VALUES "
        f"({', '.join(quote(value) for value in pipeline_values)}) ON CONFLICT (run_id) DO NOTHING;",
    ]
    for ticker in changed:
        sql.extend(_ticker_statements(ticker, model["tickers"][ticker], run_id))
    for batch in _chunks(removed):
        # Cascades to valuation_current, evidence_tasks (-> task_attempts),
        # source_documents, facts and valuation_runs (-> components); every
        # child key it follows is indexed (0001, 0019).
        sql.append(f"DELETE FROM securities WHERE ticker IN ({_in_list(batch)});")
    if previous is None:
        # FULL export: nothing says which securities disappeared since the
        # last seed, so sweep once. The only statement that scans a table,
        # and only on a full export (securities is ~850 rows).
        sql.append(
            "DELETE FROM securities WHERE ticker NOT IN "
            f"({_in_list(sorted(model['tickers']))});"
        )
    if globals_changed:
        sql.extend(
            _row_upsert("criticality_snapshots", ("scope", "symbol", "as_of", "horizon", "model_version"), row, run_id)
            for row in model["criticality"]
        )
        sql.extend(
            _row_upsert("flow_stress_snapshots", ("scope", "symbol", "as_of", "model_version"), row, run_id)
            for row in model["flow"]
        )
    state = {
        "format": SEED_FORMAT,
        "content_sha256": content_sha256,
        "run_id": run_id,
        "globals": globals_hash,
        "tickers": per_ticker,
    }
    sql.extend(state_statements(state, imported_at))
    return sql, info


def export(
    core_path: Path,
    output: Path,
    evidence_queue_path: Path = DEFAULT_EVIDENCE_QUEUE,
    *,
    ops_state: dict[str, str] | None = None,
    full: bool = False,
    technical_summary: dict | None = None,
    criticality_summary: dict | None = None,
    root: Path = ROOT,
) -> dict:
    raw = core_path.read_bytes()
    core = json.loads(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    model = build_model(core, evidence_queue_path, technical_summary, criticality_summary, root)
    previous = load_previous_state(ops_state)
    statements, info = render(model, previous, source_sha256=source_hash, full=full)
    oversized = [len(sql.encode("utf-8")) for sql in statements if len(sql.encode("utf-8")) > MAX_STATEMENT_BYTES]
    if oversized:
        raise SystemExit(
            f"{len(oversized)} seed statement(s) exceed D1's {MAX_STATEMENT_BYTES}-byte limit "
            f"(largest {max(oversized)} bytes); D1 would reject the import."
        )
    header = [
        "-- Generated by _system/scripts/export_dashboard_d1_seed.py",
        f"-- mode={info['mode']} content_sha256={info['content_sha256']} run_id={info['run_id']}",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(header + statements + [""]), encoding="utf-8")

    tickers = model["tickers"]
    report = {
        "run_id": info["run_id"],
        "generated_at": model["generated_at"],
        "source_sha256": source_hash,
        "content_sha256": info["content_sha256"],
        "mode": info["mode"],
        "skip": info["skip"],
        "changed_ticker_count": info["changed_ticker_count"],
        "removed_ticker_count": info["removed_ticker_count"],
        "globals_changed": info["globals_changed"],
        "statement_count": len(statements),
        "ticker_count": len(tickers),
        "task_count": sum(len(s["tasks"]) for s in tickers.values()),
        "blocked_without_source_task_count": model["blocked_without_source_task"],
        "source_document_count": sum(len(s["documents"]) for s in tickers.values()),
        "fact_count": sum(len(s["facts"]) for s in tickers.values()),
        "valuation_run_count": sum(len(s["runs"]) for s in tickers.values()),
        "valuation_component_count": sum(len(s["components"]) for s in tickers.values()),
        "technical_snapshot_count": 0,
        "market_structure_snapshot_count": 0,
        "price_observation_count": 0,
        "criticality_snapshot_count": len(model["criticality"]),
        "flow_stress_snapshot_count": len(model["flow"]),
        "output": output.as_posix(),
        "bytes": output.stat().st_size,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-queue", type=Path, default=DEFAULT_EVIDENCE_QUEUE)
    parser.add_argument(
        "--ops-state",
        type=Path,
        default=None,
        help="JSON object of ops_state key -> value read from D1; absent means a FULL export",
    )
    parser.add_argument("--full", action="store_true", help="ignore the persisted state (re-key everything)")
    parser.add_argument("--report", type=Path, default=None, help="also write the report JSON here")
    args = parser.parse_args()
    ops_state = None
    if args.ops_state is not None and args.ops_state.is_file():
        loaded = read_json(args.ops_state)
        ops_state = {str(k): str(v) for k, v in loaded.items()} if isinstance(loaded, dict) else None
    report = export(
        args.core, args.output, args.evidence_queue, ops_state=ops_state, full=args.full,
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
