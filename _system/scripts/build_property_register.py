#!/usr/bin/env python3
"""Validate {TICKER}/research/properties.json and roll a summary into valuation.json.

Reconciliation: sum of property estimated_fair_value_usd.base (or carrying_value_usd)
grouped by nav_overlay_line must match the corresponding nav_overlay target within
tolerance (default 5%, min $1M).

Target resolution order for each nav_overlay_line id:
  1. nav_overlay.lines[] with matching id → fair_value_m / carrying_value_m / |net_m| (millions)
  2. nav_overlay.segments_or_options[] with matching id → overlay_value_per_share or nav_per_share × shares
  3. gaap:<field> → nav_overlay.gaap_vs_fair_value[field] as millions

Usage:
  python _system/scripts/build_property_register.py STHO
  python _system/scripts/build_property_register.py STHO --check   # no write
  python _system/scripts/build_property_register.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

REQUIRED_TOP = ("schema_version", "ticker", "as_of", "properties")
REQUIRED_PROP = ("id", "name", "type", "status", "nav_overlay_line")
ALLOWED_TYPES = frozenset({
    "land", "land_development", "operating_real_estate", "farmland", "ground_lease",
    "water_rights", "mineral_rights", "royalty_acres", "pipeline", "equity_stake",
    "loan", "securities", "other",
})
ALLOWED_STATUS = frozenset({
    "held", "under_contract", "sold", "option", "mark", "development",
})
DEFAULT_TOLERANCE_PCT = 0.05
DEFAULT_TOLERANCE_FLOOR_USD = 1_000_000.0


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Failed to read {path}: {exc}") from exc


def _shares(val: dict[str, Any]) -> float:
    inp = val.get("inputs") or {}
    if inp.get("shares_outstanding"):
        return float(inp["shares_outstanding"])
    for key in ("scenarios", "nav_overlay"):
        block = val.get(key) or {}
        if key == "scenarios":
            block = (block.get("base") or {}).get("sotp_build") or {}
        elif key == "nav_overlay":
            block = block.get("sotp_build") or {}
        if block.get("shares"):
            return float(block["shares"])
    return 0.0


def _line_target_usd(line: dict[str, Any]) -> float | None:
    for key in ("fair_value_m", "carrying_value_m"):
        if line.get(key) is not None:
            return abs(float(line[key])) * 1_000_000.0
    if line.get("net_m") is not None:
        return abs(float(line["net_m"])) * 1_000_000.0
    return None


def _segment_target_usd(seg: dict[str, Any], shares: float) -> float | None:
    if shares <= 0:
        return None
    if seg.get("overlay_value_per_share") is not None:
        return abs(float(seg["overlay_value_per_share"])) * shares
    if seg.get("nav_per_share") is not None:
        return abs(float(seg["nav_per_share"])) * shares
    return None


def build_targets(val: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map overlay id → {target_usd, source}."""
    overlay = val.get("nav_overlay") or {}
    shares = _shares(val)
    targets: dict[str, dict[str, Any]] = {}

    for line in overlay.get("lines") or []:
        lid = line.get("id")
        if not lid:
            continue
        usd = _line_target_usd(line)
        if usd is not None:
            targets[str(lid)] = {
                "target_usd": usd,
                "source": f"nav_overlay.lines[{lid}]",
            }

    for seg in overlay.get("segments_or_options") or []:
        sid = seg.get("id")
        if not sid:
            continue
        usd = _segment_target_usd(seg, shares)
        if usd is not None:
            targets[str(sid)] = {
                "target_usd": usd,
                "source": f"nav_overlay.segments_or_options[{sid}]",
                "shares": shares,
            }

    gaap = overlay.get("gaap_vs_fair_value") or {}
    for key, raw in gaap.items():
        if not isinstance(raw, (int, float)):
            continue
        # Prefer million-denominated fields (…_m) and treat other numeric AF/acre counts as non-targets
        if key.endswith("_m") or key.endswith("_usd"):
            scale = 1_000_000.0 if key.endswith("_m") else 1.0
            targets[f"gaap:{key}"] = {
                "target_usd": abs(float(raw)) * scale,
                "source": f"nav_overlay.gaap_vs_fair_value.{key}",
            }
    return targets


