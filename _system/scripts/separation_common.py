#!/usr/bin/env python3
"""Shared schema, loaders and gates for corporate separations.

A separation is a split-off exchange offer, a spin-off distribution, a
carve-out IPO, a clean-up distribution, a retained-stake sale, or a Reverse
Morris Trust.  The register is append-only JSONL (the warrant pattern):
contract terms live in the registry and its amendments; flows, cohorts and
outcomes are separate point-in-time files so a model re-run can never rewrite
a published row.

Nothing here has trading authority.  Every payload the dashboard reads carries
``research_only``, ``in_base_irr: false`` and ``authority: "none"``.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
SEPARATION_DIR = ROOT / "_system" / "data" / "separations"
REGISTRY_PATH = SEPARATION_DIR / "separation_registry.jsonl"
AMENDMENTS_PATH = SEPARATION_DIR / "separation_amendments.jsonl"
EVENTS_PATH = SEPARATION_DIR / "separation_events.jsonl"
FLOWS_PATH = SEPARATION_DIR / "separation_flows.jsonl"
COHORTS_PATH = SEPARATION_DIR / "separation_cohorts.jsonl"
OUTCOMES_PATH = SEPARATION_DIR / "separation_outcomes.jsonl"
CALIBRATION_PATH = SEPARATION_DIR / "separation_calibration.json"
DISCOVERY_STATE_PATH = SEPARATION_DIR / "discovery_state.json"
DASHBOARD_PATH = ROOT / "dashboard" / "data" / "separations.json"

SCHEMA_VERSION = "separations.v1"

KINDS = {
    "split_off",
    "spin_off",
    "carve_out_ipo",
    "clean_up_spin",
    "retained_stake_sale",
    "reverse_morris_trust",
}
STATUSES = {
    "announced",
    "filed",
    "when_issued",
    "offer_open",
    "valuation_period",
    "completed",
    "withdrawn",
}
LIFECYCLES = {"candidate", "active", "closed"}
SIDES = {"parent", "spinco"}
EVENT_STATUSES = {"unreviewed", "linked", "dismissed"}

# Forms that can carry separation terms. Discovery searches these; the
# downloader pulls them for registered tickers.
SEPARATION_FORMS = (
    "10-12B",
    "10-12B/A",
    "S-4",
    "S-4/A",
    "424B3",
    "SC TO-I",
    "SC TO-I/A",
    "8-K",
    "425",
)

RESEARCH_ONLY = {"research_only": True, "in_base_irr": False, "authority": "none"}

CAPTION = (
    "Forced selling is a research trigger and a timing input. It does not change "
    "intrinsic value, and the average post-spin excess return has compressed as the "
    "trade became known. A spread without a filed formula is a headline."
)


# --------------------------------------------------------------------------- io
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return date.today().isoformat()


def parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False, newline="\n"
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def append_jsonl(path: Path, rows: Iterable[dict], *, identity_key: str | None = None) -> int:
    """Append rows; with ``identity_key`` the first write of an id wins."""
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = list(rows)
    if not incoming:
        return 0
    existing: set[str] = set()
    if identity_key and path.exists():
        for row in load_jsonl(path):
            value = row.get(identity_key)
            if value is not None:
                existing.add(str(value))
    added = [r for r in incoming if not identity_key or str(r.get(identity_key)) not in existing]
    if not added:
        return 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in added:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return len(added)


def stable_id(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------------- registry
def latest_registry(rows: list[dict] | None = None) -> list[dict]:
    """Highest version per separation_id across registry + amendments."""
    rows = rows if rows is not None else (load_jsonl(REGISTRY_PATH) + load_jsonl(AMENDMENTS_PATH))
    latest: dict[str, dict] = {}
    for row in rows:
        sid = str(row.get("separation_id") or "")
        if not sid:
            continue
        current = latest.get(sid)
        if current is None or int(row.get("version") or 0) > int(current.get("version") or 0):
            latest[sid] = row
    return sorted(
        latest.values(),
        key=lambda row: (
            str(row.get("lifecycle")),
            str((row.get("dates") or {}).get("settlement") or (row.get("dates") or {}).get("distribution") or ""),
            str(row.get("parent_ticker")),
        ),
    )


def registry_by_id(rows: list[dict] | None = None) -> dict[str, dict]:
    return {str(r.get("separation_id")): r for r in latest_registry(rows)}


def validate_registry(rows: list[dict] | None = None) -> list[str]:
    rows = rows if rows is not None else (load_jsonl(REGISTRY_PATH) + load_jsonl(AMENDMENTS_PATH))
    errors: list[str] = []
    seen_versions: set[tuple[str, int]] = set()
    for index, row in enumerate(rows):
        prefix = f"row[{index}]"
        sid = str(row.get("separation_id") or "")
        if not sid.startswith("sep:"):
            errors.append(f"{prefix}: separation_id must start with 'sep:'")
        try:
            version = int(row.get("version"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}: version must be an integer")
            version = 0
        if version < 1:
            errors.append(f"{prefix}: version must be >= 1")
        key = (sid, version)
        if key in seen_versions:
            errors.append(f"{prefix}: duplicate version {version} for {sid}")
        seen_versions.add(key)
        if row.get("kind") not in KINDS:
            errors.append(f"{prefix}: kind must be one of {sorted(KINDS)}")
        if row.get("status") not in STATUSES:
            errors.append(f"{prefix}: status must be one of {sorted(STATUSES)}")
        if row.get("lifecycle") not in LIFECYCLES:
            errors.append(f"{prefix}: lifecycle must be one of {sorted(LIFECYCLES)}")
        if not row.get("parent_ticker"):
            errors.append(f"{prefix}: parent_ticker required")
        if not isinstance(row.get("dates"), dict):
            errors.append(f"{prefix}: dates object required")
        if not isinstance(row.get("terms"), dict):
            errors.append(f"{prefix}: terms object required")
        sources = row.get("sources")
        if not isinstance(sources, list):
            errors.append(f"{prefix}: sources list required")
        else:
            for j, src in enumerate(sources):
                if not isinstance(src, dict) or not (src.get("accession") or src.get("url")):
                    errors.append(f"{prefix}.sources[{j}]: accession or url required")
        if row.get("lifecycle") == "active" and not sources:
            errors.append(f"{prefix}: an active separation needs at least one filing source")
    return errors


# -------------------------------------------------------------------------- gates
def _has(value: object) -> bool:
    return value not in (None, "", [], {})


def gate_state(record: dict) -> dict:
    """Identity and terms gates. A row is ``ranked`` only when both pass.

    identity: parent ticker + CIK; SpinCo ticker may be pending before listing
    but then the SpinCo name is required.
    terms: split_off needs discount, upper limit, expiration; spin_off needs
    distribution ratio and distribution date; every kind needs a filing source.
    """
    terms = record.get("terms") or {}
    dates = record.get("dates") or {}
    exchange = terms.get("exchange") or {}
    kind = record.get("kind")
    sources = record.get("sources") or []

    identity_missing: list[str] = []
    if not _has(record.get("parent_ticker")):
        identity_missing.append("parent_ticker")
    if not _has(record.get("parent_cik")):
        identity_missing.append("parent_cik")
    if not _has(record.get("spinco_ticker")) and not _has(record.get("spinco_name")):
        identity_missing.append("spinco_ticker_or_name")

    terms_missing: list[str] = []
    if not sources:
        terms_missing.append("filing_source")
    if kind == "split_off":
        for field in ("discount_pct", "upper_limit_ratio"):
            if not _has(exchange.get(field)):
                terms_missing.append(f"exchange.{field}")
        if not _has(dates.get("expiration")):
            terms_missing.append("dates.expiration")
    elif kind in {"spin_off", "clean_up_spin"}:
        if not _has(terms.get("distribution_ratio")):
            terms_missing.append("terms.distribution_ratio")
        if not _has(dates.get("distribution")):
            terms_missing.append("dates.distribution")
    elif kind == "retained_stake_sale":
        if not _has(terms.get("retained_stake_pct")):
            terms_missing.append("terms.retained_stake_pct")
    elif kind == "carve_out_ipo":
        if not _has(terms.get("ipo_float_pct")):
            terms_missing.append("terms.ipo_float_pct")
    elif kind == "reverse_morris_trust":
        if not _has(terms.get("distribution_ratio")) and not _has(exchange.get("discount_pct")):
            terms_missing.append("terms.distribution_ratio_or_exchange")

    identity_ok = not identity_missing
    terms_ok = not terms_missing
    return {
        "identity": {"pass": identity_ok, "missing": identity_missing},
        "terms": {"pass": terms_ok, "missing": terms_missing},
        "status": "ranked" if identity_ok and terms_ok else "discovery",
    }


def end_date(record: dict) -> str | None:
    """The date the situation ends for desk sorting: settlement, then distribution."""
    dates = record.get("dates") or {}
    for key in ("settlement", "expiration", "distribution", "clean_up_distribution"):
        if dates.get(key):
            return str(dates[key])[:10]
    return None


def tickers_of(record: dict) -> list[str]:
    out = []
    for key in ("parent_ticker", "spinco_ticker"):
        value = record.get(key)
        if value:
            out.append(str(value).upper())
    return out


def new_record(
    *,
    separation_id: str,
    kind: str,
    parent_ticker: str,
    parent_cik: str | None,
    spinco_ticker: str | None,
    spinco_cik: str | None,
    spinco_name: str | None,
    status: str,
    lifecycle: str,
    dates: dict,
    terms: dict,
    sources: list[dict],
    notes: str = "",
    market: str = "US",
    version: int = 1,
) -> dict:
    return {
        "separation_id": separation_id,
        "version": version,
        "recorded_at": utc_now(),
        "kind": kind,
        "market": market,
        "parent_ticker": parent_ticker.upper(),
        "parent_cik": str(parent_cik).zfill(10) if parent_cik else None,
        "spinco_ticker": spinco_ticker.upper() if spinco_ticker else None,
        "spinco_cik": str(spinco_cik).zfill(10) if spinco_cik else None,
        "spinco_name": spinco_name,
        "status": status,
        "lifecycle": lifecycle,
        "dates": dates,
        "terms": terms,
        "sources": sources,
        "notes": notes,
    }


def record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k not in {"recorded_at"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def with_authority(payload: dict) -> dict:
    payload.update(RESEARCH_ONLY)
    return payload
