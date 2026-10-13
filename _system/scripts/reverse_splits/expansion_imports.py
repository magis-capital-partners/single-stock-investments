"""Auditable file imports for evidence unavailable from public SEC APIs.

All files require source attribution and explicit times/units. Imports never
connect to TWS, a Gateway or a market-data terminal, and never imply that a
vendor's inventory was an approved locate.
"""

import csv
import json
import math
from datetime import date, datetime
from pathlib import Path

from .expansion import connect, digest, export_coverage, job, utcnow

TEMPLATES = {
    "security": [
        "security_id",
        "cik",
        "ticker",
        "valid_from",
        "valid_to",
        "exchange",
        "currency",
        "kind",
        "verified",
        "source_url",
    ],
    "action": [
        "security_id",
        "ticker",
        "ex_date",
        "ratio",
        "announced_at",
        "verified",
        "source_url",
    ],
    "price": [
        "security_id",
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "nominal",
        "session_basis",
        "source_url",
    ],
    "quote": [
        "security_id",
        "ticker",
        "timestamp",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "session_point",
        "source_url",
    ],
    "borrow": [
        "security_id",
        "ticker",
        "timestamp",
        "shares",
        "fee_annual_fraction",
        "approved",
        "locate_reference",
        "source_url",
    ],
    "margin": [
        "security_id",
        "ticker",
        "timestamp",
        "initial_fraction",
        "maintenance_fraction",
        "minimum_per_share",
        "source_url",
    ],
    "fact": [
        "cik",
        "ticker",
        "metric",
        "period",
        "available_at",
        "value",
        "unit",
        "accession",
        "source_url",
    ],
    "thesis": [
        "accession",
        "available_at",
        "framework",
        "mechanism",
        "market_belief",
        "downside_fraction",
        "catalyst",
        "contrary_evidence",
        "falsifier",
        "source_url",
    ],
    "decision": ["accession", "available_at", "decision", "reason", "source_url"],
    "portfolio": ["date", "nav", "net_flow", "sleeve_capital_included", "source_url"],
    "holding": ["date", "security_id", "ticker", "market_value", "source_url"],
}


def boolean(value):
    if value in (True, "true", "True", "1", 1):
        return True
    if value in (False, "false", "False", "0", 0):
        return False
    raise ValueError("Use explicit true/false values")


def number(value, *, minimum=None, maximum=None):
    result = float(value)
    if (
        not math.isfinite(result)
        or minimum is not None
        and result < minimum
        or maximum is not None
        and result > maximum
    ):
        raise ValueError("Nonfinite or out-of-range number")
    return result