def property_value_usd(prop: dict[str, Any]) -> float | None:
    fv = prop.get("estimated_fair_value_usd") or {}
    if isinstance(fv, dict) and fv.get("base") is not None:
        return float(fv["base"])
    if prop.get("carrying_value_usd") is not None:
        return float(prop["carrying_value_usd"])
    return None


def validate_schema(reg: dict[str, Any], ticker: str) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP:
        if key not in reg:
            errors.append(f"missing top-level key: {key}")
    if reg.get("schema_version") != 1:
        errors.append(f"schema_version must be 1, got {reg.get('schema_version')!r}")
    if reg.get("ticker") and str(reg["ticker"]).upper() != ticker.upper():
        errors.append(f"ticker mismatch: file={reg.get('ticker')} expected={ticker}")
    as_of = reg.get("as_of")
    if as_of and not (isinstance(as_of, str) and len(as_of) == 10 and as_of[4] == "-"):
        errors.append(f"as_of must be YYYY-MM-DD, got {as_of!r}")
    props = reg.get("properties")
    if not isinstance(props, list) or not props:
        errors.append("properties must be a non-empty array")
        return errors
    seen: set[str] = set()
    for i, prop in enumerate(props):
        if not isinstance(prop, dict):
            errors.append(f"properties[{i}] must be an object")
            continue
        for key in REQUIRED_PROP:
            if not prop.get(key):
                errors.append(f"properties[{i}] missing {key}")
        pid = prop.get("id")
        if pid:
            if pid in seen:
                errors.append(f"duplicate property id: {pid}")
            seen.add(str(pid))
        if prop.get("type") and prop["type"] not in ALLOWED_TYPES:
            errors.append(f"properties[{i}] invalid type: {prop.get('type')}")
        if prop.get("status") and prop["status"] not in ALLOWED_STATUS:
            errors.append(f"properties[{i}] invalid status: {prop.get('status')}")
        if property_value_usd(prop) is None and prop.get("reconcile", True) is not False:
            errors.append(
                f"properties[{i}] ({pid}) needs estimated_fair_value_usd.base or carrying_value_usd"
            )
    return errors


def reconcile(
    reg: dict[str, Any],
    val: dict[str, Any],
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    floor_usd: float = DEFAULT_TOLERANCE_FLOOR_USD,
) -> dict[str, Any]:
    targets = build_targets(val)
    by_line: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    for prop in reg.get("properties") or []:
        if prop.get("reconcile") is False:
            skipped.append(str(prop.get("id")))
            continue
        line = str(prop.get("nav_overlay_line") or "")
        by_line.setdefault(line, []).append(prop)

    line_results = []
    ok = True
    unknown_lines: list[str] = []
    for line_id, props in sorted(by_line.items()):
        summed = sum(property_value_usd(p) or 0.0 for p in props)
        target_meta = targets.get(line_id)
        if target_meta is None:
            unknown_lines.append(line_id)
            line_results.append({
                "nav_overlay_line": line_id,
                "property_ids": [p.get("id") for p in props],
                "sum_usd": round(summed, 2),
                "target_usd": None,
                "delta_usd": None,
                "status": "unknown_target",
            })
            ok = False
            continue
        target = float(target_meta["target_usd"])
        delta = summed - target
        tol = max(floor_usd, abs(target) * tolerance_pct)
        matched = abs(delta) <= tol
        if not matched:
            ok = False
        line_results.append({
            "nav_overlay_line": line_id,
            "property_ids": [p.get("id") for p in props],
            "sum_usd": round(summed, 2),
            "target_usd": round(target, 2),
            "delta_usd": round(delta, 2),
            "tolerance_usd": round(tol, 2),
            "source": target_meta.get("source"),
            "status": "ok" if matched else "mismatch",
        })

    total_base = sum(
        property_value_usd(p) or 0.0
        for p in (reg.get("properties") or [])
        if p.get("reconcile") is not False
    )
    return {
        "ok": ok and not unknown_lines,
        "tolerance_pct": tolerance_pct,
        "lines": line_results,
        "unknown_targets": unknown_lines,
        "skipped_property_ids": skipped,
        "total_fair_value_usd": round(total_base, 2),
        "property_count": len(reg.get("properties") or []),
    }


