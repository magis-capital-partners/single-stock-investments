"""Import dated Magis mirror observations into the one canonical KPI store.

Never executes mirror code. Conflicting same-period numbers retain the repo
observation and both source records for review. Imports never lock facts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from atomic_io import write_json_if_changed
from operating_kpis import model

ALIASES = {
    "CBOE": {"adv_spx": "spx_options_adv", "adv_vix_futures": "vix_futures_adv",
             "options_adv_index": "options_index_adv", "options_adv_multilist": "options_multilist_adv",
             "options_share_multilist": "options_multilist_share", "rpc3m_futures": "futures_rpc",
             "rpc3m_index": "options_index_rpc", "rpc3m_multilist": "options_multilist_rpc"},
    "MIAX": {"equities_capture3m": "equities_capture", "futures_fin_adv": "futures_financial_adv",
             "futures_fin_rpc3m": "futures_financial_rpc", "industry_options_adv": "options_industry_adv",
             "options_rpc3m": "options_rpc"},
    "CME": {"total_adv": "adv_total", "interest_rate_adv": "adv_interest_rate",
            "equity_index_adv": "adv_equity_index", "energy_adv": "adv_energy",
            "agricultural_adv": "adv_agricultural", "fx_adv": "adv_fx", "metals_adv": "adv_metals"},
}


def normalize(row: dict, *, mirror_as_of: str, source_hash: str) -> dict:
    row = dict(row)
    ticker = row["ticker"]
    kpi = ALIASES.get(ticker, {}).get(row["kpi"], row["kpi"])
    value, unit, yoy = row.get("value"), row.get("unit"), row.get("yoy")
    if unit == "contracts_k":
        value *= 1000
        unit = "contracts" if kpi.startswith("oi_") else "contracts_per_day"
    elif unit == "contracts" and "adv" in kpi:
        unit = "contracts_per_day"
    elif unit == "share":
        value *= 100
        yoy = yoy * 100 if yoy is not None else None
        unit = "share_pct"
    elif unit == "pct" and "share" in kpi:
        unit = "share_pct"
    elif unit == "usd_per_100sh":
        unit = "usd_per_100_shares"
    elif unit == "shares_bn" and "adv" in kpi:
        value *= 1_000_000_000
        unit = "shares_per_day"
    point = model.make_point(ticker=ticker, kpi=kpi, period=row["period"], value=value, unit=unit,
                             source_url=row["source_url"], doc=row.get("accession_or_doc") or "",
                             fetched_at=row.get("fetched_at") or mirror_as_of,
                             yoy_basis="percentage_points" if unit in {"share_pct", "pct", "pp"} else "ratio")
    source_unit = row.get("source_unit") or row["unit"]
    precision = row.get("source_precision")
    if precision is None:
        precision = (1000 if source_unit == "shares_bn" else
                     .01 if ticker == "ICE" and source_unit == "share" else
                     .0001 if source_unit == "share" else
                     .1 if source_unit == "pct" else
                     (100 if ticker == "CME" else .1) if source_unit == "contracts_k" else .0001)
    point.update({"yoy": None if "guidance" in kpi else yoy,
                  "source_as_of": (row.get("source_as_of") or row.get("fetched_at") or mirror_as_of)[:10],
                  "observation_period_end": model.period_end(row["period"]).isoformat(),
                  "ingestion_origin": "dated_box_mirror", "mirror_as_of": mirror_as_of,
                  "mirror_sha256": source_hash, "source_kpi": row.get("source_kpi") or row["kpi"], "source_unit": source_unit,
                  "source_precision": precision,
                  "claim_type": "inference", "source_verification": "mirror_unverified_not_a_valuation_fact"})
    if row.get("note") == "yoy as reported":
        point["yoy_origin"] = "issuer_reported"
    return point


def comparable(left: dict, right: dict) -> bool:
    # Existing Cboe/Miax adapters explicitly round daily contract counts to
    # whole contracts. Preserve those readings and compare their precision.
    left_precision = left.get("source_precision")
    if left_precision is None and left.get("unit") == "contracts_per_day" and float(left["value"]).is_integer():
        left_precision = 1
    tolerance = max(1e-6, float(left_precision or 0) / 2,
                    float(right.get("source_precision") or 0) / 2)
    return left["unit"] == right["unit"] and abs(left["value"] - right["value"]) <= tolerance + 1e-9


def import_mirror(directory: Path, *, tickers: set[str], root: Path) -> dict:
    path = directory / "kpi_tracker/operating_kpis.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != "magis.fa_kpi_tracker.operating_kpis.v1":
        raise ValueError("Unsupported mirror observation schema")
    stamp = payload["generated_at"]
    file_hash = hashlib.sha256(raw).hexdigest()
    grouped = {}
    for row in payload["rows"]:
        if row.get("ticker") not in tickers or row.get("value") is None or not model.period_end(row.get("period")):
            continue
        if not row.get("source_url", "").startswith("https://"):
            continue
        grouped.setdefault(row["ticker"], []).append(normalize(row, mirror_as_of=stamp, source_hash=file_hash))
    old_dir = model.STORE_DIR
    model.STORE_DIR = root / "_system/reference/market-data/operating_kpis"
    counts, total_conflicts = {}, 0
    try:
        for ticker, points in grouped.items():
            previous = model.load_ticker_store(ticker) or {}
            existing = {(p["kpi"], p["period"]): p for p in previous.get("points") or []}
            accepted, conflicts = [], list(previous.get("conflicts") or [])
            # Migrate earlier mirror observations through the same explicit
            # unit normalizer; keep the original in the store's revisions.
            for key, old in list(existing.items()):
                if old.get("ingestion_origin") == "dated_box_mirror":
                    normalized = normalize(old, mirror_as_of=old.get("mirror_as_of") or stamp,
                                           source_hash=old.get("mirror_sha256") or file_hash)
                    if (old["unit"], old["value"]) != (normalized["unit"], normalized["value"]):
                        accepted.append(normalized)
                        existing[key] = normalized
            for conflict in conflicts:
                normalized = normalize(conflict["mirror"], mirror_as_of=stamp, source_hash=file_hash)
                old = conflict["repo"]
                if old.get("ingestion_origin") == "dated_box_mirror":
                    old = normalize(old, mirror_as_of=stamp, source_hash=file_hash)
                if comparable(old, normalized):
                    conflict["status"] = "resolved_unit_normalization"
                    conflict["resolution"] = {"canonical_value": normalized["value"], "unit": normalized["unit"],
                                              "rule": "Explicit unit conversion; source precision retained.", "as_of": stamp}
            for point in points:
                old = existing.get((point["kpi"], point["period"]))
                if old and not comparable(old, point):
                    conflict = {"repo": old, "mirror": point, "status": "pending_review"}
                    if conflict not in conflicts:
                        conflicts.append(conflict)
                    continue
                if not old:
                    accepted.append(point)
            sources = list(previous.get("sources") or [])
            source = {"status": "ok", "ticker": ticker, "source_url": str(path),
                      "as_of": stamp, "content_sha256": file_hash, "claim_type": "inference"}
            if source not in sources:
                sources.append(source)
            store_path = model.write_ticker_store(ticker, accepted, sources=sources, fetched_at=stamp)
            stored = json.loads(store_path.read_text(encoding="utf-8"))
            stored["conflicts"] = conflicts
            write_json_if_changed(store_path, stored)
            counts[ticker] = len(accepted)
            total_conflicts += sum(c.get("status") == "pending_review" for c in conflicts)
    finally:
        model.STORE_DIR = old_dir
    return {"as_of": stamp, "source": str(path), "content_sha256": file_hash,
            "imported": counts, "conflicts": total_conflicts}


def royalty_signals(directory: Path, tickers: set[str]) -> dict:
    path = directory / "royalties/state.json"
    if not path.exists():
        return {}
    state = json.loads(path.read_text(encoding="utf-8"))
    conditions = state.get("conditions") or {}
    active = state.get("active_conditions") or []
    return {ticker: {"active": any(c.get("ticker") == ticker for c in active),
                     "rules": [c for c in active if c.get("ticker") == ticker],
                     "source": str(path), "as_of": state.get("last_run"), "claim_type": "inference"}
            for ticker in tickers if ticker in conditions}