def timestamp(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None or len(value) <= 10:
        raise ValueError("A timestamp must include time and timezone")
    return moment.isoformat()


def validate(kind, row):
    required = TEMPLATES[kind]
    missing = [k for k in required if k not in row]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    r = dict(row)
    if not r["source_url"]:
        raise ValueError("Source attribution is required")
    for key in ("timestamp", "available_at", "announced_at"):
        if key in r:
            r[key] = timestamp(r[key])
    for key in ("date", "valid_from", "ex_date", "period"):
        if key in r:
            r[key] = date.fromisoformat(r[key]).isoformat()
    if kind == "security":
        if r["valid_to"]:
            r["valid_to"] = date.fromisoformat(r["valid_to"]).isoformat()
            if r["valid_to"] < r["valid_from"]:
                raise ValueError("Security interval ends before it starts")
        r["verified"] = boolean(r["verified"])
        if not str(r["cik"]).isdigit() or not r["security_id"] or not r["ticker"]:
            raise ValueError("Security identity is incomplete")
    elif kind == "action":
        r["ratio"] = number(r["ratio"], minimum=1e-12)
        if r["ratio"] == 1:
            raise ValueError("A corporate share adjustment must change the quantity")
        r["verified"] = boolean(r["verified"])
    elif kind == "price":
        r["nominal"] = boolean(r["nominal"])
        if not r["nominal"] or r["currency"] != "USD":
            raise ValueError(
                "Replay price imports require nominal USD OHLCV; convert with an audited source first"
            )
        if r["session_basis"] not in {"regular_session", "official_auction"}:
            raise ValueError(
                "Price imports must explicitly identify regular-session or official-auction benchmarks"
            )
        for k in ("open", "high", "low", "close"):
            r[k] = number(r[k], minimum=1e-12)
        r["volume"] = number(r["volume"], minimum=0)
        if (
            r["low"] > min(r["open"], r["close"])
            or r["high"] < max(r["open"], r["close"])
            or r["low"] > r["high"]
        ):
            raise ValueError("Invalid OHLC bounds")
    elif kind == "quote":
        for k in ("bid", "ask"):
            r[k] = number(r[k], minimum=1e-12)
        for k in ("bid_size", "ask_size"):
            r[k] = number(r[k], minimum=0)
        if r["ask"] < r["bid"] or r["session_point"] not in {"open", "close"}:
            raise ValueError("Crossed quote or invalid session point")
    elif kind == "borrow":
        r["shares"] = number(r["shares"], minimum=0)
        r["fee_annual_fraction"] = number(r["fee_annual_fraction"], minimum=0)
        r["approved"] = boolean(r["approved"])
        if r["approved"] and not r["locate_reference"]:
            raise ValueError("Approval requires an actual locate reference")
    elif kind == "margin":
        for k in ("initial_fraction", "maintenance_fraction", "minimum_per_share"):
            r[k] = number(r[k], minimum=0)
    elif kind == "fact":
        r["value"] = number(r["value"])
        if (
            not str(r["cik"]).isdigit()
            or not r["accession"]
            or r["unit"] not in {"USD", "shares", "USD/shares", "pure"}
        ):
            raise ValueError(
                "Fact requires issuer, accession and explicit supported unit"
            )
        if r["available_at"][:10] < r["period"]:
            raise ValueError("Fact published before its period ends")
    elif kind == "thesis":
        r["downside_fraction"] = number(r["downside_fraction"], minimum=0, maximum=1)
        if any(
            not r[k].strip()
            for k in (
                "framework",
                "mechanism",
                "market_belief",
                "catalyst",
                "contrary_evidence",
                "falsifier",
            )
        ):
            raise ValueError(
                "Thesis requires mechanism, contrary evidence, catalyst and falsifier"
            )
    elif kind == "decision":
        if (
            r["decision"] not in {"research", "pass", "paper", "trade"}
            or not r["reason"]
        ):
            raise ValueError("Decision requires a recognized action and reason")
    elif kind == "portfolio":
        r["nav"] = number(r["nav"], minimum=1)
        r["net_flow"] = number(r["net_flow"])
        r["sleeve_capital_included"] = boolean(r["sleeve_capital_included"])
    elif kind == "holding":
        r["market_value"] = number(r["market_value"])
    return r


def import_evidence(cfg, kind, path):
    if kind not in TEMPLATES:
        raise ValueError("Unknown evidence kind")
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [validate(kind, r) for r in csv.DictReader(handle)]
    conn = connect(cfg)
    sha = digest(path)
    try:
        with conn:
            for r in rows:
                at = (
                    r.get("timestamp")
                    or r.get("available_at")
                    or r.get("announced_at")
                    or r.get("date")
                    or r.get("valid_from")
                )
                identity = (
                    r.get("security_id")
                    or r.get("cik")
                    or r.get("accession")
                    or "owner"
                )
                key = f"{identity}/{r.get('ticker', '')}/{r.get('metric', '')}/{r.get('period', '')}/{r.get('session_point', '')}"
                # Immutable evidence vintages: amendments require another time.
                old = conn.execute(
                    "SELECT data_json FROM evidence_imports WHERE kind=? AND key=? AND available_at=?",
                    (kind, key, at),
                ).fetchone()
                payload = json.dumps(r, sort_keys=True, allow_nan=False)
                if old and old["data_json"] != payload:
                    raise ValueError(
                        "A frozen evidence vintage cannot be overwritten; supply a revision timestamp"
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO evidence_imports VALUES (?,?,?,?,?)",
                    (kind, key, at, payload, sha),
                )
                if kind == "security":
                    intervals = conn.execute(
                        "SELECT * FROM security_history WHERE ticker=? AND verified=1",
                        (r["ticker"],),
                    ).fetchall()
                    for old in intervals:
                        if old["security_id"] != r["security_id"] and max(
                            old["valid_from"], r["valid_from"]
                        ) <= min(old["valid_to"] or "9999", r["valid_to"] or "9999"):
                            raise ValueError("Conflicting verified security intervals")
                    conn.execute(
                        "INSERT OR IGNORE INTO security_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                        tuple(r[k] for k in TEMPLATES["security"]),
                    )
                elif kind == "action":
                    conn.execute(
                        "INSERT OR IGNORE INTO independent_actions VALUES (?,?,?,?,?,?,?,?)",
                        tuple(r[k] for k in TEMPLATES["action"]) + (sha,),
                    )
                elif kind in {"thesis", "decision"}:
                    conn.execute(
                        "INSERT INTO review_revisions(accession,recorded_at,data_json) VALUES (?,?,?)",
                        (
                            r["accession"],
                            utcnow(),
                            json.dumps(
                                {
                                    **r,
                                    "import_kind": kind,
                                    "retrospective_import": r["available_at"]
                                    < utcnow(),
                                }
                            ),
                        ),
                    )
        job(
            conn,
            "import",
            f"{kind}/{sha}",
            "completed",
            {"rows": len(rows), "file": path.name},
        )
        export_coverage(cfg, conn)
    finally:
        conn.close()
    return {"kind": kind, "rows": len(rows), "sha256": sha}


def write_templates(cfg):
    root = cfg.local_dir / "expansion_imports"
    root.mkdir(parents=True, exist_ok=True)
    for kind, columns in TEMPLATES.items():
        with (root / (kind + ".csv")).open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(columns)
    return root


def evidence(conn, kind):
    return [
        json.loads(r[0])
        for r in conn.execute(
            "SELECT data_json FROM evidence_imports WHERE kind=? ORDER BY available_at",
            (kind,),
        )
    ]