def build_summary(reg: dict[str, Any], recon: dict[str, Any], ticker: str) -> dict[str, Any]:
    props = reg.get("properties") or []
    types: dict[str, int] = {}
    for p in props:
        t = str(p.get("type") or "other")
        types[t] = types.get(t, 0) + 1
    return {
        "status": "ok" if recon.get("ok") else "needs_review",
        "as_of": reg.get("as_of"),
        "source": reg.get("source"),
        "in_base_irr": bool(reg.get("in_base_irr", False)),
        "property_count": recon.get("property_count", len(props)),
        "total_fair_value_usd": recon.get("total_fair_value_usd"),
        "total_fair_value_m": round((recon.get("total_fair_value_usd") or 0) / 1_000_000.0, 3),
        "types": types,
        "reconciliation": {
            "ok": recon.get("ok"),
            "unknown_targets": recon.get("unknown_targets") or [],
            "lines": recon.get("lines") or [],
        },
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "register_path": f"{ticker}/research/properties.json",
    }


def process_ticker(
    ticker: str,
    *,
    write: bool = True,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> dict[str, Any]:
    ticker = ticker.upper() if not ticker.endswith(".T") else ticker
    # Preserve exotic tickers as folder names
    folder = ticker if (ROOT / ticker).is_dir() else ticker.upper()
    if not (ROOT / folder).is_dir():
        # try original case
        folder = ticker
    research = ROOT / folder / "research"
    reg_path = research / "properties.json"
    val_path = research / "valuation.json"
    if not reg_path.exists():
        return {"ticker": folder, "skipped": True, "reason": "no properties.json"}

    reg = _load_json(reg_path) or {}
    errors = validate_schema(reg, folder)
    val = _load_json(val_path) or {}
    if not val and write:
        return {"ticker": folder, "ok": False, "errors": errors + ["missing valuation.json"]}

    recon = reconcile(reg, val, tolerance_pct=tolerance_pct) if val else {
        "ok": False,
        "lines": [],
        "unknown_targets": [],
        "property_count": len(reg.get("properties") or []),
        "total_fair_value_usd": 0,
    }
    if errors:
        recon["ok"] = False

    summary = build_summary(reg, recon, folder)
    result = {
        "ticker": folder,
        "ok": bool(recon.get("ok")) and not errors,
        "errors": errors,
        "summary": summary,
        "reconciliation": recon,
    }

    if write and val_path.exists():
        val["property_register"] = summary
        val_path.write_text(json.dumps(val, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result["wrote"] = str(val_path.relative_to(ROOT)).replace("\\", "/")
    return result


def discover_tickers() -> list[str]:
    found = []
    for path in ROOT.glob("*/research/properties.json"):
        found.append(path.parent.parent.name)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ticker", nargs="?", help="Ticker folder (or --all)")
    ap.add_argument("--all", action="store_true", help="Process every properties.json")
    ap.add_argument("--check", action="store_true", help="Validate only; do not write valuation.json")
    ap.add_argument(
        "--tolerance-pct",
        type=float,
        default=DEFAULT_TOLERANCE_PCT,
        help="Relative reconciliation tolerance (default 0.05)",
    )
    args = ap.parse_args(argv)

    if args.all:
        tickers = discover_tickers()
    elif args.ticker:
        tickers = [args.ticker]
    else:
        ap.error("Provide TICKER or --all")
        return 2

    exit_ok = True
    for t in tickers:
        result = process_ticker(t, write=not args.check, tolerance_pct=args.tolerance_pct)
        if result.get("skipped"):
            print(f"{result['ticker']}: skip ({result.get('reason')})")
            continue
        status = "OK" if result.get("ok") else "REVIEW"
        if not result.get("ok"):
            exit_ok = False
        summary = result.get("summary") or {}
        print(
            f"{result['ticker']}: {status} "
            f"n={summary.get('property_count')} "
            f"FV=${summary.get('total_fair_value_m')}m "
            f"recon={summary.get('reconciliation', {}).get('ok')}"
        )
        for err in result.get("errors") or []:
            print(f"  schema: {err}")
        for line in (result.get("reconciliation") or {}).get("lines") or []:
            if line.get("status") != "ok":
                print(
                    f"  line {line.get('nav_overlay_line')}: "
                    f"{line.get('status')} sum={line.get('sum_usd')} "
                    f"target={line.get('target_usd')} delta={line.get('delta_usd')}"
                )
        if result.get("wrote"):
            print(f"  wrote {result['wrote']}")
    return 0 if exit_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
